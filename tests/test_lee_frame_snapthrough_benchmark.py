from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pytest

from structural_analysis.benchmark.lee_frame import (
    LEE_FRAME_PUBLISHED_PATH,
    LEE_FRAME_REFERENCE_DOI,
    LEE_FRAME_SCHEMA_VERSION,
    LeeFrameArcLengthProblem,
    build_lee_frame_snapthrough_benchmark,
    corotational_frame_element_response,
    finite_difference_lee_frame_checks,
)


@pytest.fixture(scope="module")
def lee_frame_receipt() -> dict[str, Any]:
    return build_lee_frame_snapthrough_benchmark()


def test_corotational_element_is_invariant_under_rigid_body_motion() -> None:
    coordinates = np.asarray([[0.2, -0.1], [1.1, 0.5]], dtype=np.float64)
    rigid_rotation = 0.73
    translation = np.asarray([0.4, -0.2], dtype=np.float64)
    rotation = np.asarray(
        [
            [math.cos(rigid_rotation), -math.sin(rigid_rotation)],
            [math.sin(rigid_rotation), math.cos(rigid_rotation)],
        ],
        dtype=np.float64,
    )
    current_coordinates = coordinates @ rotation.T + translation
    displacements = np.asarray(
        [
            *(current_coordinates[0] - coordinates[0]),
            rigid_rotation,
            *(current_coordinates[1] - coordinates[1]),
            rigid_rotation,
        ],
        dtype=np.float64,
    )

    response = corotational_frame_element_response(
        node_coordinates_m=coordinates,
        element_displacements=displacements,
        youngs_modulus_kn_per_m2=72_000_000.0,
        area_m2=6.0e-4,
        second_moment_m4=2.0e-8,
    )

    assert response.strain_energy_kn_m == pytest.approx(0.0, abs=1.0e-24)
    assert np.max(np.abs(response.internal_force_global)) <= 2.0e-12
    assert response.basic_deformations == pytest.approx((0.0, 0.0, 0.0), abs=2.0e-15)
    assert np.array_equal(
        response.consistent_tangent_global,
        response.consistent_tangent_global.T,
    )


def test_frame_geometry_supports_load_and_initial_tangent() -> None:
    problem = LeeFrameArcLengthProblem()
    zero_state = problem.initial_free_displacements_m()

    assert problem.node_coordinates_m.shape == (21, 2)
    assert len(problem.elements) == 20
    assert problem.free_dof_count == 59
    assert problem.load_point_node_index == 12
    assert problem.node_coordinates_m[problem.load_point_node_index] == pytest.approx(
        (0.24, 1.2)
    )
    assert problem.rotation_coordinate_scale_m == pytest.approx(0.12)
    assert problem.reference_load_kn()[problem.load_point_y_free_dof_index] == -1.0
    assert np.count_nonzero(problem.reference_load_kn()) == 1
    assert problem.strain_energy_kn_m(zero_state) == 0.0
    assert np.array_equal(problem.internal_force_kn(zero_state), np.zeros(59))

    tangent = problem.consistent_tangent_kn_per_m(zero_state)
    assert np.array_equal(tangent, tangent.T)
    assert np.linalg.eigvalsh(tangent)[0] > 0.0


def test_frame_force_and_tangent_are_energy_derivatives() -> None:
    check = finite_difference_lee_frame_checks(LeeFrameArcLengthProblem())

    assert check["contract_pass"] is True
    assert check["equation_count"] == 59
    assert check["energy_gradient_relative_error"] <= 1.0e-7
    assert check["tangent_hessian_relative_error"] <= 2.0e-7
    assert check["tangent_symmetry_relative_error"] <= 1.0e-12


