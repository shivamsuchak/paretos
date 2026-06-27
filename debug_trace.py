#!/usr/bin/env python3
"""Deep trace of what each agent sees, thinks, and decides."""

import sys
import time
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from paretos_core.config import Settings
from paretos_core.data_loader import DataStore
from paretos_agents.orchestrator import run_weekly_cycle

week_idx = 10
store = DataStore(Settings())
week_idx = min(week_idx, len(store.weekly_cycles) - 1)
week = store.weekly_cycles[week_idx]

# Build history
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
log = [e.model_dump(mode="json") for e in store.decision_log[:15]]

print("=" * 80)
print(f"DEEP TRACE — Week {week_idx}: {week.planned_week_start}")
print("=" * 80)

# Show what data goes in
print(f"\n📥 INPUT DATA")
print(f"  Recommendations (what the optimiser says to staff):")
for r in raw_recs:
    print(f"    {r['date']}: {r['total_operative_person_days']:.1f} person-days")
print(f"  Previous week actuals (what actually happened last week):")
if prev_actuals:
    for a in prev_actuals:
        print(f"    {a['date']}: {a.get('operative_person_days', a.get('total_person_days', '?'))}")
else:
    print(f"    (none available)")

print(f"  Planner notes: {len(log)} entries")
for n in log[:3]:
    print(f"    - [{n.get('date','')}] {n.get('note', str(n))[:100]}")

print(f"\n  Historical data for calibration:")
print(f"    {len(hist_recs)} past recommendation days")
print(f"    {len(hist_actuals)} past actual days")

# Run the pipeline (no dashboard — auto-approve)
print(f"\n{'=' * 80}")
print("RUNNING PIPELINE — watch each agent think...")
print("=" * 80)

result = run_weekly_cycle(
    cycle_date=week.planned_week_start - timedelta(days=5),
    planned_week_start=week.planned_week_start,
    raw_recommendations=raw_recs,
    historical_recs=hist_recs,
    historical_actuals=hist_actuals,
    decision_log_entries=log,
    previous_actuals=prev_actuals,
    volumes=vols,
    visualize=False,
)

# Now print EVERYTHING each agent thought
thinking = result.get("thinking", [])
print(f"\n{'=' * 80}")
print(f"FULL AGENT THINKING TRACE ({len(thinking)} steps)")
print("=" * 80)

current_agent = None
for t in thinking:
    agent = t.get("agent", "?")
    if agent != current_agent:
        current_agent = agent
        print(f"\n{'─' * 60}")
        print(f"🤖 AGENT: {agent.upper()}")
        print(f"{'─' * 60}")
    print(f"  [{t.get('timestamp','')}] {t.get('step','')}")
    print(f"    → {t.get('detail','')}")

# Show the plan
print(f"\n{'=' * 80}")
print("FINAL OUTPUTS")
print("=" * 80)

plan = result.get("optimised_plan") or result.get("adjusted_plan", [])
print(f"\n📋 Staffing Plan:")
for p in plan:
    print(f"  {p['date']}: {p['planned_operative_person_days']:.1f} pd")

risk = result.get("risk_assessment", {})
if risk.get("scenarios"):
    print(f"\n🔴 Red Team Risk Assessment:")
    print(f"  Overall risk score: {risk.get('overall_risk_score', '?')}/100 ({risk.get('risk_level', '?')})")
    print(f"  Total expected regret: €{risk.get('total_expected_regret', 0):,.0f}")
    print(f"  Fragile days: {risk.get('fragile_days', [])}")
    for i, s in enumerate(risk["scenarios"], 1):
        print(f"\n  Scenario {i}: [{s.get('severity','')}] {s.get('title','')}")
        print(f"    What could happen: {s.get('description','')}")
        print(f"    Probability: {s.get('probability_pct','?')}%")
        print(f"    Cost if it happens: €{s.get('estimated_cost_eur', 0):,.0f}")
        print(f"    Expected loss: €{s.get('expected_regret_eur', 0):,.0f}")
        print(f"    Affected days: {s.get('affected_days', [])}")
        print(f"    How to fix: {s.get('mitigation','')}")

mkt = result.get("marketplace_summary", {})
if mkt.get("total_atoms"):
    print(f"\n🏪 Marketplace:")
    print(f"  {mkt['total_atoms']} work atoms generated")
    print(f"  {mkt['total_headcount']} total headcount needed")

print(f"\n✅ Pipeline complete.")
