"""Running findings: per-run rows, pooled measures and set tagging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from redaction.viewer.results import measure_value, metric, questions, results_table, set_of


def _sample(
    sid: str, label: str, unedited: float, edited: float, **extra: object
) -> dict[str, Any]:
    return {
        "scenario_id": sid,
        "policy": "text_redaction",
        "label": label,
        "judge_unedited": unedited,
        "judge_edited": edited,
        "secrets": [{"p_prior": 0.1, "p_unedited": 0.9, "p_edited": 0.5}],
        **extra,
    }


def _run(
    tmp: Path, name: str, stance: str, samples: list[dict[str, Any]], build: str = "abc"
) -> None:
    folder = tmp / name
    folder.mkdir()
    record = {
        "name": name,
        "recorded_at": "2026-10-23T00:00:00+00:00",
        "config": {
            "split": "dev",
            "stance": stance,
            "data": f"built:{build}",
            "models": {"judge": "j"},
        },
    }
    (folder / "run.json").write_text(json.dumps(record), encoding="utf-8")
    (folder / "samples.jsonl").write_text(
        "\n".join(json.dumps(s) for s in samples), encoding="utf-8"
    )


SAMPLES = [
    _sample("dev-e001-x-violation", "violation", 90, 80),
    _sample("dev-e002-x-red_herring", "red_herring", 10, 60),
    _sample("dev-001-x-violation", "violation", 90, 90),
    _sample("dev-002-x-red_herring", "red_herring", 10, 10),
]


def test_set_of_reads_prefix_or_build_depth() -> None:
    assert set_of("dev-e012-a-violation") == "entangled"
    assert set_of("dev-012-a-violation") == "disjoint"
    assert set_of("dev-012-a-violation", "entangled") == "entangled"


def test_metrics() -> None:
    assert metric("persistence", SAMPLES[2:]) == 1.0
    assert metric("leakage", SAMPLES[:1]) == 0.5
    assert metric("fpr", SAMPLES[:2]) == 1.0


def test_rows_and_pooling(tmp_path: Path) -> None:
    _run(tmp_path, "p1-dev-honest-20261023T000000Z", "honest", SAMPLES)
    _run(tmp_path, "p1-dev-honest-20261024T000000Z", "honest", SAMPLES)
    from redaction.viewer.results import load_runs  # noqa: PLC0415

    runs = load_runs(tmp_path)
    rows = results_table(runs)
    assert {(r["set"], r["n"]) for r in rows} == {("entangled", 2), ("disjoint", 2)}
    m = measure_value(
        {
            "metric": "persistence",
            "policy": "text_redaction",
            "stance": "honest",
            "set": "disjoint",
        },
        runs,
    )
    assert m["value"] == 1.0
    assert m["n"] == 4
    assert len(m["trend"]) == 2
    other = measure_value(
        {"metric": "persistence", "policy": "text_redaction", "stance": "red_team"}, runs
    )
    assert other["value"] is None


def test_questions_use_pooling_defaults(tmp_path: Path) -> None:
    _run(tmp_path, "p1-dev-honest-20261023T000000Z", "honest", SAMPLES)
    direction = {
        "pooling": {"judge": "other"},
        "question": [{"id": "Q", "measure": [{"metric": "fnr", "policy": "text_redaction"}]}],
    }
    assert questions(direction, tmp_path)[0]["measure"][0]["n"] == 0


def test_ruling_shares() -> None:
    samples = [
        {"rulings": [{"decision": "grant"}, {"decision": "modify"}]},
        {"rulings": [{"decision": "modify"}, {"decision": "deny"}]},
    ]
    assert metric("as_asked", samples) == 0.25
    assert metric("rewritten", samples) == 0.5
    assert metric("denied", samples) == 0.25
    assert metric("denied", [{"rulings": []}]) is None


def test_cluster_bootstrap_is_wider_than_scenario_bootstrap() -> None:
    from redaction.viewer.results import _interval  # noqa: PLC0415

    # Two skeletons, each repeated 10 times: one separates perfectly, one not at all.
    good = [_sample(f"dev-{i:03d}-x-v", "violation", 90, 90) for i in range(10)]
    good += [_sample(f"dev-{i:03d}-x-r", "red_herring", 10, 10) for i in range(10)]
    bad = [_sample(f"dev-{i:03d}-y-v", "violation", 90, 40) for i in range(10)]
    bad += [_sample(f"dev-{i:03d}-y-r", "red_herring", 10, 60) for i in range(10)]
    for s in good:
        s["cluster"] = "good-" + s["label"]
    for s in bad:
        s["cluster"] = "bad-" + s["label"]
    clustered = _interval("persistence", good + bad)
    loose = _interval("persistence", [{**s, "cluster": None} for s in good + bad])
    assert clustered is not None
    assert loose is not None
    assert clustered[1] - clustered[0] > loose[1] - loose[0]
