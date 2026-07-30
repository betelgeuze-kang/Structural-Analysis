"""Shared source-bound 6DOF force/moment equation scaling.

Translations are measured in metres and rotational coordinates in radians.
Rotational equilibrium rows are divided by the model characteristic length,
and rotational unknown columns are divided by the same length.  The resulting
linear system therefore compares force/length blocks without mixing raw force
and moment magnitudes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from numbers import Integral
import re
from typing import Any, Iterable

import numpy as np
from scipy.sparse import csr_matrix, diags, issparse

from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_data_hash,
    canonical_hash,
    immutable_array,
)


EQUATION_SCALING_6DOF_SCHEMA_VERSION = (
    "structural-analysis-equation-scaling-6dof.v1"
)
EQUATION_SCALING_6DOF_POLICY = "centroid_diameter_force_moment_6dof.v1"
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class EquationScaling6DOFError(ValueError):
    """Fail-closed invalid 6DOF scaling input."""


@dataclass(frozen=True)
class EquationScaling6DOF:
    schema_version: str
    scaling_hash: str
    policy: str
    source_identity_hash: str
    characteristic_length_m: float
    reference_force: float
    residual_translation_scale: float
    residual_rotation_scale: float
    increment_translation_scale_m: float
    increment_rotation_scale_rad: float
    dof_count: int
    free_equation_count: int
    source_node_coordinates_hash: str
    source_reference_load_hash: str
    source_free_dofs_hash: str
    row_equilibration_hash: str
    column_equilibration_hash: str

    def to_manifest(self) -> dict[str, Any]:
        _validate_equation_scaling(self)
        payload = _manifest(self, include_hash=True)
        if self.scaling_hash != canonical_hash(_manifest(self, include_hash=False)):
            raise EquationScaling6DOFError("equation scaling hash mismatch")
        return payload


def create_equation_scaling_6dof(
    *,
    source_identity_hash: str,
    node_coordinates_m: Any,
    reference_equation_load: Any,
    free_dofs: Iterable[int],
    minimum_characteristic_length_m: float = 1.0e-12,
    minimum_reference_force: float = 1.0,
) -> EquationScaling6DOF:
    """Create deterministic scaling from coordinates, load, and free DOFs."""

    _require_hash(source_identity_hash, "source_identity_hash")
    coordinates = _real_binary64_array(node_coordinates_m, "node coordinates")
    loads = _real_binary64_array(reference_equation_load, "reference load")
    if (
        coordinates.ndim != 2
        or coordinates.shape[0] < 1
        or coordinates.shape[1] != 3
        or not np.all(np.isfinite(coordinates))
    ):
        raise EquationScaling6DOFError("node coordinates must be finite N by 3")
    if (
        loads.ndim != 1
        or loads.size != coordinates.shape[0] * 6
        or not np.all(np.isfinite(loads))
    ):
        raise EquationScaling6DOFError(
            "reference load must be one finite six-DOF vector per node"
        )
    free = _free_dof_array(free_dofs, int(loads.size))
    minimum_length = _positive(
        minimum_characteristic_length_m,
        "minimum_characteristic_length_m",
    )
    minimum_force = _positive(minimum_reference_force, "minimum_reference_force")
    centroid = np.asarray(
        [
            math.fsum(float(value) for value in coordinates[:, component])
            / coordinates.shape[0]
            for component in range(3)
        ],
        dtype=np.float64,
    )
    radii = np.linalg.norm(coordinates - centroid, axis=1)
    characteristic_length = max(
        2.0 * float(np.max(radii)),
        minimum_length,
    )
    translational = [
        abs(float(loads[dof])) for dof in free.tolist() if dof % 6 < 3
    ]
    rotational = [
        abs(float(loads[dof])) / characteristic_length
        for dof in free.tolist()
        if dof % 6 >= 3
    ]
    reference_force = max(*translational, *rotational, minimum_force)
    row_scale, column_scale = equilibration_vectors_6dof(
        free,
        characteristic_length,
    )
    provisional = EquationScaling6DOF(
        schema_version=EQUATION_SCALING_6DOF_SCHEMA_VERSION,
        scaling_hash=_ZERO_HASH,
        policy=EQUATION_SCALING_6DOF_POLICY,
        source_identity_hash=source_identity_hash,
        characteristic_length_m=characteristic_length,
        reference_force=reference_force,
        residual_translation_scale=reference_force,
        residual_rotation_scale=reference_force * characteristic_length,
        increment_translation_scale_m=characteristic_length,
        increment_rotation_scale_rad=1.0,
        dof_count=int(loads.size),
        free_equation_count=int(free.size),
        source_node_coordinates_hash=array_data_hash(
            np.asarray(coordinates, dtype="<f8")
        ),
        source_reference_load_hash=array_data_hash(np.asarray(loads, dtype="<f8")),
        source_free_dofs_hash=array_data_hash(np.asarray(free, dtype="<i8")),
        row_equilibration_hash=array_data_hash(np.asarray(row_scale, dtype="<f8")),
        column_equilibration_hash=array_data_hash(
            np.asarray(column_scale, dtype="<f8")
        ),
    )
    scaling = replace(
        provisional,
        scaling_hash=canonical_hash(_manifest(provisional, include_hash=False)),
    )
    scaling.to_manifest()
    return scaling


def equilibration_vectors_6dof(
    free_dofs: Iterable[int],
    characteristic_length_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return row and unknown-column multipliers in free-equation order."""

    length = _positive(characteristic_length_m, "characteristic_length_m")
    free = _unbounded_free_dof_array(free_dofs)
    row_scale = np.ones(free.size, dtype=np.float64)
    column_scale = np.ones(free.size, dtype=np.float64)
    rotational = np.mod(free, 6) >= 3
    row_scale[rotational] = 1.0 / length
    column_scale[rotational] = 1.0 / length
    return row_scale, column_scale


