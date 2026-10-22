"""Command-line entry point: `redaction data generate`, `redaction p1 run | analyze`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from inspect_ai.model import Model

from redaction.core.models import Split
from redaction.core.roles import Role, Stance
from redaction.data.background import build_sample, load_sample
from redaction.data.generator import build_split
from redaction.data.pipeline.build import build_split_v2, manifest, write_build
from redaction.data.pipeline.model_render import ModelRenderer, ModelReviewer
from redaction.data.pipeline.render import Renderer, TemplateRenderer
from redaction.data.reports import templated_report
from redaction.escalation.ablation import Condition
from redaction.escalation.ablation_task import analyze_ablation, run_ablation
from redaction.escalation.analysis import analyze_run
from redaction.escalation.checks import checks_table
from redaction.escalation.mock import mock_model
from redaction.escalation.policies import Policy
from redaction.escalation.runner import run_experiment, token_usage
from redaction.escalation.summary import summary_table
from redaction.escalation.task import data_source
from redaction.infra.log_setup import configure_logging, get_logger
from redaction.infra.runs import record_run
from redaction.infra.settings import Settings, get_settings
from redaction.infra.storage import write_jsonl
from redaction.viewer.build import build_site

app = typer.Typer(no_args_is_help=True, help=__doc__)
data_app = typer.Typer(no_args_is_help=True, help="Scenario data shared by both proposals.")
p1_app = typer.Typer(no_args_is_help=True, help="Proposal 1: Redaction Under Escalation.")
app.add_typer(data_app, name="data")
app.add_typer(p1_app, name="p1")
log = get_logger(__name__)


@app.callback()
def main() -> None:
    """Privacy-preserving redaction in AI audits: shared data and the P1 harness."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


@data_app.command("generate")
def generate(
    split: Annotated[Split, typer.Option(help="Which split to generate.")] = Split.DEV,
    seed: Annotated[int | None, typer.Option(help="Override the split's default seed.")] = None,
    out_dir: Annotated[
        Path | None, typer.Option(help="Defaults to REDACTION_SCENARIOS_DIR.")
    ] = None,
) -> None:
    """Write a split's scenarios and their templated reports as JSON Lines, for inspection."""
    directory = out_dir or get_settings().scenarios_dir
    scenarios = build_split(split, seed=seed)
    write_jsonl(directory / f"{split}_scenarios.jsonl", scenarios)
    write_jsonl(directory / f"{split}_reports.jsonl", (templated_report(s) for s in scenarios))
    log.info("split_written", split=split, scenarios=len(scenarios), directory=str(directory))


@data_app.command("background")
def background(
    size: Annotated[int, typer.Option(help="Jobs to sample from the Philly trace.")] = 5000,
) -> None:
    """Extract the Philly job sample that background lines are drawn from (needs the raw trace)."""
    settings = get_settings()
    if not settings.philly_raw.exists():
        log.error(
            "philly_trace_missing",
            path=str(settings.philly_raw),
            hint="run scripts/fetch_sources.py first",
        )
        raise typer.Exit(code=1)
    count = build_sample(settings.philly_raw, settings.background_sample, size=size)
    log.info("background_sample_written", jobs=count, path=str(settings.background_sample))


