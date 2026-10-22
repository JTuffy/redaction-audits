# Decisions

One line per decision, newest first, with the reason. Change a line only to mark a decision as reversed, and say why.

| Date | Decision | Why |
|---|---|---|
| 2026-10-22 | Entangled draft (`--depth entangled`) for opted_out_data, classifier_off and unreported_compute. Scenarios carry `confidential` values: a second customer or codename, redacted like a secret but not scored. Pseudonyms are consistent per value (Customer A, Customer B); markers are per type. | Persistence can only move when the secret is the evidence (Findings). |
| 2026-10-22 | Unedited-only judge runs are labelled "Judge only"; "Re-ask" is kept for cache-off noise runs, and runs now record `cache_replies`. | The site was showing build comparisons as noise re-asks, compared against an older build. |
| 2026-10-22 | `docs/direction.toml` holds the question, hypothesis, focus and experiment threads; the Overview page and run grouping come from it; runs take `--experiment`. | Josh asked for visibility into the direction without being overwhelmed. |
| 2026-10-22 | Deep variants drafted for three types (cot_in_training, opted_out_data, classifier_off): five or six evidence lines per scenario, one shared skeleton per type, label decided by a relation between lines. Built with `--depth deep`, alongside the original set. | Josh, mentor grill: the scenarios lack "sufficient logs or depth"; scale-up waits on better scenarios. |
| 2026-10-22 | Model families: the template build stays the headline; the second label reviewer is GPT-5.6; a third-family reviewer and fallback renderer when a key is available. | Josh delegated this. The judge (GPT-5.6 Terra) is OpenAI and the executor Anthropic. A second reviewer from either family shares blind spots with one role, so the third family is the clean fix, and is noted as open. |
| 2026-10-22 | Lead the MVP with the leakage contrast (text redaction 0.86 vs 0.27 and 0.20). | Mentor grill. |
| 2026-10-22 | Add a summary policy: the executor writes a summary of the evidence instead of editing it. | Mentor grill: puts a second rung of the brief's access ladder on the curve. |
| 2026-10-22 | Paper target: NeurIPS Datasets & Benchmarks track. | Mentor grill. |
| 2026-10-22 | Report the honest and the adversarial lab separately: leakage leads the first, persistence the second. | Mentor grill. |
| 2026-10-22 | Scope stated plainly: P1 measures whether a finding survives redaction, not whether it is found. Model auditor after the adversaries. | Mentor grill. |
| 2026-10-22 | Variants and adversaries in parallel. The adversary gets a better harness (a model that will play the role), with scripted attacks as bounds. | Mentor grill; Josh: "we can work around this, maybe with better harness". |
| 2026-10-22 | Second label reviewer from another model family, no human pass yet. | Mentor grill. |
| 2026-10-22 | Full dev and val runs wait for the deeper scenarios. | Mentor grill (Josh's note). |
| 2026-10-22 | Self-redaction is the no-executor baseline: the executor's value is the gap to contextual rewrite. | Mentor grill. |
| 2026-10-22 | Separate the redaction-display choices in the ablation: marker alone, marker with rationale, pseudonym. | Mentor grill (Josh: see these choices separated). |
| 2026-10-22 | FOIA redaction benchmarks: related work only. ZK proofs and TEEs: out of scope. Realism: internal validity only, stated in limitations. | Mentor grill. |
| 2026-10-22 | Repo goes public at paper time; test split released as a sealed eval. No weekly update this week. | Mentor grill. |
| 2026-10-22 | The paper lives in `paper/` (NeurIPS 2025 style, compiled with Tectonic), with a live Paper page on the site. Numbers in the text come from generated macros. | Josh asked for a live paper page. Overleaf has no plugin API and its Git sync needs a paid plan; generated numbers can't drift from the runs. |
| 2026-10-22 | Cues stay verbatim in the reference build; paraphrase mode stays available. | Built both: separation was unchanged (AUROC 1.00 vs 0.99), so the variants, not the tokens, make the task easy. |
| 2026-10-22 | Dev `LATEST` is the template build; the model-rendered builds are kept beside it. | Rephrasing didn't change difficulty, and the template build has no renderer-family confound. |
| 2026-10-22 | Renderer refusals are their own issue. The render prompt says the data is synthetic, and GPT-5.6 renders any attempt Sonnet refuses (`--fallback`). | Sonnet 5.5's content filter refused 40–45% of render requests, mostly about monitoring and classifiers, which the validator had logged as hundreds of empty lines. |
| 2026-10-22 | Fixed the claims of skipped_eval, monitoring_off and opted_out_data, and four variants, after the blind reviewer disagreed with 15 scenarios. | Every disagreement was a blueprint bug (see Findings, "Are the labels right?"). |
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
