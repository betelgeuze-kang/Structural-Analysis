from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_phase2_mesh_load_step_convergence_artifacts.py"

SPEC = importlib.util.spec_from_file_location(
    "build_phase2_mesh_load_step_convergence_artifacts",
    SCRIPT_PATH,
)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_phase2_mesh_load_step_convergence_builds_honest_grid_artifacts() -> None:
    artifacts = module.build_phase2_mesh_load_step_convergence_artifacts(repo_root=REPO_ROOT)
    result = artifacts["result"]
    summary = artifacts["summary"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert result["analysis_type"] == "nonlinear_static_mesh_load_step_convergence_seed"
    assert result["residual_formula"] == "F_internal_minus_F_external"
    assert summary["element_counts"] == [1, 2, 4]
    assert summary["load_partition_counts"] == [1, 2, 4]
    assert summary["case_count"] == 9
    assert len(result["rows"]) == 9
    assert summary["all_rows_contract_pass"] is True
    assert summary["all_tangent_gates_passed"] is True
    assert summary["all_series_force_gates_passed"] is True
    assert summary["tip_displacement_spread_m"] <= module.TIP_DISPLACEMENT_TOLERANCE_M
    assert all(
        value <= module.TIP_DISPLACEMENT_TOLERANCE_M
        for value in summary["partition_tip_spread_by_element_count_m"].values()
    )
    assert result["regularization_used"] is False
    assert result["fallback_used"] is False
    assert result["guarded_solver_usage_present"] is False
    assert result["g1_closure_claim"] is False
    assert result["mesh_load_step_convergence_closure_claim"] is False
    assert result["full_mesh_closure_claim"] is False
    assert summary["g1_closure_claim"] is False
    assert summary["regularization_used"] is False
    assert summary["fallback_used"] is False
    assert summary["guarded_solver_usage_present"] is False
    assert summary["mesh_load_step_convergence_closure_claim"] is False
    assert summary["full_mesh_closure_claim"] is False
    assert summary["blockers_remaining"] == [
        "general_frame_shell_mesh_load_step_convergence_not_closed",
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "general_sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
        "broad_material_newton_breadth_not_closed",
    ]
    assert "not close general frame/shell meshes" in result["claim_boundary"]

    row_keys = {(row["element_count"], row["partition_count"]) for row in result["rows"]}
    assert row_keys == {
        (element_count, partition_count)
        for element_count in module.ELEMENT_COUNTS
        for partition_count in module.LOAD_PARTITION_COUNTS
    }
    for row in result["rows"]:
        assert row["contract_pass"] is True
        assert row["final_residual_gate_passed"] is True
        assert row["final_increment_gate_passed"] is True
        assert row["tangent_gate_passed"] is True
        assert row["series_force_gate_passed"] is True
        assert row["final_residual_inf_norm_kn"] <= module.RESIDUAL_TOLERANCE_KN
        assert row["regularization_used"] is False
        assert row["fallback_used"] is False
        assert len(row["steps"]) == row["partition_count"]
        assert row["steps"][-1]["load_factor"] == 1.0
        assert all(step["contract_pass"] is True for step in row["steps"])


def test_phase2_mesh_load_step_flags_guarded_solver_usage_from_steps() -> None:
    row = {
        "regularization_used": False,
        "fallback_used": False,
        "steps": [
            {"regularization_used": False, "fallback_used": False},
            {"regularization_used": True, "fallback_used": False},
        ],
    }

    assert module._row_has_guarded_solver_usage(row) is True


def test_phase2_mesh_load_step_flags_guarded_solver_usage_from_row() -> None:
    row = {
        "regularization_used": False,
        "fallback_used": True,
        "steps": [{"regularization_used": False, "fallback_used": False}],
    }

    assert module._row_has_guarded_solver_usage(row) is True


def test_phase2_mesh_load_step_convergence_check_detects_missing_outputs(tmp_path: Path) -> None:
    ok, message = module.check_phase2_mesh_load_step_convergence_artifacts(
        repo_root=REPO_ROOT,
        result_out=tmp_path / "missing_result.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_mesh_load_step_convergence_missing:")
