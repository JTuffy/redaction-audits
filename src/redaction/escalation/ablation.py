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

from redaction.core.models import EvidenceQuote, Report, Scenario
from redaction.core.registry import redaction_marker
from redaction.escalation.pseudonyms import stand_ins

# Neutral stand-ins: none is a registry option, and none looks like a redaction.


class Condition(StrEnum):
    """How removed values are shown to the "human" judge."""

    UNEDITED = "unedited"
    MARKER = "marker"
    PSEUDONYM = "pseudonym"
    MARKER_ONLY = "marker_only"


def _replace(text: str, needle: str, replacement: str) -> str:
    return re.sub(re.escape(needle), lambda _: replacement, text, flags=re.IGNORECASE)


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
