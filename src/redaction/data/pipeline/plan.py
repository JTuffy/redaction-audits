"""Layer 1 of the pipeline: the plan, which fixes every fact before any text is written.

A plan decides the label, the violation evidence, the secret values, the correlates and the
background. Renderers only phrase it; validators check the phrasing against it. Ground truth
therefore never depends on what a model chose to write.
"""

from __future__ import annotations

import random
import re
from enum import StrEnum
from typing import Final

from redaction.core.models import (
    Correlate,
    CorrelateStrength,
    Difficulty,
    Frozen,
    Label,
    PlantedSecret,
    SecretType,
    Split,
    ViolationType,
)
from redaction.core.registry import spec_for
from redaction.data.background import PhillyJob, background_lines
from redaction.data.blueprints import (
    BLUEPRINTS,
    NEUTRAL_LINES,
    NOISE_SECRET_LINES,
    SECRET_PLACEHOLDERS,
    Variant,
    variant_for,
)
from redaction.data.correlates import correlate_lines
from redaction.data.generator import LAB_NAMES, ScenarioSpec, neutral_values

# A key=value token such as `consent_basis=none_recorded`: the cues renderers must keep.
TOKEN_PATTERN: Final = re.compile(r"[A-Za-z_][\w.-]*=[^\s,;]+")
BACKGROUND_RANGE: Final = (24, 56)  # real-cluster lines per scenario
LAB_NOISE_LINES: Final = 4  # lab-flavoured filler, so not all noise is scheduler output


class LineKind(StrEnum):
    """What a planted line is for."""

    EVIDENCE = "evidence"  # the violation or red-herring lines the audit turns on
    CORRELATE = "correlate"  # reveals a secret without its value
    SECRET_MENTION = "secret_mention"  # noqa: S105  the noise secret, mentioned in passing
    LAB_NOISE = "lab_noise"  # generic lab chatter
    BACKGROUND = "background"  # real Philly scheduler records


class PlannedLine(Frozen):
    """One line the renderer must produce. `required` must survive any rephrasing verbatim."""

    kind: LineKind
    source: str
    text: str
    required: tuple[str, ...]
    key_evidence: bool = False
    correlate_type: SecretType | None = None
    correlate_snippet: str | None = None
    correlate_strength: CorrelateStrength | None = None
    correlate_rationale: str | None = None

    @property
    def rephrasable(self) -> bool:
        """Background lines are real records and are kept as they are."""
        return self.kind is not LineKind.BACKGROUND


class ScenarioPlan(Frozen):
    """Every fact about one scenario; the input to a renderer."""

    scenario_id: str
    split: Split
    index: int
    violation_type: ViolationType
    claim: str
    label: Label
    difficulty: Difficulty | None
    variant: str
    lab_name: str
    secrets: tuple[PlantedSecret, ...]
    lines: tuple[PlannedLine, ...]
    separating_cues: tuple[str, ...]
    secret_cues: tuple[SecretType, ...]
    forbidden: tuple[str, ...]  # violation-only tokens a non-violation must not contain

    def correlates_for(self, log_ids: tuple[str, ...]) -> tuple[Correlate, ...]:
        """Correlate records once lines have log IDs (log_ids in plan order)."""
        return tuple(
            Correlate(
                secret_type=line.correlate_type,
                log_id=log_id,
                snippet=line.correlate_snippet,
                strength=line.correlate_strength,
                rationale=line.correlate_rationale or "see correlates module",
            )
            for line, log_id in zip(self.lines, log_ids, strict=True)
            if line.correlate_type is not None
            and line.correlate_snippet is not None
            and line.correlate_strength is not None
        )


def tokens(text: str) -> tuple[str, ...]:
    """The key=value tokens in a line, in order."""
    return tuple(TOKEN_PATTERN.findall(text))


def _required(text: str, secrets: tuple[PlantedSecret, ...]) -> tuple[str, ...]:
    """What must survive rephrasing: secret values and cue tokens; else the whole line."""
    values = tuple(s.value for s in secrets if s.value in text)
    found = values + tokens(text)
    return found or (text,)


