"""
Build a normalized SQLite database from the Paretos warehouse staffing data.

Tables created:
  1. activities           – lookup for activity names & groups
  2. daily_actuals        – actual staffing per day (present_long.csv + raw actuals)
  3. daily_volumes        – forecast vs realized volumes (volumes_long.csv + raw actuals)
  4. recommendations      – per-activity per-day staffing recommendations
  5. cost_model           – single-row cost/scoring parameters
  6. decision_log_authors – planner author lookup
  7. decision_log         – planner notes / institutional memory
"""

import csv
import json
import sqlite3
import os
import re
import glob
from datetime import datetime, timedelta
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(os.path.dirname(__file__), "paretos.db")


# ── helpers ──────────────────────────────────────────────────────────────────

def parse_german_decimal(val: str) -> Optional[float]:
    """Convert '12,5' → 12.5 or return None for empty/invalid."""
    val = val.strip().strip('"')
    if not val:
        return None
    return float(val.replace(",", "."))


def parse_german_date(val: str) -> Optional[str]:
    """Convert 'DD.MM.YYYY' → 'YYYY-MM-DD'."""
    val = val.strip().strip('"')
    if not val:
        return None
    parts = val.split(".")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return val  # already ISO


def parse_mixed_date(val: str) -> Optional[str]:
    """Parse date strings from volumes actuals which mix German/English formats."""
    val = val.strip().strip('"')
    if not val:
        return None
    # Try German: "Montag, 18. Mai 2026"
    german_months = {
        "Januar": 1, "Februar": 2, "März": 3, "April": 4,
        "Mai": 5, "Juni": 6, "Juli": 7, "August": 8,
        "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
    }
    english_months = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }
    # Pattern: "Weekday, DD. Month YYYY" (German)
    m = re.match(r"[A-Za-zäöüÄÖÜ]+,\s+(\d+)\.\s+(\w+)\s+(\d{4})", val)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = german_months.get(month_name) or english_months.get(month_name)
        if month:
            return f"{year}-{month:02d}-{day:02d}"
    # Pattern: "Weekday, Month DD, YYYY" (English)
    m = re.match(r"[A-Za-z]+,\s+(\w+)\s+(\d+),\s+(\d{4})", val)
    if m:
        month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        month = english_months.get(month_name) or german_months.get(month_name)
        if month:
            return f"{year}-{month:02d}-{day:02d}"
    # Fallback: DD.MM.YYYY
    return parse_german_date(val)


def week_start_from_filename(fname: str) -> str:
    """Extract YYYY-MM-DD from filename like 'present_2026-05-18.csv'."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
    return m.group(1) if m else ""


# ── schema ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    activity_group  TEXT    NOT NULL CHECK(activity_group IN ('operative', 'admin'))
);

CREATE TABLE IF NOT EXISTS daily_actuals (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    date                        TEXT    NOT NULL,
    week_start                  TEXT,
    present_total_person_days   REAL    NOT NULL,
    present_operative_person_days REAL  NOT NULL,
    UNIQUE(date)
);

CREATE TABLE IF NOT EXISTS daily_volumes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT    NOT NULL,
    week_start          TEXT,
    picks_forecast      INTEGER,
    picks_realized      INTEGER,
    outbound_forecast   INTEGER,
    outbound_realized   INTEGER,
    inbound_forecast    INTEGER,
    inbound_realized    INTEGER,
    UNIQUE(date)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_date           TEXT    NOT NULL,
    planned_week_start      TEXT    NOT NULL,
    date                    TEXT    NOT NULL,
    activity_id             INTEGER NOT NULL REFERENCES activities(id),
    recommended_person_days REAL    NOT NULL,
    UNIQUE(decision_date, date, activity_id)
);

CREATE TABLE IF NOT EXISTS cost_model (
    id                              INTEGER PRIMARY KEY CHECK(id = 1),
    currency                        TEXT    NOT NULL,
    regular_cost_per_person_day     REAL    NOT NULL,
    overstaffing_idle_cost          REAL    NOT NULL,
    understaffing_overtime_pct      REAL    NOT NULL,
    understaffing_sla_tolerance_pd  REAL    NOT NULL,
    understaffing_sla_penalty       REAL    NOT NULL,
    scoring_note                    TEXT
);

CREATE TABLE IF NOT EXISTS decision_log_authors (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL UNIQUE,
    role    TEXT
);

CREATE TABLE IF NOT EXISTS decision_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        TEXT    NOT NULL UNIQUE,
    captured_on     TEXT    NOT NULL,
    author_id       INTEGER NOT NULL REFERENCES decision_log_authors(id),
    scope           TEXT,
    note            TEXT    NOT NULL,
    claimed_effect  TEXT
);

CREATE INDEX IF NOT EXISTS idx_actuals_date ON daily_actuals(date);
CREATE INDEX IF NOT EXISTS idx_volumes_date ON daily_volumes(date);
CREATE INDEX IF NOT EXISTS idx_recommendations_date ON recommendations(date);
CREATE INDEX IF NOT EXISTS idx_recommendations_decision_date ON recommendations(decision_date);
CREATE INDEX IF NOT EXISTS idx_decision_log_captured ON decision_log(captured_on);
"""


