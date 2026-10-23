"""Build a simulated set: plan, render, validate, review, freeze, with attributes alongside."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from redaction.core.models import Scenario, Split
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
    made = [simulate(split, i, seed, dist) for i in range(n)]
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
