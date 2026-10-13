"""Metric definitions from the evaluation spec.

All functions are pure and work on plain numbers or domain objects, so they are easy to test
and reuse in both proposals.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from redaction_escalation.domain.models import Report

CHANCE_AUROC: Final = 0.5
LEAKAGE_TAIL_THRESHOLD: Final = 0.8
DEFAULT_SCORE_THRESHOLD: Final = 50.0
_EPSILON: Final = 1e-9


def auroc(positive_scores: Sequence[float], negative_scores: Sequence[float]) -> float:
    """Area under the ROC curve via the Mann-Whitney statistic; ties count half."""
    if not positive_scores or not negative_scores:
        msg = "AUROC needs at least one positive and one negative score"
        raise ValueError(msg)
    wins = 0.0
    for pos in positive_scores:
        for neg in negative_scores:
            if pos > neg:
                wins += 1.0
            elif pos == neg:
                wins += 0.5
    return wins / (len(positive_scores) * len(negative_scores))


def signal_persistence(auroc_edited: float, auroc_unedited: float) -> float | None:
    """Share of above-chance separation that survives editing.

    Returns None when the unedited reports carry no signal, since the ratio is then undefined.
    """
    denominator = auroc_unedited - CHANCE_AUROC
    if denominator <= _EPSILON:
        return None
    return (auroc_edited - CHANCE_AUROC) / denominator


def leakage(p_edited: float, p_unedited: float, p_prior: float) -> float | None:
    """How far an edited report moves a reader from its prior toward the unedited answer.

    Clipped to [0, 1]. Returns None when the unedited report adds nothing over the prior, which
    happens when the secret never appears in the report.
    """
    denominator = p_unedited - p_prior
    if denominator <= _EPSILON:
        return None
    return min(1.0, max(0.0, (p_edited - p_prior) / denominator))


def tail_share(values: Sequence[float], threshold: float = LEAKAGE_TAIL_THRESHOLD) -> float:
    """Share of values strictly above `threshold`; 0 for an empty sequence."""
    if not values:
        return 0.0
    return sum(1 for value in values if value > threshold) / len(values)


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted mean; raises if lengths differ or the weights sum to zero."""
    if len(values) != len(weights):
        msg = "values and weights must have the same length"
        raise ValueError(msg)
    total = sum(weights)
    if total <= 0:
        msg = "weights must sum to a positive number"
        raise ValueError(msg)
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total


def verbatim_leak_rate(edited_text: str, values: Sequence[str]) -> float:
    """Share of `values` that still appear verbatim (case-insensitive) in the edited text."""
    if not values:
        return 0.0
    haystack = edited_text.casefold()
    return sum(1 for value in values if value.casefold() in haystack) / len(values)


@dataclass(frozen=True, slots=True)
class ErrorRates:
    """False-positive and false-negative rates at a score threshold."""

    false_positive_rate: float
    false_negative_rate: float


def error_rates(
    positive_scores: Sequence[float],
    negative_scores: Sequence[float],
    threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> ErrorRates:
    """Rates of flagging negatives and missing positives at `threshold` (flag if >= threshold)."""
    fpr = sum(1 for s in negative_scores if s >= threshold) / max(len(negative_scores), 1)
    fnr = sum(1 for s in positive_scores if s < threshold) / max(len(positive_scores), 1)
    return ErrorRates(false_positive_rate=fpr, false_negative_rate=fnr)


def evidence_loss(original: Report, edited: Report, key_evidence_ids: Sequence[str]) -> float:
    """Share of key-evidence quotes that redaction changed."""
    keys = set(key_evidence_ids)
    before = {q.log_id: q.quote for q in original.evidence if q.log_id in keys}
    if not before:
        return 0.0
    after = {q.log_id: q.quote for q in edited.evidence}
    changed = sum(1 for log_id, quote in before.items() if after.get(log_id) != quote)
    return changed / len(before)


def redaction_volume(original: Report, edited: Report) -> float:
    """Share of the original report's characters that did not survive editing.

    Measured on words: the characters of original words that no longer appear anywhere in
    the edited text. Working on words keeps the measure independent of marker length.
    """
    before = original.redactable_text().split()
    after = set(edited.redactable_text().split())
    if not before:
        return 0.0
    removed = sum(len(word) for word in before if word not in after)
    return removed / sum(len(word) for word in before)


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with a bootstrap confidence interval."""

    estimate: float
    low: float
    high: float


def bootstrap_interval[T](
    items: Sequence[T],
    statistic: Callable[[Sequence[T]], float | None],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> Interval | None:
    """Percentile bootstrap over `items` (resampled whole, so pairing is preserved).

    Resamples where the statistic is undefined are skipped. Returns None if the statistic is
    undefined on the full sample.
    """
    estimate = statistic(items)
    if estimate is None:
        return None
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(resamples):
        value = statistic([items[rng.randrange(len(items))] for _ in items])
        if value is not None:
            draws.append(value)
    if not draws:
        return Interval(estimate=estimate, low=estimate, high=estimate)
    alpha = (1 - confidence) / 2
    quantiles = statistics.quantiles(draws, n=1000, method="inclusive")
    low = quantiles[max(0, round(alpha * 1000) - 1)]
    high = quantiles[min(len(quantiles) - 1, round((1 - alpha) * 1000) - 1)]
    return Interval(estimate=estimate, low=low, high=high)
