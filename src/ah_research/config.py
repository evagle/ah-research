"""Runtime configuration.

Sources, in precedence order:
 1. Process env vars (AH_RESEARCH_*, ANTHROPIC_API_KEY)
 2. .env file in project root (for development)
 3. keyring (future; for production secrets)
 4. defaults

Secrets (API keys) never persist in profile.yaml.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AH_RESEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".ah-research",
        description="Root dir for cache.duckdb and sessions/",
    )

    # Secrets read directly from env (not AH_RESEARCH_-prefixed)
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    log_level: str = "INFO"
    log_json: bool = True

    @property
    def cache_duckdb_path(self) -> Path:
        return self.cache_dir / "cache.duckdb"

    @property
    def sessions_dir(self) -> Path:
        return self.cache_dir / "sessions"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton per process. Tests clear via ``get_settings.cache_clear()``."""
    return Settings()
