"""Data loading and validation for all dataset files."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from paretos_core.config import Settings
from paretos_core.exceptions import DataLoadError, DataValidationError
from paretos_core.schemas import (
    DailyActual,
    DailyRecommendation,
    DailyRecommendationTotal,
    DailyVolume,
    DecisionLogEntry,
    WeeklyData,
)


def _parse_date(d: str) -> date:
    """Parse a YYYY-MM-DD date string."""
    return datetime.strptime(d, "%Y-%m-%d").date()


def load_actuals(path: Path) -> list[DailyActual]:
    """Load present_long.csv into a list of DailyActual."""
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise DataLoadError(f"Failed to load actuals from {path}: {e}") from e

    required = {"date", "present_total_person_days", "present_operative_person_days"}
    if not required.issubset(df.columns):
        raise DataValidationError(f"Missing columns in {path}: {required - set(df.columns)}")

    return [
        DailyActual(
            date=_parse_date(row["date"]),
            present_total_person_days=float(row["present_total_person_days"]),
            present_operative_person_days=float(row["present_operative_person_days"]),
        )
        for _, row in df.iterrows()
    ]


def load_recommendations(path: Path) -> list[DailyRecommendation]:
    """Load recommendations_long.csv into a list of DailyRecommendation."""
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise DataLoadError(f"Failed to load recommendations from {path}: {e}") from e

    required = {
        "decision_date",
        "planned_week_start",
        "date",
        "activity",
        "group",
        "recommended_person_days",
    }
    if not required.issubset(df.columns):
        raise DataValidationError(f"Missing columns in {path}: {required - set(df.columns)}")

    return [
        DailyRecommendation(
            decision_date=_parse_date(row["decision_date"]),
            planned_week_start=_parse_date(row["planned_week_start"]),
            date=_parse_date(row["date"]),
            activity=row["activity"],
            group=row["group"],
            recommended_person_days=float(row["recommended_person_days"]),
        )
        for _, row in df.iterrows()
    ]


def aggregate_recommendations(
    recs: Sequence[DailyRecommendation],
) -> list[DailyRecommendationTotal]:
    """Aggregate activity-level recommendations into daily operative totals."""
    by_date: dict[date, dict] = {}

    for r in recs:
        if r.group != "operative":
            continue
        if r.date not in by_date:
            by_date[r.date] = {
                "decision_date": r.decision_date,
                "planned_week_start": r.planned_week_start,
                "total": 0.0,
                "by_activity": {},
            }
        by_date[r.date]["total"] += r.recommended_person_days
        by_date[r.date]["by_activity"][r.activity] = r.recommended_person_days

    return [
        DailyRecommendationTotal(
            date=d,
            decision_date=info["decision_date"],
            planned_week_start=info["planned_week_start"],
            total_operative_person_days=info["total"],
            by_activity=info["by_activity"],
        )
        for d, info in sorted(by_date.items())
    ]


def load_volumes(path: Path) -> list[DailyVolume]:
    """Load volumes_long.csv into a list of DailyVolume."""
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise DataLoadError(f"Failed to load volumes from {path}: {e}") from e

    required = {
        "date",
        "picks_forecast",
        "picks_realized",
        "outbound_forecast",
        "outbound_realized",
        "inbound_forecast",
        "inbound_realized",
    }
    if not required.issubset(df.columns):
        raise DataValidationError(f"Missing columns in {path}: {required - set(df.columns)}")

    return [
        DailyVolume(
            date=_parse_date(row["date"]),
            picks_forecast=int(row["picks_forecast"]),
            picks_realized=int(row["picks_realized"]),
            outbound_forecast=int(row["outbound_forecast"]),
            outbound_realized=int(row["outbound_realized"]),
            inbound_forecast=int(row["inbound_forecast"]),
            inbound_realized=int(row["inbound_realized"]),
        )
        for _, row in df.iterrows()
    ]


def load_decision_log(path: Path) -> list[DecisionLogEntry]:
    """Load decision_log.json into a list of DecisionLogEntry."""
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        raise DataLoadError(f"Failed to load decision log from {path}: {e}") from e

    return [
        DecisionLogEntry(
            id=entry["id"],
            captured_on=_parse_date(entry["captured_on"]),
            author=entry["author"],
            scope=entry["scope"],
            note=entry["note"],
            claimed_effect=entry["claimed_effect"],
        )
        for entry in data["entries"]
    ]


def build_weekly_cycles(
    recommendations: list[DailyRecommendationTotal],
    actuals: list[DailyActual] | None = None,
    volumes: list[DailyVolume] | None = None,
) -> list[WeeklyData]:
    """Group data into weekly cycles keyed by (decision_date, planned_week_start).

    Each cycle contains the recommendations for that week, plus any matching
    actuals and volumes (if available for that week).
    """
    actuals_by_date = {a.date: a for a in actuals} if actuals else {}
    volumes_by_date = {v.date: v for v in volumes} if volumes else {}

    weeks: dict[tuple[date, date], list[DailyRecommendationTotal]] = defaultdict(list)
    for rec in recommendations:
        key = (rec.decision_date, rec.planned_week_start)
        weeks[key].append(rec)

    result = []
    for (dec_date, week_start), week_recs in sorted(weeks.items()):
        week_dates = [r.date for r in week_recs]
        week_actuals = [actuals_by_date[d] for d in week_dates if d in actuals_by_date] or None
        week_volumes = [volumes_by_date[d] for d in week_dates if d in volumes_by_date] or None

        result.append(
            WeeklyData(
                decision_date=dec_date,
                planned_week_start=week_start,
                recommendations=week_recs,
                actuals=week_actuals,
                volumes=week_volumes,
            )
        )

    return result


OPERATIVE_ACTIVITIES = {
    "Unloading", "Receiving", "Putaway", "Picking", "Staging", "Loading",
    "Replenishment / relocation", "Transit drivers", "Yard shunting",
    "Team leads", "Pick QA", "Co-Packing line", "VNA replenishment",
    "Returns / QC", "Aisle maintenance",
}

SKIP_ROWS = {
    "Datum/Volumen", "PAL_Wareneingang", "VollPAL_Warenausgang",
    "Picks_Warenausgang", "KomPAL_Warenausgang", "Mitarbeiter operativ",
    "Summe operativ", "Mitarbeiter administrativ", "Summe administrativ",
    "Control room", "Outbound office", "Inbound office", "Inventory",
}


def _parse_german_float(s: str) -> float:
    """Parse a German-formatted decimal (comma as separator)."""
    s = s.strip()
    if not s:
        return 0.0
    return float(s.replace(",", "."))


def _parse_german_date(s: str) -> date:
    """Parse DD.MM.YYYY date string."""
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def load_raw_recommendation_file(
    path: Path, decision_date: date | None = None,
) -> list[DailyRecommendationTotal]:
    """Parse a single raw recommendation CSV (semicolon-delimited, German decimals).

    The filename encodes the decision date (rec_YYYY-MM-DD.csv).
    The first row has dates in DD.MM.YYYY format.
    """
    if decision_date is None:
        match = re.search(r"rec_(\d{4}-\d{2}-\d{2})", path.stem)
        if match:
            decision_date = _parse_date(match.group(1))
        else:
            raise DataLoadError(f"Cannot infer decision date from filename: {path}")

    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    if not rows:
        raise DataLoadError(f"Empty file: {path}")

    # Row 0: header with dates (skip first cell "Datum/Volumen")
    header = rows[0]
    day_dates = [_parse_german_date(h) for h in header[1:] if h.strip()]
    weekday_dates = [d for d in day_dates if d.weekday() < 5]  # Mon-Fri only
    planned_week_start = min(weekday_dates) if weekday_dates else day_dates[0]

    # Build per-day activity totals
    by_day: dict[date, dict[str, float]] = {d: {} for d in weekday_dates}

    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        activity = row[0].strip()
        if activity in SKIP_ROWS or activity not in OPERATIVE_ACTIVITIES:
            continue
        for i, d in enumerate(day_dates):
            if d not in by_day:
                continue
            col_idx = i + 1
            if col_idx < len(row):
                val = _parse_german_float(row[col_idx])
                by_day[d][activity] = val

    result = []
    for d in sorted(by_day.keys()):
        activities = by_day[d]
        total = sum(activities.values())
        if total > 0:
            result.append(
                DailyRecommendationTotal(
                    date=d,
                    decision_date=decision_date,
                    planned_week_start=planned_week_start,
                    total_operative_person_days=total,
                    by_activity=activities,
                )
            )

    return result


def load_raw_recommendations_dir(
    directory: Path, only_holdout: bool = False, training_dates: set[date] | None = None,
) -> list[DailyRecommendationTotal]:
    """Load all raw recommendation CSVs from a directory.

    Args:
        directory: Path to data/recommendations/
        only_holdout: If True, skip files whose dates are in training_dates.
        training_dates: Set of dates already covered by clean data.
    """
    all_recs = []
    for path in sorted(directory.glob("rec_*.csv")):
        file_recs = load_raw_recommendation_file(path)
        if only_holdout and training_dates:
            file_recs = [r for r in file_recs if r.date not in training_dates]
        all_recs.extend(file_recs)
    return all_recs


class DataStore:
    """Convenience wrapper that loads all dataset files and provides query methods."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._actuals: list[DailyActual] | None = None
        self._recs_raw: list[DailyRecommendation] | None = None
        self._recs: list[DailyRecommendationTotal] | None = None
        self._volumes: list[DailyVolume] | None = None
        self._decision_log: list[DecisionLogEntry] | None = None
        self._weekly_cycles: list[WeeklyData] | None = None

    @property
    def actuals(self) -> list[DailyActual]:
        if self._actuals is None:
            self._actuals = load_actuals(self.settings.present_csv)
        return self._actuals

    @property
    def recommendations_raw(self) -> list[DailyRecommendation]:
        if self._recs_raw is None:
            self._recs_raw = load_recommendations(self.settings.recommendations_csv)
        return self._recs_raw

    @property
    def recommendations(self) -> list[DailyRecommendationTotal]:
        if self._recs is None:
            self._recs = aggregate_recommendations(self.recommendations_raw)
        return self._recs

    @property
    def volumes(self) -> list[DailyVolume]:
        if self._volumes is None:
            self._volumes = load_volumes(self.settings.volumes_csv)
        return self._volumes

    @property
    def decision_log(self) -> list[DecisionLogEntry]:
        if self._decision_log is None:
            self._decision_log = load_decision_log(self.settings.decision_log_json)
        return self._decision_log

    @property
    def weekly_cycles(self) -> list[WeeklyData]:
        if self._weekly_cycles is None:
            all_recs = self.all_recommendations
            self._weekly_cycles = build_weekly_cycles(all_recs, self.actuals, self.volumes)
        return self._weekly_cycles

    @property
    def all_recommendations(self) -> list[DailyRecommendationTotal]:
        """All recommendations: clean (training) + raw holdout files."""
        training_recs = self.recommendations
        training_dates = {r.date for r in training_recs}

        raw_dir = self.settings.data_dir / "recommendations"
        if raw_dir.is_dir():
            holdout_recs = load_raw_recommendations_dir(
                raw_dir, only_holdout=True, training_dates=training_dates
            )
        else:
            holdout_recs = []

        return sorted(training_recs + holdout_recs, key=lambda r: r.date)

    def actuals_by_date(self) -> dict[date, DailyActual]:
        return {a.date: a for a in self.actuals}

    def recommendations_by_date(self) -> dict[date, DailyRecommendationTotal]:
        return {r.date: r for r in self.all_recommendations}

    def training_weeks(self) -> list[WeeklyData]:
        """Return only weeks that have actuals (training set)."""
        return [w for w in self.weekly_cycles if w.actuals]

    def holdout_weeks(self) -> list[WeeklyData]:
        """Return only weeks without actuals (holdout set)."""
        return [w for w in self.weekly_cycles if not w.actuals]
