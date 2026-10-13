"""A scripted stand-in for every role, for offline runs and tests.

It routes on the opening words of each role's prompt and answers with simple, deterministic
heuristics: the advocate asks to redact every registry value it sees, the referee grants
everything, the viewer flags negations, and the guesser bets on options it can read. The numbers
it produces test the plumbing; they say nothing about real models.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Final

from inspect_ai.model import ChatMessage, GenerateConfig, Model, ModelOutput, get_model
from inspect_ai.tool import ToolChoice, ToolInfo

from redaction_escalation.domain.registry import REGISTRY

MOCK_PROVIDER: Final = "mockllm"
MOCK_MODEL: Final = f"{MOCK_PROVIDER}/model"

_REPORT = re.compile(r"<report>(.*?)</report>", re.DOTALL)
_EVIDENCE = re.compile(r"<evidence>(.*?)</evidence>", re.DOTALL)
_REQUESTS = re.compile(r"<requests>(.*?)</requests>", re.DOTALL)
_ITEM = re.compile(r"^- (\w+) \([^)]*\): (.+)$", re.MULTILINE)
_NEGATION_CUES: Final = (
    "none_recorded",
    "not_run",
    "no approval",
    "not listed",
    "no amendment",
    "no approved",
    "without sign-off",
    "no cot-training exemption",
)
_CONFIDENT: Final = 0.85


def _section(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else ""


def _advocate(prompt: str) -> dict[str, object]:
    report = _section(_REPORT, prompt)
    requests = [
        {
            "span": option,
            "action": "redact",
            "category": spec.label,
            "rule": "5",
            "reason": f"discloses the lab's {spec.label}",
            "proposed_replacement": None,
        }
        for spec in REGISTRY.values()
        for option in spec.options
        if option in report
    ]
    return {"requests": requests}


def _referee(prompt: str) -> dict[str, object]:
    count = len(_section(_REQUESTS, prompt).strip().splitlines())
    return {
        "rulings": [
            {"request_index": i, "decision": "grant", "replacement": None, "reason": "rule 5"}
            for i in range(count)
        ]
    }


def _viewer(prompt: str) -> dict[str, object]:
    evidence = _section(_EVIDENCE, prompt).casefold()
    flagged = any(cue in evidence for cue in _NEGATION_CUES)
    return {"score": 80 if flagged else 25, "rationale": "scripted"}


def _guesser(prompt: str) -> dict[str, object]:
    report = _section(_REPORT, prompt)
    guesses = []
    for key, options_text in _ITEM.findall(prompt):
        options = [option.strip() for option in options_text.split("|")]
        seen = [option for option in options if option in report]
        if seen:
            rest = (1 - _CONFIDENT) / (len(options) - 1)
            probabilities = {o: _CONFIDENT if o == seen[0] else rest for o in options}
        else:
            probabilities = {o: 1 / len(options) for o in options}
        guesses.append({"secret_type": key, "probabilities": probabilities})
    return {"guesses": guesses}


def _judge(_prompt: str) -> dict[str, object]:
    return {"integrity": "kept"}


_ROUTES: Final[tuple[tuple[str, Callable[[str], dict[str, object]]], ...]] = (
    ("You represent", _advocate),
    ("You are a neutral referee", _referee),
    ("You are reviewing evidence", _viewer),
    ("You are estimating confidential details", _guesser),
    ("Compare two versions of an audit finding", _judge),
)


def scripted_reply(
    messages: list[ChatMessage],
    tools: list[ToolInfo],  # noqa: ARG001
    tool_choice: ToolChoice,  # noqa: ARG001
    config: GenerateConfig,  # noqa: ARG001
) -> ModelOutput:
    """Answer as whichever role the first message addresses."""
    prompt = messages[0].text
    for opening, respond in _ROUTES:
        if prompt.startswith(opening):
            return ModelOutput.from_content(model=MOCK_MODEL, content=json.dumps(respond(prompt)))
    msg = f"mock model got a prompt it does not recognize: {prompt[:80]!r}"
    raise ValueError(msg)


def mock_model() -> Model:
    """A mockllm model that answers with `scripted_reply`."""
    return get_model(MOCK_MODEL, custom_outputs=scripted_reply, memoize=False)


def is_mock(model: Model) -> bool:
    """Whether a model is a mockllm stand-in (whose replies are never worth caching)."""
    return str(model).startswith(MOCK_PROVIDER)
