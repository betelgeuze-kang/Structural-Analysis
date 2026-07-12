"""Fail-closed canonical normalization for MIDAS MGT imports.

Raw section parsing is owned by :mod:`structural_analysis.io.midas.raw_parser`.
The legacy topology adapter remains available explicitly as
``load_midas_mgt_topology``; this module alone owns public canonical load
normalization.
"""

from __future__ import annotations

from dataclasses import replace
from math import isfinite
from pathlib import Path
from typing import Any, Iterable

from structural_analysis.io.midas.loader import (
    load_midas_mgt as load_midas_mgt_topology,
)
from structural_analysis.io.midas.raw_parser import (
    MidasRawModel,
    expand_integer_expression,
    parse_float_token,
    parse_midas_mgt,
    parse_static_load_cases,
    split_csv_like,
)
from structural_analysis.model.schema import CanonicalModel

_COMPONENT_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")


def load_midas_mgt(path: Path) -> CanonicalModel:
    """Parse MGT raw sections, then normalize them to the public canonical model."""

    raw_model = parse_midas_mgt(path)
    topology_model = load_midas_mgt_topology(path)
    return canonicalize_midas_mgt(raw_model, topology_model)


def canonicalize_midas_mgt(
    raw_model: MidasRawModel,
    topology_model: CanonicalModel,
) -> CanonicalModel:
    """Normalize one matching raw parse and topology model without import side effects."""

    raw_source = Path(raw_model.source_path).resolve(strict=False)
    topology_source = Path(topology_model.source_path).resolve(strict=False)
    if raw_source != topology_source:
        raise ValueError(
            "MIDAS raw/topology source mismatch: "
            f"{raw_source} != {topology_source}"
        )
    if topology_model.source_format != "midas_mgt":
        raise ValueError(
            "MIDAS canonicalization requires a midas_mgt topology model; "
            f"received {topology_model.source_format}"
        )

    node_ids = _canonical_node_ids(topology_model)
    static_load_cases = parse_static_load_cases(raw_model.section("STLDCASE"))
    nodal_loads, load_issues = _parse_nodal_loads(
        raw_model.section("CONLOAD"),
        node_ids,
    )

    unsupported = list(topology_model.unsupported_features)
    warnings = list(topology_model.warnings)

    if len(static_load_cases) == 1:
        load_case = str(static_load_cases[0].get("name", "")).strip()
        if load_case:
            nodal_loads = [
                {**row, "load_case": load_case}
                for row in nodal_loads
            ]
    elif len(static_load_cases) > 1 and nodal_loads:
        unsupported.append(
            {
                "kind": "mgt_conload_load_case_association_missing",
                "detail": (
                    "Multiple *STLDCASE definitions exist, but this thin adapter "
                    "cannot prove which *CONLOAD row belongs to which case. Nodal "
                    "loads remain unlabelled and solver use is blocked."
                ),
                "available_load_cases": [
                    str(row.get("name", ""))
                    for row in static_load_cases
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

    metadata = dict(topology_model.metadata)
    metadata.update(
        {
            "adapter": "structural_analysis.io.midas.load_midas_mgt",
            "adapter_pipeline": [
                "parse_midas_mgt",
                "load_midas_mgt_topology",
                "canonicalize_midas_mgt",
            ],
            "raw_parser": "structural_analysis.io.midas.raw_parser.parse_midas_mgt",
            "canonical_adapter": (
                "structural_analysis.io.midas.canonical.canonicalize_midas_mgt"
            ),
            "adapter_scope": (
                "topology/model-health import plus lossless single-node *CONLOAD "
                "normalization; deterministic MGT solver closure remains outside "
                "this adapter"
            ),
            "raw_section_counts": raw_model.section_counts,
            "raw_line_count": raw_model.line_count,
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
        topology_model,
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
    rows: Iterable[str],
    node_ids: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    loads: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        tokens = split_csv_like(row)
        if len(tokens) < 7:
            issues.append(
                {
                    "row_index": row_index,
                    "reason": "too_short",
                    "raw": row,
                }
            )
            continue

        target_nodes, target_error = expand_integer_expression(tokens[0])
        if target_error is not None or not target_nodes:
            issues.append(
                {
                    "row_index": row_index,
                    "reason": target_error or "empty_node_expression",
                    "raw": row,
                }
            )
            continue

        missing_nodes = [
            node_id
            for node_id in target_nodes
            if node_id not in node_ids
        ]
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

        values = [parse_float_token(token) for token in tokens[1:7]]
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

        components = dict(
            zip(_COMPONENT_LABELS, numeric_values, strict=True)
        )
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
