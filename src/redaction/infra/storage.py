"""Reading and writing pydantic models as JSON Lines and JSON."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


def write_jsonl(path: Path, items: Iterable[BaseModel]) -> int:
    """Write one model per line, creating parent directories. Returns the number written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(item.model_dump_json() + "\n")
            count += 1
    return count


def write_json[T](path: Path, value: T, adapter: TypeAdapter[T]) -> None:
    """Write any value pydantic can serialize, pretty-printed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(adapter.dump_json(value, indent=2))


def write_text(path: Path, text: str) -> None:
    """Write text, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
