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
    """A ruling as the referee writes it."""

    model_config = _LENIENT


class WireGuess(SecretGuess):
    """One secret's distribution as the guesser writes it."""

    model_config = _LENIENT


class Reply(BaseModel):
    """Base for every model reply."""

    model_config = _LENIENT


class AdvocateReply(Reply):
    """The advocate's requests."""

    requests: tuple[WireRequest, ...] = ()


class RefereeReply(Reply):
    """The referee's rulings."""

    rulings: tuple[WireRuling, ...] = ()


class ViewerReply(Reply):
    """The viewer's suspicion score."""

    score: Grade
    rationale: str = ""


class GuesserReply(Reply):
    """The guesser's distributions, one per secret asked about."""

    guesses: tuple[WireGuess, ...]


class JudgeReply(Reply):
    """The judge's verdict on whether editing changed the finding."""

    integrity: FindingIntegrity
