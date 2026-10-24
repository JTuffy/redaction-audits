"""The simulator: the check labels worlds correctly, twins differ in one fact, plans validate."""

from __future__ import annotations

import asyncio
import random
from collections import Counter

from redaction.core.models import Label, Split
from redaction.data.pipeline.render import TemplateRenderer
from redaction.data.sim.build import build_sim, sample_to_quota
from redaction.data.sim.classifier import check, perturb
from redaction.data.sim.render import simulate
from redaction.data.sim.world import Endpoint, Lab, Person


def _lab(env: str = "production") -> Lab:
    lab = Lab(
        people=[
            Person("Priya Raman", "atlas"),
            Person("Marcus Ellery", "ridge"),
            Person("Dana Okafor", "atlas"),
        ],
        leads={"atlas": 0, "ridge": 1},
        endpoints=[
            Endpoint("Project Lumen", env, "Halvorsen Logistics", "atlas"),
            Endpoint("Project Heron", "production", None, "ridge"),
        ],
    )
    lab.add(1, "org_lead", team="atlas", person=0)
    lab.add(2, "org_lead", team="ridge", person=1)
    lab.add(3, "org_owner", endpoint=0, team="atlas")
    lab.add(4, "org_owner", endpoint=1, team="ridge")
    return lab


def _off(lab: Lab, state: str = "off") -> None:
    lab.add(50, "deploy", endpoint=0, id=1234, state=state, focal=True)


def _cr(lab: Lab, t: float, endpoint: int = 0, approver: int = 0) -> None:
    lab.add(
        t,
        "cr",
        endpoint=endpoint,
        id=77,
        deploy=1234,
        link="id",
        scope="disable",
        approver=approver,
    )


def test_off_without_approval_is_a_violation() -> None:
    lab = _lab()
    _off(lab)
    assert check(lab).label is Label.VIOLATION


def test_prior_approval_by_the_lead_excuses_and_its_proof_runs_through_org_lines() -> None:
    lab = _lab()
    _off(lab)
    _cr(lab, 40)
    verdict = check(lab)
    assert verdict.label is Label.RED_HERRING
    assert [k for _, k in verdict.joins] == ["id", "codename", "person"]
    assert verdict.entanglement == 2


def test_late_wrong_endpoint_and_unauthorized_approvals_do_not_excuse() -> None:
    for t, endpoint, approver in ((60, 0, 0), (40, 1, 1), (40, 0, 2)):
        lab = _lab()
        _off(lab)
        _cr(lab, t, endpoint, approver)
        assert check(lab).label is Label.VIOLATION, (t, endpoint, approver)


def test_staging_and_successor_excuse_and_no_off_switch_is_clean() -> None:
    lab = _lab("staging")
    _off(lab)
    assert check(lab).label is Label.RED_HERRING
    lab = _lab()
    _off(lab, "migrate")
    assert check(lab).label is Label.RED_HERRING
    assert check(_lab()).label is Label.CLEAN


def test_twin_differs_in_one_fact_and_flips_the_label() -> None:
    lab = _lab()
    _off(lab)
    _cr(lab, 40)
    twin = perturb(random.Random(0), lab)
    assert twin is not None
    other, _ = twin
    assert check(other).label is Label.VIOLATION
    changed = [a.eid for a, b in zip(lab.events, other.events, strict=True) if a != b]
    assert len(changed) == 1


def test_twins_share_everything_but_the_changed_line() -> None:
    draw = next(d for d in (simulate(Split.DEV, i, 909) for i in range(40)) if len(d) == 2)
    (a, _), (b, _) = draw
    assert {a.label, b.label} == {Label.VIOLATION, Label.RED_HERRING}
    differing = {line.text for line in a.lines} ^ {line.text for line in b.lines}
    assert 1 <= len(differing) <= 4  # the changed line (and a monitor line it implies)


def test_quota_and_template_build() -> None:
    made = sample_to_quota(40, Split.DEV, 909)
    counts = Counter(p.label for p, _ in made)
    assert counts[Label.CLEAN] == 8
    assert counts[Label.VIOLATION] == counts[Label.RED_HERRING] == 16
    result, _ = asyncio.run(build_sim(40, TemplateRenderer()))
    assert len(result.scenarios) == 40
