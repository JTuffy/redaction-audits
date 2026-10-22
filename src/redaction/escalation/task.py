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

from redaction.core.models import Scenario, Split
from redaction.core.roles import Stance
from redaction.data.frozen import latest_version, load_built
from redaction.data.generator import build_split
from redaction.escalation.policies import Policy
from redaction.escalation.scoring import SampleResult, TrialRecord, sample_result
from redaction.escalation.trial import run_trial
from redaction.escalation.views import logs_view, report_view
from redaction.infra.log_setup import get_logger
from redaction.infra.settings import get_settings

log = get_logger(__name__)

SCORER_NAME: Final = "redaction_scorer"
_TRIAL_KEY: Final = "trial"
_RESULT_KEY: Final = "result"
_SCENARIO_KEY: Final = "scenario"


def scenarios_for(split: Split, seed: int | None = None) -> tuple[Scenario, ...]:
    """The split's latest frozen build; the v1 generator when there is none or a seed is given."""
    settings = get_settings()
    built = (
        None if seed is not None else load_built(split, settings.built_dir, settings.build_version)
    )
    if built is not None:
        return built
    log.warning("using_v1_generator", split=split, reason="seed given" if seed else "no build")
    return tuple(build_split(split, seed=seed))


def data_source(split: Split, seed: int | None = None) -> str:
    """What a run's scenarios came from, for the run ledger: `built:<version>` or `generator:v1`."""
    settings = get_settings()
    pinned = settings.build_version
    if seed is None and pinned and (settings.built_dir / split.value / pinned).is_dir():
        return f"built:{pinned}"
    version = None if seed is not None else latest_version(split, settings.built_dir)
    return f"built:{version}" if version else "generator:v1"


def to_sample(scenario: Scenario) -> Sample:
    """An Inspect sample carrying the whole scenario in its metadata."""
    return Sample(
        id=scenario.scenario_id,
        input=logs_view(scenario),
        target=scenario.label.value,
        metadata={_SCENARIO_KEY: scenario.model_dump(mode="json")},
    )


def scenario_of(state: TaskState) -> Scenario:
    """The scenario a sample carries in its metadata."""
    return Scenario.model_validate(state.metadata[_SCENARIO_KEY])


@solver
def redaction_trial(policy: Policy, stance: Stance) -> Solver:
    """Run one trial of a policy on a scenario and store the raw outputs."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:  # noqa: ARG001
        record = await run_trial(scenario_of(state), policy, stance)
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
        result = sample_result(scenario_of(state), record)
        return Score(
            value={
                "judge_unedited": result.judge_unedited,
                "judge_edited": result.judge_edited,
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
def redaction(
    split: str = Split.DEV.value,
    policy: str = Policy.CONTEXTUAL_REWRITE.value,
    stance: str = Stance.HONEST.value,
    seed: int | None = None,
) -> Task:
    """Redaction Under Escalation for one policy on one split."""
    chosen_split, chosen_policy, chosen_stance = Split(split), Policy(policy), Stance(stance)
    dataset = MemoryDataset(
        [to_sample(s) for s in scenarios_for(chosen_split, seed)],
        name=f"redaction-escalation-{chosen_split}",
    )
    return Task(
        dataset=dataset,
        solver=redaction_trial(chosen_policy, chosen_stance),
        scorer=redaction_scorer(),
        name=f"redaction_{chosen_policy}",
        metadata={"split": chosen_split, "policy": chosen_policy, "stance": chosen_stance},
    )
