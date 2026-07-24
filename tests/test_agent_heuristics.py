"""Tests for the deterministic fallback reasoning used when the LLM is
unavailable -- these are exercised directly (not via a live model call) so
CI can run them without any API key."""
from __future__ import annotations

from incident_response.agents.diagnostic_agent import _heuristic_diagnosis
from incident_response.agents.monitoring_agent import _heuristic_triage
from incident_response.agents.postmortem_agent import _heuristic_postmortem
from incident_response.agents.remediation_agent import _heuristic_plan


def test_heuristic_triage_flags_degraded_mode_and_anomalies():
    report = _heuristic_triage("INC-T1", "checkout-service")
    assert report.degraded_mode is True
    assert report.severity in ("low", "medium", "high", "critical")
    assert len(report.anomalies) >= 1


def test_heuristic_diagnosis_produces_ranked_hypotheses():
    triage = _heuristic_triage("INC-T2", "payment-db")
    diagnosis = _heuristic_diagnosis("INC-T2", "payment-db", triage)
    assert diagnosis.hypotheses
    assert diagnosis.leading_hypothesis_id in {h.id for h in diagnosis.hypotheses}
    assert len(diagnosis.decomposition) >= 2


def test_heuristic_plan_orders_low_risk_first_goal():
    triage = _heuristic_triage("INC-T3", "auth-service")
    diagnosis = _heuristic_diagnosis("INC-T3", "auth-service", triage)
    plan = _heuristic_plan("INC-T3", diagnosis)
    assert plan.goals
    assert plan.ranked_recommendation == "Immediate mitigation"
    assert all(step.rollback for goal in plan.goals for step in goal.steps)


def test_heuristic_postmortem_records_rejection_path():
    triage = _heuristic_triage("INC-T4", "checkout-service")
    diagnosis = _heuristic_diagnosis("INC-T4", "checkout-service", triage)
    plan = _heuristic_plan("INC-T4", diagnosis)
    doc = _heuristic_postmortem(
        "INC-T4", triage, diagnosis, plan,
        decision_summary="reject by grady -- needs more data",
        execution_summary=[],
    )
    assert doc.remediation_taken == ["none"]
    assert "reject" in doc.human_decisions[0]
