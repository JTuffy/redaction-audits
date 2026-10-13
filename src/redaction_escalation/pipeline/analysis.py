"""Turning Inspect logs into the spec's headline numbers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log

from redaction_escalation.domain.metrics import Interval
from redaction_escalation.domain.results import PolicySummary, SampleResult
from redaction_escalation.infra.log_setup import get_logger
from redaction_escalation.pipeline.task import SCORER_NAME, result_from_metadata

log = get_logger(__name__)


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


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_interval(interval: Interval | None) -> str:
    if interval is None:
        return "n/a"
    return f"{interval.estimate:.2f} [{interval.low:.2f}, {interval.high:.2f}]"


def summary_table(summaries: Sequence[PolicySummary]) -> str:
    """A markdown table of the headline numbers, one row per policy."""
    header = (
        "| Policy | n | AUROC auditor | AUROC unedited | AUROC edited | Persistence (95% CI) "
        "| FPR / FNR | Leakage (95% CI) | Tail > 0.8 | Verbatim | Evidence loss | Volume |"
    )
    rows = [header, "|" + "---|" * 12]
    rows.extend(
        f"| {s.policy} | {s.samples} | {_fmt(s.auroc_auditor)} | {_fmt(s.auroc_unedited)} "
        f"| {_fmt(s.auroc_edited)} | {_fmt_interval(s.persistence)} "
        f"| {s.errors_edited.false_positive_rate:.2f} / {s.errors_edited.false_negative_rate:.2f} "
        f"| {_fmt_interval(s.leakage_mean)} | {s.leakage_tail:.2f} | {s.verbatim_leak_rate:.2f} "
        f"| {s.evidence_loss:.2f} | {s.redaction_volume:.2f} |"
        for s in summaries
    )
    return "\n".join(rows)
