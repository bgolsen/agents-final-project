"""Simulated metrics/log/action-execution tools.

Each specialist agent runs as its own process (its own A2A server), so tool
state here is deliberately keyed by `service`/`step_id` rather than kept in a
shared "current incident" global -- there is no shared memory across
processes. Chaos injection (`SCENARIOS[...].chaos`) fails the first N calls
to a given tool for a given service/step so error-handling paths are
exercised deterministically on every demo run.
"""
from __future__ import annotations

from incident_response.config import settings
from incident_response.data.scenarios import SCENARIOS, Scenario

_call_counts: dict[tuple[str, str], int] = {}


class TelemetryUnavailableError(RuntimeError):
    """Raised when a simulated telemetry/execution backend is unreachable."""


def _scenario_for_service(service: str) -> Scenario | None:
    for scenario in SCENARIOS.values():
        if service == scenario.primary_service or service in scenario.affected_services:
            return scenario
    return None


def _maybe_inject_chaos(tool_name: str, service: str, call_key: str | None = None) -> None:
    """Raise on the first `fail_budget` calls to `tool_name` for `service`.

    `call_key` (defaults to `service`) is what the retry counter is keyed by,
    so distinct steps against the same service (e.g. execute-action per
    remediation step) can be tracked independently while still resolving the
    chaos budget from the scenario `service` actually belongs to.
    """
    if not settings.chaos_mode:
        return
    scenario = _scenario_for_service(service)
    if scenario is None:
        return
    fail_budget = scenario.chaos.get(tool_name, 0)
    key = (tool_name, call_key or service)
    _call_counts[key] = _call_counts.get(key, 0) + 1
    attempt = _call_counts[key]
    if attempt <= fail_budget:
        raise TelemetryUnavailableError(
            f"{tool_name}('{service}') timed out (simulated transient failure, "
            f"attempt {attempt}/{fail_budget})"
        )


def get_metrics_snapshot(service: str) -> dict:
    """Fetch a live 15-minute metrics snapshot for a service.

    Args:
        service: the service name, e.g. "checkout-service".

    Returns:
        dict with `service`, `window_minutes`, and `metrics` -- a mapping of
        metric name to {value, baseline, threshold, unit}. A metric is
        anomalous when value exceeds threshold.

    Raises:
        TelemetryUnavailableError: the metrics backend is unreachable
            (simulated transient failure).
    """
    _maybe_inject_chaos("get_metrics_snapshot", service)
    scenario = _scenario_for_service(service)
    if scenario is None:
        return {"service": service, "window_minutes": 15, "metrics": {}}
    return {
        "service": service,
        "window_minutes": 15,
        "metrics": {
            name: {
                "value": m.value,
                "baseline": m.baseline,
                "threshold": m.threshold,
                "unit": m.unit,
                "is_anomalous": m.value > m.threshold,
            }
            for name, m in scenario.metrics.items()
        },
    }


def get_recent_logs(service: str, minutes: int = 15) -> dict:
    """Fetch recent log lines for a service.

    Args:
        service: the service name, e.g. "checkout-service".
        minutes: lookback window in minutes.

    Returns:
        dict with `service` and `lines` (list of raw log strings).

    Raises:
        TelemetryUnavailableError: the log backend is unreachable
            (simulated transient failure).
    """
    _maybe_inject_chaos("get_recent_logs", service)
    scenario = _scenario_for_service(service)
    lines = list(scenario.logs) if scenario else []
    return {"service": service, "window_minutes": minutes, "lines": lines}


def simulate_execute_action(step_id: str, service: str, action: str) -> dict:
    """Execute a remediation action against a service (simulated).

    Args:
        step_id: id of the remediation step being executed.
        service: target service.
        action: human-readable description of the action to perform.

    Returns:
        dict with `status` ("success" or "failed") and `detail`.

    Raises:
        TelemetryUnavailableError: the execution backend is unreachable
            (simulated transient failure) -- callers should retry.
    """
    _maybe_inject_chaos("simulate_execute_action", service, call_key=f"{service}:{step_id}")
    return {
        "status": "success",
        "detail": f"Executed '{action}' against {service} (simulated). "
        f"Verified metrics returned to baseline after 30s cooldown.",
    }
