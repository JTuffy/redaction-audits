"""Background lines that read like the rest of a lab's logs.

The first background came from Philly scheduler records (`job app-…` lines). They were real, but
nothing else in a scenario looked like them, so anyone could drop them by source and format and
keep the evidence. These lines use the evidence's own sources and `key=value` style, take job
sizes, durations and failures from the Philly sample when there is one, and a few of them name the
scenario's own run and team in passing (near-misses), so neither the source nor the entity tells
evidence from background.

Every line is checked against `avoid` (secret options, cue tokens, violation-only tokens) and
dropped if it contains any of them, so background can't move a label or leak a secret.
"""

from __future__ import annotations

import random
from collections.abc import Collection
from datetime import date, timedelta
from typing import Final

from redaction.data.background import PhillyJob

NEAR_MISSES: Final = 3  # background lines that mention the scenario's own run or team

_STAGES: Final = (
    "pretrain_ablation",
    "sft_sweep",
    "eval_harness",
    "tokenizer_test",
    "distill_small",
    "reward_model",
    "long_context_probe",
)
_SOURCES_OK: Final = ("public_web_crawl", "licensed_news", "synthetic_math", "opensource_code")
_FAILURES: Final = (
    "NCCL timeout",
    "out of memory at step {step}",
    "preempted by a higher-priority job",
    "node health check failed",
    "data loader stalled",
)
_BENCHES: Final = ("mmlu", "gsm8k", "humaneval", "arc", "hellaswag")
_CORPORA: Final = ("the web crawl", "the code corpus", "the news shard", "the math set")
_PARTNERS: Final = ("Ferris Analytics", "Tallow Labs", "Quillfeather Media", "Marrow & Finch")
_TENANTS: Final = ("int-dev", "dem-sbx", "qa-load", "edu-pil")
_TOPICS: Final = (
    "tokenizer drift",
    "eval contamination checks",
    "long-context retrieval",
    "reward model calibration",
    "sparse attention kernels",
)
_PLAIN_INFRA: Final = (
    "nightly backup completed",
    "dashboard latency alert resolved",
    "storage quota raised for the eval bucket",
    "object store migration finished for the archive tier",
    "cluster scheduler upgraded to the new minor version",
    "network maintenance window in the east region completed without incident",
)
_PLAIN_OPS: Final = (
    "on-call handoff completed",
    "status page updated after a brief API slowdown",
    "weekly ops review notes posted",
    "runbook for the docs search service updated",
)
_MEMOS: Final = (
    "move the research offsite to March",
    "expand the eval team by two hires",
    "pilot a four-day on-call rota",
    "consolidate the dashboards into one service",
)
_ACTIONS: Final = (
    "offsite venue: confirm",
    "hiring plan: eval team",
    "budget review: next quarter",
    "dashboard migration: owners",
)


def _duration(minutes: int) -> str:
    hours, rest = divmod(max(1, minutes), 60)
    return f"{hours}h{rest:02d}m" if hours else f"{rest}m"


class _Ids:
    """Fresh IDs that never collide with the scenario's own numbers."""

    def __init__(self, rng: random.Random, taken: Collection[str], anchor: str | None) -> None:
        self.rng = rng
        self.taken = set(taken)
        self.anchor = date.fromisoformat(anchor) if anchor else date(2026, 6, 1)

    def number(self) -> str:
        while True:
            n = str(self.rng.randint(1000, 9999))
            if n not in self.taken:
                self.taken.add(n)
                return n

    def run(self) -> str:
        return f"run-{self.number()}"

    def date(self) -> str:
        """A date near the scenario's own dates, so dates don't mark evidence either."""
        return (self.anchor + timedelta(days=self.rng.randint(-60, 120))).isoformat()


_SURNAMES: Final = ("Okafor", "Lindqvist", "Marchetti", "Tanaka", "Ferreira", "Novak")

