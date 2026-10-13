"""Download the real-world source data used as backbone for scenario generation.

Sources (both openly licensed, no gating):
- WildChat-1M (allenai, ODC-BY): production chatbot traffic with per-utterance timestamps,
  OpenAI and Detoxify moderation results, and hashed user IPs. Backbone for the
  classifier-off, opted-out-data and production-traffic scenarios.
- Philly traces (Microsoft, CC-BY-4.0): 117k deep-learning training jobs with users, GPU
  allocations, attempts and outcomes. Backbone for compute and run-record scenarios.

Files land in data/raw/ (git-ignored). Re-running skips files that are already complete.

    uv run python scripts/fetch_sources.py               # 2 WildChat shards + Philly
    uv run python scripts/fetch_sources.py --shards 14   # all of WildChat (~3.4 GB)
"""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
WILDCHAT = "https://huggingface.co/datasets/allenai/WildChat-1M/resolve/main/data/train-{i:05d}-of-00014.parquet"
PHILLY = "https://github.com/msr-fiddle/philly-traces/raw/master/trace-data.tar.gz"


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip  {dest.relative_to(RAW)} (exists)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    print(f"fetch {url}")
    with urllib.request.urlopen(url) as response, partial.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(response, out, length=1 << 20)
    partial.replace(dest)
    print(f"done  {dest.relative_to(RAW)} ({dest.stat().st_size / 1e6:.0f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, default=2, help="WildChat shards to fetch (1-14)")
    args = parser.parse_args()
    for i in range(min(max(args.shards, 1), 14)):
        fetch(WILDCHAT.format(i=i), RAW / "wildchat" / f"train-{i:05d}.parquet")
    fetch(PHILLY, RAW / "philly" / "trace-data.tar.gz")


if __name__ == "__main__":
    main()
