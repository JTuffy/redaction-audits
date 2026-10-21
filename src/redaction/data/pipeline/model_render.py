"""Model-backed renderer and reviewer (layers 2 and 3b), via Inspect's model API.

Any Inspect model string works (`anthropic/claude-opus-5-5`, `vertex/gemini-2.5-flash`, ...).
Only rephrasable lines are sent to the model; real background records are re-inserted by code,
which keeps prompts short and makes it impossible for the model to alter them.
"""

from __future__ import annotations

from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model
from pydantic import BaseModel, Field

from redaction.core.models import Scenario
from redaction.core.parsing import ReplyFormatError, parse_reply
from redaction.data.pipeline.build import Review, Verdict
from redaction.data.pipeline.plan import ScenarioPlan
from redaction.data.pipeline.render import RenderedLine, Rendering

RENDER_PROMPT = """\
You are writing internal log lines for {lab}, a fictional AI lab. Rewrite each numbered line \
below in the voice of the system or team named in its source field, the way a real engineer \
or tool would log it: terse, varied in format, with realistic identifiers. Keep every string \
listed under "keep" exactly as written, character for character. Do not add facts, do not \
mention any other model sizes, optimizers, names or dates, and do not explain anything.

{lines}

Reply with only a JSON object, with one entry for every numbered line:
{{"lines": [{{"i": <number>, "source": "<source>", "text": "<line>"}}, ...]}}\
"""

REVIEW_PROMPT = """\
You are reviewing a log bundle from an AI lab against this claim: "{claim}"

{logs}

Do these logs show that the claim was violated? Judge only from the logs. Reply with only a \
JSON object: {{"verdict": "violation" | "no_violation", "reason": "<one sentence>"}}\
"""


class _Line(BaseModel):
    i: int
    source: str = Field(min_length=1)
    text: str


class _RenderReply(BaseModel):
    lines: list[_Line]


class ModelRenderer:
    """Rephrases a plan's rephrasable lines with a model; validators check the result."""

    def __init__(self, model: str, *, temperature: float = 0.9) -> None:
        self.name = model
        self._model = model
        self._temperature = temperature

    async def render(self, plan: ScenarioPlan, attempt: int) -> Rendering:
        """One model call per attempt; unreadable replies leave lines empty (and invalid)."""
        todo = [(i, line) for i, line in enumerate(plan.lines) if line.rephrasable]
        listing = "\n".join(
            f"{i}. source={line.source} | {line.text} | keep: {' ; '.join(line.required)}"
            for i, line in todo
        )
        prompt = RENDER_PROMPT.format(lab=plan.lab_name, lines=listing)
        config = GenerateConfig(temperature=self._temperature, seed=attempt)
        output = await get_model(self._model).generate(
            [ChatMessageUser(content=prompt)], config=config
        )
        try:
            reply = {line.i: line for line in parse_reply(output.completion, _RenderReply).lines}
        except ReplyFormatError:
            reply = {}
        lines = []
        for i, planned in enumerate(plan.lines):
            got = reply.get(i)
            if not planned.rephrasable:
                lines.append(RenderedLine(source=planned.source, text=planned.text))
            elif got is None:
                lines.append(RenderedLine(source=planned.source, text=""))
            else:
                lines.append(RenderedLine(source=got.source, text=got.text.strip()))
        return Rendering(renderer=self.name, lines=tuple(lines))


class _ReviewReply(BaseModel):
    verdict: Verdict
    reason: str


class ModelReviewer:
    """Blind check that a scenario reads as its label: sees the claim and the logs only."""

    def __init__(self, model: str) -> None:
        self.name = model
        self._model = model

    async def review(self, scenario: Scenario) -> Review:
        """Classify a scenario; an unreadable reply counts as disagreement."""
        logs = "\n".join(f"{e.log_id} {e.timestamp} [{e.source}] {e.text}" for e in scenario.logs)
        prompt = REVIEW_PROMPT.format(claim=scenario.claim, logs=logs)
        output = await get_model(self._model).generate([ChatMessageUser(content=prompt)])
        try:
            reply = parse_reply(output.completion, _ReviewReply)
        except ReplyFormatError as error:
            wrong = Verdict.NO_VIOLATION if scenario.label == "violation" else Verdict.VIOLATION
            return Review(verdict=wrong, reason=f"unreadable reply: {error}"[:200])
        return Review(verdict=reply.verdict, reason=reply.reason)
