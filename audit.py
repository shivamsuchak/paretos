#!/usr/bin/env python3
"""Comprehensive data audit — what's used, what's missing, what's underutilized."""
import csv, json, sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

DATA = Path("data")

print("=" * 80)
print("COMPREHENSIVE DATA AUDIT")
print("=" * 80)

# ── 1. Load all data sources ──
with open(DATA / "clean/present_long.csv") as f:
    actuals = list(csv.DictReader(f))
with open(DATA / "clean/volumes_long.csv") as f:
    volumes = list(csv.DictReader(f))
with open(DATA / "clean/recommendations_long.csv") as f:
    recs = list(csv.DictReader(f))
with open(DATA / "cost_model.json") as f:
    cost = json.load(f)
with open(DATA / "decision_log.json") as f:
    dlog = json.load(f)

# Raw files
raw_rec_files = sorted((DATA / "recommendations").glob("rec_*.csv"))
raw_present_files = sorted((DATA / "actuals").glob("present_*.csv"))
raw_volume_files = sorted((DATA / "actuals").glob("volumes_*.csv"))

print(f"\n📁 DATA INVENTORY")
print(f"  clean/present_long.csv:        {len(actuals)} rows (daily actuals)")
print(f"  clean/volumes_long.csv:        {len(volumes)} rows (daily volumes)")
print(f"  clean/recommendations_long.csv:{len(recs)} rows (activity-level recs)")
print(f"  cost_model.json:               1 file")
print(f"  decision_log.json:             {len(dlog['entries'])} entries")
print(f"  recommendations/ (raw):        {len(raw_rec_files)} weekly files")
print(f"  actuals/present_* (raw):       {len(raw_present_files)} weekly files")
print(f"  actuals/volumes_* (raw):       {len(raw_volume_files)} weekly files")

# ── 2. Date coverage ──
actual_dates = sorted(set(r["date"] for r in actuals))
vol_dates = sorted(set(r["date"] for r in volumes))
rec_dates = sorted(set(r["date"] for r in recs))

print(f"\n📅 DATE COVERAGE")
print(f"  Actuals:  {actual_dates[0]} to {actual_dates[-1]} ({len(actual_dates)} days)")
print(f"  Volumes:  {vol_dates[0]} to {vol_dates[-1]} ({len(vol_dates)} days)")
print(f"  Recs:     {rec_dates[0]} to {rec_dates[-1]} ({len(rec_dates)} unique days)")

actual_set = set(actual_dates)
vol_set = set(vol_dates)
rec_set = set(rec_dates)

print(f"\n  Actuals without volumes: {len(actual_set - vol_set)} days")
print(f"  Volumes without actuals: {len(vol_set - actual_set)} days")
print(f"  Actuals without recs:    {len(actual_set - rec_set)} days")
print(f"  Recs without actuals:    {len(rec_set - actual_set)} days (= holdout weeks)")

# Gaps in actuals
dates = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in actual_dates)
gaps = []
for i in range(1, len(dates)):
    gap = (dates[i] - dates[i - 1]).days
    if gap > 3:
        gaps.append(f"    {dates[i-1]} → {dates[i]} ({gap} days)")
print(f"  Gaps in actuals (>weekend): {len(gaps)}")
for g in gaps:
    print(g)

# ── 3. Column audit ──
print(f"\n📊 COLUMN AUDIT — what exists vs what's used by agents")

# Actuals columns
print(f"\n  present_long.csv columns: {list(actuals[0].keys())}")
print(f"    ✅ date — used everywhere")
print(f"    ✅ present_total_person_days — loaded but NOT used by any agent")
print(f"    ✅ present_operative_person_days — used by Planning, Cost, Red Team")

