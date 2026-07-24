"""Central configuration loaded from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def _float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


@dataclass(frozen=True)
class Settings:
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    adk_model: str = os.getenv("ADK_MODEL", "gemini-2.5-flash")

    langsmith_tracing: bool = _bool("LANGSMITH_TRACING", True)
    langsmith_api_key: str = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "incident-response-adk")

    agent_host: str = os.getenv("AGENT_HOST", "127.0.0.1")
    monitoring_agent_port: int = _int("MONITORING_AGENT_PORT", 8001)
    diagnostic_agent_port: int = _int("DIAGNOSTIC_AGENT_PORT", 8002)
    remediation_agent_port: int = _int("REMEDIATION_AGENT_PORT", 8003)
    postmortem_agent_port: int = _int("POSTMORTEM_AGENT_PORT", 8004)

    coordinator_host: str = os.getenv("COORDINATOR_HOST", "127.0.0.1")
    coordinator_port: int = _int("COORDINATOR_PORT", 8110)

    chaos_mode: bool = _bool("CHAOS_MODE", True)

    n8n_alert_webhook_url: str = os.getenv("N8N_ALERT_WEBHOOK_URL", "")

    # Optional mode: skip the HITL gate for well-understood, low-stakes plans.
    # Off by default -- every incident stops for a human unless explicitly enabled.
    auto_approve_low_risk: bool = _bool("AUTO_APPROVE_LOW_RISK", False)
    auto_approve_confidence_threshold: float = _float("AUTO_APPROVE_CONFIDENCE_THRESHOLD", 0.75)

    @property
    def has_llm_credentials(self) -> bool:
        return bool(self.google_api_key) or _bool("GOOGLE_GENAI_USE_VERTEXAI", False)


settings = Settings()

AGENT_PORTS = {
    "monitoring": settings.monitoring_agent_port,
    "diagnostic": settings.diagnostic_agent_port,
    "remediation": settings.remediation_agent_port,
    "postmortem": settings.postmortem_agent_port,
}


def agent_card_url(agent_name: str) -> str:
    port = AGENT_PORTS[agent_name]
    return f"http://{settings.agent_host}:{port}/.well-known/agent-card.json"
