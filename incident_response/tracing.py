"""LangSmith tracing helpers.

Every coordinator stage and every specialist-agent call is wrapped in a
`@traceable` span tagged with the incident id, so the full diagnostic
reasoning chain -- triage -> decomposition -> hypotheses -> plan -> human
decision -> execution -> postmortem -- shows up as one nested run tree in
LangSmith (project = `LANGSMITH_PROJECT`). If no LangSmith API key is
configured the decorator is a documented no-op, so the system still runs
(and still logs locally via `logger`), it just isn't remotely traced.
"""
from __future__ import annotations

import logging

from langsmith import traceable as _traceable

from incident_response.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("incident_response")

# Re-exported so callers do `from incident_response.tracing import traceable`.
traceable = _traceable


def incident_extra(incident_id: str, **metadata) -> dict:
    """Build the `langsmith_extra` kwarg for a traced call, tagged by incident."""
    return {
        "metadata": {"incident_id": incident_id, **metadata},
        "tags": [f"incident:{incident_id}", settings.langsmith_project],
    }
