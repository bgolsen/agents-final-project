"""End-to-end CLI demo: spins up the 4 specialist A2A servers + the
coordinator API, files a simulated alert, drives the pipeline to the HITL
checkpoint, prompts a human for approve/reject/modify, then shows execution
and the final postmortem.

Usage:
    python -m incident_response.run_incident
    python -m incident_response.run_incident --scenario auth-cert-expiry
    python -m incident_response.run_incident --no-spawn   # servers already running (e.g. via scripts/start_agents.ps1)
    python -m incident_response.run_incident --auto-approve   # non-interactive, for CI/scripted demos
"""
from __future__ import annotations

import argparse
import atexit
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from incident_response.config import settings
from incident_response.data.scenarios import SCENARIOS

COORDINATOR_BASE = f"http://{settings.coordinator_host}:{settings.coordinator_port}"
AGENTS = ["monitoring", "diagnostic", "remediation", "postmortem"]
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

_procs: list[subprocess.Popen] = []
_log_files: list = []


def _spawn_all() -> None:
    # Agent/coordinator subprocess output (including ADK's internal
    # self-correction retries on structured-output validation, which are
    # noisy but not failures -- the request still succeeds) goes to per
    # process log files instead of the terminal, so the demo output stays
    # readable. See logs/<name>.log if something looks wrong.
    LOGS_DIR.mkdir(exist_ok=True)

    def _spawn(name: str, args: list[str]) -> None:
        log_file = open(LOGS_DIR / f"{name}.log", "w", encoding="utf-8")
        _log_files.append(log_file)
        p = subprocess.Popen([sys.executable, *args], stdout=log_file, stderr=subprocess.STDOUT)
        _procs.append(p)

    for agent in AGENTS:
        _spawn(agent, ["-m", "incident_response.a2a_server", agent])
    _spawn("coordinator", ["-m", "incident_response.api"])
    atexit.register(_shutdown)
    print(f"(agent/coordinator logs are being written to {LOGS_DIR}/)")


def _shutdown() -> None:
    for p in _procs:
        if p.poll() is None:
            p.terminate()
    for p in _procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    for f in _log_files:
        f.close()


def _wait_healthy(timeout_s: float = 30.0) -> None:
    urls = [f"http://{settings.agent_host}:{port}/.well-known/agent-card.json"
            for port in [settings.monitoring_agent_port, settings.diagnostic_agent_port,
                         settings.remediation_agent_port, settings.postmortem_agent_port]]
    urls.append(f"{COORDINATOR_BASE}/health")
    deadline = time.monotonic() + timeout_s
    with httpx.Client() as client:
        for url in urls:
            while True:
                try:
                    r = client.get(url, timeout=2.0)
                    if r.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError(f"timed out waiting for {url} to become healthy")
                time.sleep(0.5)
    print("All agents + coordinator are up.\n")


