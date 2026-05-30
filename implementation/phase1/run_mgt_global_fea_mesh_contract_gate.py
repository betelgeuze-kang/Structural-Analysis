#!/usr/bin/env python3
"""Validate parsed MGT roundtrip NPZ mesh contract (no global FEA solve)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from design_optimization.io import load_json


SCHEMA_VERSION = "mgt-global-fea-mesh-contract-gate.v1"


def _section_count(roundtrip: dict[str, Any], key: str) -> int:
    parser = roundtrip.get("parser") if isinstance(roundtrip.get("parser"), dict) else {}
    counts = parser.get("section_counts") if isinstance(parser.get("section_counts"), dict) else {}
    try:
        return int(counts.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def build_mgt_global_fea_mesh_contract_gate(
    *,
    roundtrip_json: Path,
    roundtrip_npz: Path | None = None,
) -> dict[str, Any]:
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    blockers: list[str] = []
    if not roundtrip_json.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "native_solve_status": "not_wired",
            "blockers": ["roundtrip_json_missing"],
        }
    if not roundtrip_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "native_solve_status": "not_wired",
            "blockers": ["roundtrip_npz_missing"],
        }

    roundtrip = load_json(roundtrip_json)
    parse_report_path = roundtrip_json.with_name(roundtrip_json.stem + ".parse_report.json")
    parse_report = load_json(parse_report_path) if parse_report_path.is_file() else {}
    parse_metrics = parse_report.get("metrics") if isinstance(parse_report.get("metrics"), dict) else {}
    expected_elements = int(parse_metrics.get("element_count") or 0) or _section_count(roundtrip, "ELEMENT")
    expected_nodes = int(parse_metrics.get("node_count") or 0) or _section_count(roundtrip, "NODE")
    node_count_basis = "parse_report" if parse_metrics.get("node_count") else "roundtrip_section_counts"

    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        required = (
            "node_id",
            "node_xyz",
            "edge_index",
            "elem_id",
            "elem_type_code",
            "elem_section_id",
            "elem_material_id",
        )
        missing_arrays = [key for key in required if key not in archive.files]
        if missing_arrays:
            blockers.append("npz_missing_required_arrays")
        elem_count = int(len(archive["elem_id"])) if "elem_id" in archive.files else 0
        node_count = int(len(archive["node_id"])) if "node_id" in archive.files else 0
        edge_pairs = int(archive["edge_index"].shape[1]) if "edge_index" in archive.files else 0

    if expected_elements and abs(elem_count - expected_elements) > max(2, int(0.01 * expected_elements)):
        blockers.append("element_count_mismatch")
    if expected_nodes and abs(node_count - expected_nodes) > max(2, int(0.01 * expected_nodes)):
        blockers.append("node_count_mismatch")
    if edge_pairs < 1:
        blockers.append("edge_index_empty")

    ready = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "blocked",
        "claim": "NPZ mesh contract check only; does not execute global nonlinear FEA.",
        "native_solve_status": "not_wired",
        "mesh_contract_ready": ready,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "metrics": {
            "expected_element_count": expected_elements,
            "npz_element_count": elem_count,
            "expected_node_count": expected_nodes,
            "npz_node_count": node_count,
            "npz_edge_pairs": edge_pairs,
            "npz_missing_arrays": missing_arrays,
            "node_count_basis": node_count_basis,
            "node_count_pre_coarsening": int(parse_metrics.get("node_count_pre_coarsening") or 0),
        },
        "blockers": blockers,
        "next_step": "Map elem_id/section_id tensors into global solver assembly import.",
    }
