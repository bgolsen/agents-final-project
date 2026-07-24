"""Tests for the coordinator's resilience/fallback and HITL-goal-selection
logic, without needing live agent servers."""
from __future__ import annotations

import pytest

from incident_response.coordinator import _call_with_resilience, _select_goal
from incident_response.schemas import ApprovalDecision, RemediationGoal, RemediationPlan, RemediationStep


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
