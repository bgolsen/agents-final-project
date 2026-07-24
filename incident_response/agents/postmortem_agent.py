"""Postmortem Agent -- synthesizes the full incident trace (triage,
diagnosis, plan, human decision, execution results) into a structured
post-mortem document."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from incident_response.agents.common import (
    extract_field,
    extract_prompt_text,
    model_to_llm_response,
)
from incident_response.config import settings
from incident_response.schemas import (
    DiagnosticReport,
    PostmortemDoc,
    RemediationPlan,
    TriageReport,
)
from incident_response.tracing import logger

NAME = "postmortem_agent"

INSTRUCTION = """You are the Postmortem Agent in an incident-response system.

You receive the full incident trace as JSON: incident_id, the TriageReport,
the DiagnosticReport, the RemediationPlan, the human reviewer's decision
(approve/reject/modify + notes), and the execution log (which steps actually
ran and their result, empty if the human rejected the plan).

Write a structured post-mortem:
- title: short, specific.
- timeline: bullet list reconstructing what happened in order (detection ->
  diagnosis -> decision -> execution/rejection).
- root_cause: the leading hypothesis, stated plainly, noting confidence.
- impact: which services/users were affected and how badly (from severity).
- remediation_taken: what was actually executed (or "none -- human rejected
  the plan: <reason>" if applicable).
- human_decisions: record exactly what the human approved/rejected/modified
  and why -- this is not optional, the HITL decision must be traceable.
- lessons_learned: 1-3 concrete, specific observations.
- action_items: 1-3 concrete follow-ups (e.g. add an alert, add a runbook).

Be honest about degraded_mode / data_gaps / unresolved_uncertainty if the
inputs mention them -- do not paper over gaps.

Always echo the given incident_id back.
"""


def _heuristic_postmortem(
    incident_id: str,
    triage: TriageReport,
    diagnosis: DiagnosticReport,
    plan: RemediationPlan,
    decision_summary: str,
    execution_summary: list[str],
) -> PostmortemDoc:
    leading = next(
        (h for h in diagnosis.hypotheses if h.id == diagnosis.leading_hypothesis_id),
        None,
    )
    root_cause = (
        f"{leading.statement} (confidence {leading.confidence:.2f})"
        if leading
        else "Root cause not conclusively identified."
    )
    return PostmortemDoc(
        incident_id=incident_id,
        title=f"Postmortem: {triage.summary[:80]}",
        timeline=[
            f"Detected: {triage.summary}",
            f"Diagnosed: leading hypothesis -- {root_cause}",
            f"Human decision: {decision_summary}",
            *(execution_summary or ["No remediation executed."]),
        ],
        root_cause=root_cause,
        impact=f"Severity {triage.severity}; affected services: {', '.join(triage.affected_services)}.",
        remediation_taken=execution_summary or ["none"],
        human_decisions=[decision_summary],
        lessons_learned=[
            "Operating in degraded mode (LLM unavailable) for this postmortem -- "
            "review manually for nuance beyond the templated summary."
        ],
        action_items=[
            "Verify metrics returned to baseline.",
            "Confirm the preventive follow-up step (if any) is scheduled.",
        ],
        degraded_mode=True,
    )


def _on_model_error(*, callback_context, llm_request, error):
    prompt_text = extract_prompt_text(llm_request)
    incident_id = extract_field(prompt_text, "incident_id", "unknown")
    logger.warning(
        "postmortem_agent: LLM call failed for incident %s (%s); falling back to templated postmortem",
        incident_id,
        error,
    )

    def _parse(field, schema, default):
        try:
            return schema.model_validate_json(extract_field(prompt_text, field, "{}"))
        except Exception:
            return default

    triage = _parse(
        "triage_report_json",
        TriageReport,
        TriageReport(incident_id=incident_id, summary="unavailable", severity="medium", affected_services=[], anomalies=[], confidence=0.0),
    )
    diagnosis = _parse(
        "diagnostic_report_json",
        DiagnosticReport,
        DiagnosticReport(incident_id=incident_id, decomposition=[], hypotheses=[], leading_hypothesis_id="", unresolved_uncertainty="unavailable"),
    )
    plan = _parse(
        "plan_json",
        RemediationPlan,
        RemediationPlan(incident_id=incident_id, goals=[], ranked_recommendation="", risk_summary="unavailable"),
    )
    decision_summary = extract_field(prompt_text, "decision_summary", "unknown")
    execution_summary_raw = extract_field(prompt_text, "execution_summary", "")
    execution_summary = [s for s in execution_summary_raw.split("|") if s]

    doc = _heuristic_postmortem(
        incident_id, triage, diagnosis, plan, decision_summary, execution_summary
    )
    return model_to_llm_response(doc)


def build_agent() -> LlmAgent:
    return LlmAgent(
        name=NAME,
        description="Synthesizes the full incident trace into a structured post-mortem, including the human decision and execution results.",
        model=settings.adk_model,
        instruction=INSTRUCTION,
        tools=[],
        output_schema=PostmortemDoc,
        on_model_error_callback=_on_model_error,
    )
