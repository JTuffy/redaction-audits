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
    GenerateConfig,
    get_model,
)
from inspect_ai.util import collect

from redaction.core.models import (
    FindingIntegrity,
    RedactionRequest,
    Report,
    Ruling,
    Scenario,
    SecretGuess,
    SecretType,
)
from redaction.core.parsing import ReplyFormatError, parse_reply
from redaction.core.roles import Role, Stance
from redaction.escalation.adversary import scripted_requests
from redaction.escalation.mock import is_mock
from redaction.escalation.policies import Policy
from redaction.escalation.prompting import (
    advocate_prompt,
    executor_prompt,
    integrity_prompt,
    retry_prompt,
    secrets_prompt,
    violation_prompt,
)
from redaction.escalation.schemas import (
    AdvocateReply,
    ExecutorReply,
    IntegrityReply,
    Reply,
    SecretsReply,
    ViolationReply,
)
from redaction.infra.log_setup import get_logger
from redaction.infra.settings import get_settings

log = get_logger(__name__)

# Never expire, so R2 can reuse R1's reports a week later; separate per epoch (seed).
_CACHE = CachePolicy(expiry=None, per_epoch=True)


async def ask[T: Reply](
    role: Role,
    prompt: str,
    schema: type[T],
    check: Callable[[T], None] | None = None,
    sample: int = 0,
) -> T:
    """Ask a role's model and parse the reply, re-asking with the error if it is unreadable.

    `check` adds validation the schema cannot express; it raises `ReplyFormatError`. `sample`
    numbers repeated asks of the same prompt: each gets its own cache entry, so averaging k
    samples costs k replies once and nothing on reruns.
    """
    settings = get_settings()
    model = get_model(role=role.value)
    policy = (
        _CACHE
        if sample == 0
        else CachePolicy(expiry=None, per_epoch=True, scopes={"sample": str(sample)})
    )
    cache: CachePolicy | bool = policy if settings.cache_replies and not is_mock(model) else False
    config = GenerateConfig(reasoning_effort=settings.reasoning_for(role))
    messages: list[ChatMessage] = [ChatMessageUser(content=prompt)]
    attempts = settings.parse_attempts
    for attempt in range(1, attempts + 1):
        output = await model.generate(messages, config=config, cache=cache)
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
    """The lab advocate's redaction requests; a scripted stance needs no model."""
    if stance.scripted:
        return scripted_requests(scenario, report, stance)
    prompt = advocate_prompt(scenario, report, policy, stance)
    return (await ask(Role.ADVOCATE, prompt, AdvocateReply)).requests


async def executor(report: Report, requests: Sequence[RedactionRequest]) -> tuple[Ruling, ...]:
    """The honest executor's rulings. Requests left without a ruling are treated as denied."""
    if not requests:
        return ()
    return (await ask(Role.EXECUTOR, executor_prompt(report, requests), ExecutorReply)).rulings


async def judge_violation_samples(scenario: Scenario, report: Report) -> tuple[int, ...]:
    """The "human" judge's 0-100 suspicion scores, one per judge sample, from the evidence alone."""
    prompt = violation_prompt(scenario, report)
    replies = await collect(
        *(ask(Role.JUDGE, prompt, ViolationReply, sample=i) for i in range(_judge_samples()))
    )
    return tuple(r.score for r in replies)


async def judge_violation(scenario: Scenario, report: Report) -> float:
    """The mean of the judge's suspicion samples."""
    scores = await judge_violation_samples(scenario, report)
    return sum(scores) / len(scores)


def _judge_samples() -> int:
    return get_settings().judge_samples


def average_guesses(samples: Sequence[tuple[SecretGuess, ...]]) -> tuple[SecretGuess, ...]:
    """Average each secret's distribution over the judge samples (missing options count as 0)."""
    first = samples[0]
    out = []
    for guess in first:
        dists = [next((g for g in s if g.secret_type is guess.secret_type), None) for s in samples]
        options = {o for d in dists if d is not None for o in d.probabilities}
        out.append(
            SecretGuess(
                secret_type=guess.secret_type,
                probabilities={
                    o: sum(d.probability_of(o) if d is not None else 0.0 for d in dists)
                    / len(dists)
                    for o in sorted(options)
                },
            )
        )
    return tuple(out)


async def judge_secrets(
    scenario: Scenario, secret_types: Sequence[SecretType], report: Report | None
) -> tuple[SecretGuess, ...]:
    """The "human" judge's distributions over each secret's options; `report=None` is the prior."""
    if not secret_types:
        return ()

    def covers_every_secret(reply: SecretsReply) -> None:
        missing = set(secret_types) - {g.secret_type for g in reply.guesses}
        if missing:
            msg = f"missing guesses for: {', '.join(sorted(missing))}"
            raise ReplyFormatError(msg)

    prompt = secrets_prompt(scenario, secret_types, report)
    replies = await collect(
        *(
            ask(Role.JUDGE, prompt, SecretsReply, covers_every_secret, sample=i)
            for i in range(_judge_samples())
        )
    )
    return average_guesses([r.guesses for r in replies])


async def check_integrity(original: Report, edited: Report) -> FindingIntegrity:
    """Whether editing changed the finding. An untouched finding is kept without a call."""
    if original.finding == edited.finding:
        return FindingIntegrity.KEPT
    return (
        await ask(Role.INTEGRITY_CHECK, integrity_prompt(original, edited), IntegrityReply)
    ).integrity
