"""The retry loop in `calls.ask`, with a mock model that misbehaves on cue."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from inspect_ai.model import Model, ModelOutput, get_model

from redaction_escalation.domain.roles import Role
from redaction_escalation.pipeline import calls
from redaction_escalation.pipeline.mock import MOCK_MODEL
from redaction_escalation.pipeline.parsing import ReplyFormatError
from redaction_escalation.pipeline.schemas import ViolationReply


def _model(*replies: str) -> Model:
    outputs: Iterator[ModelOutput] = (
        ModelOutput.from_content(model=MOCK_MODEL, content=reply) for reply in replies
    )
    return get_model(MOCK_MODEL, custom_outputs=outputs, memoize=False)


def _ask_with(monkeypatch: pytest.MonkeyPatch, model: Model) -> ViolationReply:
    monkeypatch.setattr(calls, "get_model", lambda **_: model)
    return asyncio.run(calls.ask(Role.JUDGE, "prompt", ViolationReply))


def test_recovers_after_one_unreadable_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model("no idea", '{"score": 64, "rationale": "ok"}')
    assert _ask_with(monkeypatch, model).score == 64


def test_gives_up_after_the_configured_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model("no idea", "still no idea", '{"score": 64}')
    with pytest.raises(ReplyFormatError, match="no readable reply after 2 attempts"):
        _ask_with(monkeypatch, model)
