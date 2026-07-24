"""Diagnostic Agent -- decomposes the incident into sub-questions, gathers
evidence for each, and produces a ranked set of root-cause hypotheses.

This is where the system's "planning / hierarchical reasoning" requirement
lives: the agent must *explicitly* break the open-ended question "why is
this happening" into an inspectable list of sub-questions before it is
allowed to rank hypotheses, and every hypothesis must cite the evidence and
past incidents that support (or contradict) it.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from incident_response.agents.common import (
    extract_field,
    extract_prompt_text,
    model_to_llm_response,
)
from incident_response.config import settings
from incident_response.data.knowledge_base import search_knowledge_base
from incident_response.data.telemetry import TelemetryUnavailableError, get_recent_logs
from incident_response.schemas import (
    DiagnosticReport,
    DiagnosticSubtask,
    RootCauseHypothesis,
    TriageReport,
)
from incident_response.tracing import logger

NAME = "diagnostic_agent"

INSTRUCTION = """You are the Diagnostic Agent in an incident-response system.

You receive an incident_id, a service, and a TriageReport (JSON) produced by
the Monitoring Agent describing observed anomalies. Your job is root-cause
analysis via explicit hierarchical decomposition, NOT a single guess:

1. Break the question "what is causing this incident" into 2-4 concrete
   sub-questions (e.g. "did a recent deploy correlate with the onset?",
   "is this isolated to one service or a downstream dependency?", "does this
   match a known failure pattern?"). Record each as a `decomposition` entry
   with your `finding` for it.
2. To answer the sub-questions, call `get_recent_logs` for more detail and
   `search_knowledge_base` with a query built from the triage anomalies/
   summary to find similar past incidents.
3. If a tool fails, record that as an unresolved sub-question rather than
   guessing -- lower your confidence accordingly.
4. Produce 1-3 ranked RootCauseHypothesis entries, each with supporting
   evidence (cite specific log lines / metrics / past incident ids),
   contradicting evidence if any, and a confidence 0-1.
5. Set leading_hypothesis_id to the id of your top hypothesis and describe
   any unresolved_uncertainty honestly.

Always echo the given incident_id back in your report.
"""


def _heuristic_diagnosis(incident_id: str, service: str, triage: TriageReport) -> DiagnosticReport:
    """Deterministic fallback: still decomposes into sub-questions and still
    calls the real KB search tool -- it just doesn't use an LLM to reason
    about the results, so it's a legitimate (if less nuanced) fallback."""
    decomposition = []
    data_gaps: list[str] = list(triage.data_gaps)

    query_terms = [service, triage.summary] + [a.metric for a in triage.anomalies] + [
        a.observation for a in triage.anomalies
    ]
    query = " ".join(query_terms)

    decomposition.append(
        DiagnosticSubtask(
            question="Does this match a known historical failure pattern?",
            finding="Queried the incident knowledge base with the triage anomalies/summary.",
        )
    )

    try:
        matches = search_knowledge_base(query, top_k=3)
    except Exception as exc:  # defensive: KB is local/in-memory but keep the pattern consistent
        matches = []
        data_gaps.append(f"knowledge base unavailable: {exc}")

    decomposition.append(
        DiagnosticSubtask(
            question="Is there additional log evidence beyond the triage anomalies?",
            finding="Fetched recent logs directly." if not data_gaps else "Skipped due to earlier data gaps.",
        )
    )
    extra_lines: list[str] = []
    try:
        extra_lines = get_recent_logs(service)["lines"]
    except TelemetryUnavailableError as exc:
        data_gaps.append(f"logs unavailable: {exc}")

    hypotheses = []
    for i, match in enumerate(matches):
        evidence = [a.observation for a in triage.anomalies[:2]]
        evidence += [l for l in extra_lines if "ERROR" in l][:2]
        hypotheses.append(
            RootCauseHypothesis(
                id=f"H{i+1}",
                statement=match["root_cause"],
                supporting_evidence=evidence or ["triage anomalies (see TriageReport)"] ,
                contradicting_evidence=[],
                confidence=min(0.9, max(0.2, match["score"])) * (0.7 if data_gaps else 1.0),
                similar_past_incidents=[match["id"]],
            )
        )

    if not hypotheses:
        hypotheses.append(
            RootCauseHypothesis(
                id="H1",
                statement="Insufficient data to identify a specific root cause; recommend manual investigation.",
                supporting_evidence=[a.observation for a in triage.anomalies] or ["no anomalies observed"],
                contradicting_evidence=[],
                confidence=0.2,
                similar_past_incidents=[],
            )
        )

    leading = max(hypotheses, key=lambda h: h.confidence)

    return DiagnosticReport(
        incident_id=incident_id,
        decomposition=decomposition,
        hypotheses=hypotheses,
        leading_hypothesis_id=leading.id,
        unresolved_uncertainty=(
            "Operating in degraded mode (LLM unavailable): "
            + ("; ".join(data_gaps) if data_gaps else "ranking based on keyword-overlap similarity only.")
        ),
        degraded_mode=True,
    )


def _on_model_error(*, callback_context, llm_request, error):
    prompt_text = extract_prompt_text(llm_request)
    incident_id = extract_field(prompt_text, "incident_id", "unknown")
    service = extract_field(prompt_text, "service", "unknown-service")
    triage_json = extract_field(prompt_text, "triage_report_json", "{}")
    logger.warning(
        "diagnostic_agent: LLM call failed for incident %s (%s); falling back to rule-based diagnosis",
        incident_id,
        error,
    )
    try:
        triage = TriageReport.model_validate_json(triage_json)
    except Exception:
        triage = TriageReport(
            incident_id=incident_id,
            summary="triage report unavailable",
            severity="medium",
            affected_services=[service],
            anomalies=[],
            confidence=0.0,
            data_gaps=["triage report could not be parsed in fallback path"],
        )
    report = _heuristic_diagnosis(incident_id, service, triage)
    return model_to_llm_response(report)


def build_agent() -> LlmAgent:
    return LlmAgent(
        name=NAME,
        description="Decomposes an incident into sub-questions, gathers evidence, and ranks root-cause hypotheses against a knowledge base of past incidents.",
        model=settings.adk_model,
        instruction=INSTRUCTION,
        tools=[get_recent_logs, search_knowledge_base],
        output_schema=DiagnosticReport,
        on_model_error_callback=_on_model_error,
    )
