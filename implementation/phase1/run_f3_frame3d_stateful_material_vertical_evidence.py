#!/usr/bin/env python3
"""Build the Frame3D stateful-material nine-surface evidence receipt."""

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


DIRECT = _load_module(
    "f3_direct_runner",
    ROOT / "implementation/phase1/run_f3_frame3d_direct_control_vertical_evidence.py",
)
LINEAR = DIRECT.LINEAR

from structural_analysis.assembly.corotational_frame3d_global import (  # noqa: E402
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (  # noqa: E402
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseModel,
    solve_stateful_corotational_frame3d_sparse_load_path,
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


MODEL_PATH = Path("tests/fixtures/model_ir_v2/frame_cantilever_stateful_steel.json")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_stateful_material_vertical_evidence.json"
)
DIRECT_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_direct_control_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-frame3d-stateful-material-vertical-evidence.v1"
LOAD_FACTORS = (0.5, 1.0, -1.0, 0.25)
SOURCE_PATHS = (
    MODEL_PATH,
    Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/assembly/stateful_corotational_frame3d_sparse.py"),
    Path("src/structural_analysis/engine_v2/contracts/nonlinear_result.py"),
    Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
    Path("src/structural_analysis/results/viewer.py"),
    Path("src/structural_analysis/validation/f3_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_direct_control_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_frame3d_stateful_material_vertical_evidence.py"),
    Path("tests/test_f3_frame3d_stateful_material_vertical_evidence.py"),
)


def _model() -> tuple[Any, StatefulCorotationalFrame3DSparseModel, np.ndarray]:
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    payload = document.to_dict()
    material_row = payload["materials"][0]
    material = material_row["parameters"]
    section_row = payload["sections"][0]["parameters"]
    elastic_modulus_mpa = float(material["elastic_modulus_pa"]) / 1.0e6
    shear_modulus_mpa = elastic_modulus_mpa / (
        2.0 * (1.0 + float(material["poisson_ratio"]))
    )
    section = TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=float(section_row["area_m2"]),
            e_n_per_m2=elastic_modulus_mpa * 1000.0,
            g_n_per_m2=shear_modulus_mpa * 1000.0,
            iy_m4=float(section_row["iy_m4"]),
            iz_m4=float(section_row["iz_m4"]),
            j_m4=float(section_row["torsional_constant_m4"]),
        ),
        effective_shear_area_y_m2=float(section_row["shear_area_y_m2"]),
        effective_shear_area_z_m2=float(section_row["shear_area_z_m2"]),
    )
    pattern = payload["load_patterns"][0]
    reference_load_n = np.zeros(12, dtype="<f8")
    components = pattern["nodal_loads"][0]["components_si"]
    reference_load_n[6:] = [
        float(components[label]) for label in ("FX", "FY", "FZ", "MX", "MY", "MZ")
    ]
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=tuple(
            tuple(float(value) for value in row["coordinates_m"])
            for row in payload["nodes"]
        ),
        members=(CorotationalFrame3DMember("E1", 0, 1, section),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(float(value / 1000.0) for value in reference_load_n),
        model_id=document.model_id,
    )
    steel = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=elastic_modulus_mpa,
        yield_stress_mpa=float(material["yield_stress_pa"]) / 1.0e6,
        isotropic_hardening_modulus_mpa=(
            float(material["isotropic_hardening_modulus_pa"]) / 1.0e6
        ),
        kinematic_hardening_modulus_mpa=(
            float(material["kinematic_hardening_modulus_pa"]) / 1.0e6
        ),
        material_id=material_row["id"],
    )
    return (
        document,
        StatefulCorotationalFrame3DSparseModel(elastic, (steel,)),
        reference_load_n,
    )


def _material_entry(state: Any) -> MaterialStateInput:
    payload = state.to_dict()
    return MaterialStateInput(
        entity_id="element.E1",
        integration_point_id="ip.0",
        material_type_id="steel.bilinear-combined-hardening",
        material_schema_version=str(payload["schema_version"]),
        state_bytes=canonical_json_bytes(payload),
    )


def _accepted_line_search_alphas(step: Any) -> tuple[float, ...]:
    return tuple(
        float(row["selected_alpha"])
        for row in step.line_search_history
        if row["selected_alpha"] is not None
    )


def _convergence_checks(step: Any) -> dict[str, bool]:
    return {
        "scaled_residual_gate": bool(step.residual_gate_passed),
        "scaled_increment_gate": bool(step.increment_gate_passed),
        "line_search_step_valid": bool(step.line_search_valid),
        "material_admissibility": bool(step.material_admissibility_passed),
        "final_reassembled_equilibrium": bool(
            step.final_reassembled_equilibrium_passed
        ),
        "parent_state_immutable": bool(step.parent_state_immutable),
        "sparse_diagnostic_pass": bool(step.sparse_diagnostic_passed),
    }


