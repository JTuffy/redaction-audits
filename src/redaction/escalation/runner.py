"""Running the experiment through Inspect's `eval`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.model import Model

from redaction.core.models import Split
from redaction.core.roles import Stance
from redaction.escalation.policies import Policy
from redaction.escalation.task import redaction
from redaction.infra.log_setup import get_logger

log = get_logger(__name__)


def run_experiment(
    *,
    split: Split,
    policies: Sequence[Policy],
    stance: Stance,
    model_roles: Mapping[str, str | Model],
    log_dir: Path,
    limit: int | None = None,
    max_connections: int = 10,
    seed: int | None = None,
) -> list[EvalLog]:
    """Run one task per policy and return Inspect's logs (also written to `log_dir`)."""
    tasks = [redaction(split=split, policy=policy, stance=stance, seed=seed) for policy in policies]
    log.info(
        "run_started",
        split=split,
        policies=[str(p) for p in policies],
        stance=stance,
        limit=limit,
        log_dir=str(log_dir),
    )
    logs = inspect_eval(
        tasks,
        model=next(iter(model_roles.values())),
        model_roles=model_roles,
        log_dir=str(log_dir),
        limit=limit,
        max_connections=max_connections,
        max_tasks=len(tasks),
        display="plain",
    )
    for eval_log in logs:
        log.info("task_finished", task=eval_log.eval.task, status=eval_log.status)
    return logs
