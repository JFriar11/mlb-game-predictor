from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from MLB_* environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MLB_", extra="ignore")

    database_url: str = "postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor"
    log_level: str = "INFO"
    api_base_url: str = "https://statsapi.mlb.com/api"
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_attempts: int = Field(default=3, ge=1, le=8)
    notification_webhook_url: str | None = None
    watcher_idle_seconds: int = Field(default=900, ge=60, le=3600)
    watcher_approaching_seconds: int = Field(default=300, ge=60, le=900)


@lru_cache
def get_settings() -> Settings:
    return Settings()
