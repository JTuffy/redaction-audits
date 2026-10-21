"""Background log lines from a real GPU cluster trace (Microsoft Philly, 2017).

The planted lines (the violation evidence, secrets and correlates) are synthetic; everything
around them is drawn from real scheduler records, so the noise has the variety, failures and
odd job sizes of a real cluster rather than a fixed pool of a dozen sentences.

The raw trace is ~40 MB of JSON. `build_sample` extracts a few thousand jobs once into a small
JSON Lines file, which the generator reads. Without that file the generator falls back to the
fixed neutral lines in `blueprints`, so tests and CI need no download.
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class PhillyJob(NamedTuple):
    """The fields of one Philly job the background lines use."""

    job: str
    vc: str
    user: str
    status: str
    gpus: int
    machine: str
    attempts: int
    minutes: int


def _job_from_record(record: dict[str, object]) -> PhillyJob | None:
    """Parse one raw trace record; jobs that never ran are skipped."""
    attempts = record.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return None
    last = attempts[-1]
    try:
        start = datetime.strptime(last["start_time"], _TIME_FORMAT)
        end = datetime.strptime(last["end_time"], _TIME_FORMAT)
        detail = last["detail"]
        gpus = sum(len(d["gpus"]) for d in detail)
        machine = detail[0]["ip"]
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if gpus == 0:
        return None
    return PhillyJob(
        job=str(record["jobid"]).replace("application_", "app-"),
        vc=str(record["vc"]),
        user=str(record["user"]),
        status=str(record["status"]),
        gpus=gpus,
        machine=str(machine),
        attempts=len(attempts),
        minutes=max(1, int((end - start).total_seconds() // 60)),
    )


def build_sample(raw_log: Path, out: Path, *, size: int = 5000, seed: int = 0) -> int:
    """Extract a reproducible random sample of parseable jobs from the raw trace."""
    records = json.loads(raw_log.read_text(encoding="utf-8"))
    jobs = [job for r in records if (job := _job_from_record(r)) is not None]
    sample = random.Random(seed).sample(jobs, min(size, len(jobs)))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for job in sample:
            handle.write(json.dumps(job._asdict()) + "\n")
    return len(sample)


def load_sample(path: Path) -> tuple[PhillyJob, ...]:
    """Read a sample written by `build_sample`; empty if the file does not exist."""
    if not path.exists():
        return ()
    with path.open(encoding="utf-8") as handle:
        return tuple(PhillyJob(**json.loads(line)) for line in handle if line.strip())


def _duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}m" if hours else f"{rest}m"


def job_line(job: PhillyJob, rng: random.Random) -> tuple[str, str]:
    """One scheduler line about a job, as (source, text). The phrasing varies with the job."""
    gpus = f"{job.gpus} GPU" + ("s" if job.gpus > 1 else "")
    if job.attempts > 1 and rng.random() < 0.5:  # noqa: PLR2004
        return "scheduler", (
            f"job {job.job} (vc {job.vc}) attempt {job.attempts} restarted on {job.machine}, {gpus}"
        )
    if job.status == "Failed":
        return "scheduler", f"job {job.job} failed after {_duration(job.minutes)} on {job.machine}"
    if job.status == "Killed":
        return (
            "scheduler",
            f"job {job.job} killed by user u-{job.user} after {_duration(job.minutes)}",
        )
    if rng.random() < 0.5:  # noqa: PLR2004
        return (
            "scheduler",
            f"job {job.job} queued by u-{job.user} in vc {job.vc}, requesting {gpus}",
        )
    return "scheduler", f"job {job.job} finished status=Pass after {_duration(job.minutes)}, {gpus}"


def background_lines(
    jobs: tuple[PhillyJob, ...], rng: random.Random, count: int
) -> list[tuple[str, str]]:
    """`count` background lines drawn from `jobs` (with replacement if the sample is small)."""
    if not jobs:
        return []
    picks = rng.sample(jobs, count) if count <= len(jobs) else rng.choices(jobs, k=count)
    return [job_line(job, rng) for job in picks]
