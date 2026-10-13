"""Who takes part in a trial, and what the lab wants from its advocate."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """The model roles in a trial. The values double as Inspect `model_roles` keys."""

    ADVOCATE = "advocate"
    REFEREE = "referee"
    VIEWER = "viewer"
    GUESSER = "guesser"
    JUDGE = "judge"


class Stance(StrEnum):
    """What the lab wants from its advocate: honest but aggressive (R1) or cover-up (R2)."""

    HONEST = "honest"
    COVER_UP = "cover_up"