# ── loaders ──────────────────────────────────────────────────────────────────

def load_activities(cur: sqlite3.Cursor):
    """Seed activity lookup from the clean recommendations CSV."""
    path = os.path.join(DATA_DIR, "clean", "recommendations_long.csv")
    seen = set()
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["activity"], row["group"])
            if key not in seen:
                seen.add(key)
                cur.execute(
                    "INSERT OR IGNORE INTO activities (name, activity_group) VALUES (?, ?)",
                    (row["activity"], row["group"]),
                )
    print(f"  ✓ {len(seen)} activities loaded")


def load_daily_actuals_clean(cur: sqlite3.Cursor):
    """Load from data/clean/present_long.csv."""
    path = os.path.join(DATA_DIR, "clean", "present_long.csv")
    count = 0
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                """INSERT OR IGNORE INTO daily_actuals
                   (date, present_total_person_days, present_operative_person_days)
                   VALUES (?, ?, ?)""",
                (row["date"],
                 float(row["present_total_person_days"]),
                 float(row["present_operative_person_days"])),
            )
            count += 1
    print(f"  ✓ {count} daily_actuals rows (clean)")


def load_daily_actuals_raw(cur: sqlite3.Cursor):
    """Load from data/actuals/present_*.csv (German format, semicolon-delimited)."""
    pattern = os.path.join(DATA_DIR, "actuals", "present_*.csv")
    count = 0
    for fpath in sorted(glob.glob(pattern)):
        week_start = week_start_from_filename(os.path.basename(fpath))
        with open(fpath) as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if not row or not row[0].strip().strip('"'):
                    continue
                date = parse_german_date(row[0])
                total = parse_german_decimal(row[1]) if len(row) > 1 else None
                if date and total is not None:
                    operative = total - 8.0
                    cur.execute(
                        """INSERT OR IGNORE INTO daily_actuals
                           (date, week_start, present_total_person_days, present_operative_person_days)
                           VALUES (?, ?, ?, ?)""",
                        (date, week_start, total, operative),
                    )
                    # Update week_start if row already existed
                    cur.execute(
                        "UPDATE daily_actuals SET week_start = ? WHERE date = ? AND week_start IS NULL",
                        (week_start, date),
                    )
                    count += 1
    print(f"  ✓ {count} daily_actuals rows processed (raw)")


