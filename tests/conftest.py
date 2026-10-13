from __future__ import annotations

import pytest

from redaction_escalation.domain.models import Label, Report, Scenario, Split
from redaction_escalation.scenarios.generator import build_split
from redaction_escalation.scenarios.reports import templated_report


@pytest.fixture(scope="session")
def dev_scenarios() -> tuple[Scenario, ...]:
    return build_split(Split.DEV)


@pytest.fixture(scope="session")
def violation(dev_scenarios: tuple[Scenario, ...]) -> Scenario:
    return next(s for s in dev_scenarios if s.label is Label.VIOLATION)


@pytest.fixture(scope="session")
def violation_report(violation: Scenario) -> Report:
    return templated_report(violation)
