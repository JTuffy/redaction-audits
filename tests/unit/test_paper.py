"""Generated paper tables and the section outline."""

from __future__ import annotations

import json
from pathlib import Path

from redaction.paper.build import _macro, builds_table, outline, write_generated


def _manifest(root: Path, split: str, version: str) -> None:
    folder = root / split / version
    folder.mkdir(parents=True)
    (root / split / "LATEST").write_text(version + "\n", encoding="utf-8")
    manifest = {
        "version": version,
        "renderer": "anthropic/claude-sonnet-5-5>openai/gpt-5.6",
        "cues": "paraphrase",
        "stages": {"planned": 40, "kept": 39},
        "labels": {"violation": 11, "red_herring": 18, "clean": 10},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_macro_names_are_letters_only() -> None:
    assert _macro("leakage", "text_redaction") == "LeakageTextRedaction"
    assert _macro("AurocEdited", "self_redaction") == "AurocEditedSelfRedaction"


def test_builds_table_has_a_row_per_split(tmp_path: Path) -> None:
    _manifest(tmp_path, "dev", "abc123")
    table = builds_table(tmp_path)
    assert "dev & \\texttt{abc123}" in table
    assert "39/40 & 11 & 18 & 10" in table
    assert "val" not in table.split("\\midrule")[1]


def test_generated_files_without_runs(tmp_path: Path) -> None:
    built, ledger, paper = tmp_path / "built", tmp_path / "runs", tmp_path / "paper"
    _manifest(built, "val", "v1")
    names = {p.name for p in write_generated(paper, built_dir=built, ledger_dir=ledger)}
    assert names == {"builds.tex", "p1_pilot.tex", "numbers.tex", "figures.tex"}
    assert "No recorded P1 run" in (paper / "generated" / "p1_pilot.tex").read_text()


def test_generated_p1_macros(tmp_path: Path) -> None:
    ledger = tmp_path / "runs"
    (ledger / "p1-x").mkdir(parents=True)
    (ledger / "ledger.jsonl").write_text(json.dumps({"name": "p1-x", "kind": "p1"}) + "\n")
    summary = [
        {
            "policy": "text_redaction",
            "samples": 12,
            "auroc_edited": 0.9,
            "persistence": {"estimate": 0.8},
            "leakage_mean": {"estimate": 0.857, "low": 0.76, "high": 0.93},
            "evidence_loss": 0.5,
        }
    ]
    (ledger / "p1-x" / "summary.json").write_text(json.dumps(summary))
    write_generated(tmp_path / "paper", built_dir=tmp_path / "built", ledger_dir=ledger)
    numbers = (tmp_path / "paper" / "generated" / "numbers.tex").read_text()
    assert "\\newcommand{\\LeakageTextRedaction}{0.86}" in numbers


def test_outline_counts_prose_not_comments(tmp_path: Path) -> None:
    (tmp_path / "sections").mkdir()
    (tmp_path / "main.tex").write_text("\\input{sections/intro}\n\\input{sections/missing}\n")
    (tmp_path / "sections" / "intro.tex").write_text(
        "\\section{Introduction}\\label{sec:intro}\n% a comment with words\n"
        "Auditors need \\emph{evidence} here.\\todo{cite}\n"
    )
    assert outline(tmp_path) == [
        {"file": "sections/intro.tex", "title": "Introduction", "words": 4}
    ]
