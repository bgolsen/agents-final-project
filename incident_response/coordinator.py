"""Coordinator -- the rule-based orchestration layer that manages handoffs
between the specialist agents over A2A, gates execution on human approval,
and degrades gracefully when a specialist (or the LLM behind it) is
unavailable.

Design note (see ARCHITECTURE.md for the full tradeoff discussion): the
coordinator is deliberately *not* itself an LLM-driven agent that
auto-delegates to sub-agents. HITL needs a hard stop between "plan produced"
and "plan executed" that a human controls, and Track 2 explicitly calls for
"handling partial information" -- both are easier to guarantee with explicit
control flow than with LLM-driven transfer-of-control.

Resilience has two independent layers, matching two different failure modes:
  1. The specialist process is reachable but its LLM call fails -> handled
     *inside* that agent via `on_model_error_callback` (see agents/*.py).
  2. The specialist process itself is unreachable/times out -> handled here,
     by retrying once and then falling back to the same deterministic
     heuristic the agent would have used, called directly in-process.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Literal, TypeVar

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from pydantic import BaseModel

from incident_response.adk_runtime import AgentInvocationError, run_agent_for_model
from incident_response.agents import (
    diagnostic_agent,
    monitoring_agent,
    postmortem_agent,
    remediation_agent,
)
from incident_response.config import agent_card_url, settings
from incident_response.data.scenarios import get_scenario
from incident_response.data.telemetry import TelemetryUnavailableError, simulate_execute_action
from incident_response.schemas import (
    ApprovalDecision,
    DiagnosticReport,
    ExecutedStep,
    PostmortemDoc,
    RemediationGoal,
    RemediationPlan,
    TriageReport,
)
from incident_response.tracing import incident_extra, logger, traceable

T = TypeVar("T", bound=BaseModel)

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


class IncidentState(BaseModel):
    incident_id: str
    scenario_id: str
    service: str
    description: str
    status: Literal[
        "triaging", "diagnosing", "planning", "awaiting_approval",
        "executing", "closed", "rejected", "failed",
    ] = "triaging"
    triage: TriageReport | None = None
    diagnosis: DiagnosticReport | None = None
    plan: RemediationPlan | None = None
    decision: ApprovalDecision | None = None
    execution_log: list[ExecutedStep] = []
    postmortem: PostmortemDoc | None = None
    coordinator_notes: list[str] = []
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remote(agent_name: str) -> RemoteA2aAgent:
    return RemoteA2aAgent(
        name=f"{agent_name}_agent",
        agent_card=agent_card_url(agent_name),
        timeout=120.0,
    )


def _format_prompt(**fields: str) -> str:
    return "\n".join(f"{key}: {value}" for key, value in fields.items())


def _compact(model: BaseModel) -> str:
    return json.dumps(model.model_dump(), separators=(",", ":"))


async def _call_with_resilience(
    incident_id: str,
    agent_name: str,
    call: Callable[[], Awaitable[T]],
    fallback: Callable[[], T],
    notes: list[str],
    retries: int = 1,
) -> T:
    """Try the remote A2A call (with one retry), and if the specialist
    process itself is unreachable, fall back to the same deterministic
    heuristic the agent would use -- computed locally so the pipeline never
    just crashes because a downstream process is down."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await call()
        except (AgentInvocationError, ConnectionError, OSError, TimeoutError) as exc:
            last_error = exc
            logger.warning(
                "coordinator: %s unreachable for incident %s (attempt %d/%d): %s",
                agent_name, incident_id, attempt + 1, retries + 1, exc,
            )
            await asyncio.sleep(0.3)
        except Exception as exc:  # noqa: BLE001 - last line of defense, must not crash the pipeline
            last_error = exc
            logger.warning(
                "coordinator: %s raised an unexpected error for incident %s: %s",
                agent_name, incident_id, exc,
            )
            break
    note = (
        f"{agent_name} agent unreachable after {retries + 1} attempt(s) "
        f"({last_error}); coordinator used local deterministic fallback."
    )
    logger.error("coordinator: %s", note)
    notes.append(note)
    return fallback()


@traceable(name="triage_stage", run_type="chain")
async def run_triage(state: IncidentState) -> TriageReport:
    prompt = _format_prompt(
        incident_id=state.incident_id,
        service=state.service,
        description=state.description,
    )

    async def call() -> TriageReport:
        return await run_agent_for_model(
            _remote("monitoring"), prompt, TriageReport, app_name="coordinator"
        )

    def fallback() -> TriageReport:
        return monitoring_agent._heuristic_triage(state.incident_id, state.service)

    return await _call_with_resilience(
        state.incident_id, "monitoring", call, fallback, state.coordinator_notes
    )


