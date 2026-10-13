"""Pulling a JSON object out of a model reply and validating it."""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel

_FENCE: Final = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class ReplyFormatError(ValueError):
    """A model reply did not contain a valid JSON object for the expected schema."""


def extract_json_object(text: str) -> str:
    """Return the JSON object in a reply, tolerating code fences and surrounding prose."""
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end < start:
        msg = "no JSON object found in the reply"
        raise ReplyFormatError(msg)
    return candidate[start : end + 1]


def parse_reply[T: BaseModel](text: str, schema: type[T]) -> T:
    """Parse and validate a reply; raises `ReplyFormatError` with a readable reason."""
    try:
        return schema.model_validate_json(extract_json_object(text))
    except ValueError as error:  # pydantic.ValidationError is a ValueError
        raise ReplyFormatError(str(error)) from error
