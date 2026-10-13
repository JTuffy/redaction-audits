"""What each reader is allowed to see, rendered as plain text.

Keeping these renderings in one place guarantees the information boundaries in the spec:
the "human" judge sees evidence only, no reader ever sees the grade, and the auditor sees the logs.
"""

from __future__ import annotations

from redaction_escalation.domain.models import Report, Scenario


def logs_view(scenario: Scenario) -> str:
    """The log bundle as the auditor reads it."""
    lines = [f"Lab: {scenario.lab_name}", ""]
    lines.extend(
        f"[{entry.log_id}] {entry.timestamp} {entry.source}: {entry.text}"
        for entry in scenario.logs
    )
    return "\n".join(lines)


def evidence_view(report: Report) -> str:
    """Evidence quotes only: no finding, no reasoning, no grade (the "human" judge's input)."""
    if not report.evidence:
        return "(The report quotes no evidence.)"
    return "\n".join(f"[{quote.log_id}] {quote.quote}" for quote in report.evidence)


def report_view(report: Report) -> str:
    """The full report text without the grade (the advocate's and honest executor's input)."""
    return "\n".join(
        [
            f"Finding: {report.finding}",
            "",
            "Evidence:",
            evidence_view(report),
            "",
            f"Reasoning: {report.reasoning}",
        ]
    )
