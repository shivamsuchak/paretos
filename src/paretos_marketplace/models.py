"""Pydantic models for the Micro-Shift Marketplace."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TimeSlot(BaseModel):
    """A worker availability window."""

    date: date
    start: time
    end: time


class WorkAtom(BaseModel):
    """A 2-hour claimable unit of warehouse work."""

    id: str = Field(default_factory=lambda: f"atom-{uuid.uuid4().hex[:8]}")
    date: date
    start_time: time
    end_time: time
    activity: str
    required_pd: float = Field(description="Person-days needed for this atom")
    headcount: int = Field(description="Number of workers needed")
    base_price_eur: float = Field(description="Base rate per worker (EUR)")
    surge_multiplier: float = Field(default=1.0)
    final_price_eur: float = Field(description="base × surge per worker")
    skill_requirements: list[str] = Field(default_factory=list)
    status: Literal["open", "claimed", "filled", "expired"] = "open"
    claimed_by: list[str] = Field(default_factory=list, description="Worker IDs")

    @property
    def remaining_headcount(self) -> int:
        return max(0, self.headcount - len(self.claimed_by))


class Worker(BaseModel):
    """A warehouse worker available for micro-shifts."""

    id: str = Field(default_factory=lambda: f"w-{uuid.uuid4().hex[:6]}")
    name: str
    skills: list[str] = Field(default_factory=list)
    availability: list[TimeSlot] = Field(default_factory=list)
    max_daily_hours: float = Field(default=10.0, description="Legal limit (ArbZG)")
    min_rest_hours: float = Field(default=11.0, description="Min rest between shifts (ArbZG)")
    current_atoms: list[str] = Field(default_factory=list, description="Claimed atom IDs")
    productivity_rating: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="0-1 rating, 0.7 default for new temps"
    )
    tier: Literal["experienced", "standard", "new"] = "standard"


class Claim(BaseModel):
    """A worker's claim on a work atom."""

    id: str = Field(default_factory=lambda: f"claim-{uuid.uuid4().hex[:8]}")
    atom_id: str
    worker_id: str
    claimed_at: datetime = Field(default_factory=datetime.now)
    status: Literal["pending", "confirmed", "cancelled"] = "pending"


class ShiftComposition(BaseModel):
    """A composed legal shift from multiple atoms for one worker on one day."""

    worker_id: str
    worker_name: str = ""
    date: date
    atoms: list[WorkAtom] = Field(default_factory=list)
    total_hours: float = 0.0
    break_required: bool = Field(default=False, description="Required after 6h (ArbZG)")
    break_scheduled: bool = False
    total_pay_eur: float = 0.0
    legal_valid: bool = True
    violations: list[str] = Field(default_factory=list)


class MarketplaceSummary(BaseModel):
    """Dashboard summary for marketplace state."""

    date: date
    total_atoms: int = 0
    open_atoms: int = 0
    claimed_atoms: int = 0
    filled_atoms: int = 0
    fill_rate_pct: float = 0.0
    total_headcount_needed: int = 0
    total_headcount_filled: int = 0
    total_revenue_eur: float = 0.0
    activities: dict[str, int] = Field(default_factory=dict)
