"""Layering rules: each package may import only from the layers below it."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = "redaction"
ROOT = Path(__file__).parents[2] / "src" / PACKAGE

# Which of the package's own layers each layer may import from.
ALLOWED = {
    "core": {"core"},
    "data": {"core", "data"},
    "infra": {"core", "infra"},
    "escalation": {"core", "data", "infra", "escalation"},
    "detective": {"core", "data", "infra", "detective"},
}


def _internal_imports(path: Path) -> set[str]:
    """The top-level package layers a module imports from."""
    layers: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        for name in names:
            parts = name.split(".")
            if parts[0] == PACKAGE and len(parts) > 1:
                layers.add(parts[1])
    return layers


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_layer_imports(layer: str) -> None:
    for path in (ROOT / layer).rglob("*.py"):
        forbidden = _internal_imports(path) - ALLOWED[layer]
        assert not forbidden, f"{path.relative_to(ROOT)} imports {sorted(forbidden)}"
