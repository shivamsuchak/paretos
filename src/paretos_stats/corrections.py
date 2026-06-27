"""Unified correction engine that applies the full correction stack.

Correction order:
1. Regime adjustment (pick-by-light: −27% on picking activity)
2. Day-of-week factors (per-weekday multipliers on adjusted total)
3. Newsvendor offset (additive shift toward understaffing)

Note: We apply regime adjustment BEFORE DoW factors because the regime change
(pick-by-light) affects the base recommendation, and DoW factors should scale
the regime-adjusted total.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from paretos_core.schemas import (
    CorrectionParams,
    DailyActual,
    DailyRecommendationTotal,
    StaffingPlan,
)
from paretos_stats.bias_correction import compute_bias_factor
from paretos_stats.dow_adjustment import compute_dow_factors, _weekday_name


class CorrectionEngine:
    """Applies the full correction stack to produce adjusted staffing plans."""

    def __init__(self, params: CorrectionParams):
        self.params = params

    @classmethod
    def from_training_data(
        cls,
        recommendations: Sequence[DailyRecommendationTotal],
        actuals: Sequence[DailyActual],
        picking_regime_start: date | None = None,
        picking_regime_factor: float | None = None,
        newsvendor_offset: float = 0.0,
    ) -> CorrectionEngine:
        """Calibrate correction parameters from training data.

        This is the primary factory method: it computes bias and DoW factors
        from historical recommendations vs actuals, and accepts regime/newsvendor
        parameters as inputs.
        """
        # Filter to only dates with both recommendations and actuals
        actuals_by_date = {a.date: a for a in actuals}
        matched_recs = [r for r in recommendations if r.date in actuals_by_date]
        matched_actuals = [actuals_by_date[r.date] for r in matched_recs]

        # If we have a regime change, compute factors only from pre-regime data
        # to avoid the regime shift contaminating the base correction
        if picking_regime_start:
            pre_regime_recs = [r for r in matched_recs if r.date < picking_regime_start]
            pre_regime_actuals = [
                actuals_by_date[r.date] for r in pre_regime_recs
            ]
            # Use pre-regime data for bias and DoW if we have enough
            if len(pre_regime_recs) >= 10:
                bias_recs, bias_actuals = pre_regime_recs, pre_regime_actuals
            else:
                bias_recs, bias_actuals = matched_recs, matched_actuals
        else:
            bias_recs, bias_actuals = matched_recs, matched_actuals

        bias_factor = compute_bias_factor(bias_recs, bias_actuals)
        dow_factors = compute_dow_factors(bias_recs, bias_actuals)

        effective_from = min(r.date for r in recommendations) if recommendations else date.today()

        params = CorrectionParams(
            effective_from=effective_from,
            bias_factor=bias_factor,
            dow_factors=dow_factors,
            picking_regime_factor=picking_regime_factor,
            picking_regime_start=picking_regime_start,
            newsvendor_offset=newsvendor_offset,
        )

        return cls(params)

    def correct_day(self, rec: DailyRecommendationTotal) -> StaffingPlan:
        """Apply the full correction stack to a single day's recommendation.

        Steps:
        1. Start with raw operative total
        2. Apply regime adjustment (reduce picking if post-regime)
        3. Apply DoW factor (scale adjusted total by weekday multiplier)
        4. Apply newsvendor offset (additive shift)
        5. Clamp to non-negative
        """
        base = rec.total_operative_person_days

        # Step 1: Regime adjustment (pick-by-light)
        if (
            self.params.picking_regime_factor is not None
            and self.params.picking_regime_start is not None
            and rec.date >= self.params.picking_regime_start
        ):
            picking_rec = rec.by_activity.get("Picking", 0.0)
            # Reduce the picking component
            picking_reduction = picking_rec * (1 - self.params.picking_regime_factor)
            base -= picking_reduction

        # Step 2: Apply bias + DoW as a combined factor
        dow = _weekday_name(rec.date)
        dow_factor = self.params.dow_factors.get(dow, self.params.bias_factor)
        adjusted = base * dow_factor

        # Step 3: Newsvendor offset
        adjusted += self.params.newsvendor_offset

        # Step 4: Clamp
        adjusted = max(0.0, adjusted)

        return StaffingPlan(
            date=rec.date,
            planned_operative_person_days=round(adjusted, 2),
        )

    def correct_week(
        self, recommendations: Sequence[DailyRecommendationTotal]
    ) -> list[StaffingPlan]:
        """Apply corrections to a full week of recommendations."""
        return [self.correct_day(rec) for rec in recommendations]

    def summary(self) -> str:
        """Human-readable summary of correction parameters."""
        p = self.params
        lines = [
            f"Correction Parameters (effective from {p.effective_from}):",
            f"  Bias factor: {p.bias_factor:.4f} ({(p.bias_factor - 1) * 100:+.1f}%)",
            "  DoW factors:",
        ]
        for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            f = p.dow_factors.get(dow, p.bias_factor)
            lines.append(f"    {dow}: {f:.4f} ({(f - 1) * 100:+.1f}%)")

        if p.picking_regime_factor is not None:
            lines.append(
                f"  Picking regime: ×{p.picking_regime_factor:.2f} "
                f"({(p.picking_regime_factor - 1) * 100:+.1f}%) from {p.picking_regime_start}"
            )
        if p.newsvendor_offset != 0:
            lines.append(f"  Newsvendor offset: {p.newsvendor_offset:+.1f} person-days")

        return "\n".join(lines)
