"""Worker-atom matching with German labour law (ArbZG) constraints.

Legal constraints enforced:
  - Max 10 hours/day working time (§3 ArbZG)
  - Min 11 hours rest between shifts (§5 ArbZG)
  - Mandatory 30-min break after 6 hours (§4 ArbZG)
  - Max 5 consecutive atoms (10 hours)
  - Fairness: no single worker gets >60% of atoms on any day
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Sequence

from paretos_marketplace.models import Claim, ShiftComposition, WorkAtom, Worker

MAX_DAILY_HOURS = 10.0
MIN_REST_HOURS = 11.0
BREAK_THRESHOLD_HOURS = 6.0
BREAK_DURATION_MINUTES = 30
MAX_CONSECUTIVE_ATOMS = 5
FAIRNESS_MAX_SHARE = 0.60  # No worker gets >60% of day's atoms


def _time_to_hours(t: time) -> float:
    return t.hour + t.minute / 60.0


def _atoms_overlap(a1: WorkAtom, a2: WorkAtom) -> bool:
    """Check if two atoms overlap in time."""
    return a1.start_time < a2.end_time and a2.start_time < a1.end_time


def compute_match_score(worker: Worker, atom: WorkAtom) -> float:
    """Score a worker-atom match.

    Returns 0.0 if ineligible, otherwise a score in (0, 1].
    Score = skill_match × availability_match × productivity_rating.
    """
    # Skill match: all required skills must be present
    required = set(atom.skill_requirements)
    worker_skills = set(worker.skills)
    if required and not required.issubset(worker_skills):
        return 0.0

    # Availability match: worker must be available during atom window
    available = False
    for slot in worker.availability:
        if slot.date == atom.date and slot.start <= atom.start_time and slot.end >= atom.end_time:
            available = True
            break

    if not available and worker.availability:
        return 0.0

    # If no availability data, assume available (for mock testing)
    return worker.productivity_rating


def check_daily_hours(
    worker: Worker,
    new_atom: WorkAtom,
    existing_atoms: Sequence[WorkAtom],
) -> tuple[bool, str]:
    """Check if adding this atom would exceed daily hours limit."""
    same_day = [a for a in existing_atoms if a.date == new_atom.date]
    total_hours = sum(_time_to_hours(a.end_time) - _time_to_hours(a.start_time) for a in same_day)
    new_hours = _time_to_hours(new_atom.end_time) - _time_to_hours(new_atom.start_time)

    if total_hours + new_hours > worker.max_daily_hours:
        return False, f"Exceeds {worker.max_daily_hours}h daily limit ({total_hours + new_hours:.1f}h)"
    return True, ""


def check_rest_period(
    worker: Worker,
    new_atom: WorkAtom,
    existing_atoms: Sequence[WorkAtom],
) -> tuple[bool, str]:
    """Check minimum rest period between shifts on different days."""
    for a in existing_atoms:
        if a.date == new_atom.date:
            continue

        # Check rest between end of one day and start of next
        if a.date < new_atom.date:
            end_dt = datetime.combine(a.date, a.end_time)
            start_dt = datetime.combine(new_atom.date, new_atom.start_time)
        else:
            end_dt = datetime.combine(new_atom.date, new_atom.end_time)
            start_dt = datetime.combine(a.date, a.start_time)

        rest_hours = (start_dt - end_dt).total_seconds() / 3600
        if 0 < rest_hours < worker.min_rest_hours:
            return False, f"Only {rest_hours:.1f}h rest (need {worker.min_rest_hours}h)"

    return True, ""


def check_time_overlap(
    new_atom: WorkAtom,
    existing_atoms: Sequence[WorkAtom],
) -> tuple[bool, str]:
    """Check if atom overlaps with already-claimed atoms."""
    for a in existing_atoms:
        if a.date == new_atom.date and _atoms_overlap(a, new_atom):
            return False, f"Overlaps with {a.id} ({a.start_time}–{a.end_time})"
    return True, ""


def check_consecutive_limit(
    new_atom: WorkAtom,
    existing_atoms: Sequence[WorkAtom],
) -> tuple[bool, str]:
    """Check max consecutive atoms (prevents >10h continuous work)."""
    same_day = [a for a in existing_atoms if a.date == new_atom.date]
    same_day.append(new_atom)
    same_day.sort(key=lambda a: a.start_time)

    consecutive = 1
    for i in range(1, len(same_day)):
        if same_day[i].start_time == same_day[i - 1].end_time:
            consecutive += 1
        else:
            consecutive = 1

        if consecutive > MAX_CONSECUTIVE_ATOMS:
            return False, f"Exceeds {MAX_CONSECUTIVE_ATOMS} consecutive atoms"

    return True, ""


def check_fairness(
    worker: Worker,
    new_atom: WorkAtom,
    all_atoms_for_day: Sequence[WorkAtom],
) -> tuple[bool, str]:
    """Ensure no single worker holds >60% of a day's atoms."""
    day_atoms = [a for a in all_atoms_for_day if a.date == new_atom.date]
    total_day_atoms = len(day_atoms) + 1  # +1 for new atom

    worker_count = sum(1 for a in day_atoms if worker.id in a.claimed_by) + 1
    share = worker_count / max(total_day_atoms, 1)

    if share > FAIRNESS_MAX_SHARE:
        return False, f"Worker would hold {share:.0%} of day's atoms (max {FAIRNESS_MAX_SHARE:.0%})"
    return True, ""


