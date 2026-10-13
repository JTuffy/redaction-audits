"""Print a quick profile of the raw source data in data/raw/ (run fetch_sources.py first)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def wildchat() -> None:
    df = pl.scan_parquet(RAW / "wildchat" / "*.parquet")
    print("WildChat schema:", df.collect_schema())
    summary = df.select(
        pl.len().alias("conversations"),
        pl.col("timestamp").min().alias("first"),
        pl.col("timestamp").max().alias("last"),
        pl.col("hashed_ip").n_unique().alias("users"),
        pl.col("model").n_unique().alias("models"),
    ).collect()
    print(summary)
    print(df.group_by("model").len().sort("len", descending=True).head(5).collect())


def philly() -> None:
    root = next(RAW.glob("philly/**/cluster_job_log"), None)
    if root is None:
        print("Philly: cluster_job_log not found (still extracting?)")
        return
    jobs = json.loads(root.read_text(encoding="utf-8"))
    print(f"Philly jobs: {len(jobs)}; example keys: {sorted(jobs[0])}")
    print(json.dumps(jobs[0], indent=1)[:800])


if __name__ == "__main__":
    wildchat()
    philly()
