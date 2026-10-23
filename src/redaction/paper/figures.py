"""Result figures for the paper and the site, drawn from committed run records only.

Each figure in `paper/figures.toml` names the runs it uses, so a figure always matches the
ledger. Output: `<id>.pdf` for LaTeX and `<id>-light.svg` / `<id>-dark.svg` for the site.
Colors follow the data-viz reference palette (categorical slots 1-3 only, which validate
all-pairs in both modes); identity is never color alone (shapes, direct labels).
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from redaction.infra.log_setup import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Theme:
    """Surface, ink and the three series colors for one mode."""

    surface: str
    ink: str
    muted: str
    grid: str
    series: tuple[str, str, str]


THEMES: Final = {
    "light": Theme("#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", ("#2a78d6", "#eb6834", "#1baf7a")),
    "dark": Theme("#1a1a19", "#f0efec", "#c3c2b7", "#33322f", ("#3987e5", "#d95926", "#199e70")),
}
CONDITIONS: Final = (("unedited", "Unedited"), ("marker", "Markers"), ("pseudonym", "Pseudonyms"))
IDENTITY: Final = ("classifier_off", "cot_in_training", "opted_out_data", "monitoring_off")
MAGNITUDE: Final = ("unreported_compute", "skipped_eval")
POLICY_NAMES: Final = {
    "text_redaction": "Text redaction",
    "text_pseudonym": "Text pseudonyms",
    "text_generalize": "Text generalize",
    "contextual_rewrite": "Contextual rewrite",
    "self_redaction": "Self-redaction",
}


def _samples(runs_dir: Path, name: str) -> list[dict[str, Any]]:
    path = runs_dir / name / "samples.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def entangled(sample: dict[str, Any]) -> bool:
    """Entangled scenario IDs carry an `e` before the index (dev-e012-...)."""
    return str(sample["scenario_id"]).split("-")[1].startswith("e")


def auroc(pos: Iterable[float], neg: Iterable[float]) -> float:
    """Probability a random violation outscores a random non-violation (ties count half)."""
    p, n = list(pos), list(neg)
    if not p or not n:
        return float("nan")
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in p for b in n)
    return wins / (len(p) * len(n))


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def _style(ax: Axes, theme: Theme) -> None:
    ax.set_facecolor(theme.surface)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme.grid)
    ax.tick_params(colors=theme.muted, labelsize=9, length=0)
    ax.grid(axis="x", color=theme.grid, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(theme: Theme, size: tuple[float, float]) -> Figure:
    fig = plt.figure(figsize=size, dpi=150, facecolor=theme.surface)
    fig.patch.set_facecolor(theme.surface)
    return fig


def auroc_by_condition(runs_dir: Path, runs: list[str], theme: Theme) -> Figure:
    """Dot plot: AUROC per display condition, disjoint against entangled."""
    per_run: dict[tuple[bool, str], list[float]] = {
        (st, c): [] for st in (False, True) for c, _ in CONDITIONS
    }
    for name in runs:
        rows = _samples(runs_dir, name)
        for st in (False, True):
            for c, _ in CONDITIONS:
                xs = [s for s in rows if s["condition"] == c and entangled(s) == st]
                pos = [s["score"] for s in xs if s["label"] == "violation"]
                neg = [s["score"] for s in xs if s["label"] != "violation"]
                per_run[(st, c)].append(auroc(pos, neg))
    fig = _figure(theme, (6.4, 2.6))
    ax = fig.add_subplot(1, 1, 1)
    _style(ax, theme)
    sets = ((False, "Disjoint", theme.series[0], "o"), (True, "Entangled", theme.series[1], "s"))
    for row, (cond, _) in enumerate(CONDITIONS):
        for k, (st, name, color, marker) in enumerate(sets):
            y = row + (k - 0.5) * 0.28
            vals = per_run[(st, cond)]
            ax.scatter(vals, [y] * len(vals), s=14, color=color, alpha=0.45, marker=marker, lw=0)
            m = _mean(vals)
            ax.scatter([m], [y], s=70, color=color, marker=marker, edgecolors=theme.surface, lw=2)
            ax.annotate(
                f"{m:.2f}",
                (m, y),
                xytext=(8, 0),
                textcoords="offset points",
                va="center",
                fontsize=8.5,
                color=theme.ink,
            )
            if row == 0:
                ax.annotate(
                    name,
                    (0.5, y),
                    xytext=(4, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8.5,
                    color=theme.muted,
                )
    ax.set_yticks(range(len(CONDITIONS)), [label for _, label in CONDITIONS], color=theme.ink)
    ax.invert_yaxis()
    ax.set_xlim(0.5, 1.04)
    ax.set_xlabel("AUROC (0.5 = chance)", color=theme.muted, fontsize=9)
    fig.tight_layout()
    return fig


def link_types(runs_dir: Path, runs: list[str], theme: Theme) -> Figure:
    """Two panels (violations, hard red herrings): mean score per entangled type and condition."""
    rows = [s for name in runs for s in _samples(runs_dir, name) if entangled(s)]
    types = (*IDENTITY, *MAGNITUDE)
    fig = _figure(theme, (7.2, 3.4))
    panels = (
        ("violation", None, "Violations (should stay high)"),
        ("red_herring", "hard", "Hard red herrings (should stay low)"),
    )
    shapes = ("o", "s", "D")
    for p, (label, difficulty, title) in enumerate(panels):
        ax = fig.add_subplot(1, 2, p + 1)
        _style(ax, theme)
        for row, t in enumerate(types):
            y = row + (0.6 if t in MAGNITUDE else 0)
            points = []
            for cond, _ in CONDITIONS:
                xs = [
                    s["score"]
                    for s in rows
                    if s["violation_type"] == t
                    and s["label"] == label
                    and s["difficulty"] == difficulty
                    and s["condition"] == cond
                ]
                points.append(_mean(xs))
            ax.plot([min(points), max(points)], [y, y], color=theme.grid, lw=2, zorder=1)
            for k, x in enumerate(points):
                ax.scatter(
                    [x],
                    [y],
                    s=46,
                    color=theme.series[k],
                    marker=shapes[k],
                    edgecolors=theme.surface,
                    lw=1.5,
                    zorder=3,
                )
        ticks = [row + (0.6 if t in MAGNITUDE else 0) for row, t in enumerate(types)]
        ax.set_yticks(
            ticks,
            [t.replace("_", " ") for t in types] if p == 0 else [""] * len(types),
            color=theme.ink,
            fontsize=8.5,
        )
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_title(title, color=theme.ink, fontsize=9.5, loc="left")
        ax.set_xlabel("mean judge score", color=theme.muted, fontsize=9)
    handles = [
        Line2D([], [], ls="", marker=shapes[k], color=theme.series[k], markersize=7, label=name)
        for k, (_, name) in enumerate(CONDITIONS)
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=8.5,
        labelcolor=theme.ink,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return fig


def _leak(sample: dict[str, Any]) -> list[float]:
    out = []
    for x in sample["secrets"]:
        lift = x["p_unedited"] - x["p_prior"]
        if lift > 0.05:  # noqa: PLR2004 - secrets the unedited evidence barely reveals are skipped
            out.append(min(1.0, max(0.0, (x["p_edited"] - x["p_prior"]) / lift)))
    return out


def tradeoff_points(rows: list[dict[str, Any]]) -> dict[tuple[str, bool], tuple[float, float]]:
    """(policy, entangled) -> (leakage, persistence), recomputed from per-sample records."""
    out = {}
    for policy in POLICY_NAMES:
        for st in (False, True):
            xs = [s for s in rows if s["policy"] == policy and entangled(s) == st]
            if not xs:
                continue
            au = auroc(
                [s["judge_unedited"] for s in xs if s["label"] == "violation"],
                [s["judge_unedited"] for s in xs if s["label"] != "violation"],
            )
            ae = auroc(
                [s["judge_edited"] for s in xs if s["label"] == "violation"],
                [s["judge_edited"] for s in xs if s["label"] != "violation"],
            )
            persistence = (ae - 0.5) / (au - 0.5) if au > 0.5 else float("nan")  # noqa: PLR2004
            out[(policy, st)] = (_mean(v for s in xs for v in _leak(s)), persistence)
    return out


def tradeoff(runs_dir: Path, runs: list[str], theme: Theme) -> Figure:
    """Persistence against leakage per policy; an arrow from disjoint to entangled."""
    rows = [s for name in runs for s in _samples(runs_dir, name)]
    points = tradeoff_points(rows)
    fig = _figure(theme, (6.4, 3.6))
    ax = fig.add_subplot(1, 1, 1)
    _style(ax, theme)
    ax.grid(axis="y", color=theme.grid, linewidth=0.8)
    color = theme.series[0]
    for policy, name in POLICY_NAMES.items():
        if (policy, False) not in points or (policy, True) not in points:
            continue
        (x0, y0), (x1, y1) = points[(policy, False)], points[(policy, True)]
        ax.annotate(
            "", (x1, y1), (x0, y0), arrowprops={"arrowstyle": "->", "color": theme.muted, "lw": 1}
        )
        ax.scatter([x0], [y0], s=46, facecolors=theme.surface, edgecolors=color, lw=1.8, zorder=3)
        ax.scatter([x1], [y1], s=46, color=color, edgecolors=theme.surface, lw=1.5, zorder=3)
        ax.annotate(
            name,
            (x1, y1),
            xytext=(7, -3),
            textcoords="offset points",
            fontsize=8.5,
            color=theme.ink,
        )
    ax.set_xlim(0, 1)
    ax.set_ylim(0.4, 1.25)
    ax.axhline(1.0, color=theme.muted, lw=0.8, ls=":")
    ax.set_xlabel(
        "leakage (0 = nothing inferred, 1 = as much as unedited)", color=theme.muted, fontsize=9
    )
    ax.set_ylabel("persistence (1 = all signal kept)", color=theme.muted, fontsize=9)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(theme.grid)
    handles = [
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            markerfacecolor=theme.surface,
            markeredgecolor=color,
            markersize=7,
            label="disjoint",
        ),
        Line2D([], [], ls="", marker="o", color=color, markersize=7, label="entangled"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=8.5, labelcolor=theme.ink, loc="lower left")
    fig.tight_layout()
    return fig


KINDS: Final = {
    "auroc_by_condition": auroc_by_condition,
    "link_types": link_types,
    "tradeoff": tradeoff,
}


def build_figures(paper_dir: Path, runs_dir: Path) -> list[dict[str, str]]:
    """Draw every figure in figures.toml; return their ids, titles and captions."""
    spec = tomllib.loads((paper_dir / "figures.toml").read_text(encoding="utf-8"))
    out_dir = paper_dir / "figures"
    out_dir.mkdir(exist_ok=True)
    made = []
    for fig_spec in spec.get("figure", []):
        draw = KINDS[fig_spec["kind"]]
        for mode, theme in THEMES.items():
            fig = draw(runs_dir, fig_spec["runs"], theme)
            fig.savefig(out_dir / f"{fig_spec['id']}-{mode}.svg", facecolor=theme.surface)
            if mode == "light":
                fig.savefig(out_dir / f"{fig_spec['id']}.pdf", facecolor=theme.surface)
            plt.close(fig)
        made.append({k: fig_spec[k] for k in ("id", "title", "caption")})
        log.info("figure_written", figure=fig_spec["id"])
    (out_dir / "figures.json").write_text(json.dumps(made, indent=1), encoding="utf-8")
    return made
