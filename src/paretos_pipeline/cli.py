"""Command-line interface for the Paretos staffing optimisation system."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from paretos_core.config import Settings
from paretos_core.cost_model import CostModel
from paretos_core.data_loader import DataStore
from paretos_eval.scoring import compute_baseline_cost, format_summary, performance_summary
from paretos_pipeline.backtest import (
    generate_holdout_predictions,
    run_walk_forward_backtest,
)
from paretos_stats.changepoint import detect_picking_regime_change


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run walk-forward backtest."""
    settings = Settings()
    store = DataStore(settings)
    cost_model = CostModel.from_json(settings.cost_model_json)

    run_walk_forward_backtest(
        store=store,
        cost_model=cost_model,
        strategy=args.strategy,
        newsvendor_offset=args.newsvendor_offset,
        verbose=True,
    )


def cmd_holdout(args: argparse.Namespace) -> None:
    """Generate holdout predictions."""
    settings = Settings()
    store = DataStore(settings)
    cost_model = CostModel.from_json(settings.cost_model_json)

    output_path = Path(args.output) if args.output else None
    generate_holdout_predictions(
        store=store,
        cost_model=cost_model,
        strategy=args.strategy,
        newsvendor_offset=args.newsvendor_offset,
        output_path=output_path,
    )


def cmd_baseline(args: argparse.Namespace) -> None:
    """Show baseline cost (raw optimiser recommendations)."""
    settings = Settings()
    store = DataStore(settings)
    cost_model = CostModel.from_json(settings.cost_model_json)

    baseline_results = compute_baseline_cost(
        store.recommendations, store.actuals, cost_model
    )
    total = sum(r.cost for r in baseline_results)
    print(f"\nBaseline cost (raw optimiser): €{total:,.0f}")
    print(f"  Days evaluated: {len(baseline_results)}")
    print(f"  Days overstaffed: {sum(1 for r in baseline_results if r.overstaffed)}")
    print(f"  Mean error: {sum(r.error for r in baseline_results)/len(baseline_results):+.2f} pd")


def cmd_detect(args: argparse.Namespace) -> None:
    """Run changepoint detection."""
    settings = Settings()
    store = DataStore(settings)

    result = detect_picking_regime_change(store.recommendations, store.actuals)
    if result:
        print(f"\nChangepoint detected:")
        for k, v in result.items():
            print(f"  {k}: {v}")
    else:
        print("\nNo changepoint detected.")


def cmd_info(args: argparse.Namespace) -> None:
    """Show dataset information."""
    settings = Settings()
    store = DataStore(settings)

    print(f"\nDataset Info:")
    print(f"  Actuals: {len(store.actuals)} days")
    print(f"  Recommendations: {len(store.recommendations)} days")
    print(f"  Volumes: {len(store.volumes)} days")
    print(f"  Decision log: {len(store.decision_log)} entries")
    print(f"  Weekly cycles: {len(store.weekly_cycles)} total")
    print(f"    Training: {len(store.training_weeks())} weeks")
    print(f"    Holdout: {len(store.holdout_weeks())} weeks")

    if store.actuals:
        dates = [a.date for a in store.actuals]
        print(f"  Date range: {min(dates)} to {max(dates)}")
        ops = [a.present_operative_person_days for a in store.actuals]
        print(f"  Operative person-days: mean={sum(ops)/len(ops):.1f}, "
              f"min={min(ops):.1f}, max={max(ops):.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="paretos",
        description="Paretos — Compounding Decision Intelligence for Warehouse Staffing",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # backtest
    bt = subparsers.add_parser("backtest", help="Run walk-forward backtest")
    bt.add_argument(
        "-s", "--strategy", choices=["A", "B", "C"], default="C",
        help="Correction strategy: A=flat, B=DoW, C=full compound (default: C)",
    )
    bt.add_argument(
        "--newsvendor-offset", type=float, default=-1.0,
        help="Newsvendor offset in person-days (default: -1.0)",
    )

    # holdout
    ho = subparsers.add_parser("holdout", help="Generate holdout predictions")
    ho.add_argument(
        "-s", "--strategy", choices=["A", "B", "C"], default="C",
        help="Correction strategy (default: C)",
    )
    ho.add_argument(
        "--newsvendor-offset", type=float, default=-1.0,
        help="Newsvendor offset in person-days (default: -1.0)",
    )
    ho.add_argument(
        "-o", "--output", type=str, default=None,
        help="Output CSV path (default: output/holdout_predictions.csv)",
    )

    # baseline
    subparsers.add_parser("baseline", help="Show baseline cost")

    # detect
    subparsers.add_parser("detect", help="Run changepoint detection")

    # info
    subparsers.add_parser("info", help="Show dataset information")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "backtest": cmd_backtest,
        "holdout": cmd_holdout,
        "baseline": cmd_baseline,
        "detect": cmd_detect,
        "info": cmd_info,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
