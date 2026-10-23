"""Runtime settings, read from the environment and `.env`.

Provider API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are read by Inspect's providers
directly and never pass through this module.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from redaction.core.roles import Role

type ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]


class LogFormat(StrEnum):
    """How application logs are rendered."""

    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    """All tunable settings. Override any field with a `REDACTION_` environment variable."""

    model_config = SettingsConfigDict(
        env_prefix="REDACTION_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    advocate_model: str = "anthropic/claude-sonnet-5-5"
    executor_model: str = "anthropic/claude-sonnet-5-5"
    judge_model: str = "openai/gpt-5.6-terra"
    integrity_check_model: str = "anthropic/claude-haiku-5-5"

    # Reasoning is billed as output and dominates cost uncertainty, so each role is capped.
    # The setting is part of the frozen protocol; how each provider maps it is checked on dev.
    advocate_reasoning: ReasoningEffort = "low"
    executor_reasoning: ReasoningEffort = "low"
    judge_reasoning: ReasoningEffort = "low"  # gpt-5.6-terra rejects "minimal"
    integrity_check_reasoning: ReasoningEffort = "none"

    inspect_log_dir: Path = Path("logs/inspect")
    results_dir: Path = Path("results")
    scenarios_dir: Path = Path("data/generated")
    built_dir: Path = Path("data/built")  # frozen pipeline builds, one folder per version
    philly_raw: Path = Path("data/raw/philly/trace-data/cluster_job_log")
    background_sample: Path = Path("data/derived/philly_jobs.jsonl")
    site_dir: Path = Path("site/dist")
    public_site_dir: Path = Path("site/public")  # the public profile; see docs/publishing.md
    public_repo: str | None = None  # HTTPS URL of the Pages repo that holds the public build
    ledger_dir: Path = Path("runs")  # committed run records; see infra/runs.py
    direction_file: Path = Path("docs/direction.toml")  # question, focus, experiment threads
    paper_dir: Path = Path("paper")  # LaTeX sources; see paper/README.md
    notes_dir: Path = Path("docs/notes")  # Pipeline, Protocol, Findings, Decisions

    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE
    max_connections: int = Field(default=10, ge=1)
    # Protocol knobs added after the first pilot (see docs/notes/decisions.md).
    report_context: bool = True  # reports also quote correlates and two innocent lines
    judge_samples: int = Field(default=3, ge=1)  # judge replies averaged per question
    reviewer_model: str = "anthropic/claude-sonnet-5-5"  # blind label check on every build
    build_version: str | None = None  # pin runs to one frozen build; default is the split's LATEST
    parse_attempts: int = Field(default=2, ge=1)
    cache_replies: bool = True

    def model_roles(self) -> dict[str, str]:
        """Inspect `model_roles` for every role."""
        return {role.value: self.model_for(role) for role in Role}

    def model_for(self, role: Role) -> str:
        """The configured model for one role."""
        model: str = getattr(self, f"{role.value}_model")
        return model

    def reasoning_for(self, role: Role) -> ReasoningEffort:
        """The configured reasoning effort for one role."""
        effort: ReasoningEffort = getattr(self, f"{role.value}_reasoning")
        return effort


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once."""
    return Settings()
