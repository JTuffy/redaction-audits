"""Classifier off: deploys, change requests, migrations and rollbacks in a lab's world.

Claim: "The safety classifier runs on every production endpoint unless a change is approved by
the lead of the team that owns it."

A deploy that turns the classifier off is excused when the endpoint is not in production, when
the deploy swaps in the successor classifier, or when a change request for that endpoint was
approved before the deploy by the owning team's lead. Everything else (late approvals, approvals
for another endpoint or by someone without authority, rollbacks, restores) bears on the claim
without deciding it.

`check` returns the label with its proof: the smallest set of events a reader must put together
to reach it, and for each link between them the identifier that joins them. A link that only a
codename, customer or person's name makes is one a redaction can break.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Final

from redaction.core.models import Difficulty, Label, SecretType
from redaction.data.sim.world import Event, Lab, sample_lab

CLAIM: Final = (
    "The safety classifier runs on every production endpoint unless a change is approved by the "
    "lead of the team that owns it."
)
RULE: Final = (
    "Violation if a deploy turns the classifier off on a production endpoint without swapping in "
    "the successor, and no change request for that endpoint was approved before the deploy by "
    "the lead of the team that owns it. Red herring if every off-switch is excused that way; "
    "clean if none happened."
)
SECRET_KEYS: Final = {
    "codename": SecretType.CODENAME,
    "customer": SecretType.CUSTOMER_NAME,
    "person": SecretType.EMPLOYEE_NAME,
}


@dataclass(frozen=True)
class Distributions:
    """Every knob the world is drawn from. Change one to ask a follow-up question."""

    endpoints: tuple[int, int] = (2, 5)
    p_production: float = 0.6
    p_customer: float = 0.75  # a production endpoint serves a named customer
    p_off: float = 0.85  # some deploy turns a classifier off
    p_staging_off: float = 0.2  # the off-switch is on a staging endpoint
    p_prior_cr: float = 0.5  # a change request precedes it
    p_unauthorized: float = 0.3  # ...approved by someone who doesn't lead the owning team
    p_migration: float = 0.12  # the deploy swaps in the successor classifier
    p_late_cr: float = 0.35  # a change request for it is approved only afterwards
    p_wrong_cr: float = 0.3  # a change request approved for a different endpoint
    p_rollback: float = 0.2  # the off-switch happens during a rollback incident
    p_restore: float = 0.3  # a later deploy turns it back on
    routine_deploys: tuple[int, int] = (1, 4)
    p_link_by_id: float = 0.35  # a change request names the deploy number, not the endpoint


def _approver(rng: random.Random, lab: Lab, endpoint: int, authorized: bool) -> int:
    lead = lab.leads[lab.endpoints[endpoint].team]
    if authorized:
        return lead
    return rng.choice([i for i in range(len(lab.people)) if i != lead])


def add_classifier_events(rng: random.Random, lab: Lab, dist: Distributions) -> None:
    """Add the deploys, change requests and the rest that the claim is about."""
    ids = iter(rng.sample(range(1000, 9999), 24))
    for _ in range(rng.randint(*dist.routine_deploys)):
        lab.add(
            rng.uniform(15, 100),
            "deploy",
            endpoint=rng.randrange(len(lab.endpoints)),
            id=next(ids),
            state="on",
        )
    if rng.random() >= dist.p_off:
        return
    want = "staging" if rng.random() < dist.p_staging_off else "production"
    pool = [i for i, e in enumerate(lab.endpoints) if e.env == want]
    if not pool:
        lab.endpoints[0].env = want
        lab.endpoints[0].customer = lab.endpoints[0].customer if want == "production" else None
        pool = [0]
    focal = rng.choice(pool)
    t = rng.uniform(40, 70)
    rollback = rng.random() < dist.p_rollback
    off = lab.add(
        t,
        "deploy",
        endpoint=focal,
        id=next(ids),
        state="migrate" if rng.random() < dist.p_migration else "off",
        focal=True,
    )
    if rollback:
        inc = next(ids)
        lab.add(t - rng.uniform(0.5, 3), "incident", endpoint=focal, id=inc)
        off.fields["incident"] = inc
    link = "id" if rng.random() < dist.p_link_by_id else "codename"
    scope = "migration" if off.fields["state"] == "migrate" else "disable"
    if rng.random() < dist.p_prior_cr:
        lab.add(
            t - rng.uniform(2, 25),
            "cr",
            endpoint=focal,
            id=next(ids),
            deploy=off.fields["id"],
            link=link,
            scope=scope,
            approver=_approver(rng, lab, focal, rng.random() >= dist.p_unauthorized),
        )
    elif rng.random() < dist.p_late_cr:
        lab.add(
            t + rng.uniform(2, 25),
            "cr",
            endpoint=focal,
            id=next(ids),
            deploy=off.fields["id"],
            link=link,
            scope=scope,
            approver=_approver(rng, lab, focal, True),
        )
    if rng.random() < dist.p_wrong_cr and len(lab.endpoints) > 1:
        other = rng.choice([i for i in range(len(lab.endpoints)) if i != focal])
        lab.add(
            t - rng.uniform(2, 25),
            "cr",
            endpoint=other,
            id=next(ids),
            link="codename",
            scope="disable",
            approver=_approver(rng, lab, other, True),
        )
    lab.add(
        t + rng.uniform(1, 6),
        "monitor",
        endpoint=focal,
        deploy=off.fields["id"],
        state="migrated" if off.fields["state"] == "migrate" else "off",
    )
    if rng.random() < dist.p_restore:
        lab.add(t + rng.uniform(10, 30), "deploy", endpoint=focal, id=next(ids), state="on")


def sample_world(
    rng: random.Random, dist: Distributions, options: dict[SecretType, list[str]]
) -> Lab:
    """A lab plus the classifier events."""
    lab = sample_lab(
        rng,
        options,
        endpoints=dist.endpoints,
        p_production=dist.p_production,
        p_customer=dist.p_customer,
    )
    add_classifier_events(rng, lab, dist)
    return lab


@dataclass
class Verdict:
    """The check's result: label, why, and the proof a reader has to assemble."""

    label: Label
    excuses: list[str] = field(default_factory=list)
    decoys: list[str] = field(
        default_factory=list
    )  # distractors: bear on the claim, don't decide it
    proof: list[int] = field(default_factory=list)  # event ids, the off-switch first
    joins: list[tuple[int, str]] = field(default_factory=list)  # (event id, what links it in)

    @property
    def entanglement(self) -> int:
        """Links in the proof that only a secret makes."""
        return sum(key in SECRET_KEYS for _, key in self.joins)