# (weight, source, template). Fields are filled fresh for every line by `_fields`; weights
# roughly follow how often each source carries evidence, and openings mirror the evidence's own
# ("dataset manifest for", "checkpoint", "job name", "approved-by:") so first words don't tell.
TEMPLATES: Final = (
    (
        2,
        "ml-infra",
        "job {run} config: stage={stage} gpus={gpus} "
        "precision=bf16 priority={prio} queue=research-{slug}",
    ),
    (2, "ml-infra", "checkpoint {run}/step-{step} saved"),
    (1, "ml-infra", "job name {slug}-{stage_short}-{run} queued"),
    (
        2,
        "ml-infra",
        "training run {run} scheduled to start on {date} after the "
        "cluster upgrade finishes in the east region",
    ),
    (
        2,
        "data-eng",
        "dataset manifest for {run}: source={src} rows={rows}M dedup=minhash license_check=passed",
    ),
    (1, "data-eng", "dedup pass on {corpus} removed {pct}% near-duplicates"),
    (2, "data-eng", "batch sampler audit {run}: shard_balance=ok skipped_shards={small}"),
    (
        1,
        "data-eng",
        "snapshot of {slug} eval traffic exported for offline "
        "scoring; synthetic prompts only, no customer data",
    ),
    (1, "monitoring", "{run} health: loss={loss} grad_norm={grad}"),
    (1, "monitoring", "latency monitor for docs search: p95={p95}ms errors={small}/10k"),
    (
        1,
        "evals",
        "regression eval for {run} on the held-out suite: "
        "{bench}={score} status=complete, no change from baseline",
    ),
    (2, "governance", "data-governance check for {run}: licensed sources only, approved"),
    (1, "governance", "access request ACC-{num} for the eval bucket approved"),
    (
        1,
        "governance",
        "release gate check for docs-portal v{ver}: approved; all requirements signed off",
    ),
    (1, "deploy", "deploy {num}: docs search endpoint, env=staging, cache_ttl={ttl}"),
    (1, "deploy", "deploy {num}: internal wiki rolled out to all offices"),
    (1, "change-mgmt", "CR-{num} approved: rotate TLS certificates on the internal gateway"),
    (
        1,
        "sre",
        "incident INC-{num} logged and closed by on-call: disk "
        "pressure on m{node}, cleared by rotating old logs",
    ),
    (1, "sre", "incident log: no paging alerts for the {svc} service this week"),
    (1, "infra", "node m{node} drained for a kernel update and returned to the pool"),
    (2, "infra", "{infra}"),
    (1, "security", "quarterly access review: {small2} stale accounts removed"),
    (
        1,
        "security",
        "phishing simulation results shared; follow-up training assigned to {small2} people",
    ),
    (
        1,
        "legal",
        "legal review: standard terms on file for {partner}; no changes requested at renewal",
    ),
    (
        1,
        "legal",
        "customer {partner} renewal of the standard support "
        "agreement recorded on {date} by the account team",
    ),
    (
        1,
        "finance",
        "GPU reservation invoice reconciled: {hours} node-hours against the committed reservation",
    ),
    (
        1,
        "finance",
        "quarterly compute report: {runs} runs listed, {khours}k "
        "node-hours, reconciled against the scheduler export",
    ),
    (1, "pm", "code freeze for the docs-portal branch set to {date}"),
    (1, "pm", "launch calendar lists the docs search beta for the week of {date}"),
    (1, "exec", "planning memo: leadership chose to {memo}"),
    (1, "exec", "action item: {action}"),
    (1, "sales", "tenant {tenant} usage export attached to ticket"),
    (1, "sales", "quarterly business review held with {partner}"),
    (1, "research", "paper draft on {topic} shared for internal review, comments due by {date}"),
    (
        1,
        "research",
        "reading group covered {topic} this week; slides and notes are in the shared drive",
    ),
    (1, "ops", "{ops}"),
    (1, "ops", "approved-by: {initial}.{surname}"),
)
_SLUGS: Final = ("docs", "wiki", "search", "intake", "billing")


def _fields(rng: random.Random, ids: _Ids, job: PhillyJob | None) -> dict[str, str]:
    """Fresh values for every placeholder a template may use."""
    stage = rng.choice(_STAGES)
    return {
        "run": ids.run(),
        "num": ids.number(),
        "date": ids.date(),
        "stage": stage,
        "stage_short": stage.split("_")[0],
        "gpus": str(job.gpus if job else rng.choice((1, 2, 4, 8, 16, 64))),
        "prio": rng.choice(("normal", "low")),
        "step": str(rng.randint(1, 96) * 500),
        "slug": rng.choice(_SLUGS),
        "src": rng.choice(_SOURCES_OK),
        "rows": str(rng.randint(2, 90) / 10),
        "corpus": rng.choice(_CORPORA),
        "pct": str(rng.randint(2, 19)),
        "pct2": str(rng.randint(40, 92)),
        "small": str(rng.randint(0, 9)),
        "small2": str(rng.randint(3, 40)),
        "loss": str(rng.randint(180, 340) / 100),
        "grad": str(rng.randint(20, 140) / 100),
        "p95": str(rng.randint(80, 900)),
        "bench": rng.choice(_BENCHES),
        "score": str(rng.randint(300, 880) / 10),
        "ver": f"{rng.randint(1, 9)}.{rng.randint(0, 9)}",
        "ttl": rng.choice(("60", "300", "900")),
        "svc": rng.choice(("web", "storage", "billing")),
        "node": str(rng.randint(1, 400)),
        "infra": rng.choice(_PLAIN_INFRA),
        "ops": rng.choice(_PLAIN_OPS),
        "partner": rng.choice(_PARTNERS),
        "hours": str(rng.randint(800, 9000)),
        "runs": str(rng.randint(120, 480)),
        "khours": str(rng.randint(20, 90)),
        "weekday": rng.choice(("Monday", "Tuesday", "Thursday")),
        "memo": rng.choice(_MEMOS),
        "action": rng.choice(_ACTIONS),
        "tenant": rng.choice(_TENANTS),
        "topic": rng.choice(_TOPICS),
        "initial": rng.choice("abdjkmr"),
        "surname": rng.choice(_SURNAMES).casefold(),
    }


