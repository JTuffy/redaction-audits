# Architecture

The code is split so the experiment's logic can be read, tested and changed without Inspect, and so Inspect can be swapped or upgraded without touching that logic. Two checks keep the layers honest: a ruff rule (`TID251`) bans `inspect_ai` imports outside `pipeline/`, `infra/` and `cli.py`, and `tests/unit/test_architecture.py` fails if a package imports from a layer above it.

Allowed dependencies: `scenarios` and `infra` use `domain`; `pipeline` uses all of them plus `prompts`; `cli` sits on top. `domain` imports nothing from the package outside itself.

```
src/redaction_escalation/
  domain/       pure logic, no I/O, no Inspect
    models.py     value types: Scenario, Report, RedactionRequest, Ruling, SecretGuess
    roles.py      the model roles and the advocate's stance
    registry.py   the 12 secret types, their tiers, weights and four options each
    policies.py   the three policies and the rules every policy enforces
    views.py      what each reader is allowed to see
    metrics.py    AUROC, persistence, leakage, error rates, bootstrap intervals
    scoring.py    one trial: TrialRecord -> SampleResult
    summary.py    many samples: SampleResult -> PolicySummary, and the markdown table
  scenarios/    deterministic scenario generation (pure)
    blueprints.py the log lines behind each violation type and its red herrings
    generator.py  splits built from blueprints, seeded per scenario
    reports.py    templated audit reports for the MVP
  prompts/      prompt templates as text files, filled with string.Template
  pipeline/     everything that talks to models
    prompting.py  builds each role's prompt (pure)
    schemas.py    the JSON contract for each role's reply
    parsing.py    extracts and validates JSON from a reply
    calls.py      one async function per role; retries unreadable replies
    trial.py      the experiment's procedure for one scenario, policy and stance
    task.py       Inspect plumbing: dataset, solver, scorer
    runner.py     runs one task per policy
    analysis.py   reads Inspect logs back into results and writes a run's summary files
    mock.py       a scripted model for offline runs and tests
  infra/        settings (pydantic-settings), structured logging (structlog), file output
  cli.py        typer commands: generate, run, analyze
```

## One trial

`pipeline/trial.run_trial` holds the procedure. For a scenario, a policy and a stance it:

1. builds the auditor's report (`audit_report`; templated in the MVP);
2. asks the advocate for redaction requests (contextual rewrite and self-redaction);
3. asks the honest executor to rule on them (contextual rewrite only);
4. applies the policy with `domain.policies.redact`;
5. asks the "human" judge, which sees only the claim and the quoted evidence, how likely a violation is, on the unedited and the edited evidence;
6. asks the "human" judge for each secret in the evidence under three conditions: prior, unedited, edited;
7. runs the finding-integrity check: did editing change the finding (skipped when the finding is untouched)? This is a measurement, not a participant.

It returns a `TrialRecord`. The Inspect solver in `task.py` only stores that record; the scorer turns it into a `SampleResult` with `domain.scoring.sample_result`, and the result travels in the score's metadata, so `analyze` can rebuild every number from the logs alone. Cross-sample metrics (AUROC, persistence, mean leakage and their intervals) are computed in `domain.summary`, outside Inspect.

Swapping the templated report for a model auditor means changing `audit_report` and adding an auditor role in `calls.py`; nothing in `task.py` or the domain changes.

## Decisions worth knowing

- **A scenario carries its own claim.** Prompts read `scenario.claim`, so the pipeline never reaches into the scenario blueprints.
- **Prompt text lives in `prompts/`, not in Python.** Changing a template changes the prompt hash and therefore the cache key, which is the point: a cached reply is only reused for an identical prompt.
- **Terminology.** The roles are the auditor, the lab advocate, the honest executor and the "human" judge. The finding-integrity check is a measurement, not a role.
- **The "human" judge sees evidence only, for both questions.** A judge that could read the finding would copy the auditor's verdict. The cost is that secrets restated only in the finding or reasoning are not scored.
- **Leakage is scored only on secrets that appear in the unedited evidence.** For the others, the unedited evidence adds nothing over the prior and the ratio is undefined.
- **Unreadable replies are re-asked once with the parsing error.** If the second reply is also unreadable, or the "human" judge still skips a secret, the sample errors; `analyze` excludes it and logs the count.
- **Honest executor rulings that are missing count as denials**, and rulings that point at a request that does not exist are ignored.
- **Spans that contain a log ID are never edited**, under any policy (rule 2).
- **Scenarios are seeded per scenario** (`seed:index`), so adding scenarios never changes existing ones.