@data_app.command("build")
def build(
    split: Annotated[Split, typer.Option(help="Which split to build.")] = Split.DEV,
    renderer: Annotated[
        str, typer.Option(help="'template', or an Inspect model string to rephrase lines.")
    ] = "template",
    reviewer: Annotated[
        str | None, typer.Option(help="Inspect model string for the blind label check.")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Build only the first N scenarios.")] = None,
    attempts: Annotated[int, typer.Option(help="Render attempts per scenario (models only).")] = 3,
) -> None:
    """Run the synthetic data pipeline for one split and freeze the result."""
    settings = get_settings()
    jobs = load_sample(settings.background_sample)
    if not jobs:
        log.warning("no_background_sample", hint="run `redaction data background`; using none")
    chosen: Renderer = TemplateRenderer() if renderer == "template" else ModelRenderer(renderer)
    result = asyncio.run(
        build_split_v2(
            split,
            chosen,
            jobs=jobs,
            reviewer=ModelReviewer(reviewer) if reviewer else None,
            limit=limit,
            max_attempts=attempts,
        )
    )
    directory = write_build(result, settings.built_dir, background_jobs=len(jobs))
    summary = manifest(result, background_jobs=len(jobs))
    typer.echo(f"{directory}\n{summary['stages']}\nissues: {summary['issues']}")


@app.command("site")
def site(
    bundle_logs: Annotated[
        bool, typer.Option(help="Bundle Inspect logs into the site's Runs tab.")
    ] = True,
) -> None:
    """Build the static viewer (data pipeline and runs) into REDACTION_SITE_DIR."""
    settings = get_settings()
    out = build_site(
        built_dir=settings.built_dir,
        results_dir=settings.results_dir,
        log_dir=settings.inspect_log_dir if bundle_logs else None,
        out_dir=settings.site_dir,
        ledger_dir=settings.ledger_dir,
        notes_dir=settings.notes_dir,
    )
    typer.echo(str(out))


@p1_app.command("run")
def run(
    split: Annotated[Split, typer.Option(help="Which split to run.")] = Split.DEV,
    policy: Annotated[
        list[Policy] | None, typer.Option(help="Policies to run; repeat the flag. Default: all.")
    ] = None,
    stance: Annotated[Stance, typer.Option(help="The advocate's stance.")] = Stance.HONEST,
    limit: Annotated[int | None, typer.Option(help="Run only the first N samples.")] = None,
    sample_id: Annotated[
        list[str] | None, typer.Option(help="Run only these scenario IDs; repeat the flag.")
    ] = None,
    mock: Annotated[bool, typer.Option(help="Use the scripted offline model.")] = False,
    analyze_after: Annotated[bool, typer.Option(help="Summarize the run when done.")] = True,
    purpose: Annotated[str, typer.Option(help="Why this run exists, for the run ledger.")] = "",
) -> None:
    """Run Proposal 1 for one split and stance. Real runs are recorded in the run ledger."""
    settings = get_settings()
    roles: dict[str, str | Model]
    if mock:
        model = mock_model()
        roles = {role.value: model for role in Role}
    else:
        roles = dict(settings.model_roles())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = settings.inspect_log_dir / f"p1-{split}-{stance}-{stamp}"
    logs = run_experiment(
        split=split,
        policies=policy or list(Policy),
        stance=stance,
        model_roles=roles,
        log_dir=log_dir,
        limit=limit,
        sample_ids=sample_id,
        max_connections=settings.max_connections,
    )
    if analyze_after:
        analyze(log_dir)
    if not mock:
        record_run(
            name=log_dir.name,
            kind="p1",
            purpose=purpose,
            config={
                "split": split.value,
                "policies": [p.value for p in (policy or list(Policy))],
                "stance": stance.value,
                "data": data_source(split),
                "limit": limit,
                "sample_ids": sample_id,
                **_protocol(settings),
                "tokens": token_usage(logs),
            },
            results_dir=settings.results_dir / log_dir.name,
            ledger_dir=settings.ledger_dir,
        )
        _refresh_site(settings)


def _refresh_site(settings: Settings) -> None:
    """Rebuild the viewer so a recorded run shows up without a manual `redaction site`."""
    try:
        build_site(
            built_dir=settings.built_dir,
            results_dir=settings.results_dir,
            log_dir=settings.inspect_log_dir,
            out_dir=settings.site_dir,
            ledger_dir=settings.ledger_dir,
            notes_dir=settings.notes_dir,
        )
    except OSError as error:  # the run is recorded either way; the site can be rebuilt by hand
        log.warning("site_refresh_failed", error=str(error))


def _protocol(settings: Settings) -> dict[str, object]:
    """Models and reasoning effort per role: the parts of the protocol a run depends on."""
    return {
        "models": settings.model_roles(),
        "reasoning": {role.value: settings.reasoning_for(role) for role in Role},
        "report_context": settings.report_context,
        "judge_samples": settings.judge_samples,
        "log_dir": str(settings.inspect_log_dir),
    }


@p1_app.command("ablate")
def ablate(
    split: Annotated[Split, typer.Option(help="Which split to run.")] = Split.DEV,
    condition: Annotated[
        list[Condition] | None,
        typer.Option(help="Conditions to show the judge; repeat the flag. Default: all."),
    ] = None,
    sample_id: Annotated[
        list[str] | None, typer.Option(help="Run only these scenario IDs; repeat the flag.")
    ] = None,
    mock: Annotated[bool, typer.Option(help="Use the scripted offline model.")] = False,
    purpose: Annotated[str, typer.Option(help="Why this run exists, for the run ledger.")] = "",
) -> None:
    """Marker ablation: the "human" judge's suspicion when removed values are shown differently."""
    settings = get_settings()
    roles: dict[str, str | Model]
    if mock:
        model = mock_model()
        roles = {role.value: model for role in Role}
    else:
        roles = dict(settings.model_roles())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = settings.inspect_log_dir / f"ablation-{split}-{stamp}"
    logs = run_ablation(
        split=split,
        conditions=condition or list(Condition),
        model_roles=roles,
        log_dir=log_dir,
        sample_ids=sample_id,
        max_connections=settings.max_connections,
    )
    out_dir = settings.results_dir / log_dir.name
    if analyze_ablation(log_dir, out_dir) is None:
        raise typer.Exit(code=1)
    typer.echo((out_dir / "ablation.md").read_text(encoding="utf-8"))
    if not mock:
        record_run(
            name=log_dir.name,
            kind="ablation",
            purpose=purpose,
            config={
                "split": split.value,
                "conditions": [c.value for c in (condition or list(Condition))],
                "data": data_source(split),
                "sample_ids": sample_id,
                **_protocol(settings),
                "tokens": token_usage(logs),
            },
            results_dir=out_dir,
            ledger_dir=settings.ledger_dir,
        )
        _refresh_site(settings)


@p1_app.command("analyze")
def analyze(
    log_dir: Annotated[Path, typer.Argument(help="A directory of Inspect logs from `p1 run`.")],
) -> None:
    """Compute Proposal 1's headline numbers and write them under REDACTION_RESULTS_DIR."""
    analysis = analyze_run(log_dir, get_settings().results_dir / log_dir.name)
    if analysis is None:
        raise typer.Exit(code=1)
    typer.echo(summary_table(analysis.summaries))
    typer.echo("\nMVP gate:\n" + checks_table(analysis.checks))
