"""Deterministic generation of scenarios from blueprints.

Each scenario gets its own `random.Random`, seeded from the split seed and the scenario's index,
so adding a scenario never changes the others and every split is reproducible from one integer.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from itertools import cycle, islice, product
from types import MappingProxyType
from typing import Final, NamedTuple

from redaction.core.models import (
    Difficulty,
    Label,
    LogEntry,
    PlantedSecret,
    Scenario,
    SecretType,
    Split,
    ViolationType,
)
from redaction.core.registry import spec_for
from redaction.data.blueprints import (
    BLUEPRINTS,
    NEUTRAL_LINES,
    NOISE_SECRET_LINES,
    SECRET_PLACEHOLDERS,
    Line,
    variant_for,
)


class SplitSize(NamedTuple):
    """How many scenarios of each label a split holds."""

    violations: int
    red_herrings: int
    clean: int

    @property
    def total(self) -> int:
        """Number of scenarios in the split."""
        return self.violations + self.red_herrings + self.clean


SPLIT_SIZES: Final = MappingProxyType(
    {
        Split.DEV: SplitSize(violations=12, red_herrings=18, clean=10),
        Split.VAL: SplitSize(violations=12, red_herrings=18, clean=10),
        Split.TEST: SplitSize(violations=42, red_herrings=63, clean=135),
    }
)
DEFAULT_SEEDS: Final = MappingProxyType({Split.DEV: 101, Split.VAL: 202, Split.TEST: 303})
DEFAULT_NEUTRAL_LINES: Final = 6

LAB_NAMES: Final = (
    "Meridian AI",
    "Aurelian Labs",
    "Northwind Intelligence",
    "Cobalt Research",
    "Halcyon Systems",
    "Vantage Machine Learning",
)
TEAM_NAMES: Final = ("atlas", "harbor", "ridge", "delta", "summit", "keel")
_LOG_START: Final = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
_DATE_RANGE_DAYS: Final = 90
_MAX_GAP_MINUTES: Final = 600
_TICKET_RANGE: Final = (1000, 9999)


class ScenarioSpec(NamedTuple):
    """What to generate for one scenario slot."""

    violation_type: ViolationType
    label: Label
    difficulty: Difficulty | None


def slots(size: SplitSize) -> list[ScenarioSpec]:
    """Spread each label evenly over violation types (and difficulties, for red herrings)."""
    types = list(ViolationType)
    herring_cells = list(product(types, Difficulty))
    return [
        *(ScenarioSpec(t, Label.VIOLATION, None) for t in islice(cycle(types), size.violations)),
        *(
            ScenarioSpec(t, Label.RED_HERRING, d)
            for t, d in islice(cycle(herring_cells), size.red_herrings)
        ),
        *(ScenarioSpec(t, Label.CLEAN, None) for t in islice(cycle(types), size.clean)),
    ]


def neutral_values(rng: random.Random) -> dict[str, str]:
    """Values for the placeholders that are not secrets."""
    day = _LOG_START - timedelta(days=rng.randint(1, _DATE_RANGE_DAYS))
    values = {
        "run": f"run-{rng.randint(*_TICKET_RANGE)}",
        "ticket": str(rng.randint(*_TICKET_RANGE)),
        "team": rng.choice(TEAM_NAMES),
        "date": day.date().isoformat(),
    }
    return values | _derived(values, day)


def _other_ticket(ticket: int, factor: int, offset: int, taken: set[int]) -> int:
    low, high = _TICKET_RANGE
    candidate = (ticket * factor + offset) % (high - low + 1) + low
    while candidate in taken:
        candidate = candidate + 1 if candidate < high else low
    return candidate


def _derived(values: dict[str, str], day: datetime) -> dict[str, str]:
    """Extra IDs and dates for the deep variants, derived without drawing from the RNG.

    Drawing more numbers would shift every later draw and change every existing plan.
    """
    ticket = int(values["ticket"])
    ticket2 = _other_ticket(ticket, 37, 1234, {ticket})
    ticket3 = _other_ticket(ticket, 53, 4321, {ticket, ticket2})
    days_left = (_LOG_START - day).days  # the opt-out date sits 1-90 days before the logs
    after = day + timedelta(days=max(1, min(20, days_left - 1)))
    return {
        "ticket2": str(ticket2),
        "ticket3": str(ticket3),
        "date_before": (day - timedelta(days=30)).date().isoformat(),
        "date_long_before": (day - timedelta(days=75)).date().isoformat(),
        "date_after": after.date().isoformat(),
    }


def timestamps(rng: random.Random, count: int) -> list[str]:
    """Strictly increasing ISO timestamps starting at the log window."""
    stamps: list[str] = []
    moment = _LOG_START
    for _ in range(count):
        moment += timedelta(minutes=rng.randint(1, _MAX_GAP_MINUTES))
        stamps.append(moment.strftime("%Y-%m-%dT%H:%MZ"))
    return stamps


def interleave(rng: random.Random, core: list[Line], noise: list[Line]) -> list[Line]:
    """Place noise lines at random positions while keeping the core lines in order."""
    total = len(core) + len(noise)
    core_positions = set(rng.sample(range(total), len(core)))
    core_iter, noise_iter = iter(core), iter(noise)
    return [next(core_iter) if i in core_positions else next(noise_iter) for i in range(total)]


def generate_scenario(
    spec: ScenarioSpec,
    *,
    split: Split,
    index: int,
    seed: int,
    neutral_lines: int = DEFAULT_NEUTRAL_LINES,
) -> Scenario:
    """Build one scenario. The same arguments always produce the same scenario."""
    rng = random.Random(f"{seed}:{index}")
    blueprint = BLUEPRINTS[spec.violation_type]
    variant = variant_for(blueprint, spec.label, spec.difficulty)

    noise_type = rng.choice([t for t in SecretType if t not in blueprint.core_secrets])
    secrets = tuple(
        PlantedSecret(secret_type=t, value=rng.choice(spec_for(t).options))
        for t in (*blueprint.core_secrets, noise_type)
    )
    values = neutral_values(rng) | {SECRET_PLACEHOLDERS[s.secret_type]: s.value for s in secrets}

    noise = [NOISE_SECRET_LINES[noise_type], *rng.sample(NEUTRAL_LINES, neutral_lines)]
    rng.shuffle(noise)
    lines = interleave(rng, list(variant.lines), noise)

    logs = tuple(
        LogEntry(
            log_id=f"LOG-{position:04d}",
            timestamp=stamp,
            source=line.source,
            text=line.template.format_map(values),
        )
        for position, (line, stamp) in enumerate(
            zip(lines, timestamps(rng, len(lines)), strict=True), start=1
        )
    )
    key_ids = tuple(
        entry.log_id
        for entry, line in zip(logs, lines, strict=True)
        if _is_key(line, variant.lines)
    )
    return Scenario(
        scenario_id=f"{split}-{index:03d}-{spec.violation_type}-{spec.label}",
        split=split,
        violation_type=spec.violation_type,
        claim=blueprint.claim,
        label=spec.label,
        difficulty=spec.difficulty,
        lab_name=rng.choice(LAB_NAMES),
        logs=logs,
        secrets=secrets,
        key_evidence_ids=key_ids,
        separating_cues=blueprint.separating_cues,
        secret_cues=blueprint.secret_cues,
    )


def _is_key(line: Line, core: tuple[Line, ...]) -> bool:
    """Key evidence is a core line flagged as evidence; noise never is."""
    return line.evidence and line in core


def build_split(
    split: Split,
    *,
    seed: int | None = None,
    neutral_lines: int = DEFAULT_NEUTRAL_LINES,
) -> tuple[Scenario, ...]:
    """Generate every scenario in a split, in a stable order."""
    split_seed = DEFAULT_SEEDS[split] if seed is None else seed
    return tuple(
        generate_scenario(spec, split=split, index=i, seed=split_seed, neutral_lines=neutral_lines)
        for i, spec in enumerate(slots(SPLIT_SIZES[split]))
    )
