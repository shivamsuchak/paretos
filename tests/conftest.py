"""Shared fixtures for tests."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from paretos_core.config import Settings
from paretos_core.cost_model import CostModel
from paretos_core.data_loader import DataStore
from paretos_core.schemas import (
    DailyActual,
    DailyRecommendationTotal,
    StaffingPlan,
)


@pytest.fixture
def settings() -> Settings:
    """Settings pointing to the real dataset."""
    return Settings(
        data_dir=Path("data"),
        clean_data_dir=Path("data/clean"),
    )


@pytest.fixture
def cost_model(settings: Settings) -> CostModel:
    """CostModel loaded from cost_model.json."""
    return CostModel.from_json(settings.cost_model_json)


@pytest.fixture
def store(settings: Settings) -> DataStore:
    """DataStore with all data loaded."""
    return DataStore(settings)


@pytest.fixture
def sample_actual() -> DailyActual:
    return DailyActual(
        date=date(2026, 5, 18),
        present_total_person_days=64.25,
        present_operative_person_days=56.25,
    )


@pytest.fixture
def sample_recommendation() -> DailyRecommendationTotal:
    return DailyRecommendationTotal(
        date=date(2026, 5, 18),
        decision_date=date(2026, 5, 12),
        planned_week_start=date(2026, 5, 18),
        total_operative_person_days=65.0,
        by_activity={"Picking": 12.9, "Putaway": 13.7, "Staging": 6.8},
    )
