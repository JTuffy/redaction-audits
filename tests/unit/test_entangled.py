"""The entangled blueprint draft: every cell plans and validates, markers turn the hard red
herring into the violation, and consistent pseudonyms keep the two confidential entities apart."""

from __future__ import annotations

import asyncio

import pytest

from redaction.core.models import Difficulty, Label, Scenario, SecretType, Split, ViolationType
from redaction.data.blueprints import ENTANGLED_BLUEPRINTS, variant_for
from redaction.data.generator import ScenarioSpec
from redaction.data.pipeline.plan import compute_thresholds, plan_scenario
from redaction.data.pipeline.render import TemplateRenderer, assemble
from redaction.data.pipeline.validate import validate
from redaction.data.reports import templated_report
from redaction.escalation.ablation import Condition, variant
from redaction.escalation.policies import apply_text_redaction

CELLS = [
    (Label.VIOLATION, None),
    (Label.RED_HERRING, Difficulty.EASY),
    (Label.RED_HERRING, Difficulty.MEDIUM),
    (Label.RED_HERRING, Difficulty.HARD),
    (Label.CLEAN, None),
]


def _scenario(
    violation_type: ViolationType, label: Label, difficulty: Difficulty | None, index: int = 0
) -> Scenario:
    spec = ScenarioSpec(violation_type, label, difficulty)
    plan = plan_scenario(spec, split=Split.DEV, index=index, seed=101, jobs=(), depth="entangled")
    rendering = asyncio.run(TemplateRenderer().render(plan, 1))
    assert validate(plan, rendering) == ()
    return assemble(plan, rendering)


@pytest.mark.parametrize("violation_type", sorted(ENTANGLED_BLUEPRINTS))
@pytest.mark.parametrize(("label", "difficulty"), CELLS)
def test_every_entangled_cell_plans_and_validates(
    violation_type: ViolationType, label: Label, difficulty: Difficulty | None
) -> None:
    for index in range(5):
        scenario = _scenario(violation_type, label, difficulty, index)
        assert scenario.depth == "entangled"
        assert len(scenario.key_evidence_ids) >= 4
        values = {s.value for s in scenario.redactable()}
        assert len(values) == len(scenario.redactable())  # the second value is a different one


# Placeholders that a marker (or a hidden footprint) makes indistinguishable.
_MERGED = {"{customer2}": "{customer}", "{codename2}": "{codename}"}
_MERGED |= {"{threshold_above}": "{threshold_below}"}


def _merged(template: str) -> str:
    for a, b in _MERGED.items():
        template = template.replace(a, b)
    return template


@pytest.mark.parametrize("violation_type", sorted(ENTANGLED_BLUEPRINTS))
def test_markers_turn_the_hard_herring_into_the_violation(violation_type: ViolationType) -> None:
    blueprint = ENTANGLED_BLUEPRINTS[violation_type]
    hard = variant_for(blueprint, Label.RED_HERRING, Difficulty.HARD)
    real = [line.template for line in blueprint.violation.lines]
    assert [line.template for line in hard.lines] != real
    assert [_merged(line.template) for line in hard.lines] == [_merged(t) for t in real]


def test_pseudonyms_keep_two_customers_apart_and_markers_merge_them() -> None:
    scenario = _scenario(ViolationType.OPTED_OUT_DATA, Label.RED_HERRING, Difficulty.HARD)
    assert [c.secret_type for c in scenario.confidential] == [SecretType.CUSTOMER_NAME]
    report = templated_report(scenario, context=False)
    pseudo = " ".join(q.quote for q in variant(report, scenario, Condition.PSEUDONYM).evidence)
    marked = " ".join(q.quote for q in variant(report, scenario, Condition.MARKER).evidence)
    redacted = " ".join(q.quote for q in apply_text_redaction(report, scenario).evidence)
    assert "Customer A" in pseudo
    assert "Customer B" in pseudo
    for value in (s.value for s in scenario.redactable()):
        assert value not in pseudo
        assert value not in marked
        assert value not in redacted


def test_compute_thresholds_bracket_the_footprint() -> None:
    assert compute_thresholds("512 GPUs for 60 days") == {  # 737,280 GPU-hours
        "threshold_below": "300,000",
        "threshold_above": "1,500,000",
    }
    assert compute_thresholds(None) == {}
