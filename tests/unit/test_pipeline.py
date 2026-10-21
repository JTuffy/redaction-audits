from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest

from redaction.core.models import Label, SecretType, Split
from redaction.core.registry import spec_for
from redaction.data.background import PhillyJob, background_lines
from redaction.data.correlates import correlate_lines
from redaction.data.generator import SPLIT_SIZES, slots
from redaction.data.pipeline.build import build_split_v2, manifest, write_build
from redaction.data.pipeline.plan import LineKind, ScenarioPlan, plan_scenario
from redaction.data.pipeline.render import RenderedLine, Rendering, TemplateRenderer, assemble
from redaction.data.pipeline.validate import Check, validate
from redaction.viewer.build import build_site

JOBS = tuple(
    PhillyJob(
        job=f"app-{i}", vc="vc1", user="u1", status=s, gpus=g, machine="m1", attempts=a, minutes=m
    )
    for i, (s, g, a, m) in enumerate(
        [("Pass", 1, 1, 5), ("Failed", 8, 1, 90), ("Killed", 4, 2, 600), ("Pass", 2, 3, 61)] * 20
    )
)


@pytest.mark.parametrize("secret_type", list(SecretType))
def test_every_option_has_correlates_that_hide_the_value(secret_type: SecretType) -> None:
    for option in spec_for(secret_type).options:
        lines = correlate_lines(secret_type, option)
        assert lines
        for line in lines:
            text = line.template.format(run="run-1", team="atlas")
            assert line.snippet in text
            assert option not in text


def test_correlates_differ_between_options() -> None:
    for secret_type in SecretType:
        snippets = {
            correlate_lines(secret_type, o)[0].snippet for o in spec_for(secret_type).options
        }
        assert len(snippets) == len(spec_for(secret_type).options), secret_type


def test_background_lines_are_deterministic() -> None:
    a = background_lines(JOBS, random.Random(1), 10)
    b = background_lines(JOBS, random.Random(1), 10)
    assert a == b
    assert len(a) == 10


def _plan(label: Label = Label.RED_HERRING) -> ScenarioPlan:
    slot = next(s for s in slots(SPLIT_SIZES[Split.DEV]) if s.label is label)
    return plan_scenario(slot, split=Split.DEV, index=3, seed=7, jobs=JOBS)


def test_plan_is_deterministic_and_complete() -> None:
    plan = _plan()
    assert plan == _plan()
    kinds = {line.kind for line in plan.lines}
    assert {LineKind.EVIDENCE, LineKind.CORRELATE, LineKind.BACKGROUND} <= kinds
    assert plan.forbidden  # a red herring knows which tokens would make it a violation


def _template(plan: ScenarioPlan) -> Rendering:
    return asyncio.run(TemplateRenderer().render(plan, 1))


def test_template_rendering_is_valid_and_assembles() -> None:
    plan = _plan()
    rendering = _template(plan)
    assert validate(plan, rendering) == ()
    scenario = assemble(plan, rendering)
    assert len(scenario.correlates) == sum(
        1 for line in plan.lines if line.kind is LineKind.CORRELATE
    )
    assert scenario.key_evidence_ids


def _replace(rendering: Rendering, index: int, text: str) -> Rendering:
    lines = list(rendering.lines)
    lines[index] = RenderedLine(source=lines[index].source, text=text)
    return rendering.model_copy(update={"lines": tuple(lines)})


def _first(plan: ScenarioPlan, kind: LineKind) -> int:
    return next(i for i, line in enumerate(plan.lines) if line.kind is kind)


def test_validators_catch_each_failure() -> None:
    plan = _plan()
    good = _template(plan)
    background = _first(plan, LineKind.BACKGROUND)
    correlate = _first(plan, LineKind.CORRELATE)
    evidence = _first(plan, LineKind.EVIDENCE)
    secret = next(s for s in plan.secrets if s.secret_type is plan.lines[correlate].correlate_type)
    other = next(o for o in spec_for(secret.secret_type).options if o != secret.value)
    cases = {
        Check.BACKGROUND_INTACT: _replace(good, background, "rewritten scheduler line"),
        Check.CORRELATE_KEPT: _replace(good, correlate, "something vague"),
        Check.NO_VERBATIM_IN_CORRELATE: _replace(
            good, correlate, plan.lines[correlate].text + f" ({secret.value})"
        ),
        Check.REQUIRED_KEPT: _replace(good, evidence, "a paraphrase with no tokens"),
        Check.NO_FOREIGN_OPTION: _replace(good, background, plan.lines[background].text + other),
        Check.LABEL_CLEAN: _replace(
            good, evidence, plan.lines[evidence].text + " " + plan.forbidden[0]
        ),
        Check.SHAPE: good.model_copy(update={"lines": good.lines[:-1]}),
    }
    for check, rendering in cases.items():
        assert check in {i.check for i in validate(plan, rendering)}, check


def test_build_writes_a_frozen_split(tmp_path: Path) -> None:
    result = asyncio.run(build_split_v2(Split.DEV, TemplateRenderer(), jobs=JOBS, limit=6))
    assert len(result.scenarios) == 6
    info = manifest(result, background_jobs=len(JOBS))
    assert info["stages"] == {"planned": 6, "rendered": 6, "valid": 6, "reviewed": 0, "kept": 6}
    directory = write_build(result, tmp_path, background_jobs=len(JOBS))
    assert (tmp_path / "dev" / "LATEST").read_text().strip() == result.version
    assert {p.name for p in directory.iterdir()} == {
        "scenarios.jsonl",
        "plans.jsonl",
        "records.jsonl",
        "manifest.json",
    }
    site = build_site(
        built_dir=tmp_path, results_dir=tmp_path / "none", log_dir=None, out_dir=tmp_path / "site"
    )
    assert (site / "index.html").exists()
    assert (site / "data" / "site.json").stat().st_size > 0


def test_same_inputs_give_the_same_version() -> None:
    a = asyncio.run(build_split_v2(Split.DEV, TemplateRenderer(), jobs=JOBS, limit=3))
    b = asyncio.run(build_split_v2(Split.DEV, TemplateRenderer(), jobs=JOBS, limit=3))
    assert a.version == b.version
