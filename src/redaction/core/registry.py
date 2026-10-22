"""The shared secret registry used by both proposals.

Each secret type has a tier (how the policies treat it), a sensitivity (how leakage is
weighted) and eight realistic options, exactly one of which is planted in a given scenario.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from pydantic import Field, model_validator

from redaction.core.models import Frozen, SecretTier, SecretType, Sensitivity

OPTIONS_PER_SECRET: Final = 8  # widened from 4 on 22 Oct: one-of-four was too easy to recover

SENSITIVITY_WEIGHT: Final = MappingProxyType(
    {Sensitivity.LOW: 1.0, Sensitivity.MEDIUM: 2.0, Sensitivity.HIGH: 3.0}
)


class SecretSpec(Frozen):
    """Registry entry for one secret type."""

    secret_type: SecretType
    label: str
    tier: SecretTier
    sensitivity: Sensitivity
    options: tuple[str, ...] = Field(min_length=OPTIONS_PER_SECRET, max_length=OPTIONS_PER_SECRET)

    @model_validator(mode="after")
    def _options_are_distinct(self) -> SecretSpec:
        if len(set(self.options)) != len(self.options):
            msg = f"duplicate options for {self.secret_type}"
            raise ValueError(msg)
        return self

    @property
    def weight(self) -> float:
        """Weight of this secret type when averaging leakage."""
        return SENSITIVITY_WEIGHT[self.sensitivity]


def _spec(
    secret_type: SecretType,
    label: str,
    tier: SecretTier,
    sensitivity: Sensitivity,
    *options: str,
) -> SecretSpec:
    return SecretSpec(
        secret_type=secret_type, label=label, tier=tier, sensitivity=sensitivity, options=options
    )


_ALWAYS, _CONTEXT = SecretTier.ALWAYS_REDACT, SecretTier.CONTEXT
_LOW, _MED, _HIGH = Sensitivity.LOW, Sensitivity.MEDIUM, Sensitivity.HIGH

REGISTRY: Final = MappingProxyType(
    {
        spec.secret_type: spec
        for spec in (
            _spec(
                SecretType.LR_SCHEDULE,
                "learning-rate schedule",
                _ALWAYS,
                _HIGH,
                "peak 3e-4 cosine with 2k warmup",
                "peak 1e-4 linear with 4k warmup",
                "peak 6e-4 WSD with 1k warmup",
                "peak 2e-4 cosine with 8k warmup",
                "peak 5e-4 cosine with 4k warmup",
                "peak 8e-4 WSD with 2k warmup",
                "peak 1.5e-4 constant with 1k warmup",
                "peak 4e-4 linear with 500 warmup",
            ),
            _spec(
                SecretType.DATA_MIX,
                "data mix",
                _ALWAYS,
                _HIGH,
                "42% web / 18% code / 9% synthetic",
                "55% web / 12% code / 5% synthetic",
                "38% web / 25% code / 15% synthetic",
                "60% web / 10% code / 2% synthetic",
                "50% web / 20% code / 10% synthetic",
                "45% web / 30% code / 4% synthetic",
                "65% web / 8% code / 12% synthetic",
                "35% web / 15% code / 25% synthetic",
            ),
            _spec(
                SecretType.CUSTOMER_NAME,
                "customer name",
                _ALWAYS,
                _HIGH,
                "Halvorsen Logistics",
                "Brightwater Health",
                "Corvane Capital",
                "Tessaly Retail Group",
                "Marrowind Freight",
                "Oakhaven Insurance",
                "Pellucid Biotech",
                "Sundial Energy",
            ),
            _spec(
                SecretType.EMPLOYEE_NAME,
                "employee name",
                _ALWAYS,
                _MED,
                "Priya Raman",
                "Marcus Ellery",
                "Dana Okafor",
                "Lukas Brandt",
                "Elena Vasquez",
                "Ravi Sundaram",
                "Grace Achterberg",
                "Samuel Oyelaran",
            ),
            _spec(
                SecretType.OPTIMIZER,
                "optimizer",
                _CONTEXT,
                _MED,
                "AdamW",
                "Muon",
                "Adafactor",
                "Lion",
                "SGD with momentum",
                "Sophia",
                "Shampoo",
                "AdEMAMix",
            ),
            _spec(
                SecretType.PARAMETER_SCALE,
                "parameter scale",
                _CONTEXT,
                _HIGH,
                "70B",
                "200B",
                "400B",
                "1T",
                "13B",
                "34B",
                "120B",
                "1.5T",
            ),
            _spec(
                SecretType.ARCHITECTURE,
                "architecture",
                _CONTEXT,
                _HIGH,
                "dense decoder",
                "MoE with 16 experts",
                "MoE with 64 experts",
                "hybrid attention-SSM",
                "MoE with 8 experts",
                "MoE with 128 experts",
                "linear-attention decoder",
                "encoder-decoder",
            ),
            _spec(
                SecretType.DATA_VENDOR,
                "data vendor",
                _CONTEXT,
                _MED,
                "Lexora Data",
                "Quillstone Corpora",
                "Northbank Licensing",
                "Ferrite Media",
                "Corvid Archives",
                "Halyard Text",
                "Brinewood Press",
                "Tallis Datasets",
            ),
            _spec(
                SecretType.CODENAME,
                "internal codename",
                _CONTEXT,
                _LOW,
                "Project Kestrel",
                "Project Basalt",
                "Project Lumen",
                "Project Tamarack",
                "Project Heron",
                "Project Cinder",
                "Project Juniper",
                "Project Quartz",
            ),
            _spec(
                SecretType.DELIBERATION,
                "internal deliberation",
                _CONTEXT,
                _MED,
                "leadership chose to delay the eval to hit the launch window",
                "leadership chose to cut eval scope to save compute",
                "leadership chose to outsource the eval to a contractor",
                "leadership chose to rerun the eval after a config error",
                "leadership chose to waive the eval for a minor version",
                "leadership chose to run the eval on a smaller checkpoint",
                "leadership chose to ship to a limited preview first",
                "leadership chose to let the safety team sign off after launch",
            ),
            _spec(
                SecretType.COMPUTE_FOOTPRINT,
                "compute footprint",
                _CONTEXT,
                _LOW,
                "2,048 GPUs for 21 days",
                "4,096 GPUs for 14 days",
                "8,192 GPUs for 30 days",
                "1,024 GPUs for 45 days",
                "512 GPUs for 60 days",
                "16,384 GPUs for 10 days",
                "3,072 GPUs for 28 days",
                "6,144 GPUs for 18 days",
            ),
            _spec(
                SecretType.RELEASE_DATE,
                "release date",
                _CONTEXT,
                _MED,
                "week of 2026-11-09",
                "week of 2026-12-07",
                "week of 2027-01-18",
                "week of 2027-02-22",
                "week of 2026-10-26",
                "week of 2027-03-29",
                "week of 2027-04-19",
                "week of 2027-05-10",
            ),
        )
    }
)


def spec_for(secret_type: SecretType) -> SecretSpec:
    """Return the registry entry for a secret type."""
    return REGISTRY[secret_type]


def redaction_marker(secret_type: SecretType) -> str:
    """The marker that replaces a removed value of this secret type."""
    return f"[REDACTED: {spec_for(secret_type).label}]"
