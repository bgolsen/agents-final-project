"""Shared chaos-injection machinery for the simulated backends (telemetry,
knowledge base, remediation execution).

Each specialist agent runs as its own process, so this state is
process-local by design (see telemetry.py's module docstring for the
tradeoff). `SCENARIOS[...].chaos` fails the first N calls to a given tool
for a given service, then lets it succeed, so error-handling paths are
exercised deterministically on every demo run without relying on real
infrastructure flakiness.
"""
from __future__ import annotations

from incident_response.config import settings
from incident_response.data.scenarios import SCENARIOS, Scenario

_call_counts: dict[tuple[str, str], int] = {}


class SimulatedBackendUnavailableError(RuntimeError):
    """Raised when a simulated backend is unreachable (injected chaos)."""


def scenario_for_service(service: str) -> Scenario | None:
    for scenario in SCENARIOS.values():
        if service == scenario.primary_service or service in scenario.affected_services:
            return scenario
    return None


def scenario_for_text(text: str) -> Scenario | None:
    """Resolve a scenario from free text (e.g. a KB search query) by looking
    for any of its service names as a substring -- used by tools that don't
    take an explicit `service` argument."""
    lowered = text.lower()
    for scenario in SCENARIOS.values():
        for name in (scenario.primary_service, *scenario.affected_services):
            if name.lower() in lowered:
                return scenario
    return None

def maybe_fail(tool_name: str, scenario: Scenario | None, *, subject: str, call_key: str | None = None) -> None:
    """Raise on the first `fail_budget` calls to `tool_name` for `scenario`.

    `call_key` (defaults to `subject`) is what the retry counter is keyed
    by, so distinct calls (e.g. one per remediation step) can be tracked
    independently while still resolving the chaos budget from `scenario`.
    """
    if not settings.chaos_mode or scenario is None:
        return
    fail_budget = scenario.chaos.get(tool_name, 0)
    key = (tool_name, call_key or subject)
    _call_counts[key] = _call_counts.get(key, 0) + 1
    attempt = _call_counts[key]
    if attempt <= fail_budget:
        raise SimulatedBackendUnavailableError(
            f"{tool_name}('{subject}') timed out (simulated transient failure, "
            f"attempt {attempt}/{fail_budget})"
        )
