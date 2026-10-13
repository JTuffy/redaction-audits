"""The spec's headline figure: signal persistence against secret leakage, one point per policy.

A good policy sits top left: the finding survives editing and the secrets do not.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt

from redaction.escalation.summary import PolicySummary


def plot_tradeoff(summaries: Sequence[PolicySummary], path: Path) -> Path | None:
    """Write the persistence-vs-leakage plot. Policies missing either number are left out.

    Returns the path written, or None when no policy has both numbers.
    """
    points = [
        (s.policy, s.leakage_mean, s.persistence)
        for s in summaries
        if s.persistence is not None and s.leakage_mean is not None
    ]
    if not points:
        return None
    fig, ax = plt.subplots(figsize=(5, 4))
    for policy, x, y in points:
        ax.errorbar(
            x.estimate,
            y.estimate,
            xerr=[[x.estimate - x.low], [x.high - x.estimate]],
            yerr=[[y.estimate - y.low], [y.high - y.estimate]],
            fmt="o",
            capsize=3,
            label=str(policy),
        )
    ax.set_xlabel("Secret leakage (lower is better)")
    ax.set_ylabel("Signal persistence (higher is better)")
    ax.axhline(1.0, linestyle=":", color="grey", linewidth=1)
    ax.axvline(0.0, linestyle=":", color="grey", linewidth=1)
    ax.grid(visible=True, alpha=0.3)
    ax.legend(loc="lower right", fontsize="small")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
