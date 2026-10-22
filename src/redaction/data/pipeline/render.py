"""Layer 2: rendering a plan into log text, and assembling the result into a `Scenario`.

A renderer returns one `RenderedLine` per planned line, in plan order. The template renderer
copies the planned text; a model renderer (see `model_render`) rephrases rephrasable lines.
Either way the validators in `validate` decide whether the rendering is kept.
"""

from __future__ import annotations

import random
from typing import Protocol

from redaction.core.models import Frozen, LogEntry, Scenario
from redaction.data.generator import timestamps
from redaction.data.pipeline.plan import ScenarioPlan


class RenderedLine(Frozen):
    """The text a renderer produced for one planned line."""

    source: str
    text: str


class Rendering(Frozen):
    """A renderer's output for one plan: one line per planned line, in plan order."""

    renderer: str
    lines: tuple[RenderedLine, ...]
    refused: bool = False  # the model declined (a content filter); lines are empty


class Renderer(Protocol):
    """Anything that can phrase a plan."""

    name: str

    async def render(self, plan: ScenarioPlan, attempt: int) -> Rendering:
        """Phrase the plan. `attempt` counts from 1 and lets a renderer vary retries."""
        ...


class TemplateRenderer:
    """Copies the planned text. Deterministic and free; the baseline and the CI renderer."""

    name = "template"

    async def render(self, plan: ScenarioPlan, attempt: int) -> Rendering:  # noqa: ARG002
        """Return the planned lines unchanged."""
        return Rendering(
            renderer=self.name,
            lines=tuple(RenderedLine(source=line.source, text=line.text) for line in plan.lines),
        )


def assemble(plan: ScenarioPlan, rendering: Rendering) -> Scenario:
    """Give rendered lines log IDs and timestamps and attach the plan's ground truth.

    Call only after the rendering has passed validation; `Scenario` re-checks the invariants.
    """
    rng = random.Random(f"assemble:{plan.scenario_id}")
    log_ids = tuple(f"LOG-{i:04d}" for i in range(1, len(rendering.lines) + 1))
    logs = tuple(
        LogEntry(log_id=log_id, timestamp=stamp, source=line.source, text=line.text)
        for log_id, stamp, line in zip(
            log_ids, timestamps(rng, len(log_ids)), rendering.lines, strict=True
        )
    )
    return Scenario(
        scenario_id=plan.scenario_id,
        split=plan.split,
        violation_type=plan.violation_type,
        claim=plan.claim,
        label=plan.label,
        difficulty=plan.difficulty,
        lab_name=plan.lab_name,
        logs=logs,
        secrets=plan.secrets,
        key_evidence_ids=tuple(
            log_id for log_id, line in zip(log_ids, plan.lines, strict=True) if line.key_evidence
        ),
        separating_cues=plan.separating_cues,
        secret_cues=plan.secret_cues,
        correlates=plan.correlates_for(log_ids),
        depth=plan.depth,
    )
