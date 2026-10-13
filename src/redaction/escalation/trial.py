"""One trial: a scenario, a policy and a stance in; the raw outputs of every role out.

This is the experiment's procedure in one place, kept apart from Inspect's task plumbing in
`task.py`. The order follows the spec: report, advocate, honest executor, redaction, then the
"human" judge's two questions and the finding-integrity check. Calls that do not depend on each
other run concurrently.
"""

from __future__ import annotations

from inspect_ai.util import collect

from redaction.core.models import Report, Scenario
from redaction.core.roles import Stance
from redaction.data.reports import templated_report
from redaction.escalation import calls
from redaction.escalation.policies import Policy, redact
from redaction.escalation.scoring import TrialRecord, secrets_in_evidence
from redaction.infra.log_setup import get_logger

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
    rulings = await calls.executor(report, requests) if policy.uses_executor else ()
    edited = redact(policy, report, scenario, requests, rulings)

    secret_types = secrets_in_evidence(scenario, report)
    judge_unedited, judge_edited = await collect(
        calls.judge_violation(scenario, report), calls.judge_violation(scenario, edited)
    )
    prior, unedited, after_edit = await collect(
        calls.judge_secrets(scenario, secret_types, None),
        calls.judge_secrets(scenario, secret_types, report),
        calls.judge_secrets(scenario, secret_types, edited),
    )
    integrity = await calls.check_integrity(report, edited)
    log.debug("trial_done", sample=scenario.scenario_id, policy=policy, requests=len(requests))
    return TrialRecord(
        policy=policy,
        report=report,
        edited=edited,
        requests=requests,
        rulings=rulings,
        judge_unedited=judge_unedited,
        judge_edited=judge_edited,
        guesses_prior=prior,
        guesses_unedited=unedited,
        guesses_edited=after_edit,
        integrity=integrity,
    )
