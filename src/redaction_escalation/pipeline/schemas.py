"""The JSON contracts between the pipeline and the models.

Wire types subclass the domain types with a lenient config (unknown keys ignored, numbers
accepted where strings are expected), so a parsed reply is already a domain object.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from redaction_escalation.domain.models import (
    FindingIntegrity,
    Grade,
    RedactionRequest,
    Ruling,
    SecretGuess,
)

_LENIENT = ConfigDict(frozen=True, extra="ignore", coerce_numbers_to_str=True)


class WireRequest(RedactionRequest):
    """A redaction request as the advocate writes it."""

    model_config = _LENIENT


class WireRuling(Ruling):
    """A ruling as the honest executor writes it."""

    model_config = _LENIENT


class WireGuess(SecretGuess):
    """One secret's distribution as the "human" judge writes it."""

    model_config = _LENIENT


class Reply(BaseModel):
    """Base for every model reply."""

    model_config = _LENIENT


class AdvocateReply(Reply):
    """The advocate's requests."""

    requests: tuple[WireRequest, ...] = ()


class ExecutorReply(Reply):
    """The honest executor's rulings."""

    rulings: tuple[WireRuling, ...] = ()


class ViolationReply(Reply):
    """The "human" judge's suspicion score."""

    score: Grade
    rationale: str = ""


class SecretsReply(Reply):
    """The "human" judge's distributions, one per secret asked about."""

    guesses: tuple[WireGuess, ...]


class IntegrityReply(Reply):
    """The judge's verdict on whether editing changed the finding."""

    integrity: FindingIntegrity
