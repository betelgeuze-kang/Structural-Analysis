"""Strict MIDAS ID-list and ``to``/``by`` range expansion."""

from __future__ import annotations

from collections.abc import Iterable
import re


class RangeSyntaxError(ValueError):
    """Raised when an MGT ID expression cannot be expanded without guessing."""


_RANGE_RE = re.compile(
    r"(?P<start>\d+)\s*to\s*(?P<stop>\d+)(?:\s*by\s*(?P<step>\d+))?",
    re.IGNORECASE,
)
_INTEGER_RE = re.compile(r"\d+")
_SEPARATOR_RE = re.compile(r"[\s,]*")


def expand_id_expression(expression: str, *, max_items: int = 1_000_000) -> tuple[int, ...]:
    """Expand an ordered MGT ID expression, preserving duplicates and direction."""

    if max_items < 1:
        raise ValueError("max_items must be positive")
    text = str(expression)
    position = 0
    values: list[int] = []
    while position < len(text):
        separator = _SEPARATOR_RE.match(text, position)
        assert separator is not None
        position = separator.end()
        if position == len(text):
            break

        range_match = _RANGE_RE.match(text, position)
        if range_match is not None and _is_token_boundary(text, range_match.end()):
            start = int(range_match.group("start"))
            stop = int(range_match.group("stop"))
            step_token = range_match.group("step")
            step = int(step_token) if step_token is not None else 1
            if step == 0:
                raise RangeSyntaxError("range step must be greater than zero")
            signed_step = step if start <= stop else -step
            stop_bound = stop + (1 if signed_step > 0 else -1)
            _extend_checked(values, range(start, stop_bound, signed_step), max_items=max_items)
            position = range_match.end()
            continue

        integer_match = _INTEGER_RE.match(text, position)
        if integer_match is not None and _is_token_boundary(text, integer_match.end()):
            _extend_checked(values, (int(integer_match.group(0)),), max_items=max_items)
            position = integer_match.end()
            continue

        excerpt = text[position : position + 24]
        raise RangeSyntaxError(f"invalid MGT ID expression near {excerpt!r}")
    return tuple(values)


def _is_token_boundary(text: str, position: int) -> bool:
    return position == len(text) or text[position].isspace() or text[position] == ","


def _extend_checked(values: list[int], additions: Iterable[int], *, max_items: int) -> None:
    for value in additions:
        if len(values) >= max_items:
            raise RangeSyntaxError(f"expanded ID list exceeds max_items={max_items}")
        values.append(int(value))
