"""Strict finite UTF-8 JSON transport without a solver dependency."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn

STRICT_JSON_MAX_DEPTH = 64
STRICT_JSON_DEFAULT_MAX_BYTES = 128 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number: {value}")


def strict_json_object_bytes(
    data: bytes,
    *,
    maximum_bytes: int = STRICT_JSON_DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Decode finite UTF-8 JSON once; reject duplicates, oversize and deep trees.

    This validates JSON transport only. A ModelIR caller must still apply its
    own document contract to the returned object, using these same input bytes.
    """
    if type(data) is not bytes:
        raise ValueError("JSON input must be bytes")
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("maximum_bytes must be a positive integer")
    if not data or len(data) > maximum_bytes:
        raise ValueError("JSON input is empty or exceeds maximum_bytes")
    try:
        payload = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if type(payload) is not dict:
            raise ValueError("JSON root must be an object")
        stack = [(payload, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > STRICT_JSON_MAX_DEPTH:
                raise ValueError("JSON nesting exceeds maximum depth")
            if type(item) in (int, float) and not math.isfinite(float(item)):
                raise ValueError("JSON number must be finite")
            if type(item) is str:
                item.encode("utf-8")
            elif type(item) is dict:
                stack.extend((key, depth + 1) for key in item)
                stack.extend((value, depth + 1) for value in item.values())
            elif type(item) is list:
                stack.extend((value, depth + 1) for value in item)
    except (ValueError, UnicodeError, OverflowError, RecursionError) as error:
        raise ValueError(f"invalid JSON object: {error}") from error
    return payload
