"""A tiny keyword-overlap search over a JSON file of past incidents.

This stands in for a real vector-search / ticketing-system integration. The
scoring is deliberately simple and transparent so both the LLM-driven
diagnostic agent *and* its deterministic fallback (used when the LLM is
unavailable, see agents/diagnostic_agent.py) can call the exact same function
and get a real, inspectable answer -- not a canned one.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from incident_response.data.chaos import maybe_fail, scenario_for_text
from incident_response.data.text_utils import tokenize

_DB_PATH = Path(__file__).parent / "incidents.json"


class PastIncident(TypedDict):
    id: str
    title: str
    keywords: list[str]
    root_cause: str
    fix_applied: str
    tags: list[str]


def _load() -> list[PastIncident]:
    with _DB_PATH.open(encoding="utf-8") as f:
        return json.load(f)


_INCIDENTS = _load()


def search_knowledge_base(query: str, top_k: int = 3) -> list[dict]:
    """Search the historical-incident knowledge base for similar past incidents.

    Args:
        query: free-text description of symptoms/observations (e.g. service
            name, metric names, log snippets).
        top_k: max number of results to return, ranked by relevance.

    Returns:
        A list of past-incident records (id, title, root_cause, fix_applied,
        tags) ordered from most to least relevant, each with a `score` field.

    Raises:
        SimulatedBackendUnavailableError: the knowledge base is unreachable
            (simulated transient failure).
    """
    maybe_fail("search_knowledge_base", scenario_for_text(query), subject=query[:60])
    query_tokens = tokenize(query)
    scored = []
    for inc in _INCIDENTS:
        corpus_tokens = tokenize(
            " ".join([inc["title"], *inc["keywords"], *inc["tags"]])
        )
        overlap = query_tokens & corpus_tokens
        if not overlap:
            continue
        score = len(overlap) / max(len(query_tokens), 1)
        scored.append((score, inc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {**inc, "score": round(score, 3)} for score, inc in scored[:top_k]
    ]


def get_incident_by_id(incident_id: str) -> dict | None:
    return next((i for i in _INCIDENTS if i["id"] == incident_id), None)


def all_incidents() -> list[PastIncident]:
    return list(_INCIDENTS)
