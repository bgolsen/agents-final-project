"""Tests for the simulated telemetry / knowledge base / remediation catalog."""
from __future__ import annotations

import pytest

from incident_response.data.knowledge_base import search_knowledge_base
from incident_response.data.remediation_catalog import list_remediation_catalog
from incident_response.data.telemetry import (
    TelemetryUnavailableError,
    get_metrics_snapshot,
    get_recent_logs,
    simulate_execute_action,
)


def test_knowledge_base_ranks_relevant_incident_first():
    results = search_knowledge_base("connection pool exhaustion database max_connections", top_k=3)
    assert results
    assert results[0]["id"] == "INC-0877"


def test_knowledge_base_no_match_returns_empty():
    assert search_knowledge_base("zzz_no_such_symptom_zzz") == []


def test_remediation_catalog_falls_back_to_generic_restart():
    results = list_remediation_catalog("zzz_totally_unrelated_query_zzz")
    assert len(results) == 1
    assert results[0]["id"] == "restart-service"


def test_remediation_catalog_ranks_relevant_action_first():
    results = list_remediation_catalog("expired tls certificate handshake failure ssl")
    assert results[0]["id"] == "rotate-certificate"


def test_metrics_snapshot_flags_anomalies_by_threshold():
    snapshot = get_metrics_snapshot("checkout-service")
    metrics = snapshot["metrics"]
    assert metrics["error_rate_pct"]["is_anomalous"] is True
    assert metrics["cpu_pct"]["is_anomalous"] is False


def test_metrics_snapshot_unknown_service_returns_empty():
    snapshot = get_metrics_snapshot("some-unmonitored-service")
    assert snapshot["metrics"] == {}


def test_chaos_injection_fails_then_succeeds(monkeypatch):
    # payment-db scenario configures get_metrics_snapshot to fail exactly once.
    from incident_response.data import telemetry

    monkeypatch.setattr("incident_response.data.chaos._call_counts", {})
    with pytest.raises(TelemetryUnavailableError):
        telemetry.get_metrics_snapshot("payment-db")
    # second call for the same service succeeds
    snapshot = telemetry.get_metrics_snapshot("payment-db")
    assert snapshot["service"] == "payment-db"


def test_execute_action_chaos_resolves_scenario_from_plain_service_name(monkeypatch):
    # Regression test: simulate_execute_action passes a composite
    # "service:step_id" call-key, which must NOT be used to look up the
    # scenario (only plain service names match `Scenario.primary_service`/
    # `affected_services`) -- otherwise chaos silently never fires.
    monkeypatch.setattr("incident_response.data.chaos._call_counts", {})
    with pytest.raises(TelemetryUnavailableError):
        simulate_execute_action("S1", "payment-db", "recycle the pool")
    # retry succeeds
    result = simulate_execute_action("S1", "payment-db", "recycle the pool")
    assert result["status"] == "success"


def test_knowledge_base_chaos_resolves_scenario_from_query_text(monkeypatch):
    # auth-cert-expiry scenario configures search_knowledge_base to fail once;
    # the KB tool has no `service` argument, so the scenario must be resolved
    # from the query text itself.
    monkeypatch.setattr("incident_response.data.chaos._call_counts", {})
    with pytest.raises(TelemetryUnavailableError):
        search_knowledge_base("auth-service handshake failure certificate")
    # retry succeeds
    results = search_knowledge_base("auth-service handshake failure certificate")
    assert results


def test_chaos_can_be_disabled(monkeypatch):
    class _NoChaosSettings:
        chaos_mode = False

    monkeypatch.setattr("incident_response.data.chaos.settings", _NoChaosSettings())
    monkeypatch.setattr("incident_response.data.chaos._call_counts", {})
    # would normally fail on the first call; disabled chaos means it never raises
    get_recent_logs("checkout-service")
    get_recent_logs("checkout-service")