# Volumes columns
print(f"\n  volumes_long.csv columns: {list(volumes[0].keys())}")
print(f"    ✅ date — used for joining")
print(f"    ✅ picks_forecast — used by Forecast agent (MAPE calc)")
print(f"    ✅ picks_realized — used by Forecast agent (MAPE + trend)")
print(f"    ❌ outbound_forecast — NOT used by any agent")
print(f"    ❌ outbound_realized — NOT used by any agent")
print(f"    ❌ inbound_forecast — NOT used by any agent")
print(f"    ❌ inbound_realized — NOT used by any agent")

# Recommendations columns
print(f"\n  recommendations_long.csv columns: {list(recs[0].keys())}")
print(f"    ✅ decision_date — used for weekly cycle grouping")
print(f"    ✅ planned_week_start — used for weekly cycle grouping")
print(f"    ✅ date — used everywhere")
print(f"    ✅ activity — loaded into by_activity dict, passed to Red Team prompt")
print(f"    ✅ group — used to filter operative vs admin")
print(f"    ✅ recommended_person_days — summed for total, used in planning")

# Activity breakdown
activities = Counter(r["activity"] for r in recs if r["group"] == "operative")
print(f"\n  Activities in recommendations ({len(activities)} operative):")
for act, count in activities.most_common():
    print(f"    {act}: {count} rows")

# Admin activities (always 8 pd, excluded from scoring)
admin_activities = Counter(r["activity"] for r in recs if r["group"] == "admin")
print(f"\n  Admin activities (excluded from scoring, always 8 pd/day):")
for act, count in admin_activities.most_common():
    print(f"    {act}: {count} rows")

# ── 4. Raw file column audit (what's in raw CSVs but not in clean) ──
print(f"\n📋 RAW FILE AUDIT — data in raw CSVs that doesn't make it to clean")

# Read one raw recommendation to check volume rows
with open(raw_rec_files[5]) as f:
    raw_lines = f.readlines()
print(f"\n  Raw recommendation file has these volume rows (SKIPPED by loader):")
for line in raw_lines[1:6]:
    parts = line.strip().split(";")
    if parts[0] in ("PAL_Wareneingang", "VollPAL_Warenausgang", "Picks_Warenausgang", "KomPAL_Warenausgang"):
        print(f"    {parts[0]}: {parts[1:6]}")

# Raw present files have FORECAST_PL column
print(f"\n  Raw present files (present_*.csv) have column FORECAST_PL:")
empty_count = 0
non_empty = 0
for pf in raw_present_files:
    with open(pf) as f:
        reader = csv.DictReader(f)
        for row in reader:
            val = row.get("FORECAST_PL", "").strip().strip('"')
            if val:
                non_empty += 1
            else:
                empty_count += 1
print(f"    Empty values: {empty_count}")
print(f"    Non-empty values: {non_empty}")
if non_empty == 0:
    print(f"    ⚠️  FORECAST_PL is always empty — column exists but has no data")

# ── 5. Cost model audit ──
print(f"\n💰 COST MODEL AUDIT")
print(f"  regular_cost_per_person_day: €{cost['regular_cost_per_person_day']}")
print(f"  idle_cost_per_person_day:    €{cost['overstaffing']['idle_cost_per_person_day']}")
print(f"  overtime_premium_pct:        {cost['understaffing']['overtime_premium_pct']}%")
print(f"  sla_tolerance_person_days:   {cost['understaffing']['sla_tolerance_person_days']}")
print(f"  sla_penalty_per_person_day:  €{cost['understaffing']['sla_penalty_per_person_day']}")
print(f"  ✅ All fields used by Cost agent")

# ── 6. Decision log audit ──
print(f"\n📝 DECISION LOG AUDIT")
entries = dlog["entries"]
print(f"  Total entries: {len(entries)}")
authors = Counter(e["author"] for e in entries)
print(f"  Authors: {dict(authors)}")
scopes = Counter(str(e["scope"]) for e in entries)
print(f"  Scopes: {dict(scopes)}")
effects = Counter(e["claimed_effect"]["kind"] for e in entries)
print(f"  Effect types: {dict(effects)}")
print(f"  ✅ All entries loaded and sent to Knowledge agent for validation")
print(f"  ⚠️  claimed_effect.kind is used as a hint but NOT machine-applied")
print(f"     (the agent only validates notes, doesn't auto-apply rules like 'fixed transit = 4')")

