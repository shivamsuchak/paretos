"""Walk-forward backtesting over the 20 training weeks.

Simulates the compounding loop: each week uses ONLY information available
up to that decision date. No future data leakage.

Strategies:
  A) Flat bias correction (calibrated on all available history)
  B) DoW-adjusted correction
  C) Full compound: DoW + pick-by-light regime + newsvendor offset
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Sequence

from paretos_core.config import Settings
from paretos_core.cost_model import CostModel
from paretos_core.data_loader import DataStore
from paretos_core.schemas import (
    CorrectionParams,
    DailyActual,
    DailyRecommendationTotal,
    StaffingPlan,
)
from paretos_eval.scoring import (
    compute_baseline_cost,
    format_summary,
    performance_summary,
    score_plans,
)
from paretos_stats.bias_correction import compute_bias_factor
from paretos_stats.corrections import CorrectionEngine
from paretos_stats.dow_adjustment import compute_dow_factors

PICK_BY_LIGHT_DATE = date(2026, 8, 24)
PICK_BY_LIGHT_FACTOR = 0.73  # 1 - 0.27 = 73% of original picking need


def _cumulative_data_up_to(
    all_recs: Sequence[DailyRecommendationTotal],
    all_actuals: Sequence[DailyActual],
    cutoff: date,
) -> tuple[list[DailyRecommendationTotal], list[DailyActual]]:
    """Get all data strictly before the cutoff date (no future leakage)."""
    recs = [r for r in all_recs if r.date < cutoff]
    actuals = [a for a in all_actuals if a.date < cutoff]
    return recs, actuals


def run_walk_forward_backtest(
    store: DataStore,
    cost_model: CostModel,
    strategy: str = "C",
    newsvendor_offset: float = -1.0,
    verbose: bool = True,
) -> tuple[list[StaffingPlan], dict]:
    """Run walk-forward backtest over all training weeks.

    For each week:
    1. Gather all historical data up to the decision date
    2. Calibrate correction parameters on available history
    3. Apply corrections to the current week's recommendations
    4. Score against actuals

    Args:
        store: DataStore with loaded data.
        cost_model: CostModel instance.
        strategy: 'A' (flat), 'B' (DoW), or 'C' (full compound).
        newsvendor_offset: Additive person-day offset for strategy C.
        verbose: Print per-week results.

    Returns:
        Tuple of (all plans, performance summary dict).
    """
    training = store.training_weeks()
    all_recs = store.recommendations
    all_actuals = store.actuals

    all_plans: list[StaffingPlan] = []
    all_plan_actuals: list[DailyActual] = []

    if verbose:
        print(f"\n{'='*70}")
        print(f"WALK-FORWARD BACKTEST — Strategy {strategy}")
        print(f"{'='*70}\n")

    for week in training:
        # Data available up to the decision date (strict: no same-week actuals)
        hist_recs, hist_actuals = _cumulative_data_up_to(
            all_recs, all_actuals, week.planned_week_start
        )

        if len(hist_actuals) < 5:
            # Not enough history — use flat global bias
            engine = CorrectionEngine(
                CorrectionParams(
                    effective_from=week.planned_week_start,
                    bias_factor=0.837,  # fallback from analysis
                    dow_factors={"Mon": 0.837, "Tue": 0.837, "Wed": 0.837,
                                 "Thu": 0.837, "Fri": 0.837},
                )
            )
        else:
            # Determine regime parameters
            use_regime = strategy == "C" and week.planned_week_start >= PICK_BY_LIGHT_DATE
            picking_start = PICK_BY_LIGHT_DATE if use_regime else None
            picking_factor = PICK_BY_LIGHT_FACTOR if use_regime else None

            nv_offset = newsvendor_offset if strategy == "C" else 0.0

            if strategy == "A":
                # Flat bias only — compute factor, use it as uniform DoW
                factor = compute_bias_factor(hist_recs, hist_actuals)
                engine = CorrectionEngine(
                    CorrectionParams(
                        effective_from=week.planned_week_start,
                        bias_factor=factor,
                        dow_factors={d: factor for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]},
                    )
                )
            else:
                # Strategy B or C — use full calibration
                engine = CorrectionEngine.from_training_data(
                    hist_recs,
                    hist_actuals,
                    picking_regime_start=picking_start,
                    picking_regime_factor=picking_factor,
                    newsvendor_offset=nv_offset,
                )

        # Apply corrections
        week_plans = engine.correct_week(week.recommendations)
        all_plans.extend(week_plans)

        if week.actuals:
            all_plan_actuals.extend(week.actuals)

            if verbose:
                week_results = score_plans(week_plans, week.actuals, cost_model)
                week_cost = sum(r.cost for r in week_results)
                baseline = compute_baseline_cost(week.recommendations, week.actuals, cost_model)
                baseline_cost = sum(r.cost for r in baseline)
                saving = baseline_cost - week_cost
                print(
                    f"  Week {week.planned_week_start}: "
                    f"baseline=€{baseline_cost:>8,.0f}  plan=€{week_cost:>8,.0f}  "
                    f"saving=€{saving:>8,.0f}  "
                    f"(bias={engine.params.bias_factor:.3f})"
                )

    # Overall scoring
    plan_results = score_plans(all_plans, all_plan_actuals, cost_model)
    baseline_results = compute_baseline_cost(
        [r for r in all_recs if any(a.date == r.date for a in all_plan_actuals)],
        all_plan_actuals,
        cost_model,
    )
    summary = performance_summary(plan_results, baseline_results)

    if verbose:
        print()
        print(format_summary(summary))

    return all_plans, summary


def generate_holdout_predictions(
    store: DataStore,
    cost_model: CostModel,
    strategy: str = "C",
    newsvendor_offset: float = -1.0,
    output_path: Path | None = None,
) -> list[StaffingPlan]:
    """Generate staffing plans for the holdout period.

    Uses ALL training data to calibrate, then applies corrections to holdout
    recommendations.
    """
    all_recs = store.recommendations
    all_actuals = store.actuals
    holdout_weeks = store.holdout_weeks()

    if not holdout_weeks:
        print("No holdout weeks found.")
        return []

    # Calibrate on all training data
    use_regime = strategy == "C"
    picking_start = PICK_BY_LIGHT_DATE if use_regime else None
    picking_factor = PICK_BY_LIGHT_FACTOR if use_regime else None
    nv_offset = newsvendor_offset if strategy == "C" else 0.0

    if strategy == "A":
        factor = compute_bias_factor(all_recs, all_actuals)
        engine = CorrectionEngine(
            CorrectionParams(
                effective_from=date(2026, 5, 18),
                bias_factor=factor,
                dow_factors={d: factor for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]},
            )
        )
    else:
        engine = CorrectionEngine.from_training_data(
            all_recs,
            all_actuals,
            picking_regime_start=picking_start,
            picking_regime_factor=picking_factor,
            newsvendor_offset=nv_offset,
        )

    print(f"\nHoldout correction parameters:\n{engine.summary()}\n")

    all_plans = []
    for week in holdout_weeks:
        week_plans = engine.correct_week(week.recommendations)
        all_plans.extend(week_plans)

    # Write output CSV
    if output_path is None:
        output_path = Path("output/holdout_predictions.csv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "planned_operative_person_days"])
        for plan in sorted(all_plans, key=lambda p: p.date):
            writer.writerow([plan.date.isoformat(), f"{plan.planned_operative_person_days:.2f}"])

    print(f"Holdout predictions written to {output_path}")
    print(f"  {len(all_plans)} days predicted")

    return all_plans
