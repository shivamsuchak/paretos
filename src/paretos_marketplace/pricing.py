"""Dynamic pricing engine for work atoms.

Surge factors:
  - Time urgency: atoms posted <24h before start → 1.3×, <4h → 1.5×
  - Skill scarcity: <3 qualified workers available → 1.2×
  - Fill rate: day fill rate <50% → 1.4×
  - Off-peak discount: before 07:00 or after 18:00 → 0.85×

Final price = base × max(surge_factors), capped at 2.0×.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Sequence

from paretos_marketplace.models import WorkAtom, Worker

# Price cap to prevent runaway pricing
MAX_SURGE = 2.0


def compute_urgency_factor(atom: WorkAtom, now: datetime | None = None) -> float:
    """Higher price for last-minute postings."""
    now = now or datetime.now()
    atom_start = datetime.combine(atom.date, atom.start_time)
    hours_until = (atom_start - now).total_seconds() / 3600

    if hours_until < 4:
        return 1.5
    if hours_until < 24:
        return 1.3
    return 1.0


def compute_scarcity_factor(
    atom: WorkAtom, workers: Sequence[Worker]
) -> float:
    """Higher price when few workers have the required skills."""
    required = set(atom.skill_requirements)
    qualified = sum(
        1 for w in workers
        if required.issubset(set(w.skills))
    )
    if qualified < 3:
        return 1.2
    return 1.0


def compute_fill_rate_factor(
    atom: WorkAtom, all_atoms_for_day: Sequence[WorkAtom]
) -> float:
    """Higher price if overall day fill rate is low."""
    if not all_atoms_for_day:
        return 1.0

    total_hc = sum(a.headcount for a in all_atoms_for_day)
    filled_hc = sum(len(a.claimed_by) for a in all_atoms_for_day)
    fill_rate = filled_hc / max(total_hc, 1)

    if fill_rate < 0.5:
        return 1.4
    return 1.0


def compute_off_peak_factor(atom: WorkAtom) -> float:
    """Discount for early morning or late shifts."""
    if atom.start_time < time(7, 0) or atom.start_time >= time(18, 0):
        return 0.85
    return 1.0


def price_atom(
    atom: WorkAtom,
    workers: Sequence[Worker] | None = None,
    all_atoms_for_day: Sequence[WorkAtom] | None = None,
    now: datetime | None = None,
) -> WorkAtom:
    """Apply dynamic pricing to a single atom. Returns updated atom.

    The surge multiplier is the maximum of all applicable factors,
    capped at MAX_SURGE (2.0×).
    """
    factors = [compute_urgency_factor(atom, now)]

    if workers is not None:
        factors.append(compute_scarcity_factor(atom, workers))

    if all_atoms_for_day is not None:
        factors.append(compute_fill_rate_factor(atom, all_atoms_for_day))

    factors.append(compute_off_peak_factor(atom))

    surge = min(max(factors), MAX_SURGE)
    atom.surge_multiplier = round(surge, 2)
    atom.final_price_eur = round(atom.base_price_eur * surge, 2)

    return atom


def price_all_atoms(
    atoms: list[WorkAtom],
    workers: Sequence[Worker] | None = None,
    now: datetime | None = None,
) -> list[WorkAtom]:
    """Apply dynamic pricing to all atoms, using per-day context."""
    # Group atoms by date for fill-rate calculation
    by_date: dict[str, list[WorkAtom]] = {}
    for a in atoms:
        key = str(a.date)
        by_date.setdefault(key, []).append(a)

    for a in atoms:
        day_atoms = by_date.get(str(a.date), [])
        price_atom(a, workers=workers, all_atoms_for_day=day_atoms, now=now)

    return atoms
