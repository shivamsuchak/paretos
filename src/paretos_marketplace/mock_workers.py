"""Generate a pool of 50 synthetic workers with varied skills and tiers."""

from __future__ import annotations

import random
from datetime import date, time, timedelta

from paretos_marketplace.models import TimeSlot, Worker

# Typical warehouse skill sets
SKILL_POOLS = {
    "experienced": {
        "skills": ["picking", "rf_scanner", "staging", "forklift", "loading",
                    "unloading", "receiving", "qc_basic", "putaway", "replenishment"],
        "productivity_range": (0.85, 0.98),
        "max_skills": 8,
        "min_skills": 5,
    },
    "standard": {
        "skills": ["picking", "rf_scanner", "staging", "loading", "unloading",
                    "receiving", "packing", "copacking"],
        "productivity_range": (0.60, 0.84),
        "max_skills": 5,
        "min_skills": 3,
    },
    "new": {
        "skills": ["picking", "rf_scanner", "packing", "copacking", "loading"],
        "productivity_range": (0.40, 0.65),
        "max_skills": 3,
        "min_skills": 1,
    },
}

FIRST_NAMES = [
    "Max", "Lukas", "Leon", "Finn", "Noah", "Paul", "Ben", "Elias", "Jonas", "Louis",
    "Anna", "Mia", "Emma", "Hannah", "Sophia", "Lena", "Marie", "Clara", "Laura", "Lea",
    "Ali", "Mehmet", "Yusuf", "Fatma", "Zeynep", "Emre", "Selin", "Hassan", "Amira", "Omar",
    "Piotr", "Katarzyna", "Marta", "Jan", "Agnieszka", "Tomasz", "Ewa", "Krzysztof",
    "Ivan", "Natalia", "Dmitri", "Olena", "Sergei", "Tatiana", "Andrei",
    "Carlos", "Maria", "João", "Ana", "Pedro",
]

LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Koch", "Bauer", "Richter", "Klein",
    "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun",
    "Yilmaz", "Kaya", "Kowalski", "Nowak", "Petrov", "Silva", "Santos",
]


def generate_availability(
    worker_date: date,
    n_days: int = 5,
) -> list[TimeSlot]:
    """Generate random availability for a worker across the week."""
    slots = []
    for d in range(n_days):
        day = worker_date + timedelta(days=d)
        # 70% chance of being available on any given day
        if random.random() < 0.70:
            # Random start between 06:00 and 10:00
            start_hour = random.choice([6, 7, 8, 9, 10])
            # Random duration 4-10 hours
            duration = random.choice([4, 6, 8, 10])
            end_hour = min(start_hour + duration, 20)
            slots.append(TimeSlot(
                date=day,
                start=time(start_hour, 0),
                end=time(end_hour, 0),
            ))
    return slots


def generate_mock_workers(
    n: int = 50,
    week_start: date | None = None,
    seed: int | None = 42,
) -> list[Worker]:
    """Generate n synthetic workers.

    Distribution: ~20% experienced, ~50% standard, ~30% new.
    """
    if seed is not None:
        random.seed(seed)

    week_start = week_start or date.today()
    workers: list[Worker] = []

    tier_distribution = (
        [("experienced", SKILL_POOLS["experienced"])] * int(n * 0.20)
        + [("standard", SKILL_POOLS["standard"])] * int(n * 0.50)
        + [("new", SKILL_POOLS["new"])] * int(n * 0.30)
    )

    # Pad to exactly n
    while len(tier_distribution) < n:
        tier_distribution.append(("standard", SKILL_POOLS["standard"]))

    random.shuffle(tier_distribution)

    used_names: set[str] = set()
    for i, (tier, pool) in enumerate(tier_distribution):
        # Unique name
        while True:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break

        n_skills = random.randint(pool["min_skills"], pool["max_skills"])
        skills = random.sample(pool["skills"], min(n_skills, len(pool["skills"])))

        prod_lo, prod_hi = pool["productivity_range"]
        productivity = round(random.uniform(prod_lo, prod_hi), 2)

        availability = generate_availability(week_start, n_days=5)

        worker = Worker(
            id=f"w-{i+1:03d}",
            name=name,
            skills=skills,
            availability=availability,
            productivity_rating=productivity,
            tier=tier,
        )
        workers.append(worker)

    return workers
