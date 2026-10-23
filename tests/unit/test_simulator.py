"""The classifier-off simulator: the check labels worlds correctly and plans pass validation."""

from __future__ import annotations

import asyncio

from redaction.core.models import Label, Split
from redaction.data.pipeline.render import TemplateRenderer
from redaction.data.sim.build import build_sim
from redaction.data.sim.classifier import Endpoint, Event, World, check
from redaction.data.sim.render import simulate


def _world(env: str, *events: Event) -> World:
    return World(
        [
            Endpoint("Project Lumen", env, "Halvorsen Logistics"),
            Endpoint("Project Heron", "production", None),
        ],
        list(events),
        "Priya Raman",
        0,
    )


def _off(t: float = 50, state: str = "off") -> Event:
    return Event(t, "deploy", 0, {"id": 1234, "state": state})


def test_off_in_production_without_approval_is_a_violation() -> None:
    assert check(_world("production", _off())).label is Label.VIOLATION


def test_late_approval_does_not_excuse() -> None:
    late = Event(60, "cr", 0, {"id": 1, "link": "codename", "scope": "disable"})
    verdict = check(_world("production", _off(), late))
    assert verdict.label is Label.VIOLATION
    assert "approval after the change" in verdict.decoys


def test_prior_approval_staging_and_successor_excuse() -> None:
    prior = Event(40, "cr", 0, {"id": 1, "link": "id", "deploy": 1234, "scope": "disable"})
    assert check(_world("production", prior, _off())).label is Label.RED_HERRING
    assert check(_world("staging", _off())).label is Label.RED_HERRING
    assert check(_world("production", _off(state="migrate"))).label is Label.RED_HERRING


def test_approval_for_another_endpoint_does_not_excuse() -> None:
    wrong = Event(40, "cr", 1, {"id": 1, "link": "codename", "scope": "disable"})
    assert check(_world("production", wrong, _off())).label is Label.VIOLATION


def test_no_off_switch_is_clean() -> None:
    assert (
        check(_world("production", Event(10, "deploy", 0, {"id": 9, "state": "on"}))).label
        is Label.CLEAN
    )


def test_simulated_plans_are_deterministic_and_valid() -> None:
    first, attrs = simulate(Split.DEV, 3, 909)
    again, _ = simulate(Split.DEV, 3, 909)
    assert first == again
    assert attrs["label"] == first.label
    result, _ = asyncio.run(build_sim(40, TemplateRenderer()))
    assert len(result.scenarios) == 40
    assert {s.label for s in result.scenarios} == set(Label)
