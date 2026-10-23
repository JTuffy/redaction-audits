# Redaction audits

Evaluation harnesses for the SPAR Fall 2026 privacy-preserving redaction workstream. Two proposals share one secret registry, one leakage definition and one scenario pipeline, so their results can be compared directly:

- **Proposal 1, Redaction Under Escalation** (`src/redaction/escalation`): how much audit signal survives when a lab edits an audit report before outside readers see it, and how much of the lab's confidential information still gets through.
- **Proposal 2, Redaction Detective** (`src/redaction/detective`, not built yet): how leakage grows when an auditor can ask many questions and every answer is redacted.

`docs/architecture.md` explains how the code is laid out. The specifications are in the P1 and P2 Google Docs.

## Proposal 1 in brief

Five redaction policies are compared on the same scenarios:

- **Text redaction:** a script replaces every registry value with a per-type marker.
- **Text pseudonyms:** a script replaces each value with a consistent pseudonym (Customer A, Customer B).
- **Text generalize:** pseudonyms, plus numbers and dates generalized in a way that keeps the comparison a finding turns on ("above the reporting threshold").
- **Contextual rewrite:** a lab advocate asks for redactions or generalizations, and an honest executor rules on each one under six rules. Always-redact values are removed afterwards whatever the executor decides.
- **Self-redaction:** the advocate's requests are applied without review (the no-executor control).

The advocate's stance is honest, red team (the advocate model framed as an authorized exercise), or a scripted attack with no model: link-break (a type marker on every confidential value) or evidence removal.

For each scenario and policy, a "human" judge sees only the claim and the quoted evidence and answers two questions: how likely the lab broke the claim, and a probability for each option of every planted secret. It answers on the edited evidence, on the unedited evidence and, for the secrets, with no evidence at all (the prior). The headline numbers are signal persistence, `(AUROC_edited − 0.5) / (AUROC_unedited − 0.5)` over violations against red herrings, and leakage, `(p_edited − p_prior) / (p_unedited − p_prior)` per secret, clipped to [0, 1].

The benchmark has two sets per split: **disjoint** scenarios, where secrets and evidence are separate, and **entangled** ones, where the secret is the link the finding turns on. Current results are on the site's Overview and in `docs/notes/findings.md`.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```powershell
uv sync
uv run pre-commit install
copy .env.example .env   # then add API keys, and HF_TOKEN for the MALT source data
```

## Usage

```powershell
uv run redaction data build --split dev           # the benchmark (disjoint + entangled) into data/built/dev/<version>
uv run redaction p1 run --mock                    # full P1 pipeline offline, scripted model
uv run redaction p1 run --split dev --experiment entangled --purpose "..."   # real models, every policy
uv run redaction p1 run --split dev --stance scripted_link --policy contextual_rewrite --policy self_redaction
uv run redaction p1 ablate --split dev            # marker ablation (judge only)
uv run redaction p1 analyze logs/inspect/<run>    # recompute the summary from saved logs
uv run redaction deploy                           # figures, paper, private site, public build (linted, not pushed)

uv run python scripts/fetch_sources.py            # real source data (MALT, Philly) into data/raw/
uv run python scripts/botec.py                    # reproduce the compute budget
```

Each real run is recorded in `runs/` (ledger, `run.json`, summary files and per-sample results) and rebuilds the site. Inspect logs go under `logs/inspect/<run>` (`uv run inspect view`), summaries under `results/<run>`.

### Synthetic data pipeline

```powershell
uv run redaction data background                  # sample 5,000 real jobs from the Philly trace (once)
uv run redaction data build --split dev           # plan, render, validate, freeze into data/built/dev/<version>
uv run redaction data build --split dev --background philly   # reproduce the pre-2026-10-23 background
uv run redaction data build --split dev --renderer anthropic/claude-sonnet-5-5 --fallback openai/gpt-5.6
uv run redaction data build --split dev --renderer anthropic/claude-sonnet-5-5 --fallback openai/gpt-5.6 --cues paraphrase
uv run redaction site                             # static viewer into site/dist (pipeline + runs + Inspect View)
```

The pipeline has four layers (`src/redaction/data/pipeline/`):

1. **Plan** (`plan.py`): code fixes every fact: label, violation evidence, secret values, **correlates** (details that reveal a secret without stating it, from `data/correlates.py`), and background lines in the evidence's own sources and style, with job sizes and outcomes from the Philly trace (`data/lab_background.py`, `data/background.py`).
2. **Render** (`render.py`, `model_render.py`): the template renderer copies the planned text; a model renderer rephrases every line except the background, keeping secret values, cue tokens and correlate details verbatim (or, with `--cues paraphrase`, stating evidence cues in plain words). `--fallback` renders attempts the main model refuses.
3. **Validate** (`validate.py`, `surface.py`): eight code checks (values and cues kept, correlates kept and not stating the value, no other option of a secret, no violation-only token in a non-violation, background untouched, no duplicates), a blind model reviewer (on by default) that must read the label correctly, and `surface_auroc`: how well surface features alone tell planted lines from background (0.5: not at all).
4. **Freeze** (`build.py`): kept scenarios, plans, per-scenario records and a manifest, under a version hash.

The template build passes the code checks by construction; they earn their keep once a model renders.

### Site

The private viewer is served on the tailnet at `/projects/redaction` via agent-os `tailnet-serve` (app `redaction`); `uv run redaction site` refreshes it, and every recorded run does so by itself. The Overview pools every full run per hypothesis (the `[[question]]` entries in `docs/direction.toml`).

A public profile of the same site (`uv run redaction site --public`, or `publish`) drops internal pages and transcripts, replaces names with roles, and fails a lint on anything private-looking. It is built and linted on every `deploy` but pushed only when publishing is switched on; see `docs/publishing.md` for the GitHub Pages or Firebase Hosting target and the Google Sites embed.

Models are set per role with `REDACTION_ADVOCATE_MODEL`, `REDACTION_EXECUTOR_MODEL`, `REDACTION_JUDGE_MODEL` and `REDACTION_INTEGRITY_CHECK_MODEL`. Model replies are cached, so conditions shared across policies (the prior and the unedited report) are paid for once.

### Paper

```powershell
uv run redaction paper watch                      # recompile paper/ on every save; the site's Paper page reloads itself
uv run redaction paper build                      # compile once (Tectonic) and regenerate paper/generated/
```

See `paper/README.md`.

## Development

```powershell
uv run pytest              # unit and offline end-to-end tests, with coverage
uv run pytest -m "not e2e" # unit tests only
uv run ruff check .
uv run ruff format .
uv run mypy src tests
```

## Status

P1: full dev runs on the benchmark for every policy under the honest lab and three adversaries; results on the site and in `docs/notes/findings.md`. Next: rerun the headline cells on the lab-background builds, replicate on val, a model adversary without the executor. P2: specified, not built.
