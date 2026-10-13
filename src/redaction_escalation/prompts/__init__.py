"""Prompt templates, kept as text files beside this module.

Templates use `string.Template` (`$name`) so JSON examples in the prompts need no escaping.
Rendering is strict: a missing value raises instead of sending a half-filled prompt.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from importlib.resources import files
from string import Template


class PromptName(StrEnum):
    """Every prompt template in the package."""

    ADVOCATE = "advocate"
    STANCE_HONEST = "stance_honest"
    STANCE_COVER_UP = "stance_cover_up"
    PROCESS_EXECUTOR = "process_executor"
    PROCESS_SELF = "process_self"
    RULES = "rules"
    EXECUTOR = "executor"
    JUDGE_VIOLATION = "judge_violation"
    JUDGE_SECRETS = "judge_secrets"
    CONTEXT_PRIOR = "context_prior"
    CONTEXT_EVIDENCE = "context_evidence"
    INTEGRITY_CHECK = "integrity_check"
    RETRY = "retry"


@cache
def _template(name: PromptName) -> Template:
    text = files(__package__).joinpath(f"{name.value}.md").read_text(encoding="utf-8")
    return Template(text.strip())


def render(name: PromptName, **values: str) -> str:
    """Fill a template; raises `KeyError` if a placeholder has no value."""
    return _template(name).substitute(values)
