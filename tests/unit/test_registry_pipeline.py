"""The widened registry, its correlates, and the pipeline's paraphrase mode."""

from __future__ import annotations

from collections import Counter

from redaction.core.models import CorrelateStrength, SecretType, Split
from redaction.core.registry import OPTIONS_PER_SECRET, REGISTRY
from redaction.data.correlates import correlate_lines
from redaction.data.generator import DEFAULT_SEEDS, SPLIT_SIZES, slots
from redaction.data.pipeline.plan import LineKind, plan_scenario, required_for


def test_every_secret_has_eight_options_and_correlates_for_each() -> None:
    for secret_type, spec in REGISTRY.items():
        assert len(spec.options) == OPTIONS_PER_SECRET == 8
        for option in spec.options:
            lines = correlate_lines(secret_type, option)
            assert lines, (secret_type, option)
            for line in lines:
                assert (
                    line.snippet
                    in line.template.replace("{run}", "run-1").replace("{team}", "atlas")
                    or line.snippet in line.template
                )


def test_identifying_correlates_point_at_one_option() -> None:
    for secret_type, spec in REGISTRY.items():
        snippets = Counter(
            line.snippet
            for option in spec.options
            for line in correlate_lines(secret_type, option)
            if line.strength is CorrelateStrength.IDENTIFYING
        )
        assert all(n == 1 for n in snippets.values()), (secret_type, snippets)


def test_no_option_contains_another() -> None:
    for spec in REGISTRY.values():
        for a in spec.options:
            for b in spec.options:
                assert a == b or a not in b, (spec.secret_type, a, b)


def test_paraphrase_relaxes_only_evidence_cues() -> None:
    slot = slots(SPLIT_SIZES[Split.DEV])[0]
    plan = plan_scenario(slot, split=Split.DEV, index=0, seed=DEFAULT_SEEDS[Split.DEV], jobs=())
    values = {s.value for s in plan.secrets}
    for line in plan.lines:
        relaxed = required_for(line, paraphrase=True)
        if line.kind is LineKind.EVIDENCE:
            assert set(relaxed) <= values
        else:
            assert relaxed == line.required
    assert any(
        required_for(line, paraphrase=True) != line.required
        for line in plan.lines
        if line.kind is LineKind.EVIDENCE
    )


def test_secret_types_all_registered() -> None:
    assert set(REGISTRY) == set(SecretType)
