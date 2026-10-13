"""Reading Inspect logs back into results, and writing a run's summary files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Final, NamedTuple

from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log
from pydantic import TypeAdapter

from redaction.escalation.checks import GateCheck, checks_table, mvp_checks
from redaction.escalation.plots import plot_tradeoff
from redaction.escalation.scoring import SampleResult
from redaction.escalation.summary import PolicySummary, summarize_all, summary_table
from redaction.escalation.task import SCORER_NAME, result_from_metadata
from redaction.infra.log_setup import get_logger
from redaction.infra.storage import write_json, write_jsonl, write_text

log = get_logger(__name__)

_SUMMARIES: Final = TypeAdapter(tuple[PolicySummary, ...])


def load_logs(log_dir: Path) -> list[EvalLog]:
    """Read every eval log in a directory."""
    return [read_eval_log(info) for info in list_eval_logs(str(log_dir))]


def results_from_logs(logs: Iterable[EvalLog]) -> list[SampleResult]:
    """Every scored sample in the logs. Samples that errored are counted and skipped."""
    results: list[SampleResult] = []
    for eval_log in logs:
        skipped = 0
        for sample in eval_log.samples or []:
            score = (sample.scores or {}).get(SCORER_NAME)
            if sample.error is not None or score is None or score.metadata is None:
                skipped += 1
                continue
            results.append(result_from_metadata(score.metadata))
        if skipped:
            log.warning("samples_skipped", task=eval_log.eval.task, count=skipped)
    return results


class RunAnalysis(NamedTuple):
    """What `analyze_run` computed."""

    summaries: tuple[PolicySummary, ...]
    checks: tuple[GateCheck, ...]


def analyze_run(log_dir: Path, out_dir: Path) -> RunAnalysis | None:
    """Summarize a run's logs and write the results to `out_dir`.

    Writes `samples.jsonl`, `summary.json`, `summary.md`, `checks.md` and, when any policy has
    both headline numbers, `tradeoff.png`. Returns None, and writes nothing, when the logs hold
    no scored samples.
    """
    results = results_from_logs(load_logs(log_dir))
    if not results:
        log.error("no_results", log_dir=str(log_dir))
        return None
    summaries = summarize_all(results)
    checks = mvp_checks(results)
    write_jsonl(out_dir / "samples.jsonl", results)
    write_json(out_dir / "summary.json", summaries, _SUMMARIES)
    write_text(out_dir / "summary.md", summary_table(summaries) + "\n")
    write_text(out_dir / "checks.md", checks_table(checks) + "\n")
    plot_tradeoff(summaries, out_dir / "tradeoff.png")
    log.info("analysis_written", samples=len(results), directory=str(out_dir))
    return RunAnalysis(summaries=summaries, checks=checks)
