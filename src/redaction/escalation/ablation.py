"""Marker ablation: does a visible redaction marker, by itself, make evidence look guiltier?

In the first real run, swapping two names for markers raised the "human" judge's suspicion of a
red herring from 15 to 70. This ablation holds everything else fixed and varies only how removed
values are shown, on the quoted evidence the judge reads:

- `unedited`: the evidence as quoted.
- `marker`: every planted secret value replaced by `[REDACTED: <label>]` (text redaction's form).
- `pseudonym`: the same values replaced by neutral stand-ins ("Customer A"), with no marker.
- `marker_only`: the values kept, and a marker appended to each line that holds one, so a marker
  is present but nothing is actually removed.

`marker` against `pseudonym` isolates the marker's form with the same information removed;
`marker_only` against `unedited` isolates the marker with no information removed.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from redaction.core.models import EvidenceQuote, Report, Scenario, SecretType
from redaction.core.registry import redaction_marker

# Neutral stand-ins: none is a registry option, and none looks like a redaction.
PSEUDONYMS: Final[dict[SecretType, str]] = {
    SecretType.LR_SCHEDULE: "schedule S1",
    SecretType.DATA_MIX: "mix M1",
    SecretType.CUSTOMER_NAME: "Customer A",
    SecretType.EMPLOYEE_NAME: "Employee A",
    SecretType.OPTIMIZER: "optimizer O1",
    SecretType.PARAMETER_SCALE: "size S1",
    SecretType.ARCHITECTURE: "architecture A1",
    SecretType.DATA_VENDOR: "Vendor A",
    SecretType.CODENAME: "Project A",
    SecretType.DELIBERATION: "the decision recorded in minutes M1",
    SecretType.COMPUTE_FOOTPRINT: "allocation C1",
    SecretType.RELEASE_DATE: "release window R1",
}


class Condition(StrEnum):
    """How removed values are shown to the "human" judge."""

    UNEDITED = "unedited"
    MARKER = "marker"
    PSEUDONYM = "pseudonym"
    MARKER_ONLY = "marker_only"


def _replace(text: str, needle: str, replacement: str) -> str:
    return re.sub(re.escape(needle), lambda _: replacement, text, flags=re.IGNORECASE)


def nth_pseudonym(secret_type: SecretType, k: int) -> str:
    """The k-th distinct stand-in for a type: Customer A, Customer B; allocation C1, C2."""
    base = PSEUDONYMS[secret_type]
    if k == 0:
        return base
    if base[-1].isdigit():
        return f"{base[:-1]}{int(base[-1]) + k}"
    return f"{base[:-1]}{chr(ord(base[-1]) + k)}"


def stand_ins(scenario: Scenario, *, consistent: bool) -> dict[str, str]:
    """Replacement text per confidential value.

    Consistent stand-ins give each distinct value of a type its own pseudonym, so two customers
    stay two customers. Markers are not consistent: every value of a type gets the same marker.
    """
    seen: dict[SecretType, int] = {}
    out: dict[str, str] = {}
    for secret in scenario.redactable():
        k = seen.get(secret.secret_type, 0)
        seen[secret.secret_type] = k + 1
        out[secret.value] = (
            nth_pseudonym(secret.secret_type, k)
            if consistent
            else redaction_marker(secret.secret_type)
        )
    return out


def _substitute(report: Report, replacements: dict[str, str]) -> Report:
    values = sorted(replacements, key=len, reverse=True)

    def transform(text: str) -> str:
        for value in values:
            text = _replace(text, value, replacements[value])
        return text

    return report.with_text(transform)


def _append_markers(report: Report, scenario: Scenario) -> Report:
    def marked(quote: EvidenceQuote) -> EvidenceQuote:
        held = [s for s in scenario.redactable() if s.value.casefold() in quote.quote.casefold()]
        if not held:
            return quote
        markers = " ".join(redaction_marker(s.secret_type) for s in held)
        return EvidenceQuote(log_id=quote.log_id, quote=f"{quote.quote} {markers}")

    return report.model_copy(update={"evidence": tuple(marked(q) for q in report.evidence)})


def variant(report: Report, scenario: Scenario, condition: Condition) -> Report:
    """The report as the judge sees it under one condition."""
    if condition is Condition.UNEDITED:
        return report
    if condition is Condition.MARKER:
        return _substitute(report, stand_ins(scenario, consistent=False))
    if condition is Condition.PSEUDONYM:
        return _substitute(report, stand_ins(scenario, consistent=True))
    return _append_markers(report, scenario)
