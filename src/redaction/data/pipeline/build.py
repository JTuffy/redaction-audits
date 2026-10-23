"""Running the pipeline for one split: plan, render, validate, review, freeze.

Output goes to `<out>/<split>/<version>/`, where the version is a hash of the plans and the
renderer, so a frozen dataset is never overwritten by a different one:

- `scenarios.jsonl`  kept scenarios, the input to P1 and P2
- `plans.jsonl`      every plan, kept or not (the ground truth before rendering)
- `records.jsonl`    one record per planned scenario: attempts, issues, review, line counts
- `manifest.json`    stage counts, issue counts and settings, for the viewer and for papers
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from redaction.core.models import Frozen, Label, Scenario, Split
from redaction.data.background import PhillyJob
from redaction.data.blueprints import BENCHMARK_SETS, blueprints_for
from redaction.data.generator import DEFAULT_SEEDS, SPLIT_SIZES, slots
from redaction.data.pipeline.plan import LineKind, ScenarioPlan, plan_scenario
from redaction.data.pipeline.render import Renderer, Rendering, assemble
from redaction.data.pipeline.surface import surface_auroc
from redaction.data.pipeline.validate import Issue, validate


class Verdict(StrEnum):
    """A blind reviewer's reading of a scenario."""

    VIOLATION = "violation"
    NO_VIOLATION = "no_violation"


class Review(Frozen):
    """What the reviewer concluded from the logs alone."""

    verdict: Verdict
    reason: str


class Reviewer(Protocol):
    """Reads a scenario blind (claim and logs only) and says whether it shows a violation."""

    name: str

    async def review(self, scenario: Scenario) -> Review:
        """Classify one scenario."""
        ...


class Status(StrEnum):
    """Where a planned scenario ended up."""

    KEPT = "kept"
    INVALID = "invalid"  # failed the code checks on every attempt
    REVIEW_DISAGREES = "review_disagrees"  # valid, but the reviewer read the label differently


class ScenarioRecord(Frozen):
    """The pipeline's history for one planned scenario."""

    scenario_id: str
    label: Label
    violation_type: str
    difficulty: str | None
    status: Status
    attempts: int
    issues: tuple[Issue, ...]
    review: Review | None
    lines_by_kind: dict[str, int]
    refusals: int = 0  # attempts the renderer declined outright
    rendered_by: str | None = None  # the model behind the kept rendering


class BuildResult(Frozen):
    """Everything one build produced."""

    split: Split
    version: str
    renderer: str
    reviewer: str | None
    cues: str = "verbatim"  # whether evidence cues had to survive rendering word for word
    depth: str = "shallow"  # which blueprint set the plans use
    background: str = "philly"  # "lab" (evidence-like lines) or "philly" (scheduler records)
    plans: tuple[ScenarioPlan, ...]
    scenarios: tuple[Scenario, ...]
    records: tuple[ScenarioRecord, ...]


def _agrees(review: Review, label: Label) -> bool:
    return (review.verdict is Verdict.VIOLATION) == (label is Label.VIOLATION)


def _version(plans: tuple[ScenarioPlan, ...], settings: str) -> str:
    """A hash of the plans and every setting that changes the output (renderer, reviewer, cues)."""
    digest = hashlib.sha256(settings.encode())
    for plan in plans:
        # Shallow plans hash as they did before `depth` existed, so old versions stay valid.
        exclude = {"depth"} if plan.depth == "shallow" else set()
        if not plan.confidential:
            exclude.add("confidential")
        digest.update(plan.model_dump_json(exclude=exclude or None).encode())
    return digest.hexdigest()[:10]


async def _run_one(
    plan: ScenarioPlan,
    renderer: Renderer,
    reviewer: Reviewer | None,
    max_attempts: int,
    *,
    paraphrase: bool = False,
) -> tuple[Scenario | None, ScenarioRecord]:
    issues: tuple[Issue, ...] = ()
    review: Review | None = None
    status = Status.INVALID
    scenario: Scenario | None = None
    attempt = 0
    refusals = 0
    rendered_by: str | None = None
    for attempt in range(1, max_attempts + 1):
        rendering: Rendering = await renderer.render(plan, attempt)
        refusals += rendering.refused
        issues = validate(plan, rendering, paraphrase=paraphrase)
        if issues:
            continue
        candidate = assemble(plan, rendering)
        review = await reviewer.review(candidate) if reviewer else None
        if review is None or _agrees(review, plan.label):
            scenario, status, rendered_by = candidate, Status.KEPT, rendering.renderer
            break
        status = Status.REVIEW_DISAGREES
    record = ScenarioRecord(
        scenario_id=plan.scenario_id,
        label=plan.label,
        violation_type=str(plan.violation_type),
        difficulty=None if plan.difficulty is None else str(plan.difficulty),
        status=status,
        attempts=attempt,
        issues=issues,
        review=review,
        lines_by_kind=dict(Counter(str(line.kind) for line in plan.lines)),
        refusals=refusals,
        rendered_by=rendered_by,
    )
    return scenario, record


