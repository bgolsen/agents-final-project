"""Remediation Agent -- turns a diagnosis into a ranked, hierarchical
remediation plan (goal -> ordered steps), the artifact the HITL checkpoint
reviews before anything is actually executed.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from incident_response.agents.common import (
    extract_field,
    extract_prompt_text,
    model_to_llm_response,
)
from incident_response.config import settings
from incident_response.data.remediation_catalog import list_remediation_catalog
from incident_response.schemas import (
    DiagnosticReport,
    RemediationGoal,
    RemediationPlan,
    RemediationStep,
)
from incident_response.tracing import logger

NAME = "remediation_agent"

INSTRUCTION = """You are the Remediation Agent in an incident-response system.

You receive an incident_id, a service, and a DiagnosticReport (JSON) with
ranked root-cause hypotheses. Your job is hierarchical remediation planning,
NOT a single tool call:

1. Call `list_remediation_catalog` with a query built from the leading
   hypothesis's statement/evidence to retrieve candidate actions.
2. Organize your plan into 2 goals:
   - "Immediate mitigation": the fastest safe action(s) that stop user
     impact now (prefer low/medium risk).
   - "Preventive follow-up": action(s) that address the underlying cause so
     it doesn't recur.
   Each goal contains an ordered list of RemediationStep (action, tool,
   risk, rationale, rollback plan).
3. Set `ranked_recommendation` to the goal text of whichever goal should be
   executed first (normally "Immediate mitigation").
4. Set `risk_summary`: one or two sentences on overall risk and why the
   ordering is safe.

Never propose a high-risk step without a concrete rollback plan. If the
diagnostic report shows low confidence or unresolved_uncertainty, prefer
lower-risk actions and say so in risk_summary.

Always echo the given incident_id back in your report.

IMPORTANT: always set `degraded_mode` to `false`. That field is reserved for
the system's own automatic fallback path (used only when you are completely
unavailable) and must never be set to `true` by you -- record any concerns
about data quality in `risk_summary` instead.
"""


def _heuristic_plan(incident_id: str, diagnosis: DiagnosticReport) -> RemediationPlan:
    leading = next(
        (h for h in diagnosis.hypotheses if h.id == diagnosis.leading_hypothesis_id),
        diagnosis.hypotheses[0] if diagnosis.hypotheses else None,
    )
    query = leading.statement if leading else "generic incident"
    candidates = list_remediation_catalog(query, top_k=4)

    def to_step(i: int, c: dict) -> RemediationStep:
        return RemediationStep(
            id=f"S{i+1}",
            action=c["action"],
            tool=c["tool"],
            risk=c["risk"],
            rationale=c["rationale"],
            rollback=c["rollback"],
        )

    immediate = [c for c in candidates if c["risk"] in ("low", "medium")][:2] or candidates[:1]
    followup = [c for c in candidates if c not in immediate][:2]

    goals = [
        RemediationGoal(
            goal="Immediate mitigation",
            steps=[to_step(i, c) for i, c in enumerate(immediate)],
        ),
    ]
    if followup:
        goals.append(
            RemediationGoal(
                goal="Preventive follow-up",
                steps=[to_step(i, c) for i, c in enumerate(followup)],
            )
        )

    return RemediationPlan(
        incident_id=incident_id,
        goals=goals,
        ranked_recommendation="Immediate mitigation",
        risk_summary=(
            "Operating in degraded mode (LLM unavailable): plan derived from keyword-overlap "
            "catalog matching against the leading hypothesis; steps ordered low-risk first."
        ),
        degraded_mode=True,
    )


def _on_model_error(*, callback_context, llm_request, error):
    prompt_text = extract_prompt_text(llm_request)
    incident_id = extract_field(prompt_text, "incident_id", "unknown")
    diagnostic_json = extract_field(prompt_text, "diagnostic_report_json", "{}")
    logger.warning(
        "remediation_agent: LLM call failed for incident %s (%s); falling back to rule-based plan",
        incident_id,
        error,
    )
    try:
        diagnosis = DiagnosticReport.model_validate_json(diagnostic_json)
    except Exception:
        diagnosis = DiagnosticReport(
            incident_id=incident_id,
            decomposition=[],
            hypotheses=[],
            leading_hypothesis_id="",
            unresolved_uncertainty="diagnostic report could not be parsed in fallback path",
        )
    plan = _heuristic_plan(incident_id, diagnosis)
    return model_to_llm_response(plan)


def build_agent() -> LlmAgent:
    return LlmAgent(
        name=NAME,
        description="Turns a ranked diagnosis into a hierarchical, risk-ranked remediation plan for human approval.",
        model=settings.adk_model,
        instruction=INSTRUCTION,
        tools=[list_remediation_catalog],
        output_schema=RemediationPlan,
        on_model_error_callback=_on_model_error,
    )