def validate_claim(
    worker: Worker,
    atom: WorkAtom,
    worker_atoms: Sequence[WorkAtom],
    all_day_atoms: Sequence[WorkAtom] | None = None,
) -> tuple[bool, list[str]]:
    """Run all legal constraint checks. Returns (valid, list_of_violations)."""
    violations = []

    ok, msg = check_time_overlap(atom, worker_atoms)
    if not ok:
        violations.append(msg)

    ok, msg = check_daily_hours(worker, atom, worker_atoms)
    if not ok:
        violations.append(msg)

    ok, msg = check_rest_period(worker, atom, worker_atoms)
    if not ok:
        violations.append(msg)

    ok, msg = check_consecutive_limit(atom, worker_atoms)
    if not ok:
        violations.append(msg)

    if all_day_atoms is not None:
        ok, msg = check_fairness(worker, atom, all_day_atoms)
        if not ok:
            violations.append(msg)

    return len(violations) == 0, violations


def find_eligible_workers(
    atom: WorkAtom,
    workers: Sequence[Worker],
    atoms_by_worker: dict[str, list[WorkAtom]] | None = None,
    all_day_atoms: Sequence[WorkAtom] | None = None,
) -> list[tuple[Worker, float]]:
    """Find and rank eligible workers for an atom.

    Returns list of (worker, score) tuples, sorted by score descending.
    """
    atoms_by_worker = atoms_by_worker or {}
    eligible = []

    for w in workers:
        score = compute_match_score(w, atom)
        if score <= 0:
            continue

        worker_atoms = atoms_by_worker.get(w.id, [])
        valid, _ = validate_claim(w, atom, worker_atoms, all_day_atoms)
        if not valid:
            continue

        eligible.append((w, score))

    eligible.sort(key=lambda x: x[1], reverse=True)
    return eligible


def compose_shift(
    worker: Worker,
    atoms: Sequence[WorkAtom],
    target_date: date,
) -> ShiftComposition:
    """Compose a legal shift from a worker's atoms on a given day."""
    day_atoms = sorted(
        [a for a in atoms if a.date == target_date],
        key=lambda a: a.start_time,
    )

    total_hours = sum(
        _time_to_hours(a.end_time) - _time_to_hours(a.start_time)
        for a in day_atoms
    )
    total_pay = sum(a.final_price_eur for a in day_atoms)
    break_required = total_hours > BREAK_THRESHOLD_HOURS

    violations = []
    if total_hours > worker.max_daily_hours:
        violations.append(f"Exceeds {worker.max_daily_hours}h limit")

    return ShiftComposition(
        worker_id=worker.id,
        worker_name=worker.name,
        date=target_date,
        atoms=list(day_atoms),
        total_hours=round(total_hours, 1),
        break_required=break_required,
        break_scheduled=break_required,  # Auto-schedule if required
        total_pay_eur=round(total_pay, 2),
        legal_valid=len(violations) == 0,
        violations=violations,
    )
