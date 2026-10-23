"""The public profile scrubs names and private lines, and its lint catches what's left."""

from __future__ import annotations

from pathlib import Path

from redaction.viewer.public import lint_site, lint_text, scrub, scrub_text


def test_scrub_replaces_names_and_drops_private_lines() -> None:
    text = "Josh asked.\nCath's view.\nbudget line <!-- private -->\nkept"
    assert scrub_text(text) == "the author asked.\nthe mentor's view.\nkept"
    assert scrub({"a": ["Josh's note"]}) == {"a": ["the author's note"]}


def test_lint_flags_private_looking_text() -> None:
    kinds = {i.split(": ")[1] for i in lint_text("$40 at josh-pc.basa.ts.net, a@b.com", "x")}
    assert kinds == {"money", "hostname", "e-mail", "name"}
    assert not lint_text("persistence 0.95 on the entangled set", "x")


def test_lint_site_reads_text_files(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "site.json").write_text(
        '{"x": "C:\\\\Users\\\\someone"}', encoding="utf-8"
    )
    assert any("windows path" in i for i in lint_site(tmp_path))
