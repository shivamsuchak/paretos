"""Asymmetric cost model for warehouse staffing decisions.

Implements the scoring function from cost_model.json:
- Overstaffing: €230 per surplus person-day (idle wage)
- Understaffing: €41.40 per short person-day (18% overtime premium)
  + €600 per short person-day beyond SLA tolerance (2.0 pd)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Sequence

from paretos_core.exceptions import CostModelError
from paretos_core.schemas import CostResult, StaffingPlan, DailyActual, WeeklyCostSummary


class CostModel:
    """Asymmetric cost function for staffing decisions."""

    def __init__(
        self,
        overstaffing_cost: float = 230.0,
        overtime_premium_pct: float = 18.0,
        sla_tolerance_pd: float = 2.0,
        sla_penalty_per_pd: float = 600.0,
        regular_cost_per_pd: float = 230.0,
    ):
        self.overstaffing_cost = overstaffing_cost
        self.overtime_premium_pct = overtime_premium_pct
        self.overtime_cost_per_pd = regular_cost_per_pd * (overtime_premium_pct / 100.0)
        self.sla_tolerance_pd = sla_tolerance_pd
        self.sla_penalty_per_pd = sla_penalty_per_pd

    @classmethod
    def from_json(cls, path: Path) -> CostModel:
        """Load cost model from the dataset's cost_model.json."""
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise CostModelError(f"Failed to load cost model from {path}: {e}") from e

        return cls(
            overstaffing_cost=data["overstaffing"]["idle_cost_per_person_day"],
            overtime_premium_pct=data["understaffing"]["overtime_premium_pct"],
            sla_tolerance_pd=data["understaffing"]["sla_tolerance_person_days"],
            sla_penalty_per_pd=data["understaffing"]["sla_penalty_per_person_day"],
            regular_cost_per_pd=data["regular_cost_per_person_day"],
        )

    def compute_daily_cost(self, planned: float, actual: float) -> float:
        """Compute the excess cost of a staffing decision vs perfect knowledge.

        Args:
            planned: Planned operative person-days.
            actual: Actual operative person-days needed.

        Returns:
            Cost in EUR (always >= 0). Zero means planned == actual.
        """
        if planned < 0 or actual < 0:
            raise CostModelError(
                f"Person-days cannot be negative: planned={planned}, actual={actual}"
            )

        if planned >= actual:
            # Overstaffed: surplus is idle
            return (planned - actual) * self.overstaffing_cost
        else:
            # Understaffed: shortfall covered by overtime + potential SLA penalty
            shortfall = actual - planned
            if shortfall <= self.sla_tolerance_pd:
                return shortfall * self.overtime_cost_per_pd
            else:
                within_tolerance = self.sla_tolerance_pd * self.overtime_cost_per_pd
                beyond_tolerance = (shortfall - self.sla_tolerance_pd) * self.sla_penalty_per_pd
                return within_tolerance + beyond_tolerance

    def evaluate_day(self, plan: StaffingPlan, actual: DailyActual) -> CostResult:
        """Evaluate a single day's staffing plan against actuals."""
        if plan.date != actual.date:
            raise CostModelError(
                f"Date mismatch: plan={plan.date}, actual={actual.date}"
            )
        planned = plan.planned_operative_person_days
        actual_pd = actual.present_operative_person_days
        cost = self.compute_daily_cost(planned, actual_pd)
        error = planned - actual_pd

        return CostResult(
            date=plan.date,
            planned=planned,
            actual=actual_pd,
            error=error,
            cost=cost,
            overstaffed=planned >= actual_pd,
        )

    def evaluate_week(
        self,
        plans: Sequence[StaffingPlan],
        actuals: Sequence[DailyActual],
        decision_date: date,
        planned_week_start: date,
    ) -> WeeklyCostSummary:
        """Evaluate a full week of staffing plans against actuals."""
        actuals_by_date = {a.date: a for a in actuals}
        daily_costs = []

        for plan in plans:
            if plan.date not in actuals_by_date:
                continue
            daily_costs.append(self.evaluate_day(plan, actuals_by_date[plan.date]))

        if not daily_costs:
            raise CostModelError("No matching plan/actual pairs found for the week")

        return WeeklyCostSummary(
            decision_date=decision_date,
            planned_week_start=planned_week_start,
            daily_costs=daily_costs,
            total_cost=sum(c.cost for c in daily_costs),
            mean_error=sum(c.error for c in daily_costs) / len(daily_costs),
            days_overstaffed=sum(1 for c in daily_costs if c.overstaffed),
            days_understaffed=sum(1 for c in daily_costs if not c.overstaffed),
        )

    def __repr__(self) -> str:
        return (
            f"CostModel(over=€{self.overstaffing_cost}/pd, "
            f"under=€{self.overtime_cost_per_pd:.1f}/pd, "
            f"sla_tol={self.sla_tolerance_pd}pd, "
            f"sla_pen=€{self.sla_penalty_per_pd}/pd)"
        )
