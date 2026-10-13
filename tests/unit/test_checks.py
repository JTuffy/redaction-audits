from __future__ import annotations

from pathlib import Path

from redaction.core.models import Difficulty, Label, Scenario
from redaction.escalation.checks import (
    check_difficulty_order,
    check_unedited_auroc,
    checks_table,
    mvp_checks,
)
from redaction.escalation.plots import plot_tradeoff
from redaction.escalation.scoring import SampleResult, sample_result
from redaction.escalation.summary import summarize_all
from tests.unit.test_results import _record

_RED_HERRING_SCORE = {Difficulty.EASY: 10, Difficulty.MEDIUM: 25, Difficulty.HARD: 45}


def _results(scenarios: tuple[Scenario, ...], *, ordered: bool = True) -> list[SampleResult]:
    results = []
    for scenario in scenarios:
        result = sample_result(scenario, _record(scenario, 0.55))
        if scenario.difficulty is not None:
            score = _RED_HERRING_SCORE[scenario.difficulty] if ordered else 30
            result = result.model_copy(update={"judge_unedited": score})
        results.append(result)
    return results


def test_auroc_check_passes_when_separable(dev_scenarios: tuple[Scenario, ...]) -> None:
    check = check_unedited_auroc(_results(dev_scenarios))
    assert check.passed is True


def test_auroc_check_undecided_without_red_herrings(dev_scenarios: tuple[Scenario, ...]) -> None:
    only_violations = [r for r in _results(dev_scenarios) if r.label is Label.VIOLATION]
    assert check_unedited_auroc(only_violations).passed is None


def test_difficulty_order(dev_scenarios: tuple[Scenario, ...]) -> None:
    assert check_difficulty_order(_results(dev_scenarios)).passed is True
    assert check_difficulty_order(_results(dev_scenarios, ordered=False)).passed is False


def test_checks_table_lists_every_check(dev_scenarios: tuple[Scenario, ...]) -> None:
    checks = mvp_checks(_results(dev_scenarios))
    table = checks_table(checks)
    assert all(c.name in table for c in checks)


def test_plot_tradeoff_writes_png(dev_scenarios: tuple[Scenario, ...], tmp_path: Path) -> None:
    path = plot_tradeoff(summarize_all(_results(dev_scenarios)), tmp_path / "tradeoff.png")
    assert path is not None
    assert path.stat().st_size > 0


def test_plot_tradeoff_skips_empty(tmp_path: Path) -> None:
    assert plot_tradeoff((), tmp_path / "tradeoff.png") is None
