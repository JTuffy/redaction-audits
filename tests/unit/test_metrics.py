from __future__ import annotations

from collections.abc import Sequence

import pytest

from redaction.core.metrics import (
    auroc,
    bootstrap_interval,
    error_rates,
    leakage,
    signal_persistence,
    tail_share,
    verbatim_leak_rate,
    weighted_mean,
)


class TestAuroc:
    def test_perfect_separation(self) -> None:
        assert auroc([90, 80], [10, 20]) == 1.0

    def test_reversed_separation(self) -> None:
        assert auroc([10], [90]) == 0.0

    def test_ties_count_half(self) -> None:
        assert auroc([50], [50]) == 0.5

    def test_mixed(self) -> None:
        assert auroc([60, 40], [50]) == 0.5

    def test_empty_side_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            auroc([], [1.0])


class TestPersistence:
    def test_full_and_none(self) -> None:
        assert signal_persistence(0.9, 0.9) == pytest.approx(1.0)
        assert signal_persistence(0.5, 0.9) == pytest.approx(0.0)

    def test_undefined_without_signal(self) -> None:
        assert signal_persistence(0.7, 0.5) is None


class TestLeakage:
    def test_halfway(self) -> None:
        assert leakage(p_edited=0.5, p_unedited=0.75, p_prior=0.25) == pytest.approx(0.5)

    @pytest.mark.parametrize(("p_edited", "expected"), [(0.1, 0.0), (0.95, 1.0)])
    def test_clipped(self, p_edited: float, expected: float) -> None:
        assert leakage(p_edited=p_edited, p_unedited=0.75, p_prior=0.25) == expected

    def test_undefined_when_report_adds_nothing(self) -> None:
        assert leakage(p_edited=0.3, p_unedited=0.25, p_prior=0.25) is None


def test_tail_share() -> None:
    assert tail_share([0.9, 0.8, 0.1, 1.0]) == 0.5
    assert tail_share([]) == 0.0


def test_weighted_mean() -> None:
    assert weighted_mean([1.0, 0.0], [3.0, 1.0]) == 0.75
    with pytest.raises(ValueError, match="same length"):
        weighted_mean([1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="positive"):
        weighted_mean([1.0], [0.0])


def test_verbatim_leak_rate_is_case_insensitive() -> None:
    assert verbatim_leak_rate("trained with MUON on 70B", ["Muon", "AdamW"]) == 0.5
    assert verbatim_leak_rate("anything", []) == 0.0


def test_error_rates_flag_at_threshold() -> None:
    rates = error_rates([50, 40], [50, 10], threshold=50)
    assert rates.false_positive_rate == 0.5
    assert rates.false_negative_rate == 0.5


class TestBootstrap:
    def test_deterministic_and_brackets_estimate(self) -> None:
        items = [float(i) for i in range(20)]

        def mean(xs: Sequence[float]) -> float:
            return sum(xs) / len(xs)

        first = bootstrap_interval(items, mean, resamples=300, seed=1)
        second = bootstrap_interval(items, mean, resamples=300, seed=1)
        assert first == second
        assert first is not None
        assert first.low <= first.estimate <= first.high

    def test_undefined_statistic(self) -> None:
        assert bootstrap_interval([1.0], lambda _: None) is None
