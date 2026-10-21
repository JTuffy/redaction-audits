"""Static viewer: the data pipeline's latest builds and P1 runs, as one folder of files.

`build_site` copies the page in `static/` and writes `data/site.json` next to it. When Inspect
logs exist it also bundles Inspect View into `viewer/`, which the Runs tab links to for full
transcripts. The output needs no server beyond static hosting (tailnet-serve, Pages, a folder).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from redaction.infra.log_setup import get_logger

log = get_logger(__name__)
STATIC = Path(__file__).parent / "static"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _build_payload(directory: Path) -> dict[str, Any]:
    """One frozen build, shaped for the page: logs carry their planned kind."""
    plans = {p["scenario_id"]: p for p in _jsonl(directory / "plans.jsonl")}
    scenarios = []
    for s in _jsonl(directory / "scenarios.jsonl"):
        plan = plans.get(s["scenario_id"], {})
        kinds = [line["kind"] for line in plan.get("lines", [])]
        for entry, kind in zip(s["logs"], kinds, strict=False):
            entry["kind"] = kind
        s["variant"] = plan.get("variant", "")
        scenarios.append(s)
    return {
        "manifest": json.loads((directory / "manifest.json").read_text(encoding="utf-8")),
        "records": _jsonl(directory / "records.jsonl"),
        "scenarios": scenarios,
    }


def _builds(built_dir: Path) -> list[dict[str, Any]]:
    """The LATEST build of each split."""
    builds = []
    order = {"dev": 0, "val": 1, "test": 2}
    split_dirs = sorted(
        (p for p in built_dir.glob("*") if p.is_dir()), key=lambda p: order.get(p.name, 9)
    )
    for split_dir in split_dirs:
        latest = split_dir / "LATEST"
        if latest.exists():
            directory = split_dir / latest.read_text(encoding="utf-8").strip()
            if (directory / "manifest.json").exists():
                builds.append(_build_payload(directory))
    return builds


def _models(log_dir: Path | None, run: str) -> list[str]:
    """Models a run used, read from its eval logs' headers (an .eval file is a zip)."""
    if log_dir is None:
        return []
    models: set[str] = set()
    for path in (log_dir / run).glob("*.eval"):
        try:
            with zipfile.ZipFile(path) as archive:
                header = json.loads(archive.read("header.json"))
            roles = header["eval"].get("model_roles") or {}
            models.update(r["model"] if isinstance(r, dict) else str(r) for r in roles.values())
            models.add(str(header["eval"]["model"]))
        except (KeyError, OSError, ValueError, zipfile.BadZipFile):
            continue
    return sorted(models)


def _runs(results_dir: Path, log_dir: Path | None) -> list[dict[str, Any]]:
    """Summaries written by `p1 analyze`, newest first."""
    runs = []
    for run in sorted(results_dir.glob("p1-*"), reverse=True):
        summary = run / "summary.json"
        if not summary.exists():
            continue
        checks = []
        checks_md = run / "checks.md"
        lines = checks_md.read_text(encoding="utf-8").splitlines()[2:] if checks_md.exists() else []
        for line in lines:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 3:  # noqa: PLR2004
                checks.append({"name": cells[0], "result": cells[1], "detail": cells[2]})
        runs.append(
            {
                "name": run.name,
                "models": _models(log_dir, run.name),
                "summary": json.loads(summary.read_text(encoding="utf-8")),
                "checks": checks,
            }
        )
    return runs


def _bundle_inspect(log_dir: Path, out: Path) -> bool:
    """Bundle Inspect View with the logs; False if there are no logs or the CLI fails."""
    if not log_dir.exists() or not any(log_dir.rglob("*.eval")):
        return False
    name = "inspect.exe" if sys.platform == "win32" else "inspect"
    command = [
        str(Path(sys.executable).parent / name),
        "view",
        "bundle",
        "--log-dir",
        str(log_dir),
        "--output-dir",
        str(out),
        "--overwrite",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        log.warning("inspect_bundle_failed", stderr=result.stderr[-500:])
        return False
    return True


def build_site(*, built_dir: Path, results_dir: Path, log_dir: Path | None, out_dir: Path) -> Path:
    """Write the viewer into `out_dir`, replacing what was there."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(STATIC, out_dir)
    has_viewer = log_dir is not None and _bundle_inspect(log_dir, out_dir / "viewer")
    builds, runs = _builds(built_dir), _runs(results_dir, log_dir)
    payload = {"builds": builds, "runs": runs, "inspect_viewer": has_viewer}
    (out_dir / "data").mkdir(exist_ok=True)
    (out_dir / "data" / "site.json").write_text(json.dumps(payload), encoding="utf-8")
    log.info(
        "site_written",
        directory=str(out_dir),
        builds=len(builds),
        runs=len(runs),
        inspect_viewer=has_viewer,
    )
    return out_dir
