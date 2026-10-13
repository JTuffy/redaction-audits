from __future__ import annotations

from collections import Counter

import pytest

from redaction_escalation.domain.models import Difficulty, Label, Scenario, Split, ViolationType
from redaction_escalation.scenarios.blueprints import BLUEPRINTS
from redaction_escalation.scenarios.generator import SPLIT_SIZES, build_split
from redaction_escalation.scenarios.reports import BASE_GRADES, GRADE_JITTER, templated_report


def test_every_violation_type_has_a_blueprint() -> None:
    assert set(BLUEPRINTS) == set(ViolationType)


@pytest.mark.parametrize("split", list(Split))
def test_split_sizes(split: Split) -> None:
    scenarios = build_split(split)
    counts = Counter(s.label for s in scenarios)
    size = SPLIT_SIZES[split]
    assert counts == {
        Label.VIOLATION: size.violations,
        Label.RED_HERRING: size.red_herrings,
        Label.CLEAN: size.clean,
    }
    assert len({s.scenario_id for s in scenarios}) == size.total


def test_dev_covers_every_type_and_difficulty(dev_scenarios: tuple[Scenario, ...]) -> None:
    herrings = {(s.violation_type, s.difficulty) for s in dev_scenarios if s.difficulty}
    assert herrings == {(t, d) for t in ViolationType for d in Difficulty}


def test_generation_is_deterministic(dev_scenarios: tuple[Scenario, ...]) -> None:
    assert build_split(Split.DEV) == dev_scenarios
    assert build_split(Split.DEV, seed=7) != dev_scenarios


def test_scenario_shape(dev_scenarios: tuple[Scenario, ...]) -> None:
    for scenario in dev_scenarios:
        blueprint = BLUEPRINTS[scenario.violation_type]
        assert len(scenario.secrets) == len(blueprint.core_secrets) + 1
        assert len(scenario.key_evidence_ids) == 3
        assert [e.timestamp for e in scenario.logs] == sorted(e.timestamp for e in scenario.logs)
        assert "{" not in "".join(e.text for e in scenario.logs)


def test_report_quotes_key_evidence_verbatim(dev_scenarios: tuple[Scenario, ...]) -> None:
    for scenario in dev_scenarios:
        report = templated_report(scenario)
        by_id = {e.log_id: e.text for e in scenario.logs}
        assert [q.log_id for q in report.evidence] == list(scenario.key_evidence_ids)
        assert all(q.quote == by_id[q.log_id] for q in report.evidence)
        base = BASE_GRADES[(scenario.label, scenario.difficulty)]
        assert abs(report.grade - base) <= GRADE_JITTER
