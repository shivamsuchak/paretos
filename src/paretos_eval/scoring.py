"""Cost scoring and performance evaluation.

Scores staffing plans against actuals using the asymmetric cost model.
Reports performance against two anchors:
- Baseline: raw optimiser recommendation (doing nothing)
- Perfect: staffing exactly the realised need (unreachable floor)
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from paretos_core.cost_model import CostModel
from paretos_core.schemas import (
    DailyActual,
    DailyRecommendationTotal,
    StaffingPlan,
    CostResult,
)


def score_plans(
    plans: Sequence[StaffingPlan],
    actuals: Sequence[DailyActual],
    cost_model: CostModel,
) -> list[CostResult]:
    """Score a sequence of staffing plans against actuals.

    Returns CostResult for each day where both plan and actual exist.
    """
    actuals_by_date = {a.date: a for a in actuals}
    results = []
    for plan in plans:
        if plan.date in actuals_by_date:
            results.append(cost_model.evaluate_day(plan, actuals_by_date[plan.date]))
    return results


def compute_baseline_cost(
    recommendations: Sequence[DailyRecommendationTotal],
    actuals: Sequence[DailyActual],
    cost_model: CostModel,
) -> list[CostResult]:
    """Compute cost if we just follow the raw optimiser recommendation."""
    plans = [
        StaffingPlan(
            date=r.date,
            planned_operative_person_days=r.total_operative_person_days,
        )
        for r in recommendations
    ]
    return score_plans(plans, actuals, cost_model)


def gap_closure(
    plan_cost: float,
    baseline_cost: float,
    perfect_cost: float = 0.0,
) -> float:
    """Compute the percentage of the baseline→perfect gap that is closed.

    Returns a float in [0, 100] (or >100 if plan beats perfect, which shouldn't happen).
    """
    gap = baseline_cost - perfect_cost
    if gap <= 0:
        return 100.0
    improvement = baseline_cost - plan_cost
    return (improvement / gap) * 100.0


def performance_summary(
    plan_results: list[CostResult],
    baseline_results: list[CostResult],
) -> dict:
    """Generate a performance summary comparing plan vs baseline.

    Returns dict with key metrics.
    """
    plan_total = sum(r.cost for r in plan_results)
    baseline_total = sum(r.cost for r in baseline_results)
    perfect_total = 0.0

    plan_errors = [r.error for r in plan_results]
    baseline_errors = [r.error for r in baseline_results]

    return {
        "n_days": len(plan_results),
        "plan_total_cost": round(plan_total, 2),
        "baseline_total_cost": round(baseline_total, 2),
        "perfect_total_cost": perfect_total,
        "savings_vs_baseline": round(baseline_total - plan_total, 2),
        "savings_pct": round((baseline_total - plan_total) / baseline_total * 100, 1)
        if baseline_total > 0
        else 0.0,
        "gap_closure_pct": round(gap_closure(plan_total, baseline_total), 1),
        "plan_mean_error": round(sum(plan_errors) / len(plan_errors), 2)
        if plan_errors
        else 0.0,
        "baseline_mean_error": round(sum(baseline_errors) / len(baseline_errors), 2)
        if baseline_errors
        else 0.0,
        "plan_days_overstaffed": sum(1 for r in plan_results if r.overstaffed),
        "plan_days_understaffed": sum(1 for r in plan_results if not r.overstaffed),
        "plan_max_understaffing": round(
            min((r.error for r in plan_results), default=0.0), 2
        ),
    }


def format_summary(summary: dict) -> str:
    """Format a performance summary as a human-readable string."""
    lines = [
        "=" * 60,
        "PERFORMANCE SUMMARY",
        "=" * 60,
        f"  Days evaluated:        {summary['n_days']}",
        f"  Baseline cost:         €{summary['baseline_total_cost']:,.0f}",
        f"  Plan cost:             €{summary['plan_total_cost']:,.0f}",
        f"  Savings vs baseline:   €{summary['savings_vs_baseline']:,.0f} "
        f"({summary['savings_pct']}%)",
        f"  Gap closure:           {summary['gap_closure_pct']}%",
        "-" * 60,
        f"  Plan mean error:       {summary['plan_mean_error']:+.2f} person-days",
        f"  Baseline mean error:   {summary['baseline_mean_error']:+.2f} person-days",
        f"  Days overstaffed:      {summary['plan_days_overstaffed']}",
        f"  Days understaffed:     {summary['plan_days_understaffed']}",
        f"  Max understaffing:     {summary['plan_max_understaffing']:.2f} person-days",
        "=" * 60,
    ]
    return "\n".join(lines)
