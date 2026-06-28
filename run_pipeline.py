"""Run the multi-agent pipeline with live visualization.

Usage:
    python run_pipeline.py              # Run with visualization (opens browser)
    python run_pipeline.py --no-viz     # Run without visualization
    python run_pipeline.py --week 15    # Run for a specific training week (0-19)
"""

import argparse
import sys
import time

sys.path.insert(0, "src")

from datetime import timedelta

from paretos_core.config import Settings
from paretos_core.data_loader import DataStore
from paretos_agents.orchestrator import run_weekly_cycle
from paretos_agents.trace_server import (
    start_trace_server, broadcast_pipeline_done, broadcast_results,
    broadcast_available_weeks, wait_for_week_selection,
)


def _build_week_payload(store: DataStore) -> list[dict]:
    """Build the list of available weeks for the UI picker."""
    weeks = []
    for i, wc in enumerate(store.weekly_cycles):
        has_actuals = bool(wc.actuals)
        label = f"Week {i}: {wc.planned_week_start}"
        if not has_actuals:
            label += " (holdout)"
        weeks.append({
            "index": i,
            "week_start": str(wc.planned_week_start),
            "has_actuals": has_actuals,
            "label": label,
        })
    return weeks


def _prepare_week(store: DataStore, week_idx: int, max_notes: int = 5):
    """Prepare all data for a given week index."""
    week_idx = min(week_idx, len(store.weekly_cycles) - 1)
    week = store.weekly_cycles[week_idx]

    prior = [w for w in store.weekly_cycles[:week_idx] if w.actuals]
    hist_recs = [r.model_dump(mode="json") for w in prior for r in w.recommendations]
    hist_actuals = [a.model_dump(mode="json") for w in prior for a in w.actuals]
    raw_recs = [r.model_dump(mode="json") for r in week.recommendations]

    prev_actuals = None
    if week_idx > 0:
        pw = store.weekly_cycles[week_idx - 1]
        if pw.actuals:
            prev_actuals = [a.model_dump(mode="json") for a in pw.actuals]

    vols = [v.model_dump(mode="json") for v in store.volumes] if store.volumes else None
    log = [e.model_dump(mode="json") for e in store.decision_log[:max_notes]]

    return week, week_idx, hist_recs, hist_actuals, raw_recs, prev_actuals, vols, log


