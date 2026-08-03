#!/usr/bin/env python3
"""Materialize deterministic bounded-planar ModelIR corpus cases M1–M5/L1–L2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


PROFILE = "planar_frame_verified_alpha.v1"
CASE_SIZES = {
    "M1": (35, 54),
    "M2": (36, 56),
    "M3": (36, 55),
    "M4": (48, 78),
    "M5": (55, 90),
    "L1": (85, 144),
    "L2": (126, 220),
}


class PlanarCorpusError(RuntimeError):
    """Raised when a deterministic corpus model cannot be constructed."""


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def _source_hash(case_id: str, node_count: int, member_count: int) -> str:
    body = f"planar-corpus:{case_id}:{node_count}:{member_count}:v1".encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _grid_shape(node_count: int) -> tuple[int, int]:
    columns = max(5, min(12, int(round(math.sqrt(node_count * 1.3)))))
    rows = math.ceil(node_count / columns)
    return columns, rows


def _node_id(index: int) -> str:
    return f"N{index + 1}"


def _candidate_edges(node_count: int, columns: int) -> list[tuple[int, int]]:
    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    def add(i: int, j: int) -> None:
        if i == j or not 0 <= i < node_count or not 0 <= j < node_count:
            return
        edge = (min(i, j), max(i, j))
        if edge not in seen:
            seen.add(edge)
            edges.append(edge)

    base_count = min(columns, node_count)
    for index in range(base_count - 1):
        add(index, index + 1)
    for index in range(columns, node_count):
        add(index - columns, index)
    for row_start in range(columns, node_count, columns):
        row_end = min(row_start + columns, node_count)
        for index in range(row_start, row_end - 1):
            add(index, index + 1)
    for index in range(columns, node_count):
        column = index % columns
        if column > 0:
            add(index - columns - 1, index)
        if column + 1 < columns and index - columns + 1 < node_count:
            add(index - columns + 1, index)
    for span in (2, columns + 2, 2 * columns):
        for index in range(node_count - span):
            add(index, index + span)
    return edges


def build_case(case_id: str) -> dict[str, Any]:
    if case_id not in CASE_SIZES:
        raise PlanarCorpusError(f"unknown_case:{case_id}")
    node_count, member_count = CASE_SIZES[case_id]
    columns, rows = _grid_shape(node_count)
    edges = _candidate_edges(node_count, columns)
    if len(edges) < member_count:
        raise PlanarCorpusError(
            f"insufficient_candidate_edges:{case_id}:{len(edges)}/{member_count}"
        )
    edges = edges[:member_count]
    reachable = {0}
    changed = True
    while changed:
        changed = False
        for i, j in edges:
            if i in reachable and j not in reachable:
                reachable.add(j)
                changed = True
            elif j in reachable and i not in reachable:
                reachable.add(i)
                changed = True
    if len(reachable) != node_count:
        raise PlanarCorpusError(f"graph_not_connected:{case_id}")

    nodes = []
    for index in range(node_count):
        row, column = divmod(index, columns)
        nodes.append(
            {
                "id": _node_id(index),
                "index": index,
                "coordinates_m": [4.0 * column, 3.0 * row, 0.0],
                "source_id": f"generated:{case_id}:{_node_id(index)}",
                "extensions": {},
            }
        )

    elements = []
    for index, (i, j) in enumerate(edges):
        elements.append(
            {
                "id": f"E{index + 1}",
                "index": index,
                "type": "frame_2d",
                "formulation": "stateful_corotational_rc_fiber_frame2d",
                "node_ids": [_node_id(i), _node_id(j)],
                "section_id": "RC1",
                "integration_order": 2,
                "offsets": {
                    "i_global_m": [0.0, 0.0, 0.0],
                    "j_global_m": [0.0, 0.0, 0.0],
                },
                "releases": {"i": [], "j": []},
                "uniform_distributed_load_local": {
                    "basis": "initial_member_local",
                    "behavior": "dead",
                    "qx_n_per_m": 0.0,
                    "qy_n_per_m": 0.0,
                },
                "source_id": f"generated:{case_id}:E{index + 1}",
                "extensions": {},
            }
        )

    constraints = []
    base_count = min(columns, node_count)
    for index in range(node_count):
        base = index < base_count
        dofs = ["UX", "UY", "UZ", "RX", "RY", "RZ"] if base else ["UZ", "RX", "RY"]
        constraints.append(
            {
                "id": f"BC{index + 1}",
                "index": index,
                "type": "fixed_dofs",
                "node_id": _node_id(index),
                "dofs": dofs,
                "prescribed_values_si": {dof: 0.0 for dof in dofs},
                "source_id": f"generated:{case_id}:BC{index + 1}",
                "extensions": {},
            }
        )

    top_row = rows - 1
    top_nodes = [
        index for index in range(node_count) if index // columns == top_row
    ]
    nodal_loads = []
    for load_index, node_index in enumerate(top_nodes):
        nodal_loads.append(
            {
                "id": f"P{load_index + 1}",
                "index": load_index,
                "node_id": _node_id(node_index),
                "components_si": {
                    "FX": 50.0,
                    "FY": -500.0,
                    "FZ": 0.0,
                    "MX": 0.0,
                    "MY": 0.0,
                    "MZ": 0.0,
                },
                "source_id": f"generated:{case_id}:P{load_index + 1}",
                "extensions": {},
            }
        )

    return {
        "schema_version": "structural-analysis-model-ir.v2",
        "model_id": f"planar-corpus-{case_id.lower()}",
        "capability_profile": PROFILE,
        "provenance": {
            "source_format": "generated",
            "source_ref": f"generated:planar-corpus:{case_id}",
            "source_sha256": _source_hash(case_id, node_count, member_count),
            "normalizer_id": "planar-verification-corpus-builder",
            "normalizer_version": "1",
            "source_units": {
                "length": "m",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad",
            },
            "unit_scales_to_si": {
                "length_to_m": 1.0,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0,
            },
            "extensions": {},
        },
        "units": {
            "length": "m",
            "force": "N",
            "mass": "kg",
            "time": "s",
            "rotation": "rad",
        },
        "coordinate_system": {
            "frame_id": "global",
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
            "handedness": "right",
            "origin_m": [0.0, 0.0, 0.0],
        },
        "dof_components": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
        "nodes": nodes,
        "materials": [
            {
                "id": "steel",
                "index": 0,
                "law_id": "bilinear_combined_hardening_steel",
                "parameter_set_version": "1",
                "parameters": {
                    "elastic_modulus_pa": 200000000000.0,
                    "yield_stress_pa": 1000000000000.0,
                    "isotropic_hardening_modulus_pa": 0.0,
                    "kinematic_hardening_modulus_pa": 0.0,
                    "yield_tolerance_pa": 0.0001,
                },
                "state_schema": {
                    "stateful": True,
                    "state_update_epoch": "accepted_step",
                    "supports_trial_commit_rollback": True,
                },
                "source_id": f"generated:{case_id}:steel",
                "extensions": {},
            },
            {
                "id": "concrete",
                "index": 1,
                "law_id": "asymmetric_concrete_damage",
                "parameter_set_version": "1",
                "parameters": {
                    "elastic_modulus_pa": 30000000000.0,
                    "tensile_strength_pa": 1000000000000.0,
                    "compressive_strength_pa": 1000000000000.0,
                    "tensile_softening_rate": 1.0,
                    "compressive_softening_rate": 1.0,
                    "history_tolerance": 1e-14,
                },
                "state_schema": {
                    "stateful": True,
                    "state_update_epoch": "accepted_step",
                    "supports_trial_commit_rollback": True,
                },
                "source_id": f"generated:{case_id}:concrete",
                "extensions": {},
            },
        ],
        "sections": [
            {
                "id": "RC1",
                "index": 0,
                "family_id": "rectangular_rc_fiber_2d",
                "parameter_set_version": "1",
                "parameters": {
                    "width_m": 0.4,
                    "depth_m": 0.6,
                    "cover_m": 0.05,
                    "concrete_layer_count": 2,
                    "top_bar_count": 2,
                    "bottom_bar_count": 2,
                    "bar_area_m2": 0.000387,
                },
                "steel_material_id": "steel",
                "concrete_material_id": "concrete",
                "source_id": f"generated:{case_id}:RC1",
                "extensions": {},
            }
        ],
        "elements": elements,
        "constraints": constraints,
        "load_patterns": [
            {
                "id": "LP1",
                "index": 0,
                "analysis_type": "nonlinear_static_load_control",
                "self_weight": [0.0, 0.0, 0.0],
                "nodal_loads": nodal_loads,
                "source_id": f"generated:{case_id}:LP1",
                "extensions": {},
            }
        ],
        "load_combinations": [],
        "time_functions": [],
        "construction_stages": [],
        "roundtrip_map": [],
        "unsupported_features": [],
        "extensions": {},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(CASE_SIZES), action="append")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    selected = args.case or list(CASE_SIZES)
    artifacts = []
    for case_id in selected:
        payload = build_case(case_id)
        out = args.out_dir / f"{case_id}.model-ir.v2.json"
        _write_json(out, payload)
        artifacts.append(
            {
                "case_id": case_id,
                "path": out.as_posix(),
                "node_count": len(payload["nodes"]),
                "member_count": len(payload["elements"]),
                "sha256": "sha256:" + hashlib.sha256(out.read_bytes()).hexdigest(),
            }
        )
    receipt = {
        "schema_version": "planar-corpus-materialization.v1",
        "contract_pass": True,
        "profile": PROFILE,
        "artifacts": artifacts,
        "claim_boundary": (
            "These generated ModelIR cases provide deterministic internal execution "
            "coverage only. They do not create independent scientific reference, "
            "external V&V, performance, design, or release authority."
        ),
    }
    _write_json(args.out_dir / "materialization-receipt.json", receipt)
    if args.json:
        print(_serialized(receipt), end="")
    else:
        print(f"planar corpus materialized: {len(artifacts)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
