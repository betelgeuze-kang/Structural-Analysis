from __future__ import annotations

from structural_analysis.benchmark.arc_length_fgmres_continuation import (
    ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY,
    build_arc_length_cpu_fgmres_continuation_seed,
)


def test_full_short_path_uses_cpu_fgmres_for_every_tangent_solve() -> None:
    payload = build_arc_length_cpu_fgmres_continuation_seed()
    verification = payload["verification"]
    claims = payload["claims"]

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["tangent_solver_mode"] == "materialized_tangent_matrix"
    assert payload["solver_result"]["metrics"]["tangent_linear_solver_mode"] == (
        "materialized_tangent_matrix"
    )
    assert verification["path_gate_passed"] is True
    assert verification["limit_point_crossed"] is True
    assert verification["negative_load_branch_reached"] is True
    assert verification["external_tangent_integration_gate_passed"] is True
    assert verification["all_tangent_solves_ready"] is True
    assert verification["tangent_solve_count"] == 57
    assert verification["maximum_tangent_solve_iteration_count"] == 2
    assert verification[
        "maximum_tangent_solve_explicit_residual_inf_norm_kn"
    ] <= 1.0e-12
    assert claims["complete_short_path_cpu_fgmres_arc_length_integration"] is True
    assert claims["engine_v2_cpu_fgmres_every_tangent_solve"] is True
    assert claims["general_frame_shell_arc_length"] is False
    assert claims["production_scale_sparse_preconditioner"] is False
    assert claims["production_rocm_hip_nonlinear_parity"] is False
    assert claims["g1_full_building_closure"] is False


def test_full_short_path_rolls_back_and_restarts_exactly() -> None:
    verification = build_arc_length_cpu_fgmres_continuation_seed()["verification"]

    assert verification["rollback_evidence_passed"] is True
    assert verification["checkpoint_restart_exact"] is True
    assert verification["deterministic_replay_exact"] is True
    assert verification["restart_checkpoint_state_hash"].startswith("sha256:")
    assert verification["final_checkpoint_state_hash"] == verification[
        "restarted_final_checkpoint_state_hash"
    ]
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0


def test_full_short_path_matches_dense_augmented_and_exact_reduction() -> None:
    verification = build_arc_length_cpu_fgmres_continuation_seed()["verification"]

    assert verification["dense_augmented_reference_gate_passed"] is True
    assert verification["exact_scalar_reduction_gate_passed"] is True
    assert verification["same_dense_reference_checkpoint_count"] is True
    assert verification[
        "maximum_dense_reference_displacement_absolute_error_m"
    ] <= 1.0e-12
    assert verification[
        "maximum_dense_reference_load_factor_absolute_error"
    ] <= 1.0e-12
    assert verification["maximum_coupling_relation_absolute_error_m"] <= 1.0e-12
    assert verification[
        "maximum_reduced_equilibrium_absolute_error_kn"
    ] <= 1.0e-10


def test_full_short_path_is_deterministic_and_claim_bounded() -> None:
    first = build_arc_length_cpu_fgmres_continuation_seed()
    second = build_arc_length_cpu_fgmres_continuation_seed()

    assert first == second
    assert first["claim_boundary"] == ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY
    assert "does not connect a frame/shell residual" in first["claim_boundary"]
    assert "frame_shell_consistent_residual_not_connected" in first[
        "blockers_remaining"
    ]
