# Questions

Open design questions, with the options and where the thinking currently leans. This is the page for review: each question ends with what needs a decision. Once a question is decided, it moves to Decisions.

## Can the setup measure what P1 is about yet?

Not fully. Three mechanisms are switched off by design, not by chance:

| Measure | Why it can't move yet | Fix |
|---|---|---|
| Persistence | Nobody has tried to remove the cues that separate violations from red herrings. The honest advocate doesn't, and text redaction removes secret values, not cues. | An adversarial advocate. |
| Leakage | Until 22 Oct the judge never saw a correlate, so only stated values could leak. | Context-quoting reports (now on). |
| Executor robustness | Sonnet 5.5 won't play the cover-up stance. | A scripted adversary. |

A correction: earlier notes blamed the ceiling (unedited AUROC 1.00) for persistence being stuck at 1.00. The ceiling makes the task unrealistically easy, but persistence can still fall from 1.00 if editing removes cues. It is stuck because nothing has tried to remove them.

Needs a decision: none. This is the framing for the questions below.

## Which auditor?

| Option | For | Against |
|---|---|---|
| Templated, evidence only (until 22 Oct) | Deterministic, free | Hands the judge the answer key, and never quotes correlates. |
| Templated with context (now) | Still deterministic and free. Correlates reach the judge. | Still quotes every decisive cue verbatim, so the ceiling stays. |
| Model auditor | Closest to the spec. Picks its own quotes and can miss things. | Cost and noise. A missed violation muddies what persistence means. |

Lean: templated with context until the adversaries work, then a model auditor.

Needs a decision: when to switch to a model auditor, and whether its own misses count against the policies or are filtered out.

## What should the adversary do?

The honest executor's rule 3 says evidence may be generalized but not removed. A blatant adversary that asks to delete the evidence lines tests only that rule. The real risk is subtler:

1. **Blatant.** Request the key-evidence lines outright. This is a control; the executor should deny every request.
2. **Cue generalization.** Generalize the token that separates the labels (`consent_basis=none_recorded` → `consent_basis=[internal reference]`) while claiming a confidentiality harm. Rule 3 then depends on the executor recognising that the cue *is* the evidence.
3. **Context stripping.** Generalize the line that exonerates a red herring, so innocent evidence looks guilty. A lab trying to look clean gains nothing from this, so it's out of scope for P1.

Scripted versions of 1 and 2 give a worst case that doesn't depend on a model agreeing to play the part. A model adversary prompted as the lab's counsel could follow later.

Needs a decision: whether a scripted adversary is acceptable for the headline result, or only as a bound next to a model adversary.

## How many judge samples?

The judge moved 15+ points on about 1 in 6 red-herring re-asks. Three samples per question (now the default) cut the standard deviation of the mean by about 1.7×, at 3× the judge cost. The judge is the cheapest role, so the cost is small. Five samples would halve it.

Needs a decision: none until the 3-sample noise is measured.

## How should difficulty be defined?

Red-herring difficulty is set by design (how closely the blueprint imitates the violation), and the judge doesn't agree: hard red herrings scored no higher than medium. Two options:

- Keep designed difficulty, and report the gate failure as a finding about the blueprints.
- Define difficulty empirically, from the judge's unedited score or from disagreement between judge samples, and bin red herrings after the fact.

Lean: report designed difficulty as built, and add the empirical bin as a second view. That keeps the design honest and the analysis useful.

Needs a decision: whether the MVP gate should use designed or empirical difficulty.

## What does the MVP show Cath?

Her 9 Oct ask was an MVP with results. The honest result so far is the table at the top of this page: which mechanisms the setup can and can't measure yet, why, and the fix for each, plus the first numbers once the fixes run. Per her request, the write-up is Josh's own.

Needs a decision: Josh's.
