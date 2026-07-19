from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_phase2_adaptive_newton_continuation_artifacts.py"
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_adaptive_newton_continuation_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_adaptive_newton_truth_without_g1_promotion() -> None:
    payloads = module.build_phase2_adaptive_newton_continuation_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert result["analytic_seed_full_load_pass"] is True
    assert result["g1_full_load_claim"] is False
    assert result["full_mesh_closure_claim"] is False
    assert result["production_nonlinear_closure_claim"] is False
    assert result["metrics"]["final_load_factor"] == 1.0
    assert result["metrics"]["rejected_attempt_count"] >= 1
    assert result["metrics"]["rollback_exact_all"] is True
    assert result["metrics"]["fallback_count"] == 0
    assert result["metrics"]["regularization_count"] == 0
    assert result["metrics"]["no_solve_reaction_only_step_count"] == 0
    assert result["metrics"]["iterative_solver_step_count"] == 4
    assert result["metrics"]["solver_executed_step_count"] == 4
    assert result["metrics"]["newton_convergence_claim_count"] == 4
    assert result["metrics"]["solver_executed"] is True
    assert result["metrics"]["convergence_claim"] is True
    assert result["metrics"]["reaction_observation_only"] is False
    assert result["metrics"]["terminal_dispositions"] == [
        "solve_free_equations"
    ]
    assert result["verification"]["rollback_exact_gate_passed"] is True
    assert result["verification"]["line_search_history_present"] is True
    assert (
        result["verification"]["checkpoint_restart"]["exact_final_state_match"]
        is True
    )
    assert result["verification"]["finite_difference_jacobian"]["pass"] is True
    assert result["verification"]["quadratic_convergence"]["pass"] is True

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["final_load_factor"] == 1.0
    assert summary["rollback_exact_gate_passed"] is True
    assert summary["checkpoint_restart_exact_gate_passed"] is True
    assert summary["finite_difference_jacobian_gate_passed"] is True
    assert summary["quadratic_convergence_gate_passed"] is True
    assert summary["no_solve_reaction_only_step_count"] == 0
    assert summary["iterative_solver_step_count"] == 4
    assert summary["solver_executed_step_count"] == 4
    assert summary["newton_convergence_claim_count"] == 4
    assert summary["solver_executed"] is True
    assert summary["convergence_claim"] is True
    assert summary["reaction_observation_only"] is False
    assert summary["terminal_dispositions"] == ["solve_free_equations"]
    assert summary["g1_full_load_claim"] is False
    assert "g1_full_building_load_factor_1_not_closed" in summary["blockers_remaining"]
    assert "two-element 1D" in summary["claim_boundary"]


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = module.check_phase2_adaptive_newton_continuation_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_adaptive_newton_continuation_missing:")


def test_committed_adaptive_newton_artifacts_match_builder() -> None:
    ok, message = (
        module.check_phase2_adaptive_newton_continuation_artifacts(
            repo_root=ROOT
        )
    )

    assert ok is True
    assert message == "phase2_adaptive_newton_continuation_consistent"
