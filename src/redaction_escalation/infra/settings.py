"""Runtime settings, read from the environment and `.env`.

Provider API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are read by Inspect's providers
directly and never pass through this module.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from redaction_escalation.domain.roles import Role


class LogFormat(StrEnum):
    """How application logs are rendered."""

    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    """All tunable settings. Override any field with a `REDESC_` environment variable."""

    model_config = SettingsConfigDict(
        env_prefix="REDESC_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    advocate_model: str = "anthropic/claude-sonnet-5-5"
    executor_model: str = "anthropic/claude-sonnet-5-5"
    judge_model: str = "openai/gpt-5.6-terra"
    integrity_check_model: str = "anthropic/claude-haiku-5-5"

    inspect_log_dir: Path = Path("logs/inspect")
    results_dir: Path = Path("results")
    scenarios_dir: Path = Path("data/generated")

    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE
    max_connections: int = Field(default=10, ge=1)
    parse_attempts: int = Field(default=2, ge=1)
    cache_replies: bool = True

    def model_roles(self) -> dict[str, str]:
        """Inspect `model_roles` for every role."""
        return {role.value: self.model_for(role) for role in Role}

    def model_for(self, role: Role) -> str:
        """The configured model for one role."""
        model: str = getattr(self, f"{role.value}_model")
        return model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once."""
    return Settings()