def scaled_residual_metrics_6dof(
    residual_free: Any,
    free_dofs: Iterable[int],
    scaling: Any,
) -> dict[str, float]:
    free_array = _unbounded_free_dof_array(free_dofs)
    _validate_scaling_source_binding(scaling, free_array)
    free = tuple(int(value) for value in free_array)
    residual = _finite_vector(residual_free, len(free), "free residual")
    translation = residual[[index for index, dof in enumerate(free) if dof % 6 < 3]]
    rotation = residual[[index for index, dof in enumerate(free) if dof % 6 >= 3]]
    translation_norm = _linf(translation)
    rotation_norm = _linf(rotation)
    translation_scale = _scaling_field(
        scaling,
        "residual_translation_scale",
        "residual_translation_scale_kn",
    )
    rotation_scale = _scaling_field(
        scaling,
        "residual_rotation_scale",
        "residual_rotation_scale_kn_m",
    )
    return {
        "translation": translation_norm,
        "rotation": rotation_norm,
        "scaled": max(
            translation_norm / translation_scale,
            rotation_norm / rotation_scale,
        ),
    }


def scaled_increment_metrics_6dof(
    increment_free: Any,
    free_dofs: Iterable[int],
    scaling: Any,
) -> dict[str, float]:
    free_array = _unbounded_free_dof_array(free_dofs)
    _validate_scaling_source_binding(scaling, free_array)
    free = tuple(int(value) for value in free_array)
    increment = _finite_vector(increment_free, len(free), "free increment")
    translation = increment[[index for index, dof in enumerate(free) if dof % 6 < 3]]
    rotation = increment[[index for index, dof in enumerate(free) if dof % 6 >= 3]]
    translation_norm = _linf(translation)
    rotation_norm = _linf(rotation)
    translation_scale = _scaling_field(
        scaling,
        "increment_translation_scale_m",
    )
    rotation_scale = _scaling_field(
        scaling,
        "increment_rotation_scale_rad",
    )
    return {
        "translation": translation_norm,
        "rotation": rotation_norm,
        "scaled": max(
            translation_norm / translation_scale,
            rotation_norm / rotation_scale,
        ),
    }


