"""Pydantic models for all data structures crossing module boundaries."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DailyActual(BaseModel):
    """One day's actual staffing data."""

    date: date
    present_total_person_days: float
    present_operative_person_days: float

    @field_validator("present_operative_person_days")
    @classmethod
    def operative_nonneg(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Operative person-days cannot be negative: {v}")
        return v


class DailyRecommendation(BaseModel):
    """One activity's recommendation for one day."""

    decision_date: date
    planned_week_start: date
    date: date
    activity: str
    group: str
    recommended_person_days: float


class DailyRecommendationTotal(BaseModel):
    """Aggregated operative recommendation for one day."""

    date: date
    decision_date: date
    planned_week_start: date
    total_operative_person_days: float
    by_activity: dict[str, float] = Field(default_factory=dict)


class DailyVolume(BaseModel):
    """One day's volume data (forecast and realised)."""

    date: date
    picks_forecast: int
    picks_realized: int
    outbound_forecast: int
    outbound_realized: int
    inbound_forecast: int
    inbound_realized: int


class StaffingPlan(BaseModel):
    """A single day's committed staffing plan (the decision output)."""

    date: date
    planned_operative_person_days: float

    @field_validator("planned_operative_person_days")
    @classmethod
    def planned_nonneg(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Planned person-days cannot be negative: {v}")
        return v


class WeeklyData(BaseModel):
    """All data for one weekly cycle (decision Tuesday → following Mon–Fri)."""

    decision_date: date
    planned_week_start: date
    recommendations: list[DailyRecommendationTotal]
    actuals: Optional[list[DailyActual]] = None
    volumes: Optional[list[DailyVolume]] = None


class CorrectionParams(BaseModel):
    """Versioned correction parameters applied by the Planning Agent."""

    version: int = 1
    effective_from: date
    bias_factor: float = Field(
        description="Multiplicative bias correction (e.g., 0.837 for -16.3%)"
    )
    dow_factors: dict[str, float] = Field(
        default_factory=lambda: {
            "Mon": 1.0,
            "Tue": 1.0,
            "Wed": 1.0,
            "Thu": 1.0,
            "Fri": 1.0,
        },
        description="Day-of-week multipliers applied to recommendation",
    )
    picking_regime_factor: Optional[float] = Field(
        default=None,
        description="Picking reduction factor for post-regime-change (e.g., 0.73 for -27%)",
    )
    picking_regime_start: Optional[date] = Field(
        default=None,
        description="Date from which picking regime factor applies",
    )
    newsvendor_offset: float = Field(
        default=0.0,
        description="Additive offset in person-days (negative = lean toward understaffing)",
    )


class CostResult(BaseModel):
    """Cost evaluation result for a single day."""

    date: date
    planned: float
    actual: float
    error: float = Field(description="planned - actual (positive = overstaffed)")
    cost: float = Field(description="Asymmetric cost in EUR")
    overstaffed: bool


class WeeklyCostSummary(BaseModel):
    """Cost summary for one weekly cycle."""

    decision_date: date
    planned_week_start: date
    daily_costs: list[CostResult]
    total_cost: float
    mean_error: float
    days_overstaffed: int
    days_understaffed: int


class DecisionLogEntry(BaseModel):
    """One planner note from the decision log."""

    id: str
    captured_on: date
    author: str
    scope: str | list[str]
    note: str
    claimed_effect: dict
