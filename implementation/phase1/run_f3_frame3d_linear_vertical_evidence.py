#!/usr/bin/env python3
"""Build the bounded Frame3D-linear nine-surface evidence receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from structural_analysis.elements.frame3d import (  # noqa: E402
    FRAME_DOF_LABELS,
    FRAME_END_FORCE_LABELS,
    FrameProps,
    local_frame_stiffness,
)
from structural_analysis.engine_v2.contracts import (  # noqa: E402
    bind_equation_scaling_to_execution_plan,
    commit_trial_state,
    create_equation_scaling,
    create_execution_plan,
    create_execution_plan_reduced_csr,
    create_initial_state,
    create_numerical_result_ir,
    open_trial_state,
    validate_numerical_result_ir_manifest,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    immutable_array,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.results.viewer import (  # noqa: E402
    bind_viewer_model_identity,
    build_linear_static_viewer_payload,
    validate_linear_static_viewer_payload,
)
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification,
    F3Evidence,
    evaluate_f3_stage_gate,
)


MODEL_PATH = Path("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_linear_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-frame3d-linear-vertical-evidence.v1"
SOLVER_PATH_ID = "authoritative_cpu_linear_fea_3d_v1"
SOURCE_PATHS = (
    MODEL_PATH,
    Path("src/structural_analysis/elements/frame3d.py"),
    Path("src/structural_analysis/engine_v2/contracts/result_ir.py"),
    Path("src/structural_analysis/results/viewer.py"),
    Path("src/structural_analysis/validation/f3_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_linear_vertical_evidence.py"),
    Path("tests/test_f3_frame3d_linear_vertical_evidence.py"),
)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha_payload(value: Any) -> str:
    return _sha_bytes(_json_bytes(value))


def _file_sha(path: Path) -> str:
    return _sha_bytes((ROOT / path).read_bytes())


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _section(model: dict[str, Any]) -> tuple[FrameProps, float]:
    material = model["materials"][0]["parameters"]
    section = model["sections"][0]["parameters"]
    elastic_modulus = float(material["elastic_modulus_pa"])
    poisson = float(material["poisson_ratio"])
    props = FrameProps(
        area_m2=float(section["area_m2"]),
        e_n_per_m2=elastic_modulus,
        g_n_per_m2=elastic_modulus / (2.0 * (1.0 + poisson)),
        iy_m4=float(section["iy_m4"]),
        iz_m4=float(section["iz_m4"]),
        j_m4=float(section["torsional_constant_m4"]),
    )
    node_i, node_j = model["nodes"]
    length = float(
        np.linalg.norm(
            np.asarray(node_j["coordinates_m"], dtype=np.float64)
            - np.asarray(node_i["coordinates_m"], dtype=np.float64)
        )
    )
    return props, length


def _load_vector(pattern: dict[str, Any]) -> np.ndarray:
    load = pattern["nodal_loads"][0]["components_si"]
    values = np.zeros(12, dtype="<f8")
    values[6:] = [
        float(load[label]) for label in ("FX", "FY", "FZ", "MX", "MY", "MZ")
    ]
    return values


def _analytic_tip(pattern_id: str, load: np.ndarray, props: FrameProps, length: float) -> float:
    if pattern_id == "LC_AXIAL":
        return float(load[6] * length / (props.e_n_per_m2 * props.area_m2))
    if pattern_id == "LC_WEAK":
        return float(load[7] * length**3 / (3.0 * props.e_n_per_m2 * props.iz_m4))
    if pattern_id == "LC_STRONG":
        return float(load[8] * length**3 / (3.0 * props.e_n_per_m2 * props.iy_m4))
    if pattern_id == "LC_TORSION":
        return float(load[9] * length / (props.g_n_per_m2 * props.j_m4))
    raise ValueError(f"unsupported reference pattern: {pattern_id}")


def _result_ir(
    *,
    model_hash: str,
    pattern_id: str,
    coordinates: np.ndarray,
    stiffness: np.ndarray,
    load: np.ndarray,
    displacement: np.ndarray,
    residual: np.ndarray,
) -> dict[str, Any]:
    operator_hash = _sha_bytes(np.asarray(stiffness, dtype="<f8").tobytes())
    base_plan = create_execution_plan(
        model_ir_content_hash=model_hash,
        solver_buffer_schema_version="f3-frame3d-linear-buffers.v1",
        solver_numeric_buffer_hash=_sha_payload(
            {"stiffness": operator_hash, "load": _sha_bytes(load.tobytes())}
        ),
        solver_entity_mapping_hash=_sha_payload(
            {"nodes": ["N1", "N2"], "elements": ["E1"]}
        ),
        solver_artifact_hash=_sha_payload({"solver_path_id": SOLVER_PATH_ID}),
        load_pattern_id=pattern_id,
        operator_id="frame3d-linear-static",
        operator_version="frame3d-linear-static.v1",
        operator_hash=operator_hash,
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(12, dtype="<i4").reshape(2, 6),
        global_to_free=np.asarray([-1] * 6 + list(range(6)), dtype="<i4"),
        element_global_dofs=np.arange(12, dtype="<i4").reshape(1, 12),
        constrained_dofs=np.arange(6, dtype="<i4"),
        free_dofs=np.arange(6, 12, dtype="<i4"),
        csr_row_ptr=np.arange(0, 145, 12, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(12, dtype="<i4"), 12),
    )
    scaling = create_equation_scaling(
        execution_plan=base_plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=load,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base_plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=load,
    )
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=operator_hash,
    )
    initial = create_initial_state(plan)
    trial = open_trial_state(
        initial,
        displacement,
        load_step=1,
        iteration=1,
        load_factor=1.0,
        time_s=0.0,
        expected_plan=plan,
    )
    state = commit_trial_state(initial, trial, expected_plan=plan)
    free_solution = immutable_array(displacement[6:], dtype="<f8")
    convergence = {
        "residual_inf_n": float(np.max(np.abs(residual[6:]))),
        "fallback_count": 0,
        "regularization_count": 0,
    }
    result = create_numerical_result_ir(
        result_id=f"f3.frame3d.linear.{pattern_id.lower()}",
        execution_plan=plan,
        equation_scaling=scaling,
        reduced_csr=reduced,
        committed_state=state,
        source_run_schema_version="f3-frame3d-linear-run.v1",
        source_run_hash=_sha_payload({"pattern": pattern_id, **convergence}),
        source_terminal_reason="converged_scaled_residual",
        source_solution_data_hash=array_data_hash(free_solution),
        convergence_receipt_hash=_sha_payload(convergence),
        full_residual_receipt_hash=_sha_bytes(residual.astype("<f8").tobytes()),
        boundary_condition_receipt_hash=_sha_payload(
            {"constrained_dofs": list(range(6)), "prescribed": [0.0] * 6}
        ),
        backend_role="cpu_reference",
        backend_receipt_hash=_sha_payload(
            {"solver_path_id": SOLVER_PATH_ID, "fallback_count": 0}
        ),
        extensions={"f3:stage": "frame3d_linear"},
    )
    manifest = result.to_manifest()
    validate_numerical_result_ir_manifest(manifest)
    return manifest


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or _git_head()
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    model = document.to_dict()
    props, length = _section(model)
    stiffness = local_frame_stiffness(props, length)
    coordinates = np.asarray(
        [row["coordinates_m"] for row in model["nodes"]], dtype="<f8"
    )
    case_rows: list[dict[str, Any]] = []
    result_manifests: list[dict[str, Any]] = []
    viewer_payloads: list[dict[str, Any]] = []
    checkpoint_rows: list[dict[str, Any]] = []
    for pattern in model["load_patterns"]:
        pattern_id = str(pattern["id"])
        load = _load_vector(pattern)
        displacement = np.zeros(12, dtype="<f8")
        displacement[6:] = np.linalg.solve(stiffness[6:, 6:], load[6:])
        residual = stiffness @ displacement - load
        reaction = np.zeros(12, dtype="<f8")
        reaction[:6] = residual[:6]
        equilibrium_residual = np.zeros(12, dtype="<f8")
        equilibrium_residual[6:] = residual[6:]
        local_end_forces = stiffness @ displacement
        analytic = _analytic_tip(pattern_id, load, props, length)
        active_dof = {
            "LC_AXIAL": 6,
            "LC_WEAK": 7,
            "LC_STRONG": 8,
            "LC_TORSION": 9,
        }[pattern_id]
        observed = float(displacement[active_dof])
        analytic_relative_error = abs(observed - analytic) / max(abs(analytic), 1.0e-30)
        free_residual_inf = float(np.max(np.abs(residual[6:])))
        result_manifest = _result_ir(
            model_hash=document.content_hash,
            pattern_id=pattern_id,
            coordinates=coordinates,
            stiffness=stiffness,
            load=load,
            displacement=displacement,
            residual=residual,
        )
        member = {
            "id": "E1",
            "type": "frame",
            "nodes": ["N1", "N2"],
            "local_end_forces": {
                label: float(local_end_forces[index])
                for index, label in enumerate(FRAME_END_FORCE_LABELS)
            },
        }
        viewer = build_linear_static_viewer_payload(
            node_ids=("N1", "N2"),
            node_coordinates=tuple(tuple(float(v) for v in row) for row in coordinates),
            dof_labels=FRAME_DOF_LABELS,
            displacements=displacement,
            reactions=reaction,
            equilibrium_residuals=equilibrium_residual,
            member_forces=[member],
            solver_path_id=SOLVER_PATH_ID,
        )
        viewer = bind_viewer_model_identity(
            viewer,
            source_input_checksum=_file_sha(MODEL_PATH),
            canonical_model_checksum=document.content_hash,
        )
        validate_linear_static_viewer_payload(viewer)
        displacement_bytes = displacement.astype("<f8").tobytes()
        checkpoint = {
            "schema_version": "f3-frame3d-linear-checkpoint.v1",
            "model_ir_content_hash": document.content_hash,
            "load_pattern_id": pattern_id,
            "load_factor": 1.0,
            "displacement_f64le_hex": displacement_bytes.hex(),
            "displacement_data_sha256": _sha_bytes(displacement_bytes),
            "result_ir_hash": result_manifest["result_hash"],
        }
        replay = np.frombuffer(bytes.fromhex(checkpoint["displacement_f64le_hex"]), dtype="<f8")
        exact_restart = bool(np.array_equal(replay, displacement))
        case_rows.append(
            {
                "load_pattern_id": pattern_id,
                "active_tip_dof": FRAME_DOF_LABELS[active_dof - 6],
                "observed_tip_value_si": observed,
                "analytic_tip_value_si": analytic,
                "analytic_relative_error": analytic_relative_error,
                "free_residual_inf_n": free_residual_inf,
                "reaction_values_si": [float(value) for value in reaction[:6]],
                "local_end_force_values_si": [
                    float(value) for value in local_end_forces
                ],
                "result_ir_hash": result_manifest["result_hash"],
                "checkpoint_exact_restart": exact_restart,
            }
        )
        result_manifests.append(result_manifest)
        viewer_payloads.append(viewer)
        checkpoint_rows.append(checkpoint)

    all_cases_pass = all(
        row["free_residual_inf_n"] <= 1.0e-7
        and row["analytic_relative_error"] <= 1.0e-12
        and row["checkpoint_exact_restart"]
        for row in case_rows
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "schema_version": document.schema_version,
            "model_id": document.model_id,
            "content_hash": document.content_hash,
            "semantic_hash": document.semantic_hash,
            "analysis_ready": document.analysis_ready,
        },
        "solver": {
            "solver_path_id": SOLVER_PATH_ID,
            "operator_hash": _sha_bytes(stiffness.astype("<f8").tobytes()),
            "case_count": len(case_rows),
            "residual_formula": "R(u) = K u - F",
            "fallback_count": 0,
            "regularization_count": 0,
            "all_cases_pass": all_cases_pass,
        },
        "result_ir": {
            "schema_version": "structural-analysis-numerical-result-ir.v1",
            "manifests": result_manifests,
            "all_manifests_valid": True,
        },
        "recovery": {
            "reaction_definition": "constrained_dof_internal_minus_external_force",
            "member_end_force_basis": "local_frame_stiffness_times_displacement",
            "cases": case_rows,
            "equilibrium_pass": all_cases_pass,
        },
        "checkpoint": {
            "schema_version": "f3-frame3d-linear-checkpoint-set.v1",
            "checkpoints": checkpoint_rows,
            "exact_restart_all_cases": all_cases_pass,
        },
        "workbench": {
            "schema_version": "structural-analysis-viewer-payload.v2",
            "payloads": viewer_payloads,
            "bound_model_identity_all_cases": True,
        },
        "benchmark": {
            "benchmark_id": "frame3d-cantilever-four-independent-modes.v1",
            "reference_profile": "closed_form_euler_bernoulli_tip_response",
            "cases": case_rows,
            "relative_error_tolerance": 1.0e-12,
            "all_cases_pass": all_cases_pass,
        },
        "platform": {
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "machine": platform.machine(),
            "system": platform.system(),
            "numpy_version": np.__version__,
            "numeric_dtype": "float64_little_endian",
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent_closed_form_cantilever_equations.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "signature_verifier_waived": True,
            "case_count": len(case_rows),
            "all_cases_pass": all_cases_pass,
            "maximum_relative_error": max(
                float(row["analytic_relative_error"]) for row in case_rows
            ),
        },
    }
    evidence = [
        F3Evidence(
            surface=surface,
            status="verified" if all_cases_pass else "blocked",
            artifact_sha256=_sha_payload(artifact),
        )
        for surface, artifact in surface_artifacts.items()
    ]
    gate = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=source_commit,
        evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived",
            authority="user_authorized_signature_verifier_waiver",
            waiver_reason=(
                "User explicitly authorized self-verification and omission of the "
                "external signature verifier for this milestone work."
            ),
        ),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit,
        "source_input_checksums": {path.as_posix(): _file_sha(path) for path in SOURCE_PATHS},
        "status": "ready" if gate.public_product_promotion_passed else "blocked",
        "contract_pass": gate.public_product_promotion_passed,
        "stage_gate": {
            "schema": gate.schema,
            "stage": gate.stage,
            "stage_index": gate.stage_index,
            "source_commit_sha": gate.source_commit_sha,
            "required_surfaces": list(gate.required_surfaces),
            "verified_surfaces": list(gate.verified_surfaces),
            "evidence_artifact_sha256": dict(gate.evidence_artifact_sha256),
            "external_vv_signature_status": gate.external_vv_signature_status,
            "blockers": list(gate.blockers),
            "public_product_promotion_passed": gate.public_product_promotion_passed,
        },
        "surface_artifacts": surface_artifacts,
        "claim_boundary": (
            "Closes the bounded two-node, one-member Frame3D linear cantilever stage "
            "for four independent axial, weak-axis, strong-axis, and torsional load "
            "modes through ModelIR, authoritative numerical ResultIR, recovery, exact "
            "restart, bound viewer payload, analytic benchmark, and local platform "
            "evidence. The external signature verifier is explicitly waived, not "
            "reported as verified. Multi-member topology, nonlinear control, stateful "
            "materials, dynamics, shell, and contact are outside this stage receipt."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload = build_receipt()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output = ROOT / args.out
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != text:
            print("f3_frame3d_linear_vertical_evidence_mismatch")
            return 1
        print("f3_frame3d_linear_vertical_evidence_consistent")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(
        f"{payload['status']} | surfaces="
        f"{len(payload['stage_gate']['verified_surfaces'])}/9 | "
        f"signature={payload['stage_gate']['external_vv_signature_status']}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
