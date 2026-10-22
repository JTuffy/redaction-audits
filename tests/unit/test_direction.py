"""docs/direction.toml stays consistent with the ledger and the Findings page it points to."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from redaction.viewer.build import _decisions, _direction

ROOT = Path(__file__).parents[2]
STATUSES = {"planned", "running", "open", "settled", "blocked"}


def test_direction_file_is_consistent() -> None:
    direction = _direction(ROOT / "docs" / "direction.toml")
    assert direction is not None
    for key in ("question", "hypothesis", "focus", "next", "updated"):
        assert direction["project"][key]
    ledger = {
        json.loads(line)["name"]
        for line in (ROOT / "runs" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    }
    findings = (ROOT / "docs" / "notes" / "findings.md").read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (.+)$", findings, re.MULTILINE))
    seen: set[str] = set()
    ids = [x["id"] for x in direction["experiment"]]
    assert len(ids) == len(set(ids))
    for x in direction["experiment"]:
        assert x["status"] in STATUSES, x["id"]
        assert not x["finding"] or x["finding"] in headings, x["finding"]
        missing = set(x["runs"]) - ledger
        assert not missing, (x["id"], missing)
        assert not set(x["runs"]) & seen, x["id"]  # a run belongs to one thread
        seen |= set(x["runs"])


def test_decisions_table_parses(tmp_path: Path) -> None:
    (tmp_path / "decisions.md").write_text(
        "| Date | Decision | Why |\n|---|---|---|\n| 2026-10-22 | Do `x` | Because. |\n",
        encoding="utf-8",
    )
    assert _decisions(tmp_path) == [{"date": "2026-10-22", "decision": "Do `x`", "why": "Because."}]


def test_toml_module_is_available() -> None:
    assert tomllib.loads('a = "b"') == {"a": "b"}
