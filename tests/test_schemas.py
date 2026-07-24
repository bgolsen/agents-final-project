"""Tests that the structured hand-off contracts validate as expected."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from incident_response.schemas import (
    Anomaly,
    ApprovalDecision,
    RemediationStep,
    TriageReport,
)


def test_triage_report_requires_confidence_in_range():
    with pytest.raises(ValidationError):
        TriageReport(
            incident_id="INC-1",
            summary="x",
            severity="low",
            affected_services=[],
            anomalies=[],
            confidence=1.5,
        )


def test_triage_report_round_trips_through_json():
    report = TriageReport(
        incident_id="INC-1",
        summary="x",
        severity="high",
        affected_services=["svc-a"],
        anomalies=[Anomaly(metric="cpu", observation="cpu high", severity="high")],
        confidence=0.8,
        data_gaps=["logs unavailable"],
    )
    restored = TriageReport.model_validate_json(report.model_dump_json())
    assert restored == report


def test_approval_decision_rejects_invalid_choice():
    with pytest.raises(ValidationError):
        ApprovalDecision(decision="maybe", reviewer="grady")


def test_remediation_step_requires_risk_enum():
    with pytest.raises(ValidationError):
        RemediationStep(
            id="S1", action="do it", tool="x", risk="extreme",
            rationale="r", rollback="r",
        )
