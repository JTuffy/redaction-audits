"""Who takes part in a trial, and what the lab wants from its advocate."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """The model roles in a trial. The values double as Inspect `model_roles` keys.

    The auditor is templated in the MVP, so it has no role yet. JUDGE is the "human" judge: one
    outside party that answers both the violation question and the secrets question.
    INTEGRITY_CHECK is a measurement, not a participant.
    """

    ADVOCATE = "advocate"
    EXECUTOR = "executor"
    JUDGE = "judge"
    INTEGRITY_CHECK = "integrity_check"


class Stance(StrEnum):
    """What the lab wants from its advocate: honest but aggressive (R1) or cover-up (R2)."""

    HONEST = "honest"
    COVER_UP = "cover_up"
