from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.solvers import (
    EquationScaling6DOFError,
    build_equation_scaling_6dof,
    characteristic_length_from_coordinates,
)
from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    ScalarNonlinearAxialReference,
    newton_raphson_scalar,
    newton_raphson_vector,
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


def test_equation_scaling_6dof_separates_force_moment_and_increment_units() -> None:
    scaling = build_equation_scaling_6dof(
        reference_force=100.0,
        characteristic_length=4.0,
        residual=np.array([10.0, -5.0, 2.0, 40.0, -20.0, 8.0]),
        increment=np.array([0.04, -0.02, 0.01, 0.01, -0.005, 0.002]),
        tangent=np.diag([25.0, 25.0, 25.0, 400.0, 400.0, 400.0]),
        dof_labels=("UX", "UY", "UZ", "RX", "RY", "RZ"),
    )

    assert set(scaling.to_dict()) == REQUIRED_FIELDS
    assert scaling.translation_residual_norm == 10.0
    assert scaling.rotation_residual_norm == 40.0
    assert scaling.scaled_residual_norm == pytest.approx(0.1)
    assert scaling.translation_increment_norm == 0.04
    assert scaling.rotation_increment_norm == 0.01
    assert scaling.scaled_increment_norm == pytest.approx(0.01)
    assert scaling.scaled_tangent_condition == pytest.approx(1.0)
    assert scaling.scaling_hash.startswith("sha256:")


def test_scaling_hash_changes_with_physical_policy_not_response_values() -> None:
    common = {
        "reference_force": 100.0,
        "characteristic_length": 4.0,
        "tangent": np.eye(2),
        "dof_labels": ("UX", "RZ"),
    }
    first = build_equation_scaling_6dof(
        residual=(1.0, 2.0),
        increment=(0.1, 0.2),
        **common,
    )
    second = build_equation_scaling_6dof(
        residual=(9.0, 8.0),
        increment=(0.3, 0.4),
        **common,
    )
    changed = build_equation_scaling_6dof(
        residual=(1.0, 2.0),
        increment=(0.1, 0.2),
        **{**common, "characteristic_length": 5.0},
    )

    assert first.scaling_hash == second.scaling_hash
    assert first.scaling_hash != changed.scaling_hash


def test_scaled_tangent_condition_is_invariant_to_consistent_unit_change() -> None:
    base = build_equation_scaling_6dof(
        reference_force=100.0,
        characteristic_length=2.0,
        residual=(1.0, 2.0),
        increment=(0.1, 0.01),
        tangent=np.diag([50.0, 200.0]),
        dof_labels=("UX", "RZ"),
    )
    scaled_units = build_equation_scaling_6dof(
        reference_force=100_000.0,
        characteristic_length=2000.0,
        residual=(1000.0, 2_000_000.0),
        increment=(100.0, 0.01),
        tangent=np.diag([50.0, 200_000_000.0]),
        dof_labels=("UX", "RZ"),
    )

    assert base.scaled_residual_norm == pytest.approx(
        scaled_units.scaled_residual_norm
    )
    assert base.scaled_increment_norm == pytest.approx(
        scaled_units.scaled_increment_norm
    )
    assert base.scaled_tangent_condition == pytest.approx(
        scaled_units.scaled_tangent_condition
    )


def test_sparse_tangent_condition_does_not_materialize_dense_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tangent = csr_matrix(np.diag([25.0, 400.0]))

    def _forbid_dense(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("sparse tangent must not be densified")

    monkeypatch.setattr(csr_matrix, "toarray", _forbid_dense)
    scaling = build_equation_scaling_6dof(
        reference_force=100.0,
        characteristic_length=4.0,
        residual=(1.0, 4.0),
        increment=(0.04, 0.01),
        tangent=tangent,
        dof_labels=("UX", "RZ"),
    )

    assert scaling.scaled_tangent_condition == pytest.approx(1.0)


def test_invalid_or_singular_scaling_inputs_fail_closed() -> None:
    with pytest.raises(EquationScaling6DOFError, match="reference_force"):
        build_equation_scaling_6dof(
            reference_force=0.0,
            characteristic_length=1.0,
            residual=(0.0,),
            increment=(0.0,),
            tangent=np.eye(1),
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


def test_characteristic_length_uses_model_bounding_diagonal() -> None:
    length = characteristic_length_from_coordinates(
        ((0.0, 0.0, 0.0), (3.0, 4.0, 12.0))
    )

    assert length == pytest.approx(13.0)


class _MixedSixDofLinearProblem:
    case_id = "mixed_six_dof_linear_scaling"

    def reference_force_scale(self) -> float:
        return 100.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(6, dtype=float)

    def equation_dof_labels(self) -> tuple[str, ...]:
        return ("UX", "UY", "UZ", "RX", "RY", "RZ")

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        tangent = np.diag([25.0, 25.0, 25.0, 400.0, 400.0, 400.0])
        external = np.array([10.0, -5.0, 2.0, 40.0, -20.0, 8.0])
        return tangent @ free_displacements_m - external, tangent


def test_newton_vector_uses_shared_scaling_for_gates_and_line_search() -> None:
    solution = newton_raphson_vector(
        _MixedSixDofLinearProblem(),
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-12,
            increment_tolerance=1.0e-12,
            characteristic_length_m=4.0,
        ),
    )

    assert solution.status == "ready"
    scaling = solution.metrics["equation_scaling_6dof"]
    assert set(scaling) == REQUIRED_FIELDS
    assert scaling["reference_force"] == 100.0
    assert scaling["characteristic_length"] == 4.0
    assert solution.metrics["residual_gate_passed"] is True
    assert solution.metrics["increment_gate_passed"] is True
    first_attempt = solution.line_search_history[0]["attempts"][0]
    assert set(first_attempt["equation_scaling_6dof"]) == REQUIRED_FIELDS
    assert first_attempt["accepted"] is True


def test_newton_scalar_exposes_same_scaling_contract() -> None:
    solution = newton_raphson_scalar(
        ScalarNonlinearAxialReference(),
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            characteristic_length_m=2.0,
        ),
    )

    assert solution.status == "ready"
    assert set(solution.metrics["equation_scaling_6dof"]) == REQUIRED_FIELDS
    assert all(
        set(row["equation_scaling_6dof"]) == REQUIRED_FIELDS
        for row in solution.convergence_history
    )
