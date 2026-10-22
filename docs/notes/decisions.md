# Decisions

One line per decision, newest first, with the reason. Change a line only to mark a decision as reversed, and say why.

| Date | Decision | Why |
|---|---|---|
| 2026-10-22 | The scenarios are a controlled benchmark, and the scenario set is itself a deliverable: versioned, documented, labels validated, test split held out. | Pipeline review. Cath named a redaction benchmark as the workstream's main output. |
| 2026-10-22 | Stay with log scenarios for P1; build an agent-transcript scenario type as v3 afterwards. | Pipeline review. The threat models put evidence in agent sessions, but P1's first results shouldn't wait. |
| 2026-10-22 | Validate labels with the blind model reviewer on every build first; a human pass only if that raises doubts. | Pipeline review (Josh's note). Labels are the part he trusts least. |
| 2026-10-22 | Widen the registry to 8–12 options per secret. | Pipeline review. Recovering one of four is too easy. |
| 2026-10-22 | Judge both ways: a frontier judge (upper bound) and a weaker one (realistic reader). | Pipeline review. |
| 2026-10-22 | Model auditor only after the adversaries are measured. | Pipeline review. |
| 2026-10-22 | Leakage: exact-value leakage stays the headline, with entropy reduction alongside; also reported by correlate strength. | Pipeline review (delegated, then chosen). Exact value misses narrowing. |
| 2026-10-22 | Difficulty: the MVP gate stays on designed difficulty, with empirical bins (judge's unedited score) as a second view. | Pipeline review (delegated). |
| 2026-10-22 | A hard red herring closely matches a violation and takes careful cross-analysis to clear. | Josh's definition. One decisive token can't produce this, so the blueprints need redesigning. |
| 2026-10-22 | Hand-write 2–3 variants per label per violation type; Claude drafts, Josh reviews. Keep the six types. | Pipeline review. One template per cell risks measuring the template. |
| 2026-10-22 | Test split: keep its composition; report AUROC on violations vs red herrings and FPR on clean separately. | Pipeline review (delegated). Clean-heavy test gives realistic base rates for false positives. |
| 2026-10-22 | Keep real Philly background lines and the noise secret. More correlates: a model proposes, code checks each recovers its value alone. | Pipeline review. |
| 2026-10-22 | Redwood transcripts: later, as a held-out eval that Cath runs. | Pipeline review. They can't be shared. |
| 2026-10-22 | Commit the dev and val builds; make a model-rendered build now. | Pipeline review. |
| 2026-10-22 | The CLI loads the repo `.env` with override. | A user-level `OPENAI_API_KEY` on the PC silently replaced the experiment key and every judge call failed with 401. |
| 2026-10-22 | Added a Questions page for open design questions. | One place to review and decide; decided questions move here. |
| 2026-10-22 | Reports quote context: key evidence, every correlate line, and two innocent lines (`REDACTION_REPORT_CONTEXT`, default on). | The judge never saw a correlate, so leakage could only be verbatim. Quoting what surrounds a finding is also closer to a real auditor. |
| 2026-10-22 | Secrets are scored when their value is quoted or one of their correlate lines is. | Otherwise a secret given away only by a correlate would never be scored. |
| 2026-10-22 | The judge answers every question 3 times and scores are averaged (`REDACTION_JUDGE_SAMPLES`). | One sample moved 15+ points on about 1 in 6 red-herring re-asks. Each sample is cached separately, so reruns are free. |
| 2026-10-22 | Runs read the latest frozen v2 build (`data/built/<split>/LATEST`); v1 only as a fallback. | The Scenarios page should show what the judge saw, and the ledger should name the data version. |
| 2026-10-22 | Notes are fixed pages edited in place: Pipeline, Protocol, Findings, Decisions. | An append-only log buried the current state. |
| 2026-10-21 | Every real run is recorded in `runs/` (ledger, run.json, summaries); mock runs are not. | Results and logs are git-ignored, so the record of what ran needs to live somewhere committed. |
| 2026-10-21 | Each recorded run rebuilds the viewer. | The site had gone stale and was down without anyone noticing. |
| 2026-10-21 | Judge reasoning effort `low`. | GPT-5.6 Terra rejects `minimal`; this is only a proof of concept, so `low` was fine. |
| 2026-10-21 | Reworded the self-redaction prompt about log IDs. | The advocate read “spans that contain a log ID are never changed” as “log lines can't be edited” and requested nothing. |
| 2026-10-21 | API keys live only in the repo's `.env`, funded with $40 per provider. | Josh: keep these keys specific to these experiments. |
| 2026-10-21 | Start small: 3 scenarios, then a 12-scenario mixed subset, before full splits. | Find protocol bugs cheaply. |
