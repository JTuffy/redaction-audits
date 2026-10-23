"""Pure pieces of the pipeline: reply parsing and prompt building."""

from __future__ import annotations

import pytest

from redaction.core.models import Report, Scenario
from redaction.core.parsing import (
    ReplyFormatError,
    extract_json_object,
    parse_reply,
)
from redaction.core.roles import Stance
from redaction.escalation.policies import Policy
from redaction.escalation.prompting import (
    advocate_prompt,
    executor_prompt,
    integrity_prompt,
    secrets_prompt,
    violation_prompt,
)
from redaction.escalation.schemas import AdvocateReply, ViolationReply
from redaction.escalation.scoring import secrets_in_evidence


class TestParsing:
    def test_fenced_json_with_prose(self) -> None:
        text = 'Sure.\n```json\n{"score": 70, "rationale": "x"}\n```\nDone.'
        assert parse_reply(text, ViolationReply).score == 70

    def test_bare_json_with_prose(self) -> None:
        assert extract_json_object('Here: {"a": 1} ok') == '{"a": 1}'

    def test_no_json(self) -> None:
        with pytest.raises(ReplyFormatError, match="no JSON"):
            parse_reply("I cannot help with that.", ViolationReply)

    def test_out_of_range_score(self) -> None:
        with pytest.raises(ReplyFormatError):
            parse_reply('{"score": 140}', ViolationReply)

    def test_lenient_wire_types(self) -> None:
        reply = parse_reply(
            '{"requests": [{"span": "Muon", "action": "redact", "category": "optimizer",'
            ' "rule": 5, "reason": "r", "proposed_replacement": null, "confidence": "high"}]}',
            AdvocateReply,
        )
        assert reply.requests[0].rule == "5"


class TestPrompts:
    def test_no_unfilled_placeholders(self, violation: Scenario, violation_report: Report) -> None:
        secret_types = secrets_in_evidence(violation, violation_report)
        prompts = [
            advocate_prompt(violation, violation_report, policy, stance)
            for policy in (Policy.CONTEXTUAL_REWRITE, Policy.SELF_REDACTION)
            for stance in Stance
            if not stance.scripted
        ]
        prompts += [
            executor_prompt(violation_report, []),
            violation_prompt(violation, violation_report),
            secrets_prompt(violation, secret_types, None),
            secrets_prompt(violation, secret_types, violation_report),
            integrity_prompt(violation_report, violation_report),
        ]
        for prompt in prompts:
            assert "$" not in prompt

    def test_viewer_sees_evidence_only(self, violation: Scenario, violation_report: Report) -> None:
        prompt = violation_prompt(violation, violation_report)
        assert violation_report.finding not in prompt
        assert violation_report.reasoning not in prompt

    def test_prior_guess_has_no_secret_values(
        self, violation: Scenario, violation_report: Report
    ) -> None:
        prompt = secrets_prompt(violation, secrets_in_evidence(violation, violation_report), None)
        context = prompt.split("For each item")[0]
        assert all(secret.value not in context for secret in violation.secrets)