def _choose_scenario(cli_value: Optional[str]) -> str:
    if cli_value:
        if cli_value not in SCENARIOS:
            print(f"Unknown scenario '{cli_value}'. Available: {list(SCENARIOS)}")
            sys.exit(1)
        return cli_value
    print("Available incident scenarios:")
    ids = list(SCENARIOS)
    for i, sid in enumerate(ids, 1):
        print(f"  {i}. {sid} -- {SCENARIOS[sid].title}")
    choice = input(f"Pick a scenario [1-{len(ids)}] (default 1): ").strip() or "1"
    try:
        return ids[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice, defaulting to the first scenario.")
        return ids[0]


def _print_triage(triage: dict) -> None:
    print("=" * 70)
    print(f"MONITORING AGENT -- triage (severity={triage['severity']}, confidence={triage['confidence']})")
    print("=" * 70)
    print(triage["summary"])
    for a in triage["anomalies"]:
        print(f"  - [{a['severity']}] {a['metric']}: {a['observation']}")
    if triage["data_gaps"]:
        print("  DATA GAPS:")
        for g in triage["data_gaps"]:
            print(f"    ! {g}")
    if triage["degraded_mode"]:
        print("  (degraded mode: LLM unavailable, rule-based fallback used)")
    print()


def _print_diagnosis(diag: dict) -> None:
    print("=" * 70)
    print("DIAGNOSTIC AGENT -- decomposition & ranked hypotheses")
    print("=" * 70)
    for d in diag["decomposition"]:
        print(f"  Q: {d['question']}\n     -> {d['finding']}")
    for h in diag["hypotheses"]:
        marker = "  ** LEADING **" if h["id"] == diag["leading_hypothesis_id"] else ""
        print(f"  [{h['id']}] (confidence {h['confidence']:.2f}){marker}")
        print(f"      {h['statement']}")
        if h["similar_past_incidents"]:
            print(f"      similar past incidents: {', '.join(h['similar_past_incidents'])}")
    print(f"  Unresolved uncertainty: {diag['unresolved_uncertainty']}")
    if diag["degraded_mode"]:
        print("  (degraded mode: LLM unavailable, rule-based fallback used)")
    print()


def _print_plan(plan: dict) -> None:
    print("=" * 70)
    print(f"REMEDIATION AGENT -- plan (recommended: {plan['ranked_recommendation']})")
    print("=" * 70)
    for g in plan["goals"]:
        print(f"  GOAL: {g['goal']}")
        for s in g["steps"]:
            print(f"    [{s['id']}] ({s['risk']} risk) {s['action']}")
            print(f"        rationale: {s['rationale']}")
            print(f"        rollback:  {s['rollback']}")
    print(f"  Risk summary: {plan['risk_summary']}")
    if plan["degraded_mode"]:
        print("  (degraded mode: LLM unavailable, rule-based fallback used)")
    print()


def _hitl_prompt(plan: dict, auto_approve: bool) -> dict:
    print("=" * 70)
    print("HUMAN-IN-THE-LOOP CHECKPOINT")
    print("=" * 70)
    print("Nothing has been executed yet. Review the plan above.")
    if auto_approve:
        print("(--auto-approve set) Approving the recommended goal.\n")
        return {"decision": "approve", "reviewer": "cli-auto", "notes": "auto-approved for scripted demo"}

    while True:
        choice = input("Approve / Reject / Modify goal? [a/r/m]: ").strip().lower()
        if choice in ("a", "approve"):
            notes = input("Notes (optional): ").strip()
            return {"decision": "approve", "reviewer": input("Your name: ").strip() or "reviewer", "notes": notes}
        if choice in ("r", "reject"):
            notes = input("Why are you rejecting this plan?: ").strip()
            return {"decision": "reject", "reviewer": input("Your name: ").strip() or "reviewer", "notes": notes}
        if choice in ("m", "modify"):
            goals = [g["goal"] for g in plan["goals"]]
            print(f"Available goals: {goals}")
            goal = input("Which goal should run instead?: ").strip()
            notes = input("Why are you changing the plan?: ").strip()
            return {
                "decision": "modify",
                "reviewer": input("Your name: ").strip() or "reviewer",
                "notes": notes,
                "modified_goal": goal,
            }
        print("Please enter 'a', 'r', or 'm'.")


def _print_postmortem(pm: dict) -> None:
    print("=" * 70)
    print(f"POSTMORTEM AGENT -- {pm['title']}")
    print("=" * 70)
    for line in pm["timeline"]:
        print(f"  - {line}")
    print(f"\n  Root cause: {pm['root_cause']}")
    print(f"  Impact: {pm['impact']}")
    print(f"  Human decision(s): {pm['human_decisions']}")
    print(f"  Lessons learned: {pm['lessons_learned']}")
    print(f"  Action items: {pm['action_items']}")
    if pm["degraded_mode"]:
        print("  (degraded mode: LLM unavailable, rule-based fallback used)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=None, choices=list(SCENARIOS) + [None])
    parser.add_argument("--no-spawn", action="store_true", help="assume agents/coordinator are already running")
    parser.add_argument("--auto-approve", action="store_true", help="skip the interactive HITL prompt (for scripted demos)")
    args = parser.parse_args()

    if not args.no_spawn:
        print("Starting monitoring/diagnostic/remediation/postmortem agents + coordinator API...")
        _spawn_all()
        _wait_healthy()

    scenario_id = _choose_scenario(args.scenario)

    with httpx.Client(timeout=120.0) as client:
        target = settings.n8n_alert_webhook_url or f"{COORDINATOR_BASE}/incidents"
        print(f"Filing alert for scenario '{scenario_id}' -> {target}\n")
        resp = client.post(target, json={"scenario_id": scenario_id})
        resp.raise_for_status()
        state = resp.json()

        # If routed through n8n, the webhook may ack immediately; poll for the
        # coordinator to actually reach the approval gate.
        incident_id = state.get("incident_id")
        if incident_id and state.get("status") not in ("awaiting_approval", "failed"):
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                r = client.get(f"{COORDINATOR_BASE}/incidents/{incident_id}")
                if r.status_code == 200:
                    state = r.json()
                    if state["status"] in ("awaiting_approval", "failed"):
                        break
                time.sleep(1)

        if state["status"] == "failed":
            print("Incident pipeline FAILED before reaching approval:")
            print(state["coordinator_notes"])
            return

        incident_id = state["incident_id"]
        print(f"Incident ID: {incident_id}\n")
        _print_triage(state["triage"])
        _print_diagnosis(state["diagnosis"])
        _print_plan(state["plan"])

        decision = _hitl_prompt(state["plan"], args.auto_approve)
        resp = client.post(f"{COORDINATOR_BASE}/incidents/{incident_id}/decision", json=decision)
        resp.raise_for_status()
        final_state = resp.json()

        print("\n" + "=" * 70)
        print(f"EXECUTION RESULT (status={final_state['status']})")
        print("=" * 70)
        for step in final_state["execution_log"]:
            print(f"  [{step['status']}] {step['action']} -- {step['detail']}")
        if not final_state["execution_log"]:
            print("  (no steps executed)")
        if final_state["coordinator_notes"]:
            print("  Coordinator resilience notes:")
            for n in final_state["coordinator_notes"]:
                print(f"    ! {n}")
        print()

        _print_postmortem(final_state["postmortem"])

        print(f"Full incident record saved to runs/{incident_id}.json")


if __name__ == "__main__":
    main()
