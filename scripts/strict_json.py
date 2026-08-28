"""Small fail-closed JSON byte-boundary helpers for evidence tooling.

The standard-library decoder accepts duplicate object members and non-finite
numbers by default.  Evidence readers must reject both before schema validation
or hashing so two parsers cannot assign different meaning to the same bytes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, NoReturn


class StrictJSONError(ValueError):
    """Raised when JSON bytes are ambiguous or outside RFC 8259 numbers."""


def _reject_constant(token: str) -> NoReturn:
    raise StrictJSONError(f"non_finite_json_number:{token}")


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise StrictJSONError(f"non_finite_json_number:{token}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def strict_json_loads(value: str | bytes | bytearray) -> Any:
    """Decode one JSON document while rejecting duplicates and non-finite values."""

    if isinstance(value, (bytes, bytearray)):
        try:
            value = bytes(value).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StrictJSONError("json_not_utf8") from exc
    try:
        return json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise StrictJSONError("invalid_json") from exc


def strict_json_load_path(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StrictJSONError(f"json_unreadable:{path}") from exc
    return strict_json_loads(raw)
