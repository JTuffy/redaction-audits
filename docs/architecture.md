# Architecture

The code is split so the experiment's logic can be read, tested and changed without Inspect, and so Inspect can be swapped or upgraded without touching that logic. A ruff rule (`TID251`) bans `inspect_ai` imports outside `pipeline/`, `infra/` and `cli.py`.

```
src/redaction_escalation/
  domain/       pure logic, no I/O
    models.py     value types: Scenario, Report, RedactionRequest, Ruling, SecretGuess
    registry.py   the 12 secret types, their tiers, weights and four options each
    policies.py   the three policies and the rules every policy enforces
    views.py      what each reader is allowed to see
    metrics.py    AUROC, persistence, leakage, error rates, bootstrap intervals
    results.py    TrialRecord -> SampleResult -> PolicySummary
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
    task.py       the Inspect task, solver and scorer
    runner.py     runs one task per policy
    analysis.py   reads Inspect logs back into SampleResults
    mock.py       a scripted model for offline runs and tests
  infra/        settings (pydantic-settings), structured logging (structlog), file output
  cli.py        typer commands: generate, run, analyze
```

## One trial

For a scenario and a policy, the solver in `pipeline/task.py`:

1. builds the auditor's report (templated in the MVP);
2. asks the advocate for redaction requests (contextual rewrite and self-redaction);
3. asks the referee to rule on them (contextual rewrite only);
4. applies the policy with `domain.policies.redact`;
5. asks the viewer to score the unedited and the edited evidence;
6. asks the guesser for each secret in the report under three conditions: prior, unedited, edited;
7. asks the judge whether editing changed the finding (skipped when the finding is untouched).

The raw outputs are stored as a `TrialRecord`. The scorer turns it into a `SampleResult` with `domain.results.sample_result`, and the result travels in the score's metadata, so `analyze` can rebuild every number from the logs alone. Cross-sample metrics (AUROC, persistence, mean leakage and their intervals) are computed in `domain.results.summarize`, outside Inspect.

## Decisions worth knowing

- **Leakage is scored only on secrets that appear in the unedited report.** For the others, the unedited report adds nothing over the prior and the ratio is undefined.
- **Unreadable replies are re-asked once with the parsing error.** If the second reply is also unreadable, or the guesser still skips a secret, the sample errors; `analyze` excludes it and logs the count.
- **Referee rulings that are missing count as denials**, and rulings that point at a request that does not exist are ignored.
- **Spans that contain a log ID are never edited**, under any policy (rule 2).
- **Scenarios are seeded per scenario** (`seed:index`), so adding scenarios never changes existing ones.
