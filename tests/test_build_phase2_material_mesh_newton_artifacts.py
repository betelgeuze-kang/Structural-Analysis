from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase2_material_mesh_newton_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase2_material_mesh_newton_artifacts",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase2_material_mesh_newton_builds_honest_seed_artifacts() -> None:
    artifacts = module.build_material_mesh_newton_artifacts(repo_root=REPO_ROOT)
    summary = artifacts["summary"]
    mesh_payload = artifacts["mesh"]
    mesh_result = mesh_payload["mesh_result"]
    verification = mesh_result["verification"]
    metrics = mesh_result["metrics"]
    assembly = mesh_result["assembly"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["g1_closure_claim"] is False
    assert summary["material_newton_closure_claim"] is False
    assert summary["full_mesh_closure_claim"] is False
    assert summary["residual_contract"] == "F_internal_minus_F_external"
    assert summary["node_count"] == 3
    assert summary["element_count"] == 2
    assert summary["model_kind"] == "scalar_nonlinear_axial_cubic_spring"
    assert summary["sparse_backend_used"] is False
    assert summary["matrix_backend"] == "numpy_linalg_solve_dense"
    assert summary["tangent_gate_passed"] is True
    assert summary["series_force_gate_passed"] is True
    assert summary["load_step_gate_passed"] is True
    assert summary["narrow_mesh_refinement_gate_passed"] is True
    assert summary["narrow_sparse_backend_equivalence_gate_passed"] is True
    assert summary["final_tip_displacement_spread_m"] <= 1.0e-10
    assert summary["mesh_refinement_tip_displacement_spread_m"] <= 1.0e-10
    assert summary["mesh_refinement_element_counts"] == [1, 2, 4]
    assert summary["sparse_backend_equivalence_matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert sorted(summary["input_checksums"]) == [
        "scripts/build_phase2_material_mesh_newton_artifacts.py",
        "scripts/verify_quality_gate.py",
        "src/structural_analysis/assembly/__init__.py",
        "src/structural_analysis/assembly/nonlinear_static.py",
        "src/structural_analysis/solvers/nonlinear/__init__.py",
        "src/structural_analysis/solvers/nonlinear/newton.py",
        "tests/test_build_phase2_material_mesh_newton_artifacts.py",
    ]
    assert summary["blockers_remaining"] == [
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "frame_shell_material_coupling_not_closed",
        "general_mesh_load_step_nonlinear_convergence_suite_not_closed",
        "general_sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
        "broad_material_newton_breadth_not_closed",
    ]

    assert mesh_payload["status"] == "ready"
    assert mesh_payload["contract_pass"] is True
    assert mesh_payload["g1_closure_claim"] is False
    assert mesh_payload["material_newton_closure_claim"] is False
    assert mesh_payload["full_mesh_closure_claim"] is False
    assert mesh_payload["residual_formula"] == "F_internal_minus_F_external"

    assert mesh_result["status"] == "ready"
    assert mesh_result["contract_pass"] is True
    assert mesh_result["g1_closure_claim"] is False
    assert mesh_result["material_newton_closure_claim"] is False
    assert mesh_result["full_mesh_closure_claim"] is False
    assert mesh_result["residual_formula"] == "F_internal_minus_F_external"
    assert mesh_result["globalization"] == "backtracking_line_search"
    assert mesh_result["regularization_used"] is False
    assert mesh_result["fallback_used"] is False
    assert metrics["residual_gate_passed"] is True
    assert metrics["increment_gate_passed"] is True
    assert metrics["regularization_used"] is False
    assert metrics["fallback_used"] is False
    assert metrics["relative_residual"] <= 1.0e-10
    assert metrics["final_increment_abs_m"] <= 1.0e-12
    assert metrics["iteration_count"] >= 1
    assert len(mesh_result["convergence_history"]) >= 1
    assert assembly["residual_formula"] == "F_internal_minus_F_external"
    assert len(assembly["element_forces_kn"]) == 2
    assert abs(assembly["reactions_kn"][0] + 100.0) <= 1.0e-10
    assert abs(sum(assembly["external_forces_kn"]) + sum(assembly["reactions_kn"])) <= 1.0e-10
    assert verification["tangent_gate_passed"] is True
    assert verification["assembled_jacobian_finite_difference_check"]["pass"] is True
    assert verification["series_force_gate_passed"] is True
    assert verification["mesh_load_step_consistency"]["load_step_gate_passed"] is True
    refinement = verification["mesh_refinement_suite"]
    assert refinement["narrow_mesh_refinement_gate_passed"] is True
    assert refinement["element_counts"] == [1, 2, 4]
    assert refinement["tip_displacement_spread_m"] <= 1.0e-10
    assert all(row["contract_pass"] is True for row in refinement["rows"])
    assert all(row["regularization_used"] is False for row in refinement["rows"])
    assert all(row["fallback_used"] is False for row in refinement["rows"])
    sparse = verification["sparse_backend_equivalence"]
    assert sparse["narrow_sparse_backend_equivalence_gate_passed"] is True
    assert sparse["dense_backend"] == "numpy_linalg_solve_dense"
    assert sparse["sparse_backend"] == "scipy_sparse_spsolve_cpu"
    assert sparse["sparse_backend_used"] is True
    assert sparse["sparse_stiffness_storage"] == "scipy_sparse_csr"
    assert sparse["max_displacement_delta_m"] <= 1.0e-10
    assert sparse["max_residual_delta_kn"] <= 1.0e-10
    assert sparse["regularization_used"] is False
    assert sparse["fallback_used"] is False


def test_phase2_material_mesh_newton_check_detects_stale_outputs(tmp_path: Path) -> None:
    ok, message = module.check_material_mesh_newton_artifacts(
        repo_root=REPO_ROOT,
        mesh_out=tmp_path / "missing_mesh.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_material_mesh_newton_missing:")


def test_phase2_material_mesh_newton_assembly_uses_material_law_on_mesh() -> None:
    from structural_analysis.assembly.nonlinear_static import (
        default_phase2_axial_chain_mesh_problem,
        finite_difference_assembled_jacobian_check,
        solve_axial_chain_mesh,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    mesh_problem = default_phase2_axial_chain_mesh_problem()
    assert mesh_problem.node_count == 3
    assert len(mesh_problem.elements) == 2
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    solution, final_state = solve_axial_chain_mesh(mesh_problem, config=config)
    jacobian_check = finite_difference_assembled_jacobian_check(
        mesh_problem,
        solution.free_displacements_m,
    )

    assert solution.status == "ready"
    assert solution.metrics["residual_formula"] == "F_internal_minus_F_external"
    assert solution.metrics["contract_pass"] is True
    assert jacobian_check["pass"] is True
    assert len(final_state.element_forces_kn) == 2
    assert abs(final_state.reactions_kn[0] + 100.0) <= 1.0e-10
