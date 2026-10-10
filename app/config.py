"""Environment-driven configuration for local, test and production profiles."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"

DEFAULT_SECRET = "hackathon-only-not-a-secret"


class Settings(BaseSettings):
    """Runtime settings. Secrets come from the environment, not source code."""

    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    app_name: str = Field(default="Harbour Meridian Risk Intelligence", alias="APP_NAME")
    database_url: str = Field(default="sqlite:///./data/harbour_meridian.db", alias="DATABASE_URL")
    data_dir: Path = Field(default=ROOT / "data", alias="DATA_DIR")
    secret_key: str = Field(default=DEFAULT_SECRET, alias="SECRET_KEY")
    demo_today: str = Field(default="2026-10-10", alias="DEMO_TODAY")
    timezone: str = Field(default="Asia/Hong_Kong", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    upload_max_bytes: int = Field(default=20_971_520, alias="UPLOAD_MAX_BYTES")
    allow_macros: bool = Field(default=False, alias="ALLOW_MACROS")
    external_llm_enabled: bool = Field(default=False, alias="EXTERNAL_LLM_ENABLED")
    llm_provider: str = Field(default="disabled", alias="LLM_PROVIDER")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    embedding_provider: str = Field(default="hashing", alias="EMBEDDING_PROVIDER")
    vector_store: str = Field(default="local-numpy", alias="VECTOR_STORE")
    token_ttl_hours: int = Field(default=12, alias="TOKEN_TTL_HOURS")
    demo_password: str = Field(default="Harbour-Demo-2026", alias="DEMO_PASSWORD")
    dataset_seed: int = Field(default=20261010, alias="DATASET_SEED")
    ai_kill_switch_default: bool = Field(default=False, alias="AI_KILL_SWITCH_DEFAULT")
    demo_mode_default: bool = Field(default=False, alias="DEMO_MODE_DEFAULT")
    data_residency: str = Field(default="hong-kong-sar-local-hackathon", alias="DATA_RESIDENCY")

    @property
    def object_store_dir(self) -> Path:
        return self.data_dir / "object_store"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def is_production_profile(self) -> bool:
        return self.app_env.lower() == "production"


def load_json(name: str) -> Any:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
