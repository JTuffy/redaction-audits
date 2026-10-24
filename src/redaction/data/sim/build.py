"""Build a simulated set: plan, render, validate, review, freeze, with attributes alongside."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final

from redaction.core.models import Label, Scenario, Split
from redaction.data.pipeline.build import (
    BuildResult,
    Reviewer,
    ScenarioRecord,
    _run_one,
    _version,
    write_build,
)
from redaction.data.pipeline.plan import ScenarioPlan
from redaction.data.pipeline.render import Renderer
from redaction.data.sim.classifier import CLAIM, RULE, Distributions
from redaction.data.sim.render import DEPTH, simulate

SIM_SEED = 909


QUOTA: Final = {Label.VIOLATION: 0.4, Label.RED_HERRING: 0.4, Label.CLEAN: 0.2}


def sample_to_quota(
    n: int, split: Split, seed: int, dist: Distributions | None = None
) -> list[tuple[ScenarioPlan, dict[str, Any]]]:
    """Draw worlds until the label mix hits `QUOTA`; violations and red herrings come as twins.

    The distributions decide what a world looks like; the quota decides which worlds are kept,
    so the mix is set by design rather than by how often a classifier happens to be switched off.
    """
    want = {label: round(share * n) for label, share in QUOTA.items()}
    have = dict.fromkeys(QUOTA, 0)
    kept: list[tuple[ScenarioPlan, dict[str, Any]]] = []
    index = 0
    while sum(have.values()) < sum(want.values()) and index < n * 50:
        draw = simulate(split, index, seed, dist)
        index += 1
        labels = [p.label for p, _ in draw]
        if len(draw) == 1 and labels[0] is not Label.CLEAN:
            continue  # violations and red herrings come only as twins, so they stay paired
        if all(have[label] + labels.count(label) <= want[label] for label in set(labels)):
            kept += draw
            for label in labels:
                have[label] += 1
    return kept


async def build_sim(
    n: int,
    renderer: Renderer,
    *,
    reviewer: Reviewer | None = None,
    split: Split = Split.DEV,
    seed: int = SIM_SEED,
    dist: Distributions | None = None,
    concurrency: int = 8,
) -> tuple[BuildResult, list[dict[str, object]]]:
    """`n` simulated classifier-off scenarios through the usual render, validate and review."""
    made = sample_to_quota(n, split, seed, dist)
    plans = tuple(p for p, _ in made)
    gate = asyncio.Semaphore(concurrency)
    attempts = 1 if renderer.name == "template" else 3

    async def one(plan: ScenarioPlan) -> tuple[Scenario | None, ScenarioRecord]:
        async with gate:
            return await _run_one(plan, renderer, reviewer, attempts)

    outcomes = await asyncio.gather(*(one(p) for p in plans))
    result = BuildResult(
        split=split,
        version=_version(plans, f"sim|{renderer.name}|{reviewer.name if reviewer else 'none'}"),
        depth=DEPTH,
        background="lab",
        renderer=renderer.name,
        reviewer=reviewer.name if reviewer else None,
        plans=plans,
        scenarios=tuple(s for s, _ in outcomes if s is not None),
        records=tuple(r for _, r in outcomes),
    )
    return result, [a for _, a in made]


def write_sim(
    result: BuildResult,
    attributes: list[dict[str, object]],
    out_dir: Path,
    dist: Distributions | None = None,
) -> Path:
    """Freeze under `<out_dir>/<split>/<version>`, with the attributes and the distributions."""
    directory = write_build(result, out_dir, background_jobs=0, latest=True)
    with (directory / "attributes.jsonl").open("w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(a) + "\n" for a in attributes)
    about = {"claim": CLAIM, "check": RULE, "distributions": asdict(dist or Distributions())}
    (directory / "simulator.json").write_text(json.dumps(about, indent=2) + "\n", encoding="utf-8")
    return directory