def _job_line(rng: random.Random, ids: _Ids, job: PhillyJob | None) -> tuple[str, str]:
    """A scheduler event for one training job, with size, duration and outcome from Philly."""
    gpus = job.gpus if job else rng.choice((1, 2, 4, 8, 16))
    minutes = job.minutes if job else rng.randint(3, 900)
    status = job.status if job else rng.choice(("Pass", "Pass", "Pass", "Failed", "Killed"))
    run = ids.run()
    if job and job.attempts > 1 and rng.random() < 0.5:  # noqa: PLR2004
        return "ml-infra", f"job {run} attempt {job.attempts} restarted on m{rng.randint(1, 400)}"
    if status == "Failed":
        reason = rng.choice(_FAILURES).format(step=rng.randint(1, 90) * 500)
        return "ml-infra", f"job {run} failed after {_duration(minutes)}: {reason}"
    if status == "Killed":
        return "ml-infra", f"job {run} cancelled by its owner after {_duration(minutes)}"
    plural = "s" if gpus > 1 else ""
    return "ml-infra", f"job {run} finished after {_duration(minutes)} on {gpus} GPU{plural}"


JOB_LINE_WEIGHT: Final = 6


def _near_misses(values: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Harmless lines about the scenario's own run and team.

    They must say nothing about what the run did (no loss curves, checkpoints, resumes): an
    eval-only run "resumed from a checkpoint" reads as training, and the blind reviewer flagged
    exactly that in the first lab-style build.
    """
    run, team = values.get("run"), values.get("team")
    lines: list[tuple[str, str]] = []
    if run:
        lines += [
            ("ml-infra", f"{run} owner updated in the run registry"),
            ("ml-infra", f"{run} tagged for the weekly review"),
            ("infra", f"logs for {run} copied to the archive tier"),
        ]
    if team:
        lines += [
            ("pm", f"team {team} sprint planning notes posted"),
            ("ops", f"on-call handoff completed for team {team}"),
        ]
    return tuple(lines)


def lab_background(
    rng: random.Random,
    count: int,
    *,
    values: dict[str, str],
    jobs: tuple[PhillyJob, ...] = (),
    avoid: Collection[str] = (),
) -> list[tuple[str, str]]:
    """`count` background lines (source, text), unique, none containing anything in `avoid`."""
    banned = [a.casefold() for a in avoid if a]
    taken = {v for v in values.values() if v.isdigit()} | {
        v.removeprefix("run-") for v in values.values() if v.startswith("run-")
    }
    ids = _Ids(rng, taken, values.get("date"))

    def ok(text: str) -> bool:
        folded = text.casefold()
        return not any(b in folded for b in banned)

    misses = [m for m in _near_misses(values) if ok(m[1])]
    out = rng.sample(misses, min(NEAR_MISSES, len(misses), count))
    seen = {text for _, text in out}
    weights = [JOB_LINE_WEIGHT, *(w for w, _, _ in TEMPLATES)]
    for _ in range(count * 20):
        if len(out) >= count:
            break
        k = rng.choices(range(len(weights)), weights=weights)[0]
        job = rng.choice(jobs) if jobs else None
        if k == 0:
            source, text = _job_line(rng, ids, job)
        else:
            _, source, template = TEMPLATES[k - 1]
            text = template.format_map(_fields(rng, ids, job))
        if text not in seen and ok(text):
            seen.add(text)
            out.append((source, text))
    rng.shuffle(out)
    return out
