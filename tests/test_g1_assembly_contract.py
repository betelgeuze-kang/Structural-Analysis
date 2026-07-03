from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_g1_assembly_contract_seed_report.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_g1_assembly_contract_seed_report",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_axial_chain_seed_adapts_to_g1_assembly_contract() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.nonlinear_static import (
        assemble_axial_chain_state,
        default_phase2_axial_chain_mesh_problem,
        solve_axial_chain_mesh,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_phase2_axial_chain_mesh_problem()
    solution, state = solve_axial_chain_mesh(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    result = assemble_g1_state(problem, state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_axial_chain_state(problem, free_u),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_axial_chain_state(problem, free_u),
        ),
        solution,
    )

    assert result.schema_version == "g1-assembly-result.v1"
    assert result.residual_formula == "F_internal_minus_F_external"
    assert np.allclose(
        result.residual_free,
        result.internal_forces[list(state.free_node_indices)]
        - result.external_forces[list(state.free_node_indices)],
    )
    assert result.tangent_free.shape == (2, 2)
    assert result.material_state_next["state_updated_material_newton"] is False
    assert result.metrics["regularized_fixed_point_substitute"] is False
    assert result.metrics["g1_closure_claim"] is False
    assert result.contract_check()["contract_pass"] is True
    assert jvp_check["pass"] is True
    assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
    assert newton_parity["consistent_residual_jacobian_newton_gate_passed"] is False
    assert newton_parity["direct_solver_residual_match"] is True
    assert newton_parity["residual_descent_passed"] is True
    assert newton_parity["relative_increment_gate_passed"] is True
    assert newton_parity["promotes_g1_closure"] is False


def test_frame_shell_material_seed_adapts_to_g1_assembly_contract() -> None:
    from structural_analysis.assembly.coupled_static import (
        assemble_frame_shell_material_coupled_state,
        default_frame_shell_material_coupled_problem,
        solve_frame_shell_material_coupled,
    )
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_frame_shell_material_coupled_problem()
    solution, state = solve_frame_shell_material_coupled(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    result = assemble_g1_state(problem, state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_frame_shell_material_coupled_state(problem, free_u),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_frame_shell_material_coupled_state(problem, free_u),
        ),
        solution,
    )

    assert result.residual_formula == "F_internal_minus_F_external"
    assert np.allclose(
        result.residual_free,
        result.internal_forces - result.external_forces,
    )
    assert result.tangent_free.shape == (2, 2)
    assert result.tangent_free[0, 1] == result.tangent_free[1, 0]
    assert result.material_state_next["state_updated_material_newton"] is False
    assert result.metrics["fixed_point_residual_used_as_physical"] is False
    assert result.metrics["g1_closure_claim"] is False
    assert result.contract_check()["contract_pass"] is True
    assert jvp_check["pass"] is True
    assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
    assert newton_parity["consistent_residual_jacobian_newton_gate_passed"] is False
    assert newton_parity["direct_solver_residual_match"] is True
    assert newton_parity["residual_descent_passed"] is True
    assert newton_parity["relative_increment_gate_passed"] is True
    assert newton_parity["promotes_g1_closure"] is False


def test_g1_assembly_contract_rejects_fixed_point_physical_residual_substitute() -> None:
    from structural_analysis.assembly.g1_contract import AssemblyResult

    with pytest.raises(ValueError, match="substitute"):
        AssemblyResult(
            residual_formula="F_internal_minus_F_external",
            residual_source="fixed_point_residual",
            residual_free=np.array([0.0]),
            tangent_free=np.array([[1.0]]),
            internal_forces=np.array([1.0]),
            external_forces=np.array([1.0]),
            material_state_next={},
            metrics={"fixed_point_residual_used_as_physical": True},
        )


def test_g1_assembly_contract_seed_report_is_non_promoting_ready_receipt() -> None:
    payload = module.build_g1_assembly_contract_seed_report(repo_root=REPO_ROOT)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["g1_closure_claim"] is False
    assert (
        payload["phase_covered"]
        == "phase1_phase2_cpu_seed_contract_and_newton_parity"
    )
    assert payload["residual_formula"] == "F_internal_minus_F_external"
    assert payload["fixed_point_residual_promoted_to_physical"] is False
    assert payload["regularized_fixed_point_substitute"] is False
    assert payload["cpu_seed_consistent_newton_gate_passed"] is True
    assert payload["consistent_residual_jacobian_newton_gate_passed"] is False
    assert payload["case_count"] == 2
    assert all(row["contract_pass"] is True for row in payload["cases"])
    assert all(
        row["jvp_finite_difference_check"]["pass"] is True
        for row in payload["cases"]
    )
    assert all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        is True
        for row in payload["cases"]
    )
    assert all(
        row["direct_residual_newton_parity_check"][
            "direct_solver_residual_match"
        ]
        is True
        for row in payload["cases"]
    )
    assert payload["blockers_remaining"] == [
        "full_load_gate_not_closed",
        "full_mesh_nonlinear_equilibrium_not_closed",
        "material_newton_breadth_not_closed",
        "production_rocm_hip_residency_not_closed",
        "g1_consistent_residual_jacobian_newton_gate_not_closed_by_cpu_seed",
        "full_load_checkpoint_1p0_not_created_by_this_seed_report",
        "hip_residual_jvp_worker_not_executed_by_this_seed_report",
    ]


def test_g1_assembly_contract_seed_report_check_detects_missing_output(
    tmp_path: Path,
) -> None:
    ok, message = module.check_g1_assembly_contract_seed_report(
        repo_root=REPO_ROOT,
        out=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("g1_assembly_contract_seed_report_missing:")
