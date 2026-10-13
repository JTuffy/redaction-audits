# Redaction audits

Evaluation harnesses for the SPAR Fall 2026 privacy-preserving redaction workstream. Two proposals share one secret registry, one leakage definition and one scenario pipeline, so their results can be compared directly:

- **Proposal 1, Redaction Under Escalation** (`src/redaction/escalation`): how much audit signal survives when a lab edits an audit report before outside readers see it, and how much of the lab's confidential information still gets through.
- **Proposal 2, Redaction Detective** (`src/redaction/detective`, not built yet): how leakage grows when an auditor can ask many questions and every answer is redacted.

`docs/architecture.md` explains how the code is laid out. The specifications are in the P1 and P2 Google Docs.

## Proposal 1 in brief

Three redaction policies are compared on the same scenarios:

- **Text redaction:** a script removes every value in the secret registry.
- **Contextual rewrite:** a lab advocate asks for redactions or generalizations, and an honest executor rules on each one under six rules. Always-redact values (exact hyperparameters, data mix, customer and employee names) are removed afterwards whatever the executor decides; context-tier values are left to the executor.
- **Self-redaction:** the advocate's requests are applied without review (the control).

For each scenario and policy, a "human" judge sees only the claim and the quoted evidence and answers two questions: how likely the lab broke the claim, and a probability for each option of every planted secret. It answers on the edited evidence, on the unedited evidence and, for the secrets, with no evidence at all (the prior). The headline numbers are signal persistence, `(AUROC_edited − 0.5) / (AUROC_unedited − 0.5)` over violations against red herrings, and leakage, `(p_edited − p_prior) / (p_unedited − p_prior)` per secret. Both are lower bounds.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```powershell
uv sync
uv run pre-commit install
copy .env.example .env   # then add API keys, and HF_TOKEN for the MALT source data
```

## Usage

```powershell
uv run redaction data generate --split dev        # scenarios and templated reports to data/generated
uv run redaction p1 run --mock                    # full P1 pipeline offline, scripted model
uv run redaction p1 run --split dev               # real models, all three policies
uv run redaction p1 run --policy contextual_rewrite --stance cover_up --limit 10
uv run redaction p1 analyze logs/inspect/<run>    # recompute the summary from saved logs

uv run python scripts/fetch_sources.py            # real source data (MALT, Philly) into data/raw/
uv run python scripts/inspect_sources.py          # profile the source data
uv run python scripts/botec.py                    # reproduce the compute budget
```

Each P1 run writes Inspect logs under `logs/inspect/<run>` (open them with `uv run inspect view`) and a summary under `results/<run>`: `summary.md`, `summary.json`, one `SampleResult` per line in `samples.jsonl`, `checks.md` (the MVP gate: unedited "human" judge AUROC ≥ 0.65, and red-herring suspicion rising easy < medium < hard) and `tradeoff.png` (persistence against leakage, one point per policy).

Models are set per role with `REDACTION_ADVOCATE_MODEL`, `REDACTION_EXECUTOR_MODEL`, `REDACTION_JUDGE_MODEL` and `REDACTION_INTEGRITY_CHECK_MODEL`. Model replies are cached, so conditions shared across policies (the prior and the unedited report) are paid for once.

## Development

```powershell
uv run pytest              # unit and offline end-to-end tests, with coverage
uv run pytest -m "not e2e" # unit tests only
uv run ruff check .
uv run ruff format .
uv run mypy src tests
```

## Status

P1: the full pipeline runs offline with templated audit reports on the dev split (40 scenarios); it has not yet run on real models. Next: API keys, the first real dev run, then a model auditor and source-backed scenarios. P2: specified, not built.
