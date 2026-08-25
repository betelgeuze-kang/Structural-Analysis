#!/usr/bin/env python3
"""Run the bounded ModelIR -> native Frame3D -> ResultIR differential pack."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from structural_analysis.elements.frame3d import (  # noqa: E402
    FrameProps,
    frame_rotation_matrix,
    frame_transform,
    rigid_end_offset_transform,
)
from structural_analysis.elements.timoshenko_frame3d import (  # noqa: E402
    TimoshenkoFrame3DSection,
    local_timoshenko_frame_stiffness,
)
from structural_analysis.model_ir import parse_model_ir_v2  # noqa: E402


SCHEMA_VERSION_V1 = "structural-native-frame3d-modelir-parity-pack.v1"
SCHEMA_VERSION_V2 = "structural-native-frame3d-modelir-parity-pack.v2"
SCHEMA_VERSION_V3 = "structural-native-frame3d-modelir-parity-pack.v3"
RESULT_SCHEMA = "structural-native-linear-frame3d-result-ir.v1"
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
GRAVITY_M_S2 = 9.806_65
DISPLACEMENT_TOLERANCE = 5.0e-10
FORCE_TOLERANCE = 5.0e-9
GATE_TOLERANCE = 1.0e-9
RESULT_AUTHORITY_PROFILE = "bounded_native_cpu_result_candidate.v1"
RESULT_PROMOTION_BASIS = (
    "native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1"
)
COMPONENTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
DOFS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
RELEASE_DOF = {"RX": 3, "RY": 4, "RZ": 5}


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _base_model() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["elements"][0]["formulation"] = "linear_timoshenko_frame3d"
    return payload


def _node(node_id: str, index: int, coordinates_m: list[float]) -> dict[str, Any]:
    return {
        "id": node_id,
        "index": index,
        "coordinates_m": coordinates_m,
        "source_id": f"generated:{node_id}",
        "extensions": {},
    }


def _element(
    element_id: str,
    index: int,
    node_i: str,
    node_j: str,
    *,
    roll_rad: float = 0.0,
    offset_i: list[float] | None = None,
    offset_j: list[float] | None = None,
) -> dict[str, Any]:
    row = deepcopy(_base_model()["elements"][0])
    row.update(
        {
            "id": element_id,
            "index": index,
            "node_ids": [node_i, node_j],
            "local_axis_rotation_rad": roll_rad,
            "source_id": f"generated:{element_id}",
        }
    )
    row["offsets"] = {
        "i_global_m": offset_i or [0.0, 0.0, 0.0],
        "j_global_m": offset_j or [0.0, 0.0, 0.0],
    }
    row["releases"] = {"i": [], "j": []}
    return row


def _constraint(
    constraint_id: str, index: int, node_id: str, dofs: list[str]
) -> dict[str, Any]:
    return {
        "id": constraint_id,
        "index": index,
        "type": "fixed_dofs",
        "node_id": node_id,
        "dofs": dofs,
        "prescribed_values_si": {dof: 0.0 for dof in dofs},
        "source_id": f"generated:{constraint_id}",
        "extensions": {},
    }


def _nodal_load(
    load_id: str, index: int, node_id: str, values: list[float]
) -> dict[str, Any]:
    return {
        "id": load_id,
        "index": index,
        "node_id": node_id,
        "components_si": dict(zip(COMPONENTS, values, strict=True)),
        "source_id": f"generated:{load_id}",
        "extensions": {},
    }


def _uniform_load(
    load_id: str, index: int, member_id: str, values: list[float]
) -> dict[str, Any]:
    return {
        "id": load_id,
        "index": index,
        "member_id": member_id,
        "basis": "initial_member_local",
        "behavior": "dead",
        "components_si": dict(zip(("QX", "QY", "QZ"), values, strict=True)),
        "source_id": f"generated:{load_id}",
        "extensions": {},
    }


def _multi_member_model(
    *,
    nodes: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    nodal_loads: list[dict[str, Any]],
    uniform_loads: list[dict[str, Any]],
    self_weight: list[float],
) -> dict[str, Any]:
    model = _base_model()
    model["nodes"] = nodes
    model["elements"] = elements
    model["constraints"] = constraints
    model["load_patterns"] = [
        {
            "id": "LC_MULTI",
            "index": 0,
            "analysis_type": "linear_static",
            "self_weight": self_weight,
            "nodal_loads": nodal_loads,
            "uniform_member_loads": uniform_loads,
            "source_id": "generated:LC_MULTI",
            "extensions": {},
        }
    ]
    model["load_combinations"] = []
    return model


def _mixed_rotated_offset_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _base_model()
    model["nodes"][1]["coordinates_m"] = [1.3, -0.8, 2.1]
    model["elements"][0]["local_axis_rotation_rad"] = 0.37
    model["elements"][0]["offsets"]["i_global_m"] = [0.10, -0.04, 0.06]
    model["elements"][0]["offsets"]["j_global_m"] = [-0.08, 0.05, -0.03]
    pattern = model["load_patterns"][1]
    pattern["self_weight"] = [0.25, -0.4, -1.0]
    pattern["nodal_loads"][0]["components_si"] = {
        "FX": 12_000.0,
        "FY": -9_000.0,
        "FZ": 7_000.0,
        "MX": 1_500.0,
        "MY": -2_200.0,
        "MZ": 3_100.0,
    }
    pattern["uniform_member_loads"] = [
        {
            "id": "UDL_MIXED_OFFSET",
            "index": 0,
            "member_id": "E1",
            "basis": "initial_member_local",
            "behavior": "dead",
            "components_si": {"QX": 2_500.0, "QY": -4_000.0, "QZ": 1_500.0},
            "source_id": None,
            "extensions": {},
        }
    ]
    return (
        "rotated_offset_mixed_load",
        [
            "nodal_load",
            "uniform_member_load",
            "self_weight",
            "rigid_end_offset",
            "roll",
        ],
        model,
        "pattern",
        "LC_WEAK",
    )


def _released_uniform_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _base_model()
    model["elements"][0]["releases"]["i"] = ["RY"]
    model["elements"][0]["releases"]["j"] = ["RZ"]
    model["constraints"].append(
        {
            "id": "BC2",
            "index": 1,
            "type": "fixed_dofs",
            "node_id": "N2",
            "dofs": ["UY", "UZ", "RY", "RZ"],
            "prescribed_values_si": {"UY": 0.0, "UZ": 0.0, "RY": 0.0, "RZ": 0.0},
            "source_id": "generated:BC2",
            "extensions": {},
        }
    )
    pattern = model["load_patterns"][1]
    pattern["nodal_loads"] = []
    pattern["uniform_member_loads"] = [
        {
            "id": "UDL_RELEASED",
            "index": 0,
            "member_id": "E1",
            "basis": "initial_member_local",
            "behavior": "dead",
            "components_si": {"QX": 0.0, "QY": -10_000.0, "QZ": 7_000.0},
            "source_id": None,
            "extensions": {},
        }
    ]
    return (
        "released_uniform_member_load",
        ["uniform_member_load", "rotational_release", "multiple_supports"],
        model,
        "pattern",
        "LC_WEAK",
    )


def _nested_combination_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _base_model()
    model["load_patterns"][0]["self_weight"] = [-0.2, 0.1, -0.3]
    model["load_patterns"][1]["uniform_member_loads"] = [
        {
            "id": "UDL_COMB_WEAK",
            "index": 0,
            "member_id": "E1",
            "basis": "initial_member_local",
            "behavior": "dead",
            "components_si": {"QX": 2_500.0, "QY": -4_000.0, "QZ": 1_500.0},
            "source_id": None,
            "extensions": {},
        }
    ]
    model["load_combinations"] = [
        {
            "id": "COMB_BASE",
            "index": 0,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.25},
                {"ref_id": "LC_WEAK", "ref_kind": "load_pattern", "factor": -0.4},
            ],
            "source_id": None,
            "extensions": {},
        },
        {
            "id": "COMB_NESTED",
            "index": 1,
            "combination_type": "linear",
            "terms": [
                {"ref_id": "COMB_BASE", "ref_kind": "load_combination", "factor": 0.8},
                {"ref_id": "LC_STRONG", "ref_kind": "load_pattern", "factor": 1.1},
            ],
            "source_id": None,
            "extensions": {},
        },
    ]
    return (
        "nested_linear_combination",
        [
            "nodal_load",
            "uniform_member_load",
            "self_weight",
            "nested_linear_combination",
        ],
        model,
        "combination",
        "COMB_NESTED",
    )


def _two_member_chain_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _multi_member_model(
        nodes=[
            _node("N1", 0, [0.0, 0.0, 0.0]),
            _node("N2", 1, [2.0, 0.0, 0.0]),
            _node("N3", 2, [4.0, 1.0, 0.5]),
        ],
        elements=[
            _element("E1", 0, "N1", "N2"),
            _element("E2", 1, "N2", "N3", roll_rad=0.18),
        ],
        constraints=[_constraint("BC1", 0, "N1", list(DOFS))],
        nodal_loads=[
            _nodal_load("L_CHAIN_N3", 0, "N3", [8_000, -11_000, 6_000, 400, 0, 900])
        ],
        uniform_loads=[_uniform_load("UDL_CHAIN_E2", 0, "E2", [400, -700, 250])],
        self_weight=[0.1, -0.2, -1.0],
    )
    return (
        "two_member_spatial_chain",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "chain"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _planar_portal_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _multi_member_model(
        nodes=[
            _node("N1", 0, [0.0, 0.0, 0.0]),
            _node("N2", 1, [4.0, 0.0, 0.0]),
            _node("N3", 2, [0.0, 0.0, 3.0]),
            _node("N4", 3, [4.0, 0.0, 3.0]),
        ],
        elements=[
            _element("E1", 0, "N1", "N3"),
            _element("E2", 1, "N2", "N4"),
            _element("E3", 2, "N3", "N4"),
        ],
        constraints=[
            _constraint("BC1", 0, "N1", list(DOFS)),
            _constraint("BC2", 1, "N2", list(DOFS)),
        ],
        nodal_loads=[
            _nodal_load("L_PORTAL_N3", 0, "N3", [9_000, 0, -3_000, 0, 500, 0]),
            _nodal_load("L_PORTAL_N4", 1, "N4", [9_000, 0, -3_000, 0, -500, 0]),
        ],
        uniform_loads=[_uniform_load("UDL_PORTAL_E3", 0, "E3", [0, -900, -1_600])],
        self_weight=[0.0, 0.0, -1.0],
    )
    return (
        "planar_portal_multi_support",
        ["nodal_load", "uniform_member_load", "multi_member", "portal", "multiple_supports"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _spatial_corner_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _multi_member_model(
        nodes=[
            _node("N1", 0, [0.0, 0.0, 0.0]),
            _node("N2", 1, [0.0, 0.0, 2.8]),
            _node("N3", 2, [3.2, 1.7, 4.1]),
        ],
        elements=[
            _element("E1", 0, "N1", "N2"),
            _element(
                "E2",
                1,
                "N2",
                "N3",
                roll_rad=0.31,
                offset_i=[0.04, -0.02, 0.03],
                offset_j=[-0.03, 0.01, -0.02],
            ),
        ],
        constraints=[_constraint("BC1", 0, "N1", list(DOFS))],
        nodal_loads=[
            _nodal_load("L_CORNER_N3", 0, "N3", [7_000, -5_000, -8_000, 650, -450, 800])
        ],
        uniform_loads=[_uniform_load("UDL_CORNER_E2", 0, "E2", [350, -600, 420])],
        self_weight=[0.2, -0.1, -1.0],
    )
    return (
        "spatial_corner_roll_offset",
        ["nodal_load", "uniform_member_load", "rigid_end_offset", "roll", "multi_member", "spatial_frame"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _continuous_multiple_support_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    model = _multi_member_model(
        nodes=[
            _node("N1", 0, [0.0, 0.0, 0.0]),
            _node("N2", 1, [2.5, 0.0, 0.0]),
            _node("N3", 2, [5.0, 0.0, 0.0]),
        ],
        elements=[
            _element("E1", 0, "N1", "N2"),
            _element("E2", 1, "N2", "N3"),
        ],
        constraints=[
            _constraint("BC1", 0, "N1", list(DOFS)),
            _constraint("BC2", 1, "N3", ["UY", "UZ", "RX", "RY", "RZ"]),
        ],
        nodal_loads=[_nodal_load("L_CONTINUOUS_N2", 0, "N2", [2_000, -6_000, -9_000, 0, 0, 0])],
        uniform_loads=[
            _uniform_load("UDL_CONTINUOUS_E1", 0, "E1", [0, -500, -1_100]),
            _uniform_load("UDL_CONTINUOUS_E2", 1, "E2", [0, -700, -900]),
        ],
        self_weight=[0.0, 0.0, -1.0],
    )
    return (
        "continuous_line_multiple_support",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "multiple_supports"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _alpha_upper_moment_frame_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    nodes = [
        _node(f"N{level * 3 + bay + 1}", level * 3 + bay, [4.0 * bay, 0.0, 3.2 * level])
        for level in range(3)
        for bay in range(3)
    ]
    elements: list[dict[str, Any]] = []
    for level in range(2):
        for bay in range(3):
            index = len(elements)
            elements.append(
                _element(f"E{index + 1}", index, f"N{level * 3 + bay + 1}", f"N{(level + 1) * 3 + bay + 1}")
            )
    for level in (1, 2):
        for bay in range(2):
            index = len(elements)
            elements.append(
                _element(f"E{index + 1}", index, f"N{level * 3 + bay + 1}", f"N{level * 3 + bay + 2}")
            )
    model = _multi_member_model(
        nodes=nodes,
        elements=elements,
        constraints=[
            _constraint(f"BC{bay + 1}", bay, f"N{bay + 1}", list(DOFS))
            for bay in range(3)
        ],
        nodal_loads=[
            _nodal_load(f"L_TOP_{bay + 1}", bay, f"N{7 + bay}", [12_000, -2_000, -4_000, 0, 700 - 700 * bay, 0])
            for bay in range(3)
        ],
        uniform_loads=[
            _uniform_load(f"UDL_ROOF_{bay + 1}", bay, f"E{9 + bay}", [0, -700, -1_800])
            for bay in range(2)
        ],
        self_weight=[0.0, 0.0, -1.0],
    )
    return (
        "alpha_upper_moment_frame",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "multi_story", "moment_frame"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _alpha_upper_braced_frame_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    case_id, _, model, source_kind, source_id = _alpha_upper_moment_frame_case()
    del case_id
    for node_i, node_j in (("N1", "N5"), ("N2", "N4"), ("N5", "N9"), ("N6", "N8")):
        index = len(model["elements"])
        model["elements"].append(_element(f"E{index + 1}", index, node_i, node_j, roll_rad=0.11))
    model["load_patterns"][0]["nodal_loads"][0]["components_si"]["FY"] = -5_000.0
    return (
        "alpha_upper_braced_frame",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "multi_story", "braced_frame"],
        model,
        source_kind,
        source_id,
    )


def _alpha_upper_irregular_spatial_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    nodes = [
        _node("N1", 0, [0.0, 0.0, 0.0]),
        _node("N2", 1, [4.5, 0.2, 0.0]),
        _node("N3", 2, [4.1, 3.8, 0.0]),
        _node("N4", 3, [-0.3, 3.4, 0.0]),
        _node("N5", 4, [0.4, -0.2, 3.1]),
        _node("N6", 5, [4.8, 0.5, 3.6]),
        _node("N7", 6, [3.7, 4.2, 3.3]),
        _node("N8", 7, [-0.6, 3.0, 3.8]),
    ]
    connections = [
        ("N1", "N5"), ("N2", "N6"), ("N3", "N7"), ("N4", "N8"),
        ("N5", "N6"), ("N6", "N7"), ("N7", "N8"), ("N8", "N5"),
        ("N5", "N7"), ("N6", "N8"),
    ]
    elements = [
        _element(
            f"E{index + 1}",
            index,
            node_i,
            node_j,
            roll_rad=0.07 * (index % 4),
            offset_i=[0.02, -0.01, 0.01] if index == 4 else None,
            offset_j=[-0.01, 0.02, -0.01] if index == 4 else None,
        )
        for index, (node_i, node_j) in enumerate(connections)
    ]
    model = _multi_member_model(
        nodes=nodes,
        elements=elements,
        constraints=[
            _constraint(f"BC{index + 1}", index, f"N{index + 1}", list(DOFS))
            for index in range(4)
        ],
        nodal_loads=[
            _nodal_load("L_IRREGULAR_N6", 0, "N6", [8_000, -7_000, -9_000, 500, -300, 700]),
            _nodal_load("L_IRREGULAR_N8", 1, "N8", [-4_000, 6_000, -11_000, -400, 600, -500]),
        ],
        uniform_loads=[
            _uniform_load("UDL_IRREGULAR_E6", 0, "E6", [300, -650, -1_200]),
            _uniform_load("UDL_IRREGULAR_E8", 1, "E8", [-200, -500, -900]),
        ],
        self_weight=[0.15, -0.1, -1.0],
    )
    return (
        "alpha_upper_irregular_spatial",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "spatial_frame", "irregular_geometry", "roll", "rigid_end_offset"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _alpha_upper_multiple_support_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    nodes = [
        _node(f"N{index + 1}", index, [3.0 * (index % 4), 0.0, 0.0 if index < 4 else 3.0])
        for index in range(8)
    ]
    connections = [
        ("N1", "N5"), ("N2", "N6"), ("N3", "N7"), ("N4", "N8"),
        ("N5", "N6"), ("N6", "N7"), ("N7", "N8"),
    ]
    elements = [
        _element(f"E{index + 1}", index, node_i, node_j)
        for index, (node_i, node_j) in enumerate(connections)
    ]
    model = _multi_member_model(
        nodes=nodes,
        elements=elements,
        constraints=[
            _constraint(f"BC{index + 1}", index, f"N{index + 1}", list(DOFS))
            for index in range(4)
        ],
        nodal_loads=[
            _nodal_load(f"L_SUPPORT_{index + 1}", index, f"N{index + 5}", [2_000 * (index + 1), -1_000, -6_000, 0, 0, 300])
            for index in range(4)
        ],
        uniform_loads=[
            _uniform_load(f"UDL_SUPPORT_{index + 1}", index, f"E{index + 5}", [0, -400 - 100 * index, -1_000])
            for index in range(3)
        ],
        self_weight=[0.0, 0.0, -1.0],
    )
    return (
        "alpha_upper_multiple_support",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "multiple_supports", "continuous_frame"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _alpha_upper_mixed_feature_case() -> tuple[str, list[str], dict[str, Any], str, str]:
    nodes = [
        _node("N1", 0, [0.0, 0.0, 0.0]),
        _node("N2", 1, [4.0, 0.0, 0.0]),
        _node("N3", 2, [0.2, 0.1, 3.0]),
        _node("N4", 3, [4.3, 0.4, 3.3]),
        _node("N5", 4, [0.5, 3.2, 3.6]),
        _node("N6", 5, [4.1, 3.5, 3.1]),
    ]
    connections = [
        ("N1", "N3"), ("N2", "N4"), ("N3", "N4"),
        ("N3", "N5"), ("N4", "N6"), ("N5", "N6"), ("N3", "N6"),
    ]
    elements = [
        _element(
            f"E{index + 1}",
            index,
            node_i,
            node_j,
            roll_rad=0.09 * index,
            offset_i=[0.03, -0.01, 0.02] if index in (2, 5) else None,
            offset_j=[-0.02, 0.02, -0.01] if index in (2, 5) else None,
        )
        for index, (node_i, node_j) in enumerate(connections)
    ]
    elements[2]["releases"]["j"] = ["RY"]
    model = _multi_member_model(
        nodes=nodes,
        elements=elements,
        constraints=[
            _constraint("BC1", 0, "N1", list(DOFS)),
            _constraint("BC2", 1, "N2", list(DOFS)),
        ],
        nodal_loads=[
            _nodal_load("L_MIXED_N5", 0, "N5", [7_500, -4_500, -10_000, 800, -500, 650]),
            _nodal_load("L_MIXED_N6", 1, "N6", [-3_500, 5_500, -8_000, -450, 700, -600]),
        ],
        uniform_loads=[
            _uniform_load("UDL_MIXED_E4", 0, "E4", [250, -700, -1_300]),
            _uniform_load("UDL_MIXED_E6", 1, "E6", [-180, -500, -900]),
        ],
        self_weight=[0.1, -0.15, -1.0],
    )
    return (
        "alpha_upper_mixed_feature",
        ["nodal_load", "uniform_member_load", "self_weight", "multi_member", "spatial_frame", "roll", "rigid_end_offset", "rotational_release"],
        model,
        "pattern",
        "LC_MULTI",
    )


def _section(
    model: dict[str, Any], element: dict[str, Any]
) -> TimoshenkoFrame3DSection:
    material = next(
        row for row in model["materials"] if row["id"] == element["material_id"]
    )
    section = next(
        row for row in model["sections"] if row["id"] == element["section_id"]
    )
    material_values = material["parameters"]
    section_values = section["parameters"]
    elastic_kn_m2 = float(material_values["elastic_modulus_pa"]) / 1_000.0
    poisson = float(material_values["poisson_ratio"])
    shear_kn_m2 = elastic_kn_m2 / (2.0 * (1.0 + poisson))
    return TimoshenkoFrame3DSection(
        frame=FrameProps(
            area_m2=float(section_values["area_m2"]),
            e_n_per_m2=elastic_kn_m2,
            g_n_per_m2=shear_kn_m2,
            iy_m4=float(section_values["iy_m4"]),
            iz_m4=float(section_values["iz_m4"]),
            j_m4=float(section_values["torsional_constant_m4"]),
        ),
        effective_shear_area_y_m2=float(section_values["shear_area_y_m2"]),
        effective_shear_area_z_m2=float(section_values["shear_area_z_m2"]),
    )


def _condense_releases(
    stiffness: np.ndarray,
    equivalent: np.ndarray,
    released: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if released.size == 0:
        return stiffness, equivalent
    retained = np.asarray(
        [index for index in range(12) if index not in released], dtype=int
    )
    inverse = np.linalg.inv(stiffness[np.ix_(released, released)])
    condensed_stiffness = np.zeros((12, 12), dtype=np.float64)
    condensed_stiffness[np.ix_(retained, retained)] = (
        stiffness[np.ix_(retained, retained)]
        - stiffness[np.ix_(retained, released)]
        @ inverse
        @ stiffness[np.ix_(released, retained)]
    )
    condensed_equivalent = np.zeros(12, dtype=np.float64)
    condensed_equivalent[retained] = (
        equivalent[retained]
        - stiffness[np.ix_(retained, released)] @ inverse @ equivalent[released]
    )
    return condensed_stiffness, condensed_equivalent


def _uniform_equivalent(load: np.ndarray, length_m: float) -> np.ndarray:
    qx, qy, qz = load
    half = length_m / 2.0
    twelfth = length_m * length_m / 12.0
    return np.asarray(
        [
            qx * half,
            qy * half,
            qz * half,
            0.0,
            -qz * twelfth,
            qy * twelfth,
            qx * half,
            qy * half,
            qz * half,
            0.0,
            qz * twelfth,
            -qy * twelfth,
        ],
        dtype=np.float64,
    )


def _flatten_patterns(
    model: dict[str, Any],
    source_kind: str,
    source_id: str,
) -> dict[str, float]:
    if source_kind == "pattern":
        return {source_id: 1.0}
    combinations = {row["id"]: row for row in model["load_combinations"]}

    def visit(
        combination_id: str, factor: float, active: tuple[str, ...]
    ) -> dict[str, float]:
        if combination_id in active:
            raise ValueError("parity pack contains a cyclic combination")
        result: dict[str, float] = {}
        for term in combinations[combination_id]["terms"]:
            weighted = factor * float(term["factor"])
            if term["ref_kind"] == "load_pattern":
                result[term["ref_id"]] = result.get(term["ref_id"], 0.0) + weighted
            else:
                for pattern_id, nested_factor in visit(
                    term["ref_id"], weighted, (*active, combination_id)
                ).items():
                    result[pattern_id] = result.get(pattern_id, 0.0) + nested_factor
        return result

    return visit(source_id, 1.0, ())


def _reference_result(
    model: dict[str, Any], source_kind: str, source_id: str
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    coefficients = _flatten_patterns(model, source_kind, source_id)
    patterns = {row["id"]: row for row in model["load_patterns"]}
    node_rows = sorted(model["nodes"], key=lambda row: row["index"])
    node_order = [row["id"] for row in node_rows]
    if len(node_order) != len(set(node_order)):
        raise ValueError("parity reference node ids must be unique")
    node_index = {node_id: index for index, node_id in enumerate(node_order)}
    nodes = {row["id"]: row for row in node_rows}
    ndof = len(node_order) * 6
    global_stiffness = np.zeros((ndof, ndof), dtype=np.float64)
    element_states: dict[str, dict[str, Any]] = {}

    element_rows = sorted(model["elements"], key=lambda row: row["index"])
    element_ids = [row["id"] for row in element_rows]
    if len(element_ids) != len(set(element_ids)):
        raise ValueError("parity reference member ids must be unique")
    for element in element_rows:
        start = np.asarray(
            nodes[element["node_ids"][0]]["coordinates_m"], dtype=np.float64
        )
        end = np.asarray(
            nodes[element["node_ids"][1]]["coordinates_m"], dtype=np.float64
        )
        offset_i = np.asarray(element["offsets"]["i_global_m"], dtype=np.float64)
        offset_j = np.asarray(element["offsets"]["j_global_m"], dtype=np.float64)
        effective_start = start + offset_i
        effective_end = end + offset_j
        length_m = float(np.linalg.norm(effective_end - effective_start))
        rotation = frame_rotation_matrix(
            effective_start,
            effective_end,
            roll_deg=np.degrees(float(element["local_axis_rotation_rad"])),
        )
        transform = frame_transform(rotation) @ rigid_end_offset_transform(
            offset_i, offset_j
        )
        section = _section(model, element)
        local_stiffness = local_timoshenko_frame_stiffness(section, length_m)
        released = np.asarray(
            [
                *[RELEASE_DOF[item] for item in element["releases"]["i"]],
                *[6 + RELEASE_DOF[item] for item in element["releases"]["j"]],
            ],
            dtype=int,
        )
        condensed_stiffness, _ = _condense_releases(
            local_stiffness, np.zeros(12, dtype=np.float64), released
        )
        dofs = np.asarray(
            [
                *range(node_index[element["node_ids"][0]] * 6, node_index[element["node_ids"][0]] * 6 + 6),
                *range(node_index[element["node_ids"][1]] * 6, node_index[element["node_ids"][1]] * 6 + 6),
            ],
            dtype=int,
        )
        global_stiffness[np.ix_(dofs, dofs)] += (
            transform.T @ condensed_stiffness @ transform
        )
        material = next(
            row for row in model["materials"] if row["id"] == element["material_id"]
        )
        element_states[element["id"]] = {
            "dofs": dofs,
            "rotation": rotation,
            "transform": transform,
            "local_stiffness": local_stiffness,
            "condensed_stiffness": condensed_stiffness,
            "released": released,
            "length_m": length_m,
            "density": float(material["parameters"]["density_kg_m3"]),
            "area": section.frame.area_m2,
            "local_equivalent": np.zeros(12, dtype=np.float64),
        }

    global_load = np.zeros(ndof, dtype=np.float64)

    for pattern_id, factor in coefficients.items():
        pattern = patterns[pattern_id]
        for load in pattern["nodal_loads"]:
            base = node_index[load["node_id"]] * 6
            global_load[base : base + 6] += factor * np.asarray(
                [float(load["components_si"][key]) / 1_000.0 for key in COMPONENTS]
            )
        member_loads: dict[str, np.ndarray] = {}
        for load in pattern.get("uniform_member_loads", []):
            if load["member_id"] not in element_states:
                raise ValueError("parity reference member load id is unknown")
            member_loads.setdefault(load["member_id"], np.zeros(3, dtype=np.float64))
            member_loads[load["member_id"]] += np.asarray(
                [float(load["components_si"][key]) / 1_000.0 for key in ("QX", "QY", "QZ")]
            )
        for element in element_rows:
            state = element_states[element["id"]]
            gravity_global_kn_m = (
                state["density"]
                * state["area"]
                * GRAVITY_M_S2
                * np.asarray(pattern["self_weight"], dtype=np.float64)
                / 1_000.0
            )
            local_line_load = member_loads.get(
                element["id"], np.zeros(3, dtype=np.float64)
            ) + state["rotation"] @ gravity_global_kn_m
            raw_equivalent = _uniform_equivalent(local_line_load, state["length_m"])
            _, condensed_equivalent = _condense_releases(
                state["local_stiffness"], raw_equivalent, state["released"]
            )
            state["local_equivalent"] += factor * condensed_equivalent
            global_load[state["dofs"]] += factor * (
                state["transform"].T @ condensed_equivalent
            )

    restrained: set[int] = set()
    for constraint in model["constraints"]:
        base = node_index[constraint["node_id"]] * 6
        restrained.update(base + DOFS.index(dof) for dof in constraint["dofs"])
    free = np.asarray(
        [index for index in range(ndof) if index not in restrained], dtype=int
    )
    displacement = np.zeros(ndof, dtype=np.float64)
    displacement[free] = np.linalg.solve(
        global_stiffness[np.ix_(free, free)], global_load[free]
    )
    reaction_kn = global_stiffness @ displacement - global_load
    return (
        {
            node_id: displacement[index * 6 : index * 6 + 6]
            for index, node_id in enumerate(node_order)
        },
        {
            node_id: reaction_kn[index * 6 : index * 6 + 6] * 1_000.0
            for index, node_id in enumerate(node_order)
        },
        {
            element["id"]: (
                element_states[element["id"]]["condensed_stiffness"]
                @ (
                    element_states[element["id"]]["transform"]
                    @ displacement[element_states[element["id"]]["dofs"]]
                )
                - element_states[element["id"]]["local_equivalent"]
            )
            * 1_000.0
            for element in element_rows
        },
    )


def _rows_by_stable_id(
    rows: list[dict[str, Any]], key: str, expected_ids: list[str]
) -> list[dict[str, Any]]:
    actual_ids = [str(row.get(key, "")) for row in rows]
    if len(actual_ids) != len(set(actual_ids)):
        raise RuntimeError(f"native ResultIR contains duplicate {key}")
    if set(actual_ids) != set(expected_ids):
        raise RuntimeError(f"native ResultIR {key} set mismatch")
    by_id = dict(zip(actual_ids, rows, strict=True))
    return [by_id[row_id] for row_id in expected_ids]


def _run_native(
    executable: Path,
    model_path: Path,
    source_kind: str,
    source_id: str,
    result_id: str,
) -> dict[str, Any]:
    selection = "--load-pattern" if source_kind == "pattern" else "--load-combination"
    completed = subprocess.run(
        [
            str(executable),
            "model",
            "analyze-frame3d",
            str(model_path),
            selection,
            source_id,
            "--result-id",
            result_id,
            "--output",
            "result-ir",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"native Frame3D CLI failed for {result_id}: {detail}")
    payload = json.loads(completed.stdout)
    if payload.get("schema_version") != RESULT_SCHEMA:
        raise RuntimeError(
            f"native Frame3D CLI returned a non-ResultIR payload for {result_id}"
        )
    return payload


def _normalized_error(actual: np.ndarray, expected: np.ndarray, floor: float) -> float:
    scale = max(
        float(np.max(np.abs(actual))),
        float(np.max(np.abs(expected))),
        floor,
    )
    return float(np.max(np.abs(actual - expected)) / scale)


def _case_result(
    executable: Path,
    temporary: Path,
    case: tuple[str, list[str], dict[str, Any], str, str],
) -> dict[str, Any]:
    case_id, features, model, source_kind, source_id = case
    document = parse_model_ir_v2(model)
    model_path = temporary / f"{case_id}.model-ir.json"
    model_path.write_text(document.canonical_json, encoding="utf-8")
    result = _run_native(
        executable,
        model_path,
        source_kind,
        source_id,
        f"parity.{case_id}",
    )
    bindings = result["bindings"]
    if (
        bindings["model_content_hash"] != document.content_hash
        or bindings["model_semantic_hash"] != document.semantic_hash
        or bindings["model_provenance_hash"] != document.provenance_hash
    ):
        raise RuntimeError(f"native ResultIR model binding mismatch for {case_id}")
    if source_kind == "pattern":
        if (
            bindings["load_pattern_id"] != source_id
            or bindings["load_combination_id"] is not None
        ):
            raise RuntimeError(
                f"native ResultIR load-pattern binding mismatch for {case_id}"
            )
    elif (
        bindings["load_combination_id"] != source_id
        or bindings["load_pattern_id"] is not None
    ):
        raise RuntimeError(
            f"native ResultIR load-combination binding mismatch for {case_id}"
        )
    if (
        result["authority_profile"] != RESULT_AUTHORITY_PROFILE
        or result["promotion_basis"] != RESULT_PROMOTION_BASIS
        or result["authority"]["engineering_design"] != "not_authoritative"
        or result["authority"]["release_readiness"] != "not_authoritative"
        or result["claim_boundary"]["external_validation_established"] is not False
        or result["claim_boundary"]["cpu_hip_parity_established"] is not False
    ):
        raise RuntimeError(f"native ResultIR authority boundary mismatch for {case_id}")

    expected_displacement, expected_reaction, expected_member_force = _reference_result(
        model, source_kind, source_id
    )
    node_ids = list(expected_displacement)
    member_ids = list(expected_member_force)
    native_nodes = _rows_by_stable_id(result["nodes"], "node_id", node_ids)
    native_members = _rows_by_stable_id(result["members"], "member_id", member_ids)
    actual_displacement = np.asarray(
        [row["displacement_m_rad"] for row in native_nodes], dtype=np.float64
    )
    expected_displacement_array = np.asarray(
        [expected_displacement[node_id] for node_id in node_ids], dtype=np.float64
    )
    actual_reaction = np.asarray(
        [row["reaction_n_nm"] for row in native_nodes], dtype=np.float64
    )
    expected_reaction_array = np.asarray(
        [expected_reaction[node_id] for node_id in node_ids], dtype=np.float64
    )
    actual_member_force = np.asarray(
        [
            [*row["end_i_force_n_nm"], *row["end_j_force_n_nm"]]
            for row in native_members
        ],
        dtype=np.float64,
    )
    expected_member_force_array = np.asarray(
        [expected_member_force[member_id] for member_id in member_ids],
        dtype=np.float64,
    )
    metrics = {
        "displacement_scaled_linf": _normalized_error(
            actual_displacement, expected_displacement_array, 1.0e-12
        ),
        "reaction_scaled_linf": _normalized_error(
            actual_reaction, expected_reaction_array, 1.0e-6
        ),
        "member_force_scaled_linf": _normalized_error(
            actual_member_force, expected_member_force_array, 1.0e-6
        ),
    }
    gates = result["gates"]
    gate_metrics = (
        float(gates["free_residual_scaled_linf"]),
        float(gates["global_force_balance_scaled_linf"]),
        float(gates["global_moment_balance_scaled_linf"]),
        float(gates["member_force_replay_scaled_linf"]),
    )
    if (
        metrics["displacement_scaled_linf"] > DISPLACEMENT_TOLERANCE
        or metrics["reaction_scaled_linf"] > FORCE_TOLERANCE
        or metrics["member_force_scaled_linf"] > FORCE_TOLERANCE
        or not gates["native_residual_gate_passed"]
        or not gates["global_resultant_gate_passed"]
        or not gates["independent_recovery_replay_passed"]
        or max(gate_metrics) > GATE_TOLERANCE
        or gates["fallback_count"] != 0
        or gates["regularization_count"] != 0
    ):
        raise RuntimeError(
            f"native Frame3D parity gate failed for {case_id}: {metrics}"
        )
    reference_hash = _sha256_bytes(
        _canonical_bytes(
            {
                "nodes": [
                    {
                        "node_id": node_id,
                        "displacement_m_rad": expected_displacement[node_id].tolist(),
                        "reaction_n_nm": expected_reaction[node_id].tolist(),
                    }
                    for node_id in node_ids
                ],
                "members": [
                    {
                        "member_id": member_id,
                        "end_force_n_nm": expected_member_force[member_id].tolist(),
                    }
                    for member_id in member_ids
                ],
            }
        )
    )
    return {
        "case_id": case_id,
        "status": "pass",
        "features": features,
        "model_content_hash": document.content_hash,
        "model_semantic_hash": document.semantic_hash,
        "model_provenance_hash": document.provenance_hash,
        "load_source": {"kind": source_kind, "id": source_id},
        "result_id": result["result_id"],
        "result_hash": result["result_hash"],
        "result_authority_profile": result["authority_profile"],
        "result_promotion_basis": result["promotion_basis"],
        "python_reference_hash": reference_hash,
        "metrics": metrics,
        "native_gates": {
            "free_residual_scaled_linf": gates["free_residual_scaled_linf"],
            "global_force_balance_scaled_linf": gates[
                "global_force_balance_scaled_linf"
            ],
            "global_moment_balance_scaled_linf": gates[
                "global_moment_balance_scaled_linf"
            ],
            "member_force_replay_scaled_linf": gates["member_force_replay_scaled_linf"],
        },
    }


def run_pack(executable: Path, *, profile: str = "v1") -> dict[str, Any]:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"structural-cli executable not found: {executable}")
    version = subprocess.run(
        [str(executable), "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    cases = [
        _mixed_rotated_offset_case(),
        _released_uniform_case(),
        _nested_combination_case(),
    ]
    if profile in {"expanded-v2", "alpha-upper-v3"}:
        cases.extend(
            [
                _two_member_chain_case(),
                _planar_portal_case(),
                _spatial_corner_case(),
                _continuous_multiple_support_case(),
            ]
        )
        if profile == "alpha-upper-v3":
            cases.extend(
                [
                    _alpha_upper_moment_frame_case(),
                    _alpha_upper_braced_frame_case(),
                    _alpha_upper_irregular_spatial_case(),
                    _alpha_upper_multiple_support_case(),
                    _alpha_upper_mixed_feature_case(),
                ]
            )
    elif profile != "v1":
        raise ValueError(f"unknown parity profile: {profile}")
    with tempfile.TemporaryDirectory(
        prefix="native-frame3d-modelir-parity-"
    ) as directory:
        case_results = [
            _case_result(executable, Path(directory), case) for case in cases
        ]
    source_paths = [
        ROOT / "src/structural_analysis/elements/frame3d.py",
        ROOT / "src/structural_analysis/elements/timoshenko_frame3d.py",
        Path(__file__).resolve(),
    ]
    return {
        "schema_version": (
            SCHEMA_VERSION_V3
            if profile == "alpha-upper-v3"
            else SCHEMA_VERSION_V2
            if profile == "expanded-v2"
            else SCHEMA_VERSION_V1
        ),
        "status": "pass",
        "native_cli_version": version,
        "native_cli_sha256": _sha256_file(executable),
        "reference_source_hashes": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "content_hash": _sha256_file(path),
            }
            for path in source_paths
        ],
        "tolerances": {
            "displacement_scaled_linf": DISPLACEMENT_TOLERANCE,
            "reaction_scaled_linf": FORCE_TOLERANCE,
            "member_force_scaled_linf": FORCE_TOLERANCE,
            "native_gate_scaled_linf": GATE_TOLERANCE,
        },
        "cases": case_results,
        "authority": {
            "implementation_verification": "bounded_cross_implementation",
            "external_code_comparison": "not_evaluated",
            "experimental_validation": "not_established",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": (
            "twelve_case_alpha_upper_modelir_python_native_differential_verification_"
            "not_industry_medium_external_validation_or_release_authority"
            if profile == "alpha-upper-v3"
            else "seven_case_multi_member_modelir_python_native_differential_verification_"
            "not_external_validation_or_release_authority"
            if profile == "expanded-v2"
            else "three_case_modelir_adapter_python_native_differential_verification_"
            "not_external_validation_or_release_authority"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structural-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--profile", choices=("v1", "expanded-v2", "alpha-upper-v3"), default="v1"
    )
    arguments = parser.parse_args()
    payload = run_pack(arguments.structural_cli, profile=arguments.profile)
    encoded = _canonical_bytes(payload) + b"\n"
    if arguments.output is None:
        sys.stdout.buffer.write(encoded)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_bytes(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
