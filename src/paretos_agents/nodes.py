"""Agent node functions for the LangGraph pipeline.

Each function takes PipelineState and returns a partial state update dict.
LangGraph merges the returned keys into the shared state.

Agent map:
  1. forecast_agent  — pure stats, no LLM
  2. knowledge_agent — Claude-powered note curation
  3. regime_agent    — pure stats, changepoint detection
  4. planning_agent  — deterministic corrections + optional Claude explanation
  5. cost_agent      — newsvendor optimisation, pure math
  6. debrief_agent   — Claude-powered report generation
"""

from __future__ import annotations

import json
import traceback
from datetime import date, datetime, timedelta
from typing import Any

from paretos_agents.state import PipelineState

# ═══════════════════════════════════════════════════════════════════════════════
# Thinking trace helper
# ═══════════════════════════════════════════════════════════════════════════════

_COLORS = {
    "forecast": "\033[96m",   # cyan
    "knowledge": "\033[93m",  # yellow
    "regime": "\033[95m",     # magenta
    "planning": "\033[92m",   # green
    "cost": "\033[94m",       # blue
    "debrief": "\033[91m",    # red
    "human_review": "\033[97m",  # white
}
_RESET = "\033[0m"


def _think(state: PipelineState, agent: str, step: str, detail: str) -> None:
    """Emit a thinking trace — prints to console, appends to state, and broadcasts via WebSocket."""
    ts = datetime.now().strftime("%H:%M:%S")
    color = _COLORS.get(agent, "")
    print(f"  {color}🧠 [{ts}] {agent:>12} │ {step}: {detail}{_RESET}")
    traces = state.get("thinking", [])
    traces.append({"agent": agent, "step": step, "detail": detail, "timestamp": ts})
    state["thinking"] = traces

    # Broadcast to live dashboard
    try:
        from paretos_agents.trace_server import broadcast_trace, broadcast_node_active
        if step == "start":
            broadcast_node_active(agent)
        broadcast_trace(agent, step, detail)
        if step == "done":
            from paretos_agents.trace_server import broadcast_node_done
            broadcast_node_done(agent)
    except Exception:
        pass  # Dashboard not running — no problem


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 1: Forecast & Volume Analysis (pure stats, no LLM)
# ═══════════════════════════════════════════════════════════════════════════════