def scale_linear_system_6dof(
    matrix: Any,
    rhs: Any,
    free_dofs: Iterable[int],
    scaling: EquationScaling6DOF,
) -> tuple[np.ndarray | csr_matrix, np.ndarray, np.ndarray]:
    """Apply ``R K C`` and ``R f``; physical solution is ``C q_scaled``."""

    if type(scaling) is not EquationScaling6DOF:
        raise EquationScaling6DOFError(
            "scaling must be an exact EquationScaling6DOF"
        )
    scaling.to_manifest()
    free_array = _free_dof_array(free_dofs, scaling.dof_count)
    if free_array.size != scaling.free_equation_count:
        raise EquationScaling6DOFError(
            "free DOF count does not match equation scaling"
        )
    if (
        array_data_hash(np.asarray(free_array, dtype="<i8"))
        != scaling.source_free_dofs_hash
    ):
        raise EquationScaling6DOFError(
            "free DOFs do not match equation scaling source binding"
        )
    free = tuple(int(value) for value in free_array)
    rhs_vector = _finite_vector(rhs, len(free), "right-hand side")
    row_scale, column_scale = equilibration_vectors_6dof(
        free,
        scaling.characteristic_length_m,
    )
    if (
        array_data_hash(np.asarray(row_scale, dtype="<f8"))
        != scaling.row_equilibration_hash
        or array_data_hash(np.asarray(column_scale, dtype="<f8"))
        != scaling.column_equilibration_hash
    ):
        raise EquationScaling6DOFError(
            "equilibration vectors do not match equation scaling source binding"
        )
    if issparse(matrix):
        source = matrix.tocsr()
        if source.shape != (len(free), len(free)):
            raise EquationScaling6DOFError("matrix shape does not match free DOFs")
        _real_binary64_array(source.data, "matrix")
        source = source.astype(np.float64, copy=False)
        scaled_sparse = (
            diags(row_scale, format="csr")
            @ source
            @ diags(column_scale, format="csr")
        ).tocsr()
        scaled_sparse.sum_duplicates()
        scaled_sparse.eliminate_zeros()
        scaled_sparse.sort_indices()
        finite_matrix = np.all(np.isfinite(scaled_sparse.data))
        scaled_matrix: np.ndarray | csr_matrix = scaled_sparse
    else:
        source = _real_binary64_array(matrix, "matrix")
        if source.shape != (len(free), len(free)):
            raise EquationScaling6DOFError("matrix shape does not match free DOFs")
        scaled_matrix = row_scale[:, None] * source * column_scale[None, :]
        finite_matrix = np.all(np.isfinite(scaled_matrix))
    scaled_rhs = row_scale * rhs_vector
    if not finite_matrix or not np.all(np.isfinite(scaled_rhs)):
        raise EquationScaling6DOFError("scaled linear system is non-finite")
    return scaled_matrix, scaled_rhs, column_scale


def exact_scaled_condition_number_1(
    scaled_matrix: Any,
    *,
    maximum_equations: int = 256,
) -> float | None:
    """Return exact small-system condition number; larger systems stay unavailable."""

    if type(maximum_equations) is not int or maximum_equations < 1:
        raise EquationScaling6DOFError("maximum_equations must be a positive integer")
    shape = getattr(scaled_matrix, "shape", None)
    if shape is None or len(shape) != 2 or shape[0] != shape[1]:
        raise EquationScaling6DOFError("condition matrix must be square")
    if int(shape[0]) > maximum_equations:
        return None
    if issparse(scaled_matrix):
        source = scaled_matrix.tocsr()
        _real_binary64_array(source.data, "condition matrix")
        dense = source.astype(np.float64, copy=False).toarray()
    else:
        dense = _real_binary64_array(scaled_matrix, "condition matrix")
    value = float(np.linalg.cond(dense, p=1))
    return value if math.isfinite(value) else None


def _free_dof_array(values: Iterable[int], dof_count: int) -> np.ndarray:
    raw = tuple(values)
    if not raw or any(
        isinstance(value, bool) or not isinstance(value, Integral)
        for value in raw
    ):
        raise EquationScaling6DOFError("free_dofs must contain integers")
    normalized = tuple(int(value) for value in raw)
    if len(set(normalized)) != len(normalized) or any(
        value < 0 or value >= dof_count for value in normalized
    ):
        raise EquationScaling6DOFError("free_dofs are duplicate or out of range")
    return np.asarray(normalized, dtype=np.int64)


