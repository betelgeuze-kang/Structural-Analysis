from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.benchmark.geometric_nonlinear import (
    TwoBarShallowArch,
    assemble_euler_column_system,
    build_geometric_nonlinear_benchmark_seed,
    euler_column_buckling_benchmark,
    finite_difference_shallow_arch_checks,
    modal_pdelta_amplification_benchmark,
    shallow_arch_snapthrough_benchmark,
)


def test_euler_column_matrices_are_symmetric_and_pinned_only_in_translation() -> None:
    system = assemble_euler_column_system(element_count=4)

    assert system.full_dof_count == 10
    assert system.free_dofs == (1, 2, 3, 4, 5, 6, 7, 9)
    assert system.elastic_stiffness.shape == (8, 8)
    assert system.unit_compression_geometric_stiffness.shape == (8, 8)
    assert np.array_equal(system.elastic_stiffness, system.elastic_stiffness.T)
    assert np.array_equal(
        system.unit_compression_geometric_stiffness,
        system.unit_compression_geometric_stiffness.T,
    )
    assert system.elastic_stiffness.flags.writeable is False
    assert system.unit_compression_geometric_stiffness.flags.writeable is False


def test_euler_column_converges_to_closed_form_load_and_sine_mode() -> None:
    result = euler_column_buckling_benchmark()
    rows = result["mesh_rows"]

    assert result["contract_pass"] is True
    assert result["exact_critical_load_kn"] == pytest.approx(
        math.pi**2 * 10_000.0 / 3.0**2
    )
    assert [row["element_count"] for row in rows] == [2, 4, 8, 16]
    assert all(row["computed_critical_load_kn"] > result["exact_critical_load_kn"] for row in rows)
    assert result["monotonic_upper_bound_convergence"] is True
    assert min(result["observed_convergence_orders"]) >= 3.7
    assert result["finest_relative_error"] <= 3.0e-6
    assert min(row["mode_mac"] for row in rows) >= 1.0 - 1.0e-12
    assert max(
        row["generalized_eigen_residual_relative_inf"] for row in rows
    ) <= 1.0e-10


def test_modal_pdelta_matches_exact_eigenmode_amplification() -> None:
    result = modal_pdelta_amplification_benchmark()
    rows = result["load_rows"]

    assert result["contract_pass"] is True
    assert result["general_frame_pdelta_claim"] is False
    assert [row["computed_modal_amplification"] for row in rows] == pytest.approx(
        [1.0, 4.0 / 3.0, 2.0, 4.0, 10.0],
        rel=1.0e-10,
    )
    assert result["amplification_monotonic"] is True
    assert max(row["relative_error"] for row in rows) <= 1.0e-10
    assert max(row["equilibrium_residual_relative_inf"] for row in rows) <= 1.0e-10


def test_two_bar_shallow_arch_tangent_is_the_energy_hessian() -> None:
    arch = TwoBarShallowArch()
    limit_displacement, _ = arch.first_limit_point()
    check = finite_difference_shallow_arch_checks(
        arch,
        downward_displacement_m=0.5 * limit_displacement,
    )

    assert check["contract_pass"] is True
    assert check["tangent_relative_error"] <= 1.0e-8
    assert check["energy_derivative_relative_error"] <= 1.0e-8
    assert arch.strain_energy_kn_m(0.0) == pytest.approx(0.0)


def test_two_bar_shallow_arch_traces_limit_point_and_inverted_branch() -> None:
    result = shallow_arch_snapthrough_benchmark()
    limit = result["first_limit_point"]
    shape = result["path_shape"]

    assert result["contract_pass"] is True
    assert 0.0 < limit["downward_displacement_m"] < 0.2
    assert limit["equilibrium_load_kn"] > 0.0
    assert abs(limit["consistent_tangent_kn_per_m"]) <= 1.0e-10
    assert limit["tangent_before_kn_per_m"] > 0.0
    assert limit["tangent_after_kn_per_m"] < 0.0
    assert shape["negative_force_after_apex_inversion_kn"] < 0.0
    assert shape["positive_force_after_rehardening_kn"] > 0.0
    assert result["arc_length_solver_claim"] is False
    assert result["lee_frame_claim"] is False


def test_geometric_seed_is_deterministic_and_remains_partial() -> None:
    first = build_geometric_nonlinear_benchmark_seed()
    second = build_geometric_nonlinear_benchmark_seed()

    assert first == second
    assert first["status"] == "partial"
    assert first["contract_pass"] is True
    assert first["implemented_benchmarks_contract_pass"] is True
    assert first["geometric_nonlinear_benchmark_breadth_claim"] is False
    assert first["general_frame_pdelta_claim"] is False
    assert first["lee_frame_snapthrough_claim"] is False
    assert first["arc_length_path_following_claim"] is False
    assert first["continuum_cantilever_large_rotation_claim"] is False
    assert first["general_2d_3d_geometric_stiffness_claim"] is False


@pytest.mark.parametrize("element_count", [0, -1, True])
def test_euler_column_rejects_invalid_element_counts(element_count: int) -> None:
    with pytest.raises(ValueError, match="element_count"):
        assemble_euler_column_system(element_count=element_count)


def test_geometric_benchmarks_reject_invalid_paths() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        euler_column_buckling_benchmark(element_counts=(2, 4, 4))
    with pytest.raises(ValueError, match=r"\[0, 1\)"):
        modal_pdelta_amplification_benchmark(load_ratios=(0.0, 1.0))
    with pytest.raises(ValueError, match="sample_count"):
        shallow_arch_snapthrough_benchmark(sample_count=8)
