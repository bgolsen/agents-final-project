"""Run the coordinator API: python -m incident_response.api"""
from __future__ import annotations

import uvicorn

from incident_response.api.server import app
from incident_response.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.coordinator_host, port=settings.coordinator_port, log_level="warning")
