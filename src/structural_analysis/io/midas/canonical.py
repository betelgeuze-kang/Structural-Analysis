"""Fail-closed canonical normalization for MIDAS MGT imports.

The legacy parser remains responsible for topology and metadata extraction. This
module normalizes ``*CONLOAD`` rows into the public six-component nodal-load
contract and keeps load-case definitions in metadata instead of mixing them with
analysis input rows.
"""

from __future__ import annotations

from dataclasses import replace
from math import isfinite
from pathlib import Path
import re
from typing import Any

from structural_analysis.io.midas import loader as _raw
from structural_analysis.model.schema import CanonicalModel

_RAW_LOAD_MIDAS_MGT = _raw.load_midas_mgt
_RANGE_BY_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*by\s*(\d+)\s*$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*$", re.IGNORECASE)
_COMPONENT_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")


def load_midas_mgt(path: Path) -> CanonicalModel:
    """Load MGT topology and normalize supported nodal-load rows without loss."""

    model = _RAW_LOAD_MIDAS_MGT(path)
    sections, _ = _raw._parse_sections(path)
    node_ids = _canonical_node_ids(model)
    static_load_cases = _raw._parse_static_load_cases(sections.get("STLDCASE", []))
    nodal_loads, load_issues = _parse_nodal_loads(
        sections.get("CONLOAD", []),
        node_ids,
    )

    unsupported = list(model.unsupported_features)
    warnings = list(model.warnings)

    if len(static_load_cases) == 1:
        load_case = str(static_load_cases[0].get("name", "")).strip()
        if load_case:
            nodal_loads = [{**row, "load_case": load_case} for row in nodal_loads]
    elif len(static_load_cases) > 1 and nodal_loads:
        unsupported.append(
            {
                "kind": "mgt_conload_load_case_association_missing",
                "detail": (
                    "Multiple *STLDCASE definitions exist, but this thin adapter cannot "
                    "prove which *CONLOAD row belongs to which case. Nodal loads remain "
                    "unlabelled and solver use is blocked."
                ),
                "available_load_cases": [
                    str(row.get("name", "")) for row in static_load_cases
                ],
                "nodal_load_count": len(nodal_loads),
            }
        )

    if load_issues:
        unsupported.append(
            {
                "kind": "mgt_conload_rows_skipped",
                "detail": (
                    "Some *CONLOAD rows could not be normalized without semantic loss."
                ),
                "skipped_count": len(load_issues),
                "issues": load_issues[:32],
            }
        )

    metadata = dict(model.metadata)
    metadata.update(
        {
            "adapter": "structural_analysis.io.midas.load_midas_mgt",
            "adapter_scope": (
                "topology/model-health import only for topology and raw "
                "material/section mapping, plus lossless single-node *CONLOAD "
                "normalization; deterministic MGT solver closure remains outside "
                "this adapter"
            ),
            "static_load_cases": static_load_cases,
            "load_summary": {
                "static_load_case_count": len(static_load_cases),
                "nodal_load_count": len(nodal_loads),
                "skipped_conload_count": len(load_issues),
            },
        }
    )

    if not static_load_cases and nodal_loads:
        warnings.append(
            "MGT *CONLOAD rows were normalized without an explicit *STLDCASE label."
        )

    return replace(
        model,
        loads=nodal_loads,
        unsupported_features=unsupported,
        warnings=warnings,
        metadata=metadata,
    )


def _canonical_node_ids(model: CanonicalModel) -> set[int]:
    node_ids: set[int] = set()
    for row in model.nodes:
        try:
            node_ids.add(int(str(row.get("id", "")).strip()))
        except (TypeError, ValueError):
            continue
    return node_ids


def _parse_nodal_loads(
    rows: list[str],
    node_ids: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    loads: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        tokens = _raw._split_csv_like(row)
        if len(tokens) < 7:
            issues.append(
                {
                    "row_index": row_index,
                    "reason": "too_short",
                    "raw": row,
                }
            )
            continue

        target_nodes, target_error = _expand_node_expr(tokens[0])
        if target_error is not None or not target_nodes:
            issues.append(
                {
                    "row_index": row_index,
                    "reason": target_error or "empty_node_expression",
                    "raw": row,
                }
            )
            continue

        missing_nodes = [node_id for node_id in target_nodes if node_id not in node_ids]
        if missing_nodes:
            issues.append(
                {
                    "row_index": row_index,
                    "reason": "unknown_node_reference",
                    "missing_nodes": missing_nodes,
                    "raw": row,
                }
            )
            continue

        values = [_raw._as_float(token) for token in tokens[1:7]]
        if any(value is None for value in values):
            issues.append(
                {
                    "row_index": row_index,
                    "reason": "non_numeric_component",
                    "raw": row,
                }
            )
            continue
        numeric_values = [float(value) for value in values]
        if not all(isfinite(value) for value in numeric_values):
            issues.append(
                {
                    "row_index": row_index,
                    "reason": "non_finite_component",
                    "raw": row,
                }
            )
            continue

        components = dict(zip(_COMPONENT_LABELS, numeric_values, strict=True))
        for node_id in target_nodes:
            loads.append(
                {
                    "kind": "nodal_load",
                    "node": str(node_id),
                    "components": dict(components),
                    "source": "midas_mgt_conload",
                    "raw": row,
                }
            )
    return loads, issues


def _expand_node_expr(expr: str) -> tuple[list[int], str | None]:
    text = str(expr).strip()
    if not text:
        return [], "empty_node_expression"

    match = _RANGE_BY_RE.match(text)
    if match:
        start, end, step = (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
        if step <= 0:
            return [], "non_positive_range_step"
        stop = end + 1 if start <= end else end - 1
        signed_step = step if start <= end else -step
        return list(range(start, stop, signed_step)), None

    match = _RANGE_RE.match(text)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        stop = end + 1 if start <= end else end - 1
        step = 1 if start <= end else -1
        return list(range(start, stop, step)), None

    lowered = text.lower()
    if " to " in lowered or " by " in lowered:
        return [], "malformed_node_range"

    node_ids: list[int] = []
    seen: set[int] = set()
    for token in text.replace(",", " ").split():
        node_id = _raw._as_int(token)
        if node_id is None:
            return [], "non_integer_node_token"
        if node_id not in seen:
            seen.add(node_id)
            node_ids.append(node_id)
    return node_ids, None
