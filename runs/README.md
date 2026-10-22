# Run ledger

Every real-model run is recorded here. `logs/` and `results/` stay git-ignored, because they are large and can be regenerated. This folder is small and committed.

- `ledger.jsonl` has one line per run, appended when the run finishes.
- `<run>/run.json` records what was run, the commit and whether the tree was dirty, the purpose (`--purpose`), models and reasoning per role, sample IDs, and tokens per model.
- `<run>/` also holds copies of the run's small summary files: `summary.md`, `checks.md`, `samples.jsonl`, `tradeoff.png`, `ablation.md`.

Runs made before the ledger existed (21 Oct 2026, before `p1-dev-cover_up-*`) were added by hand from their results folders, with `"backfilled": true`.

Mock runs are never recorded. Full transcripts stay in `logs/inspect/<run>`, which you can open with `uv run inspect view`.

Each real run also rebuilds the viewer (`site/dist`), which `tailnet-serve` publishes at `/projects/redaction`. If the page is down, run `tailnet-serve.ps1 ensure redaction` from agent-os.

Interpretation lives in `docs/notes/`, not here: Findings (by question, with a status) and Decisions (one dated line each). Edit those pages in place.
