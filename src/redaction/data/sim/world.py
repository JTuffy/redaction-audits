"""A lab's world, shared by every claim: teams, people, endpoints, and timed events.

Each claim adds the events its mechanics need (deploys and change requests for classifier off)
and checks itself against the whole world. Org structure (who leads which team, which team owns
which endpoint) lives here, so a claim can turn on it and redaction can break it.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any

from redaction.core.models import SecretType
from redaction.data.generator import TEAM_NAMES


@dataclass
class Person:
    """Someone at the lab."""

    name: str
    team: str


@dataclass
class Endpoint:
    """A model endpoint: codename, environment, customer (if any) and the team that owns it."""

    codename: str
    env: str
    customer: str | None
    team: str


@dataclass
class Event:
    """One fact. `eid` is stable across a world and its twin; `t` orders events in time."""

    eid: int
    t: float
    kind: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Lab:
    """Everything that happened at one lab during the audit window."""

    people: list[Person]
    leads: dict[str, int]  # team -> index into people
    endpoints: list[Endpoint]
    events: list[Event] = field(default_factory=list)
    next_eid: int = 0

    def add(self, t: float, kind: str, **fields: Any) -> Event:  # noqa: ANN401
        """Record an event and return it."""
        event = Event(self.next_eid, t, kind, dict(fields))
        self.next_eid += 1
        self.events.append(event)
        return event

    def ordered(self) -> list[Event]:
        """Events in time order."""
        return sorted(self.events, key=lambda e: e.t)

    def by_eid(self, eid: int) -> Event:
        """The event with this id."""
        return next(e for e in self.events if e.eid == eid)

    def lead_of(self, team: str) -> Person:
        """Who leads a team."""
        return self.people[self.leads[team]]

    def twin(self) -> Lab:
        """A deep copy to perturb."""
        return copy.deepcopy(self)


def sample_lab(
    rng: random.Random,
    options: dict[SecretType, list[str]],
    *,
    endpoints: tuple[int, int],
    p_production: float,
    p_customer: float,
) -> Lab:
    """Draw teams, people and endpoints, and record the org chart as events."""
    teams = rng.sample(list(TEAM_NAMES), rng.randint(2, 3))
    names = rng.sample(options[SecretType.EMPLOYEE_NAME], len(teams) + rng.randint(1, 3))
    people = [Person(n, teams[i % len(teams)]) for i, n in enumerate(names)]
    leads = {team: i for i, team in enumerate(teams)}  # the first person on each team leads it
    codenames = rng.sample(options[SecretType.CODENAME], rng.randint(*endpoints))
    customers = rng.sample(options[SecretType.CUSTOMER_NAME], len(codenames))
    eps = []
    for codename, customer in zip(codenames, customers, strict=True):
        env = "production" if rng.random() < p_production else "staging"
        named = env == "production" and rng.random() < p_customer
        eps.append(Endpoint(codename, env, customer if named else None, rng.choice(teams)))
    lab = Lab(people, leads, eps)
    for team in teams:
        lab.add(rng.uniform(0, 8), "org_lead", team=team, person=leads[team])
    for k, ep in enumerate(eps):
        lab.add(rng.uniform(0, 12), "org_owner", endpoint=k, team=ep.team)
    return lab
