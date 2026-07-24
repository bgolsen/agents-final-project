"""Shared helpers for building agents and their deterministic fallbacks.

The A2A server for each agent is a single long-lived process that serves
many incidents over its lifetime, so a fallback cannot close over
per-incident values at build time -- it has to recover them from the
in-flight request. `extract_prompt_text`/`extract_field` do that by reading
the structured `key: value` header every coordinator prompt starts with
(see coordinator.py `_format_prompt`).
"""
from __future__ import annotations

import re

from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel

from incident_response.tracing import logger


def extract_prompt_text(llm_request: LlmRequest) -> str:
    chunks: list[str] = []
    for content in llm_request.contents or []:
        for part in content.parts or []:
            if getattr(part, "text", None):
                chunks.append(part.text)
    return "\n".join(chunks)


def extract_field(text: str, field: str, default: str = "") -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else default


def model_to_llm_response(model_obj: BaseModel) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model", parts=[types.Part(text=model_obj.model_dump_json())]
        )
    )


def on_tool_error(*, tool, args, tool_context, error):
    """Shared `on_tool_error_callback`: instead of letting a failed tool call
    crash the whole agent invocation, hand the model a structured error so it
    can adapt within its own reasoning -- note the gap, lower confidence,
    proceed with partial information -- exactly like a human on-call engineer
    would when one signal is unavailable.

    NOTE: ADK invokes per-agent `on_tool_error_callback`s with the tool
    arguments under the keyword `args` (not `tool_args`, which is only used
    for the separate plugin-manager callback variant) -- verified against
    `google/adk/flows/llm_flows/functions.py::_run_on_tool_error_callbacks`.
    """
    logger.warning("agent tool '%s' failed with args %s: %s", tool.name, args, error)
    return {
        "error": str(error),
        "guidance": (
            "This data source is temporarily unavailable. Do not retry it. "
            "Proceed with whatever other data you have, and explicitly record "
            "this gap (lower your confidence / note it as unresolved)."
        ),
    }
