"""Simulated metrics/log/action-execution tools.

Chaos injection is shared with knowledge_base.py via `data/chaos.py`; see
that module's docstring for why chaos state is process-local.
"""
from __future__ import annotations

from incident_response.data.chaos import SimulatedBackendUnavailableError, maybe_fail, scenario_for_service

# Kept as the public name other modules import; same type as the shared error
# so `except TelemetryUnavailableError` and `except SimulatedBackendUnavailableError`
# are interchangeable.
TelemetryUnavailableError = SimulatedBackendUnavailableError


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
    scenario = scenario_for_service(service)
    maybe_fail("get_metrics_snapshot", scenario, subject=service)
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
    scenario = scenario_for_service(service)
    maybe_fail("get_recent_logs", scenario, subject=service)
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
    scenario = scenario_for_service(service)
    maybe_fail("simulate_execute_action", scenario, subject=service, call_key=f"{service}:{step_id}")
    return {
        "status": "success",
        "detail": f"Executed '{action}' against {service} (simulated). "
        f"Verified metrics returned to baseline after 30s cooldown.",
    }
