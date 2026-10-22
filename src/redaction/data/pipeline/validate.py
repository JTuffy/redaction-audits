"""Layer 3a: code checks that a rendering still carries exactly the plan's facts.

Every check returns `Issue`s rather than raising, so the build can count failures by kind and
the viewer can show why a scenario was rejected. A rendering with any error is not kept.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum

from redaction.core.models import Frozen
from redaction.core.registry import spec_for
from redaction.data.pipeline.plan import ScenarioPlan, required_for
from redaction.data.pipeline.render import Rendering


class Check(StrEnum):
    """The validators, in the order they run."""

    REFUSED = "refused"  # the renderer declined the request; nothing to check
    SHAPE = "shape"  # one rendered line per planned line, none empty
    BACKGROUND_INTACT = "background_intact"  # real records were not rewritten
    REQUIRED_KEPT = "required_kept"  # secret values and cue tokens survived rephrasing
    CORRELATE_KEPT = "correlate_kept"  # each correlate snippet is still in its line
    NO_VERBATIM_IN_CORRELATE = "no_verbatim_in_correlate"  # correlates must not state the value
    NO_FOREIGN_OPTION = "no_foreign_option"  # no other option of a planted secret appears
    LABEL_CLEAN = "label_clean"  # non-violations carry no violation-only token
    NO_DUPLICATES = "no_duplicates"  # repeated lines would make the bundle read as generated


class Issue(Frozen):
    """One failed check."""

    check: Check
    line: int | None  # plan index, when the issue is about one line
    detail: str


def validate(
    plan: ScenarioPlan, rendering: Rendering, *, paraphrase: bool = False
) -> tuple[Issue, ...]:
    """Run every check. An empty result means the rendering is kept.

    With `paraphrase`, evidence lines may restate their cues in other words (see
    `plan.required_for`); the blind reviewer then has to confirm the label instead.
    """
    if rendering.refused:
        return (Issue(check=Check.REFUSED, line=None, detail=rendering.renderer),)
    if len(rendering.lines) != len(plan.lines):
        return (
            Issue(
                check=Check.SHAPE,
                line=None,
                detail=f"{len(rendering.lines)} lines for {len(plan.lines)} planned",
            ),
        )
    issues: list[Issue] = []
    corpus = "\n".join(line.text for line in rendering.lines)
    for i, (planned, rendered) in enumerate(zip(plan.lines, rendering.lines, strict=True)):
        if not rendered.text.strip():
            issues.append(Issue(check=Check.SHAPE, line=i, detail="empty line"))
            continue
        if not planned.rephrasable and rendered.text != planned.text:
            issues.append(Issue(check=Check.BACKGROUND_INTACT, line=i, detail=rendered.text[:120]))
        missing = [
            r for r in required_for(planned, paraphrase=paraphrase) if r not in rendered.text
        ]
        if missing and planned.correlate_snippet is None:
            issues.append(Issue(check=Check.REQUIRED_KEPT, line=i, detail=", ".join(missing)))
        if planned.correlate_snippet is not None:
            if planned.correlate_snippet not in rendered.text:
                issues.append(
                    Issue(check=Check.CORRELATE_KEPT, line=i, detail=planned.correlate_snippet)
                )
            secret = next(s for s in plan.secrets if s.secret_type is planned.correlate_type)
            if secret.value in rendered.text:
                issues.append(
                    Issue(check=Check.NO_VERBATIM_IN_CORRELATE, line=i, detail=secret.value)
                )
    confidential = {c.value for c in plan.confidential}
    issues += [
        Issue(check=Check.NO_FOREIGN_OPTION, line=None, detail=f"{secret.secret_type}: {option}")
        for secret in plan.secrets
        for option in spec_for(secret.secret_type).options
        if option != secret.value and option not in confidential and option in corpus
    ]
    issues += [
        Issue(check=Check.LABEL_CLEAN, line=None, detail=token)
        for token in plan.forbidden
        if token in corpus
    ]
    repeats = [text for text, n in Counter(r.text for r in rendering.lines).items() if n > 1]
    issues += [Issue(check=Check.NO_DUPLICATES, line=None, detail=t[:120]) for t in repeats]
    return tuple(issues)
