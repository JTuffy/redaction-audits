"""The deep blueprint draft: every cell plans and validates, and hard herrings mirror violations."""

from __future__ import annotations

import asyncio
import random
from datetime import date

import pytest

from redaction.core.models import Difficulty, Label, Split, ViolationType
from redaction.data.blueprints import DEEP_BLUEPRINTS, blueprints_for, variant_for
from redaction.data.generator import ScenarioSpec, neutral_values
from redaction.data.pipeline.plan import plan_scenario
from redaction.data.pipeline.render import TemplateRenderer, assemble
from redaction.data.pipeline.validate import validate
from redaction.data.reports import templated_report

CELLS = [
    (Label.VIOLATION, None),
    (Label.RED_HERRING, Difficulty.EASY),
    (Label.RED_HERRING, Difficulty.MEDIUM),
    (Label.RED_HERRING, Difficulty.HARD),
    (Label.CLEAN, None),
]


@pytest.mark.parametrize("violation_type", sorted(DEEP_BLUEPRINTS))
@pytest.mark.parametrize(("label", "difficulty"), CELLS)
def test_every_deep_cell_plans_and_validates(
    violation_type: ViolationType, label: Label, difficulty: Difficulty | None
) -> None:
    spec = ScenarioSpec(violation_type, label, difficulty)
    for index in range(5):
        plan = plan_scenario(spec, split=Split.DEV, index=index, seed=101, jobs=(), depth="deep")
        rendering = asyncio.run(TemplateRenderer().render(plan, 1))
        assert validate(plan, rendering) == ()
        scenario = assemble(plan, rendering)
        assert scenario.depth == "deep"
        assert len(scenario.key_evidence_ids) >= 5
        report = templated_report(scenario, context=True)
        assert {q.log_id for q in report.evidence} >= set(scenario.key_evidence_ids)


@pytest.mark.parametrize("violation_type", sorted(DEEP_BLUEPRINTS))
def test_hard_herring_mirrors_the_violation(violation_type: ViolationType) -> None:
    blueprint = DEEP_BLUEPRINTS[violation_type]
    violation = {line.template for line in blueprint.violation.lines}
    hard = variant_for(blueprint, Label.RED_HERRING, Difficulty.HARD)
    shared = sum(line.template in violation for line in hard.lines)
    assert shared >= len(hard.lines) - 2  # cleared by one or two lines, not by its vocabulary


def test_derived_values_are_consistent() -> None:
    for n in range(300):
        values = neutral_values(random.Random(n))
        tickets = {values["ticket"], values["ticket2"], values["ticket3"]}
        assert len(tickets) == 3
        assert all(1000 <= int(t) <= 9999 for t in tickets)
        d = {k: date.fromisoformat(values[k]) for k in values if k.startswith("date")}
        assert d["date_long_before"] < d["date_before"] < d["date"] < d["date_after"]
        assert d["date_after"] <= date(2026, 7, 1)


def test_unknown_depth_is_rejected() -> None:
    with pytest.raises(ValueError, match="depth"):
        blueprints_for("medium")
