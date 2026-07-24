"""Tests for the coordinator's resilience/fallback and HITL-goal-selection
logic, without needing live agent servers."""
from __future__ import annotations

import pytest

from incident_response.coordinator import IncidentState, _auto_approval_decision, _call_with_resilience, _select_goal
from incident_response.schemas import (
    ApprovalDecision,
    DiagnosticReport,
    RemediationGoal,
    RemediationPlan,
    RemediationStep,
    RootCauseHypothesis,
    TriageReport,
)


@pytest.mark.asyncio
async def test_call_with_resilience_falls_back_after_retries():
    attempts = []

    async def flaky_call():
        attempts.append(1)
        raise ConnectionError("simulated: agent process unreachable")

    def fallback():
        return "fallback-result"

    notes: list[str] = []
    result = await _call_with_resilience("INC-1", "diagnostic", flaky_call, fallback, notes, retries=2)

    assert result == "fallback-result"
    assert len(attempts) == 3  # initial attempt + 2 retries
    assert notes and "unreachable" in notes[0]


@pytest.mark.asyncio
async def test_call_with_resilience_returns_call_result_when_it_succeeds():
    async def call():
        return "ok"

    def fallback():
        raise AssertionError("fallback should not be used when the call succeeds")

    notes: list[str] = []
    result = await _call_with_resilience("INC-2", "monitoring", call, fallback, notes, retries=1)
    assert result == "ok"
    assert notes == []


def _sample_plan() -> RemediationPlan:
    return RemediationPlan(
        incident_id="INC-3",
        goals=[
            RemediationGoal(
                goal="Immediate mitigation",
                steps=[RemediationStep(id="S1", action="a", tool="t", risk="low", rationale="r", rollback="rb")],
            ),
            RemediationGoal(
                goal="Preventive follow-up",
                steps=[RemediationStep(id="S1", action="b", tool="t", risk="low", rationale="r", rollback="rb")],
            ),
        ],
        ranked_recommendation="Immediate mitigation",
        risk_summary="fine",
    )


def test_select_goal_approve_uses_ranked_recommendation():
    plan = _sample_plan()
    decision = ApprovalDecision(decision="approve", reviewer="grady")
    goal = _select_goal(plan, decision)
    assert goal.goal == "Immediate mitigation"


def test_select_goal_modify_switches_to_requested_goal():
    plan = _sample_plan()
    decision = ApprovalDecision(decision="modify", reviewer="grady", modified_goal="Preventive follow-up")
    goal = _select_goal(plan, decision)
    assert goal.goal == "Preventive follow-up"


def test_select_goal_modify_without_match_falls_back_to_recommendation():
    plan = _sample_plan()
    decision = ApprovalDecision(decision="modify", reviewer="grady", modified_goal="nonexistent goal")
    goal = _select_goal(plan, decision)
    assert goal.goal == "Immediate mitigation"


class _FakeAutoApproveSettings:
    def __init__(self, enabled: bool, threshold: float = 0.75):
        self.auto_approve_low_risk = enabled
        self.auto_approve_confidence_threshold = threshold


def _sample_state(*, confidence: float, degraded: bool, high_risk_step: bool) -> IncidentState:
    now = "2026-07-24T00:00:00+00:00"
    triage = TriageReport(
        incident_id="INC-A", summary="s", severity="high", affected_services=["svc"],
        anomalies=[], confidence=0.9, degraded_mode=degraded,
    )
    diagnosis = DiagnosticReport(
        incident_id="INC-A", decomposition=[],
        hypotheses=[RootCauseHypothesis(id="H1", statement="root cause", supporting_evidence=[], confidence=confidence)],
        leading_hypothesis_id="H1", unresolved_uncertainty="", degraded_mode=degraded,
    )
    plan = RemediationPlan(
        incident_id="INC-A",
        goals=[
            RemediationGoal(
                goal="Immediate mitigation",
                steps=[RemediationStep(
                    id="S1", action="a", tool="t",
                    risk="high" if high_risk_step else "low",
                    rationale="r", rollback="rb",
                )],
            ),
        ],
        ranked_recommendation="Immediate mitigation", risk_summary="fine", degraded_mode=degraded,
    )
    return IncidentState(
        incident_id="INC-A", scenario_id="checkout-latency-spike", service="svc",
        description="d", status="awaiting_approval", triage=triage, diagnosis=diagnosis,
        plan=plan, created_at=now, updated_at=now,
    )


def test_auto_approval_disabled_by_default(monkeypatch):
    monkeypatch.setattr("incident_response.coordinator.settings", _FakeAutoApproveSettings(enabled=False))
    state = _sample_state(confidence=0.99, degraded=False, high_risk_step=False)
    assert _auto_approval_decision(state) is None


def test_auto_approval_grants_when_all_criteria_met(monkeypatch):
    monkeypatch.setattr("incident_response.coordinator.settings", _FakeAutoApproveSettings(enabled=True, threshold=0.75))
    state = _sample_state(confidence=0.9, degraded=False, high_risk_step=False)
    decision = _auto_approval_decision(state)
    assert decision is not None
    assert decision.decision == "approve"
    assert "system" in decision.reviewer


def test_auto_approval_denied_when_degraded(monkeypatch):
    monkeypatch.setattr("incident_response.coordinator.settings", _FakeAutoApproveSettings(enabled=True, threshold=0.75))
    state = _sample_state(confidence=0.99, degraded=True, high_risk_step=False)
    assert _auto_approval_decision(state) is None


def test_auto_approval_denied_when_confidence_below_threshold(monkeypatch):
    monkeypatch.setattr("incident_response.coordinator.settings", _FakeAutoApproveSettings(enabled=True, threshold=0.75))
    state = _sample_state(confidence=0.5, degraded=False, high_risk_step=False)
    assert _auto_approval_decision(state) is None


def test_auto_approval_denied_when_recommended_goal_has_high_risk_step(monkeypatch):
    monkeypatch.setattr("incident_response.coordinator.settings", _FakeAutoApproveSettings(enabled=True, threshold=0.75))
    state = _sample_state(confidence=0.99, degraded=False, high_risk_step=True)
    assert _auto_approval_decision(state) is None
