"""Decompose daily staffing plans into 2-hour claimable work atoms."""

from __future__ import annotations

import math
from datetime import date, time
from typing import Sequence

from paretos_marketplace.models import WorkAtom

# Default 2-hour time slots for a warehouse day (06:00–14:00)
DEFAULT_SLOTS: list[tuple[time, time]] = [
    (time(6, 0), time(8, 0)),
    (time(8, 0), time(10, 0)),
    (time(10, 0), time(12, 0)),
    (time(12, 0), time(14, 0)),
]

# Demand distribution across slots (bell-shaped: peak in the middle)
DEFAULT_DEMAND_CURVE: list[float] = [0.20, 0.30, 0.30, 0.20]

# Base cost per person-day from cost model
BASE_COST_PER_PD = 230.0
HOURS_PER_PD = 8.0
HOURS_PER_ATOM = 2.0

# Activity-to-skill mapping
ACTIVITY_SKILLS: dict[str, list[str]] = {
    "Picking": ["picking", "rf_scanner"],
    "Staging": ["staging", "forklift"],
    "Loading": ["loading", "forklift"],
    "Unloading": ["unloading", "forklift"],
    "Receiving": ["receiving", "qc_basic"],
    "Putaway": ["putaway", "forklift", "vna"],
    "Replenishment / relocation": ["replenishment", "forklift", "vna"],
    "Co-Packing line": ["copacking", "packing"],
    "VNA replenishment": ["vna", "forklift"],
    "Returns / QC": ["returns", "qc_basic"],
    "Pick QA": ["picking", "qc_basic"],
    "Transit drivers": ["driving"],
    "Yard shunting": ["driving", "yard"],
    "Team leads": ["leadership"],
    "Aisle maintenance": ["maintenance"],
}


def generate_atoms(
    plan: list[dict],
    slots: list[tuple[time, time]] | None = None,
    demand_curve: list[float] | None = None,
    base_cost_per_pd: float = BASE_COST_PER_PD,
) -> list[WorkAtom]:
    """Generate work atoms from an optimised staffing plan.

    Args:
        plan: List of dicts with keys: date, planned_operative_person_days,
              and optionally by_activity (dict[str, float]).
        slots: Time slot pairs. Defaults to 4 × 2-hour slots (06:00–14:00).
        demand_curve: Distribution weights across slots. Must sum to ~1.0.
        base_cost_per_pd: Base cost per person-day in EUR.

    Returns:
        List of WorkAtom objects.
    """
    slots = slots or DEFAULT_SLOTS
    demand_curve = demand_curve or DEFAULT_DEMAND_CURVE

    if len(slots) != len(demand_curve):
        raise ValueError(f"Slots ({len(slots)}) and demand curve ({len(demand_curve)}) must match")

    # Normalise demand curve
    total_weight = sum(demand_curve)
    demand_curve = [w / total_weight for w in demand_curve]

    base_per_atom = base_cost_per_pd * (HOURS_PER_ATOM / HOURS_PER_PD)  # €57.50

    atoms: list[WorkAtom] = []

    for day in plan:
        day_date = day.get("date")
        if isinstance(day_date, str):
            day_date = date.fromisoformat(day_date)

        total_pd = day.get("planned_operative_person_days", 0)
        by_activity = day.get("by_activity", {})

        if not by_activity:
            # No activity breakdown — treat as single "General" activity
            by_activity = {"General": total_pd}

        for activity, activity_pd in by_activity.items():
            if activity_pd <= 0:
                continue

            skills = ACTIVITY_SKILLS.get(activity, [activity.lower().replace(" ", "_")])

            for slot_idx, (start, end) in enumerate(slots):
                # Distribute this activity's PD across time slots
                slot_pd = activity_pd * demand_curve[slot_idx]

                if slot_pd < 0.05:
                    continue

                # Convert PD fraction to headcount for a 2-hour window
                # 1 pd = 8 hours, so 2hr atom = 0.25 pd per worker
                pd_per_worker = HOURS_PER_ATOM / HOURS_PER_PD
                headcount = max(1, math.ceil(slot_pd / pd_per_worker))

                atom_id = f"atom-{day_date}-{start.strftime('%H%M')}-{activity.lower().replace(' ', '-').replace('/', '-')}"

                atom = WorkAtom(
                    id=atom_id,
                    date=day_date,
                    start_time=start,
                    end_time=end,
                    activity=activity,
                    required_pd=round(slot_pd, 3),
                    headcount=headcount,
                    base_price_eur=round(base_per_atom, 2),
                    surge_multiplier=1.0,
                    final_price_eur=round(base_per_atom, 2),
                    skill_requirements=skills,
                    status="open",
                )
                atoms.append(atom)

    return atoms


def summarise_atoms(atoms: Sequence[WorkAtom]) -> dict:
    """Generate a summary of atom statistics."""
    total = len(atoms)
    by_status = {"open": 0, "claimed": 0, "filled": 0, "expired": 0}
    by_activity: dict[str, int] = {}
    total_headcount = 0
    filled_headcount = 0

    for a in atoms:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_activity[a.activity] = by_activity.get(a.activity, 0) + 1
        total_headcount += a.headcount
        filled_headcount += len(a.claimed_by)

    return {
        "total_atoms": total,
        "by_status": by_status,
        "by_activity": by_activity,
        "total_headcount": total_headcount,
        "filled_headcount": filled_headcount,
        "fill_rate_pct": round(filled_headcount / max(total_headcount, 1) * 100, 1),
    }
