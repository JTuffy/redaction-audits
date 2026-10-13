"""Building each role's prompt from domain objects. Pure: no model calls, no Inspect."""

from __future__ import annotations

import json
from collections.abc import Sequence
from types import MappingProxyType
from typing import Final

from redaction_escalation.domain.models import RedactionRequest, Report, Scenario, SecretType
from redaction_escalation.domain.policies import Policy
from redaction_escalation.domain.registry import REGISTRY, spec_for
from redaction_escalation.domain.roles import Stance
from redaction_escalation.domain.views import evidence_view, report_view
from redaction_escalation.prompts import PromptName, render

_STANCE_PROMPTS: Final = MappingProxyType(
    {
        Stance.HONEST: PromptName.STANCE_HONEST,
        Stance.COVER_UP: PromptName.STANCE_COVER_UP,
    }
)


def _rules() -> str:
    return render(PromptName.RULES)


def advocate_prompt(scenario: Scenario, report: Report, policy: Policy, stance: Stance) -> str:
    """The lab advocate's prompt. The process paragraph depends on whether an executor rules."""
    process = (
        render(PromptName.PROCESS_EXECUTOR, rules=_rules())
        if policy.uses_executor
        else render(PromptName.PROCESS_SELF)
    )
    return render(
        PromptName.ADVOCATE,
        lab_name=scenario.lab_name,
        categories=", ".join(spec.label for spec in REGISTRY.values()),
        secrets="\n".join(
            f"- {spec_for(s.secret_type).label}: {s.value}" for s in scenario.secrets
        ),
        process=process,
        stance=render(_STANCE_PROMPTS[stance]),
        report=report_view(report),
    )


def executor_prompt(report: Report, requests: Sequence[RedactionRequest]) -> str:
    """The honest executor's prompt, with requests numbered by their index."""
    numbered = "\n".join(
        f"{index}: {json.dumps(request.model_dump(mode='json'))}"
        for index, request in enumerate(requests)
    )
    return render(
        PromptName.EXECUTOR, rules=_rules(), report=report_view(report), requests=numbered
    )


def violation_prompt(scenario: Scenario, report: Report) -> str:
    """The "human" judge's violation prompt: the claim and the evidence quotes, nothing else."""
    return render(PromptName.JUDGE_VIOLATION, claim=scenario.claim, evidence=evidence_view(report))


def secrets_prompt(
    scenario: Scenario, secret_types: Sequence[SecretType], report: Report | None
) -> str:
    """The "human" judge's secrets prompt, on the same evidence it judges; `None` is the prior."""
    context = (
        render(PromptName.CONTEXT_PRIOR, claim=scenario.claim)
        if report is None
        else render(PromptName.CONTEXT_EVIDENCE, evidence=evidence_view(report))
    )
    items = "\n".join(
        f"- {secret_type.value} ({spec_for(secret_type).label}): "
        + " | ".join(spec_for(secret_type).options)
        for secret_type in secret_types
    )
    return render(
        PromptName.JUDGE_SECRETS, lab_name=scenario.lab_name, context=context, items=items
    )


def integrity_prompt(original: Report, edited: Report) -> str:
    """The finding-integrity check's prompt."""
    return render(PromptName.INTEGRITY_CHECK, original=original.finding, edited=edited.finding)


def retry_prompt(error: str) -> str:
    """Follow-up asking a model to fix an unreadable reply."""
    return render(PromptName.RETRY, error=error)
