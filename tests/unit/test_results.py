from __future__ import annotations

import pytest

from redaction_escalation.domain.models import (
    FindingIntegrity,
    Label,
    Report,
    Scenario,
    SecretGuess,
    SecretType,
)
from redaction_escalation.domain.policies import Policy, apply_text_redaction
from redaction_escalation.domain.registry import spec_for
from redaction_escalation.domain.results import (
    SampleResult,
    TrialRecord,
    sample_result,
    secrets_in_report,
    summarize,
    summarize_all,
)
from redaction_escalation.scenarios.reports import templated_report


def _guesses(scenario: Scenario, confidence: float | None) -> tuple[SecretGuess, ...]:
    """Uniform guesses when `confidence` is None, else `confidence` on the true value."""
    guesses = []
    for secret in scenario.secrets:
        options = spec_for(secret.secret_type).options
        if confidence is None:
            probabilities = dict.fromkeys(options, 1 / len(options))
        else:
            rest = (1 - confidence) / (len(options) - 1)
            probabilities = {o: confidence if o == secret.value else rest for o in options}
        guesses.append(SecretGuess(secret_type=secret.secret_type, probabilities=probabilities))
    return tuple(guesses)


def _record(scenario: Scenario, edited_confidence: float | None) -> TrialRecord:
    report = templated_report(scenario)
    return TrialRecord(
        policy=Policy.TEXT_REDACTION,
        report=report,
        edited=apply_text_redaction(report, scenario),
        requests=(),
        rulings=(),
        viewer_unedited=80 if scenario.label is Label.VIOLATION else 30,
        viewer_edited=60 if scenario.label is Label.VIOLATION else 40,
        guesses_prior=_guesses(scenario, None),
        guesses_unedited=_guesses(scenario, 0.85),
        guesses_edited=_guesses(scenario, edited_confidence),
        integrity=FindingIntegrity.KEPT,
    )


def test_secrets_in_report_excludes_noise_secret(
    violation: Scenario, violation_report: Report
) -> None:
    present = secrets_in_report(violation, violation_report)
    assert present
    assert set(present) <= {s.secret_type for s in violation.secrets}


def test_sample_result_leakage(violation: Scenario) -> None:
    result = sample_result(violation, _record(violation, edited_confidence=0.55))
    assert result.secrets
    for outcome in result.secrets:
        assert outcome.leakage == pytest.approx(0.5)
        assert not outcome.verbatim_after_edit


def test_missing_guess_counts_as_zero(violation: Scenario) -> None:
    record = _record(violation, None).model_copy(update={"guesses_edited": ()})
    result = sample_result(violation, record)
    assert all(o.p_edited == 0.0 for o in result.secrets)
    assert all(o.leakage == 0.0 for o in result.secrets)


def _results(dev_scenarios: tuple[Scenario, ...]) -> list[SampleResult]:
    return [sample_result(s, _record(s, 0.55)) for s in dev_scenarios]


def test_summarize(dev_scenarios: tuple[Scenario, ...]) -> None:
    summary = summarize(Policy.TEXT_REDACTION, _results(dev_scenarios), seed=0)
    assert summary.samples == len(dev_scenarios)
    assert summary.auroc_unedited == 1.0
    assert summary.auroc_edited == 1.0
    assert summary.persistence is not None
    assert summary.persistence.estimate == pytest.approx(1.0)
    assert summary.leakage_mean is not None
    assert summary.leakage_mean.estimate == pytest.approx(0.5)
    assert summary.verbatim_leak_rate == 0.0
    assert summary.integrity == {FindingIntegrity.KEPT: len(dev_scenarios)}
    assert summary.request_grant_rate is None


def test_summarize_all_groups_by_policy(dev_scenarios: tuple[Scenario, ...]) -> None:
    summaries = summarize_all(_results(dev_scenarios))
    assert [s.policy for s in summaries] == [Policy.TEXT_REDACTION]


def test_summarize_rejects_empty() -> None:
    with pytest.raises(ValueError, match="no results"):
        summarize(Policy.TEXT_REDACTION, [])


def test_secret_type_round_trip() -> None:
    assert SecretType("optimizer") is SecretType.OPTIMIZER
