"""Real-time WebSocket trace server for agent thinking visualization.

Broadcasts agent thinking traces to connected browser clients.
Each trace is a JSON message: {agent, step, detail, timestamp, type}
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import webbrowser
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any

import websockets
import websockets.server

# ── Global state ──
_ws_clients: set = set()
_event_loop: asyncio.AbstractEventLoop | None = None
_server_thread: threading.Thread | None = None
_http_thread: threading.Thread | None = None
_human_decision: threading.Event = threading.Event()
_human_response: dict = {}
_week_selection: threading.Event = threading.Event()
_week_response: dict = {}

WS_PORT = 8767
HTTP_PORT = 8768


async def _ws_handler(websocket):
    """Handle a new WebSocket connection."""
    _ws_clients.add(websocket)
    try:
        # Send current graph structure on connect
        await websocket.send(json.dumps({
            "type": "graph_structure",
            "nodes": [
                {"id": "forecast", "label": "📊 Forecast", "color": "#22d3ee"},
                {"id": "knowledge", "label": "📚 Knowledge", "color": "#fbbf24"},
                {"id": "regime", "label": "🔍 Regime", "color": "#c084fc"},
                {"id": "planning", "label": "📋 Planning", "color": "#4ade80"},
                {"id": "cost_opt", "label": "💰 Cost", "color": "#60a5fa"},
                {"id": "human_review", "label": "👤 Review", "color": "#e2e8f0"},
                {"id": "debrief", "label": "📝 Debrief", "color": "#f87171"},
            ],
            "edges": [
                {"from": "forecast", "to": "knowledge"},
                {"from": "knowledge", "to": "regime"},
                {"from": "regime", "to": "planning"},
                {"from": "planning", "to": "cost_opt"},
                {"from": "cost_opt", "to": "human_review"},
                {"from": "human_review", "to": "debrief"},
            ],
        }))
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                if msg.get("type") == "human_decision":
                    global _human_response
                    _human_response = msg
                    _human_decision.set()
                elif msg.get("type") == "week_selected":
                    global _week_response
                    _week_response = msg
                    _week_selection.set()
            except json.JSONDecodeError:
                pass
    finally:
        _ws_clients.discard(websocket)


def broadcast_trace(agent: str, step: str, detail: str, trace_type: str = "thinking"):
    """Send a thinking trace to all connected browser clients.

    Called synchronously from agent nodes — safe to call from any thread.
    """
    if not _event_loop or not _ws_clients:
        return

    msg = json.dumps({
        "type": trace_type,
        "agent": agent,
        "step": step,
        "detail": detail,
        "timestamp": time.strftime("%H:%M:%S"),
    })

    async def _send():
        dead = set()
        for ws in _ws_clients.copy():
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)

    asyncio.run_coroutine_threadsafe(_send(), _event_loop)


def broadcast_node_active(node_name: str):
    """Signal that a node has started executing."""
    broadcast_trace(node_name, "__active__", "", trace_type="node_active")


def broadcast_node_done(node_name: str):
    """Signal that a node has finished executing."""
    broadcast_trace(node_name, "__done__", "", trace_type="node_done")


def broadcast_review_request(plan: list, risk_assessment: dict, cost_summary: dict):
    """Send plan + risks to dashboard for human approval.

    The dashboard shows the plan, risk scenarios, and approve/reject buttons.
    """
    if not _event_loop or not _ws_clients:
        return

    payload = {
        "type": "review_request",
        "plan": [
            {"date": str(p.get("date", "")),
             "pd": round(p.get("planned_operative_person_days", 0), 1)}
            for p in plan
        ],
        "risk_assessment": risk_assessment,
        "cost_summary": cost_summary,
    }
    msg = json.dumps(payload)

    async def _send():
        dead = set()
        for ws in _ws_clients.copy():
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)

    asyncio.run_coroutine_threadsafe(_send(), _event_loop)


def wait_for_human_decision(timeout: float = 300.0) -> dict:
    """Block until the planner responds via the dashboard.

    Returns dict with keys: approved (bool), reason (str).
    Times out after 5 minutes and auto-approves.
    """
    global _human_response
    _human_decision.clear()
    _human_response = {}

    got_response = _human_decision.wait(timeout=timeout)

    if not got_response:
        return {"approved": True, "reason": "Timeout — auto-approved after 5 minutes"}

    return {
        "approved": _human_response.get("approved", True),
        "reason": _human_response.get("reason", ""),
    }


def broadcast_available_weeks(weeks: list[dict]):
    """Send available weeks to the dashboard for user selection.

    Each week dict should have: {index, week_start, has_actuals, label}
    """
    if not _event_loop or not _ws_clients:
        return

    payload = {"type": "available_weeks", "weeks": weeks}
    msg = json.dumps(payload)

    async def _send():
        dead = set()
        for ws in _ws_clients.copy():
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)

    asyncio.run_coroutine_threadsafe(_send(), _event_loop)


def wait_for_week_selection(timeout: float = 600.0) -> int | None:
    """Block until the user selects a week in the dashboard.

    Returns the selected week index, or None on timeout.
    """
    global _week_response
    _week_selection.clear()
    _week_response = {}

    got = _week_selection.wait(timeout=timeout)
    if not got:
        return None
    return _week_response.get("week_index")


def broadcast_pipeline_done():
    """Signal that the full pipeline is complete."""
    broadcast_trace("pipeline", "__complete__", "", trace_type="pipeline_done")


def broadcast_results(result: dict):
    """Send the final pipeline results to the dashboard for display."""
    if not _event_loop or not _ws_clients:
        return

    # Extract relevant result data for the dashboard
    fc = result.get("forecast_context", {})
    plan = result.get("optimised_plan") or result.get("adjusted_plan", [])
    regime = result.get("regime_flags", {})
    knowledge = result.get("knowledge_updates", [])
    debrief = result.get("debrief_report", "")
    errors = result.get("errors", [])
    audit = result.get("audit_log", [])

    # Extract cost agent evaluation from audit log
    cost_audit = next((a for a in audit if a.get("agent") == "cost"), {})
    cost_eval = cost_audit.get("evaluation") or {}
    newsvendor = cost_audit.get("newsvendor") or {}
    monte_carlo = cost_audit.get("monte_carlo") or {}

    # Count stale knowledge notes
    stale_count = sum(
        1 for k in (knowledge if isinstance(knowledge, list) else [])
        if isinstance(k, dict) and k.get("status") == "stale"
    )

    payload = {
        "type": "pipeline_results",
        "forecast": {
            "status": fc.get("status", "unknown"),
            "mape_pct": fc.get("mape_pct"),
            "model": fc.get("model", "unknown"),
        },
        "plan": [
            {"date": str(p.get("date", "")), "pd": round(p.get("planned_operative_person_days", 0), 1)}
            for p in plan
        ],
        "regime": {
            "detected": regime.get("detected", False),
            "label": regime.get("label", "stable"),
            "details": regime.get("details", ""),
            "method": regime.get("detection_method", ""),
            "confidence": regime.get("confidence", ""),
            "cusum_date": regime.get("cusum_date", ""),
        },
        "knowledge_count": len(knowledge),
        "knowledge_stale": stale_count,
        "knowledge": [
            {
                "id": k.get("id", "?"),
                "status": k.get("status", "?"),
                "confidence": k.get("confidence", "?"),
                "days_since": k.get("days_since_capture", ""),
            }
            for k in (knowledge[:8] if isinstance(knowledge, list) else [])
            if isinstance(k, dict)
        ],
        "approved": result.get("human_approved", False),
        "debrief": debrief[:2000] if isinstance(debrief, str) else "",
        "error_count": len(errors),
        "cost": {
            "plan_cost": cost_eval.get("evaluated_cost", 0),
            "baseline_cost": cost_eval.get("baseline_cost", 0),
            "gap_closure_pct": cost_eval.get("gap_closure_pct", 0),
            "savings": cost_eval.get("savings_vs_baseline", 0),
            "days_overstaffed": cost_eval.get("days_overstaffed", 0),
            "days_understaffed": cost_eval.get("days_understaffed", 0),
        },
        "newsvendor": {
            "critical_ratio": newsvendor.get("critical_ratio", 0),
            "optimal_offset": newsvendor.get("optimal_offset", 0),
        },
        "monte_carlo": {
            "historical_errors": monte_carlo.get("mc_historical_errors", 0),
            "simulated_offsets": monte_carlo.get("mc_simulated_offsets", 0),
            "best_cost": monte_carlo.get("mc_best_cost", 0),
            "quantile_pd": monte_carlo.get("newsvendor_quantile_pd", 0),
        },
        "risk_assessment": result.get("risk_assessment", {}),
        "marketplace": result.get("marketplace_summary", {}),
    }

    msg = json.dumps(payload)

    async def _send():
        dead = set()
        for ws in _ws_clients.copy():
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)

    asyncio.run_coroutine_threadsafe(_send(), _event_loop)


class _DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the dashboard HTML from the static directory."""

    def __init__(self, *args, **kwargs):
        self.directory = str(Path(__file__).parent / "dashboard")
        super().__init__(*args, directory=self.directory, **kwargs)

    def log_message(self, format, *args):
        pass  # Silence HTTP logs


def start_trace_server(open_browser: bool = True):
    """Start the WebSocket + HTTP servers in background threads."""
    global _event_loop, _server_thread, _http_thread

    if _server_thread and _server_thread.is_alive():
        return  # Already running

    def _run_ws():
        global _event_loop
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)

        async def _serve():
            async with websockets.serve(_ws_handler, "localhost", WS_PORT):
                await asyncio.Future()  # Run forever

        _event_loop.run_until_complete(_serve())

    _server_thread = threading.Thread(target=_run_ws, daemon=True)
    _server_thread.start()

    # Serve dashboard HTML
    dashboard_dir = Path(__file__).parent / "dashboard"
    dashboard_dir.mkdir(exist_ok=True)

    def _run_http():
        server = HTTPServer(("localhost", HTTP_PORT), _DashboardHandler)
        server.serve_forever()

    _http_thread = threading.Thread(target=_run_http, daemon=True)
    _http_thread.start()

    time.sleep(0.3)  # Let servers start

    if open_browser:
        webbrowser.open(f"http://localhost:{HTTP_PORT}")

    print(f"  🌐 Trace dashboard: http://localhost:{HTTP_PORT}")
    print(f"  🔌 WebSocket:       ws://localhost:{WS_PORT}")