@traceable(name="diagnosis_stage", run_type="chain")
async def run_diagnosis(state: IncidentState) -> DiagnosticReport:
    assert state.triage is not None
    prompt = _format_prompt(
        incident_id=state.incident_id,
        service=state.service,
        triage_report_json=_compact(state.triage),
    )

    async def call() -> DiagnosticReport:
        return await run_agent_for_model(
            _remote("diagnostic"), prompt, DiagnosticReport, app_name="coordinator"
        )

    def fallback() -> DiagnosticReport:
        return diagnostic_agent._heuristic_diagnosis(state.incident_id, state.service, state.triage)

    return await _call_with_resilience(
        state.incident_id, "diagnostic", call, fallback, state.coordinator_notes
    )


@traceable(name="remediation_planning_stage", run_type="chain")
async def run_remediation_plan(state: IncidentState) -> RemediationPlan:
    assert state.diagnosis is not None
    prompt = _format_prompt(
        incident_id=state.incident_id,
        service=state.service,
        diagnostic_report_json=_compact(state.diagnosis),
    )

    async def call() -> RemediationPlan:
        return await run_agent_for_model(
            _remote("remediation"), prompt, RemediationPlan, app_name="coordinator"
        )

    def fallback() -> RemediationPlan:
        return remediation_agent._heuristic_plan(state.incident_id, state.diagnosis)

    return await _call_with_resilience(
        state.incident_id, "remediation", call, fallback, state.coordinator_notes
    )


@traceable(name="postmortem_stage", run_type="chain")
async def run_postmortem(state: IncidentState) -> PostmortemDoc:
    assert state.triage and state.diagnosis and state.plan and state.decision
    decision_summary = (
        f"{state.decision.decision} by {state.decision.reviewer}"
        + (f" -- {state.decision.notes}" if state.decision.notes else "")
    )
    execution_summary = [f"{s.action}: {s.status} ({s.detail})" for s in state.execution_log]
    prompt = _format_prompt(
        incident_id=state.incident_id,
        triage_report_json=_compact(state.triage),
        diagnostic_report_json=_compact(state.diagnosis),
        plan_json=_compact(state.plan),
        decision_summary=decision_summary,
        execution_summary="|".join(execution_summary),
    )

    async def call() -> PostmortemDoc:
        return await run_agent_for_model(
            _remote("postmortem"), prompt, PostmortemDoc, app_name="coordinator"
        )

    def fallback() -> PostmortemDoc:
        return postmortem_agent._heuristic_postmortem(
            state.incident_id, state.triage, state.diagnosis, state.plan,
            decision_summary, execution_summary,
        )

    return await _call_with_resilience(
        state.incident_id, "postmortem", call, fallback, state.coordinator_notes
    )


def _auto_approval_decision(state: IncidentState) -> ApprovalDecision | None:
    """Optional mode (`AUTO_APPROVE_LOW_RISK`, off by default): skip the HITL
    gate only for plans that are well-understood *and* low-stakes. Every one
    of these has to hold, not just one:
      - none of triage/diagnosis/plan fell back to degraded (rule-based) mode
        -- that reasoning is deliberately weaker and shouldn't self-certify
      - the leading root-cause hypothesis clears a confidence threshold
      - every step in the goal that would run is 'low' risk

    Anything short of all three still stops for a human -- this is meant to
    auto-clear the boring, obvious cases, not to quietly widen what "low
    risk" covers.
    """
    if not settings.auto_approve_low_risk:
        return None
    assert state.triage and state.diagnosis and state.plan

    if state.triage.degraded_mode or state.diagnosis.degraded_mode or state.plan.degraded_mode:
        return None

    leading = next(
        (h for h in state.diagnosis.hypotheses if h.id == state.diagnosis.leading_hypothesis_id),
        None,
    )
    if leading is None or leading.confidence < settings.auto_approve_confidence_threshold:
        return None

    goal = next(
        (g for g in state.plan.goals if g.goal == state.plan.ranked_recommendation),
        state.plan.goals[0] if state.plan.goals else None,
    )
    if goal is None or not goal.steps or any(step.risk != "low" for step in goal.steps):
        return None

    return ApprovalDecision(
        decision="approve",
        reviewer="system (auto-approved: low risk)",
        notes=(
            f"Auto-approved by policy: leading hypothesis confidence "
            f"{leading.confidence:.2f} >= {settings.auto_approve_confidence_threshold:.2f} "
            f"threshold, all steps in '{goal.goal}' are low-risk, and no stage "
            f"ran in degraded mode."
        ),
    )


