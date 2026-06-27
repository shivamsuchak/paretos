"""LangGraph state schema for the multi-agent pipeline."""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    """Shared state flowing through all agent nodes.

    Each agent reads what it needs and writes its output key.
    LangGraph manages merging.
    """

    # ── Inputs (set by orchestrator before graph execution) ──
    cycle_date: date                          # Decision Tuesday
    planned_week_start: date                  # Following Monday
    raw_recommendations: list[dict]           # DailyRecommendationTotal as dicts
    previous_actuals: list[dict] | None       # Previous week actuals (if available)
    volumes: list[dict] | None                # Volume data (if available)
    historical_recs: list[dict]               # All prior recommendations for calibration
    historical_actuals: list[dict]            # All prior actuals for calibration
    decision_log_entries: list[dict]          # Planner notes from decision_log.json

    # ── Agent outputs (accumulated through graph) ──
    forecast_context: dict                    # Forecast Agent output
    knowledge_updates: list[dict]             # Knowledge Agent output
    regime_flags: dict                        # Regime Agent output
    adjusted_plan: list[dict]                 # Planning Agent output (StaffingPlans)
    optimised_plan: list[dict]                # Cost Agent output
    risk_assessment: dict                     # Red Team Agent output
    debrief_report: str                       # Debrief Agent output
    marketplace_summary: dict                  # Marketplace atom generation summary

    # ── Governance ──
    human_approved: bool                      # Planner review gate
    overrides: list[dict]                     # Planner manual overrides
    audit_log: list[dict]                     # Full decision trace

    # ── Tracing & thinking ──
    thinking: list[dict]                      # Agent reasoning traces
    # Each entry: {"agent": str, "step": str, "detail": str, "timestamp": str}

    # ── Error handling ──
    errors: list[str]                         # Agent-level errors
    fallback_used: bool                       # Whether fallback was triggered
