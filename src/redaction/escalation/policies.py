"""Redaction policies and the deterministic parts of applying them.

The policy is the independent variable of the experiment. Text redaction is fully mechanical.
Contextual rewrite and self-redaction need an advocate (and, for contextual rewrite, an honest
executor) to produce requests and rulings; this module applies those decisions to a report and
enforces the rules that hold under every policy.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from enum import StrEnum

from redaction.core.models import (
    PlantedSecret,
    RedactionAction,
    RedactionRequest,
    Report,
    Ruling,
    RulingDecision,
    Scenario,
    SecretTier,
    SecretType,
)
from redaction.core.registry import redaction_marker, spec_for
from redaction.escalation.pseudonyms import stand_ins

LOG_ID_PATTERN = re.compile(r"LOG-\d{4}")
ALWAYS_REDACT_ONLY = frozenset({SecretTier.ALWAYS_REDACT})


class Policy(StrEnum):
    """The redaction regimes compared in the experiment."""

    TEXT_REDACTION = "text_redaction"
    TEXT_PSEUDONYM = "text_pseudonym"  # like text redaction, but consistent pseudonyms
    TEXT_GENERALIZE = "text_generalize"  # pseudonyms, and numbers and dates kept as comparisons
    CONTEXTUAL_REWRITE = "contextual_rewrite"
    SELF_REDACTION = "self_redaction"

    @property
    def uses_advocate(self) -> bool:
        """Whether this policy acts on advocate requests."""
        return self not in {Policy.TEXT_REDACTION, Policy.TEXT_PSEUDONYM, Policy.TEXT_GENERALIZE}

    @property
    def uses_executor(self) -> bool:
        """Whether an honest executor rules on the requests."""
        return self is Policy.CONTEXTUAL_REWRITE


def _replace_case_insensitive(text: str, needle: str, replacement: str) -> str:
    return re.sub(re.escape(needle), lambda _: replacement, text, flags=re.IGNORECASE)


def apply_text_redaction(
    report: Report, scenario: Scenario, tiers: frozenset[SecretTier] | None = None
) -> Report:
    """Remove planted secret values wherever they appear in the report.

    With `tiers`, only secrets of those tiers are removed; by default every tier is.
    Longer values are replaced first so a value that contains another is not split.
    """
    chosen = [
        s for s in scenario.redactable() if tiers is None or spec_for(s.secret_type).tier in tiers
    ]
    secrets = sorted(chosen, key=lambda s: len(s.value), reverse=True)

    def transform(text: str) -> str:
        for secret in secrets:
            text = _replace_case_insensitive(
                text, secret.value, redaction_marker(secret.secret_type)
            )
        return text

    return report.with_text(transform)


def apply_pseudonyms(report: Report, scenario: Scenario) -> Report:
    """Replace every confidential value with a consistent pseudonym (Customer A, Customer B)."""
    replacements = stand_ins(scenario, consistent=True)
    values = sorted(replacements, key=len, reverse=True)

    def transform(text: str) -> str:
        for value in values:
            text = _replace_case_insensitive(text, value, replacements[value])
        return text

    return report.with_text(transform)


_FOOTPRINT = re.compile(r"([\d,]+) GPUs for (\d+) days")
_THRESHOLD = re.compile(r"above ([\d,]+) GPU-hours")
_RELEASE = re.compile(r"week of (\d{4}-\d{2}-\d{2})")
_EVAL_DUE = re.compile(r"scheduled to finish (\d{4}-\d{2}-\d{2})")


def _relative(secret: PlantedSecret, text: str) -> str | None:
    """A generalization that keeps the comparison a finding turns on, when the text states one.

    This is an oracle version of executor rule 3 (keep the property that makes a span evidence):
    it knows which number the claim compares the value with, because the report quotes it.
    """
    if secret.secret_type is SecretType.COMPUTE_FOOTPRINT:
        fp, threshold = _FOOTPRINT.fullmatch(secret.value), _THRESHOLD.search(text)
        if fp and threshold:
            hours = int(fp.group(1).replace(",", "")) * int(fp.group(2)) * 24
            limit = int(threshold.group(1).replace(",", ""))
            side = "above" if hours > limit else "below"
            return f"an allocation {side} the {threshold.group(1)} GPU-hour reporting threshold"
    if secret.secret_type is SecretType.RELEASE_DATE:
        week, due = _RELEASE.fullmatch(secret.value), _EVAL_DUE.search(text)
        if week and due:
            side = "before" if week.group(1) < due.group(1) else "after"
            return f"a date {side} the eval's scheduled finish"
    return None


def apply_generalization(report: Report, scenario: Scenario) -> Report:
    """Pseudonyms for confidential values; compared numbers and dates become the comparison.

    A footprint or release date that a quoted threshold or deadline is compared with is replaced
    by that comparison ("an allocation above the ... threshold"); everything else gets a
    consistent pseudonym.
    """
    text = "\n".join(q.quote for q in report.evidence)
    replacements = stand_ins(scenario, consistent=True)
    for secret in scenario.redactable():
        relative = _relative(secret, text)
        if relative is not None:
            replacements[secret.value] = relative
    values = sorted(replacements, key=len, reverse=True)

    def transform(t: str) -> str:
        for value in values:
            t = _replace_case_insensitive(t, value, replacements[value])
        return t

    return report.with_text(transform)


def is_protected_span(span: str) -> bool:
    """Spans that contain a log ID are never changed under any policy."""
    return LOG_ID_PATTERN.search(span) is not None


def grant_all(requests: Sequence[RedactionRequest]) -> tuple[Ruling, ...]:
    """Rulings for self-redaction: every request is granted as asked."""
    return tuple(
        Ruling(request_index=index, decision=RulingDecision.GRANT, reason="self-redaction")
        for index in range(len(requests))
    )


def _replacement_for(request: RedactionRequest, ruling: Ruling) -> str | None:
    """The text a granted or modified ruling puts in place of the span, if any."""
    if ruling.decision is RulingDecision.DENY:
        return None
    if ruling.decision is RulingDecision.MODIFY and ruling.replacement:
        return ruling.replacement
    if request.action is RedactionAction.GENERALIZE and request.proposed_replacement:
        return request.proposed_replacement
    return f"[REDACTED: {request.category}]"


def apply_rulings(
    report: Report,
    requests: Sequence[RedactionRequest],
    rulings: Iterable[Ruling],
) -> Report:
    """Apply honest executor (or self-redaction) rulings to a report.

    Protected spans are skipped whatever the ruling says, rulings that point at a missing
    request are ignored, and later requests never re-edit text an earlier one already replaced.
    """
    edits: list[tuple[str, str]] = []
    for ruling in rulings:
        if not 0 <= ruling.request_index < len(requests):
            continue
        request = requests[ruling.request_index]
        replacement = _replacement_for(request, ruling)
        if replacement is None or is_protected_span(request.span):
            continue
        edits.append((request.span, replacement))

    edits.sort(key=lambda edit: len(edit[0]), reverse=True)

    def transform(text: str) -> str:
        for span, replacement in edits:
            text = text.replace(span, replacement)
        return text

    return report.with_text(transform)


def redact(
    policy: Policy,
    report: Report,
    scenario: Scenario,
    requests: Sequence[RedactionRequest] = (),
    rulings: Iterable[Ruling] = (),
) -> Report:
    """Produce the edited report for a policy.

    Under contextual rewrite, always-redact values are removed after the honest executor's
    rulings, so no ruling can bring one back; context-tier values are left to the executor.
    """
    if policy is Policy.TEXT_REDACTION:
        return apply_text_redaction(report, scenario)
    if policy is Policy.TEXT_PSEUDONYM:
        return apply_pseudonyms(report, scenario)
    if policy is Policy.TEXT_GENERALIZE:
        return apply_generalization(report, scenario)
    edited = apply_rulings(report, requests, effective_rulings(policy, requests, rulings))
    if policy is Policy.SELF_REDACTION:
        return edited
    return apply_text_redaction(edited, scenario, ALWAYS_REDACT_ONLY)


def effective_rulings(
    policy: Policy, requests: Sequence[RedactionRequest], rulings: Iterable[Ruling]
) -> tuple[Ruling, ...]:
    """The rulings a policy actually applies: none, all granted, or the honest executor's."""
    if not policy.uses_advocate:
        return ()
    if policy is Policy.SELF_REDACTION:
        return grant_all(requests)
    return tuple(rulings)


def granted_count(
    policy: Policy, requests: Sequence[RedactionRequest], rulings: Iterable[Ruling]
) -> int:
    """How many requests a policy granted or modified (denials and stray rulings excluded)."""
    return sum(
        1
        for ruling in effective_rulings(policy, requests, rulings)
        if ruling.decision is not RulingDecision.DENY and 0 <= ruling.request_index < len(requests)
    )