def _unbounded_free_dof_array(values: Iterable[int]) -> np.ndarray:
    raw = tuple(values)
    if not raw or any(
        isinstance(value, bool) or not isinstance(value, Integral)
        for value in raw
    ):
        raise EquationScaling6DOFError("free_dofs must contain integers")
    normalized = tuple(int(value) for value in raw)
    if len(set(normalized)) != len(normalized) or any(value < 0 for value in normalized):
        raise EquationScaling6DOFError(
            "free_dofs must be unique non-negative integers"
        )
    return np.asarray(normalized, dtype=np.int64)


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EquationScaling6DOFError(f"{name} must be finite and positive")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise EquationScaling6DOFError(f"{name} must be finite and positive")
    return normalized


def _finite_vector(value: Any, size: int, name: str) -> np.ndarray:
    vector = _real_binary64_array(value, name)
    if vector.shape != (size,):
        raise EquationScaling6DOFError(
            f"{name} must be a finite vector of length {size}"
        )
    return vector


def _real_binary64_array(value: Any, name: str) -> np.ndarray:
    """Return an exact real-binary64 copy without coercing source semantics."""

    try:
        _validate_real_numeric_source(value)
        return immutable_array(value, dtype="<f8")
    except (CanonicalContractError, TypeError, ValueError, OverflowError) as error:
        raise EquationScaling6DOFError(
            f"{name} must contain finite, losslessly representable real binary64 values"
        ) from error


def _validate_real_numeric_source(value: Any) -> None:
    """Reject source scalar kinds that NumPy would otherwise silently coerce."""

    if np.ma.isMaskedArray(value):
        raise CanonicalContractError("Masked numeric sources are not contract-safe.")
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject or value.dtype.kind not in "iuf":
            raise CanonicalContractError(
                "Only integer and real floating-point sources are contract-safe."
            )
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_real_numeric_source(item)
        return
    if isinstance(value, bool) or not isinstance(value, (Integral, float, np.floating)):
        raise CanonicalContractError(
            "Only integer and real floating-point sources are contract-safe."
        )
    if isinstance(value, Integral):
        converted = float(value)
        if not math.isfinite(converted) or int(converted) != int(value):
            raise CanonicalContractError(
                "Integer source cannot be represented exactly as binary64."
            )


def _scaling_field(scaling: Any, *names: str) -> float:
    for name in names:
        if hasattr(scaling, name):
            return _positive(getattr(scaling, name), name)
    raise EquationScaling6DOFError(
        f"scaling is missing required field {' or '.join(names)}"
    )


def _require_hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise EquationScaling6DOFError(f"{name} must be a canonical sha256 hash")
    return value


def _validate_equation_scaling(scaling: EquationScaling6DOF) -> None:
    if scaling.schema_version != EQUATION_SCALING_6DOF_SCHEMA_VERSION:
        raise EquationScaling6DOFError("equation scaling schema version is invalid")
    if scaling.policy != EQUATION_SCALING_6DOF_POLICY:
        raise EquationScaling6DOFError("equation scaling policy is invalid")
    for name in (
        "scaling_hash",
        "source_identity_hash",
        "source_node_coordinates_hash",
        "source_reference_load_hash",
        "source_free_dofs_hash",
        "row_equilibration_hash",
        "column_equilibration_hash",
    ):
        _require_hash(getattr(scaling, name), name)
    for name in (
        "characteristic_length_m",
        "reference_force",
        "residual_translation_scale",
        "residual_rotation_scale",
        "increment_translation_scale_m",
        "increment_rotation_scale_rad",
    ):
        _positive(getattr(scaling, name), name)
    if (
        type(scaling.dof_count) is not int
        or scaling.dof_count < 6
        or scaling.dof_count % 6 != 0
        or type(scaling.free_equation_count) is not int
        or not 1 <= scaling.free_equation_count <= scaling.dof_count
    ):
        raise EquationScaling6DOFError("equation scaling DOF counts are invalid")
    if scaling.residual_translation_scale != scaling.reference_force:
        raise EquationScaling6DOFError(
            "translation residual scale does not match reference force"
        )
    if scaling.residual_rotation_scale != (
        scaling.reference_force * scaling.characteristic_length_m
    ):
        raise EquationScaling6DOFError(
            "rotation residual scale does not match force-length scaling"
        )
    if scaling.increment_translation_scale_m != scaling.characteristic_length_m:
        raise EquationScaling6DOFError(
            "translation increment scale does not match characteristic length"
        )
    if scaling.increment_rotation_scale_rad != 1.0:
        raise EquationScaling6DOFError("rotation increment scale must equal one radian")


