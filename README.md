# Redaction Under Escalation

Evaluation harness for Proposal 1 of the SPAR Fall 2026 privacy-preserving redaction workstream. It measures how much audit signal survives when a lab edits an audit report before outside readers see it, and how much of the lab's confidential information still gets through.

Three redaction policies are compared on the same scenarios:

- **Text redaction:** a script removes every value in the secret registry.
- **Contextual rewrite:** a lab advocate asks for redactions or generalizations, and a neutral referee rules on each one under six rules. Text redaction still applies afterwards.
- **Self-redaction:** the advocate's requests are applied without review (the control).

For each scenario and policy, a viewer scores the edited evidence for suspicion, and a guesser estimates each secret before reading the report, after reading the unedited report and after reading the edited one. The headline numbers are signal persistence, `(AUROC_edited − 0.5) / (AUROC_unedited − 0.5)` over violations against red herrings, and leakage, `(p_edited − p_prior) / (p_unedited − p_prior)` per secret. Both are lower bounds.

The full specification is in the P1 Google Doc. `docs/architecture.md` explains how the code is laid out.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```powershell
uv sync
uv run pre-commit install
copy .env.example .env   # then add API keys
```

## Usage

```powershell
uv run redesc generate --split dev          # write scenarios and templated reports to data/generated
uv run redesc run --mock                    # full pipeline offline, scripted model
uv run redesc run --split dev               # real models, all three policies
uv run redesc run --policy contextual_rewrite --stance cover_up --limit 10
uv run redesc analyze logs/inspect/<run>    # recompute the summary from saved logs
```

Each run writes Inspect logs under `logs/inspect/<run>` (open them with `uv run inspect view`) and a summary under `results/<run>`: `summary.md`, `summary.json` and one `SampleResult` per line in `samples.jsonl`.

Models are set per role with `REDESC_ADVOCATE_MODEL`, `REDESC_REFEREE_MODEL`, `REDESC_VIEWER_MODEL`, `REDESC_GUESSER_MODEL` and `REDESC_JUDGE_MODEL`. Model replies are cached, so conditions shared across policies (the prior and the unedited report) are paid for once.

## Development

```powershell
uv run pytest              # unit and offline end-to-end tests, with coverage
uv run pytest -m "not e2e" # unit tests only
uv run ruff check .
uv run ruff format .
uv run mypy src tests
```

## Status

The MVP uses templated audit reports on the dev split (40 scenarios). Replacing them with a model auditor, the remaining runs (R3 to R7) and the val and test splits come next.
