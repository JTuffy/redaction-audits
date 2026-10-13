"""One function per model role. Each builds its prompt, calls the role's model and parses.

Models are resolved by role (`get_model(role=...)`), so which model plays which part is set
when the eval starts, not here. Replies are cached, so conditions that repeat across policies
(the prior, the unedited report) are paid for once.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from inspect_ai.model import (
    CachePolicy,
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageUser,
    get_model,
)

from redaction_escalation.domain.models import (
    FindingIntegrity,
    RedactionRequest,
    Report,
    Ruling,
    Scenario,
    SecretGuess,
    SecretType,
)
from redaction_escalation.domain.policies import Policy
from redaction_escalation.infra.log_setup import get_logger
from redaction_escalation.infra.settings import MOCK_PROVIDER, Role, get_settings
from redaction_escalation.pipeline.parsing import ReplyFormatError, parse_reply
from redaction_escalation.pipeline.prompting import (
    Stance,
    advocate_prompt,
    guesser_prompt,
    judge_prompt,
    referee_prompt,
    retry_prompt,
    viewer_prompt,
)
from redaction_escalation.pipeline.schemas import (
    AdvocateReply,
    GuesserReply,
    JudgeReply,
    RefereeReply,
    Reply,
    ViewerReply,
)

log = get_logger(__name__)

# Never expire, so R2 can reuse R1's reports a week later; separate per epoch (seed).
_CACHE = CachePolicy(expiry=None, per_epoch=True)


async def ask[T: Reply](
    role: Role,
    prompt: str,
    schema: type[T],
    check: Callable[[T], None] | None = None,
) -> T:
    """Ask a role's model and parse the reply, re-asking with the error if it is unreadable.

    `check` adds validation the schema cannot express; it raises `ReplyFormatError`.
    """
    settings = get_settings()
    model = get_model(role=role.value)
    use_cache = settings.cache_replies and not str(model).startswith(MOCK_PROVIDER)
    cache: CachePolicy | bool = _CACHE if use_cache else False
    messages: list[ChatMessage] = [ChatMessageUser(content=prompt)]
    attempts = settings.parse_attempts
    for attempt in range(1, attempts + 1):
        output = await model.generate(messages, cache=cache)
        try:
            reply = parse_reply(output.completion, schema)
            if check is not None:
                check(reply)
        except ReplyFormatError as error:
            log.warning("unreadable_reply", role=role, attempt=attempt, error=str(error)[:500])
            messages += [
                ChatMessageAssistant(content=output.completion),
                ChatMessageUser(content=retry_prompt(str(error))),
            ]
        else:
            return reply
    msg = f"{role} gave no readable reply after {attempts} attempts"
    raise ReplyFormatError(msg)


async def advocate(
    scenario: Scenario, report: Report, policy: Policy, stance: Stance
) -> tuple[RedactionRequest, ...]:
    """The lab advocate's redaction requests."""
    prompt = advocate_prompt(scenario, report, policy, stance)
    return (await ask(Role.ADVOCATE, prompt, AdvocateReply)).requests


async def referee(report: Report, requests: Sequence[RedactionRequest]) -> tuple[Ruling, ...]:
    """The referee's rulings. Requests left without a ruling are treated as denied."""
    if not requests:
        return ()
    return (await ask(Role.REFEREE, referee_prompt(report, requests), RefereeReply)).rulings


async def view(scenario: Scenario, report: Report) -> int:
    """The viewer's 0-100 suspicion score from the evidence alone."""
    return (await ask(Role.VIEWER, viewer_prompt(scenario, report), ViewerReply)).score


async def guess(
    scenario: Scenario, secret_types: Sequence[SecretType], report: Report | None
) -> tuple[SecretGuess, ...]:
    """The guesser's distributions over each secret's options; `report=None` is the prior."""
    if not secret_types:
        return ()

    def covers_every_secret(reply: GuesserReply) -> None:
        missing = set(secret_types) - {g.secret_type for g in reply.guesses}
        if missing:
            msg = f"missing guesses for: {', '.join(sorted(missing))}"
            raise ReplyFormatError(msg)

    prompt = guesser_prompt(scenario, secret_types, report)
    return (await ask(Role.GUESSER, prompt, GuesserReply, covers_every_secret)).guesses


async def judge(original: Report, edited: Report) -> FindingIntegrity:
    """Whether editing changed the finding. An untouched finding is kept without a call."""
    if original.finding == edited.finding:
        return FindingIntegrity.KEPT
    return (await ask(Role.JUDGE, judge_prompt(original, edited), JudgeReply)).integrity
