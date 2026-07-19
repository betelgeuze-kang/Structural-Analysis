from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "build_stateful_nonlinear_no_solve_reaction_only_artifact.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_stateful_nonlinear_no_solve_reaction_only_artifact",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_state_transition_without_newton_convergence() -> None:
    receipt = module.build_stateful_nonlinear_no_solve_reaction_only_artifact(
        repo_root=ROOT
    )
    verification = receipt["verification"]

    assert receipt["status"] == "ready"
    assert receipt["contract_pass"] is True
    assert receipt["terminal_disposition"] == "no_solve_reaction_only"
    assert receipt["engine_v2_terminal_disposition"] == (
        "no_solve_reaction_only"
    )
    assert receipt["engine_v2_reference"]["terminal_disposition"] == (
        "no_solve_reaction_only"
    )
    assert receipt["engine_v2_reference"]["free_count"] == 0
    assert receipt["engine_v2_reference"]["free_nnz"] == 0
    assert receipt["engine_v2_reference"]["free_csr_row_ptr"] == [0]
    assert receipt["engine_v2_reference"][
        "free_csr_column_index_count"
    ] == 0
    assert receipt["engine_v2_reference"][
        "free_csr_global_value_index_count"
    ] == 0
    assert receipt["engine_v2_reference"]["solver_executed"] is False
    assert receipt["engine_v2_reference"][
        "fully_constrained_recurrence_allowed"
    ] is False
    assert receipt["residual_formula"] == "F_internal_minus_F_external"
    assert receipt["load_factors"] == [0.5, 1.0]
    assert receipt["reused_evidence"] is False
    assert receipt["newton_convergence_claim"] is False
    assert receipt["full_building_equilibrium_claim"] is False
    assert receipt["material_newton_breadth_closure_claim"] is False
    assert receipt["g1_closure_claim"] is False
    assert receipt["production_rocm_hip_parity_claim"] is False
    assert receipt["external_validation_claim"] is False
    assert receipt["release_readiness_claim"] is False

    assert verification == {
        "case_count": 3,
        "ready_case_count": 3,
        "committed_step_count": 6,
        "material_state_changed_case_count": 3,
        "deterministic_replay_exact_case_count": 3,
        "state_hash_chain_exact_case_count": 3,
        "maximum_reaction_balance_abs_kn": 0.0,
        "newton_iteration_count": 0,
        "linear_solve_count": 0,
        "line_search_step_count": 0,
        "solver_executed": False,
        "residual_norm_applicable": False,
        "increment_norm_applicable": False,
        "convergence_claim": False,
        "regularization_count": 0,
        "fallback_count": 0,
        "engine_v2_terminal_disposition_aligned": True,
    }

    assert [case["material_family"] for case in receipt["cases"]] == [
        "uniaxial_concrete_damage",
        "perfect_bond_composite_section",
        "bilinear_force_deformation_link",
    ]
    for case in receipt["cases"]:
        assert case["status"] == "ready"
        assert case["contract_pass"] is True
        assert case["active_equation_count"] == 0
        assert case["terminal_disposition"] == "no_solve_reaction_only"
        assert case["committed_step_count"] == 2
        assert case["material_state_changed"] is True
        assert case["state_hash_chain_exact"] is True
        assert case["deterministic_replay_exact"] is True
        assert case["final_state_hash_replay_exact"] is True
        assert case["initial_state_hash"] != case["final_state_hash"]
        assert case["newton_iteration_count"] == 0
        assert case["linear_solve_count"] == 0
        assert case["line_search_step_count"] == 0
        assert case["solver_executed"] is False
        assert case["residual_norm_applicable"] is False
        assert case["increment_norm_applicable"] is False
        assert case["convergence_claim"] is False
        assert case["regularization_count"] == 0
        assert case["fallback_count"] == 0
        for step in case["steps"]:
            assert step["contract_pass"] is True
            assert step["committed"] is True
            assert step["residual_dimension"] == 0
            assert step["jacobian_shape"] == [0, 0]
            assert step["solver_executed"] is False
            assert step["matrix_backend"] is None
            assert step["residual_gate_passed"] is None
            assert step["increment_gate_passed"] is None
            assert step["convergence_claim"] is False
            assert step["reaction_observation_only"] is True
            assert step["terminal_contract_pass"] is True
            assert step["iterative_solver_contract_pass"] is False
            assert step["no_solve_contract_pass"] is True
            assert step["material_state_changed"] is True


def test_builder_check_reports_missing_artifact(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    ok, message = (
        module.check_stateful_nonlinear_no_solve_reaction_only_artifact(
            repo_root=ROOT,
            output=missing,
        )
    )

    assert ok is False
    assert message == f"stateful_nonlinear_no_solve_missing:{missing}"


def test_committed_no_solve_receipt_matches_builder() -> None:
    ok, message = (
        module.check_stateful_nonlinear_no_solve_reaction_only_artifact(
            repo_root=ROOT
        )
    )

    assert ok is True
    assert message == "stateful_nonlinear_no_solve_consistent"
