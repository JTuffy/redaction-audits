"""The CLI end to end, offline: generate, run with the mock model, analyze."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from redaction.cli import app
from redaction.infra.settings import get_settings

pytestmark = pytest.mark.e2e


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    for name, sub in (
        ("SCENARIOS_DIR", "data"),
        ("INSPECT_LOG_DIR", "logs"),
        ("RESULTS_DIR", "out"),
    ):
        monkeypatch.setenv(f"REDACTION_{name}", str(tmp_path / sub))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_generate_writes_scenarios_and_reports(isolated_settings: Path) -> None:
    result = CliRunner().invoke(app, ["data", "generate", "--split", "dev"])
    assert result.exit_code == 0, result.output
    assert (isolated_settings / "data" / "dev_scenarios.jsonl").exists()
    assert (isolated_settings / "data" / "dev_reports.jsonl").exists()


def test_mock_run_then_analysis(isolated_settings: Path) -> None:
    result = CliRunner().invoke(
        app, ["p1", "run", "--mock", "--policy", "text_redaction", "--limit", "10"]
    )
    assert result.exit_code == 0, result.output
    (run_dir,) = (isolated_settings / "out").iterdir()
    written = {p.name for p in run_dir.iterdir()} - {"tradeoff.png"}
    assert written == {"samples.jsonl", "summary.json", "summary.md", "checks.md"}
    assert "MVP gate" in result.output


def test_analyze_empty_directory_fails(isolated_settings: Path) -> None:
    empty = isolated_settings / "empty"
    empty.mkdir()
    result = CliRunner().invoke(app, ["p1", "analyze", str(empty)])
    assert result.exit_code == 1