async def build_split_v2(
    split: Split,
    renderer: Renderer,
    *,
    jobs: tuple[PhillyJob, ...] = (),
    reviewer: Reviewer | None = None,
    seed: int | None = None,
    limit: int | None = None,
    max_attempts: int = 3,
    paraphrase: bool = False,
    concurrency: int = 8,
    depth: str = "shallow",
    background: str = "lab",
) -> BuildResult:
    """Plan, render, validate and (optionally) review every scenario in a split.

    Scenarios run concurrently (at most `concurrency` at once); output order is plan order.
    """
    split_seed = DEFAULT_SEEDS[split] if seed is None else seed
    sets = BENCHMARK_SETS if depth == "benchmark" else (depth,)
    planned = [
        (i, slot, one_set)
        for one_set in sets
        for i, slot in enumerate(slots(SPLIT_SIZES[split]))
        if slot.violation_type in blueprints_for(one_set)
    ][:limit]
    plans = tuple(
        plan_scenario(
            slot,
            split=split,
            index=i,
            seed=split_seed,
            jobs=jobs,
            depth=one_set,
            background=background,
        )
        for i, slot, one_set in planned
    )
    attempts = 1 if renderer.name == "template" else max_attempts  # templates are deterministic
    gate = asyncio.Semaphore(concurrency)

    async def one(plan: ScenarioPlan) -> tuple[Scenario | None, ScenarioRecord]:
        async with gate:
            return await _run_one(plan, renderer, reviewer, attempts, paraphrase=paraphrase)

    outcomes = await asyncio.gather(*(one(plan) for plan in plans))
    reviewer_name = reviewer.name if reviewer else "none"
    cues = "paraphrase" if paraphrase else "verbatim"
    return BuildResult(
        split=split,
        version=_version(plans, f"{renderer.name}|{reviewer_name}|{cues}"),
        cues=cues,
        depth=depth,
        background=background,
        renderer=renderer.name,
        reviewer=reviewer.name if reviewer else None,
        plans=plans,
        scenarios=tuple(s for s, _ in outcomes if s is not None),
        records=tuple(r for _, r in outcomes),
    )


def manifest(result: BuildResult, *, background_jobs: int) -> dict[str, object]:
    """Stage counts, issue counts and settings for one build."""
    records = result.records
    issue_counts = Counter(str(i.check) for r in records for i in r.issues)
    valid = sum(1 for r in records if r.status is not Status.INVALID)
    lines = [sum(r.lines_by_kind.values()) for r in records]
    return {
        "split": str(result.split),
        "version": result.version,
        "renderer": result.renderer,
        "reviewer": result.reviewer,
        "cues": result.cues,
        "depth": result.depth,
        "background": result.background,
        "surface_auroc": None if (a := surface_auroc(result.plans)) is None else round(a, 3),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "background_jobs": background_jobs,
        "stages": {
            "planned": len(records),
            "rendered": len(records),
            "valid": valid,
            "reviewed": valid if result.reviewer else 0,
            "kept": len(result.scenarios),
        },
        "issues": dict(issue_counts),
        "refusals": sum(r.refusals for r in records),
        "rendered_by": dict(Counter(r.rendered_by for r in records if r.rendered_by)),
        "labels": dict(Counter(str(r.label) for r in records if r.status is Status.KEPT)),
        "lines": {
            "min": min(lines, default=0),
            "max": max(lines, default=0),
            "mean": round(sum(lines) / len(lines), 1) if lines else 0,
        },
        "line_kinds": {
            str(k): sum(r.lines_by_kind.get(str(k), 0) for r in records) for k in LineKind
        },
    }


def write_build(
    result: BuildResult, out_dir: Path, *, background_jobs: int, latest: bool = True
) -> Path:
    """Freeze a build to disk and, unless `latest` is off, point `<out>/<split>/LATEST` at it."""
    directory = out_dir / str(result.split) / result.version
    directory.mkdir(parents=True, exist_ok=True)
    for name, items in (
        ("scenarios", result.scenarios),
        ("plans", result.plans),
        ("records", result.records),
    ):
        with (directory / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            handle.writelines(item.model_dump_json() + "\n" for item in items)
    (directory / "manifest.json").write_text(
        json.dumps(manifest(result, background_jobs=background_jobs), indent=2) + "\n",
        encoding="utf-8",
    )
    if latest:
        (out_dir / str(result.split) / "LATEST").write_text(result.version + "\n", encoding="utf-8")
    return directory
