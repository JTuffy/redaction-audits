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
from pathlib import Path
from typing import Any, Final

from inspect_ai.log import EvalSample, read_eval_log

from redaction.core.metrics import leakage
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


def _eval_logs(log_dir: Path | None, run: str) -> list[Path]:
    return sorted((log_dir / run).glob("*.eval")) if log_dir is not None else []


def _models(log_dir: Path | None, run: str) -> list[str]:
    """Models a run used, read from its eval logs' headers."""
    models: set[str] = set()
    for path in _eval_logs(log_dir, run):
        try:
            header = read_eval_log(str(path), header_only=True)
        except (OSError, ValueError, KeyError):
            continue
        for role in (header.eval.model_roles or {}).values():
            models.add(str(getattr(role, "model", role)))
        models.add(str(header.eval.model))
    return sorted(models)


def _guess(guesses: list[dict[str, Any]], secret_type: str, value: str) -> float:
    for guess in guesses:
        if guess.get("secret_type") == secret_type:
            return float(guess.get("probabilities", {}).get(value, 0.0))
    return 0.0


def _trial(sample: EvalSample) -> dict[str, Any] | None:
    """One sample, shaped for the Runs tab: the claim, both reports, requests, rulings, scores."""
    trial = (sample.store or {}).get("trial")
    scenario = (sample.metadata or {}).get("scenario")
    if not trial or not scenario:
        return None
    secrets = []
    for secret in scenario.get("secrets", []):
        kind, value = secret["secret_type"], secret["value"]
        p_prior = _guess(trial["guesses_prior"], kind, value)
        p_unedited = _guess(trial["guesses_unedited"], kind, value)
        p_edited = _guess(trial["guesses_edited"], kind, value)
        secrets.append(
            {
                "secret_type": kind,
                "value": value,
                "p_prior": p_prior,
                "p_unedited": p_unedited,
                "p_edited": p_edited,
                "leakage": leakage(p_edited, p_unedited, p_prior),
            }
        )
    return {
        "scenario_id": scenario["scenario_id"],
        "policy": trial["policy"],
        "label": scenario["label"],
        "difficulty": scenario.get("difficulty"),
        "violation_type": scenario["violation_type"],
        "claim": scenario["claim"],
        "auditor_grade": trial["report"]["grade"],
        "finding": trial["report"]["finding"],
        "evidence": trial["report"]["evidence"],
        "edited_evidence": trial["edited"]["evidence"],
        "requests": trial["requests"],
        "rulings": trial["rulings"],
        "judge_unedited": trial["judge_unedited"],
        "judge_edited": trial["judge_edited"],
        "integrity": trial["integrity"],
        "secrets": secrets,
    }


def _samples(log_dir: Path | None, run: str) -> list[dict[str, Any]]:
    """Every scored sample of a run, read from its Inspect logs."""
    samples = []
    for path in _eval_logs(log_dir, run):
        try:
            eval_log = read_eval_log(str(path))
        except (OSError, ValueError, KeyError):
            log.warning("eval_log_unreadable", path=str(path))
            continue
        for sample in eval_log.samples or []:
            shaped = _trial(sample)
            if shaped is not None:
                samples.append(shaped)
    return samples


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
                "samples": _samples(log_dir, run.name),
            }
        )
    return runs


def _ledger(ledger_dir: Path | None) -> list[dict[str, Any]]:
    """Run records from the committed ledger, newest first; a later line for a run wins."""
    if ledger_dir is None:
        return []
    entries = {e["name"]: e for e in _jsonl(ledger_dir / "ledger.jsonl")}
    return sorted(entries.values(), key=lambda e: e["name"].split("-")[-1], reverse=True)


# Notes pages, in sidebar order. Each is a markdown file edited in place, not a log.
NOTES_PAGES: Final = ("pipeline", "protocol", "findings", "decisions")


def _notes(notes_dir: Path | None) -> list[dict[str, str]]:
    """The notes pages that exist, as slug, title (the file's H1) and markdown."""
    if notes_dir is None:
        return []
    pages = []
    for slug in NOTES_PAGES:
        path = notes_dir / f"{slug}.md"
        if path.exists():
            text = path.read_text(encoding="utf-8")
            first = text.lstrip().splitlines()[0] if text.strip() else ""
            title = first[2:].strip() if first.startswith("# ") else slug.title()
            pages.append({"slug": slug, "title": title, "markdown": text})
    return pages


def _ablations(results_dir: Path) -> list[dict[str, Any]]:
    """Marker-ablation runs: their per-scenario scores and summary table."""
    runs = []
    for run in sorted(results_dir.glob("ablation-*"), reverse=True):
        summary = run / "ablation.json"
        if summary.exists():
            runs.append(
                {
                    "name": run.name,
                    "summary": json.loads(summary.read_text(encoding="utf-8")),
                    "samples": _jsonl(run / "samples.jsonl"),
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


def build_site(
    *,
    built_dir: Path,
    results_dir: Path,
    log_dir: Path | None,
    out_dir: Path,
    ledger_dir: Path | None = None,
    notes_dir: Path | None = None,
) -> Path:
    """Write the viewer into `out_dir`, replacing what was there."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(STATIC, out_dir)
    has_viewer = log_dir is not None and _bundle_inspect(log_dir, out_dir / "viewer")
    builds, runs = _builds(built_dir), _runs(results_dir, log_dir)
    payload = {
        "builds": builds,
        "runs": runs,
        "ablations": _ablations(results_dir),
        "ledger": _ledger(ledger_dir),
        "notes": _notes(notes_dir),
        "inspect_viewer": has_viewer,
    }
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
