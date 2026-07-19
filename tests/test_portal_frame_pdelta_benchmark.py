from __future__ import annotations

import json
from typing import Any

import numpy as np
import pytest

from structural_analysis.benchmark.portal_frame_pdelta import (
    PORTAL_FRAME_PDELTA_CONTEXT_URL,
    PORTAL_FRAME_PDELTA_SCHEMA_VERSION,
    PortalFramePDeltaProblem,
    effective_sway_stiffness_kn_per_m,
    finite_difference_portal_frame_checks,
    portal_frame_pdelta_benchmark,
    portal_frame_sway_critical_load_kn,
)


@pytest.fixture(scope="module")
def portal_receipt() -> dict[str, Any]:
    return portal_frame_pdelta_benchmark()


def test_portal_geometry_supports_and_symmetric_sway_coordinates() -> None:
    problem = PortalFramePDeltaProblem()

    assert np.array_equal(
        problem.node_coordinates_m,
        np.asarray([[0.0, 0.0], [0.0, 3.0], [5.0, 3.0], [5.0, 0.0]]),
    )
    assert len(problem.elements) == 3
    assert problem.free_global_dofs == (3, 4, 5, 6, 7, 8)
    assert problem.free_dof_count == 6
    assert problem.node_coordinates_m.flags.writeable is False

    transformation = problem.symmetric_sway_transformation()
    generalized = np.asarray([0.02, 0.003, -0.004])
    assert transformation @ generalized == pytest.approx(
        [0.02, 0.003, -0.004, 0.02, -0.003, -0.004]
    )
    assert transformation.flags.writeable is False


def test_symmetric_gravity_state_is_an_exact_prestressed_equilibrium() -> None:
    problem = PortalFramePDeltaProblem()
    gravity_load = 10_000.0
    state = problem.gravity_state(gravity_load)
    expected_shortening = (
        gravity_load * problem.story_height_m / (2.0 * problem.column_axial_rigidity_kn)
    )

    assert state == pytest.approx(
        [0.0, -expected_shortening, 0.0, 0.0, -expected_shortening, 0.0]
    )
    assert problem.current_story_height_m(gravity_load) == pytest.approx(
        problem.story_height_m - expected_shortening
    )
    _, internal_force, tangent = problem.assemble(state)
    assert internal_force == pytest.approx(
        problem.gravity_load_vector_kn(gravity_load),
        abs=1.0e-8,
    )
    assert np.array_equal(tangent, tangent.T)


def test_closed_form_sway_hessian_matches_three_member_assembly() -> None:
    problem = PortalFramePDeltaProblem()
    critical_load = portal_frame_sway_critical_load_kn(problem)
    gravity_load = 0.9 * critical_load
    analytic = problem.analytic_symmetric_sway_tangent_kn(gravity_load)
    assembled = problem.assembled_symmetric_sway_tangent_kn(gravity_load)

    assert assembled == pytest.approx(analytic, rel=1.0e-12, abs=1.0e-8)
    assert effective_sway_stiffness_kn_per_m(assembled) == pytest.approx(
        effective_sway_stiffness_kn_per_m(analytic),
        rel=2.0e-12,
    )
    assert np.linalg.eigvalsh(assembled)[0] > 0.0


def test_portal_force_and_tangent_are_energy_derivatives() -> None:
    checks = finite_difference_portal_frame_checks(PortalFramePDeltaProblem())

    assert checks["contract_pass"] is True
    assert checks["equation_count"] == 6
    assert checks["energy_gradient_relative_error"] <= 1.0e-7
    assert checks["tangent_hessian_relative_error"] <= 1.0e-7
    assert checks["tangent_symmetry_relative_error"] <= 1.0e-12


