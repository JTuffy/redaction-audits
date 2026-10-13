"""Inspect plumbing: one sample per scenario, one task per policy.

The solver hands each sample to `trial.run_trial` and stores the `TrialRecord`; the scorer turns
it into a `SampleResult` with the domain's scoring rules and carries it in the score metadata,
so the analysis can rebuild every number from the logs alone.
"""

from __future__ import annotations

from typing import Final

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver

from redaction_escalation.domain.models import Scenario, Split
from redaction_escalation.domain.policies import Policy
from redaction_escalation.domain.roles import Stance
from redaction_escalation.domain.scoring import SampleResult, TrialRecord, sample_result
from redaction_escalation.domain.views import logs_view, report_view
from redaction_escalation.pipeline.trial import run_trial
from redaction_escalation.scenarios.generator import build_split

SCORER_NAME: Final = "redaction_scorer"
_TRIAL_KEY: Final = "trial"
_RESULT_KEY: Final = "result"
_SCENARIO_KEY: Final = "scenario"


def _to_sample(scenario: Scenario) -> Sample:
    """An Inspect sample carrying the whole scenario in its metadata."""
    return Sample(
        id=scenario.scenario_id,
        input=logs_view(scenario),
        target=scenario.label.value,
        metadata={_SCENARIO_KEY: scenario.model_dump(mode="json")},
    )


def _scenario_of(state: TaskState) -> Scenario:
    return Scenario.model_validate(state.metadata[_SCENARIO_KEY])


@solver
def redaction_trial(policy: Policy, stance: Stance) -> Solver:
    """Run one trial of a policy on a scenario and store the raw outputs."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:  # noqa: ARG001
        record = await run_trial(_scenario_of(state), policy, stance)
        state.store.set(_TRIAL_KEY, record.model_dump(mode="json"))
        state.output = ModelOutput.from_content(
            model="pipeline", content=report_view(record.edited)
        )
        return state

    return solve


@scorer(metrics={"*": [mean()]}, name=SCORER_NAME)
def redaction_scorer() -> Scorer:
    """Score a trial; the full `SampleResult` rides along in the score metadata."""

    async def score(state: TaskState, target: Target) -> Score:  # noqa: ARG001
        record = TrialRecord.model_validate(state.store.get(_TRIAL_KEY))
        result = sample_result(_scenario_of(state), record)
        return Score(
            value={
                "viewer_unedited": result.viewer_unedited,
                "viewer_edited": result.viewer_edited,
                "evidence_loss": result.evidence_loss,
                "redaction_volume": result.redaction_volume,
            },
            metadata={_RESULT_KEY: result.model_dump(mode="json")},
        )

    return score


def result_from_metadata(metadata: dict[str, object]) -> SampleResult:
    """Rebuild a `SampleResult` from a score's metadata."""
    return SampleResult.model_validate(metadata[_RESULT_KEY])


@task
def redaction_escalation(
    split: str = Split.DEV.value,
    policy: str = Policy.CONTEXTUAL_REWRITE.value,
    stance: str = Stance.HONEST.value,
    seed: int | None = None,
) -> Task:
    """Redaction Under Escalation for one policy on one split."""
    chosen_split, chosen_policy, chosen_stance = Split(split), Policy(policy), Stance(stance)
    dataset = MemoryDataset(
        [_to_sample(s) for s in build_split(chosen_split, seed=seed)],
        name=f"redaction-escalation-{chosen_split}",
    )
    return Task(
        dataset=dataset,
        solver=redaction_trial(chosen_policy, chosen_stance),
        scorer=redaction_scorer(),
        name=f"redaction_escalation_{chosen_policy}",
        metadata={"split": chosen_split, "policy": chosen_policy, "stance": chosen_stance},
    )
