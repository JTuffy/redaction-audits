"""Result figures: the numbers they plot, and that every kind renders."""

from __future__ import annotations

import json
from pathlib import Path

from redaction.paper.figures import auroc, build_figures, entangled, tradeoff_points


def test_auroc_and_set_detection() -> None:
    assert auroc([90, 80], [10, 20]) == 1.0
    assert auroc([50], [50]) == 0.5
    assert entangled({"scenario_id": "dev-e012-cot_in_training-violation"})
    assert not entangled({"scenario_id": "dev-012-cot_in_training-violation"})


def _secret(p_edited: float) -> dict[str, float]:
    return {"p_prior": 0.125, "p_unedited": 1.0, "p_edited": p_edited}


def _p1_rows() -> list[dict[str, object]]:
    rows = []
    for k, sid in enumerate(["dev-001-x-violation", "dev-e001-x-violation"]):
        for label, unedited, edited in (("violation", 95, 90 - 40 * k), ("clean", 5, 10 + 70 * k)):
            rows.append(
                {
                    "scenario_id": sid
                    if label == "violation"
                    else sid.replace("violation", "clean"),
                    "policy": "text_redaction",
                    "label": label,
                    "judge_unedited": unedited,
                    "judge_edited": edited,
                    "secrets": [_secret(1.0)],
                }
            )
    return rows


def test_tradeoff_points_split_by_set() -> None:
    points = tradeoff_points(_p1_rows())
    assert points[("text_redaction", False)] == (1.0, 1.0)
    assert points[("text_redaction", True)][1] < 0  # the entangled case flips the ranking


def test_every_kind_renders(tmp_path: Path) -> None:
    runs, paper = tmp_path / "runs", tmp_path / "paper"
    (runs / "abl").mkdir(parents=True)
    (runs / "p1").mkdir()
    ablation = [
        {
            "scenario_id": f"dev-{p}001-{t}-{lab}",
            "violation_type": t,
            "label": lab,
            "difficulty": "hard" if lab == "red_herring" else None,
            "condition": c,
            "score": s,
        }
        for p in ("", "e")
        for t in ("classifier_off", "skipped_eval")
        for lab, s in (("violation", 90), ("red_herring", 20))
        for c in ("unedited", "marker", "pseudonym")
    ]
    (runs / "abl" / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in ablation))
    (runs / "p1" / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in _p1_rows()))
    paper.mkdir()
    (paper / "figures.toml").write_text(
        "\n".join(
            f'[[figure]]\nid = "{k}"\nkind = "{k}"\ntitle = "t"\ncaption = "c"\nruns = ["{r}"]\n'
            for k, r in (("auroc_by_condition", "abl"), ("link_types", "abl"), ("tradeoff", "p1"))
        )
    )
    made = build_figures(paper, runs)
    assert [m["id"] for m in made] == ["auroc_by_condition", "link_types", "tradeoff"]
    for m in made:
        assert (paper / "figures" / f"{m['id']}.pdf").is_file()
        assert (paper / "figures" / f"{m['id']}-dark.svg").is_file()
