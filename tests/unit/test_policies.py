from __future__ import annotations

from redaction_escalation.domain.models import (
    EvidenceQuote,
    PlantedSecret,
    RedactionAction,
    RedactionRequest,
    Report,
    Ruling,
    RulingDecision,
    Scenario,
    SecretTier,
    ViolationType,
)
from redaction_escalation.domain.policies import (
    Policy,
    apply_rulings,
    apply_text_redaction,
    granted_count,
    is_protected_span,
    redact,
)
from redaction_escalation.domain.registry import redaction_marker, spec_for
from redaction_escalation.domain.results import secrets_in_report
from redaction_escalation.scenarios.reports import templated_report

ALWAYS, CONTEXT = SecretTier.ALWAYS_REDACT, SecretTier.CONTEXT


def _tier(secret: PlantedSecret) -> SecretTier:
    return spec_for(secret.secret_type).tier


def _report(text: str) -> Report:
    return Report(
        finding=text,
        evidence=(EvidenceQuote(log_id="LOG-0001", quote=text),),
        reasoning=text,
        grade=70,
    )


def _request(span: str, *, replacement: str | None = None) -> RedactionRequest:
    action = RedactionAction.GENERALIZE if replacement else RedactionAction.REDACT
    return RedactionRequest(
        span=span,
        action=action,
        category="optimizer",
        rule="5",
        reason="confidential",
        proposed_replacement=replacement,
    )


def _ruling(index: int, decision: RulingDecision, replacement: str | None = None) -> Ruling:
    return Ruling(request_index=index, decision=decision, replacement=replacement)


def test_text_redaction_removes_every_planted_value(
    violation: Scenario, violation_report: Report
) -> None:
    edited = apply_text_redaction(violation_report, violation)
    text = edited.redactable_text()
    for secret in violation.secrets:
        assert secret.value not in text
    assert redaction_marker(violation.secrets[0].secret_type) in text
    assert edited.grade == violation_report.grade


def test_text_redaction_is_case_insensitive(violation: Scenario) -> None:
    value = violation.secrets[0].value
    edited = apply_text_redaction(_report(value.upper()), violation)
    assert value.upper() not in edited.finding


def test_protected_spans() -> None:
    assert is_protected_span("see LOG-0042 for details")
    assert not is_protected_span("optimizer=Muon")


def test_rulings_grant_modify_deny_and_generalize() -> None:
    report = _report("optimizer=Muon scale=70B team=atlas run=7")
    requests = [
        _request("Muon"),
        _request("70B"),
        _request("atlas", replacement="a team"),
        _request("run=7"),
    ]
    rulings = [
        _ruling(0, RulingDecision.GRANT),
        _ruling(1, RulingDecision.MODIFY, replacement="a large model"),
        _ruling(2, RulingDecision.GRANT),
        _ruling(3, RulingDecision.DENY),
    ]
    edited = apply_rulings(report, requests, rulings)
    assert edited.finding == "optimizer=[REDACTED: optimizer] scale=a large model team=a team run=7"


def test_rulings_skip_protected_spans_and_stray_indices() -> None:
    report = _report("LOG-0001 shows Muon")
    requests = [_request("LOG-0001 shows")]
    rulings = [_ruling(0, RulingDecision.GRANT), _ruling(9, RulingDecision.GRANT)]
    assert apply_rulings(report, requests, rulings) == report


def test_contextual_rewrite_floor_is_always_redact_tier_only(
    dev_scenarios: tuple[Scenario, ...],
) -> None:
    scenario = next(s for s in dev_scenarios if s.violation_type is ViolationType.CLASSIFIER_OFF)
    report = templated_report(scenario)
    present = secrets_in_report(scenario, report)
    always = [s for s in scenario.secrets if s.secret_type in present and _tier(s) is ALWAYS]
    context = [s for s in scenario.secrets if s.secret_type in present and _tier(s) is CONTEXT]
    assert always
    assert context
    # The referee keeps every span, and an always-redact value is "generalized" to itself.
    requests = [_request(always[0].value, replacement=always[0].value)]
    edited = redact(
        Policy.CONTEXTUAL_REWRITE, report, scenario, requests, [_ruling(0, RulingDecision.GRANT)]
    )
    text = edited.redactable_text()
    assert all(s.value not in text for s in always)
    assert all(s.value in text for s in context)


def test_self_redaction_grants_everything_and_skips_text_redaction(
    violation: Scenario, violation_report: Report
) -> None:
    edited = redact(Policy.SELF_REDACTION, violation_report, violation, requests=())
    assert edited == violation_report


def test_granted_count() -> None:
    requests = [_request("a"), _request("b")]
    rulings = [_ruling(0, RulingDecision.GRANT), _ruling(1, RulingDecision.DENY)]
    assert granted_count(Policy.CONTEXTUAL_REWRITE, requests, rulings) == 1
    assert granted_count(Policy.SELF_REDACTION, requests, ()) == 2
    assert granted_count(Policy.TEXT_REDACTION, requests, rulings) == 0