def _result_ir(
    *,
    document: Any,
    model: Any,
    reference_load_n: np.ndarray,
    result: Any,
    path_history: Any,
) -> dict[str, Any]:
    operator_hash = LINEAR._sha_payload(
        {
            "model_hash": model.model_hash,
            "solver_contract_hash": result.solver_contract_hash,
        }
    )
    base_plan = create_execution_plan(
        model_ir_content_hash=document.content_hash,
        solver_buffer_schema_version="stateful-frame3d-sparse-buffers.v1",
        solver_numeric_buffer_hash=LINEAR._sha_payload(
            {
                "model_hash": model.model_hash,
                "reference_load": LINEAR._sha_bytes(reference_load_n.tobytes()),
            }
        ),
        solver_entity_mapping_hash=LINEAR._sha_payload(
            {"nodes": ["N1", "N2"], "elements": ["E1"]}
        ),
        solver_artifact_hash=LINEAR._sha_payload({"profile": result.profile}),
        load_pattern_id="NL_CYCLIC_AXIAL",
        operator_id="stateful-corotational-frame3d-sparse",
        operator_version="stateful-corotational-frame3d-sparse.v1",
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
        plan, operator_numeric_values_hash=operator_hash
    )
    state = create_initial_state(plan)
    bundle = create_initial_material_state_bundle(
        bundle_id="f3.frame3d.stateful-steel.material",
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hash=state.state_hash,
        entries=tuple(
            _material_entry(row) for row in result.checkpoints[0].material_states
        ),
    )
    for index, step in enumerate(result.steps, start=1):
        trial_state = open_trial_state(
            state,
            np.asarray(step.checkpoint.displacement, dtype="<f8"),
            load_step=index,
            iteration=max(int(step.checkpoint.converged_iterations), 1),
            load_factor=float(step.load_factor),
            time_s=0.0,
            expected_plan=plan,
        )
        next_state = commit_trial_state(state, trial_state, expected_plan=plan)
        trial_bundle = open_trial_material_state_bundle(
            bundle,
            solver_state_hash=trial_state.state_hash,
            entries=tuple(
                _material_entry(row) for row in step.checkpoint.material_states
            ),
        )
        next_bundle = commit_trial_material_state_bundle(
            bundle, trial_bundle, solver_state_hash=next_state.state_hash
        )
        state, bundle = next_state, next_bundle
    final_residual_n = float(result.final_checkpoint.residual_inf_norm_kn * 1000.0)
    rejected = len(result.load_cutback_history)
    terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version=result.schema_version,
        source_solver_receipt_hash=result.result_hash,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_solution_data_hash=array_data_hash(
            immutable_array(state.displacement_si[6:], dtype="<f8")
        ),
        solver_coordinate_scaling_receipt_hash=LINEAR._sha_payload(
            {"solver_contract_hash": result.solver_contract_hash}
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
        rejected_attempt_count=rejected,
        rollback_count=rejected,
        fallback_count=0,
        regularization_count=0,
    )
    numerical = create_nonlinear_numerical_result_ir(
        result_id="f3.frame3d.stateful-material.nl-cyclic-axial",
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
    current = DIRECT.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_direct_control_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt(
        schema="f3-vertical-evidence-gate.v1",
        stage="frame3d_direct_control",
        stage_index=2,
        source_commit_sha=source_commit,
        required_surfaces=tuple(stage["required_surfaces"]),
        verified_surfaces=tuple(stage["verified_surfaces"]),
        evidence_artifact_sha256=tuple(
            sorted(stage["evidence_artifact_sha256"].items())
        ),
        predecessor_stage="frame3d_load_control",
        predecessor_receipt_sha256=stage["predecessor_receipt_sha256"],
        external_vv_signature_status="waived",
        blockers=tuple(stage["blockers"]),
        public_product_promotion_passed=bool(stage["public_product_promotion_passed"]),
    )
    persisted = json.loads((ROOT / DIRECT_RECEIPT).read_text(encoding="utf-8"))
    replay = {
        "source_receipt_path": DIRECT_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(DIRECT_RECEIPT),
        "persisted_source_commit_sha": persisted["source_commit_sha"],
        "current_source_replay_executed": True,
        "replayed_source_commit_sha": source_commit,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }
    return receipt, LINEAR._sha_payload(current["stage_gate"]), replay


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document, model, reference_load_n = _model()
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40)
    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model, LOAD_FACTORS, config=config
    )
    prefix = solve_stateful_corotational_frame3d_sparse_load_path(
        model, LOAD_FACTORS[:2], config=config
    )
    resumed = solve_stateful_corotational_frame3d_sparse_load_path(
        model, LOAD_FACTORS[2:], config=config, resume_from=prefix.final_checkpoint
    )
    repeated = solve_stateful_corotational_frame3d_sparse_load_path(
        model, LOAD_FACTORS, config=config
    )
    exact_restart = bool(
        result.final_checkpoint == resumed.final_checkpoint
        and result.steps[-1].member_results == resumed.steps[-1].member_results
    )
    deterministic = repeated.result_hash == result.result_hash
    path_history = [
        {
            "load_factor": step.load_factor,
            "checkpoint_hash": step.checkpoint.checkpoint_hash,
            "free_residual_inf_norm_kn": step.free_residual_inf_norm_kn,
            "accepted_line_search_alphas": list(_accepted_line_search_alphas(step)),
            "convergence_checks": _convergence_checks(step),
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
    member = final.member_results[0]
    end_forces_n = np.asarray(member["global_end_forces"], dtype="<f8") * 1000.0
    residual_n = np.zeros(12, dtype="<f8")
    residual_n[6:] = end_forces_n[6:] - LOAD_FACTORS[-1] * reference_load_n[6:]
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
        source_input_checksum=LINEAR._file_sha(MODEL_PATH),
        canonical_model_checksum=document.content_hash,
    )
    validate_linear_static_viewer_payload(viewer)
    material_state = result.final_checkpoint.material_states[0]
    material_payload = material_state.to_dict()
    response = member["axial_material_response"]
    expected_displacement_m = 2.0 * (
        float(response["stress_mpa"]) / 200_000.0
        + float(material_payload["plastic_strain"])
    )
    displacement_error_m = abs(final_displacement[6] - expected_displacement_m)
    final_residual_n = float(result.final_checkpoint.residual_inf_norm_kn * 1000.0)
    factorization_pass = all(
        diagnostic.contract_pass
        for step in result.steps
        for diagnostic in step.factorization_diagnostics
    )
    all_pass = bool(
        result.contract_pass
        and exact_restart
        and deterministic
        and result.material_commit_rollback_supported
        and result.exact_checkpoint_resume_supported
        and not result.fallback_used
        and not result.regularization_used
        and factorization_pass
        and all(all(_convergence_checks(step).values()) for step in result.steps)
        and float(material_payload["accumulated_plastic_strain"]) > 0.0
        and float(material_payload["dissipated_energy_density_mj_per_m3"]) > 0.0
        and final_residual_n <= 1.0e-4
        and displacement_error_m <= 1.0e-9
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "capability_profile": document.capability_profile,
            "material_law_id": document.to_dict()["materials"][0]["law_id"],
            "analysis_ready": document.analysis_ready,
        },
        "solver": {
            "schema_version": result.schema_version,
            "profile": result.profile,
            "load_factors": list(LOAD_FACTORS),
            "path_history": path_history,
            "contract_pass": result.contract_pass,
            "material_commit_rollback_supported": result.material_commit_rollback_supported,
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
            "axial_material_response": dict(response),
            "final_residual_inf_n": final_residual_n,
        },
        "checkpoint": {
            "schema_version": result.final_checkpoint.schema_version,
            "checkpoint": result.final_checkpoint.to_dict(),
            "prefix_checkpoint_hash": prefix.final_checkpoint.checkpoint_hash,
            "resumed_checkpoint_hash": resumed.final_checkpoint.checkpoint_hash,
            "exact_restart": exact_restart,
            "material_state": material_payload,
        },
        "workbench": {
            "schema_version": viewer["schema_version"],
            "viewer_payload": viewer,
            "model_identity_bound": True,
        },
        "benchmark": {
            "benchmark_id": "frame3d-combined-hardening-steel-cyclic-axial.v1",
            "deterministic_repeat": deterministic,
            "expected_final_displacement_m": expected_displacement_m,
            "observed_final_displacement_m": float(final_displacement[6]),
            "displacement_absolute_error_m": displacement_error_m,
            "plastic_history_nonzero": float(
                material_payload["accumulated_plastic_strain"]
            )
            > 0.0,
            "dissipated_energy_nonzero": float(
                material_payload["dissipated_energy_density_mj_per_m3"]
            )
            > 0.0,
            "factorization_diagnostics_pass": factorization_pass,
        },
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent_uniaxial_combined_hardening_return_mapping.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "displacement_absolute_error_m": displacement_error_m,
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
        stage="frame3d_stateful_material",
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
            "Closes the bounded single-member Frame3D stateful-material stage for a "
            "ModelIR-bound combined-hardening steel cyclic axial path with material "
            "trial/commit/rollback ancestry, accepted-state consistency, exact restart, "
            "nonlinear ResultIR, recovery, and bound Workbench projection. Additional "
            "material families, multi-member topology, modal, dynamics, shell, and "
            "contact remain outside this stage."
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
            print("f3_frame3d_stateful_material_vertical_evidence_mismatch")
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=str(recorded["source_commit_sha"]))
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if (
            recorded.get("source_input_checksums") != payload["source_input_checksums"]
            or out.read_text(encoding="utf-8") != text
        ):
            print("f3_frame3d_stateful_material_vertical_evidence_mismatch")
            return 1
        print("f3_frame3d_stateful_material_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    checkpoint = payload["surface_artifacts"]["checkpoint"]["checkpoint"]
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | "
        f"load={checkpoint['load_factor']} | ux={checkpoint['displacement'][6]}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
