from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase2_material_newton_breadth_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase2_material_newton_breadth_artifacts",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase2_material_newton_breadth_builds_honest_seed_artifacts() -> None:
    artifacts = module.build_material_newton_breadth_artifacts(repo_root=REPO_ROOT)
    summary = artifacts["summary"]
    laws_payload = artifacts["laws"]
    state_updated_payload = artifacts["state_updated_seeds"]
    law_results = laws_payload["material_laws"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["g1_closure_claim"] is False
    assert summary["material_newton_closure_claim"] is False
    assert summary["residual_contract"] == "F_internal_minus_F_external"
    assert summary["material_law_count"] == 2
    assert summary["model_kinds"] == [
        "scalar_nonlinear_axial_cubic_spring",
        "scalar_nonlinear_axial_bilinear_hardening",
    ]
    assert summary["state_updated_material_newton_seed_passed"] is True
    assert summary["state_updated_material_newton_seed_case_count"] == 9
    assert summary["state_updated_material_newton_seed_case_kinds"] == [
        "monotonic_tension_yield",
        "monotonic_steel_tension_yield",
        "elastic_only_replay",
        "monotonic_compression_yield",
        "monotonic_shell_bending_yield",
        "elastic_drilling_stiffness_replay",
        "plastic_reloading_from_committed_state",
        "elastic_unloading_from_committed_state",
        "reverse_compression_from_committed_state",
    ]
    assert summary["state_updated_material_newton_seed_structural_components"] == [
        "frame_fiber_axial",
        "rc_frame_fiber_axial",
        "shell_drilling_stiffness",
        "shell_layer_bending",
        "shell_layer_membrane",
        "src_composite_axial",
        "steel_frame_fiber_axial",
    ]
    assert summary["state_updated_material_newton_seed_material_families"] == [
        "reinforced_concrete",
        "shell_equivalent_plate",
        "src_composite",
        "steel",
    ]
    assert summary["state_updated_material_newton_seed_section_integrations"] == [
        "composite_fiber",
        "frame_fiber",
        "layered_shell",
    ]
    assert summary["state_updated_material_newton_seed_strain_modes"] == [
        "axial",
        "axial_reverse",
        "bending",
        "drilling",
        "membrane",
    ]
    assert summary["path_dependent_material_update_seed_case_count"] == 6
    assert summary["path_dependent_material_replay_seed_case_count"] == 9
    assert summary["material_state_persistence_replay_seed_passed"] is True
    assert summary["material_jvp_relative_error_pass"] is True
    assert summary["material_jvp_max_relative_error"] <= 1.0e-6
    assert summary["frame_material_newton_seed_pass"] is True
    assert summary["shell_material_newton_seed_pass"] is True
    assert summary["state_updated_material_newton_breadth_seed_coverage_ready"] is True
    assert summary["state_updated_material_newton_breadth_closed"] is False
    assert summary["sparse_backend_used"] is False
    assert summary["matrix_backend"] == "numpy_linalg_solve_scalar"
    assert sorted(summary["input_checksums"]) == [
        "scripts/build_phase2_material_newton_breadth_artifacts.py",
        "scripts/verify_quality_gate.py",
        "src/structural_analysis/assembly/g1_contract.py",
        "src/structural_analysis/assembly/material_state.py",
        "src/structural_analysis/solvers/nonlinear/__init__.py",
        "src/structural_analysis/solvers/nonlinear/newton.py",
        "tests/test_build_phase2_material_newton_breadth_artifacts.py",
        "tests/test_g1_assembly_contract.py",
    ]
    assert summary["blockers_remaining"] == [
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "frame_shell_material_coupling_not_closed",
        "mesh_load_step_nonlinear_convergence_suite_not_closed",
        "sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
        "general_newton_jacobian_assembly_not_closed",
        "full_load_g1_material_newton_breadth_not_closed_by_seed_artifact",
    ]

    assert laws_payload["status"] == "ready"
    assert laws_payload["contract_pass"] is True
    assert laws_payload["g1_closure_claim"] is False
    assert laws_payload["material_newton_closure_claim"] is False
    assert laws_payload["residual_formula"] == "F_internal_minus_F_external"
    assert len(law_results) == 2

    assert state_updated_payload["status"] == "ready"
    assert state_updated_payload["contract_pass"] is True
    assert state_updated_payload["g1_closure_claim"] is False
    assert state_updated_payload["material_newton_closure_claim"] is False
    assert (
        state_updated_payload[
            "state_updated_material_newton_breadth_seed_coverage_ready"
        ]
        is True
    )
    assert state_updated_payload["state_updated_material_newton_breadth_closed"] is False
    assert state_updated_payload["state_updated_material_newton_seed_case_count"] == 9
    assert state_updated_payload["path_dependent_material_update_seed_case_count"] == 6
    assert state_updated_payload["path_dependent_material_replay_seed_case_count"] == 9
    assert state_updated_payload["material_state_persistence_replay_seed_passed"] is True
    assert state_updated_payload["material_jvp_relative_error_pass"] is True
    assert state_updated_payload["frame_material_newton_seed_pass"] is True
    assert state_updated_payload["shell_material_newton_seed_pass"] is True

    state_rows = state_updated_payload["state_updated_seed_cases"]
    assert len(state_rows) == 9
    assert all(row["case_contract_pass"] is True for row in state_rows)
    assert all(row["state_updated_material_newton"] is True for row in state_rows)
    assert all(row["jvp_finite_difference_pass"] is True for row in state_rows)
    assert all(row["direct_residual_newton_parity_pass"] is True for row in state_rows)
    assert all(row["checkpoint_replay_pass"] is True for row in state_rows)
    assert all(row["regularization_used"] is False for row in state_rows)
    assert all(row["fallback_used"] is False for row in state_rows)
    assert all(row["g1_closure_claim"] is False for row in state_rows)
    assert {row["return_mapping"] for row in state_rows} == {
        "plastic_corrector",
        "elastic_trial_state",
    }

    for row in law_results:
        result = row["result"]
        metrics = result["metrics"]
        verification = result["verification"]

        assert row["law_contract_pass"] is True
        assert row["residual_gate_passed"] is True
        assert row["increment_gate_passed"] is True
        assert row["tangent_gate_passed"] is True
        assert row["displacement_gate_passed"] is True
        assert row["regularization_used"] is False
        assert row["fallback_used"] is False

        assert result["status"] == "ready"
        assert result["contract_pass"] is True
        assert result["g1_closure_claim"] is False
        assert result["material_newton_closure_claim"] is False
        assert result["residual_formula"] == "F_internal_minus_F_external"
        assert result["globalization"] == "backtracking_line_search"
        assert result["regularization_used"] is False
        assert result["fallback_used"] is False
        assert metrics["residual_gate_passed"] is True
        assert metrics["increment_gate_passed"] is True
        assert metrics["regularization_used"] is False
        assert metrics["fallback_used"] is False
        assert metrics["relative_residual"] <= 1.0e-10
        assert metrics["final_increment_abs_m"] <= 1.0e-12
        assert verification["displacement_gate_passed"] is True
        assert verification["tangent_gate_passed"] is True
        assert verification["displacement_abs_error_m"] <= 1.0e-10
        assert verification["tangent_finite_difference_check"]["pass"] is True


def test_phase2_material_newton_breadth_check_detects_stale_outputs(tmp_path: Path) -> None:
    ok, message = module.check_material_newton_breadth_artifacts(
        repo_root=REPO_ROOT,
        laws_out=tmp_path / "missing_laws.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_material_newton_breadth_missing:")


def test_phase2_material_newton_breadth_uses_same_residual_contract_for_both_laws() -> None:
    from structural_analysis.solvers.nonlinear.newton import (
        ScalarBilinearHardeningAxialReference,
        ScalarNonlinearAxialReference,
        newton_raphson_scalar,
        NewtonRaphsonConfig,
    )

    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    for problem in (
        ScalarNonlinearAxialReference(),
        ScalarBilinearHardeningAxialReference(),
    ):
        solution = newton_raphson_scalar(problem, config=config)
        assert solution.status == "ready"
        assert solution.metrics["residual_formula"] == "F_internal_minus_F_external"
        assert solution.metrics["contract_pass"] is True
