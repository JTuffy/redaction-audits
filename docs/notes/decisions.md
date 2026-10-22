# Decisions

One line per decision, newest first, with the reason. Change a line only to mark a decision as reversed, and say why.

| Date | Decision | Why |
|---|---|---|
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
