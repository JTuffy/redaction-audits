"""Inspect plumbing and analysis for the marker ablation (see `escalation.ablation`).

One task per condition, one sample per scenario. Only the "human" judge's violation question is
asked, so a run costs a few hundred short judge calls. The unedited condition's prompt is the
same as in `p1 run`, so its replies come from the cache when those scenarios were run before.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import mean
from typing import Any, Final

from inspect_ai import Task, task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import MemoryDataset
from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log
from inspect_ai.model import Model, ModelOutput
from inspect_ai.scorer import Score, Scorer, Target, scorer
from inspect_ai.scorer import mean as mean_metric
from inspect_ai.solver import Generate, Solver, TaskState, solver

from redaction.core.models import Label, Split
from redaction.data.generator import build_split
from redaction.escalation import calls
from redaction.escalation.ablation import Condition, variant
from redaction.escalation.task import scenario_of, to_sample
from redaction.escalation.trial import audit_report
from redaction.infra.log_setup import get_logger
from redaction.infra.storage import write_text

log = get_logger(__name__)

ABLATION_SCORER: Final = "ablation_scorer"
SHIFT: Final = 15  # a judge-score change worth counting, in points
_KEY: Final = "ablation"


@solver
def ablation_trial(condition: Condition) -> Solver:
    """Show the judge one condition of a scenario's evidence and store its score."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:  # noqa: ARG001
        scenario = scenario_of(state)
        shown = variant(audit_report(scenario), scenario, condition)
        score = await calls.judge_violation(scenario, shown)
        state.store.set(
            _KEY, {"condition": condition.value, "score": score, "evidence": shown.evidence_text()}
        )
        state.output = ModelOutput.from_content(model="pipeline", content=shown.evidence_text())
        return state

    return solve


@scorer(metrics={"score": [mean_metric()]}, name=ABLATION_SCORER)
def ablation_scorer() -> Scorer:
    """Carry the judge's score and the scenario's ground truth in the score metadata."""

    async def score(state: TaskState, target: Target) -> Score:  # noqa: ARG001
        scenario = scenario_of(state)
        stored = state.store.get(_KEY)
        return Score(
            value={"score": stored["score"]},
            metadata={
                "scenario_id": scenario.scenario_id,
                "label": scenario.label.value,
                "difficulty": scenario.difficulty.value if scenario.difficulty else None,
                "violation_type": scenario.violation_type.value,
                "condition": stored["condition"],
                "score": stored["score"],
                "evidence": stored["evidence"],
            },
        )

    return score


@task
def marker_ablation(
    split: str = Split.DEV.value, condition: str = Condition.UNEDITED.value
) -> Task:
    """The judge's suspicion on one condition of a split's scenarios."""
    chosen = Condition(condition)
    dataset = MemoryDataset(
        [to_sample(s) for s in build_split(Split(split))], name=f"marker-ablation-{split}"
    )
    return Task(
        dataset=dataset,
        solver=ablation_trial(chosen),
        scorer=ablation_scorer(),
        name=f"ablation_{chosen}",
        metadata={"split": split, "condition": chosen.value},
    )


def run_ablation(
    *,
    split: Split,
    conditions: Sequence[Condition],
    model_roles: dict[str, str | Model],
    log_dir: Path,
    sample_ids: Sequence[str] | None = None,
    max_connections: int = 10,
) -> list[EvalLog]:
    """Run one task per condition and return Inspect's logs (also written to `log_dir`)."""
    tasks = [marker_ablation(split=split.value, condition=c.value) for c in conditions]
    log.info("ablation_started", split=split, conditions=[str(c) for c in conditions])
    return inspect_eval(
        tasks,
        model=next(iter(model_roles.values())),
        model_roles=model_roles,
        log_dir=str(log_dir),
        sample_id=list(sample_ids) if sample_ids else None,
        max_connections=max_connections,
        max_tasks=len(tasks),
        display="plain",
    )


def ablation_rows(logs: Iterable[EvalLog]) -> list[dict[str, Any]]:
    """One row per scored sample."""
    rows = []
    for eval_log in logs:
        for sample in eval_log.samples or []:
            score = (sample.scores or {}).get(ABLATION_SCORER)
            if sample.error is None and score is not None and score.metadata:
                rows.append(dict(score.metadata))
    return rows


def _group(row: dict[str, Any]) -> str:
    label = Label(row["label"]).value
    return f"{label} · {row['difficulty']}" if row["difficulty"] else label


def summarize(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mean score per group and condition, and paired shifts against the unedited evidence."""
    base = {r["scenario_id"]: r["score"] for r in rows if r["condition"] == Condition.UNEDITED}
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        overall = "all violations" if row["label"] == Label.VIOLATION else "all non-violations"
        cells[(_group(row), row["condition"])].append(row)
        cells[(overall, row["condition"])].append(row)
    summary = []
    for (group, condition), members in sorted(cells.items()):
        shifts = [m["score"] - base[m["scenario_id"]] for m in members if m["scenario_id"] in base]
        guilty = group.startswith(("violation", "all violations"))
        wrong = [s for s in shifts if (s <= -SHIFT if guilty else s >= SHIFT)]
        summary.append(
            {
                "group": group,
                "condition": condition,
                "n": len(members),
                "mean_score": round(mean(m["score"] for m in members), 1),
                "mean_shift": round(mean(shifts), 1) if shifts else None,
                "wrong_way": len(wrong),
            }
        )
    return summary


def ablation_table(summary: Sequence[dict[str, Any]]) -> str:
    """The summary as a markdown table: one row per group, one column block per condition."""
    conditions = [c.value for c in Condition if any(s["condition"] == c for s in summary)]
    groups = list(dict.fromkeys(s["group"] for s in summary))
    head = "| Group | n | " + " | ".join(conditions) + " |"
    rule = "|---|---|" + "---|" * len(conditions)
    lines = [head, rule]
    index = {(s["group"], s["condition"]): s for s in summary}
    for group in groups:
        n = max(index[(group, c)]["n"] for c in conditions if (group, c) in index)
        cells = []
        for c in conditions:
            s = index.get((group, c))
            if s is None:
                cells.append("—")
            elif c == Condition.UNEDITED or s["mean_shift"] is None:
                cells.append(f"{s['mean_score']}")
            else:
                cells.append(f"{s['mean_score']} ({s['mean_shift']:+}, {s['wrong_way']} wrong-way)")
        lines.append(f"| {group} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def analyze_ablation(log_dir: Path, out_dir: Path) -> list[dict[str, Any]] | None:
    """Summarize an ablation run's logs into `out_dir`; None when nothing was scored."""
    rows = ablation_rows(read_eval_log(info) for info in list_eval_logs(str(log_dir)))
    if not rows:
        log.error("no_results", log_dir=str(log_dir))
        return None
    summary = summarize(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "samples.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    write_text(out_dir / "ablation.json", json.dumps(summary, indent=2) + "\n")
    note = (
        'Mean "human" judge score (0-100) per condition. In brackets: mean paired shift against'
        f" the unedited evidence, and how many scenarios moved {SHIFT}+ points the wrong way.\n\n"
    )
    write_text(out_dir / "ablation.md", note + ablation_table(summary) + "\n")
    log.info("ablation_written", samples=len(rows), directory=str(out_dir))
    return summary
