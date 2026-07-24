"""Monitoring Agent -- watches simulated logs/metrics and produces the initial
triage report that seeds the rest of the pipeline.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from incident_response.agents.common import (
    extract_field,
    extract_prompt_text,
    model_to_llm_response,
    on_tool_error,
)
from incident_response.config import settings
from incident_response.data.telemetry import (
    TelemetryUnavailableError,
    get_metrics_snapshot,
    get_recent_logs,
)
from incident_response.schemas import TriageReport
from incident_response.tracing import logger

NAME = "monitoring_agent"

INSTRUCTION = """You are the Monitoring Agent in an incident-response system.

You receive a raw alert (incident_id, service, description) describing a
suspected production incident. Your job:
1. Call `get_metrics_snapshot` for the named service to pull its live metrics.
2. Call `get_recent_logs` for the same service to pull recent log lines.
3. If a tool call fails, note the failure in `data_gaps` and proceed with
   whatever data you do have -- never refuse to answer because one signal is
   missing.
4. Identify anomalies: a metric is anomalous when `value` exceeds `threshold`.
   Grade severity by how far value exceeds threshold (low/medium/high/critical).
5. Produce a TriageReport: a short factual summary, overall severity, the
   affected services, the list of anomalies you found (metric, observation,
   severity), your confidence (0-1), and any data_gaps.

Only report what the data supports. Do not diagnose root cause -- that is a
different agent's job; you are triage only. Always echo the given incident_id
back in your report.

IMPORTANT: always set `degraded_mode` to `false`. That field is reserved for
the system's own automatic fallback path (used only when you are completely
unavailable) and must never be set to `true` by you -- record any data gaps
in `data_gaps` instead, that is the correct place for them.
"""


def _severity_for_ratio(ratio: float) -> str:
    if ratio >= 3:
        return "critical"
    if ratio >= 2:
        return "high"
    if ratio >= 1.2:
        return "medium"
    return "low"


def _heuristic_triage(incident_id: str, service: str) -> TriageReport:
    """Deterministic, tool-driven fallback used when the LLM is unavailable.

    Calls the exact same tools the LLM would have called and derives the
    report from real (simulated) telemetry data via a simple threshold rule,
    rather than fabricating an answer.
    """
    data_gaps: list[str] = []
    anomalies = []
    affected = {service}

    try:
        snapshot = get_metrics_snapshot(service)
        for metric, m in snapshot["metrics"].items():
            if m["is_anomalous"]:
                ratio = m["value"] / m["threshold"] if m["threshold"] else 1.0
                anomalies.append(
                    {
                        "metric": metric,
                        "observation": f"{metric}={m['value']}{m['unit']} vs threshold {m['threshold']}{m['unit']} (baseline {m['baseline']}{m['unit']})",
                        "severity": _severity_for_ratio(ratio),
                    }
                )
    except TelemetryUnavailableError as exc:
        data_gaps.append(f"metrics unavailable: {exc}")

    log_lines: list[str] = []
    try:
        logs = get_recent_logs(service)
        log_lines = logs["lines"]
    except TelemetryUnavailableError as exc:
        data_gaps.append(f"logs unavailable: {exc}")

    severities = [a["severity"] for a in anomalies]
    if "critical" in severities:
        overall = "critical"
    elif "high" in severities:
        overall = "high"
    elif "medium" in severities:
        overall = "medium"
    else:
        overall = "low"

    error_lines = [l for l in log_lines if "ERROR" in l]
    summary = (
        f"{len(anomalies)} anomalous metric(s) detected on {service}. "
        + (f"{len(error_lines)} ERROR log line(s) observed. " if error_lines else "")
        + (
            "Data incomplete: " + "; ".join(data_gaps)
            if data_gaps
            else "All telemetry sources responded."
        )
    )

    return TriageReport(
        incident_id=incident_id,
        summary=summary,
        severity=overall,
        affected_services=sorted(affected),
        anomalies=anomalies,
        confidence=0.55 if not data_gaps else 0.35,
        data_gaps=data_gaps,
        degraded_mode=True,
    )


def _on_model_error(*, callback_context, llm_request, error):
    prompt_text = extract_prompt_text(llm_request)
    incident_id = extract_field(prompt_text, "incident_id", "unknown")
    service = extract_field(prompt_text, "service", "unknown-service")
    logger.warning(
        "monitoring_agent: LLM call failed for incident %s (%s); falling back to rule-based triage",
        incident_id,
        error,
    )
    report = _heuristic_triage(incident_id, service)
    return model_to_llm_response(report)


def build_agent() -> LlmAgent:
    return LlmAgent(
        name=NAME,
        description="Watches simulated production logs/metrics and produces a factual triage report for a suspected incident.",
        model=settings.adk_model,
        instruction=INSTRUCTION,
        tools=[get_metrics_snapshot, get_recent_logs],
        output_schema=TriageReport,
        on_model_error_callback=_on_model_error,
        on_tool_error_callback=on_tool_error,
    )