def main():
    parser = argparse.ArgumentParser(description="Run the staffing agent pipeline")
    parser.add_argument("--no-viz", action="store_true", help="Disable visualization")
    parser.add_argument("--week", type=int, default=None,
                        help="Training week index (0-19). If omitted with --no-viz, defaults to 10. "
                             "If omitted with visualization, shows a picker in the dashboard.")
    parser.add_argument("--notes", type=int, default=5, help="Max decision log notes to send")
    args = parser.parse_args()

    store = DataStore(Settings())

    # Start real-time thinking dashboard
    if not args.no_viz:
        start_trace_server(open_browser=True)
        time.sleep(1)  # Let browser connect

    # Determine week index
    if args.week is not None:
        # Explicit --week flag: use it directly
        week_idx = args.week
    elif args.no_viz:
        # No viz, no --week: default to 10
        week_idx = 10
    else:
        # Viz mode, no --week: let user pick in the dashboard
        print("Waiting for week selection in dashboard...")
        available = _build_week_payload(store)
        broadcast_available_weeks(available)
        selected = wait_for_week_selection(timeout=600)
        if selected is None:
            print("Timeout waiting for week selection. Defaulting to week 10.")
            week_idx = 10
        else:
            week_idx = selected
            print(f"User selected week {week_idx}")

    week, week_idx, hist_recs, hist_actuals, raw_recs, prev_actuals, vols, log = \
        _prepare_week(store, week_idx, args.notes)

    print(f"{'='*60}")
    print(f"PARETOS MULTI-AGENT PIPELINE")
    print(f"{'='*60}")
    print(f"Week:        {week.planned_week_start}")
    print(f"History:     {len(hist_recs)} rec days, {len(hist_actuals)} actual days")
    print(f"This week:   {len(raw_recs)} recommendation days")
    print(f"Notes:       {len(log)} decision log entries")
    print(f"Visualize:   {'YES — browser will open' if not args.no_viz else 'disabled'}")
    print(f"{'='*60}")
    print()

    t0 = time.time()

    result = run_weekly_cycle(
        cycle_date=week.planned_week_start - timedelta(days=5),
        planned_week_start=week.planned_week_start,
        raw_recommendations=raw_recs,
        historical_recs=hist_recs,
        historical_actuals=hist_actuals,
        decision_log_entries=log,
        previous_actuals=prev_actuals,
        volumes=vols,
        visualize=not args.no_viz,
    )

    elapsed = time.time() - t0

    # Signal dashboard that pipeline is done + send results
    if not args.no_viz:
        broadcast_results(result)
        time.sleep(0.3)  # Let results arrive before done signal
        broadcast_pipeline_done()

    print(f"\n{'='*60}")
    print(f"RESULTS (completed in {elapsed:.1f}s)")
    print(f"{'='*60}")
    fc = result.get("forecast_context", {})
    print(f"Forecast:  {fc.get('status', '?')} (MAPE: {fc.get('mape_pct', '?')}%)")
    print(f"Knowledge: {len(result.get('knowledge_updates', []))} notes curated")
    print(f"Regime:    detected={result.get('regime_flags', {}).get('detected', '?')}")
    print(f"Plan:      {len(result.get('adjusted_plan', []))} days")
    print(f"Approved:  {result.get('human_approved', '?')}")
    print(f"Errors:    {len(result.get('errors', []))}")

    print(f"\n--- Adjusted Plan ---")
    for p in result.get("adjusted_plan", []):
        print(f"  {p['date']}: {p['planned_operative_person_days']:.1f} person-days")

    if result.get("knowledge_updates"):
        print(f"\n--- Knowledge Updates ---")
        for ku in result.get("knowledge_updates", [])[:5]:
            if isinstance(ku, dict):
                print(f"  {ku.get('id','?')}: {ku.get('status','?')} "
                      f"(confidence: {ku.get('confidence','?')})")

    # Show risk assessment
    risk = result.get("risk_assessment", {})
    if risk.get("scenarios"):
        print(f"\n--- Red Team Risk Assessment (score: {risk.get('overall_risk_score', '?')}/100, "
              f"level: {risk.get('risk_level', '?')}) ---")
        for sc in risk["scenarios"]:
            sev = sc.get("severity", "?").upper()
            print(f"  [{sev}] {sc.get('title', '?')}")
            print(f"         P={sc.get('probability', 0):.0%}, "
                  f"cost €{sc.get('cost_if_triggered', 0):,.0f}, "
                  f"regret €{sc.get('expected_regret', 0):,.0f}")
            if sc.get("mitigation"):
                print(f"         ⚡ {sc['mitigation']}")

    # Show thinking trace summary
    thinking = result.get("thinking", [])
    if thinking:
        print(f"\n--- Agent Thinking Trace ({len(thinking)} steps) ---")
        for t in thinking:
            print(f"  [{t.get('timestamp','')}] {t.get('agent','?'):>12} │ "
                  f"{t.get('step','')}: {t.get('detail','')}")

    print(f"\n--- Debrief Report ---")
    print(result.get("debrief_report", "N/A")[:1000])

    # Show marketplace summary
    mkt = result.get("marketplace_summary", {})
    if mkt.get("total_atoms"):
        print(f"\n--- Marketplace (auto-generated) ---")
        print(f"  Atoms:     {mkt['total_atoms']}")
        print(f"  Headcount: {mkt['total_headcount']}")
        print(f"  Fill rate: {mkt['fill_rate_pct']}%")
        by_act = mkt.get("by_activity", {})
        if by_act:
            print(f"  Activities: {', '.join(f'{k}: {v}' for k, v in by_act.items())}")

    if result.get("errors"):
        print(f"\n--- Errors ---")
        for err in result.get("errors", []):
            print(f"  {err[:200]}")


if __name__ == "__main__":
    main()
