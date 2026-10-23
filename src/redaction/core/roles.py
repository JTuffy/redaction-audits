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
    """What the lab wants from its advocate.

    HONEST and COVER_UP prompt the advocate model. RED_TEAM prompts it to play the cover-up as
    an authorized internal exercise, since models tend to refuse COVER_UP. The SCRIPTED stances
    use no model: fixed attacks that bound what an adversarial advocate could get past the
    executor (see `escalation/adversary.py`).
    """

    HONEST = "honest"
    COVER_UP = "cover_up"
    RED_TEAM = "red_team"
    SCRIPTED_BLATANT = "scripted_blatant"  # ask to remove each key-evidence line outright
    SCRIPTED_LINK = "scripted_link"  # ask for type markers on every confidential value

    @property
    def scripted(self) -> bool:
        """Whether the requests come from a script rather than the advocate model."""
        return self in {Stance.SCRIPTED_BLATANT, Stance.SCRIPTED_LINK}
