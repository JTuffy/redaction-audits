"""Command-line entry point: `redesc generate | run | analyze`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from inspect_ai.model import Model
from pydantic import TypeAdapter

from redaction_escalation.domain.models import Split
from redaction_escalation.domain.policies import Policy
from redaction_escalation.domain.results import PolicySummary, summarize_all
from redaction_escalation.infra.log_setup import configure_logging, get_logger
from redaction_escalation.infra.settings import Role, get_settings
from redaction_escalation.infra.storage import write_json, write_jsonl, write_text
from redaction_escalation.pipeline.analysis import load_logs, results_from_logs, summary_table
from redaction_escalation.pipeline.mock import mock_model
from redaction_escalation.pipeline.prompting import Stance
from redaction_escalation.pipeline.runner import run_experiment
from redaction_escalation.scenarios.generator import build_split
from redaction_escalation.scenarios.reports import templated_report

app = typer.Typer(no_args_is_help=True, help=__doc__)
log = get_logger(__name__)

_SUMMARIES = TypeAdapter(tuple[PolicySummary, ...])


@app.callback()
def main() -> None:
    """Redaction Under Escalation: signal and secrets under lab-requested redaction."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


@app.command()
def generate(
    split: Annotated[Split, typer.Option(help="Which split to generate.")] = Split.DEV,
    seed: Annotated[int | None, typer.Option(help="Override the split's default seed.")] = None,
    out_dir: Annotated[Path | None, typer.Option(help="Defaults to REDESC_SCENARIOS_DIR.")] = None,
) -> None:
    """Write a split's scenarios and their templated reports as JSON Lines, for inspection."""
    directory = out_dir or get_settings().scenarios_dir
    scenarios = build_split(split, seed=seed)
    write_jsonl(directory / f"{split}_scenarios.jsonl", scenarios)
    write_jsonl(directory / f"{split}_reports.jsonl", (templated_report(s) for s in scenarios))
    log.info("split_written", split=split, scenarios=len(scenarios), directory=str(directory))


@app.command()
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
    """Run the experiment for one split and stance."""
    settings = get_settings()
    roles: dict[str, str | Model]
    if mock:
        model = mock_model()
        roles = {role.value: model for role in Role}
    else:
        roles = dict(settings.model_roles())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = settings.inspect_log_dir / f"{split}-{stance}-{stamp}"
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


@app.command()
def analyze(
    log_dir: Annotated[Path, typer.Argument(help="A directory of Inspect logs from `run`.")],
) -> None:
    """Compute the headline numbers for a run and write them under REDESC_RESULTS_DIR."""
    results = results_from_logs(load_logs(log_dir))
    if not results:
        log.error("no_results", log_dir=str(log_dir))
        raise typer.Exit(code=1)
    summaries = summarize_all(results)
    out_dir = get_settings().results_dir / log_dir.name
    write_jsonl(out_dir / "samples.jsonl", results)
    write_json(out_dir / "summary.json", summaries, _SUMMARIES)
    table = summary_table(summaries)
    write_text(out_dir / "summary.md", table + "\n")
    typer.echo(table)
    log.info("analysis_written", samples=len(results), directory=str(out_dir))
