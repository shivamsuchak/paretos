"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration — values come from .env or environment variables."""

    # Data paths
    data_dir: Path = Field(default=Path("data"), description="Root data directory")
    clean_data_dir: Path = Field(default=Path("data/clean"), description="Clean CSV directory")

    # Cost model
    sla_tolerance_pd: float = Field(default=2.0, description="SLA tolerance in person-days")
    newsvendor_critical_ratio: float = Field(
        default=0.15, description="Newsvendor critical ratio cu/(cu+co)"
    )

    # Knowledge agent
    knowledge_staleness_weeks: int = Field(
        default=6, description="Weeks before a note is flagged stale"
    )

    # Regime detection
    regime_sensitivity: float = Field(
        default=0.05, description="Changepoint detection sensitivity"
    )

    # Admin constant
    admin_person_days: float = Field(
        default=8.0, description="Fixed admin desks (always staffed)"
    )

    # LLM (optional — Phase 2+)
    openai_api_key: str = Field(default="", description="OpenAI API key")
    primary_llm_model: str = Field(default="gpt-4o", description="Primary LLM model")
    small_llm_model: str = Field(default="gpt-4o-mini", description="Small/cheap LLM model")
    llm_temperature: float = Field(default=0.1, description="LLM temperature")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def present_csv(self) -> Path:
        return self.clean_data_dir / "present_long.csv"

    @property
    def recommendations_csv(self) -> Path:
        return self.clean_data_dir / "recommendations_long.csv"

    @property
    def volumes_csv(self) -> Path:
        return self.clean_data_dir / "volumes_long.csv"

    @property
    def decision_log_json(self) -> Path:
        return self.data_dir / "decision_log.json"

    @property
    def cost_model_json(self) -> Path:
        return self.data_dir / "cost_model.json"
