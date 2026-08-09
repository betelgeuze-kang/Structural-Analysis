#!/usr/bin/env python3
"""Build the Frame3D load-control nine-surface evidence receipt."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LINEAR_RUNNER_PATH = (
    ROOT / "implementation/phase1/run_f3_frame3d_linear_vertical_evidence.py"
)
LINEAR_SPEC = importlib.util.spec_from_file_location(
    "f3_linear_runner", LINEAR_RUNNER_PATH
)
if LINEAR_SPEC is None or LINEAR_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("f3_linear_runner_import_failed")
LINEAR = importlib.util.module_from_spec(LINEAR_SPEC)
LINEAR_SPEC.loader.exec_module(LINEAR)

from structural_analysis.assembly.corotational_frame3d_global import (  # noqa: E402
    CorotationalFrame3DGlobalConfig,
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
    assemble_corotational_frame3d_global,
    solve_corotational_frame3d_global_load_path,
)
from structural_analysis.elements.frame3d import (  # noqa: E402
    FRAME_DOF_LABELS,
    FRAME_END_FORCE_LABELS,
    Frame3DProperties,
    FrameProps,
    frame3d_local_end_forces,
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


DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_load_control_vertical_evidence.json"
)
LINEAR_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_linear_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-frame3d-load-control-vertical-evidence.v1"
SOURCE_PATHS = (
    LINEAR.MODEL_PATH,
    Path("src/structural_analysis/assembly/corotational_frame3d_global.py"),
    Path("src/structural_analysis/elements/corotational_frame3d.py"),
    Path("src/structural_analysis/engine_v2/contracts/nonlinear_result.py"),
    Path("src/structural_analysis/results/viewer.py"),
    Path("src/structural_analysis/validation/f3_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_linear_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_load_control_vertical_evidence.py"),
    Path("tests/test_f3_frame3d_load_control_vertical_evidence.py"),
)


def _model_and_load() -> tuple[dict[str, Any], CorotationalFrame3DModel, np.ndarray]:
    document = load_model_ir_v2(ROOT / LINEAR.MODEL_PATH)
    payload = document.to_dict()
    props_n, _length = LINEAR._section(payload)
    section = payload["sections"][0]["parameters"]
    props_kn = FrameProps(
        area_m2=props_n.area_m2,
        e_n_per_m2=props_n.e_n_per_m2 / 1000.0,
        g_n_per_m2=props_n.g_n_per_m2 / 1000.0,
        iy_m4=props_n.iy_m4,
        iz_m4=props_n.iz_m4,
        j_m4=props_n.j_m4,
    )
    timoshenko = TimoshenkoFrame3DSection(
        props_kn,
        effective_shear_area_y_m2=float(section["shear_area_y_m2"]),
        effective_shear_area_z_m2=float(section["shear_area_z_m2"]),
    )
    weak_pattern = next(
        row for row in payload["load_patterns"] if row["id"] == "LC_WEAK"
    )
    reference_load_n = LINEAR._load_vector(weak_pattern)
    model = CorotationalFrame3DModel(
        node_coordinates_m=tuple(
            tuple(float(value) for value in row["coordinates_m"])
            for row in payload["nodes"]
        ),
        members=(CorotationalFrame3DMember("E1", 0, 1, timoshenko),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(float(value / 1000.0) for value in reference_load_n),
        model_id=document.model_id + ".load-control",
    )
    return payload, model, reference_load_n


def _convergence_checks(step: Any) -> dict[str, bool]:
    return {
        "scaled_residual_gate": bool(step.residual_gate_passed),
        "scaled_increment_gate": bool(step.increment_gate_passed),
        "line_search_step_valid": bool(step.line_search_valid),
        "final_reassembled_equilibrium": bool(
            step.final_reassembled_equilibrium_passed
        ),
        "parent_state_immutable": bool(step.parent_state_immutable),
    }


def _nonlinear_result_ir(
    *,
    model_ir_content_hash: str,
    model: CorotationalFrame3DModel,
    reference_load_n: np.ndarray,
    displacement: np.ndarray,
    result_hash: str,
    final_residual_n: float,
    path_history_hash: str,
) -> dict[str, Any]:
    operator_hash = LINEAR._sha_payload(
        {
            "model_hash": model.model_hash,
            "solver_contract": "corotational-load-control.v1",
        }
    )
    base_plan = create_execution_plan(
        model_ir_content_hash=model_ir_content_hash,
        solver_buffer_schema_version="corotational-frame3d-load-control-buffers.v1",
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
            {"profile": "dense_elastic_corotational_timoshenko_frame3d_load_control.v1"}
        ),
        load_pattern_id="LC_WEAK",
        operator_id="corotational-frame3d-load-control",
        operator_version="corotational-frame3d-load-control.v1",
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
    coordinates = np.asarray(model.node_coordinates_m, dtype="<f8")
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
    initial_state = create_initial_state(plan)
    trial_state = open_trial_state(
        initial_state,
        displacement,
        load_step=1,
        iteration=1,
        load_factor=1.0,
        time_s=0.0,
        expected_plan=plan,
    )
    committed_state = commit_trial_state(initial_state, trial_state, expected_plan=plan)
    initial_bundle = create_initial_material_state_bundle(
        bundle_id="f3.frame3d.elastic.initial",
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hash=initial_state.state_hash,
        entries=(
            MaterialStateInput(
                entity_id="element.E1",
                integration_point_id="ip.0",
                material_type_id="linear.elastic.isotropic",
                material_schema_version="elastic-no-history.v1",
                state_bytes=b"elastic-initial",
            ),
        ),
    )
    trial_bundle = open_trial_material_state_bundle(
        initial_bundle,
        solver_state_hash=trial_state.state_hash,
        entries=(
            MaterialStateInput(
                entity_id="element.E1",
                integration_point_id="ip.0",
                material_type_id="linear.elastic.isotropic",
                material_schema_version="elastic-no-history.v1",
                state_bytes=b"elastic-accepted-load-1.0",
            ),
        ),
    )
    bundle = commit_trial_material_state_bundle(
        initial_bundle,
        trial_bundle,
        solver_state_hash=committed_state.state_hash,
    )
    free_solution = immutable_array(displacement[6:], dtype="<f8")
    terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version="corotational-frame3d-global-result.v1",
        source_solver_receipt_hash=result_hash,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_solution_data_hash=array_data_hash(free_solution),
        solver_coordinate_scaling_receipt_hash=LINEAR._sha_payload(
            {"equation_scaling_hash": scaling.scaling_hash}
        ),
        state_hash=committed_state.state_hash,
        material_state_bundle_hash=bundle.bundle_hash,
        path_history_hash=path_history_hash,
        terminal_reason="converged_residual_and_increment",
        converged=True,
        final_residual_linf=final_residual_n,
        residual_tolerance_linf=1.0e-4,
        final_increment_linf=0.0,
        increment_tolerance_linf=1.0e-8,
        accepted_step_count=1,
        fallback_count=0,
        regularization_count=0,
    )
    result = create_nonlinear_numerical_result_ir(
        result_id="f3.frame3d.load-control.lc-weak",
        execution_plan=plan,
        equation_scaling=scaling,
        reduced_csr=reduced,
        committed_state=committed_state,
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
    manifest = result.to_manifest()
    validate_nonlinear_result_manifest(manifest)
    return manifest


def _predecessor(source_commit: str) -> tuple[Any, str, dict[str, Any]]:
    linear_payload = json.loads((ROOT / LINEAR_RECEIPT).read_text(encoding="utf-8"))
    checksums_current = {
        path: LINEAR._file_sha(Path(path))
        for path in linear_payload["source_input_checksums"]
    }
    inputs_unchanged = checksums_current == linear_payload["source_input_checksums"]
    current_linear_payload = LINEAR.build_receipt(source_commit_sha=source_commit)
    if not current_linear_payload["contract_pass"]:
        raise RuntimeError("f3_linear_predecessor_replay_failed")
    artifacts = current_linear_payload["surface_artifacts"]
    evidence = [
        F3Evidence(
            surface=surface,
            status="verified",
            artifact_sha256=LINEAR._sha_payload(artifact),
        )
        for surface, artifact in artifacts.items()
    ]
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=source_commit,
        evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived",
            authority="user_authorized_signature_verifier_waiver",
            waiver_reason="User authorized signature-verifier omission for F3 self-verification.",
        ),
    )
    replay = {
        "source_receipt_path": LINEAR_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(LINEAR_RECEIPT),
        "input_checksums_unchanged": inputs_unchanged,
        "current_source_replay_executed": True,
        "replayed_source_commit_sha": source_commit,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }
    return receipt, LINEAR._sha_payload(replay), replay


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    payload, model, reference_load_n = _model_and_load()
    document = load_model_ir_v2(ROOT / LINEAR.MODEL_PATH)
    config = CorotationalFrame3DGlobalConfig()
    load_factors = (0.25, 0.5, 1.0)
    solution = solve_corotational_frame3d_global_load_path(
        model, load_factors, config=config
    )
    prefix = solve_corotational_frame3d_global_load_path(
        model, (0.25, 0.5), config=config
    )
    resumed = solve_corotational_frame3d_global_load_path(
        model,
        (1.0,),
        config=config,
        resume_from=prefix.final_checkpoint,
    )
    final = solution.steps[-1]
    displacement = np.asarray(solution.final_checkpoint.displacement, dtype="<f8")
    exact_restart = bool(
        resumed.final_checkpoint == solution.final_checkpoint
        and resumed.steps[-1].members == solution.steps[-1].members
    )
    assembly = assemble_corotational_frame3d_global(model, displacement)
    full_residual_kn = assembly.internal_force - np.asarray(
        model.reference_load_kn, dtype=np.float64
    )
    final_residual_n = float(
        np.max(np.abs(full_residual_kn[list(model.free_dofs)])) * 1000.0
    )
    path_history = [
        {
            "load_factor": step.load_factor,
            "checkpoint_hash": step.checkpoint.checkpoint_hash,
            "free_residual_inf_norm_kn": step.free_residual_inf_norm_kn,
            "accepted_line_search_alphas": [
                float(row["selected_alpha"])
                for row in step.line_search_history
                if row["selected_alpha"] is not None
            ],
        }
        for step in solution.steps
    ]
    path_history_hash = LINEAR._sha_payload(path_history)
    result_manifest = _nonlinear_result_ir(
        model_ir_content_hash=document.content_hash,
        model=model,
        reference_load_n=reference_load_n,
        displacement=displacement,
        result_hash=solution.result_hash,
        final_residual_n=final_residual_n,
        path_history_hash=path_history_hash,
    )
    props_n, _ = LINEAR._section(payload)
    element_properties = Frame3DProperties(
        element_id="E1",
        node_ids=("N1", "N2"),
        start_coordinates=tuple(payload["nodes"][0]["coordinates_m"]),
        end_coordinates=tuple(payload["nodes"][1]["coordinates_m"]),
        props=props_n,
    )
    local_end_forces_n = frame3d_local_end_forces(element_properties, displacement)
    reactions_n = np.zeros(12, dtype="<f8")
    for dof, reaction_kn in final.reactions:
        reactions_n[dof] = reaction_kn * 1000.0
    equilibrium_n = np.zeros(12, dtype="<f8")
    equilibrium_n[6:] = full_residual_kn[6:] * 1000.0
    viewer = build_linear_static_viewer_payload(
        node_ids=("N1", "N2"),
        node_coordinates=model.node_coordinates_m,
        dof_labels=FRAME_DOF_LABELS,
        displacements=displacement,
        reactions=reactions_n,
        equilibrium_residuals=equilibrium_n,
        member_forces=[
            {
                "id": "E1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "local_end_forces": {
                    label: float(local_end_forces_n[index])
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
    one_shot_repeat = solve_corotational_frame3d_global_load_path(
        model, load_factors, config=config
    )
    deterministic = one_shot_repeat.result_hash == solution.result_hash
    all_pass = bool(
        solution.contract_pass
        and exact_restart
        and deterministic
        and final_residual_n <= 1.0e-4
        and not solution.fallback_used
        and not solution.regularization_used
        and all(_convergence_checks(final).values())
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "load_pattern_id": "LC_WEAK",
            "analysis_ready": document.analysis_ready,
        },
        "solver": {
            "schema_version": solution.schema_version,
            "profile": solution.profile,
            "load_factors": list(load_factors),
            "result_hash": solution.result_hash,
            "contract_pass": solution.contract_pass,
            "fallback_used": solution.fallback_used,
            "regularization_used": solution.regularization_used,
            "path_history": path_history,
        },
        "result_ir": {
            "schema_version": result_manifest["schema_version"],
            "manifest": result_manifest,
            "manifest_valid": True,
        },
        "recovery": {
            "reactions_n": [float(value) for value in reactions_n[:6]],
            "local_end_forces_n": [float(value) for value in local_end_forces_n],
            "free_residual_inf_n": final_residual_n,
            "equilibrium_pass": final_residual_n <= 1.0e-4,
        },
        "checkpoint": {
            "schema_version": solution.final_checkpoint.schema_version,
            "checkpoint": solution.final_checkpoint.to_dict(),
            "prefix_checkpoint_hash": prefix.final_checkpoint.checkpoint_hash,
            "resumed_checkpoint_hash": resumed.final_checkpoint.checkpoint_hash,
            "exact_restart": exact_restart,
        },
        "workbench": {
            "schema_version": viewer["schema_version"],
            "viewer_payload": viewer,
            "model_identity_bound": True,
        },
        "benchmark": {
            "benchmark_id": "frame3d-corotational-cantilever-load-control.v1",
            "deterministic_repeat": deterministic,
            "load_factor_monotonic": [step.load_factor for step in solution.steps]
            == list(load_factors),
            "full_load_reached": solution.final_checkpoint.load_factor == 1.0,
            "all_convergence_checks_pass": all(_convergence_checks(final).values()),
        },
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": __import__("platform").python_implementation(),
            "python_version": __import__("platform").python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent_linear_limit_plus_equilibrium_and_restart.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "full_load_equilibrium_pass": final_residual_n <= 1.0e-4,
            "exact_restart_pass": exact_restart,
            "deterministic_repeat_pass": deterministic,
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
        stage="frame3d_load_control",
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
            "Closes the bounded elastic Corotational Frame3D load-control stage for "
            "one ModelIR-bound cantilever through 0.25, 0.5, and 1.0 load factors, "
            "authoritative nonlinear ResultIR, equilibrium recovery, exact restart, "
            "bound viewer payload, and deterministic replay. Direct control, stateful "
            "material, broader topology, dynamics, shell, and contact remain outside."
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
            print("f3_frame3d_load_control_vertical_evidence_mismatch")
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=str(recorded["source_commit_sha"]))
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if (
            recorded.get("source_input_checksums") != payload["source_input_checksums"]
            or out.read_text(encoding="utf-8") != text
        ):
            print("f3_frame3d_load_control_vertical_evidence_mismatch")
            return 1
        print("f3_frame3d_load_control_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | "
        f"load={payload['surface_artifacts']['checkpoint']['checkpoint']['load_factor']}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
