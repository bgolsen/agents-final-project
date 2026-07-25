"""Coordinator HTTP API.

This is the single HTTP surface both n8n and the CLI demo talk to. It owns
the in-memory incident store and is the HITL gate: `POST /incidents` runs
triage -> diagnosis -> planning and stops; nothing gets executed until a
human calls `POST /incidents/{id}/decision`.

    POST /incidents                       start a new incident from an alert
    GET  /incidents                       list all incidents (brief)
    GET  /incidents/{id}                  full incident state
    GET  /approvals/{id}                  poll target for n8n's Wait node
    POST /incidents/{id}/decision         the HITL checkpoint (JSON, used by n8n/curl)
    POST /incidents/{id}/decision-form    the HITL checkpoint (HTML form, used by the dashboard)
    POST /notify                          mock notification sink (n8n -> here)
    GET  /dashboard                       human-readable live view of all incidents,
                                           including past ones reloaded from runs/ on startup
    GET  /incidents/{id}/report           human-readable live view of one incident
                                           (every agent's reasoning, an in-page approve/
                                           reject/modify form, execution, postmortem --
                                           auto-refreshes while still in flight)
"""
from __future__ import annotations

import asyncio

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from incident_response.api.report import render_dashboard_html, render_incident_html
from incident_response.coordinator import (
    RUNS_DIR,
    IncidentState,
    new_incident,
    resume_after_decision,
    run_to_approval,
    save_state,
)
from incident_response.data.scenarios import SCENARIOS
from incident_response.schemas import ApprovalDecision
from incident_response.tracing import logger

app = FastAPI(title="Incident Response Coordinator")


def _load_incidents_from_disk() -> dict[str, IncidentState]:
    """Reload previously-saved incidents (runs/<id>.json) so the dashboard
    shows full history across coordinator restarts, not just whatever was
    created since the process last started."""
    incidents: dict[str, IncidentState] = {}
    if not RUNS_DIR.exists():
        return incidents
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            state = IncidentState.model_validate_json(path.read_text(encoding="utf-8"))
            incidents[state.incident_id] = state
        except Exception as exc:  # noqa: BLE001 - a corrupt/partial file shouldn't block startup
            logger.warning("could not reload saved incident from %s: %s", path, exc)
    if incidents:
        logger.info("reloaded %d incident(s) from %s", len(incidents), RUNS_DIR)
    return incidents


_incidents: dict[str, IncidentState] = _load_incidents_from_disk()
_lock = asyncio.Lock()
_notifications: list[dict] = []


class StartIncidentRequest(BaseModel):
    scenario_id: str


class NotifyRequest(BaseModel):
    channel: str = "ops-alerts"
    message: str


def _get_or_404(incident_id: str) -> IncidentState:
    state = _incidents.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"unknown incident_id '{incident_id}'")
    return state


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    return render_dashboard_html(list(_incidents.values()))


@app.get("/incidents/{incident_id}/report", response_class=HTMLResponse)
async def incident_report(incident_id: str) -> str:
    return render_incident_html(_get_or_404(incident_id))


@app.get("/scenarios")
async def list_scenarios() -> dict:
    return {
        sid: {"title": s.title, "primary_service": s.primary_service}
        for sid, s in SCENARIOS.items()
    }


@app.post("/incidents")
async def start_incident(req: StartIncidentRequest) -> dict:
    if req.scenario_id not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown scenario_id '{req.scenario_id}'. Available: {list(SCENARIOS)}",
        )
    state = new_incident(req.scenario_id)
    async with _lock:
        _incidents[state.incident_id] = state
    logger.info("API: starting incident %s (scenario=%s)", state.incident_id, req.scenario_id)
    try:
        state = await run_to_approval(state)
    except Exception as exc:  # noqa: BLE001 - surface as a failed incident, not a 500 that loses state
        logger.exception("API: incident %s failed during triage/diagnosis/planning", state.incident_id)
        state.status = "failed"
        state.coordinator_notes.append(f"pipeline failed before reaching approval: {exc}")
        save_state(state)
    async with _lock:
        _incidents[state.incident_id] = state
    return state.model_dump()


@app.get("/incidents")
async def list_incidents() -> list[dict]:
    return [
        {"incident_id": s.incident_id, "status": s.status, "service": s.service, "scenario_id": s.scenario_id}
        for s in _incidents.values()
    ]


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str) -> dict:
    return _get_or_404(incident_id).model_dump()


@app.get("/approvals/{incident_id}")
async def get_approval_status(incident_id: str) -> dict:
    state = _get_or_404(incident_id)
    return {
        "incident_id": incident_id,
        "status": state.status,
        "plan": state.plan.model_dump() if state.plan else None,
    }


async def _apply_decision(incident_id: str, decision: ApprovalDecision) -> IncidentState:
    """Shared by the JSON and HTML-form decision endpoints so both routes
    apply exactly the same HITL logic and failure handling."""
    state = _get_or_404(incident_id)
    if state.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"incident {incident_id} is '{state.status}', not awaiting approval",
        )
    logger.info(
        "API: incident %s HITL decision=%s reviewer=%s", incident_id, decision.decision, decision.reviewer
    )
    try:
        state = await resume_after_decision(state, decision)
    except Exception as exc:  # noqa: BLE001
        logger.exception("API: incident %s failed after HITL decision", incident_id)
        state.status = "failed"
        state.coordinator_notes.append(f"pipeline failed after decision: {exc}")
        save_state(state)
    async with _lock:
        _incidents[incident_id] = state
    return state


@app.post("/incidents/{incident_id}/decision")
async def submit_decision(incident_id: str, decision: ApprovalDecision) -> dict:
    state = await _apply_decision(incident_id, decision)
    return state.model_dump()


@app.post("/incidents/{incident_id}/decision-form")
async def submit_decision_form(
    incident_id: str,
    decision: str = Form(...),
    reviewer: str = Form(...),
    notes: str = Form(""),
    modified_goal: str = Form(""),
) -> RedirectResponse:
    """Same HITL gate as `/decision`, but takes an HTML form POST (the
    dashboard's approve/reject/modify buttons) and redirects back to the
    incident's report page instead of returning JSON."""
    approval = ApprovalDecision(
        decision=decision,  # type: ignore[arg-type]  -- validated by ApprovalDecision's Literal
        reviewer=reviewer,
        notes=notes,
        modified_goal=modified_goal or None,
    )
    await _apply_decision(incident_id, approval)
    return RedirectResponse(url=f"/incidents/{incident_id}/report", status_code=303)


@app.post("/notify")
async def notify(req: NotifyRequest) -> dict:
    """Mock notification sink standing in for Slack/PagerDuty/email -- n8n's
    routing step calls this so the routing behavior is visible in the demo
    without needing real chat-ops credentials."""
    entry = {"channel": req.channel, "message": req.message}
    _notifications.append(entry)
    logger.info("NOTIFY [%s]: %s", req.channel, req.message)
    return {"ok": True}


@app.get("/notifications")
async def list_notifications() -> list[dict]:
    return _notifications
