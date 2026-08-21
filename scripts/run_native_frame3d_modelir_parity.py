#!/usr/bin/env python3
"""Run the bounded ModelIR -> native Frame3D -> ResultIR differential pack."""

from __future__ import annotations

import argparse
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


SCHEMA_VERSION = "structural-native-frame3d-modelir-parity-pack.v1"
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


def _section(model: dict[str, Any]) -> TimoshenkoFrame3DSection:
    element = model["elements"][0]
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    element = model["elements"][0]
    nodes = {row["id"]: row for row in model["nodes"]}
    start = np.asarray(nodes[element["node_ids"][0]]["coordinates_m"], dtype=np.float64)
    end = np.asarray(nodes[element["node_ids"][1]]["coordinates_m"], dtype=np.float64)
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
    local_stiffness = local_timoshenko_frame_stiffness(_section(model), length_m)
    released = np.asarray(
        [
            *[RELEASE_DOF[item] for item in element["releases"]["i"]],
            *[6 + RELEASE_DOF[item] for item in element["releases"]["j"]],
        ],
        dtype=int,
    )
    zero = np.zeros(12, dtype=np.float64)
    condensed_stiffness, _ = _condense_releases(local_stiffness, zero, released)
    global_stiffness = transform.T @ condensed_stiffness @ transform

    coefficients = _flatten_patterns(model, source_kind, source_id)
    patterns = {row["id"]: row for row in model["load_patterns"]}
    global_load = np.zeros(12, dtype=np.float64)
    local_equivalent = np.zeros(12, dtype=np.float64)
    material = next(
        row for row in model["materials"] if row["id"] == element["material_id"]
    )
    density = float(material["parameters"]["density_kg_m3"])
    area = _section(model).frame.area_m2
    node_order = [
        row["id"] for row in sorted(model["nodes"], key=lambda row: row["index"])
    ]
    node_index = {node_id: index for index, node_id in enumerate(node_order)}

    for pattern_id, factor in coefficients.items():
        pattern = patterns[pattern_id]
        for load in pattern["nodal_loads"]:
            base = node_index[load["node_id"]] * 6
            global_load[base : base + 6] += factor * np.asarray(
                [float(load["components_si"][key]) / 1_000.0 for key in COMPONENTS]
            )
        local_line_load = np.zeros(3, dtype=np.float64)
        for load in pattern.get("uniform_member_loads", []):
            if load["member_id"] != element["id"]:
                raise ValueError("parity pack reference supports one member")
            local_line_load += np.asarray(
                [
                    float(load["components_si"]["QX"]) / 1_000.0,
                    float(load["components_si"]["QY"]) / 1_000.0,
                    float(load["components_si"]["QZ"]) / 1_000.0,
                ]
            )
        gravity_global_kn_m = (
            density
            * area
            * GRAVITY_M_S2
            * np.asarray(pattern["self_weight"], dtype=np.float64)
            / 1_000.0
        )
        local_line_load += rotation @ gravity_global_kn_m
        raw_equivalent = _uniform_equivalent(local_line_load, length_m)
        _, condensed_equivalent = _condense_releases(
            local_stiffness, raw_equivalent, released
        )
        local_equivalent += factor * condensed_equivalent
        global_load += factor * (transform.T @ condensed_equivalent)

    restrained: set[int] = set()
    for constraint in model["constraints"]:
        base = node_index[constraint["node_id"]] * 6
        restrained.update(base + DOFS.index(dof) for dof in constraint["dofs"])
    free = np.asarray(
        [index for index in range(12) if index not in restrained], dtype=int
    )
    displacement = np.zeros(12, dtype=np.float64)
    displacement[free] = np.linalg.solve(
        global_stiffness[np.ix_(free, free)], global_load[free]
    )
    reaction_kn = global_stiffness @ displacement - global_load
    member_force_kn = (
        condensed_stiffness @ (transform @ displacement) - local_equivalent
    )
    return (
        displacement.reshape(2, 6),
        reaction_kn.reshape(2, 6) * 1_000.0,
        member_force_kn * 1_000.0,
    )


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
    actual_displacement = np.asarray(
        [row["displacement_m_rad"] for row in result["nodes"]], dtype=np.float64
    )
    actual_reaction = np.asarray(
        [row["reaction_n_nm"] for row in result["nodes"]], dtype=np.float64
    )
    actual_member_force = np.asarray(
        [
            *result["members"][0]["end_i_force_n_nm"],
            *result["members"][0]["end_j_force_n_nm"],
        ],
        dtype=np.float64,
    )
    metrics = {
        "displacement_scaled_linf": _normalized_error(
            actual_displacement, expected_displacement, 1.0e-12
        ),
        "reaction_scaled_linf": _normalized_error(
            actual_reaction, expected_reaction, 1.0e-6
        ),
        "member_force_scaled_linf": _normalized_error(
            actual_member_force, expected_member_force, 1.0e-6
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
                "displacement_m_rad": expected_displacement.tolist(),
                "reaction_n_nm": expected_reaction.tolist(),
                "member_end_force_n_nm": expected_member_force.tolist(),
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


def run_pack(executable: Path) -> dict[str, Any]:
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
        "schema_version": SCHEMA_VERSION,
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
            "three_case_modelir_adapter_python_native_differential_verification_"
            "not_external_validation_or_release_authority"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structural-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    payload = run_pack(arguments.structural_cli)
    encoded = _canonical_bytes(payload) + b"\n"
    if arguments.output is None:
        sys.stdout.buffer.write(encoded)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_bytes(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