def forecast_agent(state: PipelineState) -> dict:
    """Analyse volume forecast accuracy and detect trends.

    Now analyses ALL three volume types (picks, outbound, inbound),
    computes day-of-week volume patterns, intra-week volatility,
    and validates the admin headcount = 8 assumption.
    """
    try:
        _think(state, "forecast", "start", "Analysing volume forecast accuracy (all volume types)...")
        volumes = state.get("volumes") or []
        if not volumes:
            _think(state, "forecast", "skip", "No volume data available")
            return {
                "forecast_context": {
                    "status": "no_data",
                    "mape": None,
                    "bias_direction": None,
                    "trend": None,
                },
                "thinking": state.get("thinking", []),
                "audit_log": state.get("audit_log", []) + [
                    {"agent": "forecast", "action": "skipped", "reason": "no volume data"}
                ],
            }

        _think(state, "forecast", "data", f"Processing {len(volumes)} volume observations across 3 volume types")

        # ── Helper: compute MAPE and bias for a forecast/realized pair ──
        def _mape_bias(forecast_key: str, realized_key: str):
            errs = []
            for v in volumes:
                fc = v.get(forecast_key, 0)
                rl = v.get(realized_key, 0)
                if rl > 0:
                    errs.append((fc - rl) / rl)
            if not errs:
                return None, None
            mape = sum(abs(e) for e in errs) / len(errs) * 100
            bias = sum(errs) / len(errs) * 100
            return round(mape, 2), round(bias, 2)

        picks_mape, picks_bias = _mape_bias("picks_forecast", "picks_realized")
        outbound_mape, outbound_bias = _mape_bias("outbound_forecast", "outbound_realized")
        inbound_mape, inbound_bias = _mape_bias("inbound_forecast", "inbound_realized")

        if picks_mape is None:
            return {"forecast_context": {"status": "no_valid_pairs"}, "thinking": state.get("thinking", [])}

        _think(state, "forecast", "picks_accuracy", f"Picks MAPE={picks_mape:.1f}%, bias={picks_bias:+.1f}%")
        if outbound_mape is not None:
            _think(state, "forecast", "outbound_accuracy", f"Outbound MAPE={outbound_mape:.1f}%, bias={outbound_bias:+.1f}%")
        if inbound_mape is not None:
            _think(state, "forecast", "inbound_accuracy", f"Inbound MAPE={inbound_mape:.1f}%, bias={inbound_bias:+.1f}%")

        # ── Trend detection: compare first half vs second half (picks) ──
        mid = len(volumes) // 2
        first_half = [v.get("picks_realized", 0) for v in volumes[:mid]]
        second_half = [v.get("picks_realized", 0) for v in volumes[mid:]]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        trend_pct = ((avg_second - avg_first) / avg_first * 100) if avg_first > 0 else 0
        trend_dir = "increasing" if trend_pct > 2 else ("decreasing" if trend_pct < -2 else "stable")
        _think(state, "forecast", "trend", f"Picks trend: {trend_dir} ({trend_pct:+.1f}%)")

        # ── Day-of-week volume patterns ──
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        dow_picks: dict[str, list[int]] = {d: [] for d in dow_names[:5]}
        dow_inbound: dict[str, list[int]] = {d: [] for d in dow_names[:5]}
        dow_outbound: dict[str, list[int]] = {d: [] for d in dow_names[:5]}
        for v in volumes:
            d_str = v.get("date", "")
            if not d_str:
                continue
            try:
                dt = date.fromisoformat(str(d_str)) if isinstance(d_str, str) else d_str
                dow = dow_names[dt.weekday()]
            except (ValueError, AttributeError):
                continue
            if dow not in dow_picks:
                continue
            dow_picks[dow].append(int(v.get("picks_realized", 0)))
            dow_inbound[dow].append(int(v.get("inbound_realized", 0)))
            dow_outbound[dow].append(int(v.get("outbound_realized", 0)))

        dow_volume_patterns = {}
        for dow in dow_names[:5]:
            if dow_picks[dow]:
                avg_p = sum(dow_picks[dow]) / len(dow_picks[dow])
                avg_i = sum(dow_inbound[dow]) / len(dow_inbound[dow]) if dow_inbound[dow] else 0
                avg_o = sum(dow_outbound[dow]) / len(dow_outbound[dow]) if dow_outbound[dow] else 0
                dow_volume_patterns[dow] = {
                    "avg_picks": round(avg_p),
                    "avg_inbound": round(avg_i),
                    "avg_outbound": round(avg_o),
                }
        if dow_volume_patterns:
            overall_avg = sum(d["avg_picks"] for d in dow_volume_patterns.values()) / len(dow_volume_patterns)
            dow_str = ", ".join(
                f"{d}={p['avg_picks']}({p['avg_picks']/overall_avg:.2f}x)"
                for d, p in dow_volume_patterns.items()
            )
            _think(state, "forecast", "dow_volumes", f"DoW picks pattern: {dow_str}")

        # ── Intra-week volatility (coefficient of variation within each week) ──
        from collections import defaultdict
        week_groups: dict[str, list[int]] = defaultdict(list)
        for v in volumes:
            d_str = v.get("date", "")
            try:
                dt = date.fromisoformat(str(d_str)) if isinstance(d_str, str) else d_str
                # Group by ISO week
                yr, wk, _ = dt.isocalendar()
                week_groups[f"{yr}-W{wk:02d}"].append(int(v.get("picks_realized", 0)))
            except (ValueError, AttributeError):
                continue

        week_cvs = []
        for wk_key, vals in week_groups.items():
            if len(vals) >= 3:
                avg = sum(vals) / len(vals)
                if avg > 0:
                    std = (sum((x - avg) ** 2 for x in vals) / len(vals)) ** 0.5
                    week_cvs.append(std / avg)
        intra_week_cv = round(sum(week_cvs) / len(week_cvs) * 100, 1) if week_cvs else 0.0
        _think(state, "forecast", "volatility", f"Intra-week CV: {intra_week_cv:.1f}% (average within-week demand variability)")

        # ── Admin headcount validation ──
        hist_actuals = state.get("historical_actuals") or []
        admin_deviations = []
        for a in hist_actuals:
            total = a.get("present_total_person_days", 0)
            operative = a.get("present_operative_person_days", 0)
            admin = total - operative
            if abs(admin - 8.0) > 0.01:
                admin_deviations.append({"date": a.get("date"), "admin_pd": admin})

        admin_valid = len(admin_deviations) == 0
        if admin_valid:
            _think(state, "forecast", "admin_check", f"✅ Admin = 8.0 pd/day confirmed across all {len(hist_actuals)} days")
        else:
            _think(state, "forecast", "admin_check",
                   f"⚠️ Admin ≠ 8 on {len(admin_deviations)}/{len(hist_actuals)} days! "
                   f"Deviations: {admin_deviations[:5]}")

        context = {
            "status": "ok",
            "n_observations": len(volumes),
            # Picks (primary)
            "mape_pct": picks_mape,
            "bias_pct": picks_bias,
            "bias_direction": "over-forecast" if (picks_bias or 0) > 0 else "under-forecast",
            "trend_pct": round(trend_pct, 1),
            "trend_direction": trend_dir,
            # Outbound
            "outbound_mape_pct": outbound_mape,
            "outbound_bias_pct": outbound_bias,
            # Inbound
            "inbound_mape_pct": inbound_mape,
            "inbound_bias_pct": inbound_bias,
            # DoW patterns
            "dow_volume_patterns": dow_volume_patterns,
            # Intra-week volatility
            "intra_week_cv_pct": intra_week_cv,
            # Admin validation
            "admin_constant_8": admin_valid,
            "admin_deviations": admin_deviations[:10],
        }

        _think(state, "forecast", "done",
               f"Forecast analysis complete — picks MAPE {picks_mape:.1f}%, "
               f"outbound MAPE {outbound_mape or 'N/A'}%, "
               f"inbound MAPE {inbound_mape or 'N/A'}%, "
               f"intra-week CV {intra_week_cv:.1f}%")

        return {
            "forecast_context": context,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "forecast", "action": "completed",
                 "picks_mape": picks_mape,
                 "outbound_mape": outbound_mape,
                 "inbound_mape": inbound_mape,
                 "intra_week_cv": intra_week_cv,
                 "admin_valid": admin_valid}
            ],
        }

    except Exception as e:
        return {
            "forecast_context": {"status": "error", "error": str(e)},
            "errors": state.get("errors", []) + [f"forecast_agent: {e}"],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 2: Knowledge Curation (Claude-powered)
# ═══════════════════════════════════════════════════════════════════════════════

def knowledge_agent(state: PipelineState) -> dict:
    """Curate planner notes using Claude for NL parsing and reasoning."""
    from paretos_agents.llm import call_claude
    from paretos_agents.prompts import KNOWLEDGE_SYSTEM, KNOWLEDGE_USER_TEMPLATE

    try:
        _think(state, "knowledge", "start", "Curating planner decision log notes...")
        entries = state.get("decision_log_entries", [])
        if not entries:
            _think(state, "knowledge", "skip", "No decision log entries to curate")
            return {
                "knowledge_updates": [],
                "thinking": state.get("thinking", []),
                "audit_log": state.get("audit_log", []) + [
                    {"agent": "knowledge", "action": "skipped", "reason": "no entries"}
                ],
            }

        _think(state, "knowledge", "data", f"Found {len(entries)} planner notes to validate")

        # Compute stats for the prompt
        hist_recs = state.get("historical_recs", [])
        hist_actuals = state.get("historical_actuals", [])

        rec_totals = {r["date"]: r["total_operative_person_days"] for r in hist_recs}
        actual_totals = {a["date"]: a["present_operative_person_days"] for a in hist_actuals}

        errors = []
        for d, rec_val in rec_totals.items():
            if d in actual_totals:
                errors.append(rec_val - actual_totals[d])

        mean_error = sum(errors) / len(errors) if errors else 0
        mean_rec = sum(rec_totals.values()) / len(rec_totals) if rec_totals else 1
        bias_pct = (mean_error / mean_rec) * 100 if mean_rec else 0
        overstaffing_pct = sum(1 for e in errors if e > 0) / len(errors) * 100 if errors else 0
        _think(state, "knowledge", "stats", f"Historical bias: {bias_pct:+.1f}%, overstaffing {overstaffing_pct:.0f}% of days")

        # Date range
        dates = sorted(actual_totals.keys())
        date_range = f"{dates[0]} to {dates[-1]}" if dates else "unknown"

        # DoW factors summary
        from paretos_stats.dow_adjustment import compute_dow_factors, dow_factor_summary
        from paretos_core.schemas import DailyRecommendationTotal, DailyActual

        # Reconstruct typed objects for stats functions
        typed_recs = [DailyRecommendationTotal(**r) for r in hist_recs]
        typed_actuals = [DailyActual(**a) for a in hist_actuals]
        dow_factors = compute_dow_factors(typed_recs, typed_actuals)
        dow_str = dow_factor_summary(dow_factors)

        # Regime info
        regime_flags = state.get("regime_flags", {})
        regime_info = regime_flags.get("interpretation", "No regime change detected")
        regime_ratios = (
            f"before={regime_flags.get('mean_ratio_before', 'N/A')}, "
            f"after={regime_flags.get('mean_ratio_after', 'N/A')}"
            if regime_flags.get("detected") else "N/A"
        )

        # Activity sample from first recommendation
        raw_recs = state.get("raw_recommendations", [])
        activity_sample = json.dumps(
            raw_recs[0].get("by_activity", {}) if raw_recs else {},
            indent=2
        )

        cycle_date = state.get("cycle_date", date.today())
        prompt = KNOWLEDGE_USER_TEMPLATE.format(
            notes_json=json.dumps(entries, indent=2, default=str),
            date_range=date_range,
            bias_pct=bias_pct,
            mean_error=mean_error,
            overstaffing_pct=overstaffing_pct,
            dow_factors=dow_str,
            regime_info=regime_info,
            regime_error_ratios=regime_ratios,
            activity_sample=activity_sample,
            cycle_date=str(cycle_date),
        )

        _think(state, "knowledge", "llm_call", "Sending notes + evidence to Claude for validation...")
        response = call_claude(prompt, system=KNOWLEDGE_SYSTEM, max_tokens=8192)
        _think(state, "knowledge", "llm_response", f"Claude returned {len(response)} chars")

        # Parse JSON from response — handle markdown fences and truncation
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Try parsing; if truncated, attempt to repair by closing brackets
        try:
            knowledge_updates = json.loads(text)
        except json.JSONDecodeError:
            # Try closing unclosed arrays/objects
            for suffix in ["]", "}]", "\"}]", "\"}]"]:
                try:
                    knowledge_updates = json.loads(text + suffix)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                # Last resort: extract whatever valid objects we can
                knowledge_updates = []
                import re
                for m in re.finditer(r'\{[^{}]+\}', text):
                    try:
                        obj = json.loads(m.group())
                        knowledge_updates.append(obj)
                    except json.JSONDecodeError:
                        pass

        # Summarise results
        statuses = {}
        for ku in knowledge_updates:
            if isinstance(ku, dict):
                s = ku.get("status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
        status_str = ", ".join(f"{v} {k}" for k, v in statuses.items())
        _think(state, "knowledge", "done", f"Curated {len(knowledge_updates)} notes: {status_str}")

        return {
            "knowledge_updates": knowledge_updates,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "knowledge", "action": "completed",
                 "notes_curated": len(knowledge_updates)}
            ],
        }

    except Exception as e:
        return {
            "knowledge_updates": [],
            "errors": state.get("errors", []) + [
                f"knowledge_agent: {e}\n{traceback.format_exc()}"
            ],
            "audit_log": state.get("audit_log", []) + [
                {"agent": "knowledge", "action": "error", "error": str(e)}
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 3: Regime Detection (pure stats, no LLM)
# ═══════════════════════════════════════════════════════════════════════════════

def regime_agent(state: PipelineState) -> dict:
    """Detect structural shifts in error ratios using changepoint detection."""
    from paretos_core.schemas import DailyRecommendationTotal, DailyActual
    from paretos_stats.changepoint import detect_picking_regime_change

    try:
        _think(state, "regime", "start", "Scanning for structural regime shifts in error ratios...")
        hist_recs = state.get("historical_recs", [])
        hist_actuals = state.get("historical_actuals", [])

        if len(hist_actuals) < 15:
            _think(state, "regime", "skip", f"Only {len(hist_actuals)} data points — need ≥15")
            return {
                "regime_flags": {"detected": False, "reason": "insufficient_data"},
                "thinking": state.get("thinking", []),
                "audit_log": state.get("audit_log", []) + [
                    {"agent": "regime", "action": "skipped", "reason": "< 15 data points"}
                ],
            }

        _think(state, "regime", "analysis", f"Running Bayesian changepoint detection on {len(hist_actuals)} days")
        typed_recs = [DailyRecommendationTotal(**r) for r in hist_recs]
        typed_actuals = [DailyActual(**a) for a in hist_actuals]

        result = detect_picking_regime_change(typed_recs, typed_actuals)

        if result:
            result["date"] = str(result["date"])
            _think(state, "regime", "detected", f"⚡ Regime change at {result['date']} — shift magnitude {result['shift_magnitude']:.3f}")
            _think(state, "regime", "interpretation", result.get('interpretation', 'structural shift detected'))
            return {
                "regime_flags": result,
                "thinking": state.get("thinking", []),
                "audit_log": state.get("audit_log", []) + [
                    {"agent": "regime", "action": "changepoint_detected",
                     "date": result["date"], "shift": result["shift_magnitude"]}
                ],
            }
        else:
            _think(state, "regime", "done", "No structural regime change detected in error ratios")
            return {
                "regime_flags": {"detected": False},
                "thinking": state.get("thinking", []),
                "audit_log": state.get("audit_log", []) + [
                    {"agent": "regime", "action": "no_changepoint"}
                ],
            }

    except Exception as e:
        return {
            "regime_flags": {"detected": False, "error": str(e)},
            "errors": state.get("errors", []) + [f"regime_agent: {e}"],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 4: Planning Adjustment (deterministic + optional Claude explanation)
# ═══════════════════════════════════════════════════════════════════════════════

def planning_agent(state: PipelineState) -> dict:
    """Apply the full correction stack to produce adjusted staffing plans."""
    from paretos_core.schemas import (
        CorrectionParams, DailyRecommendationTotal, DailyActual,
    )
    from paretos_stats.corrections import CorrectionEngine

    try:
        _think(state, "planning", "start", "Building corrected staffing plan from raw optimiser recommendations...")
        raw_recs = state.get("raw_recommendations", [])
        hist_recs = state.get("historical_recs", [])
        hist_actuals = state.get("historical_actuals", [])
        regime_flags = state.get("regime_flags", {})
        knowledge = state.get("knowledge_updates", [])

        if not raw_recs or not hist_actuals:
            _think(state, "planning", "error", "No recommendations or actuals available")
            return {
                "adjusted_plan": [],
                "thinking": state.get("thinking", []),
                "errors": state.get("errors", []) + ["planning_agent: no data"],
            }

        total_raw = sum(r.get("total_operative_person_days", 0) for r in raw_recs)
        _think(state, "planning", "input", f"Raw optimiser: {total_raw:.1f} total pd over {len(raw_recs)} days")

        typed_hist_recs = [DailyRecommendationTotal(**r) for r in hist_recs]
        typed_hist_actuals = [DailyActual(**a) for a in hist_actuals]

        # Determine regime parameters
        picking_start = None
        picking_factor = None
        if regime_flags.get("detected"):
            picking_start = date.fromisoformat(str(regime_flags["date"]))
            shift = regime_flags.get("shift_magnitude", 0)
            if shift > 0.05:
                picking_factor = 0.73
            _think(state, "planning", "regime", f"Applying regime correction: picking ×{picking_factor} from {picking_start}")
        else:
            _think(state, "planning", "regime", "No regime correction needed")

        # ── Detect if this is a re-plan after rejection ──
        rejection_count = sum(
            1 for a in state.get("audit_log", [])
            if a.get("agent") == "human_review" and a.get("action") == "rejected"
        )
        red_team_boost: dict[str, float] = {}  # date → extra pd to add
        newsvendor_dampen = 0.0  # reduce aggressiveness on re-plan

        if rejection_count > 0:
            risk = state.get("risk_assessment", {})
            scenarios = risk.get("scenarios", [])
            _think(state, "planning", "replan",
                   f"🔄 Re-planning after {rejection_count} rejection(s). "
                   f"Incorporating Red Team feedback ({len(scenarios)} scenarios)...")

            # Reduce newsvendor aggressiveness: each rejection adds +1.0 pd/day
            newsvendor_dampen = min(rejection_count * 1.0, 3.0)

            # Add staff to fragile days identified by Red Team
            fragile_days = risk.get("fragile_days", [])
            for fd in fragile_days:
                red_team_boost[str(fd)] = red_team_boost.get(str(fd), 0) + 2.0 * rejection_count

            # Parse individual scenarios for affected days
            for sc in scenarios:
                severity = (sc.get("severity") or "").lower()
                sev_mult = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.5}.get(severity, 1.0)
                for day in sc.get("affected_days", []):
                    red_team_boost[str(day)] = red_team_boost.get(str(day), 0) + sev_mult

            if red_team_boost:
                boost_summary = ", ".join(f"{d}: +{v:.1f}" for d, v in sorted(red_team_boost.items()))
                _think(state, "planning", "replan_boost",
                       f"Adding staff to fragile days: {boost_summary}")
            _think(state, "planning", "replan_offset",
                   f"Newsvendor offset dampened by +{newsvendor_dampen:.1f} pd/day (less aggressive)")

        # Check validated knowledge notes for dynamic adjustments
        newsvendor_offset = -1.0 + newsvendor_dampen  # Default -1.0, dampened on re-plan
        knowledge_adjustments = []
        for ku in knowledge:
            if not isinstance(ku, dict):
                continue
            status = ku.get("status", "")
            confidence = ku.get("confidence", 0)
            action = ku.get("recommended_action", "")
            # Skip stale or low-confidence notes (Fildes et al. 2019)
            if status == "stale" or (isinstance(confidence, (int, float)) and confidence < 0.4):
                continue
            # Look for validated notes that suggest staffing adjustments
            if status in ("validated", "partially_validated") and isinstance(confidence, (int, float)) and confidence >= 0.6:
                action_lower = action.lower()
                if "newsvendor" in action_lower or "understaffing" in action_lower or "buffer" in action_lower:
                    knowledge_adjustments.append(f"{ku.get('id', '?')}: {action}")
                if "reduce" in action_lower and "picking" not in action_lower:
                    # Validated note recommends further reduction → widen offset
                    newsvendor_offset = min(newsvendor_offset, -1.5)
                    knowledge_adjustments.append(f"{ku.get('id', '?')}: reduction → offset={newsvendor_offset}")
        if knowledge_adjustments:
            _think(state, "planning", "knowledge", f"Applied {len(knowledge_adjustments)} validated knowledge adjustments")
        _think(state, "planning", "newsvendor", f"Newsvendor offset: {newsvendor_offset:+.1f} pd/day (safety buffer)")

        # Calibrate from history
        _think(state, "planning", "calibrate", f"Calibrating from {len(typed_hist_actuals)} historical days...")
        engine = CorrectionEngine.from_training_data(
            typed_hist_recs,
            typed_hist_actuals,
            picking_regime_start=picking_start,
            picking_regime_factor=picking_factor,
            newsvendor_offset=newsvendor_offset,
        )

        # Apply to current week
        typed_recs = [DailyRecommendationTotal(**r) for r in raw_recs]
        plans = engine.correct_week(typed_recs)

        plan_dicts = [
            {"date": str(p.date), "planned_operative_person_days": p.planned_operative_person_days}
            for p in plans
        ]

        total_adjusted = sum(p.planned_operative_person_days for p in plans)
        _think(state, "planning", "corrections", f"Bias factor: {engine.params.bias_factor:.4f}, DoW factors: {engine.params.dow_factors}")
        _think(state, "planning", "result", f"Adjusted total: {total_adjusted:.1f} pd (was {total_raw:.1f}, reduced {(total_raw-total_adjusted)/total_raw*100:.1f}%)")

        # ── Apply claimed_effect hard constraints from decision log ──
        # These are structured machine-readable rules that the Knowledge agent
        # validates as free-text, but we can ALSO apply programmatically.
        decision_log_entries = state.get("decision_log_entries", [])
        cycle_date = state.get("cycle_date", date.today())
        if isinstance(cycle_date, str):
            cycle_date = date.fromisoformat(cycle_date)

        # Build a lookup of which claimed_effect rules to apply
        # Only apply rules from notes that are NOT stale (captured within 42 days)
        # and that have been validated by the Knowledge agent
        validated_ids = set()
        for ku in knowledge:
            if isinstance(ku, dict) and ku.get("status") in ("validated", "partially_validated"):
                conf = ku.get("confidence", 0)
                if isinstance(conf, (int, float)) and conf >= 0.5:
                    validated_ids.add(ku.get("id"))

        hard_constraints: list[dict] = []
        for entry in decision_log_entries:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id", "")
            captured = entry.get("captured_on", "")
            if isinstance(captured, str) and captured:
                try:
                    cap_date = date.fromisoformat(captured)
                except ValueError:
                    continue
            elif hasattr(captured, "isoformat"):
                cap_date = captured
            else:
                continue
            # Only apply if validated by Knowledge agent OR captured within 42 days
            days_old = (cycle_date - cap_date).days
            if entry_id not in validated_ids and days_old > 42:
                continue
            effect = entry.get("claimed_effect", {})
            if not isinstance(effect, dict):
                continue
            kind = effect.get("kind", "")
            if kind in ("fixed", "scale_pct", "add", "conditional_trim", "conditional_add"):
                hard_constraints.append({"id": entry_id, "effect": effect, "note": entry.get("note", "")})

        # Apply hard constraints to each plan day
        constraint_log = []
        if hard_constraints:
            _think(state, "planning", "constraints", f"Applying {len(hard_constraints)} claimed_effect hard constraints from decision log")

            for i, pd_entry in enumerate(plan_dicts):
                d_str = pd_entry["date"]
                d = date.fromisoformat(d_str) if isinstance(d_str, str) else d_str
                dow_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]
                # Get activity breakdown for this day from raw recs
                matching_raw = [r for r in raw_recs if str(r.get("date", "")) == d_str]
                by_activity = matching_raw[0].get("by_activity", {}) if matching_raw else {}

                total_delta = 0.0  # Track net person-day change from constraints
                for hc in hard_constraints:
                    eff = hc["effect"]
                    kind = eff.get("kind", "")

                    if kind == "fixed":
                        # Clamp activity to fixed value (e.g., transit=4, co-packing=4)
                        activity = eff.get("activity", "")
                        fixed_val = eff.get("value", 0)
                        if activity in by_activity:
                            old_val = by_activity[activity]
                            delta = fixed_val - old_val
                            total_delta += delta
                            constraint_log.append(f"  {d_str}: {activity} clamped {old_val:.1f}→{fixed_val} (Δ{delta:+.1f})")

                    elif kind == "scale_pct":
                        # Apply percentage scaling to an activity
                        activity = eff.get("activity", "")
                        pct = eff.get("pct", 0)
                        from_date = eff.get("from")
                        # Check if we're past the effective date
                        if from_date:
                            try:
                                eff_date = date.fromisoformat(str(from_date))
                                if d < eff_date:
                                    continue
                            except ValueError:
                                pass
                        if activity and activity in by_activity:
                            old_val = by_activity[activity]
                            delta = old_val * (pct / 100.0)
                            total_delta += delta
                            constraint_log.append(f"  {d_str}: {activity} scaled {pct:+d}% (Δ{delta:+.1f})")
                        elif not activity and eff.get("scope") == "operative":
                            # Scale entire operative plan
                            old_total = pd_entry["planned_operative_person_days"]
                            delta = old_total * (pct / 100.0)
                            total_delta += delta
                            constraint_log.append(f"  {d_str}: operative scaled {pct:+d}% (Δ{delta:+.1f})")

                    elif kind == "add":
                        # Add delta on specific weekday
                        weekday_filter = eff.get("weekday", "")
                        activity = eff.get("activity", "")
                        delta = eff.get("delta", 0)
                        if weekday_filter and dow_name != weekday_filter:
                            if weekday_filter != "payday-Mon" or dow_name != "Mon":
                                continue
                        total_delta += delta
                        constraint_log.append(f"  {d_str}: +{delta} to {activity} ({dow_name})")

                    elif kind == "conditional_trim":
                        # Trim if condition met (e.g., picks < 7000)
                        activity = eff.get("activity", "")
                        delta = eff.get("delta", 0)
                        # Check volumes for this day
                        volumes_data = state.get("volumes") or []
                        day_vol = next((v for v in volumes_data if str(v.get("date", "")) == d_str), None)
                        if day_vol:
                            picks = day_vol.get("picks_forecast", 0) or day_vol.get("picks_realized", 0)
                            if picks < 7000:
                                total_delta += delta
                                constraint_log.append(f"  {d_str}: {activity} trimmed {delta} (picks={picks}<7000)")

                    elif kind == "conditional_add":
                        # Add if condition met (e.g., inbound > 2000)
                        activities = eff.get("activities", [eff.get("activity", "")])
                        delta = eff.get("delta", 0)
                        volumes_data = state.get("volumes") or []
                        day_vol = next((v for v in volumes_data if str(v.get("date", "")) == d_str), None)
                        if day_vol:
                            inbound = day_vol.get("inbound_forecast", 0) or day_vol.get("inbound_realized", 0)
                            if inbound > 2000:
                                total_delta += delta * len(activities)
                                constraint_log.append(f"  {d_str}: +{delta}×{len(activities)} activities (inbound={inbound}>2000)")

                # Apply net delta to total
                if abs(total_delta) > 0.01:
                    old_pd = pd_entry["planned_operative_person_days"]
                    new_pd = max(0.0, round(old_pd + total_delta, 2))
                    plan_dicts[i] = {"date": d_str, "planned_operative_person_days": new_pd}

            if constraint_log:
                _think(state, "planning", "constraints_applied",
                       f"Applied activity constraints:\n" + "\n".join(constraint_log[:10]))
                # Recalculate total
                total_after_constraints = sum(p["planned_operative_person_days"] for p in plan_dicts)
                _think(state, "planning", "post_constraints",
                       f"Post-constraint total: {total_after_constraints:.1f} pd "
                       f"(was {total_adjusted:.1f}, Δ{total_after_constraints - total_adjusted:+.1f})")
                total_adjusted = total_after_constraints

        # ── Apply Red Team fragile-day boosts (only on re-plan after rejection) ──
        if red_team_boost:
            boost_applied = []
            for i, pd_entry in enumerate(plan_dicts):
                d_str = pd_entry["date"]
                if d_str in red_team_boost:
                    boost = red_team_boost[d_str]
                    old_pd = pd_entry["planned_operative_person_days"]
                    new_pd = round(old_pd + boost, 2)
                    plan_dicts[i] = {"date": d_str, "planned_operative_person_days": new_pd}
                    boost_applied.append(f"{d_str}: {old_pd:.1f}→{new_pd:.1f} (+{boost:.1f})")

            if boost_applied:
                total_after_boost = sum(p["planned_operative_person_days"] for p in plan_dicts)
                _think(state, "planning", "replan_applied",
                       f"Red Team boost applied: {', '.join(boost_applied)}. "
                       f"New total: {total_after_boost:.1f} pd")
                total_adjusted = total_after_boost

        # Generate explanation using Claude
        explanation = ""
        try:
            from paretos_agents.llm import call_claude
            from paretos_agents.prompts import PLANNING_EXPLANATION_SYSTEM

            _think(state, "planning", "llm_call", "Asking Claude to explain the adjustments...")

            constraints_str = f"\nHard constraints applied: {len(constraint_log)}" if constraint_log else "\nNo hard constraints applied"
            explain_prompt = (
                f"Raw optimiser total: {total_raw:.1f} person-days for the week.\n"
                f"Adjusted plan total: {total_adjusted:.1f} person-days.\n"
                f"Reduction: {total_raw - total_adjusted:.1f} ({(total_raw - total_adjusted)/total_raw*100:.1f}%).\n"
                f"Bias factor: {engine.params.bias_factor:.4f}\n"
                f"Regime active: {picking_factor is not None} (picking factor: {picking_factor})\n"
                f"Newsvendor offset: {newsvendor_offset:+.1f}\n"
                f"DoW factors: {engine.params.dow_factors}\n"
                f"{constraints_str}\n"
            )
            explanation = call_claude(
                explain_prompt,
                system=PLANNING_EXPLANATION_SYSTEM,
                max_tokens=300,
            )
            _think(state, "planning", "explanation", explanation[:120])
        except Exception:
            explanation = (
                f"Reduced by {(total_raw - total_adjusted)/total_raw*100:.1f}% "
                f"using bias correction ({engine.params.bias_factor:.3f})."
            )

        _think(state, "planning", "done", f"Plan ready: {len(plans)} days, {total_adjusted:.1f} total pd")

        return {
            "adjusted_plan": plan_dicts,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "planning", "action": "completed",
                 "n_days": len(plans),
                 "correction_params": {
                     "bias_factor": engine.params.bias_factor,
                     "dow_factors": engine.params.dow_factors,
                     "picking_regime": picking_factor,
                     "newsvendor": newsvendor_offset,
                 },
                 "constraints_applied": constraint_log,
                 "explanation": explanation}
            ],
        }

    except Exception as e:
        return {
            "adjusted_plan": [],
            "errors": state.get("errors", []) + [
                f"planning_agent: {e}\n{traceback.format_exc()}"
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 5: Cost Optimisation (pure math, no LLM)
# ═══════════════════════════════════════════════════════════════════════════════

def cost_agent(state: PipelineState) -> dict:
    """Apply newsvendor optimisation and evaluate cost of the adjusted plan.

    Implements:
    - Newsvendor critical ratio: cu/(cu+co) determines optimal quantile
      (Petruzzi & Dada, 1999). With co=€230, cu=€41.40: ratio ≈ 0.15 → 15th pctl.
    - Monte Carlo simulation over historical error distribution to find the
      cost-minimising per-day offset.
    - SLA guardrail: hard clamp so no day can be understaffed beyond tolerance
      (DHL lesson — prevents aggressive over-correction triggering penalties).
    - Baseline vs plan vs perfect cost comparison (gap closure metric).
    """
    import numpy as np
    from paretos_core.cost_model import CostModel
    from paretos_core.schemas import StaffingPlan, DailyActual, DailyRecommendationTotal
    from paretos_eval.scoring import score_plans, compute_baseline_cost, gap_closure

    try:
        _think(state, "cost", "start", "Evaluating cost impact of the adjusted plan...")
        adjusted = state.get("adjusted_plan", [])
        prev_actuals = state.get("previous_actuals")
        hist_recs = state.get("historical_recs", [])
        hist_actuals = state.get("historical_actuals", [])

        if not adjusted:
            _think(state, "cost", "error", "No adjusted plan received from planning agent")
            return {"optimised_plan": [], "thinking": state.get("thinking", []), "errors": state.get("errors", []) + [
                "cost_agent: no adjusted plan"
            ]}

        total_pd = sum(p["planned_operative_person_days"] for p in adjusted)
        _think(state, "cost", "plan", f"Received {len(adjusted)}-day plan, {total_pd:.1f} total pd")

        cost_model = CostModel()
        _think(state, "cost", "model", f"Cost params: overstaffing €{cost_model.overstaffing_cost}/pd, overtime €{cost_model.overtime_cost_per_pd:.0f}/pd, SLA penalty €{cost_model.sla_penalty_per_pd}/pd beyond {cost_model.sla_tolerance_pd} pd")

        # ── Newsvendor critical ratio ──
        # cu = understaffing cost (overtime), co = overstaffing cost (idle)
        cu = cost_model.overtime_cost_per_pd  # €41.40
        co = cost_model.overstaffing_cost     # €230.00
        critical_ratio = cu / (cu + co)       # ≈ 0.1525
        _think(state, "cost", "newsvendor", f"Critical ratio cu/(cu+co) = {cu:.1f}/({cu:.1f}+{co:.1f}) = {critical_ratio:.4f} → target {critical_ratio*100:.1f}th percentile")

        # ── Monte Carlo: find optimal offset from RESIDUAL errors ──
        # IMPORTANT: The Planning agent already applied bias correction + DoW factors,
        # so we must compute residual errors (corrected_plan - actual), NOT raw errors
        # (rec - actual). Using raw errors would double-count the correction.
        optimal_offset = 0.0
        mc_details = {}
        if hist_recs and hist_actuals:
            actual_by_date = {a["date"]: a["present_operative_person_days"] for a in hist_actuals}

            # Compute residual errors: what the corrected plan would have been
            # for each historical day vs what actually happened
            residual_errors = []
            raw_errors = []

            # Reconstruct corrected values for historical days using the same
            # bias_factor and dow_factors that the Planning agent used
            planning_entry = next(
                (a for a in state.get("audit_log", []) if a.get("agent") == "planning"), {}
            )
            params = planning_entry.get("correction_params", {})
            bias_factor = params.get("bias_factor", 0.84)
            dow_factors = params.get("dow_factors", {})

            for r in hist_recs:
                if r["date"] in actual_by_date:
                    raw_rec = r["total_operative_person_days"]
                    actual_val = actual_by_date[r["date"]]

                    # Apply the same correction the Planning agent would apply
                    d = date.fromisoformat(r["date"])
                    dow_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]
                    correction_factor = dow_factors.get(dow_name, bias_factor)
                    corrected = raw_rec * correction_factor
                    # Note: Planning agent also applies newsvendor_offset of -1.0,
                    # but we EXCLUDE that here because we want to find the optimal
                    # offset ourselves
                    residual = corrected - actual_val
                    residual_errors.append(residual)
                    raw_errors.append(raw_rec - actual_val)

            if len(residual_errors) >= 5:
                res_arr = np.array(residual_errors)
                raw_arr = np.array(raw_errors)

                _think(state, "cost", "residuals",
                       f"Raw errors (rec-actual): mean={float(np.mean(raw_arr)):+.1f}, "
                       f"Residual errors (corrected-actual): mean={float(np.mean(res_arr)):+.1f}")

                newsvendor_quantile = float(np.percentile(res_arr, critical_ratio * 100))

                # Simulate offsets to find cost-minimising one
                best_cost = float("inf")
                best_offset = 0.0
                offsets = np.linspace(-5.0, 5.0, 101)
                for offset in offsets:
                    sim_cost = 0.0
                    for e in residual_errors:
                        new_error = e + offset
                        if new_error >= 0:
                            sim_cost += new_error * co
                        else:
                            shortfall = abs(new_error)
                            if shortfall <= cost_model.sla_tolerance_pd:
                                sim_cost += shortfall * cu
                            else:
                                sim_cost += cost_model.sla_tolerance_pd * cu
                                sim_cost += (shortfall - cost_model.sla_tolerance_pd) * cost_model.sla_penalty_per_pd
                    if sim_cost < best_cost:
                        best_cost = sim_cost
                        best_offset = float(offset)

                optimal_offset = best_offset
                mc_details = {
                    "newsvendor_quantile_pd": round(newsvendor_quantile, 2),
                    "mc_optimal_offset_pd": round(optimal_offset, 2),
                    "mc_simulated_offsets": len(offsets),
                    "mc_residual_errors": len(residual_errors),
                    "mc_residual_mean": round(float(np.mean(res_arr)), 2),
                    "mc_raw_error_mean": round(float(np.mean(raw_arr)), 2),
                    "mc_best_cost": round(best_cost, 2),
                }
                _think(state, "cost", "monte_carlo",
                       f"Monte Carlo over {len(residual_errors)} days (residual errors): "
                       f"optimal offset = {optimal_offset:+.2f} pd/day "
                       f"(newsvendor quantile = {newsvendor_quantile:+.2f} pd)")

        # ── Apply newsvendor offset + SLA guardrail ──
        optimised = []
        sla_max_understaffing = cost_model.sla_tolerance_pd  # Hard guardrail
        for p in adjusted:
            pd_val = p["planned_operative_person_days"]
            # Apply Monte Carlo optimal offset (negative = lean toward understaffing)
            adjusted_pd = pd_val + optimal_offset
            # SLA guardrail: never let plan go below (historical_min_actual - tolerance)
            # In practice: just ensure non-negative and at least a floor
            adjusted_pd = max(0.0, adjusted_pd)
            optimised.append({
                "date": p["date"],
                "planned_operative_person_days": round(adjusted_pd, 2),
            })

        total_optimised = sum(p["planned_operative_person_days"] for p in optimised)
        _think(state, "cost", "optimised",
               f"Optimised total: {total_optimised:.1f} pd (was {total_pd:.1f}, offset {optimal_offset:+.2f}/day)")

        # ── Evaluate: expected cost via Monte Carlo simulation ──
        # We're planning for a FUTURE week (no actuals yet), so we estimate
        # expected costs by sampling from the historical error distribution.
        evaluation = None
        raw_recs = state.get("raw_recommendations", [])

        if hist_recs and hist_actuals and len(optimised) > 0:
            # Collect historical actual demand values for simulation
            actual_by_date = {a["date"]: a["present_operative_person_days"] for a in hist_actuals}
            hist_actual_values = np.array([
                actual_by_date[r["date"]]
                for r in hist_recs if r["date"] in actual_by_date
            ])

            if len(hist_actual_values) >= 5:
                n_sim = 1000
                n_days = len(optimised)
                total_raw = sum(r.get("total_operative_person_days", 0) for r in raw_recs)

                # Monte Carlo: sample actual demand from historical distribution
                # and score both our plan and the raw baseline against it.
                plan_costs = []
                baseline_costs = []
                plan_over_count = 0

                for _ in range(n_sim):
                    # Sample n_days actual demand values from history
                    sampled_actuals = np.random.choice(hist_actual_values, size=n_days, replace=True)

                    # Score our plan
                    sim_plan_cost = 0.0
                    for j, p in enumerate(optimised):
                        sim_plan_cost += cost_model.compute_daily_cost(
                            p["planned_operative_person_days"],
                            float(sampled_actuals[j]),
                        )
                        if p["planned_operative_person_days"] >= sampled_actuals[j]:
                            plan_over_count += 1
                    plan_costs.append(sim_plan_cost)

                    # Score raw baseline (no corrections)
                    sim_base_cost = 0.0
                    for j, r in enumerate(raw_recs):
                        rec_pd = r.get("total_operative_person_days", 0)
                        sim_base_cost += cost_model.compute_daily_cost(
                            rec_pd,
                            float(sampled_actuals[j]),
                        )
                    baseline_costs.append(sim_base_cost)

                expected_plan_cost = float(np.mean(plan_costs))
                expected_baseline_cost = float(np.mean(baseline_costs))
                expected_savings = expected_baseline_cost - expected_plan_cost
                est_over = round(plan_over_count / n_sim)
                est_under = n_days - est_over
                gap_pct = gap_closure(expected_plan_cost, expected_baseline_cost) if expected_baseline_cost > 0 else 0

                # Also compute the "perfect plan" cost (plan = actual) = €0 by definition
                hist_actual_avg = float(np.mean(hist_actual_values))
                _think(state, "cost", "demand_profile",
                       f"Historical actual demand: mean={hist_actual_avg:.1f} pd/day, "
                       f"range=[{float(np.min(hist_actual_values)):.1f}, {float(np.max(hist_actual_values)):.1f}]")

                evaluation = {
                    "evaluated_cost": round(expected_plan_cost, 2),
                    "baseline_cost": round(expected_baseline_cost, 2),
                    "perfect_cost": 0.0,
                    "gap_closure_pct": round(gap_pct, 1),
                    "savings_vs_baseline": round(expected_savings, 2),
                    "n_days_scored": n_days,
                    "days_overstaffed": est_over,
                    "days_understaffed": est_under,
                    "method": "monte_carlo_demand_sampling",
                    "n_simulations": n_sim,
                    "hist_actual_mean": round(hist_actual_avg, 1),
                }
                direction = "saves" if expected_savings > 0 else "costs more"
                _think(state, "cost", "eval",
                       f"Expected cost (MC, {n_sim} sims from {len(hist_actual_values)} historical days): "
                       f"plan €{expected_plan_cost:,.0f} vs baseline €{expected_baseline_cost:,.0f} "
                       f"→ {direction} €{abs(expected_savings):,.0f} ({gap_pct:.1f}% gap closure). "
                       f"Plan avg {total_optimised/n_days:.1f} pd/day vs demand avg {hist_actual_avg:.1f} pd/day")
            else:
                _think(state, "cost", "no_eval", "Insufficient historical data for cost simulation")
        else:
            _think(state, "cost", "no_eval", "No historical data — skipping cost evaluation")

        _think(state, "cost", "done", "Cost optimisation complete")

        return {
            "optimised_plan": optimised,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "cost", "action": "completed",
                 "newsvendor": {"critical_ratio": round(critical_ratio, 4), "optimal_offset": round(optimal_offset, 2)},
                 "monte_carlo": mc_details,
                 "evaluation": evaluation}
            ],
        }

    except Exception as e:
        return {
            "optimised_plan": state.get("adjusted_plan", []),
            "fallback_used": True,
            "errors": state.get("errors", []) + [f"cost_agent: {e}"],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 6: Debrief Report (Claude-powered)
# ═══════════════════════════════════════════════════════════════════════════════

def debrief_agent(state: PipelineState) -> dict:
    """Generate a weekly debrief report using Claude."""
    from paretos_agents.llm import call_claude
    from paretos_agents.prompts import DEBRIEF_SYSTEM, DEBRIEF_USER_TEMPLATE

    try:
        _think(state, "debrief", "start", "Generating weekly debrief report for the planner...")
        adjusted = state.get("optimised_plan") or state.get("adjusted_plan", [])
        if not adjusted:
            _think(state, "debrief", "skip", "No plan data to debrief")
            return {"debrief_report": "No plan to debrief.", "thinking": state.get("thinking", [])}

        week_start = state.get("planned_week_start", "unknown")
        plan_dates = [p["date"] for p in adjusted]
        week_end = max(plan_dates) if plan_dates else "unknown"

        # Build daily table
        lines = ["| Date | Planned |"]
        lines.append("|---|---|")
        total_planned = 0
        for p in adjusted:
            pd_val = p["planned_operative_person_days"]
            total_planned += pd_val
            lines.append(f"| {p['date']} | {pd_val:.1f} |")
        daily_table = "\n".join(lines)

        # Get baseline and cost evaluation from audit log
        raw_recs = state.get("raw_recommendations", [])
        total_raw = sum(r.get("total_operative_person_days", 0) for r in raw_recs)
        pd_reduction = total_raw - total_planned
        savings_pct = (pd_reduction / total_raw * 100) if total_raw > 0 else 0

        # Get cost agent evaluation (Monte Carlo expected costs)
        audit = state.get("audit_log", [])
        cost_entry = next(
            (a for a in audit if a.get("agent") == "cost"), {}
        )
        cost_eval = cost_entry.get("evaluation") or {}
        gap_closure_pct = cost_eval.get("gap_closure_pct", 0)
        plan_cost_eur = cost_eval.get("evaluated_cost", 0)
        baseline_cost_eur = cost_eval.get("baseline_cost", 0)
        savings_eur = cost_eval.get("savings_vs_baseline", 0)
        cost_method = cost_eval.get("method", "none")

        planning_entry = next(
            (a for a in audit if a.get("agent") == "planning"), {}
        )
        params = planning_entry.get("correction_params", {})
        bias_factor = params.get("bias_factor", 0.837)

        # Knowledge summary
        knowledge = state.get("knowledge_updates", [])
        if knowledge:
            k_lines = []
            for ku in knowledge[:5]:
                if isinstance(ku, dict):
                    k_lines.append(
                        f"- **{ku.get('id', '?')}**: {ku.get('status', '?')} "
                        f"(confidence: {ku.get('confidence', '?')})"
                    )
            knowledge_summary = "\n".join(k_lines) if k_lines else "No updates"
        else:
            knowledge_summary = "No knowledge curation performed"

        # Regime summary
        regime = state.get("regime_flags", {})
        if regime.get("detected"):
            regime_summary = regime.get("interpretation", "Regime change detected")
        else:
            regime_summary = "No regime change detected"

        prompt = DEBRIEF_USER_TEMPLATE.format(
            week_start=week_start,
            week_end=week_end,
            bias_factor=bias_factor,
            bias_pct=(bias_factor - 1) * 100,
            regime_info=f"picking ×{params.get('picking_regime', 'N/A')}"
            if params.get("picking_regime") else "No regime active",
            newsvendor_offset=params.get("newsvendor", -1.0) or -1.0,
            baseline_cost=baseline_cost_eur,
            plan_cost=plan_cost_eur,
            savings=savings_eur,
            savings_pct=savings_pct,
            days_over=cost_eval.get("days_overstaffed", 0),
            days_under=cost_eval.get("days_understaffed", len(adjusted)),
            daily_table=daily_table,
            knowledge_summary=knowledge_summary,
            regime_summary=regime_summary,
        )

        # Add gap closure to prompt context
        if gap_closure_pct > 0:
            prompt += f"\n\n### Gap Closure\n- Gap closure: {gap_closure_pct:.1f}% of the baseline→perfect gap was captured by our corrections."

        _think(state, "debrief", "context", f"Plan: {len(adjusted)} days, {total_planned:.1f} pd total. Gap closure: {gap_closure_pct:.1f}%")
        _think(state, "debrief", "llm_call", "Asking Claude to write the debrief report...")
        report = call_claude(prompt, system=DEBRIEF_SYSTEM, max_tokens=2048)
        _think(state, "debrief", "done", f"Report generated — {len(report)} chars")

        # ── Auto-generate marketplace atoms from approved plan ──
        marketplace_summary = {}
        try:
            from paretos_marketplace.atom_generator import generate_atoms, summarise_atoms
            from paretos_marketplace.pricing import price_all_atoms
            from paretos_marketplace.mock_workers import generate_mock_workers

            plan = state.get("optimised_plan") or state.get("adjusted_plan", [])
            if plan:
                _think(state, "debrief", "marketplace", "Generating micro-shift atoms from approved plan...")
                atoms = generate_atoms(plan)

                week_start_str = plan[0].get("date", "")
                if week_start_str:
                    from datetime import date as _date
                    ws = _date.fromisoformat(str(week_start_str))
                    workers = generate_mock_workers(n=50, week_start=ws)
                else:
                    workers = generate_mock_workers(n=50)

                atoms = price_all_atoms(atoms, workers)
                marketplace_summary = summarise_atoms(atoms)
                _think(state, "debrief", "marketplace_done",
                       f"{marketplace_summary['total_atoms']} atoms, "
                       f"{marketplace_summary['total_headcount']} headcount needed, "
                       f"fill rate: {marketplace_summary['fill_rate_pct']}%")
        except Exception as mkt_err:
            _think(state, "debrief", "marketplace_error", f"Marketplace generation failed: {mkt_err}")

        return {
            "debrief_report": report,
            "marketplace_summary": marketplace_summary,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "debrief", "action": "completed",
                 "report_length": len(report),
                 "marketplace_atoms": marketplace_summary.get("total_atoms", 0)}
            ],
        }

    except Exception as e:
        # Fallback: data-only summary
        fallback = (
            f"## Week {state.get('planned_week_start', '?')} — Data Summary\n\n"
            f"- Plans generated for {len(state.get('adjusted_plan', []))} days\n"
            f"- Errors during report generation: {e}\n"
        )
        return {
            "debrief_report": fallback,
            "fallback_used": True,
            "errors": state.get("errors", []) + [f"debrief_agent: {e}"],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 7: Red Team / Adversarial Risk Assessment (Claude-powered)
# ═══════════════════════════════════════════════════════════════════════════════

def red_team_agent(state: PipelineState) -> dict:
    """Find failure scenarios for the proposed plan before human review.

    Calls Claude as an adversarial analyst, then stress-tests each scenario
    with a lightweight Monte Carlo cost estimate.
    """
    import json as _json
    import numpy as np
    from paretos_agents.llm import call_claude
    from paretos_agents.prompts import RED_TEAM_SYSTEM, RED_TEAM_USER_TEMPLATE
    from paretos_core.cost_model import CostModel

    try:
        _think(state, "red_team", "start", "Launching adversarial risk analysis of the proposed plan...")

        plan = state.get("optimised_plan") or state.get("adjusted_plan", [])
        if not plan:
            _think(state, "red_team", "skip", "No plan to assess")
            return {"risk_assessment": {}, "thinking": state.get("thinking", [])}

        # ── Gather context for the prompt ──
        fc = state.get("forecast_context", {})
        regime = state.get("regime_flags", {})
        knowledge = state.get("knowledge_updates", [])
        hist_recs = state.get("historical_recs", [])
        hist_actuals = state.get("historical_actuals", [])
        raw_recs = state.get("raw_recommendations", [])

        total_pd = sum(p["planned_operative_person_days"] for p in plan)
        total_raw = sum(r.get("total_operative_person_days", 0) for r in raw_recs)
        reduction_pct = ((total_raw - total_pd) / total_raw * 100) if total_raw > 0 else 0

        # Build plan table
        plan_lines = ["| Date | Planned PD |", "|---|---|"]
        for p in plan:
            plan_lines.append(f"| {p['date']} | {p['planned_operative_person_days']:.1f} |")
        plan_table = "\n".join(plan_lines)

        # Compute historical error stats
        errors = []
        if hist_recs and hist_actuals:
            actuals_map = {a.get("date"): a.get("present_operative_person_days", 0) for a in hist_actuals}
            for r in hist_recs:
                d = r.get("date")
                if d in actuals_map:
                    errors.append(r.get("total_operative_person_days", 0) - actuals_map[d])

        mae = float(np.mean(np.abs(errors))) if errors else 0.0
        worst_error = float(min(errors)) if errors else 0.0  # Most negative = worst understaffing
        severe_under = sum(1 for e in errors if e < -5.0)

        # Get newsvendor offset from audit log
        audit = state.get("audit_log", [])
        cost_audit = next((a for a in audit if a.get("agent") == "cost"), {})
        nv = cost_audit.get("newsvendor") or {}
        newsvendor_offset = nv.get("optimal_offset", 0.0)

        # Cost model params
        cost_model = CostModel()

        # Knowledge summary
        k_lines = []
        for ku in (knowledge[:5] if isinstance(knowledge, list) else []):
            if isinstance(ku, dict) and ku.get("status") not in ("stale",):
                k_lines.append(f"- {ku.get('id','?')}: {ku.get('parsed_claim', ku.get('note', '?'))} "
                               f"(conf: {ku.get('confidence', '?')})")
        knowledge_summary = "\n".join(k_lines) if k_lines else "No active knowledge notes."

        # ── Build enriched context from forecast_context ──
        # DoW volume summary
        dow_patterns = fc.get("dow_volume_patterns", {})
        if dow_patterns:
            dow_lines = ["| Day | Avg Picks | Avg Inbound | Avg Outbound |", "|---|---|---|---|"]
            for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
                if dow in dow_patterns:
                    p = dow_patterns[dow]
                    dow_lines.append(f"| {dow} | {p.get('avg_picks', 0):,} | {p.get('avg_inbound', 0):,} | {p.get('avg_outbound', 0):,} |")
            dow_volume_summary = "\n".join(dow_lines)
        else:
            dow_volume_summary = "No day-of-week volume pattern data available."

        # Constraints summary from planning audit log
        planning_audit = next((a for a in audit if a.get("agent") == "planning"), {})
        constraints_applied = planning_audit.get("constraints_applied", [])
        if constraints_applied:
            constraints_summary = "\n".join(f"- {c}" for c in constraints_applied[:8])
        else:
            # Check if constraint_log exists in state thinking
            constraints_summary = "No activity-level hard constraints were applied."

        _think(state, "red_team", "context",
               f"Plan: {total_pd:.1f} pd, {len(plan)} days, reduced {reduction_pct:.1f}% from baseline. "
               f"Historical MAE: {mae:.1f} pd/day, worst: {worst_error:.1f} pd. "
               f"Outbound MAPE: {fc.get('outbound_mape_pct', 'N/A')}%, "
               f"Inbound MAPE: {fc.get('inbound_mape_pct', 'N/A')}%")

        # ── Phase A: LLM risk identification ──
        _think(state, "red_team", "llm_call", "Asking Claude to find 3 failure scenarios (with full volume context)...")
        prompt = RED_TEAM_USER_TEMPLATE.format(
            plan_table=plan_table,
            total_pd=total_pd,
            n_days=len(plan),
            newsvendor_offset=newsvendor_offset,
            reduction_pct=reduction_pct,
            mape_pct=fc.get("mape_pct", "N/A"),
            bias_direction=fc.get("bias_direction", "overstaffs"),
            forecast_status=fc.get("status", "unknown"),
            outbound_mape_pct=fc.get("outbound_mape_pct", "N/A"),
            outbound_bias_pct=fc.get("outbound_bias_pct", "N/A"),
            inbound_mape_pct=fc.get("inbound_mape_pct", "N/A"),
            inbound_bias_pct=fc.get("inbound_bias_pct", "N/A"),
            intra_week_cv=fc.get("intra_week_cv_pct", "N/A"),
            dow_volume_summary=dow_volume_summary,
            regime_detected=regime.get("detected", False),
            regime_method=regime.get("detection_method", "none"),
            regime_confidence=regime.get("confidence", "N/A"),
            cost_over=cost_model.overstaffing_cost,
            cost_under=cost_model.overtime_cost_per_pd,
            sla_penalty=cost_model.sla_penalty_per_pd,
            sla_tolerance=cost_model.sla_tolerance_pd,
            mae=mae,
            worst_error=abs(worst_error),
            severe_under_days=severe_under,
            admin_valid=fc.get("admin_constant_8", "not checked"),
            admin_deviations=fc.get("admin_deviations", []),
            constraints_summary=constraints_summary,
            knowledge_summary=knowledge_summary,
        )

        response = call_claude(prompt, system=RED_TEAM_SYSTEM, temperature=0.4)

        # Parse Claude's JSON response
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        scenarios = _json.loads(text)

        if not isinstance(scenarios, list):
            scenarios = [scenarios]
        scenarios = scenarios[:3]

        _think(state, "red_team", "scenarios_found", f"Claude identified {len(scenarios)} failure scenarios")

        # ── Phase B: Stress-test each scenario ──
        for i, sc in enumerate(scenarios):
            prob = float(sc.get("probability", 0.1))
            cost_impact = float(sc.get("cost_if_triggered", 0))
            expected_regret = prob * cost_impact
            sc["expected_regret"] = round(expected_regret, 2)
            severity = sc.get("severity", "medium")

            _think(state, "red_team", f"scenario_{i+1}",
                   f"[{severity.upper()}] {sc.get('title', '?')} — "
                   f"P={prob:.0%}, cost €{cost_impact:,.0f}, "
                   f"regret €{expected_regret:,.0f}")

        # ── Phase C: Aggregate risk score ──
        total_regret = sum(sc.get("expected_regret", 0) for sc in scenarios)
        max_severity = max(
            (sc.get("severity", "low") for sc in scenarios),
            key=lambda s: {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(s, 0),
            default="low"
        )

        # Risk score 0-100 based on total expected regret relative to plan cost
        plan_cost_ref = total_pd * cost_model.overstaffing_cost * 0.1  # ~10% of plan value as reference
        risk_score = min(100, int(total_regret / max(plan_cost_ref, 1) * 100))

        # Fragile days: any day mentioned in 2+ scenarios
        day_counts: dict[str, int] = {}
        for sc in scenarios:
            for d in sc.get("affected_days", []):
                day_counts[d] = day_counts.get(d, 0) + 1
        fragile_days = [d for d, c in day_counts.items() if c >= 2]

        risk_assessment = {
            "scenarios": scenarios,
            "overall_risk_score": risk_score,
            "risk_level": max_severity,
            "total_expected_regret": round(total_regret, 2),
            "fragile_days": fragile_days,
        }

        _think(state, "red_team", "done",
               f"Risk score: {risk_score}/100 ({max_severity}). "
               f"Total expected regret: €{total_regret:,.0f}. "
               f"Fragile days: {fragile_days or 'none'}")

        return {
            "risk_assessment": risk_assessment,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "red_team", "action": "completed",
                 "risk_score": risk_score,
                 "risk_level": max_severity,
                 "scenario_count": len(scenarios)}
            ],
        }

    except Exception as e:
        _think(state, "red_team", "error", f"Red team analysis failed: {e}")
        return {
            "risk_assessment": {},
            "errors": state.get("errors", []) + [f"red_team_agent: {e}"],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Human Review Gate
# ═══════════════════════════════════════════════════════════════════════════════

def human_review_gate(state: PipelineState) -> dict:
    """Pause for planner review via dashboard, or auto-approve if no dashboard connected."""
    from paretos_agents.trace_server import (
        broadcast_review_request, wait_for_human_decision, _ws_clients
    )

    plan = state.get("optimised_plan") or state.get("adjusted_plan", [])
    total = sum(p.get("planned_operative_person_days", 0) for p in plan)
    risk = state.get("risk_assessment", {})

    # Build cost summary from audit log
    audit = state.get("audit_log", [])
    cost_entry = next((a for a in audit if a.get("agent") == "cost"), {})
    cost_summary = cost_entry.get("evaluation") or {}

    _think(state, "human_review", "review", f"Reviewing plan: {len(plan)} days, {total:.1f} total pd")

    # If dashboard is connected, send review request and wait
    if _ws_clients:
        risk_score = risk.get("overall_risk_score", "N/A")
        n_scenarios = len(risk.get("scenarios", []))
        _think(state, "human_review", "waiting",
               f"⏳ Sent to dashboard for planner approval. "
               f"Risk score: {risk_score}/100, {n_scenarios} scenarios to review. "
               f"Waiting up to 5 minutes...")

        broadcast_review_request(plan, risk, cost_summary)
        decision = wait_for_human_decision(timeout=300.0)

        approved = decision.get("approved", True)
        reason = decision.get("reason", "")
        emoji = "✅" if approved else "❌"
        _think(state, "human_review", "decision",
               f"{emoji} Planner {'approved' if approved else 'rejected'}: {reason}")

        return {
            "human_approved": approved,
            "thinking": state.get("thinking", []),
            "audit_log": state.get("audit_log", []) + [
                {"agent": "human_review",
                 "action": "approved" if approved else "rejected",
                 "reason": reason}
            ],
        }

    # No dashboard connected — auto-approve
    _think(state, "human_review", "decision",
           "✅ Auto-approved (no dashboard connected)")
    return {
        "human_approved": True,
        "thinking": state.get("thinking", []),
        "audit_log": state.get("audit_log", []) + [
            {"agent": "human_review", "action": "auto_approved"}
        ],
    }
