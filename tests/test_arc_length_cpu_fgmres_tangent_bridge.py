from __future__ import annotations

from structural_analysis.benchmark.arc_length_fgmres_bridge import (
    ARC_LENGTH_FGMRES_BRIDGE_CLAIM_BOUNDARY,
    build_arc_length_cpu_fgmres_tangent_bridge_seed,
)


def test_arc_length_bridge_closes_only_the_tangent_solve_contract() -> None:
    payload = build_arc_length_cpu_fgmres_tangent_bridge_seed()
    verification = payload["verification"]
    claims = payload["claims"]

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert verification["all_tangent_solves_ready"] is True
    assert verification["positive_negative_positive_determinant_coverage"] is True
    assert verification["schur_augmented_correction_equivalence"] is True
    assert verification["deterministic_replay_exact"] is True
    assert verification["tangent_solve_count"] == 6
    assert verification["fallback_count"] == 0
    assert verification["regularization_count"] == 0
    assert claims["engine_v2_cpu_fgmres_tangent_bridge"] is True
    assert claims["schur_augmented_increment_equivalence"] is True
    assert claims["indefinite_tangent_solve"] is True
    assert claims["complete_arc_length_backend_integration"] is False
    assert claims["frame_shell_residual_assembly"] is False
    assert claims["production_sparse_nonlinear_backend"] is False
    assert claims["production_rocm_hip_parity"] is False
    assert claims["g1_full_building_closure"] is False


def test_arc_length_bridge_schur_increment_matches_augmented_solve() -> None:
    rows = build_arc_length_cpu_fgmres_tangent_bridge_seed()["state_rows"]

    assert len(rows) == 3
    assert all(row["contract_pass"] is True for row in rows)
    assert max(row["maximum_correction_absolute_error"] for row in rows) <= 1.0e-12
    assert max(row["augmented_linear_residual_inf_norm"] for row in rows) <= 1.0e-12
    assert max(
        row["residual_tangent_solve_direct_absolute_error"] for row in rows
    ) <= 1.0e-12
    assert max(
        row["reference_load_tangent_solve_direct_absolute_error"] for row in rows
    ) <= 1.0e-12


def test_arc_length_bridge_covers_indefinite_tangent_without_fallback() -> None:
    rows = build_arc_length_cpu_fgmres_tangent_bridge_seed()["state_rows"]

    assert rows[0]["consistent_tangent_determinant"] > 0.0
    assert rows[1]["consistent_tangent_determinant"] < 0.0
    assert rows[2]["consistent_tangent_determinant"] > 0.0
    for row in rows:
        for solve_name in (
            "residual_tangent_solve",
            "reference_load_tangent_solve",
        ):
            solve = row[solve_name]
            assert solve["status"] == "ready"
            assert solve["contract_pass"] is True
            assert solve["solver"]["converged"] is True
            assert solve["solver"]["iteration_count"] == 2
            assert solve["solver"]["fallback_count"] == 0
            assert solve["solver"]["regularization_count"] == 0
            assert solve["explicit_residual"]["gate_passed"] is True


def test_arc_length_bridge_is_deterministic_and_claim_bounded() -> None:
    first = build_arc_length_cpu_fgmres_tangent_bridge_seed()
    second = build_arc_length_cpu_fgmres_tangent_bridge_seed()

    assert first == second
    assert first["claim_boundary"] == ARC_LENGTH_FGMRES_BRIDGE_CLAIM_BOUNDARY
    assert "does not run the complete continuation loop" in first["claim_boundary"]
    assert (
        "complete_continuation_loop_not_using_engine_v2_tangent_adapter"
        in first["blockers_remaining"]
    )
