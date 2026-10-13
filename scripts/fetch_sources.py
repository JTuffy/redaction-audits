"""Download the real-world source data used as backbone for scenario generation.

Sources:
- MALT-public (METR, MIT): manually reviewed agent transcripts labelled for sabotage,
  constraint bypassing, hardcoded solutions and so on. Gated: accept the terms at
  https://huggingface.co/datasets/metr-evals/malt-public, then set HF_TOKEN (a read token)
  in the environment or .env, or run `hf auth login`.
- Philly traces (Microsoft, CC-BY-4.0): 117k deep-learning training jobs with users, GPU
  allocations, attempts and outcomes. Not gated.

Files land in data/raw/ (git-ignored). Re-running skips files that are already complete.

    uv run python scripts/fetch_sources.py               # 3 MALT shards (~180 MB) + Philly
    uv run python scripts/fetch_sources.py --shards 41   # all of MALT's default config (~5 GB)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MALT = "https://huggingface.co/datasets/metr-evals/malt-public/resolve/main/default/public-{i:05d}-of-00041.parquet"
PHILLY = "https://github.com/msr-fiddle/philly-traces/raw/master/trace-data.tar.gz"


def hf_token() -> str | None:
    if token := os.environ.get("HF_TOKEN"):
        return token
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("HF_TOKEN=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip()
    cached = Path.home() / ".cache" / "huggingface" / "token"
    return cached.read_text(encoding="utf-8").strip() if cached.exists() else None


def fetch(url: str, dest: Path, token: str | None = None) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip  {dest.relative_to(RAW)} (exists)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url)  # noqa: S310
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    print(f"fetch {url}")
    with urllib.request.urlopen(request) as response, partial.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(response, out, length=1 << 20)
    partial.replace(dest)
    print(f"done  {dest.relative_to(RAW)} ({dest.stat().st_size / 1e6:.0f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, default=3, help="MALT shards to fetch (1-41)")
    args = parser.parse_args()
    fetch(PHILLY, RAW / "philly" / "trace-data.tar.gz")
    token = hf_token()
    if token is None:
        sys.exit("MALT needs HF_TOKEN: accept the dataset terms on Hugging Face, then set it.")
    for i in range(min(max(args.shards, 1), 41)):
        fetch(MALT.format(i=i), RAW / "malt" / f"public-{i:05d}.parquet", token)


if __name__ == "__main__":
    main()
