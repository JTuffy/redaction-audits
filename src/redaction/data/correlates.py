"""Correlates: log lines that reveal a secret without stating its value.

Each secret option maps to one or two operational details a lab's logs would plausibly contain
(a checkpoint size, a node reservation, optimizer hyperparameters, a freeze date). An informed
reader can recover the option from them, and redacting the literal value leaves them in place.
That gap is what P1's leakage measure needs in order to mean "inferable", not just "verbatim".

The mappings are deliberately simple and physically consistent, so a correlate's strength is a
fact about the data rather than a judgment call:
- parameter scale: bf16 checkpoint size is 2 bytes per parameter;
- compute footprint: 8 GPUs per node, and the reservation window in days;
- optimizer, LR schedule, data mix, architecture: hyperparameters or metrics that differ by option;
- names and dates: the partial forms (initials, slugs, domains, freeze dates) redaction misses.
"""

from __future__ import annotations

from typing import Final, NamedTuple

from redaction.core.models import CorrelateStrength, SecretType

_ID, _NARROW = CorrelateStrength.IDENTIFYING, CorrelateStrength.NARROWING


class CorrelateLine(NamedTuple):
    """A log line template carrying a correlate. `snippet` must appear in the filled text."""

    source: str
    template: str
    snippet: str
    strength: CorrelateStrength
    rationale: str


def _slug(text: str) -> str:
    return text.lower().replace("project ", "").replace(" ", "-")


def _initial_surname(name: str) -> str:
    first, last = name.split(" ", 1)
    return f"{first[0].lower()}.{last.lower()}"


_SCALE: Final = {
    "70B": ("140 GB", "tp=8 pp=2"),
    "200B": ("400 GB", "tp=8 pp=4"),
    "400B": ("800 GB", "tp=8 pp=8"),
    "1T": ("2.0 TB", "tp=8 pp=16"),
    "13B": ("26 GB", "tp=2 pp=1"),
    "34B": ("68 GB", "tp=4 pp=1"),
    "120B": ("240 GB", "tp=8 pp=3"),
    "1.5T": ("3.0 TB", "tp=8 pp=24"),
}
_COMPUTE: Final = {
    "2,048 GPUs for 21 days": ("256 nodes", "21d"),
    "4,096 GPUs for 14 days": ("512 nodes", "14d"),
    "8,192 GPUs for 30 days": ("1024 nodes", "30d"),
    "1,024 GPUs for 45 days": ("128 nodes", "45d"),
    "512 GPUs for 60 days": ("64 nodes", "60d"),
    "16,384 GPUs for 10 days": ("2048 nodes", "10d"),
    "3,072 GPUs for 28 days": ("384 nodes", "28d"),
    "6,144 GPUs for 18 days": ("768 nodes", "18d"),
}
_OPTIMIZER: Final = {
    "AdamW": "betas=(0.9,0.95) eps=1e-8 states=2",
    "Muon": "ns_steps=5 momentum=0.95 orthogonalize=true",
    "Adafactor": "factored_second_moment=true relative_step=true states=1",
    "Lion": "betas=(0.9,0.99) sign_update=true states=1",
    "SGD with momentum": "momentum=0.9 nesterov=true states=1",
    "Sophia": "hessian_update_interval=10 rho=0.04 states=2",
    "Shampoo": "preconditioner_update_freq=100 block_size=1024 states=2",
    "AdEMAMix": "betas=(0.9,0.999,0.9999) alpha=5 states=3",
}
_LR: Final = {
    "peak 3e-4 cosine with 2k warmup": ("step 2000 lr=3.0e-04", "decay=cosine"),
    "peak 1e-4 linear with 4k warmup": ("step 4000 lr=1.0e-04", "decay=linear"),
    "peak 6e-4 WSD with 1k warmup": ("step 1000 lr=6.0e-04", "decay=wsd"),
    "peak 2e-4 cosine with 8k warmup": ("step 8000 lr=2.0e-04", "decay=cosine"),
    "peak 5e-4 cosine with 4k warmup": ("step 4000 lr=5.0e-04", "decay=cosine"),
    "peak 8e-4 WSD with 2k warmup": ("step 2000 lr=8.0e-04", "decay=wsd"),
    "peak 1.5e-4 constant with 1k warmup": ("step 1000 lr=1.5e-04", "decay=constant"),
    "peak 4e-4 linear with 500 warmup": ("step 500 lr=4.0e-04", "decay=linear"),
}
_MIX: Final = {
    "42% web / 18% code / 9% synthetic": "code_share=0.18 synthetic_share=0.09",
    "55% web / 12% code / 5% synthetic": "code_share=0.12 synthetic_share=0.05",
    "38% web / 25% code / 15% synthetic": "code_share=0.25 synthetic_share=0.15",
    "60% web / 10% code / 2% synthetic": "code_share=0.10 synthetic_share=0.02",
    "50% web / 20% code / 10% synthetic": "code_share=0.20 synthetic_share=0.10",
    "45% web / 30% code / 4% synthetic": "code_share=0.30 synthetic_share=0.04",
    "65% web / 8% code / 12% synthetic": "code_share=0.08 synthetic_share=0.12",
    "35% web / 15% code / 25% synthetic": "code_share=0.15 synthetic_share=0.25",
}
_ARCH: Final = {
    "dense decoder": "router_metrics=absent moe_layers=0",
    "MoE with 16 experts": "router_aux_loss=0.011 experts_per_layer=16",
    "MoE with 64 experts": "router_aux_loss=0.019 experts_per_layer=64",
    "hybrid attention-SSM": "ssm_state_dim=128 attn_layers=1/6",
    "MoE with 8 experts": "router_aux_loss=0.008 experts_per_layer=8",
    "MoE with 128 experts": "router_aux_loss=0.024 experts_per_layer=128",
    "linear-attention decoder": "attn_kernel=linear moe_layers=0",
    "encoder-decoder": "encoder_layers=24 cross_attn=true",
}
_RELEASE: Final = {
    "week of 2026-11-09": "2026-11-02",
    "week of 2026-12-07": "2026-11-30",
    "week of 2027-01-18": "2027-01-11",
    "week of 2027-02-22": "2027-02-15",
    "week of 2026-10-26": "2026-10-19",
    "week of 2027-03-29": "2027-03-22",
    "week of 2027-04-19": "2027-04-12",
    "week of 2027-05-10": "2027-05-03",
}
_DELIBERATION: Final = {
    "leadership chose to delay the eval to hit the launch window": "eval moved after launch gate",
    "leadership chose to cut eval scope to save compute": "eval suites reduced 12 -> 5",
    "leadership chose to outsource the eval to a contractor": "eval PO raised to external vendor",
    "leadership chose to rerun the eval after a config error": "eval rerun ticket: config fix",
    "leadership chose to waive the eval for a minor version": "eval waiver: minor version",
    "leadership chose to run the eval on a smaller checkpoint": "eval target: smaller ckpt",
    "leadership chose to ship to a limited preview first": "rollout limited to preview cohort",
    "leadership chose to let the safety team sign off after launch": "safety sign-off: post-launch",
}


