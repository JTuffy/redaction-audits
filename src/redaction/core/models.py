"""Core value types for the Redaction Under Escalation experiment.

Everything here is immutable and free of I/O, so the same objects flow through the scenario
generator, the policies, the metrics and the Inspect pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Frozen(BaseModel):
    """Base for immutable, strictly validated value objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Label(StrEnum):
    """Ground-truth label of a scenario."""

    VIOLATION = "violation"
    RED_HERRING = "red_herring"
    CLEAN = "clean"


class Difficulty(StrEnum):
    """How hard a red herring is to tell apart from its violation."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ViolationType(StrEnum):
    """The audit claim a scenario is about."""

    COT_IN_TRAINING = "cot_in_training"
    CLASSIFIER_OFF = "classifier_off"
    OPTED_OUT_DATA = "opted_out_data"
    SKIPPED_EVAL = "skipped_eval"
    MONITORING_OFF = "monitoring_off"
    UNREPORTED_COMPUTE = "unreported_compute"


class Split(StrEnum):
    """Dataset split. Prompts are tuned on dev, confirmed on val, frozen for test."""

    DEV = "dev"
    VAL = "val"
    TEST = "test"


class SecretTier(StrEnum):
    """How the redaction policies treat a secret type."""

    ALWAYS_REDACT = "always_redact"
    CONTEXT = "context"


class Sensitivity(StrEnum):
    """How much a leak of this secret type matters; used to weight leakage."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SecretType(StrEnum):
    """The twelve secret types in the shared registry."""

    LR_SCHEDULE = "lr_schedule"
    DATA_MIX = "data_mix"
    CUSTOMER_NAME = "customer_name"
    EMPLOYEE_NAME = "employee_name"
    OPTIMIZER = "optimizer"
    PARAMETER_SCALE = "parameter_scale"
    ARCHITECTURE = "architecture"
    DATA_VENDOR = "data_vendor"
    CODENAME = "codename"
    DELIBERATION = "deliberation"
    COMPUTE_FOOTPRINT = "compute_footprint"
    RELEASE_DATE = "release_date"


Grade = Annotated[int, Field(ge=0, le=100)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
type TextTransform = Callable[[str], str]


class PlantedSecret(Frozen):
    """A secret placed in a scenario's logs; `value` is the true registry option."""

    secret_type: SecretType
    value: str = Field(min_length=1)


class LogEntry(Frozen):
    """One line of a lab's log bundle."""

    log_id: str = Field(pattern=r"^LOG-\d{4}$")
    timestamp: str
    source: str
    text: str


class CorrelateStrength(StrEnum):
    """How much a correlate gives away on its own."""

    IDENTIFYING = "identifying"  # an informed reader can recover the exact option
    NARROWING = "narrowing"  # rules out some options, or needs another detail to finish


class Correlate(Frozen):
    """A detail in the logs that reveals a secret without stating its value.

    `snippet` is the exact text in the log line that carries the signal, so validators and
    viewers can find it. Correlates are what text redaction of the literal value misses.
    """

    secret_type: SecretType
    log_id: str = Field(pattern=r"^LOG-\d{4}$")
    snippet: str = Field(min_length=1)
    strength: CorrelateStrength
    rationale: str = Field(min_length=1)


class Scenario(Frozen):
    """A fictional lab's log bundle for one audit claim, with its ground truth."""

    scenario_id: str
    split: Split
    violation_type: ViolationType
    claim: str = Field(min_length=1)
    label: Label
    difficulty: Difficulty | None = None
    lab_name: str
    logs: tuple[LogEntry, ...]
    secrets: tuple[PlantedSecret, ...]
    key_evidence_ids: tuple[str, ...]
    separating_cues: tuple[str, ...]
    secret_cues: tuple[SecretType, ...] = ()
    correlates: tuple[Correlate, ...] = ()

    @model_validator(mode="after")
    def _check_consistency(self) -> Scenario:
        if (self.label is Label.RED_HERRING) != (self.difficulty is not None):
            msg = "difficulty is set exactly when the label is red_herring"
            raise ValueError(msg)
        log_ids = {entry.log_id for entry in self.logs}
        missing = set(self.key_evidence_ids) - log_ids
        if missing:
            msg = f"key evidence ids not in logs: {sorted(missing)}"
            raise ValueError(msg)
        corpus = "\n".join(entry.text for entry in self.logs)
        absent = [s.secret_type for s in self.secrets if s.value not in corpus]
        if absent:
            msg = f"planted secrets missing from logs: {absent}"
            raise ValueError(msg)
        texts = {entry.log_id: entry.text for entry in self.logs}
        misplaced = [c.log_id for c in self.correlates if c.snippet not in texts.get(c.log_id, "")]
        if misplaced:
            msg = f"correlate snippets not found in their log lines: {misplaced}"
            raise ValueError(msg)
        return self

    def secret(self, secret_type: SecretType) -> PlantedSecret | None:
        """Return the planted secret of a type, if the scenario has one."""
        return next((s for s in self.secrets if s.secret_type is secret_type), None)


class EvidenceQuote(Frozen):
    """A log line quoted in a report, tied to its log ID."""

    log_id: str
    quote: str


class Report(Frozen):
    """An audit report. The grade is never shown to readers and never redacted."""

    finding: str
    evidence: tuple[EvidenceQuote, ...]
    reasoning: str
    grade: Grade

    def with_text(self, transform: TextTransform) -> Report:
        """Return a copy with `transform` applied to every redactable text field."""
        return Report(
            finding=transform(self.finding),
            evidence=tuple(
                EvidenceQuote(log_id=q.log_id, quote=transform(q.quote)) for q in self.evidence
            ),
            reasoning=transform(self.reasoning),
            grade=self.grade,
        )

    def evidence_text(self) -> str:
        """The quoted evidence alone, which is all the "human" judge sees."""
        return "\n".join(q.quote for q in self.evidence)

    def redactable_text(self) -> str:
        """All text a redaction can touch, in a stable order."""
        quotes = "\n".join(q.quote for q in self.evidence)
        return f"{self.finding}\n{quotes}\n{self.reasoning}"


class RedactionAction(StrEnum):
    """What the advocate asks the honest executor to do with a span."""

    REDACT = "redact"
    GENERALIZE = "generalize"


class RedactionRequest(Frozen):
    """One redaction request from the lab advocate."""

    span: str = Field(min_length=1)
    action: RedactionAction
    category: str = Field(min_length=1)
    rule: str
    reason: str
    proposed_replacement: str | None = None


class RulingDecision(StrEnum):
    """The honest executor's decision on one request."""

    GRANT = "grant"
    MODIFY = "modify"
    DENY = "deny"


class Ruling(Frozen):
    """The honest executor's ruling on the request at `request_index`."""

    request_index: int = Field(ge=0)
    decision: RulingDecision
    replacement: str | None = None
    reason: str = ""


class SecretGuess(Frozen):
    """A reader's probability distribution over one secret's registry options."""

    secret_type: SecretType
    probabilities: dict[str, Probability]

    def probability_of(self, value: str) -> float:
        """Probability assigned to `value`, after normalizing the distribution."""
        total = sum(self.probabilities.values())
        if total <= 0:
            return 0.0
        return self.probabilities.get(value, 0.0) / total


class FindingIntegrity(StrEnum):
    """Whether redaction changed the meaning of the auditor's finding."""

    KEPT = "kept"
    SOFTENED = "softened"
    REVERSED = "reversed"
