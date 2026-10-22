"""Reading frozen pipeline builds (`data/built/<split>/<version>/`) back as scenarios.

Runs read the LATEST build of a split, so the scenarios a run used are exactly the ones the
viewer shows and the ledger names by version. The v1 generator (`data.generator`) remains the
fallback when no build exists, which keeps tests and CI free of built data.
"""

from __future__ import annotations

import json
from pathlib import Path

from redaction.core.models import Scenario, Split


def latest_version(split: Split, built_dir: Path) -> str | None:
    """The version hash in `<built_dir>/<split>/LATEST`, or None when the split was never built."""
    latest = built_dir / split.value / "LATEST"
    if not latest.exists():
        return None
    version = latest.read_text(encoding="utf-8").strip()
    return version if (built_dir / split.value / version / "scenarios.jsonl").exists() else None


def load_built(
    split: Split, built_dir: Path, version: str | None = None
) -> tuple[Scenario, ...] | None:
    """A split's build (`version`, else LATEST), in build order; None when it doesn't exist."""
    if version is not None and not (built_dir / split.value / version).is_dir():
        version = None
    version = version or latest_version(split, built_dir)
    if version is None:
        return None
    path = built_dir / split.value / version / "scenarios.jsonl"
    with path.open(encoding="utf-8") as handle:
        return tuple(Scenario.model_validate(json.loads(line)) for line in handle if line.strip())
