"""The Inspect task: one sample per scenario, one task per policy.

The solver runs a whole trial (advocate, referee, redaction, viewer, guesser, judge) and stores
a `TrialRecord`; the scorer turns it into a `SampleResult` with the domain's scoring rules.
Cross-sample metrics such as AUROC and persistence are computed afterwards from the logs.
"""

from __future__ import annotations

from typing import Final

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.util import collect

from redaction_escalation.domain.models import Scenario, Split
from redaction_escalation.domain.policies import Policy, redact
from redaction_escalation.domain.results import (
    SampleResult,
    TrialRecord,
    sample_result,
    secrets_in_report,
)
from redaction_escalation.domain.views import logs_view, report_view
from redaction_escalation.infra.log_setup import get_logger
from redaction_escalation.pipeline import calls
from redaction_escalation.pipeline.prompting import Stance
from redaction_escalation.scenarios.generator import build_split
from redaction_escalation.scenarios.reports import templated_report

TRIAL_KEY: Final = "trial"
RESULT_KEY: Final = "result"
SCENARIO_KEY: Final = "scenario"
SCORER_NAME: Final = "redaction_scorer"

log = get_logger(__name__)


def to_sample(scenario: Scenario) -> Sample:
    """An Inspect sample carrying the whole scenario in its metadata."""
    return Sample(
        id=scenario.scenario_id,
        input=logs_view(scenario),
        target=scenario.label.value,
        metadata={SCENARIO_KEY: scenario.model_dump(mode="json")},
    )


def scenario_of(state: TaskState) -> Scenario:
    """The scenario a sample was built from."""
    return Scenario.model_validate(state.metadata[SCENARIO_KEY])


@solver
def redaction_trial(policy: Policy, stance: Stance) -> Solver:
    """Run one trial of a policy on a scenario and store the raw outputs."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:  # noqa: ARG001
        scenario = scenario_of(state)
        report = templated_report(scenario)
        requests = (
            await calls.advocate(scenario, report, policy, stance) if policy.uses_advocate else ()
        )
        rulings = await calls.referee(report, requests) if policy.uses_referee else ()
        edited = redact(policy, report, scenario, requests, rulings)

        secret_types = secrets_in_report(scenario, report)
        viewer_unedited, viewer_edited = await collect(
            calls.view(scenario, report), calls.view(scenario, edited)
        )
        prior, unedited, after_edit = await collect(
            calls.guess(scenario, secret_types, None),
            calls.guess(scenario, secret_types, report),
            calls.guess(scenario, secret_types, edited),
        )
        record = TrialRecord(
            policy=policy,
            report=report,
            edited=edited,
            requests=requests,
            rulings=rulings,
            viewer_unedited=viewer_unedited,
            viewer_edited=viewer_edited,
            guesses_prior=prior,
            guesses_unedited=unedited,
            guesses_edited=after_edit,
            integrity=await calls.judge(report, edited),
        )
        state.store.set(TRIAL_KEY, record.model_dump(mode="json"))
        state.output = ModelOutput.from_content(model="pipeline", content=report_view(edited))
        log.debug("trial_done", sample=scenario.scenario_id, policy=policy, requests=len(requests))
        return state

    return solve


@scorer(metrics={"*": [mean()]}, name=SCORER_NAME)
def redaction_scorer() -> Scorer:
    """Score a trial; the full `SampleResult` rides along in the score metadata."""

    async def score(state: TaskState, target: Target) -> Score:  # noqa: ARG001
        record = TrialRecord.model_validate(state.store.get(TRIAL_KEY))
        result = sample_result(scenario_of(state), record)
        return Score(
            value={
                "viewer_unedited": result.viewer_unedited,
                "viewer_edited": result.viewer_edited,
                "evidence_loss": result.evidence_loss,
                "redaction_volume": result.redaction_volume,
            },
            metadata={RESULT_KEY: result.model_dump(mode="json")},
        )

    return score


def result_from_metadata(metadata: dict[str, object]) -> SampleResult:
    """Rebuild a `SampleResult` from a score's metadata."""
    return SampleResult.model_validate(metadata[RESULT_KEY])


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
        [to_sample(s) for s in build_split(chosen_split, seed=seed)],
        name=f"redaction-escalation-{chosen_split}",
    )
    return Task(
        dataset=dataset,
        solver=redaction_trial(chosen_policy, chosen_stance),
        scorer=redaction_scorer(),
        name=f"redaction_escalation_{chosen_policy}",
        metadata={"split": chosen_split, "policy": chosen_policy, "stance": chosen_stance},
    )
