from __future__ import annotations

import json
import math

import numpy as np
import pytest

from structural_analysis.benchmark.cantilever_elastica import (
    CANTILEVER_ELASTICA_SCHEMA_VERSION,
    assemble_discrete_cantilever_elastica,
    cantilever_elastica_large_rotation_benchmark,
    cantilever_elastica_reference,
    finite_difference_cantilever_elastica_checks,
    solve_discrete_cantilever_elastica,
)


def test_continuum_reference_matches_large_rotation_regression_values() -> None:
    reference = cantilever_elastica_reference(dimensionless_load=4.0)

    assert reference["root_converged"] is True
    assert reference["tip_rotation_rad"] == pytest.approx(
        1.1212393474875764,
        abs=2.0e-12,
    )
    assert reference["tip_x_over_length"] == pytest.approx(
        0.6710587577531542,
        abs=2.0e-12,
    )
    assert reference["tip_downward_y_over_length"] == pytest.approx(
        0.6699641812776667,
        abs=2.0e-12,
    )
    assert reference["length_constraint_abs_error"] <= 1.0e-12
    assert reference["tip_rotation_rad"] > 1.0


def test_continuum_reference_recovers_small_rotation_asymptote() -> None:
    dimensionless_load = 0.01
    reference = cantilever_elastica_reference(dimensionless_load=dimensionless_load)

    assert reference["tip_rotation_rad"] == pytest.approx(
        dimensionless_load / 2.0,
        rel=2.0e-5,
    )
    assert reference["tip_downward_y_over_length"] == pytest.approx(
        dimensionless_load / 3.0,
        rel=2.0e-5,
    )
    assert reference["tip_x_over_length"] == pytest.approx(1.0, rel=2.0e-5)


def test_discrete_residual_and_tangent_are_energy_derivatives() -> None:
    check = finite_difference_cantilever_elastica_checks()

    assert check["contract_pass"] is True
    assert check["energy_gradient_relative_error"] <= 1.0e-8
    assert check["tangent_hessian_relative_error"] <= 1.0e-8
    assert check["tangent_symmetry_abs_max"] <= 1.0e-12

    rotations = np.linspace(0.05, 0.4, 7)
    _, residual, tangent = assemble_discrete_cantilever_elastica(
        rotations,
        dimensionless_load=2.3,
    )
    assert residual.shape == (7,)
    assert tangent.shape == (7, 7)
    assert np.array_equal(tangent, tangent.T)


def test_discrete_solver_uses_unseeded_load_continuation_without_fallback() -> None:
    solution = solve_discrete_cantilever_elastica(element_count=16)

    assert solution["initialization"] == (
        "zero_rotation_then_previous_accepted_load_state"
    )
    assert solution["all_load_steps_accepted"] is True
    assert len(solution["load_step_receipts"]) == 16
    assert solution["final_residual_inf"] <= 1.0e-9
    assert solution["tangent_symmetry_abs_max"] <= 1.0e-12
    assert solution["minimum_tangent_eigenvalue"] > 0.0
    assert solution["regularization_count"] == 0
    assert solution["fallback_count"] == 0
    assert solution["tip_rotation_rad"] > 1.0


def test_large_rotation_benchmark_converges_quadratically_and_stays_bounded() -> None:
    result = cantilever_elastica_large_rotation_benchmark()

    assert result["schema_version"] == CANTILEVER_ELASTICA_SCHEMA_VERSION
    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert [row["element_count"] for row in result["mesh_rows"]] == [
        8,
        16,
        32,
        64,
    ]
    assert all(result["monotonic_convergence"].values())
    assert result["minimum_observed_convergence_order"] >= 1.9
    assert max(result["finest_mesh_abs_errors"].values()) <= 5.0e-5
    assert result["large_rotation_checks"]["contract_pass"] is True
    assert result["continuum_cantilever_large_rotation_benchmark_claim"] is True
    assert result["production_corotational_beam_validation_claim"] is False
    assert result["lee_frame_snapthrough_claim"] is False
    assert result["general_geometric_nonlinear_frame_or_shell_claim"] is False
    assert result["material_geometric_coupling_claim"] is False
    assert result["production_sparse_or_hip_solver_claim"] is False
    assert result["geometric_nonlinear_benchmark_breadth_claim"] is False
    assert result["g1_closure_claim"] is False
    json.dumps(result, allow_nan=False, sort_keys=True)


@pytest.mark.parametrize("dimensionless_load", [0.0, -1.0, math.inf, math.nan])
def test_reference_rejects_invalid_dimensionless_load(
    dimensionless_load: float,
) -> None:
    with pytest.raises(ValueError, match="dimensionless_load"):
        cantilever_elastica_reference(dimensionless_load=dimensionless_load)


def test_discrete_benchmark_rejects_invalid_meshes() -> None:
    with pytest.raises(ValueError, match="at least three"):
        cantilever_elastica_large_rotation_benchmark(element_counts=(8, 16))
    with pytest.raises(ValueError, match="strictly increasing"):
        cantilever_elastica_large_rotation_benchmark(element_counts=(8, 16, 16))
    with pytest.raises(ValueError, match="element_count"):
        solve_discrete_cantilever_elastica(element_count=True)
