"""Runs read the latest frozen build of a split, and fall back to the v1 generator without one."""

from __future__ import annotations

from pathlib import Path

from redaction.core.models import Split
from redaction.data.frozen import latest_version, load_built
from redaction.data.generator import build_split


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
