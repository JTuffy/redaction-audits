"""Lab-style background: evidence-like, harmless, and not filterable by surface alone."""

from __future__ import annotations

import random

from redaction.core.models import SecretType, Split
from redaction.core.registry import spec_for
from redaction.data.blueprints import BENCHMARK_SETS, blueprints_for
from redaction.data.generator import DEFAULT_SEEDS, SPLIT_SIZES, slots
from redaction.data.lab_background import lab_background
from redaction.data.pipeline.plan import LineKind, ScenarioPlan, plan_scenario
from redaction.data.pipeline.surface import SURFACE_AUROC_MAX, surface_auroc

OPTIONS = {o for t in SecretType for o in spec_for(t).options}


def _plans(background: str) -> list[ScenarioPlan]:
    return [
        plan_scenario(
            slot,
            split=Split.DEV,
            index=i,
            seed=DEFAULT_SEEDS[Split.DEV],
            jobs=(),
            depth=one_set,
            background=background,
        )
        for one_set in BENCHMARK_SETS
        for i, slot in enumerate(slots(SPLIT_SIZES[Split.DEV]))
        if slot.violation_type in blueprints_for(one_set)
    ]


def test_lines_are_unique_and_avoid_banned_text() -> None:
    values = {"run": "run-1234", "team": "atlas", "date": "2026-05-01"}
    lines = lab_background(random.Random(0), 40, values=values, avoid={"gpus=8", "docs"})
    texts = [t for _, t in lines]
    assert len(texts) == len(set(texts)) == 40
    assert not any("gpus=8" in t or "docs" in t for t in texts)
    assert any("run-1234" in t or "team atlas" in t for t in texts)  # near-misses


def test_background_carries_no_secret_option_or_violation_token() -> None:
    for plan in _plans("lab"):
        for line in plan.lines:
            if line.kind is LineKind.BACKGROUND:
                assert not any(o.casefold() in line.text.casefold() for o in OPTIONS), line.text
                assert not any(tok in line.text for tok in plan.forbidden), line.text


def test_lab_background_is_harder_to_filter_than_scheduler_lines() -> None:
    lab = surface_auroc(_plans("lab"))
    assert lab is not None
    assert lab < SURFACE_AUROC_MAX


def test_philly_style_reproduces_the_old_plans() -> None:
    plan = _plans("philly")[0]
    assert any(line.kind is LineKind.LAB_NOISE for line in plan.lines)
