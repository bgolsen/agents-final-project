"""Canned simulated incidents.

Each scenario supplies the "ground truth" a real monitoring/logging stack
would surface -- metrics with baselines/thresholds and raw log lines -- plus
a `chaos` map that tells the telemetry layer which tool should fail (and how
many times) before succeeding, so the demo can exercise the system's error
handling on every run without relying on real flakiness.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricPoint:
    value: float
    baseline: float
    threshold: float
    unit: str = ""


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    primary_service: str
    affected_services: list[str]
    metrics: dict[str, MetricPoint]
    logs: list[str]
    # tool_name -> number of times that tool should raise before succeeding
    chaos: dict[str, int] = field(default_factory=dict)


SCENARIOS: dict[str, Scenario] = {
    "checkout-latency-spike": Scenario(
        id="checkout-latency-spike",
        title="checkout-service latency & error spike",
        primary_service="checkout-service",
        affected_services=["checkout-service", "payment-gateway-client"],
        metrics={
            "error_rate_pct": MetricPoint(value=22.7, baseline=0.4, threshold=5.0, unit="%"),
            "p99_latency_ms": MetricPoint(value=4300, baseline=190, threshold=600, unit="ms"),
            "cpu_pct": MetricPoint(value=51, baseline=38, threshold=85, unit="%"),
            "thread_pool_saturation_pct": MetricPoint(value=97, baseline=20, threshold=80, unit="%"),
        },
        logs=[
            "WARN  checkout-service payment-gateway-client: request exceeded 2000ms, retrying",
            "ERROR checkout-service payment-gateway-client: timeout after 5000ms calling POST /charge",
            "ERROR checkout-service: thread pool 'http-worker' exhausted (200/200 in use)",
            "WARN  checkout-service: no circuit breaker configured for payment-gateway-client",
            "INFO  payment-gateway-client: upstream provider reported deploy at 09:58 UTC",
        ],
        chaos={"get_recent_logs": 1},
    ),
    "auth-cert-expiry": Scenario(
        id="auth-cert-expiry",
        title="auth-service 5xx spike",
        primary_service="auth-service",
        affected_services=["auth-service", "identity-provider-client"],
        metrics={
            "error_rate_pct": MetricPoint(value=61.0, baseline=0.2, threshold=5.0, unit="%"),
            "p99_latency_ms": MetricPoint(value=310, baseline=150, threshold=600, unit="ms"),
            "cpu_pct": MetricPoint(value=30, baseline=32, threshold=85, unit="%"),
            "handshake_failure_rate_pct": MetricPoint(value=58.0, baseline=0.1, threshold=2.0, unit="%"),
        },
        logs=[
            "ERROR auth-service identity-provider-client: SSL handshake failed: certificate has expired",
            "ERROR auth-service identity-provider-client: SSL handshake failed: certificate has expired",
            "WARN  auth-service: certificate expiry alert was not configured for idp-client.crt",
            "INFO  auth-service: last successful identity-provider handshake at 23:59:41 UTC",
        ],
        chaos={"search_knowledge_base": 1},
    ),
    "payment-db-pool-exhaustion": Scenario(
        id="payment-db-pool-exhaustion",
        title="payment-db connection pool exhaustion",
        primary_service="payment-db",
        affected_services=["payment-db", "payment-service"],
        metrics={
            "error_rate_pct": MetricPoint(value=34.5, baseline=0.3, threshold=5.0, unit="%"),
            "p99_latency_ms": MetricPoint(value=6100, baseline=90, threshold=600, unit="ms"),
            "active_connections_pct": MetricPoint(value=100, baseline=45, threshold=90, unit="%"),
            "cpu_pct": MetricPoint(value=64, baseline=40, threshold=85, unit="%"),
        },
        logs=[
            "ERROR payment-service: could not obtain DB connection from pool within 5000ms",
            "WARN  payment-db: connections in use 20/20 (max_connections reached)",
            "INFO  payment-service: deploy v2.14.0 rolled out at 08:02 UTC (route: /refund early-return)",
            "ERROR payment-db: connection held for 812s without release (query: SELECT ... refunds)",
        ],
        chaos={"get_metrics_snapshot": 1, "simulate_execute_action": 1},
    ),
}


def get_scenario(scenario_id: str) -> Scenario:
    if scenario_id not in SCENARIOS:
        raise KeyError(
            f"Unknown scenario '{scenario_id}'. Available: {list(SCENARIOS)}"
        )
    return SCENARIOS[scenario_id]
