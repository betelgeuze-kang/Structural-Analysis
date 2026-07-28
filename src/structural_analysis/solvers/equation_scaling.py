"""Physical equation scaling for mixed translational/rotational 6DOF systems.

The transform is deliberately expressed in physical units:

* translational residuals are normalized by a reference force,
* rotational residuals are normalized by reference force times length,
* translational increments are normalized by the characteristic length, and
* rotational increments are already dimensionless.

For a physical tangent ``K`` and residual ``R`` the solver therefore uses
``K_s = D_R^-1 K D_u`` and ``R_s = D_R^-1 R``.  ``D_u`` maps a dimensionless
increment back to physical translation/rotation coordinates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Sequence

import numpy as np
from scipy.sparse import csr_matrix, diags, issparse
from scipy.sparse.linalg import ArpackNoConvergence, svds

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


EQUATION_SCALING_6DOF_VERSION = "equation-scaling-6dof.v1"
TRANSLATION_DOF_LABELS = frozenset({"UX", "UY", "UZ"})
ROTATION_DOF_LABELS = frozenset({"RX", "RY", "RZ"})
FRAME3D_DOF_ORDER = ("UX", "UY", "UZ", "RX", "RY", "RZ")


class EquationScaling6DOFError(ValueError):
    """Raised when a mixed physical equation cannot be scaled safely."""


@dataclass(frozen=True)
class EquationScaling6DOF:
    """JSON-ready observation of one scaled residual/increment equation."""

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


@dataclass(frozen=True)
class EquationScaling6DOFTransform:
    """Immutable diagonal transform shared by assembly and solver gates."""

    reference_force: float
    characteristic_length: float
    dof_labels: tuple[str, ...]
    residual_scales: tuple[float, ...]
    increment_scales: tuple[float, ...]
    scaling_hash: str

    def scale_residual(self, residual: Any) -> np.ndarray:
        values = _finite_vector(residual, "residual", len(self.dof_labels))
        return np.asarray(self.residual_scales, dtype=np.float64) * values

    def scale_increment(self, increment: Any) -> np.ndarray:
        values = _finite_vector(increment, "increment", len(self.dof_labels))
        return values / np.asarray(self.increment_scales, dtype=np.float64)

    def unscale_increment(self, scaled_increment: Any) -> np.ndarray:
        values = _finite_vector(
            scaled_increment,
            "scaled_increment",
            len(self.dof_labels),
        )
        return np.asarray(self.increment_scales, dtype=np.float64) * values

    def scale_tangent(self, tangent: Any) -> csr_matrix | np.ndarray:
        """Return ``D_R^-1 K D_u`` without densifying sparse input."""

        size = len(self.dof_labels)
        row = np.asarray(self.residual_scales, dtype=np.float64)
        column = np.asarray(self.increment_scales, dtype=np.float64)
        if issparse(tangent):
            matrix = tangent.tocsr(copy=True).astype(np.float64, copy=False)
            _validate_tangent(matrix, expected_order=size)
            scaled = (
                diags(row, format="csr")
                @ matrix
                @ diags(column, format="csr")
            ).tocsr()
            scaled.sum_duplicates()
            scaled.eliminate_zeros()
            scaled.sort_indices()
            return scaled
        matrix = np.asarray(tangent, dtype=np.float64)
        _validate_tangent(matrix, expected_order=size)
        return row[:, np.newaxis] * matrix * column[np.newaxis, :]

    def observe(
        self,
        *,
        residual: Any,
        increment: Any,
        scaled_tangent_condition: float,
    ) -> EquationScaling6DOF:
        residual_values = _finite_vector(
            residual,
            "residual",
            len(self.dof_labels),
        )
        increment_values = _finite_vector(
            increment,
            "increment",
            len(self.dof_labels),
        )
        condition = _positive_finite(
            scaled_tangent_condition,
            "scaled_tangent_condition",
        )
        translation_mask = np.asarray(
            [label in TRANSLATION_DOF_LABELS for label in self.dof_labels],
            dtype=bool,
        )
        rotation_mask = ~translation_mask
        return EquationScaling6DOF(
            reference_force=self.reference_force,
            characteristic_length=self.characteristic_length,
            translation_residual_norm=_masked_inf_norm(
                residual_values,
                translation_mask,
            ),
            rotation_residual_norm=_masked_inf_norm(
                residual_values,
                rotation_mask,
            ),
            scaled_residual_norm=_inf_norm(self.scale_residual(residual_values)),
            translation_increment_norm=_masked_inf_norm(
                increment_values,
                translation_mask,
            ),
            rotation_increment_norm=_masked_inf_norm(
                increment_values,
                rotation_mask,
            ),
            scaled_increment_norm=_inf_norm(
                self.scale_increment(increment_values)
            ),
            scaled_tangent_condition=condition,
            scaling_hash=self.scaling_hash,
        )


def make_equation_scaling_6dof(
    *,
    reference_force: float,
    characteristic_length: float,
    dof_labels: Sequence[str],
) -> EquationScaling6DOFTransform:
    """Create one deterministic diagonal scaling transform."""

    force = _positive_finite(reference_force, "reference_force")
    length = _positive_finite(characteristic_length, "characteristic_length")
    labels = _normalize_labels(dof_labels)
    residual_scales = tuple(
        1.0 / force
        if label in TRANSLATION_DOF_LABELS
        else 1.0 / (force * length)
        for label in labels
    )
    increment_scales = tuple(
        length if label in TRANSLATION_DOF_LABELS else 1.0
        for label in labels
    )
    scaling_hash = canonical_hash(
        {
            "schema_version": EQUATION_SCALING_6DOF_VERSION,
            "reference_force": force,
            "characteristic_length": length,
            "dof_labels": list(labels),
            "translation_residual_scale": "1/reference_force",
            "rotation_residual_scale": (
                "1/(reference_force*characteristic_length)"
            ),
            "translation_increment_scale": "1/characteristic_length",
            "rotation_increment_scale": "1",
        }
    )
    return EquationScaling6DOFTransform(
        reference_force=force,
        characteristic_length=length,
        dof_labels=labels,
        residual_scales=residual_scales,
        increment_scales=increment_scales,
        scaling_hash=scaling_hash,
    )


def build_equation_scaling_6dof(
    *,
    reference_force: float,
    characteristic_length: float,
    residual: Sequence[float] | np.ndarray,
    increment: Sequence[float] | np.ndarray,
    tangent: Any,
    dof_labels: Sequence[str],
) -> EquationScaling6DOF:
    """Build a standalone observation, including scaled condition number."""

    transform = make_equation_scaling_6dof(
        reference_force=reference_force,
        characteristic_length=characteristic_length,
        dof_labels=dof_labels,
    )
    scaled_tangent = transform.scale_tangent(tangent)
    condition = _condition_number(scaled_tangent)
    return transform.observe(
        residual=residual,
        increment=increment,
        scaled_tangent_condition=condition,
    )


def characteristic_length_from_coordinates(
    coordinates: Sequence[Sequence[float]] | np.ndarray,
) -> float:
    """Return the positive bounding-box diagonal for a 3D model."""

    values = np.asarray(coordinates, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or values.shape[0] < 1:
        raise EquationScaling6DOFError(
            "coordinates must have shape (node_count, 3)"
        )
    if not np.all(np.isfinite(values)):
        raise EquationScaling6DOFError("coordinates must be finite")
    diagonal = float(np.linalg.norm(np.max(values, axis=0) - np.min(values, axis=0)))
    if diagonal <= float(np.finfo(np.float64).tiny):
        raise EquationScaling6DOFError(
            "characteristic length requires non-coincident coordinates"
        )
    return diagonal


def reference_force_from_mixed_load(
    load: Sequence[float] | np.ndarray,
    *,
    characteristic_length: float,
    dof_labels: Sequence[str],
    minimum_reference_force: float = 1.0,
) -> float:
    """Reduce force/moment components to one force-scale without unit mixing."""

    length = _positive_finite(characteristic_length, "characteristic_length")
    floor = _positive_finite(
        minimum_reference_force,
        "minimum_reference_force",
    )
    labels = _normalize_labels(dof_labels)
    values = _finite_vector(load, "load", len(labels))
    force_equivalents = np.asarray(
        [
            abs(value)
            if label in TRANSLATION_DOF_LABELS
            else abs(value) / length
            for value, label in zip(values, labels, strict=True)
        ],
        dtype=np.float64,
    )
    return max(_inf_norm(force_equivalents), floor)


def reference_force_from_stiffness(
    tangent: Any,
    *,
    characteristic_length: float,
    dof_labels: Sequence[str],
    minimum_reference_force: float = 1.0,
) -> float:
    """Derive a force scale from one dimensionless-coordinate stiffness action.

    The representative increment is one characteristic length for translation
    coordinates and one radian for rotation coordinates. Absolute row sums
    avoid cancellation, and moment rows are converted back to force by the
    characteristic length. This is intended for load-free eigenproblems where
    no external force vector exists.
    """

    length = _positive_finite(characteristic_length, "characteristic_length")
    floor = _positive_finite(
        minimum_reference_force,
        "minimum_reference_force",
    )
    labels = _normalize_labels(dof_labels)
    _validate_tangent(tangent, expected_order=len(labels))
    increment_scales = np.asarray(
        [
            length if label in TRANSLATION_DOF_LABELS else 1.0
            for label in labels
        ],
        dtype=np.float64,
    )
    if issparse(tangent):
        absolute_tangent = abs(tangent.tocsr(copy=False))
        row_actions = np.asarray(
            absolute_tangent @ increment_scales,
            dtype=np.float64,
        ).reshape(-1)
    else:
        absolute_tangent = np.abs(np.asarray(tangent, dtype=np.float64))
        row_actions = absolute_tangent @ increment_scales
    force_equivalents = np.asarray(
        [
            abs(value)
            if label in TRANSLATION_DOF_LABELS
            else abs(value) / length
            for value, label in zip(row_actions, labels, strict=True)
        ],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(force_equivalents)):
        raise EquationScaling6DOFError(
            "stiffness-derived reference force must be finite"
        )
    return max(_inf_norm(force_equivalents), floor)


def frame3d_dof_labels(dofs: Sequence[int]) -> tuple[str, ...]:
    """Map canonical global 6DOF indices to physical equation labels."""

    labels: list[str] = []
    for index, dof in enumerate(dofs):
        if type(dof) is not int or dof < 0:
            raise EquationScaling6DOFError(
                f"dofs[{index}] must be a non-negative integer"
            )
        labels.append(FRAME3D_DOF_ORDER[dof % 6])
    return tuple(labels)


def _normalize_labels(values: Sequence[str]) -> tuple[str, ...]:
    labels = tuple(str(value).upper() for value in values)
    if not labels:
        raise EquationScaling6DOFError("dof_labels must not be empty")
    invalid = sorted(
        set(labels) - TRANSLATION_DOF_LABELS - ROTATION_DOF_LABELS
    )
    if invalid:
        raise EquationScaling6DOFError(
            f"unsupported 6DOF labels: {','.join(invalid)}"
        )
    return labels


def _positive_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EquationScaling6DOFError(f"{label} must be finite and positive")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise EquationScaling6DOFError(f"{label} must be finite and positive")
    return normalized


def _finite_vector(value: Any, label: str, expected_order: int) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (expected_order,) or not np.all(np.isfinite(array)):
        raise EquationScaling6DOFError(
            f"{label} must be a finite {expected_order}-vector"
        )
    return array


def _validate_tangent(value: Any, *, expected_order: int) -> None:
    if value.shape != (expected_order, expected_order):
        raise EquationScaling6DOFError(
            "tangent must be square and match the equation order"
        )
    numeric = value.data if issparse(value) else value
    if not np.all(np.isfinite(numeric)):
        raise EquationScaling6DOFError("tangent must be finite")


def _condition_number(value: csr_matrix | np.ndarray) -> float:
    if issparse(value):
        matrix = value.tocsr(copy=False)
        order = int(matrix.shape[0])
        if order == 1:
            magnitude = abs(float(matrix[0, 0]))
            condition = 1.0 if magnitude > np.finfo(np.float64).tiny else math.inf
        else:
            initial = np.full(order, 1.0 / math.sqrt(order), dtype=np.float64)
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
            except (ArpackNoConvergence, ValueError, RuntimeError) as error:
                raise EquationScaling6DOFError(
                    "scaled tangent condition could not be evaluated sparsely"
                ) from error
            condition = largest / smallest if smallest > 0.0 else math.inf
    else:
        condition = float(np.linalg.cond(np.asarray(value, dtype=np.float64)))
    if not math.isfinite(condition) or condition <= 0.0:
        raise EquationScaling6DOFError(
            "scaled tangent condition must be finite and positive"
        )
    return condition


def _masked_inf_norm(values: np.ndarray, mask: np.ndarray) -> float:
    return _inf_norm(values[mask])


def _inf_norm(values: np.ndarray) -> float:
    return float(np.linalg.norm(values, ord=np.inf)) if values.size else 0.0


__all__ = [
    "EQUATION_SCALING_6DOF_VERSION",
    "EquationScaling6DOF",
    "EquationScaling6DOFError",
    "EquationScaling6DOFTransform",
    "FRAME3D_DOF_ORDER",
    "ROTATION_DOF_LABELS",
    "TRANSLATION_DOF_LABELS",
    "build_equation_scaling_6dof",
    "characteristic_length_from_coordinates",
    "frame3d_dof_labels",
    "make_equation_scaling_6dof",
    "reference_force_from_mixed_load",
    "reference_force_from_stiffness",
]
