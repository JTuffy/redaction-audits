"""The marker ablation's conditions, its summary, and the run ledger."""

from __future__ import annotations

import json
from pathlib import Path

from redaction.core.models import Label, Scenario, Split
from redaction.core.registry import REGISTRY, redaction_marker
from redaction.data.generator import build_split
from redaction.data.reports import templated_report
from redaction.escalation.ablation import Condition, variant
from redaction.escalation.ablation_task import ablation_table, summarize
from redaction.escalation.pseudonyms import PSEUDONYMS
from redaction.infra.runs import record_run


def _scenario_with_quoted_secret() -> Scenario:
    for scenario in build_split(Split.DEV):
        text = templated_report(scenario).evidence_text()
        if any(s.value in text for s in scenario.secrets):
            return scenario
    raise AssertionError("no dev scenario quotes a secret")


def test_unedited_is_the_report() -> None:
    scenario = _scenario_with_quoted_secret()
    report = templated_report(scenario)
    assert variant(report, scenario, Condition.UNEDITED) == report


def test_marker_and_pseudonym_remove_the_same_values() -> None:
    scenario = _scenario_with_quoted_secret()
    report = templated_report(scenario)
    marked = variant(report, scenario, Condition.MARKER).evidence_text()
    pseudo = variant(report, scenario, Condition.PSEUDONYM).evidence_text()
    for secret in scenario.secrets:
        assert secret.value not in marked
        assert secret.value not in pseudo
    assert "[REDACTED" in marked
    assert "[REDACTED" not in pseudo


def test_marker_only_keeps_values_and_adds_markers() -> None:
    scenario = _scenario_with_quoted_secret()
    report = templated_report(scenario)
    shown = variant(report, scenario, Condition.MARKER_ONLY).evidence_text()
    quoted = [s for s in scenario.secrets if s.value in report.evidence_text()]
    for secret in quoted:
        assert secret.value in shown
        assert redaction_marker(secret.secret_type) in shown


def test_pseudonyms_are_never_registry_options() -> None:
    options = {o for spec in REGISTRY.values() for o in spec.options}
    assert set(PSEUDONYMS) == set(REGISTRY)
    assert not options & set(PSEUDONYMS.values())


def _row(sid: str, label: Label, condition: Condition, score: int) -> dict[str, object]:
    return {
        "scenario_id": sid,
        "label": label.value,
        "difficulty": None,
        "violation_type": "x",
        "condition": condition.value,
        "score": score,
        "evidence": "",
    }


def test_summary_counts_wrong_way_shifts() -> None:
    rows = [
        _row("a", Label.CLEAN, Condition.UNEDITED, 10),
        _row("a", Label.CLEAN, Condition.MARKER, 60),
        _row("b", Label.VIOLATION, Condition.UNEDITED, 90),
        _row("b", Label.VIOLATION, Condition.MARKER, 50),
    ]
    summary = {(s["group"], s["condition"]): s for s in summarize(rows)}
    assert summary[("clean", "marker")]["mean_shift"] == 50
    assert summary[("clean", "marker")]["wrong_way"] == 1
    assert summary[("violation", "marker")]["wrong_way"] == 1
    assert "wrong-way" in ablation_table(list(summary.values()))


def test_record_run_writes_entry_and_copies(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "summary.md").write_text("table", encoding="utf-8")
    (results / "big.eval").write_text("not copied", encoding="utf-8")
    folder = record_run(
        name="p1-test",
        kind="p1",
        purpose="unit test",
        config={"stance": "honest"},
        results_dir=results,
        ledger_dir=tmp_path / "runs",
    )
    entry = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert entry["purpose"] == "unit test"
    assert entry["config"] == {"stance": "honest"}
    assert "commit" in entry
    assert (folder / "summary.md").exists()
    assert not (folder / "big.eval").exists()
    lines = (tmp_path / "runs" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
