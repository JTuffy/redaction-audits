"""The whole pipeline through Inspect, offline, with the scripted mock model."""

from __future__ import annotations

from pathlib import Path

import pytest

from redaction.core.models import Split
from redaction.core.roles import Role, Stance
from redaction.escalation.analysis import load_logs, results_from_logs
from redaction.escalation.mock import mock_model
from redaction.escalation.policies import Policy
from redaction.escalation.runner import run_experiment
from redaction.escalation.summary import summarize_all, summary_table

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def log_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("inspect-logs")
    model = mock_model()
    logs = run_experiment(
        split=Split.DEV,
        policies=list(Policy),
        stance=Stance.HONEST,
        model_roles={role.value: model for role in Role},
        log_dir=directory,
    )
    assert all(log.status == "success" for log in logs)
    return directory


def test_every_sample_is_scored(log_dir: Path) -> None:
    results = results_from_logs(load_logs(log_dir))
    assert len(results) == 40 * len(Policy)


def test_summaries(log_dir: Path) -> None:
    summaries = summarize_all(results_from_logs(load_logs(log_dir)))
    assert [s.policy for s in summaries] == list(Policy)
    by_policy = {s.policy: s for s in summaries}
    # The scripted advocate asks for every registry value and the honest executor grants all, so
    # every policy removes all planted values and nothing leaks verbatim.
    for summary in summaries:
        assert summary.verbatim_leak_rate == 0.0
    assert by_policy[Policy.TEXT_REDACTION].request_grant_rate is None
    assert by_policy[Policy.CONTEXTUAL_REWRITE].request_grant_rate == 1.0
    assert "contextual_rewrite" in summary_table(summaries)
