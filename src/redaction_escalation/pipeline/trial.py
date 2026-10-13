"""One trial: a scenario, a policy and a stance in; the raw outputs of every role out.

This is the experiment's procedure in one place, kept apart from Inspect's task plumbing in
`task.py`. The order follows the spec: report, advocate, referee, redaction, viewer, guesser,
judge. Calls that do not depend on each other run concurrently.
"""

from __future__ import annotations

from inspect_ai.util import collect

from redaction_escalation.domain.models import Report, Scenario
from redaction_escalation.domain.policies import Policy, redact
from redaction_escalation.domain.roles import Stance
from redaction_escalation.domain.scoring import TrialRecord, secrets_in_report
from redaction_escalation.infra.log_setup import get_logger
from redaction_escalation.pipeline import calls
from redaction_escalation.scenarios.reports import templated_report

log = get_logger(__name__)


def audit_report(scenario: Scenario) -> Report:
    """The auditor's report. Templated in the MVP; the model auditor replaces this."""
    return templated_report(scenario)


async def run_trial(scenario: Scenario, policy: Policy, stance: Stance) -> TrialRecord:
    """Run every role once for a scenario under a policy and collect what they produced."""
    report = audit_report(scenario)
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
    integrity = await calls.judge(report, edited)
    log.debug("trial_done", sample=scenario.scenario_id, policy=policy, requests=len(requests))
    return TrialRecord(
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
        integrity=integrity,
    )
