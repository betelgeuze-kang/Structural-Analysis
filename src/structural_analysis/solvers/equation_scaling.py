"""Shared physical equation scaling for mixed 6-DOF structural systems."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from math import isfinite
from typing import Any, Sequence

import numpy as np
from scipy.sparse import diags, issparse
from scipy.sparse.linalg import ArpackNoConvergence, svds


TRANSLATION_DOF_LABELS = frozenset({"UX", "UY", "UZ"})
ROTATION_DOF_LABELS = frozenset({"RX", "RY", "RZ"})
EQUATION_SCALING_6DOF_VERSION = "equation-scaling-6dof.v1"


class EquationScaling6DOFError(ValueError):
    """Raised when a mixed physical equation cannot be scaled safely."""


@dataclass(frozen=True)
class EquationScaling6DOF:
    """Common result contract for residual, increment, and tangent scaling."""

    reference_force: float
    characteristic_length: float
    translation_residual_norm: float
    rotation_residual_norm: float
    scaled_residual_norm: float
    translation_increment_norm: float
    rotation_increment_norm: float
    scaled_increment_norm: float
    scaled_tangent_condition: float
    scaling_hash: str

    def to_dict(self) -> dict[str, float | str]:
        return dict(asdict(self))


def build_equation_scaling_6dof(
    *,
    reference_force: float,
    characteristic_length: float,
    residual: Sequence[float] | np.ndarray,
    increment: Sequence[float] | np.ndarray,
    tangent: Any,
    dof_labels: Sequence[str],
) -> EquationScaling6DOF:
    """Scale one mixed force/moment equilibrium system deterministically."""

    reference_force = _positive_finite(reference_force, "reference_force")
    characteristic_length = _positive_finite(
        characteristic_length,
        "characteristic_length",
    )
    residual_array = _finite_vector(residual, "residual")
    increment_array = _finite_vector(increment, "increment")
    labels = tuple(str(label).upper() for label in dof_labels)
    if residual_array.shape != increment_array.shape:
        raise EquationScaling6DOFError(
            "residual and increment must have identical vector shapes"
        )
    if len(labels) != residual_array.size:
        raise EquationScaling6DOFError(
            "dof_labels length must match residual vector size"
        )
    invalid_labels = sorted(
        set(labels) - TRANSLATION_DOF_LABELS - ROTATION_DOF_LABELS
    )
    if invalid_labels:
        raise EquationScaling6DOFError(
            f"unsupported 6DOF labels: {','.join(invalid_labels)}"
        )

    translation_mask = np.asarray(
        [label in TRANSLATION_DOF_LABELS for label in labels],
        dtype=bool,
    )
    rotation_mask = ~translation_mask
    residual_scale = np.where(
        translation_mask,
        1.0 / reference_force,
        1.0 / (reference_force * characteristic_length),
    )
    displacement_scale = np.where(
        translation_mask,
        characteristic_length,
        1.0,
    )
    scaled_residual = residual_scale * residual_array
    scaled_increment = increment_array / displacement_scale
    scaled_tangent_condition = _scaled_tangent_condition(
        tangent,
        residual_scale=residual_scale,
        displacement_scale=displacement_scale,
        expected_order=residual_array.size,
    )

    return EquationScaling6DOF(
        reference_force=reference_force,
        characteristic_length=characteristic_length,
        translation_residual_norm=_masked_inf_norm(
            residual_array,
            translation_mask,
        ),
        rotation_residual_norm=_masked_inf_norm(
            residual_array,
            rotation_mask,
        ),
        scaled_residual_norm=_inf_norm(scaled_residual),
        translation_increment_norm=_masked_inf_norm(
            increment_array,
            translation_mask,
        ),
        rotation_increment_norm=_masked_inf_norm(
            increment_array,
            rotation_mask,
        ),
        scaled_increment_norm=_inf_norm(scaled_increment),
        scaled_tangent_condition=scaled_tangent_condition,
        scaling_hash=_scaling_hash(
            reference_force=reference_force,
            characteristic_length=characteristic_length,
            dof_labels=labels,
        ),
    )


def characteristic_length_from_coordinates(
    coordinates: Sequence[Sequence[float]] | np.ndarray,
) -> float:
    """Return a deterministic positive model length from node coordinates."""

    array = np.asarray(coordinates, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3 or array.shape[0] < 1:
        raise EquationScaling6DOFError(
            "coordinates must have shape (node_count, 3)"
        )
    if not np.all(np.isfinite(array)):
        raise EquationScaling6DOFError("coordinates must be finite")
    extents = np.max(array, axis=0) - np.min(array, axis=0)
    diagonal = float(np.linalg.norm(extents))
    if diagonal <= np.finfo(float).tiny:
        raise EquationScaling6DOFError(
            "characteristic length requires non-coincident coordinates"
        )
    return diagonal


def _positive_finite(value: float, label: str) -> float:
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise EquationScaling6DOFError(f"{label} must be finite and positive")
    return number


def _finite_vector(value: Any, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise EquationScaling6DOFError(f"{label} must be a finite vector")
    return array


def _scaled_tangent_condition(
    value: Any,
    *,
    residual_scale: np.ndarray,
    displacement_scale: np.ndarray,
    expected_order: int,
) -> float:
    if issparse(value):
        matrix = value.astype(float, copy=False)
        if matrix.shape != (expected_order, expected_order):
            raise EquationScaling6DOFError(
                "tangent must be square and match the residual vector order"
            )
        if not np.all(np.isfinite(matrix.data)):
            raise EquationScaling6DOFError("tangent must be finite")
        if expected_order == 0:
            return 1.0
        scaled = (
            diags(residual_scale, format="csr")
            @ matrix
            @ diags(displacement_scale, format="csr")
        )
        return _sparse_condition_number(scaled)

    array = np.asarray(value, dtype=float)
    if array.shape != (expected_order, expected_order):
        raise EquationScaling6DOFError(
            "tangent must be square and match the residual vector order"
        )
    if not np.all(np.isfinite(array)):
        raise EquationScaling6DOFError("tangent must be finite")
    if not array.size:
        return 1.0
    scaled = (
        residual_scale[:, np.newaxis]
        * array
        * displacement_scale[np.newaxis, :]
    )
    condition = float(np.linalg.cond(scaled))
    if not isfinite(condition):
        raise EquationScaling6DOFError(
            "scaled tangent condition must be finite"
        )
    return condition


def _sparse_condition_number(matrix: Any) -> float:
    """Estimate the 2-norm condition without materializing a dense matrix."""

    order = int(matrix.shape[0])
    if order == 1:
        magnitude = abs(float(matrix[0, 0]))
        if not isfinite(magnitude) or magnitude <= np.finfo(float).tiny:
            raise EquationScaling6DOFError(
                "scaled tangent condition must be finite"
            )
        return 1.0

    initial = np.full(order, 1.0 / np.sqrt(order), dtype=float)
    try:
        largest = float(
            svds(
                matrix,
                k=1,
                which="LM",
                v0=initial,
                return_singular_vectors=False,
            )[0]
        )
        smallest = float(
            svds(
                matrix,
                k=1,
                which="SM",
                v0=initial,
                return_singular_vectors=False,
            )[0]
        )
    except (ArpackNoConvergence, ValueError, RuntimeError) as exc:
        raise EquationScaling6DOFError(
            "scaled tangent condition could not be evaluated sparsely"
        ) from exc
    if (
        not isfinite(largest)
        or not isfinite(smallest)
        or smallest <= np.finfo(float).tiny
    ):
        raise EquationScaling6DOFError(
            "scaled tangent condition must be finite"
        )
    condition = largest / smallest
    if not isfinite(condition):
        raise EquationScaling6DOFError(
            "scaled tangent condition must be finite"
        )
    return condition


def _masked_inf_norm(values: np.ndarray, mask: np.ndarray) -> float:
    return _inf_norm(values[mask])


def _inf_norm(values: np.ndarray) -> float:
    return float(np.linalg.norm(values, ord=np.inf)) if values.size else 0.0


def _scaling_hash(
    *,
    reference_force: float,
    characteristic_length: float,
    dof_labels: tuple[str, ...],
) -> str:
    payload = {
        "schema_version": EQUATION_SCALING_6DOF_VERSION,
        "reference_force": reference_force,
        "characteristic_length": characteristic_length,
        "dof_labels": list(dof_labels),
        "translation_residual_scale": "1/reference_force",
        "rotation_residual_scale": (
            "1/(reference_force*characteristic_length)"
        ),
        "translation_increment_scale": "1/characteristic_length",
        "rotation_increment_scale": "1",
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
