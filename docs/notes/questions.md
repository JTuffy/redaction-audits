# Questions

Open design questions, each with its options, where the thinking leans, and what needs deciding. A decided question moves to Decisions.

## What should a redaction protocol require?

Type markers can hide a real violation (classifier: "change approved for [codename]" reads as covering the endpoint that is off) or make an innocent lab look guilty (opt-out, cot, monitoring). Options:

1. **Consistent pseudonyms** for every redacted entity, so identity across lines survives.
2. **Comparison-preserving generalization** for every number or date a finding compares ("above the reporting threshold").
3. **Explicit entanglement marking**: the redactor states when two redacted spans refer to the same entity or different ones.

What the runs show: 1 restores identity links fully and does nothing for magnitudes and dates; 1 plus 2 (text generalize) also removes the magnitude misses (entangled FNR 0.17 to 0.00); the honest executor enforces both against a link-break attack made of individually legitimate requests.

Leaning: require 1 and 2, enforced by an executor or an equivalent check.

Needs a decision: whether that is the recommendation, and whether 3 is worth testing.

## How do we measure an adversarial lab without an executor?

The red-team framing works when the executor is in the loop, but without one Sonnet's safety filter refused most requests and the run stopped at 28 of 77 scenarios. The scripted attacks bound the no-executor case, but a model adversary is the realistic one. Options:

1. **Another provider as the advocate** for this arm only. Changes the advocate's model between arms, which confounds the comparison.
2. **Another provider for both arms**, re-running the executor arm too. Clean comparison, twice the cost.
3. **Accept the scripted bound** and report the model arm as with-executor only.

Leaning: 2, on dev first.

Needs a decision: which, and whether the cost is acceptable (a few dollars per arm).

## Is the scenario shape, length and quality good enough?

Josh's concern from the pipeline review. Scenarios are 36–68 single-line log records; the evidence is three lines (disjoint) or four to six (entangled). Still missing:

- **Shape.** No multi-line events, stack traces, configs or diffs.
- **Length.** The auditor quotes exactly the relevant lines, so the judge never has to search.
- **Variety.** The template text is terse and uniform; model rendering adds variety but not depth.

The entangled set answers part of this for P1's purposes: what matters is whether the evidence turns on a secret, not how long it is. A transcript scenario type (v3) is the planned answer to shape.

Needs a decision: whether v3 transcripts are worth starting before the paper, or after.

## What does the update to Cath lead with?

Decided on 22 Oct: lead with the leakage contrast. Since then the stronger results are entanglement (markers cost signal only when the secret is the evidence, and can hide violations) and the executor under attack.

Leaning: lead with entanglement and the executor, with leakage as the third point.

Needs a decision: Josh's.
