"""Maps agent name -> (builder, port) so the A2A launcher and the coordinator
agree on a single source of truth."""
from __future__ import annotations

from google.adk.agents import BaseAgent

from incident_response.agents import (
    diagnostic_agent,
    monitoring_agent,
    postmortem_agent,
    remediation_agent,
)
from incident_response.config import AGENT_PORTS

BUILDERS = {
    "monitoring": monitoring_agent.build_agent,
    "diagnostic": diagnostic_agent.build_agent,
    "remediation": remediation_agent.build_agent,
    "postmortem": postmortem_agent.build_agent,
}


def build(agent_name: str) -> BaseAgent:
    if agent_name not in BUILDERS:
        raise KeyError(f"Unknown agent '{agent_name}'. Available: {list(BUILDERS)}")
    return BUILDERS[agent_name]()


def port_for(agent_name: str) -> int:
    return AGENT_PORTS[agent_name]
