"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration for the Drummond Geometry system."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    eodhd_api_token: str | None = Field(default=None, alias="EODHD_API_TOKEN")
    database_url: str = Field(
        default="postgresql://fireworks_app:changeme_secure_password@localhost:5432/dgas",
        alias="DGAS_DATABASE_URL",
    )
    data_dir: Path = Field(default=Path("./data"), alias="DGAS_DATA_DIR")
    eodhd_requests_per_minute: int = Field(
        default=80,
        alias="EODHD_REQUESTS_PER_MINUTE",
        ge=1,
        description="Maximum API requests per minute before throttling.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    settings = Settings()  # type: ignore[call-arg]
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


__all__ = ["Settings", "get_settings"]
