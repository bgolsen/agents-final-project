"""Catalog of known remediation actions, searchable by symptom keywords.

Mirrors `knowledge_base.py`'s approach: a small, transparent keyword-overlap
ranking so both the LLM-driven remediation agent and its deterministic
fallback can call the same function and get a real (not canned) ranked list.
"""
from __future__ import annotations

from incident_response.data.text_utils import tokenize

CATALOG: list[dict] = [
    {
        "id": "circuit-breaker",
        "action": "Add a circuit breaker with a short timeout around the failing downstream client",
        "tool": "deploy_controller",
        "risk": "medium",
        "rationale": "Prevents thread/connection exhaustion from a slow or hanging downstream dependency.",
        "rollback": "Feature-flag the breaker off to restore direct calls.",
        "keywords": ["timeout", "downstream", "dependency", "cascading", "latency", "payment-gateway", "circuit", "breaker"],
    },
    {
        "id": "rotate-certificate",
        "action": "Rotate the expired/expiring TLS certificate via the secrets manager",
        "tool": "cert_manager",
        "risk": "low",
        "rationale": "Directly resolves handshake failures caused by certificate expiry.",
        "rollback": "Re-issue previous certificate if the new one is misconfigured.",
        "keywords": ["certificate", "tls", "expired", "handshake", "ssl"],
    },
    {
        "id": "rollback-deploy",
        "action": "Roll back the most recent deploy on the affected service",
        "tool": "deploy_controller",
        "risk": "medium",
        "rationale": "Reverts a regression introduced by a recent code or config change.",
        "rollback": "Roll forward once a fix is verified in staging.",
        "keywords": ["deploy", "leak", "regression", "release", "rollout"],
    },
    {
        "id": "recycle-connection-pool",
        "action": "Recycle the exhausted DB connection pool and cap max connection hold time",
        "tool": "db_admin",
        "risk": "medium",
        "rationale": "Frees leaked/held connections so new requests can be served.",
        "rollback": "Restore previous pool configuration if recycling causes new errors.",
        "keywords": ["connection", "pool", "database", "exhaustion", "postgres", "max_connections"],
    },
    {
        "id": "warm-cache-coalesce",
        "action": "Warm the cache and enable request coalescing for cache-miss stampedes",
        "tool": "cache_admin",
        "risk": "low",
        "rationale": "Prevents a thundering-herd of cache-miss requests from overwhelming the origin store.",
        "rollback": "Disable coalescing if it introduces latency regressions.",
        "keywords": ["cache", "stampede", "thundering", "herd", "restart", "cold"],
    },
    {
        "id": "revert-config",
        "action": "Revert the last configuration push",
        "tool": "config_admin",
        "risk": "low",
        "rationale": "Undoes a bad config push (e.g. an incorrect rate-limit) directly causing the errors.",
        "rollback": "Re-apply the config once corrected and reviewed.",
        "keywords": ["config", "misconfiguration", "rate", "limit", "rate-limit"],
    },
    {
        "id": "rotate-logs-free-disk",
        "action": "Force log rotation/compaction and lower log verbosity to free disk space",
        "tool": "ops_admin",
        "risk": "low",
        "rationale": "Resolves disk-full write failures caused by unrotated debug logs.",
        "rollback": "Restore previous log level once disk headroom is confirmed.",
        "keywords": ["disk", "logs", "rotation", "storage", "enospc", "full"],
    },
    {
        "id": "isolate-noisy-neighbor",
        "action": "Move the co-located batch workload to a dedicated node pool and set CPU limits",
        "tool": "infra_admin",
        "risk": "medium",
        "rationale": "Stops a noisy-neighbor workload from starving the affected service of CPU.",
        "rollback": "Move the workload back if isolation causes scheduling issues.",
        "keywords": ["cpu", "saturation", "noisy", "neighbor", "throttling", "infrastructure"],
    },
    {
        "id": "page-vendor",
        "action": "Open an incident with the upstream/downstream vendor and request status",
        "tool": "vendor_admin",
        "risk": "low",
        "rationale": "Applies when the root cause is outside our infrastructure (third-party outage/deploy).",
        "rollback": "N/A -- informational/coordination action.",
        "keywords": ["vendor", "downstream", "provider", "third-party", "upstream"],
    },
    {
        "id": "restart-service",
        "action": "Perform a rolling restart of the affected service",
        "tool": "deploy_controller",
        "risk": "low",
        "rationale": "Generic mitigation that clears leaked in-process state (threads, memory, stuck connections) while a root-cause fix is prepared.",
        "rollback": "N/A -- restart is non-destructive.",
        "keywords": ["restart", "generic", "leak", "memory", "oom", "heap"],
    },
]


def list_remediation_catalog(query: str, top_k: int = 5) -> list[dict]:
    """Search the remediation-action catalog for actions relevant to a set of symptoms.

    Args:
        query: free-text symptoms/root-cause description.
        top_k: max number of ranked actions to return.

    Returns:
        Ranked list of catalog entries (id, action, tool, risk, rationale,
        rollback), most relevant first, each with a `score` field. Falls back
        to the generic "restart-service" action if nothing else matches.
    """
    query_tokens = tokenize(query)
    scored = []
    for entry in CATALOG:
        corpus_tokens = tokenize(" ".join([entry["action"], *entry["keywords"]]))
        overlap = query_tokens & corpus_tokens
        score = len(overlap) / max(len(query_tokens), 1)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [{**e, "score": round(s, 3)} for s, e in scored[:top_k]]
    if not results:
        fallback = next(e for e in CATALOG if e["id"] == "restart-service")
        results = [{**fallback, "score": 0.0}]
    return results
