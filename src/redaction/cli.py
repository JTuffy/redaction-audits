"""Command-line entry point: `redaction data generate`, `redaction p1 run | analyze`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from inspect_ai.model import Model

from redaction.core.models import Split
from redaction.core.roles import Role, Stance
from redaction.data.generator import build_split
from redaction.data.reports import templated_report
from redaction.escalation.analysis import analyze_run
from redaction.escalation.mock import mock_model
from redaction.escalation.policies import Policy
from redaction.escalation.runner import run_experiment
from redaction.escalation.summary import summary_table
from redaction.infra.log_setup import configure_logging, get_logger
from redaction.infra.settings import get_settings
from redaction.infra.storage import write_jsonl

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


@p1_app.command("run")
def run(
    split: Annotated[Split, typer.Option(help="Which split to run.")] = Split.DEV,
    policy: Annotated[
        list[Policy] | None, typer.Option(help="Policies to run; repeat the flag. Default: all.")
    ] = None,
    stance: Annotated[Stance, typer.Option(help="The advocate's stance.")] = Stance.HONEST,
    limit: Annotated[int | None, typer.Option(help="Run only the first N samples.")] = None,
    mock: Annotated[bool, typer.Option(help="Use the scripted offline model.")] = False,
    analyze_after: Annotated[bool, typer.Option(help="Summarize the run when done.")] = True,
) -> None:
    """Run Proposal 1 for one split and stance."""
    settings = get_settings()
    roles: dict[str, str | Model]
    if mock:
        model = mock_model()
        roles = {role.value: model for role in Role}
    else:
        roles = dict(settings.model_roles())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = settings.inspect_log_dir / f"p1-{split}-{stance}-{stamp}"
    run_experiment(
        split=split,
        policies=policy or list(Policy),
        stance=stance,
        model_roles=roles,
        log_dir=log_dir,
        limit=limit,
        max_connections=settings.max_connections,
    )
    if analyze_after:
        analyze(log_dir)


@p1_app.command("analyze")
def analyze(
    log_dir: Annotated[Path, typer.Argument(help="A directory of Inspect logs from `p1 run`.")],
) -> None:
    """Compute Proposal 1's headline numbers and write them under REDACTION_RESULTS_DIR."""
    summaries = analyze_run(log_dir, get_settings().results_dir / log_dir.name)
    if not summaries:
        raise typer.Exit(code=1)
    typer.echo(summary_table(summaries))
