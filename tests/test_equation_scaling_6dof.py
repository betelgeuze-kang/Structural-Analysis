from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.solvers import (
    EquationScaling6DOFError,
    build_equation_scaling_6dof,
    characteristic_length_from_coordinates,
    frame3d_dof_labels,
    make_equation_scaling_6dof,
    reference_force_from_mixed_load,
)


REQUIRED_FIELDS = {
    "reference_force",
    "characteristic_length",
    "translation_residual_norm",
    "rotation_residual_norm",
    "scaled_residual_norm",
    "translation_increment_norm",
    "rotation_increment_norm",
    "scaled_increment_norm",
    "scaled_tangent_condition",
    "scaling_hash",
}


def test_equation_scaling_separates_force_moment_and_increment_units() -> None:
    observation = build_equation_scaling_6dof(
        reference_force=100.0,
        characteristic_length=4.0,
        residual=(10.0, -5.0, 2.0, 40.0, -20.0, 8.0),
        increment=(0.04, -0.02, 0.01, 0.01, -0.005, 0.002),
        tangent=np.diag((25.0, 25.0, 25.0, 400.0, 400.0, 400.0)),
        dof_labels=("UX", "UY", "UZ", "RX", "RY", "RZ"),
    )

    assert set(observation.to_dict()) == REQUIRED_FIELDS
    assert observation.translation_residual_norm == 10.0
    assert observation.rotation_residual_norm == 40.0
    assert observation.scaled_residual_norm == pytest.approx(0.1)
    assert observation.translation_increment_norm == 0.04
    assert observation.rotation_increment_norm == 0.01
    assert observation.scaled_increment_norm == pytest.approx(0.01)
    assert observation.scaled_tangent_condition == pytest.approx(1.0)
    assert observation.scaling_hash.startswith("sha256:")


def test_transform_solves_dimensionless_equation_and_unscales_increment() -> None:
    transform = make_equation_scaling_6dof(
        reference_force=100.0,
        characteristic_length=4.0,
        dof_labels=("UX", "RZ"),
    )
    tangent = csr_matrix(np.diag((25.0, 400.0)))
    residual = np.asarray((-10.0, -40.0))

    scaled_tangent = transform.scale_tangent(tangent)
    scaled_residual = transform.scale_residual(residual)
    scaled_increment = np.linalg.solve(
        scaled_tangent.toarray(),
        -scaled_residual,
    )
    physical_increment = transform.unscale_increment(scaled_increment)

    np.testing.assert_allclose(physical_increment, (0.4, 0.1))
    np.testing.assert_allclose(
        tangent @ physical_increment,
        -residual,
    )


def test_scaled_condition_is_invariant_to_consistent_unit_change() -> None:
    base = build_equation_scaling_6dof(
        reference_force=100.0,
        characteristic_length=2.0,
        residual=(1.0, 2.0),
        increment=(0.1, 0.01),
        tangent=np.diag((50.0, 200.0)),
        dof_labels=("UX", "RZ"),
    )
    converted = build_equation_scaling_6dof(
        reference_force=100_000.0,
        characteristic_length=2000.0,
        residual=(1000.0, 2_000_000.0),
        increment=(100.0, 0.01),
        tangent=np.diag((50.0, 200_000_000.0)),
        dof_labels=("UX", "RZ"),
    )

    assert converted.scaled_residual_norm == pytest.approx(
        base.scaled_residual_norm
    )
    assert converted.scaled_increment_norm == pytest.approx(
        base.scaled_increment_norm
    )
    assert converted.scaled_tangent_condition == pytest.approx(
        base.scaled_tangent_condition
    )


def test_model_scale_helpers_keep_moments_out_of_force_norm() -> None:
    labels = frame3d_dof_labels((0, 4, 6, 11))
    length = characteristic_length_from_coordinates(
        ((0.0, 0.0, 0.0), (3.0, 4.0, 12.0))
    )
    force = reference_force_from_mixed_load(
        (5.0, 130.0, -10.0, 260.0),
        characteristic_length=length,
        dof_labels=labels,
    )

    assert labels == ("UX", "RY", "UX", "RZ")
    assert length == pytest.approx(13.0)
    assert force == pytest.approx(20.0)


def test_invalid_scaling_fails_closed() -> None:
    with pytest.raises(EquationScaling6DOFError, match="reference_force"):
        make_equation_scaling_6dof(
            reference_force=0.0,
            characteristic_length=1.0,
            dof_labels=("UX",),
        )
    with pytest.raises(EquationScaling6DOFError, match="condition"):
        build_equation_scaling_6dof(
            reference_force=1.0,
            characteristic_length=1.0,
            residual=(0.0,),
            increment=(0.0,),
            tangent=np.zeros((1, 1)),
            dof_labels=("UX",),
        )
