"""Structured data contracts exchanged between agents over A2A.

Every specialist agent returns one of these Pydantic models (as its ADK
`output_schema`). Because the schema is enforced by the model, the hand-off
between agents is a typed contract rather than free text -- the coordinator
can inspect, log, and persist every field, which is what makes the
hierarchical decomposition below "explicit and inspectable" rather than
hard-coded control flow.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
Risk = Literal["low", "medium", "high"]


class Anomaly(BaseModel):
    metric: str
    observation: str
    severity: Severity


class TriageReport(BaseModel):
    """Output of the Monitoring Agent."""

    incident_id: str
    summary: str
    severity: Severity
    affected_services: list[str]
    anomalies: list[Anomaly]
    confidence: float = Field(ge=0, le=1)
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Signals the agent could not obtain (e.g. a tool failed), "
        "so downstream agents know which conclusions rest on partial information.",
    )
    degraded_mode: bool = False


class DiagnosticSubtask(BaseModel):
    """One node of the explicit root-cause decomposition tree."""

    question: str
    finding: str


class RootCauseHypothesis(BaseModel):
    id: str
    statement: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    similar_past_incidents: list[str] = Field(default_factory=list)


class DiagnosticReport(BaseModel):
    """Output of the Diagnostic Agent."""

    incident_id: str
    decomposition: list[DiagnosticSubtask]
    hypotheses: list[RootCauseHypothesis]
    leading_hypothesis_id: str
    unresolved_uncertainty: str
    degraded_mode: bool = False


class RemediationStep(BaseModel):
    id: str
    action: str
    tool: str
    risk: Risk
    rationale: str
    rollback: str


class RemediationGoal(BaseModel):
    goal: str
    steps: list[RemediationStep]


class RemediationPlan(BaseModel):
    """Output of the Remediation Agent."""

    incident_id: str
    goals: list[RemediationGoal]
    ranked_recommendation: str = Field(description="goal text of the top-ranked plan")
    risk_summary: str
    degraded_mode: bool = False


class ExecutedStep(BaseModel):
    step_id: str
    action: str
    status: Literal["success", "failed", "skipped"]
    detail: str


class PostmortemDoc(BaseModel):
    """Output of the Postmortem Agent."""

    incident_id: str
    title: str
    timeline: list[str]
    root_cause: str
    impact: str
    remediation_taken: list[str]
    human_decisions: list[str]
    lessons_learned: list[str]
    action_items: list[str]
    degraded_mode: bool = False


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject", "modify"]
    reviewer: str
    notes: str = ""
    modified_goal: str | None = Field(
        default=None,
        description="If decision == modify, the goal text the human wants executed instead.",
    )
