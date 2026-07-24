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
