from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.solvers import (
    ReleaseLocalSolveError,
    condense_release_local_6dof,
)


DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ") * 2
SCALING_FIELDS = {
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


def _coupled_tangent() -> np.ndarray:
    tangent = np.diag(np.linspace(20.0, 42.0, 12))
    tangent[5, 11] = tangent[11, 5] = 3.0
    tangent[4, 11] = tangent[11, 4] = -2.0
    return tangent


def test_release_local_solve_matches_schur_condensation_and_common_receipt() -> None:
    tangent = _coupled_tangent()
    result = condense_release_local_6dof(
        local_tangent=tangent,
        released_dofs=(11,),
        dof_labels=DOF_LABELS,
        characteristic_length=4.0,
    )

    retained = np.asarray(result.retained_dofs, dtype=int)
    released = np.asarray(result.released_dofs, dtype=int)
    expected = (
        tangent[np.ix_(retained, retained)]
        - tangent[np.ix_(retained, released)]
        @ np.linalg.solve(
            tangent[np.ix_(released, released)],
            tangent[np.ix_(released, retained)],
        )
    )
    np.testing.assert_allclose(
        result.condensed_tangent[np.ix_(retained, retained)],
        expected,
        rtol=0.0,
        atol=1.0e-14,
    )
    assert np.all(result.condensed_tangent[released, :] == 0.0)
    assert np.all(result.condensed_tangent[:, released] == 0.0)
    assert result.residual_gate_passed is True
    assert result.final_reassembled_residual_passed is True
    assert result.fallback_used is False
    assert result.regularization_used is False
    assert len(result.equation_scaling_6dof) == len(retained)
    assert all(
        set(receipt.to_dict()) == SCALING_FIELDS
        and receipt.scaled_residual_norm <= 1.0e-10
        for receipt in result.equation_scaling_6dof
    )
    assert result.condensed_tangent.flags.writeable is False
    assert result.recovery_operator.flags.writeable is False


def test_release_local_solve_fails_closed_for_singular_released_partition() -> None:
    tangent = np.eye(12)
    tangent[11, 11] = 0.0

    with pytest.raises(ReleaseLocalSolveError, match="singular"):
        condense_release_local_6dof(
            local_tangent=tangent,
            released_dofs=(11,),
            dof_labels=DOF_LABELS,
            characteristic_length=4.0,
        )


@pytest.mark.parametrize("released", [(), (12,), tuple(range(12))])
def test_release_local_solve_rejects_invalid_release_partitions(
    released: tuple[int, ...],
) -> None:
    with pytest.raises(ReleaseLocalSolveError):
        condense_release_local_6dof(
            local_tangent=_coupled_tangent(),
            released_dofs=released,
            dof_labels=DOF_LABELS,
            characteristic_length=4.0,
        )
