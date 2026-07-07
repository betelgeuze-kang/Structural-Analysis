"""MIDAS adapter exports for Phase 1 thin adapters."""

from __future__ import annotations

import re

from structural_analysis.io.midas import loader as _loader

_RANGE_BY_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*by\s*(\d+)\s*$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*$", re.IGNORECASE)


def _as_int(token: str) -> int | None:
    try:
        value = float(str(token).strip())
    except ValueError:
        return None
    if abs(value - int(value)) <= 1.0e-9:
        return int(value)
    return None


def _extract_node_span(token: str) -> list[int]:
    match = _RANGE_BY_RE.match(token)
    if match:
        start, end, step = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if step <= 0:
            return []
        if start <= end:
            return list(range(start, end + 1, step))
        return list(range(start, end - 1, -step))
    match = _RANGE_RE.match(token)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end:
            return list(range(start, end + 1))
        return list(range(start, end - 1, -1))
    value = _as_int(token)
    return [int(value)] if value is not None else []


def _expand_node_expr(expr: str) -> list[int]:
    text = str(expr).strip()
    if not text:
        return []

    whole_span = _extract_node_span(text)
    if whole_span:
        return whole_span

    node_ids: list[int] = []
    for token in text.replace(",", " ").split():
        node_ids.extend(_extract_node_span(token))
    return node_ids


# Keep the existing public loader module stable while hardening the node-expression
# contract used by supports and *CONLOAD rows. This small package-level patch keeps
# the change isolated to the MIDAS adapter surface and is covered by PR-gated tests.
_loader._expand_node_expr = _expand_node_expr

load_midas_mgt = _loader.load_midas_mgt

__all__ = ["load_midas_mgt"]
