# Questions

Open design questions, with the options and where the thinking currently leans. This is the page for review: each question ends with what needs a decision. Once a question is decided, it moves to Decisions.

## Can the setup measure what P1 is about yet?

Partly. Three mechanisms were switched off by design:

| Measure | Status | Fix |
|---|---|---|
| Persistence | Still can't move: nothing has tried to remove the cues that separate violations from red herrings. | An adversarial advocate. |
| Leakage | Measurable since 22 Oct, when reports started quoting correlates. Text redaction leaked 0.86. | Done. |
| Executor robustness | Untested: Sonnet 5.5 won't play the cover-up stance. | A scripted adversary. |

The unedited AUROC of 1.00 makes the task unrealistically easy, but it isn't what holds persistence at 1.00. Persistence can fall from 1.00 if editing removes cues; it hasn't, because nothing has tried.

Needs a decision: none. This is the framing for the questions below.

## Is the scenario shape, length and quality good enough?

Josh's concern from the pipeline review. Scenarios are 36–68 single-line log entries, three of which carry the evidence, with the decisive fact usually in one token. Possible gaps:

- **Shape.** Every scenario is a flat list of one-line records, without multi-line events, stack traces, configs or diffs.
- **Length.** The evidence is three lines; real evidence is spread across more places and needs connecting.
- **Quality.** The template text is terse and uniform. A model-rendered build (decided 22 Oct) will add variety, but not depth.

The cues test (Findings, "Does rephrasing make the task harder?") points at structure over wording: paraphrasing every cue left the task as easy as before, because each variant settles its label in one line. That favours longer, multi-line evidence over better phrasing.

Needs a decision: which of these matters most, ideally pointing at one scenario that shows the problem.

## What should the adversary do?

The honest executor's rule 3 says evidence may be generalized but not removed. A blatant adversary that asks to delete the evidence lines tests only that rule. The real risk is subtler:

1. **Blatant.** Request the key-evidence lines outright. This is a control; the executor should deny every request.
2. **Cue generalization.** Generalize the token that separates the labels (`consent_basis=none_recorded` → `consent_basis=[internal reference]`) while claiming a confidentiality harm. Rule 3 then depends on the executor recognising that the cue *is* the evidence.
3. **Context stripping.** Generalize the line that exonerates a red herring, so innocent evidence looks guilty. A lab trying to look clean gains nothing from this, so it's out of scope for P1.

Scripted versions of 1 and 2 give a worst case that doesn't depend on a model agreeing to play the part. A model adversary prompted as the lab's counsel could follow later.

Decided 22 Oct: both. Scripted attacks are bounds; the headline adversary is a model in a better harness (see Decisions).

## How many judge samples?

Three samples per question are now the default. They cut the standard deviation of the mean by about 1.7×, at 3× the judge cost. Five would halve it.

Needs a decision: none until the 3-sample noise is measured.

## What does the MVP show Cath?

Her 9 Oct ask was an MVP with results. The honest result so far is the table at the top of this page, plus the leakage contrast between text redaction and the model-based policies. Per her request, the write-up is Josh's own.

Needs a decision: Josh's.