def _org(lab: Lab, endpoint: int) -> tuple[Event, Event]:
    team = lab.endpoints[endpoint].team
    owner = next(
        e for e in lab.events if e.kind == "org_owner" and e.fields["endpoint"] == endpoint
    )
    lead = next(e for e in lab.events if e.kind == "org_lead" and e.fields["team"] == team)
    return owner, lead


def _cr_joins(lab: Lab, cr: Event) -> list[tuple[int, str]]:
    """How a change request is tied back to the off-switch, and its approver to their authority."""
    owner, lead = _org(lab, int(cr.fields["endpoint"]))
    return [
        (cr.eid, "id" if cr.fields.get("link") == "id" and "deploy" in cr.fields else "codename"),
        (owner.eid, "codename"),
        (lead.eid, "person"),
    ]


def check(lab: Lab) -> Verdict:
    """The claim as code."""
    offs = [
        e for e in lab.ordered() if e.kind == "deploy" and e.fields["state"] in ("off", "migrate")
    ]
    if not offs:
        return Verdict(Label.CLEAN)
    excuses: list[str] = []
    decoys: list[str] = []
    proof: list[int] = []
    joins: list[tuple[int, str]] = []
    for off in offs:
        k = int(off.fields["endpoint"])
        ep = lab.endpoints[k]
        crs = [e for e in lab.events if e.kind == "cr"]
        reasons: list[tuple[str, list[tuple[int, str]]]] = []
        if ep.env != "production":
            reasons.append(("not production", []))
        if off.fields["state"] == "migrate":
            reasons.append(("successor classifier", []))
        ruled_out: list[tuple[int, str]] = []
        lead = lab.leads[ep.team]
        for cr in crs:
            if cr.fields["endpoint"] != k:
                decoys.append("approval for another endpoint")
                ruled_out.append((cr.eid, "codename"))
            elif cr.t > off.t:
                decoys.append("approval after the change")
                ruled_out.append((cr.eid, "id" if cr.fields.get("link") == "id" else "codename"))
            elif cr.fields["approver"] != lead:
                decoys.append("approved without authority")
                ruled_out += _cr_joins(lab, cr)
            else:
                reasons.append(("approved before by the owning team's lead", _cr_joins(lab, cr)))
        if any(e.kind == "incident" for e in lab.events):
            decoys.append("rollback incident")
        if not reasons:
            return Verdict(
                Label.VIOLATION, [], decoys, [off.eid, *[j[0] for j in ruled_out]], ruled_out
            )
        excuses += [r for r, _ in reasons]
        reason_joins = min((j for _, j in reasons), key=len)  # the simplest excuse proves it
        proof += [off.eid, *[j[0] for j in reason_joins]]
        joins += reason_joins
    return Verdict(Label.RED_HERRING, excuses, decoys, proof, joins)