def _select_goal(plan: RemediationPlan, decision: ApprovalDecision) -> RemediationGoal:
    if decision.decision == "modify" and decision.modified_goal:
        for goal in plan.goals:
            if goal.goal.strip().lower() == decision.modified_goal.strip().lower():
                return goal
    for goal in plan.goals:
        if goal.goal == plan.ranked_recommendation:
            return goal
    return plan.goals[0]


@traceable(name="execute_remediation_stage", run_type="chain")
async def execute_remediation(state: IncidentState) -> list[ExecutedStep]:
    """Execute the human-approved (or human-modified) goal's steps against
    the simulated action backend, retrying transient failures with backoff
    before marking a step failed and moving on -- a partial failure here
    must not abort the whole incident."""
    assert state.plan is not None and state.decision is not None
    goal = _select_goal(state.plan, state.decision)
    results: list[ExecutedStep] = []
    for step in goal.steps:
        detail = ""
        status: Literal["success", "failed", "skipped"] = "failed"
        for attempt in range(3):
            try:
                outcome = simulate_execute_action(step.id, state.service, step.action)
                status = "success"
                detail = outcome["detail"]
                break
            except TelemetryUnavailableError as exc:
                detail = str(exc)
                logger.warning(
                    "coordinator: execution of step %s failed (attempt %d/3): %s",
                    step.id, attempt + 1, exc,
                )
                await asyncio.sleep(0.3 * (attempt + 1))
        else:
            state.coordinator_notes.append(
                f"step {step.id} ('{step.action}') failed after 3 attempts: {detail}"
            )
        results.append(ExecutedStep(step_id=step.id, action=step.action, status=status, detail=detail))
    return results


def new_incident(scenario_id: str) -> IncidentState:
    scenario = get_scenario(scenario_id)
    now = _now()
    return IncidentState(
        incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
        scenario_id=scenario_id,
        service=scenario.primary_service,
        description=f"Automated alert: anomalous behavior detected on {scenario.primary_service}",
        created_at=now,
        updated_at=now,
    )


def save_state(state: IncidentState) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{state.incident_id}.json"
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


@traceable(name="incident_pipeline_to_approval", run_type="chain")
async def run_to_approval(state: IncidentState) -> IncidentState:
    """Stages 1-3: triage -> diagnosis -> remediation plan. No human input
    needed yet; stops at `awaiting_approval` for the HITL gate."""
    extra = incident_extra(state.incident_id, scenario=state.scenario_id)

    state.status = "triaging"
    state.triage = await run_triage(state, langsmith_extra=extra)
    state.updated_at = _now()
    save_state(state)

    state.status = "diagnosing"
    state.diagnosis = await run_diagnosis(state, langsmith_extra=extra)
    state.updated_at = _now()
    save_state(state)

    state.status = "planning"
    state.plan = await run_remediation_plan(state, langsmith_extra=extra)
    state.status = "awaiting_approval"
    state.updated_at = _now()
    save_state(state)

    auto_decision = _auto_approval_decision(state)
    if auto_decision is not None:
        logger.info(
            "coordinator: incident %s auto-approved by low-risk policy (%s)",
            state.incident_id, auto_decision.notes,
        )
        return await resume_after_decision(state, auto_decision, langsmith_extra=extra)

    return state


@traceable(name="incident_pipeline_after_decision", run_type="chain")
async def resume_after_decision(state: IncidentState, decision: ApprovalDecision) -> IncidentState:
    """Stage 4 (HITL gate result) onward: execute (or don't) and write the
    postmortem. This is where the human decision genuinely changes system
    behavior -- reject skips execution entirely, modify changes which goal
    runs, approve runs the recommended goal."""
    state.decision = decision
    state.updated_at = _now()
    extra = incident_extra(state.incident_id, scenario=state.scenario_id, decision=decision.decision)

    if decision.decision == "reject":
        state.status = "rejected"
        state.execution_log = []
    else:
        state.status = "executing"
        save_state(state)
        state.execution_log = await execute_remediation(state, langsmith_extra=extra)
        state.status = "closed"

    state.postmortem = await run_postmortem(state, langsmith_extra=extra)
    state.updated_at = _now()
    save_state(state)
    return state