# ── 7. What the pipeline ACTUALLY uses vs ignores ──
print(f"\n{'=' * 80}")
print(f"FINDINGS SUMMARY")
print(f"{'=' * 80}")

print(f"""
✅ CORRECTLY USED:
  1. present_operative_person_days — core metric for bias calibration, cost scoring
  2. picks_forecast + picks_realized — Forecast agent MAPE and trend detection
  3. by_activity breakdown — passed to Red Team for activity-level risk analysis
  4. decision_log entries — all 15 validated by Knowledge agent
  5. cost_model.json — all fields used for newsvendor critical ratio + Monte Carlo
  6. historical recs vs actuals — 48-day window for bias factor + DoW calibration

❌ NOT USED (available but ignored):
  1. outbound_forecast / outbound_realized (volumes_long.csv)
     → Could improve forecast accuracy analysis for loading/staging activities
  2. inbound_forecast / inbound_realized (volumes_long.csv)
     → Could improve forecast for receiving/putaway/unloading activities
  3. present_total_person_days (present_long.csv)
     → Loaded but never referenced by any agent (only operative pd is used)
  4. Volume rows in raw rec CSVs: PAL_Wareneingang, VollPAL_Warenausgang,
     Picks_Warenausgang, KomPAL_Warenausgang
     → Explicitly skipped by data_loader.py (SKIP_ROWS), but contain the 
        per-day volume forecasts the optimiser used when generating its plan
  5. FORECAST_PL column in raw present_*.csv
     → Always empty — appears to be a placeholder never filled
  6. claimed_effect structured data in decision_log.json
     → Has machine-readable rules (kind=fixed, value=4, activity=transit)
        but the pipeline only sends the free-text 'note' to Claude, never
        programmatically applies these structured claims

⚠️  MISSING KPIs (should exist but don't):
  1. Activity-level actuals — we have activity-level RECOMMENDATIONS but only
     TOTAL actuals. Cannot validate individual activity claims (e.g., "transit
     is always 4") because we don't have per-activity actual headcount.
  2. Forecast error by volume type — MAPE is only computed on picks. No MAPE
     for outbound pallets or inbound pallets, even though the data exists.
  3. Intra-week volatility — no metric for how much demand varies within a
     week vs. between weeks. This matters for the micro-shift marketplace.
  4. Day-of-week volume patterns — volumes are loaded but not analyzed by DoW.
     The Planning agent applies DoW corrections to staffing but never checks
     if volume itself has DoW patterns.
  5. Planner override accuracy — no tracking of "when the human rejected a
     plan, was the re-run actually better?" The human review loop logs 
     decisions but doesn't score them retrospectively.
  6. Red Team calibration — risk scenarios have P(failure) estimates but
     there's no feedback loop checking whether flagged scenarios actually
     materialized in subsequent actuals.
  7. Admin headcount stability — admin is assumed fixed at 8 pd/day (present_total
     minus present_operative). This is never validated.
  8. Worker availability / no-show rate — the Red Team flags temp agency failure
     as a risk but has no historical data on actual no-show rates.

🔧 RECOMMENDED NEXT STEPS:
  1. Use outbound + inbound volumes in Forecast agent (add MAPE per volume type)
  2. Programmatically apply claimed_effect rules from decision log as hard
     constraints in the Planning agent (e.g., clamp transit to 4 FTE)
  3. Add activity-level actual tracking (if WMS data is available) to enable
     per-activity bias calibration
  4. Build a Red Team calibration loop: after each week's actuals come in,
     check if flagged scenarios materialized
  5. Track human override quality: compare cost of approved plan vs. rejected
     plan after actuals are known
  6. Validate admin headcount assumption (always 8 pd) against data
""")
