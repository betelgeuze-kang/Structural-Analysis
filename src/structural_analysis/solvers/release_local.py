"""Fail-closed local static condensation for mixed 6-DOF end releases."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
)
from structural_analysis.solvers.equation_scaling_6dof import (
    EquationScaling6DOF,
    create_equation_scaling_6dof,
    scaled_residual_metrics_6dof,
)


_DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")


class ReleaseLocalSolveError(ValueError):
    """Raised when a release condensation cannot be proven valid."""


@dataclass(frozen=True)
class ReleaseLocalSolveResult:
    condensed_tangent: np.ndarray
    recovery_operator: np.ndarray
    retained_dofs: tuple[int, ...]
    released_dofs: tuple[int, ...]
    equation_scaling_6dof: tuple[EquationScaling6DOF, ...]
    residual_gate_passed: bool
    final_reassembled_residual_passed: bool
    fallback_used: bool
    regularization_used: bool


def condense_release_local_6dof(
    *,
    local_tangent: np.ndarray,
    released_dofs: Sequence[int],
    dof_labels: Sequence[str],
    characteristic_length: float,
    residual_tolerance: float = 1.0e-10,
) -> ReleaseLocalSolveResult:
    """Condense released local DOFs and retain auditable solve receipts.

    This is an element-local building block. It does not enable element
    releases in a public solver capability profile.
    """

    tangent = np.asarray(local_tangent, dtype=float)
    if (
        tangent.ndim != 2
        or tangent.shape[0] != tangent.shape[1]
        or tangent.shape[0] == 0
        or not np.all(np.isfinite(tangent))
    ):
        raise ReleaseLocalSolveError("local_tangent must be a finite square matrix")
    order = int(tangent.shape[0])
    labels = tuple(str(label).upper() for label in dof_labels)
    if len(labels) != order:
        raise ReleaseLocalSolveError("dof_labels must match local_tangent order")
    if order % 6 != 0 or any(
        label != _DOF_LABELS[index % 6]
        for index, label in enumerate(labels)
    ):
        raise ReleaseLocalSolveError(
            "dof_labels must contain complete ordered 6DOF node blocks"
        )
    if not isfinite(characteristic_length) or characteristic_length <= 0.0:
        raise ReleaseLocalSolveError(
            "characteristic_length must be finite and positive"
        )
    if not isfinite(residual_tolerance) or residual_tolerance <= 0.0:
        raise ReleaseLocalSolveError(
            "residual_tolerance must be finite and positive"
        )
    if not np.allclose(tangent, tangent.T, rtol=0.0, atol=1.0e-12):
        raise ReleaseLocalSolveError("local_tangent must be symmetric")

    released = tuple(sorted({int(index) for index in released_dofs}))
    if not released:
        raise ReleaseLocalSolveError("at least one released DOF is required")
    if released[0] < 0 or released[-1] >= order:
        raise ReleaseLocalSolveError("released DOF index is out of range")
    retained = tuple(index for index in range(order) if index not in released)
    if not retained:
        raise ReleaseLocalSolveError("at least one retained DOF is required")

    released_index = np.asarray(released, dtype=int)
    retained_index = np.asarray(retained, dtype=int)
    k_qq = tangent[np.ix_(released_index, released_index)]
    k_qr = tangent[np.ix_(released_index, retained_index)]
    try:
        recovery = np.linalg.solve(k_qq, -k_qr)
    except np.linalg.LinAlgError as exc:
        raise ReleaseLocalSolveError(
            "released local tangent is singular"
        ) from exc
    if not np.all(np.isfinite(recovery)):
        raise ReleaseLocalSolveError("release recovery operator is non-finite")

    receipts: list[EquationScaling6DOF] = []
    scaled_residuals: list[float] = []
    for column in range(len(retained)):
        increment = recovery[:, column]
        applied = -k_qr[:, column]
        residual = k_qq @ increment - applied
        scaling = _release_equation_scaling(
            tangent=tangent,
            applied=applied,
            order=order,
            released=released,
            retained_column=column,
            characteristic_length=characteristic_length,
        )
        receipts.append(scaling)
        scaled_residuals.append(
            scaled_residual_metrics_6dof(
                residual,
                released,
                scaling,
            )["scaled"]
        )

    k_rr = tangent[np.ix_(retained_index, retained_index)]
    k_rq = tangent[np.ix_(retained_index, released_index)]
    condensed_retained = k_rr + k_rq @ recovery
    condensed_retained = 0.5 * (condensed_retained + condensed_retained.T)
    condensed = np.zeros_like(tangent)
    condensed[np.ix_(retained_index, retained_index)] = condensed_retained
    reassembled_residual = k_qq @ recovery + k_qr
    reference = max(
        1.0,
        float(np.linalg.norm(k_qr, ord=np.inf)) if k_qr.size else 0.0,
    )
    reassembled_scaled_residual = (
        float(np.linalg.norm(reassembled_residual, ord=np.inf)) / reference
        if reassembled_residual.size
        else 0.0
    )
    residual_gate_passed = bool(
        receipts
        and all(value <= residual_tolerance for value in scaled_residuals)
    )
    final_reassembled_passed = bool(
        reassembled_scaled_residual <= residual_tolerance
    )
    if not residual_gate_passed or not final_reassembled_passed:
        raise ReleaseLocalSolveError(
            "release local solve residual gate failed"
        )
    condensed.setflags(write=False)
    recovery.setflags(write=False)
    return ReleaseLocalSolveResult(
        condensed_tangent=condensed,
        recovery_operator=recovery,
        retained_dofs=retained,
        released_dofs=released,
        equation_scaling_6dof=tuple(receipts),
        residual_gate_passed=True,
        final_reassembled_residual_passed=True,
        fallback_used=False,
        regularization_used=False,
    )


def _release_equation_scaling(
    *,
    tangent: np.ndarray,
    applied: np.ndarray,
    order: int,
    released: tuple[int, ...],
    retained_column: int,
    characteristic_length: float,
) -> EquationScaling6DOF:
    reference_load = np.zeros(order, dtype=np.float64)
    reference_load[np.asarray(released, dtype=int)] = applied
    node_coordinates = np.zeros((order // 6, 3), dtype=np.float64)
    source_identity_hash = canonical_hash(
        {
            "profile": "release-local-solve-6dof.v1",
            "tangent_hash": array_data_hash(np.asarray(tangent, dtype="<f8")),
            "released_dofs": list(released),
            "retained_column": retained_column,
        }
    )
    return create_equation_scaling_6dof(
        source_identity_hash=source_identity_hash,
        node_coordinates_m=node_coordinates,
        reference_equation_load=reference_load,
        free_dofs=released,
        minimum_characteristic_length_m=characteristic_length,
    )


def _reference_force(
    applied: np.ndarray,
    labels: tuple[str, ...],
    *,
    characteristic_length: float,
) -> float:
    equivalent_force = [
        abs(float(value)) / characteristic_length
        if label in {"RX", "RY", "RZ"}
        else abs(float(value))
        for value, label in zip(applied, labels, strict=True)
    ]
    return max(1.0, max(equivalent_force, default=0.0))


__all__ = [
    "ReleaseLocalSolveError",
    "ReleaseLocalSolveResult",
    "condense_release_local_6dof",
]
