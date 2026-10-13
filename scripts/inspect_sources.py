"""Print a quick profile of the raw source data in data/raw/ (run fetch_sources.py first)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def malt() -> None:
    files = sorted(RAW.glob("malt/*.parquet"))
    if not files:
        print("MALT: no files yet (accept the terms on Hugging Face, set HF_TOKEN, re-fetch)")
        return
    df = pl.scan_parquet(files)
    schema = df.collect_schema()
    print("MALT columns:", list(schema))
    print("rows:", df.select(pl.len()).collect().item())
    for column in ("model", "run_source", "has_chain_of_thought", "manually_reviewed"):
        if column in schema:
            print(df.group_by(column).len().sort("len", descending=True).head(8).collect())
    if "labels" in schema:
        print(df.select(pl.col("labels").explode().value_counts(sort=True)).collect())


def philly() -> None:
    root = next(RAW.glob("philly/**/cluster_job_log"), None)
    if root is None:
        print("Philly: cluster_job_log not found (still extracting?)")
        return
    jobs = json.loads(root.read_text(encoding="utf-8"))
    print(f"Philly jobs: {len(jobs)}; example keys: {sorted(jobs[0])}")
    print(json.dumps(jobs[0], indent=1)[:800])


if __name__ == "__main__":
    malt()
    philly()
