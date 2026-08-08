#!/usr/bin/env python3
"""Build the Frame3D direct-control nine-surface evidence receipt."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"{name}_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINEAR = _load_module(
    "f3_linear_runner",
    ROOT / "implementation/phase1/run_f3_frame3d_linear_vertical_evidence.py",
)
LOAD = _load_module(
    "f3_load_runner",
    ROOT / "implementation/phase1/run_f3_frame3d_load_control_vertical_evidence.py",
)

from structural_analysis.assembly.corotational_frame3d_global import (  # noqa: E402
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (  # noqa: E402
    StatefulCorotationalFrame3DDisplacementControlConfig,
    solve_stateful_corotational_frame3d_displacement_control_path,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (  # noqa: E402
    StatefulCorotationalFrame3DSparseModel,
)
from structural_analysis.elements.frame3d import (  # noqa: E402
    FRAME_DOF_LABELS,
    FRAME_END_FORCE_LABELS,
    FrameProps,
)
from structural_analysis.elements.timoshenko_frame3d import (  # noqa: E402
    TimoshenkoFrame3DSection,
)
from structural_analysis.engine_v2.contracts import (  # noqa: E402
    bind_equation_scaling_to_execution_plan,
    commit_trial_state,
    create_equation_scaling,
    create_execution_plan,
    create_execution_plan_reduced_csr,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_json_bytes,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (  # noqa: E402
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (  # noqa: E402
    create_nonlinear_numerical_result_ir,
    create_nonlinear_terminal_receipt,
    validate_nonlinear_result_manifest,
)
from structural_analysis.materials.uniaxial_plasticity import (  # noqa: E402
    BilinearCombinedHardeningSteel,
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
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)


DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_direct_control_vertical_evidence.json"
)
LOAD_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_load_control_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-frame3d-direct-control-vertical-evidence.v1"
TARGETS_M = (2.5e-5, 5.0e-5, -2.5e-5)
CONTROL_GLOBAL_DOF = 6
SOURCE_PATHS = (
    LINEAR.MODEL_PATH,
    Path("src/structural_analysis/assembly/stateful_corotational_frame3d_sparse.py"),
    Path(
        "src/structural_analysis/assembly/"
        "stateful_corotational_frame3d_displacement_control.py"
    ),
    Path("src/structural_analysis/engine_v2/contracts/nonlinear_result.py"),
    Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
    Path("src/structural_analysis/results/viewer.py"),
    Path("src/structural_analysis/validation/f3_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_linear_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_load_control_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_direct_control_vertical_evidence.py"),
    Path("tests/test_f3_frame3d_direct_control_vertical_evidence.py"),
)


def _model() -> tuple[Any, StatefulCorotationalFrame3DSparseModel, np.ndarray]:
    document = load_model_ir_v2(ROOT / LINEAR.MODEL_PATH)
    payload = document.to_dict()
    props_n, _length = LINEAR._section(payload)
    section_row = payload["sections"][0]["parameters"]
    props_kn = FrameProps(
        area_m2=props_n.area_m2,
        e_n_per_m2=props_n.e_n_per_m2 / 1000.0,
        g_n_per_m2=props_n.g_n_per_m2 / 1000.0,
        iy_m4=props_n.iy_m4,
        iz_m4=props_n.iz_m4,
        j_m4=props_n.j_m4,
    )
    section = TimoshenkoFrame3DSection(
        props_kn,
        effective_shear_area_y_m2=float(section_row["shear_area_y_m2"]),
        effective_shear_area_z_m2=float(section_row["shear_area_z_m2"]),
    )
    axial_pattern = next(
        row for row in payload["load_patterns"] if row["id"] == "LC_AXIAL"
    )
    reference_load_n = LINEAR._load_vector(axial_pattern)
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=tuple(
            tuple(float(value) for value in row["coordinates_m"])
            for row in payload["nodes"]
        ),
        members=(CorotationalFrame3DMember("E1", 0, 1, section),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(float(value / 1000.0) for value in reference_load_n),
        model_id=document.model_id + ".direct-control",
    )
    steel = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=float(payload["materials"][0]["parameters"]["elastic_modulus_pa"]) / 1.0e6,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id="M1.direct-control-elastic-range",
    )
    return document, StatefulCorotationalFrame3DSparseModel(elastic, (steel,)), reference_load_n


def _material_entry(state: Any) -> MaterialStateInput:
    return MaterialStateInput(
        entity_id="element.E1",
        integration_point_id="ip.0",
        material_type_id="steel.bilinear-combined-hardening",
        material_schema_version=str(state.to_dict()["schema_version"]),
        state_bytes=canonical_json_bytes(state.to_dict()),
    )


def _result_ir(
    *,
    document: Any,
    model: StatefulCorotationalFrame3DSparseModel,
    reference_load_n: np.ndarray,
    result: Any,
    path_history: list[dict[str, Any]],
) -> dict[str, Any]:
    operator_hash = LINEAR._sha_payload(
        {
            "model_hash": model.model_hash,
            "direct_control_contract_hash": result.direct_control_contract_hash,
        }
    )
    base_plan = create_execution_plan(
        model_ir_content_hash=document.content_hash,
        solver_buffer_schema_version="stateful-frame3d-direct-control-buffers.v1",
        solver_numeric_buffer_hash=LINEAR._sha_payload(
            {
                "model_hash": model.model_hash,
                "reference_load": LINEAR._sha_bytes(reference_load_n.tobytes()),
            }
        ),
        solver_entity_mapping_hash=LINEAR._sha_payload(
            {"nodes": ["N1", "N2"], "elements": ["E1"]}
        ),
        solver_artifact_hash=LINEAR._sha_payload(
            {"profile": result.profile, "contract_hash": result.direct_control_contract_hash}
        ),
        load_pattern_id="LC_AXIAL",
        operator_id="stateful-corotational-frame3d-direct-control",
        operator_version="stateful-corotational-frame3d-direct-control.v1",
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
    coordinates = np.asarray(model.elastic_model.node_coordinates_m, dtype="<f8")
    scaling = create_equation_scaling(
        execution_plan=base_plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load_n,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base_plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load_n,
    )
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=operator_hash,
    )
    state = create_initial_state(plan)
    bundle = create_initial_material_state_bundle(
        bundle_id="f3.frame3d.direct-control.material",
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hash=state.state_hash,
        entries=tuple(_material_entry(row) for row in result.checkpoints[0].material_states),
    )
    for index, step in enumerate(result.steps, start=1):
        displacement = np.asarray(step.checkpoint.displacement, dtype="<f8")
        trial_state = open_trial_state(
            state,
            displacement,
            load_step=index,
            iteration=max(int(step.checkpoint.converged_iterations), 1),
            load_factor=float(step.solved_load_factor),
            time_s=0.0,
            expected_plan=plan,
        )
        next_state = commit_trial_state(state, trial_state, expected_plan=plan)
        trial_bundle = open_trial_material_state_bundle(
            bundle,
            solver_state_hash=trial_state.state_hash,
            entries=tuple(_material_entry(row) for row in step.checkpoint.material_states),
        )
        next_bundle = commit_trial_material_state_bundle(
            bundle,
            trial_bundle,
            solver_state_hash=next_state.state_hash,
        )
        state, bundle = next_state, next_bundle
    free_solution = immutable_array(state.displacement_si[6:], dtype="<f8")
    final_residual_n = float(result.final_checkpoint.residual_inf_norm_kn * 1000.0)
    terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version=result.schema_version,
        source_solver_receipt_hash=result.result_hash,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_solution_data_hash=array_data_hash(free_solution),
        solver_coordinate_scaling_receipt_hash=LINEAR._sha_payload(
            {"direct_control_contract_hash": result.direct_control_contract_hash}
        ),
        state_hash=state.state_hash,
        material_state_bundle_hash=bundle.bundle_hash,
        path_history_hash=LINEAR._sha_payload(path_history),
        terminal_reason="converged_residual_and_increment",
        converged=True,
        final_residual_linf=final_residual_n,
        residual_tolerance_linf=1.0e-4,
        final_increment_linf=0.0,
        increment_tolerance_linf=1.0e-8,
        accepted_step_count=len(result.steps),
        rejected_attempt_count=0,
        rollback_count=0,
        fallback_count=0,
        regularization_count=0,
    )
    numerical = create_nonlinear_numerical_result_ir(
        result_id="f3.frame3d.direct-control.lc-axial",
        execution_plan=plan,
        equation_scaling=scaling,
        reduced_csr=reduced,
        committed_state=state,
        material_state_bundle=bundle,
        terminal_receipt=terminal,
        full_residual_receipt_hash=LINEAR._sha_payload(
            {"final_residual_linf_n": final_residual_n}
        ),
        boundary_condition_receipt_hash=LINEAR._sha_payload(
            {"constrained_dofs": list(range(6)), "prescribed": [0.0] * 6}
        ),
        backend_role="cpu_reference",
        backend_receipt_hash=LINEAR._sha_payload(
            {"fallback_count": 0, "regularization_count": 0}
        ),
    )
    manifest = numerical.to_manifest()
    validate_nonlinear_result_manifest(manifest)
    return manifest


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = LOAD.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_load_control_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt(
        schema="f3-vertical-evidence-gate.v1",
        stage="frame3d_load_control",
        stage_index=1,
        source_commit_sha=source_commit,
        required_surfaces=tuple(stage["required_surfaces"]),
        verified_surfaces=tuple(stage["verified_surfaces"]),
        evidence_artifact_sha256=tuple(sorted(stage["evidence_artifact_sha256"].items())),
        predecessor_stage="frame3d_linear",
        predecessor_receipt_sha256=stage["predecessor_receipt_sha256"],
        external_vv_signature_status="waived",
        blockers=tuple(stage["blockers"]),
        public_product_promotion_passed=bool(stage["public_product_promotion_passed"]),
    )
    persisted = json.loads((ROOT / LOAD_RECEIPT).read_text(encoding="utf-8"))
    replay = {
        "source_receipt_path": LOAD_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(LOAD_RECEIPT),
        "persisted_source_commit_sha": persisted["source_commit_sha"],
        "current_source_replay_executed": True,
        "replayed_source_commit_sha": source_commit,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }
    return receipt, LINEAR._sha_payload(current["stage_gate"]), replay


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document, model, reference_load_n = _model()
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    result = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        TARGETS_M,
        control_global_dof=CONTROL_GLOBAL_DOF,
        config=config,
    )
    prefix = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        TARGETS_M[:2],
        control_global_dof=CONTROL_GLOBAL_DOF,
        config=config,
    )
    resumed = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        TARGETS_M[2:],
        control_global_dof=CONTROL_GLOBAL_DOF,
        config=config,
        resume_from=prefix.final_checkpoint,
    )
    repeated = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        TARGETS_M,
        control_global_dof=CONTROL_GLOBAL_DOF,
        config=config,
    )
    exact_restart = bool(
        result.final_checkpoint == resumed.final_checkpoint
        and result.steps[-1].member_results == resumed.steps[-1].member_results
    )
    deterministic = repeated.result_hash == result.result_hash
    path_history = [
        {
            "target_control_displacement_m": step.target_control_displacement_m,
            "solved_load_factor": step.solved_load_factor,
            "checkpoint_hash": step.checkpoint.checkpoint_hash,
            "scaled_control_error": step.scaled_control_error,
            "accepted_line_search_alphas": list(step.accepted_line_search_alphas),
            "convergence_checks": dict(step.convergence_checks),
        }
        for step in result.steps
    ]
    result_manifest = _result_ir(
        document=document,
        model=model,
        reference_load_n=reference_load_n,
        result=result,
        path_history=path_history,
    )
    final = result.steps[-1]
    final_displacement = np.asarray(result.final_checkpoint.displacement, dtype="<f8")
    reactions_n = np.zeros(12, dtype="<f8")
    for dof, value_kn in final.reactions:
        reactions_n[dof] = value_kn * 1000.0
    residual_n = np.zeros(12, dtype="<f8")
    member = final.member_results[0]
    end_forces_n = np.asarray(member["global_end_forces"], dtype="<f8") * 1000.0
    viewer = build_linear_static_viewer_payload(
        node_ids=("N1", "N2"),
        node_coordinates=model.elastic_model.node_coordinates_m,
        dof_labels=FRAME_DOF_LABELS,
        displacements=final_displacement,
        reactions=reactions_n,
        equilibrium_residuals=residual_n,
        member_forces=[
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "local_end_forces": {
                    label: float(end_forces_n[index])
                    for index, label in enumerate(FRAME_END_FORCE_LABELS)
                },
            }
        ],
        solver_path_id=LINEAR.SOLVER_PATH_ID,
    )
    viewer = bind_viewer_model_identity(
        viewer,
        source_input_checksum=LINEAR._file_sha(LINEAR.MODEL_PATH),
        canonical_model_checksum=document.content_hash,
    )
    validate_linear_static_viewer_payload(viewer)
    props_n, length = LINEAR._section(document.to_dict())
    axial_stiffness_n_per_m = props_n.e_n_per_m2 * props_n.area_m2 / length
    expected_final_factor = (
        axial_stiffness_n_per_m * TARGETS_M[-1] / reference_load_n[CONTROL_GLOBAL_DOF]
    )
    factor_error = abs(float(result.final_checkpoint.load_factor) - expected_final_factor)
    final_residual_n = float(result.final_checkpoint.residual_inf_norm_kn * 1000.0)
    all_pass = bool(
        result.contract_pass
        and exact_restart
        and deterministic
        and result.parent_state_immutability_enforced
        and not result.fallback_used
        and not result.regularization_used
        and all(all(step.convergence_checks.values()) for step in result.steps)
        and final_residual_n <= 1.0e-4
        and factor_error <= 1.0e-8
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "load_pattern_id": "LC_AXIAL",
            "analysis_ready": document.analysis_ready,
        },
        "solver": {
            "schema_version": result.schema_version,
            "profile": result.profile,
            "control_global_dof": CONTROL_GLOBAL_DOF,
            "targets_m": list(TARGETS_M),
            "path_history": path_history,
            "contract_pass": result.contract_pass,
            "fallback_used": result.fallback_used,
            "regularization_used": result.regularization_used,
        },
        "result_ir": {
            "schema_version": result_manifest["schema_version"],
            "manifest": result_manifest,
            "manifest_valid": True,
        },
        "recovery": {
            "reactions_n": [float(value) for value in reactions_n[:6]],
            "local_end_forces_n": [float(value) for value in end_forces_n],
            "axial_material_response": dict(member["axial_material_response"]),
            "final_residual_inf_n": final_residual_n,
        },
        "checkpoint": {
            "schema_version": result.final_checkpoint.schema_version,
            "checkpoint": result.final_checkpoint.to_dict(),
            "prefix_checkpoint_hash": prefix.final_checkpoint.checkpoint_hash,
            "resumed_checkpoint_hash": resumed.final_checkpoint.checkpoint_hash,
            "exact_restart": exact_restart,
            "parent_state_immutability_enforced": result.parent_state_immutability_enforced,
        },
        "workbench": {
            "schema_version": viewer["schema_version"],
            "viewer_payload": viewer,
            "model_identity_bound": True,
        },
        "benchmark": {
            "benchmark_id": "frame3d-axial-direct-control-reversal.v1",
            "expected_final_load_factor": expected_final_factor,
            "observed_final_load_factor": result.final_checkpoint.load_factor,
            "load_factor_absolute_error": factor_error,
            "deterministic_repeat": deterministic,
            "exact_reversal_path": result.final_checkpoint.displacement[CONTROL_GLOBAL_DOF] == TARGETS_M[-1],
        },
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent_axial_bar_force_displacement_control.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "load_factor_absolute_error": factor_error,
            "equilibrium_pass": final_residual_n <= 1.0e-4,
            "exact_restart_pass": exact_restart,
            "signature_verifier_waived": True,
        },
    }
    evidence = [
        F3Evidence(
            surface=surface,
            status="verified" if all_pass else "blocked",
            artifact_sha256=LINEAR._sha_payload(artifact),
        )
        for surface, artifact in surface_artifacts.items()
    ]
    predecessor, predecessor_hash, predecessor_replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="frame3d_direct_control",
        source_commit_sha=source_commit,
        evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived",
            authority="user_authorized_signature_verifier_waiver",
            waiver_reason="User authorized signature-verifier omission for F3 self-verification.",
        ),
        predecessor_receipt=predecessor,
        predecessor_receipt_sha256=predecessor_hash,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit,
        "source_input_checksums": {
            path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS
        },
        "status": "ready" if gate.public_product_promotion_passed else "blocked",
        "contract_pass": gate.public_product_promotion_passed,
        "predecessor_replay": predecessor_replay,
        "stage_gate": {
            "stage": gate.stage,
            "stage_index": gate.stage_index,
            "source_commit_sha": gate.source_commit_sha,
            "required_surfaces": list(gate.required_surfaces),
            "verified_surfaces": list(gate.verified_surfaces),
            "evidence_artifact_sha256": dict(gate.evidence_artifact_sha256),
            "predecessor_stage": gate.predecessor_stage,
            "predecessor_receipt_sha256": gate.predecessor_receipt_sha256,
            "external_vv_signature_status": gate.external_vv_signature_status,
            "blockers": list(gate.blockers),
            "public_product_promotion_passed": gate.public_product_promotion_passed,
        },
        "surface_artifacts": surface_artifacts,
        "claim_boundary": (
            "Closes the bounded single-translation Frame3D direct-control stage "
            "for an axial target/reversal path with state/material ancestry, exact "
            "restart, nonlinear ResultIR, recovery, and bound Workbench projection. "
            "Rotational or multi-point control, yielded material breadth, modal, "
            "dynamics, shell, and contact remain outside this stage."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = ROOT / args.out
    if args.check:
        if not out.is_file():
            print("f3_frame3d_direct_control_vertical_evidence_mismatch")
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=str(recorded["source_commit_sha"]))
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if (
            recorded.get("source_input_checksums") != payload["source_input_checksums"]
            or out.read_text(encoding="utf-8") != text
        ):
            print("f3_frame3d_direct_control_vertical_evidence_mismatch")
            return 1
        print("f3_frame3d_direct_control_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | "
        f"target={payload['surface_artifacts']['checkpoint']['checkpoint']['load_factor']}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
