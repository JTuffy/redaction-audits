"""Scripted adversaries and the generalize policy on entangled scenarios."""

from __future__ import annotations

import asyncio

from redaction.core.models import Difficulty, Label, Report, Scenario, Split, ViolationType
from redaction.core.roles import Stance
from redaction.data.generator import ScenarioSpec
from redaction.data.pipeline.plan import plan_scenario
from redaction.data.pipeline.render import TemplateRenderer, assemble
from redaction.data.reports import templated_report
from redaction.escalation.adversary import scripted_requests
from redaction.escalation.policies import Policy, effective_rulings, redact


def _scenario(t: ViolationType, label: Label, difficulty: Difficulty | None = None) -> Scenario:
    spec = ScenarioSpec(t, label, difficulty)
    plan = plan_scenario(spec, split=Split.DEV, index=0, seed=101, jobs=(), depth="entangled")
    return assemble(plan, asyncio.run(TemplateRenderer().render(plan, 1)))


def _text(report: Report) -> str:
    return "\n".join(q.quote for q in report.evidence)


def test_blatant_asks_to_remove_every_key_line() -> None:
    scenario = _scenario(ViolationType.OPTED_OUT_DATA, Label.VIOLATION)
    report = templated_report(scenario, context=True)
    requests = scripted_requests(scenario, report, Stance.SCRIPTED_BLATANT)
    assert len(requests) == len(scenario.key_evidence_ids)
    edited = redact(Policy.SELF_REDACTION, report, scenario, requests)
    keys = {q.quote for q in report.evidence if q.log_id in scenario.key_evidence_ids}
    assert not any(k in _text(edited) for k in keys)


def test_link_break_merges_two_customers_under_self_redaction() -> None:
    scenario = _scenario(ViolationType.OPTED_OUT_DATA, Label.RED_HERRING, Difficulty.HARD)
    report = templated_report(scenario, context=True)
    requests = scripted_requests(scenario, report, Stance.SCRIPTED_LINK)
    assert {r.span for r in requests} >= {c.value for c in scenario.confidential}
    edited = _text(redact(Policy.SELF_REDACTION, report, scenario, requests))
    for value in (s.value for s in scenario.redactable()):
        assert value not in edited
    assert "[REDACTED: customer name]" in edited
    assert effective_rulings(Policy.TEXT_REDACTION, requests, ()) == ()


def _generalized(t: ViolationType, label: Label, difficulty: Difficulty | None = None) -> str:
    scenario = _scenario(t, label, difficulty)
    return _text(redact(Policy.TEXT_GENERALIZE, templated_report(scenario), scenario))


def test_generalize_keeps_the_threshold_comparison() -> None:
    compute = ViolationType.UNREPORTED_COMPUTE
    assert "an allocation above the" in _generalized(compute, Label.VIOLATION)
    assert "an allocation below the" in _generalized(compute, Label.RED_HERRING, Difficulty.HARD)


def test_generalize_keeps_the_date_order() -> None:
    skipped = ViolationType.SKIPPED_EVAL
    assert "a date before the eval's scheduled finish" in _generalized(skipped, Label.VIOLATION)
    hard = _generalized(skipped, Label.RED_HERRING, Difficulty.HARD)
    assert "a date after the eval's scheduled finish" in hard


def test_generalize_uses_pseudonyms_for_entities() -> None:
    text = _generalized(ViolationType.OPTED_OUT_DATA, Label.RED_HERRING, Difficulty.HARD)
    assert "Customer A" in text
    assert "Customer B" in text
