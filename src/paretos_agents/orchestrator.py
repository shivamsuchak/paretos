"""LangGraph orchestrator for the multi-agent staffing pipeline.

Execution flow:
  1. [forecast_agent] + [knowledge_agent]  (parallel)
  2. [regime_agent]
  3. [planning_agent]
  4. [cost_agent]
  5. [red_team_agent]
  6. [human_review_gate]
  7. [debrief_agent]  (if approved)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from langgraph.graph import END, StateGraph

from paretos_agents.nodes import (
    cost_agent,
    debrief_agent,
    forecast_agent,
    human_review_gate,
    knowledge_agent,
    planning_agent,
    red_team_agent,
    regime_agent,
)
from paretos_agents.state import PipelineState


def _human_review_router(state: PipelineState) -> str:
    """Route after human review: approved → debrief, rejected → planning."""
    if state.get("human_approved", False):
        return "debrief"
    return "planning"


def build_graph(visualize: bool = False):
    """Build the LangGraph workflow for one weekly cycle.

    Args:
        visualize: If True, wrap with LangGraphics for live browser visualization.

    Returns a compiled StateGraph ready to invoke.
    """
    g = StateGraph(PipelineState)

    # ── Add nodes ──
    g.add_node("forecast", forecast_agent)
    g.add_node("knowledge", knowledge_agent)
    g.add_node("regime", regime_agent)
    g.add_node("planning", planning_agent)
    g.add_node("cost_opt", cost_agent)
    g.add_node("red_team", red_team_agent)
    g.add_node("human_review", human_review_gate)
    g.add_node("debrief", debrief_agent)

    # ── Entry: forecast and knowledge run first ──
    g.set_entry_point("forecast")

    # Forecast → Knowledge (sequential since LangGraph basic doesn't support
    # true parallel without fan-out; knowledge doesn't depend on forecast anyway)
    g.add_edge("forecast", "knowledge")

    # Knowledge → Regime → Planning → Cost → Red Team → Human Review
    g.add_edge("knowledge", "regime")
    g.add_edge("regime", "planning")
    g.add_edge("planning", "cost_opt")
    g.add_edge("cost_opt", "red_team")
    g.add_edge("red_team", "human_review")

    # Conditional: Human Review → Debrief (approved) or → Planning (loop)
    g.add_conditional_edges(
        "human_review",
        _human_review_router,
        {"debrief": "debrief", "planning": "planning"},
    )

    g.add_edge("debrief", END)

    compiled = g.compile()

    # Note: We now use our own real-time thinking dashboard (trace_server.py)
    # instead of LangGraphics, to avoid port conflicts and show richer thinking data.

    return compiled


def run_weekly_cycle(
    cycle_date: date,
    planned_week_start: date,
    raw_recommendations: list[dict],
    historical_recs: list[dict],
    historical_actuals: list[dict],
    decision_log_entries: list[dict],
    previous_actuals: list[dict] | None = None,
    volumes: list[dict] | None = None,
    visualize: bool = False,
) -> PipelineState:
    """Execute the full multi-agent pipeline for one weekly cycle.

    Args:
        cycle_date: The decision date (typically a Tuesday).
        planned_week_start: The Monday of the planned week.
        raw_recommendations: This week's recommendation dicts.
        historical_recs: All prior recommendations for calibration.
        historical_actuals: All prior actuals for calibration.
        decision_log_entries: Planner notes.
        previous_actuals: Last week's actuals (for cost evaluation).
        volumes: Volume data (for forecast agent).

    Returns:
        Final PipelineState with all agent outputs.
    """
    graph = build_graph(visualize=visualize)

    initial_state: PipelineState = {
        "cycle_date": str(cycle_date),
        "planned_week_start": str(planned_week_start),
        "raw_recommendations": raw_recommendations,
        "historical_recs": historical_recs,
        "historical_actuals": historical_actuals,
        "decision_log_entries": decision_log_entries,
        "previous_actuals": previous_actuals,
        "volumes": volumes,
        "forecast_context": {},
        "knowledge_updates": [],
        "regime_flags": {},
        "adjusted_plan": [],
        "optimised_plan": [],
        "risk_assessment": {},
        "debrief_report": "",
        "marketplace_summary": {},
        "human_approved": False,
        "overrides": [],
        "thinking": [],
        "audit_log": [],
        "errors": [],
        "fallback_used": False,
    }

    return graph.invoke(initial_state)