def correlate_lines(  # noqa: PLR0911  one case per secret type reads best as a match
    secret_type: SecretType, value: str
) -> tuple[CorrelateLine, ...]:
    """The correlate lines for one planted secret. Templates may use `{run}` and `{team}`."""
    match secret_type:
        case SecretType.PARAMETER_SCALE:
            size, parallel = _SCALE[value]
            return (
                CorrelateLine(
                    "ml-infra",
                    f"checkpoint {{run}}/step-48000 saved: {size} bf16 weights",
                    f"{size} bf16 weights",
                    _ID,
                    "bf16 is 2 bytes per parameter",
                ),
                CorrelateLine(
                    "ml-infra",
                    f"{{run}} launcher: {parallel} dp=auto",
                    parallel,
                    _NARROW,
                    "pipeline depth grows with model size",
                ),
            )
        case SecretType.COMPUTE_FOOTPRINT:
            nodes, window = _COMPUTE[value]
            return (
                CorrelateLine(
                    "infra",
                    f"reservation res-{{team}}: {nodes} x 8 GPU, window {window}",
                    f"{nodes} x 8 GPU, window {window}",
                    _ID,
                    "nodes times 8 GPUs, and the window",
                ),
            )
        case SecretType.OPTIMIZER:
            return (
                CorrelateLine(
                    "ml-infra",
                    f"{{run}} optim config: {_OPTIMIZER[value]}",
                    _OPTIMIZER[value],
                    _ID,
                    "hyperparameters specific to one optimizer",
                ),
            )
        case SecretType.LR_SCHEDULE:
            peak, decay = _LR[value]
            return (
                CorrelateLine(
                    "ml-infra",
                    f"{{run}} scheduler: warmup done at {peak}, {decay}",
                    f"{peak}, {decay}",
                    _ID,
                    "warmup length, peak and decay shape",
                ),
            )
        case SecretType.DATA_MIX:
            return (
                CorrelateLine(
                    "data-eng",
                    f"batch sampler audit {{run}}: {_MIX[value]}",
                    _MIX[value],
                    _NARROW,
                    "two of the three shares; web is implied",
                ),
            )
        case SecretType.ARCHITECTURE:
            return (
                CorrelateLine(
                    "monitoring",
                    f"{{run}} health: {_ARCH[value]}",
                    _ARCH[value],
                    _ID,
                    "router or SSM metrics exist only for one design",
                ),
            )
        case SecretType.RELEASE_DATE:
            freeze = _RELEASE[value]
            return (
                CorrelateLine(
                    "pm",
                    f"code freeze for the release branch set to {freeze}",
                    f"set to {freeze}",
                    _NARROW,
                    "launches follow freeze by a week",
                ),
            )
        case SecretType.DELIBERATION:
            return (
                CorrelateLine(
                    "exec",
                    f"action item: {_DELIBERATION[value]}",
                    _DELIBERATION[value],
                    _NARROW,
                    "the action reveals the decision",
                ),
            )
        case SecretType.CODENAME:
            slug = _slug(value)
            return (
                CorrelateLine(
                    "ml-infra",
                    f"job name {slug}-rl-ft-{{run}} queued",
                    f"{slug}-rl-ft",
                    _ID,
                    "job names embed the codename in lowercase",
                ),
            )
        case SecretType.CUSTOMER_NAME:
            tenant = "-".join(w[:3].lower() for w in value.split()[:2])
            return (
                CorrelateLine(
                    "sales",
                    f"tenant {tenant} usage export attached to ticket",
                    f"tenant {tenant}",
                    _NARROW,
                    "tenant ids abbreviate the customer",
                ),
            )
        case SecretType.EMPLOYEE_NAME:
            handle = _initial_surname(value)
            return (
                CorrelateLine(
                    "ops",
                    f"approved-by: {handle}",
                    handle,
                    _ID,
                    "handles are first initial and surname",
                ),
            )
        case SecretType.DATA_VENDOR:
            domain = value.split(maxsplit=1)[0].lower() + "-data.com"
            return (
                CorrelateLine(
                    "legal",
                    f"bucket sync from sftp.{domain} completed",
                    domain,
                    _ID,
                    "the vendor's delivery domain",
                ),
            )
