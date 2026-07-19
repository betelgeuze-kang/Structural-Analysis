from __future__ import annotations

import pytest

from structural_analysis.benchmark.shallow_arch_arc_length import (
    SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    build_shallow_arch_arc_length_benchmark_seed,
)


def test_shallow_arch_arc_length_benchmark_closes_narrow_path_contract() -> None:
    payload = build_shallow_arch_arc_length_benchmark_seed()
    verification = payload["verification"]
    claims = payload["claims"]

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert all(verification.values())
    assert claims["scalar_arc_length_path_following"] is True
    assert claims["shallow_arch_limit_point_crossing"] is True
    assert claims["failed_step_rollback"] is True
    assert claims["checkpoint_restart"] is True
    assert claims["multi_dof_frame_shell_arc_length"] is False
    assert claims["lee_frame_snapthrough"] is False
    assert claims["material_geometric_coupling"] is False
    assert claims["production_rocm_hip_parity"] is False
    assert claims["geometric_nonlinear_benchmark_breadth"] is False


def test_limit_point_is_bracketed_with_bounded_load_error() -> None:
    payload = build_shallow_arch_arc_length_benchmark_seed()
    exact = payload["exact_first_limit_point"]
    bracket = payload["computed_first_limit_bracket"]

    assert bracket["below_displacement_m"] < exact["displacement_m"]
    assert exact["displacement_m"] < bracket["above_displacement_m"]
    assert bracket["first_limit_load_relative_error"] <= 0.01
    assert bracket["contract_pass"] is True
    assert exact["load_kn"] == pytest.approx(29.605176007630757)


def test_arc_length_benchmark_records_all_path_branches_without_fallback() -> None:
    result = build_shallow_arch_arc_length_benchmark_seed()["solver_result"]
    metrics = result["metrics"]

    assert result["status"] == "ready"
    assert metrics["accepted_step_count"] == 27
    assert metrics["rejected_step_count"] == 1
    assert metrics["rollback_exact"] is True
    assert metrics["fallback_count"] == 0
    assert metrics["regularization_count"] == 0
    assert metrics["consistent_tangent_sign_change_observed"] is True
    assert metrics["descending_load_branch_observed"] is True
    assert metrics["negative_load_branch_observed"] is True
    assert metrics["rehardening_branch_observed"] is True


def test_tangent_samples_match_centered_finite_differences() -> None:
    rows = build_shallow_arch_arc_length_benchmark_seed()[
        "consistent_tangent_finite_difference_rows"
    ]

    assert len(rows) == 6
    assert all(row["contract_pass"] is True for row in rows)
    assert max(row["absolute_error_kn_per_m"] for row in rows) <= 1.0e-5


def test_arc_length_benchmark_is_deterministic_and_claim_bounded() -> None:
    first = build_shallow_arch_arc_length_benchmark_seed()
    second = build_shallow_arch_arc_length_benchmark_seed()

    assert first == second
    assert first["claim_boundary"] == SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY
    assert "not a multi-DOF frame" in first["claim_boundary"]
    assert "multi_dof_frame_shell_arc_length_not_implemented" in first[
        "blockers_remaining"
    ]