def _forbidden(variant: Variant, violation: Variant, values: dict[str, str]) -> tuple[str, ...]:
    """Tokens only the violation has: a red herring or clean case containing one is mislabeled."""
    own = {t for line in variant.lines for t in tokens(line.template.format_map(values))}
    theirs = [t for line in violation.lines for t in tokens(line.template.format_map(values))]
    return tuple(dict.fromkeys(t for t in theirs if t not in own))


def _interleave[T](rng: random.Random, planted: list[T], noise: list[T]) -> list[T]:
    """Scatter noise among planted lines, keeping planted order."""
    total = len(planted) + len(noise)
    positions = set(rng.sample(range(total), len(planted)))
    p_iter, n_iter = iter(planted), iter(noise)
    return [next(p_iter) if i in positions else next(n_iter) for i in range(total)]


def plan_scenario(
    slot: ScenarioSpec,
    *,
    split: Split,
    index: int,
    seed: int,
    jobs: tuple[PhillyJob, ...],
) -> ScenarioPlan:
    """Fix every fact for one scenario. The same arguments always give the same plan."""
    rng = random.Random(f"plan:{seed}:{index}")
    blueprint = BLUEPRINTS[slot.violation_type]
    variant = variant_for(blueprint, slot.label, slot.difficulty)
    noise_type = rng.choice([t for t in SecretType if t not in blueprint.core_secrets])
    secrets = tuple(
        PlantedSecret(secret_type=t, value=rng.choice(spec_for(t).options))
        for t in (*blueprint.core_secrets, noise_type)
    )
    values = neutral_values(rng) | {SECRET_PLACEHOLDERS[s.secret_type]: s.value for s in secrets}

    planted = [
        PlannedLine(
            kind=LineKind.EVIDENCE,
            source=line.source,
            text=(text := line.template.format_map(values)),
            required=_required(text, secrets),
            key_evidence=line.evidence,
        )
        for line in variant.lines
    ]
    mention = NOISE_SECRET_LINES[noise_type]
    mention_text = mention.template.format_map(values)
    extras = [
        PlannedLine(
            kind=LineKind.SECRET_MENTION,
            source=mention.source,
            text=mention_text,
            required=_required(mention_text, secrets),
        )
    ]
    for secret in secrets:
        for c in correlate_lines(secret.secret_type, secret.value):
            text = c.template.format_map(values)
            extras.append(
                PlannedLine(
                    kind=LineKind.CORRELATE,
                    source=c.source,
                    text=text,
                    required=(c.snippet,),
                    correlate_type=secret.secret_type,
                    correlate_snippet=c.snippet,
                    correlate_strength=c.strength,
                    correlate_rationale=c.rationale,
                )
            )
    extras += [
        PlannedLine(kind=LineKind.LAB_NOISE, source=n.source, text=n.template, required=())
        for n in rng.sample(NEUTRAL_LINES, LAB_NOISE_LINES)
    ]
    extras += [
        PlannedLine(kind=LineKind.BACKGROUND, source=source, text=text, required=(text,))
        for source, text in background_lines(jobs, rng, rng.randint(*BACKGROUND_RANGE))
    ]
    rng.shuffle(extras)
    return ScenarioPlan(
        scenario_id=f"{split}-{index:03d}-{slot.violation_type}-{slot.label}",
        split=split,
        index=index,
        violation_type=slot.violation_type,
        claim=blueprint.claim,
        label=slot.label,
        difficulty=slot.difficulty,
        variant=variant.description,
        lab_name=rng.choice(LAB_NAMES),
        secrets=secrets,
        lines=tuple(_interleave(rng, planted, extras)),
        separating_cues=blueprint.separating_cues,
        secret_cues=blueprint.secret_cues,
        forbidden=()
        if slot.label is Label.VIOLATION
        else _forbidden(variant, blueprint.violation, values),
    )
