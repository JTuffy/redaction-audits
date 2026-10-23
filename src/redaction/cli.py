"""Command-line entry point: `redaction data generate`, `redaction p1 run | analyze`."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from inspect_ai.model import Model

from redaction.core.models import Split
from redaction.core.roles import Role, Stance
from redaction.data.background import build_sample, load_sample
from redaction.data.blueprints import DEPTHS, catalog
from redaction.data.generator import build_split
from redaction.data.pipeline.build import build_split_v2, manifest, write_build
from redaction.data.pipeline.model_render import ModelRenderer, ModelReviewer
from redaction.data.pipeline.plan import BACKGROUND_STYLES
from redaction.data.pipeline.render import Renderer, TemplateRenderer
from redaction.data.pipeline.surface import SURFACE_AUROC_MAX
from redaction.data.reports import templated_report
from redaction.data.sim.build import build_sim, write_sim
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
from redaction.paper.build import compile_paper, publish, watch, write_generated
from redaction.paper.figures import build_figures
from redaction.viewer.build import build_site
from redaction.viewer.public import deploy_firebase, lint_site
from redaction.viewer.public import publish as publish_public

app = typer.Typer(no_args_is_help=True, help=__doc__)
data_app = typer.Typer(no_args_is_help=True, help="Scenario data shared by both proposals.")
p1_app = typer.Typer(no_args_is_help=True, help="Proposal 1: Redaction Under Escalation.")
app.add_typer(data_app, name="data")
app.add_typer(p1_app, name="p1")
paper_app = typer.Typer(
    no_args_is_help=True, help="The paper in paper/: tables, build, live preview."
)
app.add_typer(paper_app, name="paper")
log = get_logger(__name__)


@app.callback()
def main() -> None:
    """Privacy-preserving redaction in AI audits: shared data and the P1 harness."""
    # The repo's .env wins over machine-wide variables, so these experiments always use their
    # own provider keys (a user-level OPENAI_API_KEY once silently replaced them).
    load_dotenv(Path(".env"), override=True)
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
        str | None,
        typer.Option(help="Model for the blind label check. Default: REDACTION_REVIEWER_MODEL."),
    ] = None,
    review: Annotated[bool, typer.Option(help="Run the blind label check.")] = True,
    cues: Annotated[
        str, typer.Option(help="'verbatim' (cue tokens kept word for word) or 'paraphrase'.")
    ] = "verbatim",
    depth: Annotated[
        str,
        typer.Option(help="'benchmark' (disjoint + entangled), 'shallow', 'entangled' or 'deep'."),
    ] = "benchmark",
    latest: Annotated[
        bool, typer.Option(help="Point LATEST at this build (runs read LATEST).")
    ] = True,
    background: Annotated[
        str,
        typer.Option(help="'lab' (lines in the evidence's own style) or 'philly' (old builds)."),
    ] = "lab",
    fallback: Annotated[
        str | None,
        typer.Option(help="Model that renders an attempt the main renderer refuses."),
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Build only the first N scenarios.")] = None,
    attempts: Annotated[int, typer.Option(help="Render attempts per scenario (models only).")] = 3,
) -> None:
    """Run the synthetic data pipeline for one split and freeze the result."""
    settings = get_settings()
    if depth not in (*DEPTHS, "benchmark"):
        raise typer.BadParameter(f"depth must be one of {(*DEPTHS, 'benchmark')}")
    if background not in BACKGROUND_STYLES:
        raise typer.BadParameter(f"background must be one of {BACKGROUND_STYLES}")
    if cues not in {"verbatim", "paraphrase"}:
        raise typer.BadParameter("cues must be 'verbatim' or 'paraphrase'")
    paraphrase = cues == "paraphrase"
    if paraphrase and (renderer == "template" or not review):
        raise typer.BadParameter("paraphrased cues need a model renderer and the label check")
    reviewer_model = (reviewer or settings.reviewer_model) if review else None
    jobs = load_sample(settings.background_sample)
    if not jobs:
        log.warning("no_background_sample", hint="run `redaction data background`; using none")
    chosen: Renderer = (
        TemplateRenderer()
        if renderer == "template"
        else ModelRenderer(renderer, paraphrase=paraphrase, fallback=fallback)
    )
    result = asyncio.run(
        build_split_v2(
            split,
            chosen,
            jobs=jobs,
            reviewer=ModelReviewer(reviewer_model) if reviewer_model else None,
            limit=limit,
            max_attempts=attempts,
            paraphrase=paraphrase,
            depth=depth,
            background=background,
        )
    )
    directory = write_build(result, settings.built_dir, background_jobs=len(jobs), latest=latest)
    summary = manifest(result, background_jobs=len(jobs))
    typer.echo(f"{directory}\n{summary['stages']}\nissues: {summary['issues']}")
    surface = summary["surface_auroc"]
    if isinstance(surface, float) and surface > SURFACE_AUROC_MAX:
        log.warning("background_filterable", surface_auroc=surface, limit=SURFACE_AUROC_MAX)


@data_app.command("simulate")
def simulate_cmd(
    n: Annotated[int, typer.Option(help="How many scenarios to simulate.")] = 20,
    renderer: Annotated[
        str, typer.Option(help="'template', or a model that phrases the lines.")
    ] = "template",
    review: Annotated[bool, typer.Option(help="Run the blind label check.")] = True,
    fallback: Annotated[
        str | None, typer.Option(help="Model that renders an attempt the main renderer refuses.")
    ] = None,
) -> None:
    """Simulate classifier-off scenarios (world, computed label, text) into data/built/sim-*."""
    settings = get_settings()
    chosen: Renderer = (
        TemplateRenderer() if renderer == "template" else ModelRenderer(renderer, fallback=fallback)
    )
    reviewer = ModelReviewer(settings.reviewer_model) if review else None
    result, attributes = asyncio.run(build_sim(n, chosen, reviewer=reviewer))
    key = "template" if renderer == "template" else "model"
    directory = write_sim(result, attributes, settings.built_dir / f"sim-{key}")
    summary = manifest(result, background_jobs=0)
    typer.echo(f"{directory}\n{summary['stages']}\nissues: {summary['issues']}")


@app.command("site")
def site(
    bundle_logs: Annotated[
        bool, typer.Option(help="Bundle Inspect logs into the site's Runs tab.")
    ] = True,
    public: Annotated[
        bool, typer.Option(help="Build the public profile into REDACTION_PUBLIC_SITE_DIR.")
    ] = False,
) -> None:
    """Build the static viewer (data pipeline and runs) into REDACTION_SITE_DIR."""
    out = _build_viewer(public=public, bundle_logs=bundle_logs)
    typer.echo(str(out))
    if public:
        issues = lint_site(out)
        for issue in issues:
            typer.echo(issue)
        typer.echo(f"public lint: {len(issues)} issue(s)")


def _build_viewer(*, public: bool, bundle_logs: bool = True) -> Path:
    settings = get_settings()
    return build_site(
        built_dir=settings.built_dir,
        results_dir=settings.results_dir,
        log_dir=settings.inspect_log_dir if bundle_logs else None,  # public: read, not bundled
        out_dir=settings.public_site_dir if public else settings.site_dir,
        ledger_dir=settings.ledger_dir,
        notes_dir=settings.notes_dir,
        paper_dir=settings.paper_dir,
        direction_file=settings.direction_file,
        blueprints=catalog(),
        public=public,
    )


@app.command("publish")
def publish_site(
    push: Annotated[
        bool, typer.Option(help="Actually push to the public target. Off: a dry run.")
    ] = False,
) -> None:
    """Build the public site, lint it, and (with --push) send it to the public target."""
    if not _publish_public(get_settings(), push=push):
        raise typer.Exit(code=1)


@app.command("deploy")
def deploy(
    push: Annotated[
        bool | None,
        typer.Option(help="Push the public build. Default: REDACTION_PUBLISH_ON_UPDATE."),
    ] = None,
    paper: Annotated[bool, typer.Option(help="Redraw figures and recompile the paper.")] = True,
) -> None:
    """The whole update: figures and paper, the private site, then the public build.

    The public build is always made and linted, so a lint failure shows up on the day it is
    introduced; it is pushed only with --push or REDACTION_PUBLISH_ON_UPDATE=true.
    """
    settings = get_settings()
    if paper:
        build_figures(settings.paper_dir, settings.ledger_dir)
        write_generated(
            settings.paper_dir, built_dir=settings.built_dir, ledger_dir=settings.ledger_dir
        )
        status = compile_paper(settings.paper_dir)
        if not status["ok"]:
            typer.echo("\n".join(status["errors"]))
    typer.echo(str(_build_viewer(public=False)))
    if settings.paper_dir.exists():
        publish(settings.paper_dir, settings.site_dir)
    if not _publish_public(settings, push=settings.publish_on_update if push is None else push):
        raise typer.Exit(code=1)


def _publish_public(settings: Settings, *, push: bool) -> bool:
    """Build and lint the public profile; push it when asked. False when it must not go out."""
    out = _build_viewer(public=True)
    issues = lint_site(out)
    for issue in issues:
        typer.echo(issue)
    if issues:
        typer.echo(f"public build not publishable: {len(issues)} lint issue(s); fix the sources")
        return False
    if settings.public_target == "firebase":
        if push and not settings.firebase_project:
            typer.echo("REDACTION_FIREBASE_PROJECT is not set; see docs/publishing.md")
            return False
        steps = deploy_firebase(out, settings.firebase_project or "<project>", push=push)
    else:
        if push and not settings.public_repo:
            typer.echo("REDACTION_PUBLIC_REPO is not set; see docs/publishing.md")
            return False
        steps = publish_public(
            out,
            settings.public_repo or "<REDACTION_PUBLIC_REPO>",
            push=push,
            work_dir=settings.public_site_dir.parent / "public-checkout",
        )
    typer.echo(
        ("pushed:\n" if push else "public build ok; dry run, would run:\n") + "\n".join(steps)
    )
    return True


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
    experiment: Annotated[
        str, typer.Option(help="Experiment thread id from docs/direction.toml, for the site.")
    ] = "",
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
            experiment=experiment,
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
    """Rebuild the private site, and the public build when publishing is on, after a run."""
    try:
        _build_viewer(public=False)
        if settings.paper_dir.exists():
            publish(settings.paper_dir, settings.site_dir)
        _publish_public(settings, push=settings.publish_on_update)
    except (OSError, subprocess.CalledProcessError) as error:  # the run is recorded either way
        log.warning("site_refresh_failed", error=str(error))


def _protocol(settings: Settings) -> dict[str, object]:
    """Models and reasoning effort per role: the parts of the protocol a run depends on."""
    return {
        "models": settings.model_roles(),
        "reasoning": {role.value: settings.reasoning_for(role) for role in Role},
        "report_context": settings.report_context,
        "judge_samples": settings.judge_samples,
        "cache_replies": settings.cache_replies,
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
    experiment: Annotated[
        str, typer.Option(help="Experiment thread id from docs/direction.toml, for the site.")
    ] = "",
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
            experiment=experiment,
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


@paper_app.command("tables")
def paper_tables() -> None:
    """Regenerate paper/generated/ from the frozen builds and the run ledger."""
    settings = get_settings()
    for path in write_generated(
        settings.paper_dir, built_dir=settings.built_dir, ledger_dir=settings.ledger_dir
    ):
        typer.echo(path)


@paper_app.command("figures")
def paper_figures() -> None:
    """Draw the result figures in paper/figures.toml from the recorded runs."""
    settings = get_settings()
    for fig in build_figures(settings.paper_dir, settings.ledger_dir):
        typer.echo(fig["id"])


@paper_app.command("build")
def paper_build() -> None:
    """Regenerate tables, compile the paper once, and copy the PDF into the site."""
    settings = get_settings()
    write_generated(
        settings.paper_dir, built_dir=settings.built_dir, ledger_dir=settings.ledger_dir
    )
    status = compile_paper(settings.paper_dir)
    publish(settings.paper_dir, settings.site_dir)
    typer.echo("ok" if status["ok"] else "\n".join(status["errors"]))
    if not status["ok"]:
        raise typer.Exit(1)


@paper_app.command("watch")
def paper_watch(
    interval: Annotated[float, typer.Option(help="Seconds between checks for changes.")] = 1.0,
) -> None:
    """Recompile on every save; the site's Paper page reloads the PDF by itself."""
    settings = get_settings()
    watch(
        settings.paper_dir,
        settings.site_dir,
        built_dir=settings.built_dir,
        ledger_dir=settings.ledger_dir,
        interval=interval,
    )
