from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase2_frame_shell_material_coupling_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase2_frame_shell_material_coupling_artifacts",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase2_frame_shell_material_coupling_builds_honest_seed_artifacts() -> None:
    artifacts = module.build_phase2_frame_shell_material_coupling_artifacts(
        repo_root=REPO_ROOT,
    )
    result = artifacts["result"]
    summary = artifacts["summary"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["g1_closure_claim"] is False
    assert summary["frame_shell_material_coupling_closure_claim"] is False
    assert summary["full_mesh_closure_claim"] is False
    assert summary["residual_formula"] == "F_internal_minus_F_external"
    assert summary["dense_matrix_backend"] == "numpy_linalg_solve_dense"
    assert summary["sparse_matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert summary["finite_difference_jacobian_gate_passed"] is True
    assert summary["off_diagonal_coupling_visible"] is True
    assert summary["dense_sparse_equivalence_gate_passed"] is True
    assert summary["regularization_used"] is False
    assert summary["fallback_used"] is False
    assert sorted(summary["input_checksums"]) == [
        "scripts/build_phase2_frame_shell_material_coupling_artifacts.py",
        "src/structural_analysis/assembly/__init__.py",
        "src/structural_analysis/assembly/coupled_static.py",
        "src/structural_analysis/solvers/nonlinear/newton.py",
        "tests/test_build_phase2_frame_shell_material_coupling_artifacts.py",
    ]
    assert summary["blockers_remaining"] == [
        "general_frame_shell_material_coupling_not_closed",
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "general_mesh_load_step_nonlinear_convergence_suite_not_closed",
        "production_rocm_hip_parity_not_closed",
        "design_code_adequacy_not_closed",
    ]
    assert "does not close general frame-shell" in summary["claim_boundary"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert result["g1_closure_claim"] is False
    assert result["frame_shell_material_coupling_closure_claim"] is False
    assert result["full_mesh_closure_claim"] is False
    assert result["finite_difference_jacobian_check"]["pass"] is True
    assert result["off_diagonal_coupling_visible"] is True
    assert result["dense_sparse_equivalence"]["pass"] is True
    assert result["dense_sparse_equivalence"]["max_displacement_delta_m"] <= 1.0e-10
    assert result["dense_sparse_equivalence"]["max_residual_delta_kn"] <= 1.0e-10
    assert result["dense_solution"]["status"] == "ready"
    assert result["sparse_solution"]["status"] == "ready"
    assert result["dense_solution"]["sparse_backend_used"] is False
    assert result["sparse_solution"]["sparse_backend_used"] is True
    assert result["sparse_solution"]["stiffness_storage"] == "scipy_sparse_csr"
    jacobian = result["dense_solution"]["state"]["jacobian_kn_per_m"]
    assert jacobian[0][1] == jacobian[1][0]
    assert jacobian[0][1] != 0.0
    components = result["dense_solution"]["state"]["component_forces_kn"]
    assert {row["component"] for row in components} == {
        "frame_axial_material",
        "shell_diaphragm_shear_material",
        "frame_shell_material_coupling",
    }


def test_phase2_frame_shell_material_coupling_check_detects_missing_outputs(tmp_path: Path) -> None:
    ok, message = module.check_phase2_frame_shell_material_coupling_artifacts(
        repo_root=REPO_ROOT,
        result_out=tmp_path / "missing_result.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_frame_shell_material_coupling_missing:")


def test_frame_shell_material_coupled_assembly_has_consistent_tangent() -> None:
    from structural_analysis.assembly.coupled_static import (
        default_frame_shell_material_coupled_problem,
        finite_difference_coupled_jacobian_check,
        solve_frame_shell_material_coupled,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_frame_shell_material_coupled_problem()
    solution, final_state = solve_frame_shell_material_coupled(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    check = finite_difference_coupled_jacobian_check(
        problem,
        solution.free_displacements_m,
    )

    assert solution.status == "ready"
    assert solution.metrics["contract_pass"] is True
    assert solution.metrics["regularization_used"] is False
    assert solution.metrics["fallback_used"] is False
    assert check["pass"] is True
    assert final_state.jacobian_kn_per_m[0, 1] == final_state.jacobian_kn_per_m[1, 0]
    assert final_state.jacobian_kn_per_m[0, 1] != 0.0
