"""Renders an IncidentState as a human-readable HTML report -- a much
richer view of "what happened and why" than terminal scrollback: every
agent's full structured reasoning (decomposition, hypotheses + evidence,
goal/step plan, execution results, postmortem), plus which calls fell back
to degraded mode and why. Auto-refreshes while the incident is still in
flight so it can be left open in a browser during a live demo.
"""
from __future__ import annotations

import html
import json

from incident_response.coordinator import IncidentState

TERMINAL_STATUSES = {"closed", "rejected", "failed"}

STATUS_COLORS = {
    "triaging": "#5b8def", "diagnosing": "#5b8def", "planning": "#5b8def",
    "awaiting_approval": "#e0a72e", "executing": "#5b8def",
    "closed": "#3fb56f", "rejected": "#c15b5b", "failed": "#c15b5b",
}
SEVERITY_COLORS = {"low": "#5b8def", "medium": "#e0a72e", "high": "#e0793f", "critical": "#c15b5b"}
RISK_COLORS = {"low": "#3fb56f", "medium": "#e0a72e", "high": "#c15b5b"}
DECISION_COLORS = {"approve": "#3fb56f", "reject": "#c15b5b", "modify": "#e0a72e"}

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  background: #101215; color: #e4e6eb; margin: 0; padding: 2rem 1.5rem 4rem;
  line-height: 1.5;
}
.wrap { max-width: 980px; margin: 0 auto; }
a { color: #7aa7ff; }
h1 { font-size: 1.5rem; margin: 0 0 0.2rem; }
h2 { font-size: 1.05rem; text-transform: uppercase; letter-spacing: 0.04em; color: #9aa3b2;
     border-bottom: 1px solid #262a31; padding-bottom: 0.4rem; margin: 2.2rem 0 1rem; }
.meta { color: #9aa3b2; font-size: 0.9rem; }
.badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.78rem;
         font-weight: 600; color: #0b0c0e; }
.pill { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 5px; font-size: 0.75rem;
        background: #1c2027; border: 1px solid #2a2f38; color: #c7cdd8; margin-right: 0.3rem; }
.card { background: #171a1f; border: 1px solid #262a31; border-radius: 10px; padding: 1.1rem 1.3rem; margin-bottom: 0.9rem; }
.card h3 { margin: 0 0 0.5rem; font-size: 1rem; }
.agent-tag { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: #7aa7ff;
             font-weight: 700; margin-bottom: 0.3rem; }
.degraded { color: #e0a72e; font-size: 0.8rem; margin-top: 0.5rem; }
.degraded::before { content: "\\26A0  "; }
table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; font-size: 0.88rem; }
th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #22262d; vertical-align: top; }
th { color: #9aa3b2; font-weight: 600; }
.hyp { border-left: 3px solid #2a2f38; padding: 0.5rem 0 0.5rem 0.8rem; margin: 0.6rem 0; }
.hyp.leading { border-left-color: #3fb56f; background: #14201a; border-radius: 0 6px 6px 0; }
.hyp .conf { float: right; color: #9aa3b2; font-size: 0.82rem; }
.evidence { font-size: 0.82rem; color: #b7bec9; margin: 0.3rem 0 0; padding-left: 1.1rem; }
.goal { margin-bottom: 0.9rem; }
.goal-title { font-weight: 700; margin-bottom: 0.3rem; }
.step { border: 1px solid #262a31; border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; }
.step .action { font-weight: 600; }
.step .rationale, .step .rollback { font-size: 0.82rem; color: #9aa3b2; margin-top: 0.2rem; }
.notes { background: #241c14; border: 1px solid #4a3620; border-radius: 8px; padding: 0.8rem 1rem; margin: 0.6rem 0; }
.notes.err { background: #241616; border-color: #4a2020; }
.timeline li { margin-bottom: 0.35rem; }
details summary { cursor: pointer; color: #9aa3b2; font-size: 0.85rem; margin-top: 2rem; }
pre.raw { background: #0b0c0e; border: 1px solid #262a31; border-radius: 8px; padding: 1rem; overflow-x: auto; font-size: 0.78rem; }
.hitl-box { border: 1px dashed #e0a72e; border-radius: 8px; padding: 1rem 1.2rem; color: #e0c98f; }
.hitl-box p { margin-top: 0; }
.hitl-form label { display: block; font-size: 0.85rem; color: #c7cdd8; margin: 0.7rem 0 0.25rem; }
.hitl-form input[type="text"], .hitl-form textarea, .hitl-form select {
  width: 100%; background: #10131a; border: 1px solid #2a2f38; border-radius: 6px;
  color: #e4e6eb; padding: 0.45rem 0.6rem; font-family: inherit; font-size: 0.9rem;
}
.hitl-form textarea { resize: vertical; }
.hitl-buttons { display: flex; gap: 0.6rem; margin-top: 1rem; }
.hitl-buttons button {
  flex: 1; border: none; border-radius: 6px; padding: 0.6rem 1rem; font-size: 0.9rem;
  font-weight: 700; cursor: pointer; color: #0b0c0e;
}
.hitl-buttons .btn-approve { background: #3fb56f; }
.hitl-buttons .btn-modify { background: #e0a72e; }
.hitl-buttons .btn-reject { background: #c15b5b; }
.hitl-buttons button:hover { filter: brightness(1.1); }
"""


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}">{html.escape(text)}</span>'


def _esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def _triage_section(triage) -> str:
    if triage is None:
        return '<div class="card"><div class="agent-tag">Monitoring Agent</div>pending...</div>'
    rows = "".join(
        f"<tr><td>{_badge(a.severity, SEVERITY_COLORS.get(a.severity, '#5b8def'))}</td>"
        f"<td>{_esc(a.metric)}</td><td>{_esc(a.observation)}</td></tr>"
        for a in triage.anomalies
    )
    gaps = "".join(f"<li>{_esc(g)}</li>" for g in triage.data_gaps)
    degraded = '<div class="degraded">Operating in degraded mode: LLM unavailable, rule-based fallback used.</div>' if triage.degraded_mode else ""
    return f"""
<div class="card">
  <div class="agent-tag">Monitoring Agent &rarr; TriageReport</div>
  <h3>{_badge(triage.severity, SEVERITY_COLORS.get(triage.severity, '#5b8def'))} confidence {triage.confidence:.2f}</h3>
  <p>{_esc(triage.summary)}</p>
  <table><tr><th>Severity</th><th>Metric</th><th>Observation</th></tr>{rows}</table>
  {f'<p><strong>Data gaps</strong> (agent adapted rather than failing):</p><ul>{gaps}</ul>' if gaps else ''}
  {degraded}
</div>"""


def _diagnosis_section(diag) -> str:
    if diag is None:
        return '<div class="card"><div class="agent-tag">Diagnostic Agent</div>pending...</div>'
    decomp = "".join(
        f"<tr><td>{_esc(d.question)}</td><td>{_esc(d.finding)}</td></tr>" for d in diag.decomposition
    )
    hyps = ""
    for h in diag.hypotheses:
        leading = h.id == diag.leading_hypothesis_id
        ev = "".join(f"<li>{_esc(e)}</li>" for e in h.supporting_evidence)
        similar = (
            f'<p class="evidence">Similar past incidents: {", ".join(h.similar_past_incidents)}</p>'
            if h.similar_past_incidents else ""
        )
        hyps += f"""
<div class="hyp{' leading' if leading else ''}">
  <span class="conf">confidence {h.confidence:.2f}{' &mdash; LEADING' if leading else ''}</span>
  <strong>[{_esc(h.id)}]</strong> {_esc(h.statement)}
  <ul class="evidence">{ev}</ul>
  {similar}
</div>"""
    degraded = '<div class="degraded">Operating in degraded mode: LLM unavailable, rule-based fallback used.</div>' if diag.degraded_mode else ""
    return f"""
<div class="card">
  <div class="agent-tag">Diagnostic Agent &rarr; DiagnosticReport</div>
  <h3>Decomposition (why the model asked what it asked)</h3>
  <table><tr><th>Sub-question</th><th>Finding</th></tr>{decomp}</table>
  <h3 style="margin-top:1rem">Ranked root-cause hypotheses</h3>
  {hyps}
  <p class="evidence"><strong>Unresolved uncertainty:</strong> {_esc(diag.unresolved_uncertainty)}</p>
  {degraded}
</div>"""


def _plan_section(plan) -> str:
    if plan is None:
        return '<div class="card"><div class="agent-tag">Remediation Agent</div>pending...</div>'
    goals_html = ""
    for g in plan.goals:
        recommended = g.goal == plan.ranked_recommendation
        steps = "".join(
            f"""<div class="step">
  <div class="action">{_badge(s.risk, RISK_COLORS.get(s.risk, '#5b8def'))} [{_esc(s.id)}] {_esc(s.action)}</div>
  <div class="rationale"><strong>Why:</strong> {_esc(s.rationale)}</div>
  <div class="rollback"><strong>Rollback:</strong> {_esc(s.rollback)}</div>
</div>"""
            for s in g.steps
        )
        goals_html += f"""
<div class="goal">
  <div class="goal-title">{_esc(g.goal)}{' &mdash; recommended' if recommended else ''}</div>
  {steps}
</div>"""
    degraded = '<div class="degraded">Operating in degraded mode: LLM unavailable, rule-based fallback used.</div>' if plan.degraded_mode else ""
    return f"""
<div class="card">
  <div class="agent-tag">Remediation Agent &rarr; RemediationPlan</div>
  {goals_html}
  <p class="evidence"><strong>Risk summary:</strong> {_esc(plan.risk_summary)}</p>
  {degraded}
</div>"""


def _hitl_form(state: IncidentState) -> str:
    plan = state.plan
    goal_options = "".join(
        f'<option value="{_esc(g.goal)}"{" selected" if plan and g.goal == plan.ranked_recommendation else ""}>'
        f'{_esc(g.goal)}{" (recommended)" if plan and g.goal == plan.ranked_recommendation else ""}</option>'
        for g in (plan.goals if plan else [])
    )
    return f"""
<div class="hitl-box">
  <p><strong>Awaiting your decision.</strong> Nothing has executed yet.</p>
  <form method="POST" action="/incidents/{state.incident_id}/decision-form" class="hitl-form">
    <label>Your name
      <input type="text" name="reviewer" required placeholder="e.g. grady">
    </label>
    <label>Notes (why -- shown in the postmortem)
      <textarea name="notes" rows="2" placeholder="optional, but recommended"></textarea>
    </label>
    <label>Goal to run if you click Modify (Approve always uses the recommendation)
      <select name="modified_goal">
        {goal_options}
      </select>
    </label>
    <div class="hitl-buttons">
      <button type="submit" name="decision" value="approve" class="btn-approve">Approve</button>
      <button type="submit" name="decision" value="modify" class="btn-modify">Modify &amp; run selected goal</button>
      <button type="submit" name="decision" value="reject" class="btn-reject">Reject</button>
    </div>
  </form>
</div>"""


def _hitl_section(state: IncidentState) -> str:
    if state.decision is None:
        if state.status == "awaiting_approval":
            return _hitl_form(state)
        return '<div class="card">not reached yet</div>'
    d = state.decision
    return f"""
<div class="card">
  <div class="agent-tag">Human-in-the-loop checkpoint</div>
  <h3>{_badge(d.decision, DECISION_COLORS.get(d.decision, '#5b8def'))} by {_esc(d.reviewer)}</h3>
  {f'<p>{_esc(d.notes)}</p>' if d.notes else ''}
  {f'<p class="evidence">Modified goal requested: <strong>{_esc(d.modified_goal)}</strong></p>' if d.modified_goal else ''}
</div>"""


def _execution_section(state: IncidentState) -> str:
    if not state.execution_log:
        note = "No steps executed (human rejected the plan)." if state.decision and state.decision.decision == "reject" else "pending..."
        return f'<div class="card"><div class="agent-tag">Execution</div>{note}</div>'
    rows = "".join(
        f'<tr><td>{_badge(s.status, "#3fb56f" if s.status == "success" else "#c15b5b")}</td>'
        f"<td>{_esc(s.action)}</td><td>{_esc(s.detail)}</td></tr>"
        for s in state.execution_log
    )
    return f"""
<div class="card">
  <div class="agent-tag">Execution (simulated, retried on transient failure)</div>
  <table><tr><th>Status</th><th>Step</th><th>Detail</th></tr>{rows}</table>
</div>"""


def _postmortem_section(pm) -> str:
    if pm is None:
        return '<div class="card"><div class="agent-tag">Postmortem Agent</div>pending...</div>'
    timeline = "".join(f"<li>{_esc(t)}</li>" for t in pm.timeline)
    lessons = "".join(f"<li>{_esc(l)}</li>" for l in pm.lessons_learned)
    actions = "".join(f"<li>{_esc(a)}</li>" for a in pm.action_items)
    degraded = '<div class="degraded">Operating in degraded mode: LLM unavailable, rule-based fallback used.</div>' if pm.degraded_mode else ""
    return f"""
<div class="card">
  <div class="agent-tag">Postmortem Agent &rarr; PostmortemDoc</div>
  <h3>{_esc(pm.title)}</h3>
  <ul class="timeline">{timeline}</ul>
  <p><strong>Root cause:</strong> {_esc(pm.root_cause)}</p>
  <p><strong>Impact:</strong> {_esc(pm.impact)}</p>
  <p><strong>Lessons learned</strong></p><ul>{lessons}</ul>
  <p><strong>Action items</strong></p><ul>{actions}</ul>
  {degraded}
</div>"""


def _resilience_notes(state: IncidentState) -> str:
    if not state.coordinator_notes:
        return ""
    items = "".join(f"<li>{_esc(n)}</li>" for n in state.coordinator_notes)
    return f"""
<div class="notes err">
  <strong>Coordinator resilience events</strong> (a downstream agent or tool was unreachable and
  the coordinator fell back to a local deterministic path instead of aborting the incident):
  <ul>{items}</ul>
</div>"""


def render_incident_html(state: IncidentState) -> str:
    # No auto-refresh once a human needs to act -- a timed reload would wipe
    # out whatever they're mid-typing into the approval form below.
    no_refresh_statuses = TERMINAL_STATUSES | {"awaiting_approval"}
    refresh = "" if state.status in no_refresh_statuses else '<meta http-equiv="refresh" content="3">'
    status_color = STATUS_COLORS.get(state.status, "#5b8def")
    raw = html.escape(json.dumps(state.model_dump(), indent=2))
    return f"""<!doctype html>
<html><head><meta charset="utf-8">{refresh}
<title>{_esc(state.incident_id)} -- incident report</title>
<style>{CSS}</style></head>
<body><div class="wrap">
  <p class="meta"><a href="/dashboard">&larr; all incidents</a></p>
  <h1>{_esc(state.incident_id)} {_badge(state.status, status_color)}</h1>
  <p class="meta">
    <span class="pill">scenario: {_esc(state.scenario_id)}</span>
    <span class="pill">service: {_esc(state.service)}</span>
    <span class="pill">created: {_esc(state.created_at)}</span>
    <span class="pill">updated: {_esc(state.updated_at)}</span>
  </p>
  {'<p class="meta">This page auto-refreshes every 3s while the incident is in flight.</p>' if refresh else ''}

  {_resilience_notes(state)}

  <h2>1. Triage</h2>
  {_triage_section(state.triage)}

  <h2>2. Diagnosis</h2>
  {_diagnosis_section(state.diagnosis)}

  <h2>3. Remediation plan</h2>
  {_plan_section(state.plan)}

  <h2>4. Human-in-the-loop decision</h2>
  {_hitl_section(state)}

  <h2>5. Execution</h2>
  {_execution_section(state)}

  <h2>6. Postmortem</h2>
  {_postmortem_section(state.postmortem)}

  <details>
    <summary>Raw incident state (JSON)</summary>
    <pre class="raw">{raw}</pre>
  </details>
</div></body></html>"""


def render_dashboard_html(states: list[IncidentState]) -> str:
    if not states:
        rows = '<tr><td colspan="5" class="meta">No incidents yet. POST /incidents to start one.</td></tr>'
    else:
        rows = ""
        for s in sorted(states, key=lambda s: s.created_at, reverse=True):
            rows += (
                f'<tr><td><a href="/incidents/{s.incident_id}/report">{_esc(s.incident_id)}</a></td>'
                f"<td>{_badge(s.status, STATUS_COLORS.get(s.status, '#5b8def'))}</td>"
                f"<td>{_esc(s.scenario_id)}</td><td>{_esc(s.service)}</td>"
                f"<td class='meta'>{_esc(s.updated_at)}</td></tr>"
            )
    any_active = any(s.status not in TERMINAL_STATUSES for s in states)
    refresh = '<meta http-equiv="refresh" content="4">' if any_active else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8">{refresh}
<title>Incident dashboard</title><style>{CSS}</style></head>
<body><div class="wrap">
  <h1>Incidents</h1>
  <p class="meta">Live view of every incident the coordinator has handled this session.</p>
  <table><tr><th>ID</th><th>Status</th><th>Scenario</th><th>Service</th><th>Updated</th></tr>{rows}</table>
</div></body></html>"""
