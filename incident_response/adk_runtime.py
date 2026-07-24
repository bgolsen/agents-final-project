"""Helpers for driving a (possibly remote, A2A-connected) ADK agent from
plain Python code and turning its final response into a validated Pydantic
model.
"""
from __future__ import annotations

import asyncio
from typing import TypeVar

from google.adk.agents import BaseAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from incident_response.tracing import logger

T = TypeVar("T", bound=BaseModel)


class AgentInvocationError(RuntimeError):
    """Raised when an agent (local or remote-via-A2A) fails to produce a
    usable response, after any in-agent fallback has already been tried."""


async def run_agent_once(
    agent: BaseAgent,
    prompt: str,
    *,
    app_name: str,
    user_id: str = "coordinator",
    timeout_s: float = 60.0,
) -> str:
    """Run `agent` once with `prompt` and return the concatenated text of its
    final response. Works identically whether `agent` is a local LlmAgent or
    a `RemoteA2aAgent` proxy (the A2A round-trip is transparent to callers)."""
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    try:
        session = await runner.session_service.create_session(
            app_name=app_name, user_id=user_id
        )
        message = types.Content(role="user", parts=[types.Part(text=prompt)])

        async def _consume() -> str:
            final_text = ""
            async for event in runner.run_async(
                user_id=user_id, session_id=session.id, new_message=message
            ):
                if event.content and event.content.parts:
                    texts = [p.text for p in event.content.parts if getattr(p, "text", None)]
                    if texts:
                        final_text = "\n".join(texts)
            return final_text

        try:
            return await asyncio.wait_for(_consume(), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise AgentInvocationError(
                f"agent '{agent.name}' did not respond within {timeout_s}s"
            ) from exc
    finally:
        await runner.close()


async def run_agent_for_model(
    agent: BaseAgent,
    prompt: str,
    schema: type[T],
    *,
    app_name: str,
    user_id: str = "coordinator",
    timeout_s: float = 60.0,
) -> T:
    """Run `agent` and validate its final response against `schema`."""
    text = await run_agent_once(
        agent, prompt, app_name=app_name, user_id=user_id, timeout_s=timeout_s
    )
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        logger.error("agent '%s' returned a response that failed schema validation: %s", agent.name, text[:500])
        raise AgentInvocationError(
            f"agent '{agent.name}' returned a response that did not match {schema.__name__}: {exc}"
        ) from exc
