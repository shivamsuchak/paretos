#!/usr/bin/env python3
"""CLI runner for the Micro-Shift Marketplace.

Usage:
    python run_marketplace.py                      # default: generate from latest plan
    python run_marketplace.py --plan-file plan.json # from a saved plan
    python run_marketplace.py --port 8100           # custom API port
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main():
    parser = argparse.ArgumentParser(description="Paretos Micro-Shift Marketplace")
    parser.add_argument("--port", type=int, default=8100, help="API port (default: 8100)")
    parser.add_argument("--host", default="127.0.0.1", help="API host")
    parser.add_argument("--workers", type=int, default=50, help="Number of mock workers")
    parser.add_argument("--plan-file", type=str, help="Path to saved plan JSON")
    parser.add_argument("--week", type=int, help="Week number to load plan from pipeline")
    parser.add_argument("--no-server", action="store_true", help="Just generate and print, don't start API")
    args = parser.parse_args()

    from paretos_marketplace.atom_generator import generate_atoms, summarise_atoms
    from paretos_marketplace.mock_workers import generate_mock_workers
    from paretos_marketplace.pricing import price_all_atoms

    # ── Load or create a sample plan ──
    plan: list[dict] = []

    if args.plan_file:
        with open(args.plan_file) as f:
            plan = json.load(f)
        print(f"Loaded plan from {args.plan_file}: {len(plan)} days")
    else:
        # Generate a demo plan
        from datetime import timedelta
        week_start = date.today() - timedelta(days=date.today().weekday())  # Monday
        plan = [
            {"date": str(week_start + timedelta(days=i)),
             "planned_operative_person_days": [52.0, 48.0, 50.0, 46.0, 42.0][i]}
            for i in range(5)
        ]
        print(f"Using demo plan: {len(plan)} days, week starting {week_start}")

    # ── Generate atoms ──
    atoms = generate_atoms(plan)
    print(f"\n{'='*60}")
    print(f"ATOM GENERATION")
    print(f"{'='*60}")
    print(f"Generated {len(atoms)} work atoms from {len(plan)}-day plan")

    # ── Generate mock workers ──
    week_start = date.fromisoformat(plan[0]["date"]) if plan else date.today()
    workers = generate_mock_workers(n=args.workers, week_start=week_start)
    print(f"Created {len(workers)} mock workers")

    tier_counts = {}
    for w in workers:
        tier_counts[w.tier] = tier_counts.get(w.tier, 0) + 1
    print(f"  Tiers: {tier_counts}")

    # ── Apply dynamic pricing ──
    atoms = price_all_atoms(atoms, workers)
    surged = [a for a in atoms if a.surge_multiplier > 1.0]
    print(f"Priced all atoms ({len(surged)} with surge)")

    # ── Summary ──
    summary = summarise_atoms(atoms)
    print(f"\n{'='*60}")
    print(f"MARKETPLACE SUMMARY")
    print(f"{'='*60}")
    print(f"Total atoms:     {summary['total_atoms']}")
    print(f"By status:       {summary['by_status']}")
    print(f"Total headcount: {summary['total_headcount']}")
    print(f"Fill rate:       {summary['fill_rate_pct']}%")
    print(f"\nBy activity:")
    for act, count in sorted(summary["by_activity"].items()):
        print(f"  {act:30s} {count} atoms")

    # ── Print sample atoms ──
    print(f"\n--- Sample atoms (first 5) ---")
    for a in atoms[:5]:
        print(f"  {a.id}")
        print(f"    {a.date} {a.start_time}–{a.end_time} | {a.activity}")
        print(f"    HC: {a.headcount} | €{a.final_price_eur:.2f} "
              f"(surge: {a.surge_multiplier}×) | Skills: {a.skill_requirements}")

    if args.no_server:
        return

    # ── Start FastAPI server ──
    print(f"\n{'='*60}")
    print(f"STARTING MARKETPLACE API")
    print(f"{'='*60}")
    print(f"http://{args.host}:{args.port}")
    print(f"Swagger docs: http://{args.host}:{args.port}/docs")
    print(f"Press Ctrl+C to stop\n")

    # Pre-populate the API state
    from paretos_marketplace import api
    for a in atoms:
        api._atoms[a.id] = a
    for w in workers:
        api._workers[w.id] = w

    import uvicorn
    uvicorn.run(api.app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