def test_portal_critical_load_and_amplification_follow_closed_form(
    portal_receipt: dict[str, Any],
) -> None:
    result = portal_receipt
    critical = result["critical_sway_load"]
    rows = result["load_rows"]

    assert result["schema_version"] == PORTAL_FRAME_PDELTA_SCHEMA_VERSION
    assert result["reference"]["external_context_url"] == (
        PORTAL_FRAME_PDELTA_CONTEXT_URL
    )
    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert critical["analytic_total_gravity_load_kn"] == pytest.approx(
        31_246.914946938614,
        rel=1.0e-12,
    )
    assert critical["assembled_total_gravity_load_kn"] == pytest.approx(
        critical["analytic_total_gravity_load_kn"],
        rel=1.0e-10,
    )
    assert critical["relative_error"] <= 1.0e-10
    assert [row["critical_load_ratio"] for row in rows] == [
        0.0,
        0.25,
        0.5,
        0.75,
        0.9,
        0.95,
    ]
    assert [row["assembled_lateral_amplification"] for row in rows] == (
        pytest.approx(
            [
                1.0,
                1.3332031887,
                1.9996095662,
                3.9988286985,
                9.9964860956,
                19.9925817574,
            ],
            rel=1.0e-9,
        )
    )
    assert result["path_shape"]["amplification_monotonic"] is True
    assert all(row["minimum_symmetric_tangent_eigenvalue"] > 0.0 for row in rows)


def test_portal_receipt_errors_fallbacks_and_claims_stay_bounded(
    portal_receipt: dict[str, Any],
) -> None:
    result = portal_receipt
    errors = result["error_summary"]
    claims = result["claims"]

    assert errors["maximum_tangent_relative_inf_error"] <= 1.0e-11
    assert errors["maximum_effective_stiffness_relative_error"] <= 1.0e-10
    assert errors["maximum_amplification_relative_error"] <= 1.0e-10
    assert errors["maximum_gravity_equilibrium_residual_inf_kn"] <= 1.0e-7
    assert errors["maximum_full_vs_symmetric_response_abs"] <= 1.0e-10
    assert result["solver"]["regularization_count"] == 0
    assert result["solver"]["fallback_count"] == 0

    assert claims["bounded_three_member_portal_pdelta_tangent"] is True
    assert claims["analytic_sway_stiffness_validation"] is True
    assert claims["gravity_prestress_equilibrium"] is True
    assert claims["assembled_critical_sway_load"] is True
    assert claims["energy_consistent_corotational_frame_connection"] is True
    assert claims["finite_displacement_load_path_continuation"] is False
    assert claims["member_p_small_delta_stability_functions"] is False
    assert claims["legacy_corotational_proxy_validated"] is False
    assert claims["general_2d_3d_production_frame_or_shell"] is False
    assert claims["material_geometric_coupling"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert result["blockers_remaining"]
    json.dumps(result, allow_nan=False, sort_keys=True)


@pytest.mark.parametrize(
    "load_ratios, message",
    [
        ((0.0, 0.25, 0.5), "at least four"),
        ((0.0, 0.5, 0.5, 0.9), "strictly increasing"),
        ((0.0, 0.5, 0.9, 1.0), r"\[0, 1\)"),
    ],
)
def test_portal_benchmark_rejects_invalid_load_ratios(
    load_ratios: tuple[float, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        portal_frame_pdelta_benchmark(load_ratios=load_ratios)


def test_portal_problem_rejects_invalid_prestress_and_condensation() -> None:
    problem = PortalFramePDeltaProblem()
    with pytest.raises(ValueError, match="nonnegative"):
        problem.gravity_state(-1.0)
    with pytest.raises(ValueError, match="axial-strain limit"):
        problem.gravity_state(
            2.0 * problem.column_axial_rigidity_kn * problem.maximum_column_axial_strain
        )
    with pytest.raises(ValueError, match="less than 0.1"):
        PortalFramePDeltaProblem(maximum_column_axial_strain=0.1)
    with pytest.raises(ValueError, match="finite 3x3"):
        effective_sway_stiffness_kn_per_m(np.zeros((2, 2)))
    with pytest.raises(ValueError, match="nonsingular"):
        effective_sway_stiffness_kn_per_m(np.diag([1.0, 0.0, 0.0]))
