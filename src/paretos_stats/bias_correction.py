"""Systematic bias correction for the optimiser's recommendations.

The optimiser overstaffs by ~+19.5% due to a stale rate card. A flat multiplicative
correction (−16.3%) captures 92% of available savings.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from paretos_core.schemas import DailyActual, DailyRecommendationTotal


def compute_bias_factor(
    recommendations: Sequence[DailyRecommendationTotal],
    actuals: Sequence[DailyActual],
) -> float:
    """Compute the optimal flat bias correction factor from historical data.

    Returns a multiplicative factor (e.g., 0.837 for −16.3% trim).
    Uses only dates present in both recommendations and actuals.
    """
    actuals_by_date = {a.date: a.present_operative_person_days for a in actuals}

    rec_values = []
    actual_values = []
    for rec in recommendations:
        if rec.date in actuals_by_date:
            rec_values.append(rec.total_operative_person_days)
            actual_values.append(actuals_by_date[rec.date])

    if not rec_values:
        return 1.0  # No data — no correction

    mean_rec = sum(rec_values) / len(rec_values)
    mean_actual = sum(actual_values) / len(actual_values)

    if mean_rec == 0:
        return 1.0

    return mean_actual / mean_rec


def compute_bias_stats(
    recommendations: Sequence[DailyRecommendationTotal],
    actuals: Sequence[DailyActual],
) -> dict:
    """Compute detailed bias statistics."""
    actuals_by_date = {a.date: a.present_operative_person_days for a in actuals}

    errors = []
    for rec in recommendations:
        if rec.date in actuals_by_date:
            error = rec.total_operative_person_days - actuals_by_date[rec.date]
            errors.append(error)

    if not errors:
        return {"n": 0}

    mean_error = sum(errors) / len(errors)
    overstaffed_count = sum(1 for e in errors if e > 0)

    return {
        "n": len(errors),
        "mean_error": mean_error,
        "min_error": min(errors),
        "max_error": max(errors),
        "overstaffed_pct": overstaffed_count / len(errors) * 100,
        "bias_factor": compute_bias_factor(
            [r for r in recommendations if r.date in actuals_by_date],
            [a for a in actuals if a.date in {r.date for r in recommendations}],
        ),
    }


def apply_bias_correction(
    recommendation_total: float,
    bias_factor: float,
) -> float:
    """Apply a flat multiplicative bias correction.

    Args:
        recommendation_total: Raw operative person-day recommendation.
        bias_factor: Multiplicative factor (e.g., 0.837).

    Returns:
        Corrected person-days.
    """
    return recommendation_total * bias_factor
