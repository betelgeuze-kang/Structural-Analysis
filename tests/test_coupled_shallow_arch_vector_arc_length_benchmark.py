from __future__ import annotations

from structural_analysis.benchmark.coupled_shallow_arch_arc_length import (
    COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY,
    build_coupled_shallow_arch_vector_arc_length_benchmark_seed,
)


def test_coupled_benchmark_closes_only_the_dense_vector_kernel_contract() -> None:
    payload = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()
    verification = payload["verification"]
    claims = payload["claims"]

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert verification["path_gate_passed"] is True
    assert verification["exact_scalar_reduction_gate_passed"] is True
    assert verification["limit_point_gate_passed"] is True
    assert verification["tangent_energy_finite_difference_gate_passed"] is True
    assert verification["rollback_evidence_passed"] is True
    assert verification["checkpoint_restart_exact"] is True
    assert verification["deterministic_replay_exact"] is True
    assert claims["dense_multi_dof_vector_arc_length"] is True
    assert claims["coupled_two_dof_limit_point_crossing"] is True
    assert claims["general_frame_shell_arc_length"] is False
    assert claims["lee_frame_snapthrough"] is False
    assert claims["production_sparse_backend"] is False
    assert claims["production_rocm_hip_parity"] is False
    assert claims["g1_full_building_closure"] is False


def test_coupled_benchmark_matches_its_exact_scalar_reduction() -> None:
    payload = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()
    errors = payload["exact_reduction_errors"]

    assert errors["contract_pass"] is True
    assert errors["maximum_coupling_relation_absolute_error_m"] <= 1.0e-12
    assert errors["maximum_reduced_equilibrium_absolute_error_kn"] <= 1.0e-10


def test_coupled_benchmark_brackets_first_limit_point_below_one_percent() -> None:
    payload = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()
    exact = payload["exact_first_limit_point"]
    bracket = payload["computed_first_limit_bracket"]

    assert bracket["below_primary_displacement_m"] < exact["primary_displacement_m"]
    assert exact["primary_displacement_m"] < bracket["above_primary_displacement_m"]
    assert bracket["first_limit_load_relative_error"] <= 0.01
    assert bracket["contract_pass"] is True


def test_coupled_benchmark_checks_tangent_symmetry_and_energy_gradient() -> None:
    rows = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()[
        "finite_difference_rows"
    ]

    assert len(rows) == 6
    assert all(row["contract_pass"] is True for row in rows)
    assert max(
        row["maximum_tangent_absolute_error_kn_per_m"] for row in rows
    ) <= 1.0e-5
    assert max(
        row["maximum_energy_gradient_absolute_error_kn"] for row in rows
    ) <= 1.0e-7
    assert all(row["tangent_symmetry_absolute_error_kn_per_m"] == 0.0 for row in rows)


def test_coupled_benchmark_is_deterministic_and_claim_bounded() -> None:
    first = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()
    second = build_coupled_shallow_arch_vector_arc_length_benchmark_seed()

    assert first == second
    assert first["claim_boundary"] == COUPLED_SHALLOW_ARCH_ARC_LENGTH_CLAIM_BOUNDARY
    assert "does not verify a frame" in first["claim_boundary"]
    assert "frame_shell_element_formulation_not_connected" in first[
        "blockers_remaining"
    ]
