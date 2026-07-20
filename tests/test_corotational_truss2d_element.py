from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.benchmark.material_geometric_truss import (
    corotational_truss_element_response as legacy_fixed_base_response,
)
from structural_analysis.elements.corotational_truss2d import (
    corotational_truss2d_fixed_base_response,
    corotational_truss2d_response,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


def _assert_fixed_base_parity(*, committed_state, displacement) -> None:
    material = BilinearCombinedHardeningSteel()
    base = (-1.0, 0.0)
    apex = (0.0, 0.2)
    area = 0.001

    legacy = legacy_fixed_base_response(
        element_id="left",
        base_coordinate_m=base,
        initial_apex_coordinate_m=apex,
        apex_displacement_m=displacement,
        area_m2=area,
        material=material,
        committed_state=committed_state,
    )
    extracted = corotational_truss2d_fixed_base_response(
        element_id="left",
        base_coordinate_m=base,
        initial_free_coordinate_m=apex,
        free_displacement_m=displacement,
        area_m2=area,
        material=material,
        committed_state=committed_state,
    )

    assert extracted.initial_length_m == pytest.approx(legacy.initial_length_m)
    assert extracted.current_length_m == pytest.approx(legacy.current_length_m)
    assert extracted.engineering_strain == pytest.approx(legacy.engineering_strain)
    assert extracted.axial_force_kn == pytest.approx(legacy.axial_force_kn)
    np.testing.assert_allclose(
        extracted.current_direction,
        legacy.current_direction,
        rtol=0.0,
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        extracted.node_j_internal_force_kn,
        legacy.internal_force_kn,
        rtol=0.0,
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        extracted.node_j_material_tangent_kn_per_m,
        legacy.material_tangent_kn_per_m,
        rtol=0.0,
        atol=1.0e-10,
    )
    np.testing.assert_allclose(
        extracted.node_j_geometric_tangent_kn_per_m,
        legacy.geometric_tangent_kn_per_m,
        rtol=0.0,
        atol=1.0e-10,
    )
    np.testing.assert_allclose(
        extracted.node_j_consistent_tangent_kn_per_m,
        legacy.consistent_tangent_kn_per_m,
        rtol=0.0,
        atol=1.0e-10,
    )
    assert extracted.material_response.to_dict() == legacy.material_response.to_dict()


def test_fixed_base_wrapper_matches_existing_elastic_benchmark_kernel() -> None:
    material = BilinearCombinedHardeningSteel()
    _assert_fixed_base_parity(
        committed_state=material.initial_state(),
        displacement=(0.002, -0.001),
    )


def test_fixed_base_wrapper_matches_existing_plastic_benchmark_kernel() -> None:
    material = BilinearCombinedHardeningSteel()
    committed = material.integrate(0.004, material.initial_state()).state
    _assert_fixed_base_parity(
        committed_state=committed,
        displacement=(-0.035, -0.055),
    )


def test_full_four_equation_tangent_matches_same_parent_finite_difference() -> None:
    material = BilinearCombinedHardeningSteel()
    committed = material.integrate(0.004, material.initial_state()).state
    coordinates_i = np.array([-1.0, 0.0], dtype=np.float64)
    coordinates_j = np.array([0.0, 0.2], dtype=np.float64)
    displacements = np.array(
        [0.01, -0.005, -0.04, -0.06],
        dtype=np.float64,
    )

    def evaluate(values: np.ndarray):
        return corotational_truss2d_response(
            element_id="e1",
            node_i_coordinate_m=coordinates_i,
            node_j_coordinate_m=coordinates_j,
            node_i_displacement_m=values[:2],
            node_j_displacement_m=values[2:],
            area_m2=0.001,
            material=material,
            committed_state=committed,
        )

    response = evaluate(displacements)
    epsilon = 1.0e-7
    finite_difference = np.zeros((4, 4), dtype=np.float64)
    for column in range(4):
        forward = displacements.copy()
        backward = displacements.copy()
        forward[column] += epsilon
        backward[column] -= epsilon
        finite_difference[:, column] = (
            evaluate(forward).internal_force_global_kn
            - evaluate(backward).internal_force_global_kn
        ) / (2.0 * epsilon)

    scale = max(
        1.0,
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(
            np.linalg.norm(
                response.consistent_tangent_global_kn_per_m,
                ord=np.inf,
            )
        ),
    )
    relative_error = float(
        np.linalg.norm(
            finite_difference - response.consistent_tangent_global_kn_per_m,
            ord=np.inf,
        )
        / scale
    )
    reference_committed = material.integrate(
        0.004,
        material.initial_state(),
    ).state
    assert relative_error <= 1.0e-7
    assert committed.state_hash == reference_committed.state_hash


def test_rigid_motion_preserves_length_and_zero_force() -> None:
    material = BilinearCombinedHardeningSteel()
    response = corotational_truss2d_response(
        element_id="rigid-rotation",
        node_i_coordinate_m=(0.0, 0.0),
        node_j_coordinate_m=(1.0, 0.0),
        node_i_displacement_m=(2.0, -3.0),
        node_j_displacement_m=(1.0, -2.0),
        area_m2=0.001,
        material=material,
        committed_state=material.initial_state(),
    )

    assert response.initial_length_m == pytest.approx(1.0)
    assert response.current_length_m == pytest.approx(1.0)
    assert response.engineering_strain == pytest.approx(0.0, abs=1.0e-15)
    assert response.axial_force_kn == pytest.approx(0.0, abs=1.0e-12)
    np.testing.assert_allclose(response.current_direction, [0.0, 1.0], atol=1.0e-15)
    np.testing.assert_allclose(response.internal_force_global_kn, 0.0, atol=1.0e-12)
    np.testing.assert_allclose(
        response.geometric_tangent_global_kn_per_m,
        0.0,
        atol=1.0e-12,
    )


def test_global_tangent_has_expected_symmetry_and_rigid_translation_nullspace() -> None:
    material = BilinearCombinedHardeningSteel()
    response = corotational_truss2d_response(
        element_id="e1",
        node_i_coordinate_m=(-1.0, 0.0),
        node_j_coordinate_m=(0.0, 0.2),
        node_i_displacement_m=(0.01, -0.005),
        node_j_displacement_m=(-0.02, -0.03),
        area_m2=0.001,
        material=material,
        committed_state=material.initial_state(),
    )

    tangent = response.consistent_tangent_global_kn_per_m
    np.testing.assert_allclose(tangent, tangent.T, rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(
        tangent @ np.array([1.0, 0.0, 1.0, 0.0]),
        0.0,
        atol=1.0e-10,
    )
    np.testing.assert_allclose(
        tangent @ np.array([0.0, 1.0, 0.0, 1.0]),
        0.0,
        atol=1.0e-10,
    )
    assert not response.current_direction.flags.writeable
    assert not response.internal_force_global_kn.flags.writeable
    assert not response.consistent_tangent_global_kn_per_m.flags.writeable


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"element_id": ""}, "element_id"),
        ({"area_m2": True}, "area_m2"),
        ({"area_m2": 0.0}, "area_m2"),
        ({"node_i_coordinate_m": (np.nan, 0.0)}, "node_i_coordinate_m"),
        (
            {
                "node_i_coordinate_m": (0.0, 0.0),
                "node_j_coordinate_m": (0.0, 0.0),
            },
            "initial bar length",
        ),
        (
            {
                "node_i_coordinate_m": (0.0, 0.0),
                "node_j_coordinate_m": (1.0, 0.0),
                "node_j_displacement_m": (-1.0, 0.0),
            },
            "current bar length",
        ),
    ],
)
def test_invalid_element_inputs_fail_closed(overrides, message) -> None:
    material = BilinearCombinedHardeningSteel()
    arguments = {
        "element_id": "e1",
        "node_i_coordinate_m": (0.0, 0.0),
        "node_j_coordinate_m": (1.0, 0.2),
        "node_i_displacement_m": (0.0, 0.0),
        "node_j_displacement_m": (0.0, 0.0),
        "area_m2": 0.001,
        "material": material,
        "committed_state": material.initial_state(),
    }
    arguments.update(overrides)
    with pytest.raises(ValueError, match=message):
        corotational_truss2d_response(**arguments)
