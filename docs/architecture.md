# Architecture

One repository holds both proposals and the data they share, because their results are only comparable if they use the same secret registry, leakage definition and scenario data. Each proposal is its own package; neither imports the other.

Two checks keep the layers honest. `tests/unit/test_architecture.py` fails if a package imports from a layer it should not:

| Package | May import from |
|---|---|
| `core` | itself only |
| `data` | `core` |
| `infra` | `core` |
| `escalation` (P1) | `core`, `data`, `infra` |
| `detective` (P2) | `core`, `data`, `infra` |
| `viewer` (the site) | `core`, `infra` |
| `paper` | `core`, `infra` |

A ruff rule (`TID251`) also bans `inspect_ai` everywhere except `infra/`, `cli.py` and the escalation modules that drive Inspect (`calls`, `trial`, `task`, `runner`, `analysis`, `mock`, `ablation_task`) and `viewer/build.py`. Everything else, including P1's policies and metrics, is pure and testable without Inspect.

```
src/redaction/
  core/          shared foundations, pure
    models.py      value types: Scenario, Report, RedactionRequest, Ruling, SecretGuess
    registry.py    the 12 secret types, their tiers, weights and eight options each
    roles.py       model roles and the advocate's stance (honest, red team, scripted attacks)
    metrics.py     AUROC, persistence, leakage, error rates, bootstrap intervals
    parsing.py     extracts and validates JSON from a model reply
  data/          scenario data shared by both proposals
    blueprints.py  the evidence lines behind each violation type and its red herrings, per set
                   (disjoint, entangled; deep archived)
    correlates.py  details that reveal a secret without stating it
    background.py  the Philly job sample (sizes, durations, outcomes)
    lab_background.py  background lines in the evidence's own style, built from that sample
    generator.py   split composition and neutral values, seeded per scenario
    reports.py     templated audit reports for the P1 MVP
    frozen.py      reads the latest frozen build of a split; runs use it, v1 generator as fallback
    pipeline/      plan, render, validate (+ surface.py), freeze (see docs/notes/pipeline.md)
  escalation/    Proposal 1, Redaction Under Escalation
    policies.py    the five policies and the rules every policy enforces
    pseudonyms.py  consistent stand-ins for redacted values
    adversary.py   the scripted attacks' requests
    views.py       what each role is allowed to see
    scoring.py     one trial: TrialRecord -> SampleResult
    summary.py     many samples: SampleResult -> PolicySummary, and the markdown table
    prompting.py   builds each role's prompt from templates in prompts/
    schemas.py     the JSON contract for each role's reply
    calls.py       one async function per role; retries unreadable replies
    trial.py       the procedure for one scenario, policy and stance
    task.py        Inspect plumbing: dataset, solver, scorer
    runner.py      runs one task per policy
    analysis.py    reads Inspect logs back into results and writes a run's summary files
    ablation.py    marker ablation conditions: unedited, marker, pseudonym, marker_only (pure)
    ablation_task.py  the ablation's Inspect task, runner and summary table
    mock.py        a scripted model for offline runs and tests
    prompts/       prompt templates as text files, filled with string.Template
  detective/     Proposal 2, Redaction Detective (not built yet)
  infra/         settings (pydantic-settings), structured logging (structlog), file output,
                 and the run ledger (runs.py)
  viewer/        the static site
    build.py       site.json from builds, runs, notes, the direction file and the paper
    results.py     running findings: per-run rows and measures pooled across runs
    public.py      the public profile: scrub, lint, publish (Pages or Firebase Hosting)
    static/        the page itself (app.js, style.css, index.html)
  paper/         generated tables and macros, figures from runs, Tectonic compile
  cli.py         redaction data build | p1 run | analyze | ablate | paper … | site | publish | deploy
runs/            the committed run ledger: one record per real run (see runs/README.md)
docs/notes/      Pipeline, Protocol, Findings, Questions, Decisions: edited in place, shown on the site's Notes page
docs/direction.toml  the question, hypotheses with their measures, experiment threads: the site's Overview and Runs grouping
docs/publishing.md   the public build and how it gets deployed
scripts/
  botec.py            reproduces the compute budget
  fetch_sources.py    downloads real source data (MALT, Philly) into data/raw/
  inspect_sources.py  profiles the downloaded source data
```

## One P1 trial

`escalation/trial.run_trial` holds the procedure. For a scenario, a policy and a stance it:

1. builds the auditor's report (`audit_report`; templated in the MVP);
2. asks the lab advocate for redaction requests (contextual rewrite and self-redaction);
3. asks the honest executor to rule on them (contextual rewrite only);
4. applies the policy with `escalation.policies.redact`;
5. asks the "human" judge, which sees only the claim and the quoted evidence, how likely a violation is, on the unedited and the edited evidence;
6. asks the "human" judge for each secret in the evidence under three conditions: prior, unedited, edited;
7. runs the finding-integrity check: did editing change the finding (skipped when the finding is untouched)? This is a measurement, not a participant.

It returns a `TrialRecord`. The Inspect solver in `task.py` only stores that record; the scorer turns it into a `SampleResult` with `escalation.scoring.sample_result`, and the result travels in the score's metadata, so `p1 analyze` can rebuild every number from the logs alone. Cross-sample metrics are computed in `escalation.summary`, outside Inspect; the MVP gate checks in `escalation.checks` and the trade-off plot in `escalation.plots`.

Swapping the templated report for a model auditor means changing `audit_report` and adding an auditor role in `calls.py`; nothing in `task.py` or `core` changes.

## Decisions worth knowing

- **Terminology.** The roles are the auditor, the lab advocate, the honest executor and the "human" judge. The finding-integrity check is a measurement, not a role.
- **A scenario carries its own claim.** Prompts read `scenario.claim`, so P1 never reaches into the blueprints.
- **Prompt text lives in `prompts/`, not in Python.** Changing a template changes the prompt hash and therefore the cache key: a cached reply is only reused for an identical prompt.
- **The "human" judge sees evidence only, for both questions.** A judge that could read the finding would copy the auditor's verdict. The cost is that secrets restated only in the finding or reasoning are not scored.
- **Leakage is scored only on secrets that appear in the unedited evidence.** For the others the ratio is undefined.
- **Reasoning effort is set per role** (`REDACTION_*_REASONING`) and passed as Inspect's `reasoning_effort`. It is part of the frozen protocol because it moves both cost and results. How each provider maps the setting is unverified until the first real-model run on dev.
- **Unreadable replies are re-asked once with the parsing error.** If the second reply is also unreadable, or the "human" judge still skips a secret, the sample errors; `p1 analyze` excludes it and logs the count.
- **Missing executor rulings count as denials**, and rulings that point at a request that does not exist are ignored.
- **Spans that contain a log ID are never edited**, under any policy (rule 2).
- **Scenarios are seeded per scenario** (`seed:index`), so adding scenarios never changes existing ones.
- **Shared code moves to `core` only when a second proposal needs it.** For example, `calls.ask` stays in `escalation` until P2 is built.

- **Every real run is recorded.** `p1 run` and `p1 ablate` append to `runs/ledger.jsonl` and write `runs/<run>/run.json` with the commit, a dirty flag, `--purpose`, models, reasoning and tokens per model, and copy the small summary files. Mock runs are not recorded. Commit before a run so its record points at real code.
