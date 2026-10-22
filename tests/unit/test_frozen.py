"""Runs read the latest frozen build of a split, and fall back to the v1 generator without one."""

from __future__ import annotations

from pathlib import Path

from redaction.core.models import SecretGuess, SecretType, Split
from redaction.data.frozen import latest_version, load_built
from redaction.data.generator import build_split
from redaction.data.reports import quoted_ids, templated_report
from redaction.escalation.calls import average_guesses
from redaction.escalation.scoring import secrets_in_evidence


def _write_build(root: Path, version: str) -> None:
    folder = root / "dev" / version
    folder.mkdir(parents=True)
    scenarios = build_split(Split.DEV)[:3]
    (folder / "scenarios.jsonl").write_text(
        "".join(s.model_dump_json() + "\n" for s in scenarios), encoding="utf-8"
    )
    (root / "dev" / "LATEST").write_text(version + "\n", encoding="utf-8")


def test_no_build_means_none(tmp_path: Path) -> None:
    assert latest_version(Split.DEV, tmp_path) is None
    assert load_built(Split.DEV, tmp_path) is None


def test_latest_build_is_loaded_in_order(tmp_path: Path) -> None:
    _write_build(tmp_path, "abc123")
    assert latest_version(Split.DEV, tmp_path) == "abc123"
    loaded = load_built(Split.DEV, tmp_path)
    assert loaded is not None
    assert [s.scenario_id for s in loaded] == [s.scenario_id for s in build_split(Split.DEV)[:3]]


def test_latest_pointing_at_a_missing_version_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev" / "LATEST").write_text("gone\n", encoding="utf-8")
    assert load_built(Split.DEV, tmp_path) is None


def test_context_report_quotes_correlates_and_scores_their_secrets() -> None:

    scenarios = load_built(Split.DEV, Path("data/built"))
    if scenarios is None:  # CI has no built data
        return
    scenario = next(s for s in scenarios if s.correlates)
    plain, rich = quoted_ids(scenario, context=False), quoted_ids(scenario, context=True)
    assert set(plain) < set(rich)
    assert {c.log_id for c in scenario.correlates} <= set(rich)
    assert rich == tuple(sorted(rich))  # quotes stay in log order
    scored = secrets_in_evidence(scenario, templated_report(scenario, context=True))
    assert {c.secret_type for c in scenario.correlates} <= set(scored)


def test_judge_samples_average_distributions() -> None:

    a = (SecretGuess(secret_type=SecretType.OPTIMIZER, probabilities={"AdamW": 1.0}),)
    b = (SecretGuess(secret_type=SecretType.OPTIMIZER, probabilities={"Muon": 1.0}),)
    (avg,) = average_guesses([a, b])
    assert avg.probabilities == {"AdamW": 0.5, "Muon": 0.5}
