"""Launch one specialist agent as a standalone A2A server.

Usage:
    python -m incident_response.a2a_server monitoring
    python -m incident_response.a2a_server diagnostic
    python -m incident_response.a2a_server remediation
    python -m incident_response.a2a_server postmortem

Each invocation starts a Starlette app (via ADK's `to_a2a`) exposing the
agent's AgentCard at /.well-known/agent-card.json and the A2A JSON-RPC
endpoint at /, so the coordinator (or any other A2A client) can discover and
call it over HTTP -- real inter-process agent-to-agent communication, not an
in-process function call.
"""
from __future__ import annotations

import argparse
import sys

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from incident_response.agents.registry import build, port_for
from incident_response.config import settings
from incident_response.tracing import logger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_name", choices=["monitoring", "diagnostic", "remediation", "postmortem"])
    parser.add_argument("--host", default=settings.agent_host)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    port = args.port or port_for(args.agent_name)
    agent = build(args.agent_name)
    app = to_a2a(agent, host=args.host, port=port, protocol="http")

    logger.info(
        "Starting A2A server for '%s' at http://%s:%d (agent card: /.well-known/agent-card.json)",
        args.agent_name,
        args.host,
        port,
    )
    uvicorn.run(app, host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    sys.exit(main())
