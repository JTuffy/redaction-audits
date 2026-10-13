"""Pure pieces of the pipeline: reply parsing and prompt building."""

from __future__ import annotations

import pytest

from redaction_escalation.domain.models import Report, Scenario
from redaction_escalation.domain.policies import Policy
from redaction_escalation.domain.roles import Stance
from redaction_escalation.domain.scoring import secrets_in_report
from redaction_escalation.pipeline.parsing import (
    ReplyFormatError,
    extract_json_object,
    parse_reply,
)
from redaction_escalation.pipeline.prompting import (
    advocate_prompt,
    guesser_prompt,
    judge_prompt,
    referee_prompt,
    viewer_prompt,
)
from redaction_escalation.pipeline.schemas import AdvocateReply, ViewerReply


class TestParsing:
    def test_fenced_json_with_prose(self) -> None:
        text = 'Sure.\n```json\n{"score": 70, "rationale": "x"}\n```\nDone.'
        assert parse_reply(text, ViewerReply).score == 70

    def test_bare_json_with_prose(self) -> None:
        assert extract_json_object('Here: {"a": 1} ok') == '{"a": 1}'

    def test_no_json(self) -> None:
        with pytest.raises(ReplyFormatError, match="no JSON"):
            parse_reply("I cannot help with that.", ViewerReply)

    def test_out_of_range_score(self) -> None:
        with pytest.raises(ReplyFormatError):
            parse_reply('{"score": 140}', ViewerReply)

    def test_lenient_wire_types(self) -> None:
        reply = parse_reply(
            '{"requests": [{"span": "Muon", "action": "redact", "category": "optimizer",'
            ' "rule": 5, "reason": "r", "proposed_replacement": null, "confidence": "high"}]}',
            AdvocateReply,
        )
        assert reply.requests[0].rule == "5"


class TestPrompts:
    def test_no_unfilled_placeholders(self, violation: Scenario, violation_report: Report) -> None:
        secret_types = secrets_in_report(violation, violation_report)
        prompts = [
            advocate_prompt(violation, violation_report, policy, stance)
            for policy in (Policy.CONTEXTUAL_REWRITE, Policy.SELF_REDACTION)
            for stance in Stance
        ]
        prompts += [
            referee_prompt(violation_report, []),
            viewer_prompt(violation, violation_report),
            guesser_prompt(violation, secret_types, None),
            guesser_prompt(violation, secret_types, violation_report),
            judge_prompt(violation_report, violation_report),
        ]
        for prompt in prompts:
            assert "$" not in prompt

    def test_viewer_sees_evidence_only(self, violation: Scenario, violation_report: Report) -> None:
        prompt = viewer_prompt(violation, violation_report)
        assert violation_report.finding not in prompt
        assert violation_report.reasoning not in prompt

    def test_prior_guess_has_no_secret_values(
        self, violation: Scenario, violation_report: Report
    ) -> None:
        prompt = guesser_prompt(violation, secrets_in_report(violation, violation_report), None)
        context = prompt.split("For each item")[0]
        assert all(secret.value not in context for secret in violation.secrets)
