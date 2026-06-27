"""Day-of-week correction factors.

Wednesdays consistently need ~4 fewer person-days than the optimiser recommends.
This module computes and applies per-weekday correction multipliers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Sequence

from paretos_core.schemas import DailyActual, DailyRecommendationTotal

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _weekday_name(d: date) -> str:
    return DOW_NAMES[d.weekday()]


def compute_dow_factors(
    recommendations: Sequence[DailyRecommendationTotal],
    actuals: Sequence[DailyActual],
) -> dict[str, float]:
    """Compute per-weekday correction factors from historical data.

    Returns a dict mapping weekday name → multiplicative factor.
    Factor < 1.0 means the day needs fewer person-days than recommended.
    """
    actuals_by_date = {a.date: a.present_operative_person_days for a in actuals}

    dow_actuals: dict[str, list[float]] = defaultdict(list)
    dow_recs: dict[str, list[float]] = defaultdict(list)

    for rec in recommendations:
        if rec.date in actuals_by_date:
            dow = _weekday_name(rec.date)
            dow_actuals[dow].append(actuals_by_date[rec.date])
            dow_recs[dow].append(rec.total_operative_person_days)

    factors = {}
    for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        if dow_actuals[dow] and dow_recs[dow]:
            mean_actual = sum(dow_actuals[dow]) / len(dow_actuals[dow])
            mean_rec = sum(dow_recs[dow]) / len(dow_recs[dow])
            factors[dow] = mean_actual / mean_rec if mean_rec > 0 else 1.0
        else:
            factors[dow] = 1.0

    return factors


def apply_dow_correction(
    recommendation_total: float,
    day: date,
    dow_factors: dict[str, float],
) -> float:
    """Apply day-of-week correction to a recommendation.

    Args:
        recommendation_total: Raw operative person-day recommendation.
        day: The date (used to determine weekday).
        dow_factors: Per-weekday multiplicative factors.

    Returns:
        Corrected person-days.
    """
    dow = _weekday_name(day)
    factor = dow_factors.get(dow, 1.0)
    return recommendation_total * factor


def dow_factor_summary(dow_factors: dict[str, float]) -> str:
    """Human-readable summary of DoW factors."""
    lines = []
    for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        factor = dow_factors.get(dow, 1.0)
        pct = (factor - 1.0) * 100
        sign = "+" if pct >= 0 else ""
        lines.append(f"  {dow}: {factor:.4f} ({sign}{pct:.1f}%)")
    return "\n".join(lines)