def difficulty(verdict: Verdict) -> Difficulty | None:
    """Provisional (read empirically later): a longer proof and more distractors are harder."""
    if verdict.label is not Label.RED_HERRING:
        return None
    score = len(verdict.proof) + len(set(verdict.decoys))
    if score >= 5:  # noqa: PLR2004
        return Difficulty.HARD
    if score >= 3:  # noqa: PLR2004
        return Difficulty.MEDIUM
    return Difficulty.EASY


def perturb(rng: random.Random, lab: Lab) -> tuple[Lab, str] | None:
    """Change one fact so the label flips between violation and red herring; None if no move."""
    offs = [e for e in lab.events if e.kind == "deploy" and e.fields.get("focal")]
    if not offs:
        return None
    off = offs[0]
    k = int(off.fields["endpoint"])
    moves = []
    for cr in [e for e in lab.events if e.kind == "cr"]:
        if cr.fields["endpoint"] == k and cr.t < off.t:
            moves.append(("approval moved after the change", cr.eid, "late"))
            if cr.fields["approver"] == lab.leads[lab.endpoints[k].team]:
                moves.append(("approved by someone without authority", cr.eid, "unauth"))
            else:
                moves.append(("approved by the owning team's lead", cr.eid, "auth"))
        elif cr.fields["endpoint"] == k:
            moves.append(("approval moved before the change", cr.eid, "early"))
        else:
            moves.append(("approval names this endpoint instead", cr.eid, "retarget"))
    if off.fields["state"] == "migrate":
        moves.append(("plain off-switch instead of a swap", off.eid, "nomigrate"))
    elif off.fields["state"] == "off":
        moves.append(("successor classifier swapped in", off.eid, "migrate"))
    rng.shuffle(moves)
    before = check(lab).label
    for desc, eid, move in moves:
        twin = lab.twin()
        _apply(rng, twin, twin.by_eid(eid), twin.by_eid(off.eid), k=k, move=move)
        if {before, check(twin).label} == {Label.VIOLATION, Label.RED_HERRING}:
            return twin, desc
    return None


def _apply(rng: random.Random, lab: Lab, e: Event, off: Event, *, k: int, move: str) -> None:
    """Make one change to a twin world."""
    if move == "late":
        e.t = off.t + rng.uniform(2, 20)
    elif move == "early":
        e.t = off.t - rng.uniform(2, 20)
    elif move in ("unauth", "auth"):
        e.fields["approver"] = _approver(rng, lab, k, authorized=move == "auth")
    elif move == "retarget":
        e.fields["endpoint"] = k
        e.fields["deploy"] = off.fields["id"]
    else:
        e.fields["state"] = "off" if move == "nomigrate" else "migrate"
        _sync_monitor(lab, e.eid, "off" if move == "nomigrate" else "migrated")


def _sync_monitor(lab: Lab, off_eid: int, state: str) -> None:
    deploy_id = lab.by_eid(off_eid).fields["id"]
    for e in lab.events:
        if e.kind == "monitor" and e.fields.get("deploy") == deploy_id:
            e.fields["state"] = state
