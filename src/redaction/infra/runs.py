"""The run ledger: every real run leaves a record in git, even though logs and results do not.

`logs/` and `results/` are git-ignored because they are large and regenerable. The ledger is
small and committed: one line per run in `runs/ledger.jsonl`, and a folder per run holding its
`run.json` (what was run, from which commit, why, and the tokens it used) plus copies of the
small summary files. A run can then be traced to the exact code and settings that produced it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from redaction.infra.log_setup import get_logger

log = get_logger(__name__)

# Small enough to commit; Inspect logs and per-sample texts stay in logs/ and results/.
COPIED_FILES: Final = (
    "summary.md",
    "summary.json",
    "checks.md",
    "samples.jsonl",
    "tradeoff.png",
    "ablation.md",
    "ablation.json",
)


def _git(*args: str) -> str:
    try:
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return done.stdout.strip()


def git_state() -> dict[str, Any]:
    """The commit a run came from, and whether tracked files had uncommitted changes."""
    return {
        "commit": _git("rev-parse", "HEAD") or None,
        "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
    }


def record_run(
    *,
    name: str,
    kind: str,
    purpose: str,
    config: dict[str, Any],
    results_dir: Path,
    ledger_dir: Path,
) -> Path:
    """Write the run's ledger entry and copy its summary files. Returns the run's folder."""
    entry: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "purpose": purpose,
        "command": " ".join(["redaction", *sys.argv[1:]]),
        **git_state(),
        "config": config,
    }
    folder = ledger_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    for file_name in COPIED_FILES:
        source = results_dir / file_name
        if source.exists():
            shutil.copy2(source, folder / file_name)
    with (ledger_dir / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    if entry["dirty"]:
        log.warning("run_recorded_from_dirty_tree", run=name, commit=entry["commit"])
    log.info("run_recorded", run=name, folder=str(folder))
    return folder
