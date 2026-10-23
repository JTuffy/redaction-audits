"""Can planted lines be told from background by their surface alone?

If evidence can be picked out by source, shape or length, background is decoration: an auditor
(or an adversary) can drop it without reading it. This fits a small naive Bayes model on surface
features only (source, first word, number of `key=value` tokens, length, ID shapes) on half the
violation types and scores the other half (both ways, averaged). Holding out whole types asks
the useful question: can a filter that has not seen this type's evidence find it by shape? (Within
one type, evidence repeats its template, so any first word is learnable.) An AUROC near 0.5 means
the surface gives nothing away.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Final

from redaction.core.metrics import auroc
from redaction.data.pipeline.plan import TOKEN_PATTERN, LineKind, PlannedLine, ScenarioPlan

SURFACE_AUROC_MAX: Final = 0.75  # above this the build warns: background is filterable
_ID_SHAPES: Final = (
    ("app_id", re.compile(r"\bapp-\d")),
    ("run_id", re.compile(r"\brun-\d")),
    ("ticket", re.compile(r"\b[A-Z]{2,4}-\d")),
    ("date", re.compile(r"\d{4}-\d{2}-\d{2}")),
)
PLANTED: Final = frozenset({LineKind.EVIDENCE, LineKind.CORRELATE, LineKind.SECRET_MENTION})


def features(line: PlannedLine) -> tuple[str, ...]:
    """Surface features of one line: nothing about what it says."""
    words = line.text.split()
    kv = min(3, len(TOKEN_PATTERN.findall(line.text)))
    return (
        f"src={line.source}",
        f"first={words[0].casefold() if words else ''}",
        f"kv={kv}",
        f"len={min(12, len(line.text) // 15)}",
        *(f"shape={name}" for name, pattern in _ID_SHAPES if pattern.search(line.text)),
    )


class _NaiveBayes:
    def __init__(self, examples: Iterable[tuple[tuple[str, ...], bool]]) -> None:
        self.counts = {True: Counter[str](), False: Counter[str]()}
        self.totals = Counter[bool]()
        for feats, planted in examples:
            self.totals[planted] += 1
            self.counts[planted].update(feats)

    def score(self, feats: Sequence[str]) -> float:
        """Log-odds that a line is planted."""
        logit = math.log((self.totals[True] + 1) / (self.totals[False] + 1))
        for f in feats:
            p = (self.counts[True][f] + 1) / (self.totals[True] + 2)
            q = (self.counts[False][f] + 1) / (self.totals[False] + 2)
            logit += math.log(p / q)
        return logit


def surface_auroc(plans: Sequence[ScenarioPlan]) -> float | None:
    """Held-out AUROC of planted vs background lines from surface features (None if too few).

    Train on half the violation types, score the other half, then swap; the mean of the two.
    """

    def examples(subset: Iterable[ScenarioPlan]) -> list[tuple[tuple[str, ...], bool]]:
        return [(features(line), line.kind in PLANTED) for plan in subset for line in plan.lines]

    types = sorted({str(p.violation_type) for p in plans})
    halves = (set(types[0::2]), set(types[1::2]))
    scores = []
    for train_types, test_types in (halves, halves[::-1]):
        train = examples(p for p in plans if str(p.violation_type) in train_types)
        test = examples(p for p in plans if str(p.violation_type) in test_types)
        if not train or len({planted for _, planted in test}) < 2:  # noqa: PLR2004
            continue
        model = _NaiveBayes(train)
        pos = [model.score(f) for f, planted in test if planted]
        neg = [model.score(f) for f, planted in test if not planted]
        scores.append(auroc(pos, neg))
    return sum(scores) / len(scores) if scores else None
