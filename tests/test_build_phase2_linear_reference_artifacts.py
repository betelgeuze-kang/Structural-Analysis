from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase2_linear_reference_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase2_linear_reference_artifacts", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase2_linear_reference_builds_honest_reference_artifacts() -> None:
    artifacts = module.build_linear_reference_artifacts(repo_root=REPO_ROOT)
    summary = artifacts["summary"]
    result = artifacts["analytic_result"]
    metrics = result["metrics"]
    mechanism = artifacts["mechanism_result"]
    rigid_body = artifacts["rigid_body_result"]
    convergence = artifacts["convergence_suite"]
    tangent_jacobian = artifacts["tangent_jacobian"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["g1_closure_claim"] is False
    assert summary["residual_contract"] == "F_internal_minus_F_external"
    assert summary["residual_gate_passed"] is True
    assert summary["energy_gate_passed"] is True
    assert summary["mechanism_blocked_without_regularization"] is True
    assert summary["rigid_body_blocked_without_regularization"] is True
    assert summary["linear_axial_convergence_suite_ready"] is True
    assert summary["linear_axial_convergence_case_count"] == 4
    assert summary["mesh_refinement_gate_passed"] is True
    assert summary["load_step_scaling_gate_passed"] is True
    assert summary["linear_axial_tangent_jacobian_verification_ready"] is True
    assert summary["tangent_jacobian_gate_passed"] is True
    assert summary["tangent_jacobian_finite_difference_gate_passed"] is True
    assert summary["tangent_jacobian_equals_stiffness_gate_passed"] is True
    assert summary["blockers_remaining"] == [
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "consistent_tangent_jacobian_newton_not_closed",
        "frame_shell_material_coupling_not_closed",
        "mesh_load_step_convergence_suite_not_closed",
        "sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
    ]
    assert summary["matrix_backend_gate_passed"] is True
    assert summary["stiffness_storage"] == "dense_numpy"
    assert summary["matrix_backend"] == "numpy_linalg_solve_dense"
    assert summary["sparse_backend_used"] is False

    assert result["status"] == "ready"
    assert metrics["residual_formula"] == "F_internal_minus_F_external"
    assert metrics["tangent_jacobian_equals_assembled_stiffness"] is True
    assert metrics["tangent_jacobian_storage"] == "dense_numpy"
    assert metrics["regularization_used"] is False
    assert metrics["fallback_used"] is False
    assert metrics["stiffness_storage"] == "dense_numpy"
    assert metrics["matrix_backend"] == "numpy_linalg_solve_dense"
    assert metrics["sparse_backend_used"] is False
    assert metrics["stiffness_order"] == 6
    assert metrics["free_stiffness_order"] == 1
    assert metrics["relative_residual"] == 0.0
    assert metrics["energy_balance_error"] == 0.0
    assert metrics["displacements"]["N2"]["UX"] == 0.1
    assert metrics["reactions"]["N1"]["UX"] == -100.0
    assert metrics["external_forces"]["N2"]["UX"] == 100.0
    assert metrics["internal_forces"]["N2"]["UX"] == 100.0
    assert result["convergence_history"][0]["relative_residual"] == 0.0

    unsupported_kinds = {row["kind"] for row in mechanism["unsupported_features"]}
    assert mechanism["status"] == "blocked"
    assert "linear_static_singular_stiffness" in unsupported_kinds
    mechanism_feature = next(
        row for row in mechanism["unsupported_features"] if row["kind"] == "linear_static_singular_stiffness"
    )
    assert mechanism_feature["guard_outcome"] == "blocked"
    assert mechanism_feature["mechanism_guard"] == "singular_or_rigid_body"
    assert mechanism_feature["regularization_used"] is False
    assert mechanism_feature["fallback_used"] is False
    assert mechanism["metrics"]["sparse_backend_used"] is False

    rigid_body_unsupported_kinds = {row["kind"] for row in rigid_body["unsupported_features"]}
    assert rigid_body["status"] == "blocked"
    assert "linear_static_singular_stiffness" in rigid_body_unsupported_kinds
    rigid_body_feature = next(
        row for row in rigid_body["unsupported_features"] if row["kind"] == "linear_static_singular_stiffness"
    )
    assert rigid_body_feature["guard_outcome"] == "blocked"
    assert rigid_body_feature["mechanism_guard"] == "singular_or_rigid_body"
    assert rigid_body_feature["regularization_used"] is False
    assert rigid_body_feature["fallback_used"] is False
    assert rigid_body["metrics"]["regularization_used"] is False
    assert rigid_body["metrics"]["fallback_used"] is False
    assert rigid_body["metrics"]["sparse_backend_used"] is False
    assert rigid_body["metrics"]["free_stiffness_order"] == 2

    assert convergence["status"] == "ready"
    assert convergence["contract_pass"] is True
    assert convergence["case_count"] == 4
    assert convergence["mesh_refinement_gate_passed"] is True
    assert convergence["mesh_refinement_max_tip_delta"] <= 1.0e-12
    assert convergence["load_step_scaling_gate_passed"] is True
    assert convergence["load_scaling_ratio"] == 0.5
    assert {row["element_count"] for row in convergence["rows"] if row["load_fx"] == 100.0} == {
        1,
        2,
        4,
    }
    assert all(row["pass"] is True for row in convergence["rows"])
    assert all(row["residual_formula"] == "F_internal_minus_F_external" for row in convergence["rows"])
    assert all(row["regularization_used"] is False for row in convergence["rows"])
    assert all(row["fallback_used"] is False for row in convergence["rows"])
    assert all(row["stiffness_storage"] == "dense_numpy" for row in convergence["rows"])
    assert all(row["matrix_backend"] == "numpy_linalg_solve_dense" for row in convergence["rows"])
    assert all(row["sparse_backend_used"] is False for row in convergence["rows"])

    assert tangent_jacobian["status"] == "ready"
    assert tangent_jacobian["contract_pass"] is True
    assert tangent_jacobian["case_id"] == "phase2_analytic_axial_bar"
    assert tangent_jacobian["residual_contract"] == "F_internal_minus_F_external"
    assert tangent_jacobian["tangent_jacobian_definition"] == "dR_du_equals_assembled_dense_stiffness"
    assert tangent_jacobian["free_dof_count"] == 1
    assert tangent_jacobian["free_dof_indices"] == [3]
    assert tangent_jacobian["equilibrium_residual_gate_passed"] is True
    assert tangent_jacobian["tangent_equals_stiffness_gate_passed"] is True
    assert tangent_jacobian["tangent_free_block_gate_passed"] is True
    assert tangent_jacobian["finite_difference_gate_passed"] is True
    assert tangent_jacobian["finite_difference_free_dof_count"] == 1
    assert tangent_jacobian["finite_difference_max_column_inf_norm_error"] <= 1.0e-6
    assert tangent_jacobian["g1_closure_claim"] is False
    assert tangent_jacobian["nonlinear_newton_closure_claim"] is False
    assert tangent_jacobian["regularization_used"] is False
    assert tangent_jacobian["fallback_used"] is False
    assert tangent_jacobian["sparse_backend_used"] is False
    assert all(row["pass"] is True for row in tangent_jacobian["finite_difference_rows"])

    sparse_backend = artifacts["sparse_backend"]
    assert sparse_backend["status"] == "ready"
    assert sparse_backend["contract_pass"] is True
    assert sparse_backend["case_id"] == "phase2_analytic_axial_bar"
    assert sparse_backend["dense_stiffness_storage"] == "dense_numpy"
    assert sparse_backend["dense_matrix_backend"] == "numpy_linalg_solve_dense"
    assert sparse_backend["dense_sparse_backend_used"] is False
    assert sparse_backend["sparse_stiffness_storage"] == "scipy_sparse_csr"
    assert sparse_backend["sparse_matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert sparse_backend["sparse_backend_used"] is True
    assert sparse_backend["api_config_matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert sparse_backend["api_config_solver"] == "phase2_linear_reference_sparse_api"
    assert sparse_backend["canonical_api_sparse_route_used"] is True
    assert sparse_backend["equivalence_gate_passed"] is True
    assert sparse_backend["displacement_inf_norm_error"] <= 1.0e-12
    assert sparse_backend["reaction_inf_norm_error"] <= 1.0e-12
    assert sparse_backend["residual_inf_norm_error"] <= 1.0e-12
    assert sparse_backend["g1_closure_claim"] is False
    assert sparse_backend["regularization_used"] is False
    assert sparse_backend["fallback_used"] is False
    assert sparse_backend["sparse_mechanism_blocked_without_regularization"] is True
    assert sparse_backend["sparse_rigid_body_blocked_without_regularization"] is True
    assert "linear_static_singular_stiffness" in sparse_backend["sparse_mechanism_unsupported_kinds"]
    assert "linear_static_singular_stiffness" in sparse_backend["sparse_rigid_body_unsupported_kinds"]
    assert sparse_backend["blockers_remaining"] == summary["blockers_remaining"]
    assert summary["sparse_backend_seed_verification_ready"] is True
    assert summary["sparse_backend_api_path_verification_ready"] is True
    assert summary["sparse_backend_api_config_matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert summary["sparse_backend_api_config_solver"] == "phase2_linear_reference_sparse_api"
    assert summary["sparse_backend_equivalence_gate_passed"] is True
    assert summary["sparse_mechanism_blocked_without_regularization"] is True
    assert summary["sparse_rigid_body_blocked_without_regularization"] is True
    assert summary["sparse_backend_seed_stiffness_storage"] == "scipy_sparse_csr"
    assert summary["sparse_backend_seed_matrix_backend"] == "scipy_sparse_spsolve_cpu"


def test_phase2_linear_reference_check_detects_stale_outputs(tmp_path: Path) -> None:
    ok, message = module.check_linear_reference_artifacts(
        repo_root=REPO_ROOT,
        analytic_model_out=tmp_path / "missing_analytic_model.json",
        analytic_result_out=tmp_path / "missing_analytic_result.json",
        analytic_report_out=tmp_path / "missing_analytic_report.json",
        mechanism_model_out=tmp_path / "missing_mechanism_model.json",
        mechanism_result_out=tmp_path / "missing_mechanism_result.json",
        rigid_body_model_out=tmp_path / "missing_rigid_body_model.json",
        rigid_body_result_out=tmp_path / "missing_rigid_body_result.json",
        convergence_out=tmp_path / "missing_convergence.json",
        tangent_jacobian_out=tmp_path / "missing_tangent_jacobian.json",
        sparse_backend_out=tmp_path / "missing_sparse_backend.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_linear_reference_missing:")