def _validate_scaling_source_binding(
    scaling: Any,
    free_dofs: np.ndarray,
) -> None:
    if type(scaling) is EquationScaling6DOF:
        scaling.to_manifest()
        if free_dofs.size != scaling.free_equation_count:
            raise EquationScaling6DOFError(
                "free DOF count does not match equation scaling"
            )
    else:
        serializer = getattr(scaling, "to_dict", None)
        if not callable(serializer):
            raise EquationScaling6DOFError(
                "scaling must provide a validated source-bound manifest"
            )
        try:
            serializer()
        except EquationScaling6DOFError:
            raise
        except (TypeError, ValueError, RuntimeError) as error:
            raise EquationScaling6DOFError(
                "scaling source-bound manifest is invalid"
            ) from error
    free_hash = _require_hash(
        getattr(scaling, "source_free_dofs_hash", None),
        "source_free_dofs_hash",
    )
    expected_free_hash = array_data_hash(np.asarray(free_dofs, dtype="<i8"))
    if free_hash != expected_free_hash:
        raise EquationScaling6DOFError(
            "free DOFs do not match equation scaling source binding"
        )
    length = _scaling_field(scaling, "characteristic_length_m")
    row_scale, column_scale = equilibration_vectors_6dof(free_dofs, length)
    expected_row_hash = array_data_hash(np.asarray(row_scale, dtype="<f8"))
    expected_column_hash = array_data_hash(np.asarray(column_scale, dtype="<f8"))
    if _require_hash(
        getattr(scaling, "row_equilibration_hash", None),
        "row_equilibration_hash",
    ) != expected_row_hash or _require_hash(
        getattr(scaling, "column_equilibration_hash", None),
        "column_equilibration_hash",
    ) != expected_column_hash:
        raise EquationScaling6DOFError(
            "equilibration vectors do not match equation scaling source binding"
        )


def _linf(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0


def _manifest(
    scaling: EquationScaling6DOF,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": scaling.schema_version,
        "policy": scaling.policy,
        "source_identity_hash": scaling.source_identity_hash,
        "characteristic_length_m": scaling.characteristic_length_m,
        "reference_force": scaling.reference_force,
        "residual_translation_scale": scaling.residual_translation_scale,
        "residual_rotation_scale": scaling.residual_rotation_scale,
        "increment_translation_scale_m": scaling.increment_translation_scale_m,
        "increment_rotation_scale_rad": scaling.increment_rotation_scale_rad,
        "dof_count": scaling.dof_count,
        "free_equation_count": scaling.free_equation_count,
        "source_node_coordinates_hash": scaling.source_node_coordinates_hash,
        "source_reference_load_hash": scaling.source_reference_load_hash,
        "source_free_dofs_hash": scaling.source_free_dofs_hash,
        "row_equilibration_hash": scaling.row_equilibration_hash,
        "column_equilibration_hash": scaling.column_equilibration_hash,
    }
    if include_hash:
        payload["scaling_hash"] = scaling.scaling_hash
    return payload


__all__ = [
    "EQUATION_SCALING_6DOF_POLICY",
    "EQUATION_SCALING_6DOF_SCHEMA_VERSION",
    "EquationScaling6DOF",
    "EquationScaling6DOFError",
    "create_equation_scaling_6dof",
    "equilibration_vectors_6dof",
    "exact_scaled_condition_number_1",
    "scale_linear_system_6dof",
    "scaled_increment_metrics_6dof",
    "scaled_residual_metrics_6dof",
]