def load_daily_volumes_clean(cur: sqlite3.Cursor):
    """Load from data/clean/volumes_long.csv."""
    path = os.path.join(DATA_DIR, "clean", "volumes_long.csv")
    count = 0
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                """INSERT OR IGNORE INTO daily_volumes
                   (date, picks_forecast, picks_realized,
                    outbound_forecast, outbound_realized,
                    inbound_forecast, inbound_realized)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row["date"],
                 int(row["picks_forecast"]), int(row["picks_realized"]),
                 int(row["outbound_forecast"]), int(row["outbound_realized"]),
                 int(row["inbound_forecast"]), int(row["inbound_realized"])),
            )
            count += 1
    print(f"  ✓ {count} daily_volumes rows (clean)")


def load_daily_volumes_raw(cur: sqlite3.Cursor):
    """Load from data/actuals/volumes_*.csv (mixed German/English date formats)."""
    pattern = os.path.join(DATA_DIR, "actuals", "volumes_*.csv")
    count = 0
    for fpath in sorted(glob.glob(pattern)):
        week_start = week_start_from_filename(os.path.basename(fpath))
        with open(fpath) as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if not row or not row[0].strip().strip('"'):
                    continue
                date = parse_mixed_date(row[0])
                if date:
                    picks = int(row[1].strip().strip('"')) if len(row) > 1 and row[1].strip().strip('"') else None
                    outbound = int(row[2].strip().strip('"')) if len(row) > 2 and row[2].strip().strip('"') else None
                    inbound = None  # raw volumes files don't have inbound
                    # Update existing row with realized data or set week_start
                    cur.execute(
                        "UPDATE daily_volumes SET week_start = ? WHERE date = ? AND week_start IS NULL",
                        (week_start, date),
                    )
                    count += 1
    print(f"  ✓ {count} daily_volumes rows processed (raw)")


def load_recommendations_clean(cur: sqlite3.Cursor):
    """Load from data/clean/recommendations_long.csv."""
    path = os.path.join(DATA_DIR, "clean", "recommendations_long.csv")
    # Build activity name → id map
    cur.execute("SELECT id, name FROM activities")
    act_map = {name: aid for aid, name in cur.fetchall()}

    count = 0
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            activity_id = act_map.get(row["activity"])
            if activity_id is None:
                print(f"    ⚠ Unknown activity: {row['activity']}")
                continue
            cur.execute(
                """INSERT OR IGNORE INTO recommendations
                   (decision_date, planned_week_start, date, activity_id, recommended_person_days)
                   VALUES (?, ?, ?, ?, ?)""",
                (row["decision_date"], row["planned_week_start"], row["date"],
                 activity_id, float(row["recommended_person_days"])),
            )
            count += 1
    print(f"  ✓ {count} recommendations rows (clean)")


def load_cost_model(cur: sqlite3.Cursor):
    """Load from data/cost_model.json."""
    path = os.path.join(DATA_DIR, "cost_model.json")
    with open(path) as f:
        cm = json.load(f)
    cur.execute(
        """INSERT OR REPLACE INTO cost_model
           (id, currency, regular_cost_per_person_day, overstaffing_idle_cost,
            understaffing_overtime_pct, understaffing_sla_tolerance_pd,
            understaffing_sla_penalty, scoring_note)
           VALUES (1, ?, ?, ?, ?, ?, ?, ?)""",
        (cm["currency"],
         cm["regular_cost_per_person_day"],
         cm["overstaffing"]["idle_cost_per_person_day"],
         cm["understaffing"]["overtime_premium_pct"],
         cm["understaffing"]["sla_tolerance_person_days"],
         cm["understaffing"]["sla_penalty_per_person_day"],
         cm.get("scoring_note", "")),
    )
    print("  ✓ cost_model loaded")


def load_decision_log(cur: sqlite3.Cursor):
    """Load from data/decision_log.json."""
    path = os.path.join(DATA_DIR, "decision_log.json")
    with open(path) as f:
        data = json.load(f)

    # Authors
    for name, role in data.get("authors", {}).items():
        cur.execute(
            "INSERT OR IGNORE INTO decision_log_authors (name, role) VALUES (?, ?)",
            (name, role),
        )

    # Build author name → id map
    cur.execute("SELECT id, name FROM decision_log_authors")
    author_map = {name: aid for aid, name in cur.fetchall()}

    count = 0
    for entry in data.get("entries", []):
        author_id = author_map.get(entry["author"])
        scope = entry.get("scope")
        if isinstance(scope, list):
            scope = ", ".join(scope)
        cur.execute(
            """INSERT OR IGNORE INTO decision_log
               (entry_id, captured_on, author_id, scope, note, claimed_effect)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entry["id"], entry["captured_on"], author_id,
             scope, entry["note"],
             json.dumps(entry.get("claimed_effect")) if entry.get("claimed_effect") else None),
        )
        count += 1
    print(f"  ✓ {count} decision_log entries loaded")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    print("Creating schema...")
    cur.executescript(SCHEMA)

    print("Loading data...")
    load_activities(cur)
    load_daily_actuals_clean(cur)
    load_daily_actuals_raw(cur)
    load_daily_volumes_clean(cur)
    load_daily_volumes_raw(cur)
    load_recommendations_clean(cur)
    load_cost_model(cur)
    load_decision_log(cur)

    conn.commit()

    # Summary
    print("\n── Database summary ──")
    for table in ["activities", "daily_actuals", "daily_volumes",
                   "recommendations", "cost_model",
                   "decision_log_authors", "decision_log"]:
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:30s} {count:>6} rows")

    conn.close()
    print(f"\n✅ Database saved to {DB_PATH}")


if __name__ == "__main__":
    main()