def test_lee_frame_follows_published_limit_snapthrough_and_snapback_path(
    lee_frame_receipt: dict[str, Any],
) -> None:
    result = lee_frame_receipt

    assert result["schema_version"] == LEE_FRAME_SCHEMA_VERSION
    assert result["reference"]["doi"] == LEE_FRAME_REFERENCE_DOI
    assert result["reference"]["published_path_point_count"] == len(
        LEE_FRAME_PUBLISHED_PATH
    )
    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert len(result["published_path_comparisons"]) == 23

    path_shape = result["path_shape"]
    assert path_shape["first_limit_load_factor_absolute_error"] <= 0.25
    assert path_shape["descending_load_branch_observed"] is True
    assert path_shape["negative_load_factor_observed"] is True
    assert path_shape["rehardening_load_branch_observed"] is True
    assert path_shape["snapback_observed"] is True
    assert path_shape["contract_pass"] is True

    errors = result["published_path_error_summary"]
    assert errors["maximum_displacement_path_distance_m"] <= 0.004
    assert errors["maximum_load_factor_absolute_error"] <= 0.35
    assert errors["root_mean_square_load_factor_error"] <= 0.20
    assert errors["contract_pass"] is True


def test_lee_frame_solver_receipt_is_restart_exact_and_fallback_free(
    lee_frame_receipt: dict[str, Any],
) -> None:
    result = lee_frame_receipt
    solver = result["solver"]

    assert solver["analysis_type"] == "dense_vector_spherical_arc_length"
    assert solver["terminal_reason"] == "target_monitor_displacement_reached"
    assert solver["accepted_step_count"] > 0
    assert solver["rejected_step_count"] >= 0
    assert solver["maximum_checkpoint_residual_inf_norm_kn"] <= 1.0e-7
    assert solver["maximum_accepted_constraint_residual_m2"] <= 1.0e-10
    assert solver["fallback_count"] == 0
    assert solver["regularization_count"] == 0
    assert solver["checkpoint_restart_exact"] is True
    assert (
        solver["final_checkpoint_state_hash"]
        == solver["restarted_final_checkpoint_state_hash"]
    )
    assert solver["contract_pass"] is True
    assert result["consistent_tangent_checks"]["contract_pass"] is True


def test_lee_frame_receipt_keeps_claims_bounded_and_serializable(
    lee_frame_receipt: dict[str, Any],
) -> None:
    result = lee_frame_receipt
    claims = result["claims"]

    assert claims["bounded_elastic_lee_frame_snapthrough_snapback"] is True
    assert claims["published_reference_path_validation"] is True
    assert claims["energy_consistent_corotational_frame_element"] is True
    assert claims["dense_multi_dof_arc_length_connection"] is True
    assert claims["legacy_corotational_proxy_validated"] is False
    assert claims["general_2d_3d_production_frame_or_shell"] is False
    assert claims["material_geometric_coupling"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)


@pytest.mark.parametrize("elements_per_member", [True, 4, 6])
def test_lee_frame_rejects_unsupported_meshes(elements_per_member: int) -> None:
    with pytest.raises(ValueError, match="elements_per_member"):
        LeeFrameArcLengthProblem(elements_per_member=elements_per_member)


def test_corotational_element_rejects_degenerate_chords() -> None:
    with pytest.raises(ValueError, match="must not coincide"):
        corotational_frame_element_response(
            node_coordinates_m=np.zeros((2, 2), dtype=np.float64),
            element_displacements=np.zeros(6, dtype=np.float64),
            youngs_modulus_kn_per_m2=72_000_000.0,
            area_m2=6.0e-4,
            second_moment_m4=2.0e-8,
        )

    with pytest.raises(ValueError, match="current chord is degenerate"):
        corotational_frame_element_response(
            node_coordinates_m=np.asarray([[0.0, 0.0], [1.0, 0.0]]),
            element_displacements=np.asarray([0.0, 0.0, 0.0, -1.0, 0.0, 0.0]),
            youngs_modulus_kn_per_m2=72_000_000.0,
            area_m2=6.0e-4,
            second_moment_m4=2.0e-8,
        )
