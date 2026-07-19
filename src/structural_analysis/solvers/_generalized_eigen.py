"""Shared strict helpers for deterministic symmetric generalized eigen solves."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable

import numpy as np


SEMANTIC_HASH_PROFILE = "canonical-json-scientific-12e"


class GeneralizedEigenContractError(ValueError):
    """Raised when an eigenproblem violates the strict numerical contract."""


def require_nonnegative_tolerance(value: float, *, name: str) -> float:
    if isinstance(value, bool):
        raise GeneralizedEigenContractError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise GeneralizedEigenContractError(
            f"{name} must be finite and non-negative"
        ) from exc
    if not math.isfinite(result) or result < 0.0:
        raise GeneralizedEigenContractError(f"{name} must be finite and non-negative")
    return result


def as_binary64_square(matrix: np.ndarray, *, name: str) -> np.ndarray:
    result = np.asarray(matrix, dtype=np.float64)
    if result.ndim != 2 or result.shape[0] != result.shape[1] or result.shape[0] == 0:
        raise GeneralizedEigenContractError(f"{name} must be a non-empty square matrix")
    if not np.all(np.isfinite(result)):
        raise GeneralizedEigenContractError(f"{name} must contain only finite binary64 values")
    return np.array(result, dtype=np.float64, order="C", copy=True)


def validate_symmetric(
    matrix: np.ndarray,
    *,
    name: str,
    relative_tolerance: float,
) -> tuple[np.ndarray, float, bool]:
    relative_tolerance = require_nonnegative_tolerance(
        relative_tolerance,
        name="symmetry relative tolerance",
    )
    scale = max(float(np.max(np.abs(matrix))), np.finfo(np.float64).tiny)
    error = float(np.max(np.abs(matrix - matrix.T))) / scale
    if error > relative_tolerance:
        raise GeneralizedEigenContractError(
            f"{name} relative symmetry error {error:.17g} exceeds "
            f"{relative_tolerance:.17g}"
        )
    projected = bool(np.any(matrix != matrix.T))
    return 0.5 * (matrix + matrix.T), error, projected


def require_positive_definite(matrix: np.ndarray, *, name: str) -> float:
    try:
        np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError as exc:
        raise GeneralizedEigenContractError(f"{name} must be positive definite") from exc
    minimum = float(np.min(np.linalg.eigvalsh(matrix)))
    if not math.isfinite(minimum) or minimum <= 0.0:
        raise GeneralizedEigenContractError(f"{name} must be positive definite")
    return minimum


def require_positive_semidefinite(
    matrix: np.ndarray,
    *,
    name: str,
    relative_tolerance: float,
) -> tuple[float, int]:
    relative_tolerance = require_nonnegative_tolerance(
        relative_tolerance,
        name="positive-semidefinite relative tolerance",
    )
    eigenvalues = np.linalg.eigvalsh(matrix)
    scale = max(float(np.max(np.abs(eigenvalues))), np.finfo(np.float64).tiny)
    minimum = float(np.min(eigenvalues))
    if minimum < -relative_tolerance * scale:
        raise GeneralizedEigenContractError(
            f"{name} minimum eigenvalue {minimum:.17g} violates the "
            "positive-semidefinite contract"
        )
    rank = int(np.count_nonzero(eigenvalues > relative_tolerance * scale))
    return minimum, rank


def matrix_sha256(matrix: np.ndarray) -> str:
    canonical = np.ascontiguousarray(matrix, dtype="<f8")
    return "sha256:" + hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def raw_modes_sha256(eigenvalues: Iterable[float], vectors: np.ndarray) -> str:
    values, modes = _result_arrays(eigenvalues, vectors)
    values = np.ascontiguousarray(values, dtype="<f8")
    modes = np.ascontiguousarray(modes, dtype="<f8")
    digest = hashlib.sha256()
    digest.update(values.tobytes(order="C"))
    digest.update(modes.tobytes(order="C"))
    return "sha256:" + digest.hexdigest()


def semantic_modes_sha256(eigenvalues: Iterable[float], vectors: np.ndarray) -> str:
    values, modes = _result_arrays(eigenvalues, vectors)
    payload = {
        "profile": SEMANTIC_HASH_PROFILE,
        "eigenvalues": [_semantic_number(value) for value in values.tolist()],
        "vectors_by_column": [
            _semantic_mode_column(modes[:, column])
            for column in range(modes.shape[1])
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def cluster_slices(values: np.ndarray, *, relative_tolerance: float) -> tuple[slice, ...]:
    if values.ndim != 1 or values.size == 0:
        raise GeneralizedEigenContractError("eigenvalue vector must be non-empty")
    relative_tolerance = require_nonnegative_tolerance(
        relative_tolerance,
        name="cluster relative tolerance",
    )
    starts = [0]
    for index in range(1, values.size):
        scale = max(abs(float(values[index - 1])), abs(float(values[index])), 1.0)
        if abs(float(values[index] - values[index - 1])) > relative_tolerance * scale:
            starts.append(index)
    starts.append(values.size)
    return tuple(slice(left, right) for left, right in zip(starts, starts[1:]))


def require_complete_cluster_selection(
    values: np.ndarray,
    *,
    selected_count: int,
    relative_tolerance: float,
) -> None:
    """Reject a prefix that cuts through a repeated/clustered eigenvalue group."""

    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or vector.size == 0 or not np.all(np.isfinite(vector)):
        raise GeneralizedEigenContractError(
            "candidate eigenvalue vector must be finite and non-empty"
        )
    if selected_count <= 0 or selected_count > vector.size:
        raise GeneralizedEigenContractError("selected eigenvalue count is invalid")
    if np.any(np.diff(vector) < 0.0):
        raise GeneralizedEigenContractError("candidate eigenvalues must be sorted")
    for cluster in cluster_slices(vector, relative_tolerance=relative_tolerance):
        if cluster.start < selected_count < cluster.stop:
            raise GeneralizedEigenContractError(
                "requested mode_count cuts a repeated or clustered eigenvalue group"
            )


def canonicalize_eigenspace(
    basis: np.ndarray,
    *,
    metric: np.ndarray,
    basis_tolerance: float = 1.0e-12,
) -> np.ndarray:
    """Return a coordinate-axis-derived, metric-orthonormal eigenspace basis."""

    basis_tolerance = require_nonnegative_tolerance(
        basis_tolerance,
        name="eigenspace basis tolerance",
    )
    vectors = np.asarray(basis, dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[0] != metric.shape[0] or vectors.shape[1] == 0:
        raise GeneralizedEigenContractError("eigenspace basis shape is invalid")
    orthonormal = _metric_orthonormalize(
        (vectors[:, index] for index in range(vectors.shape[1])),
        metric=metric,
        required_count=vectors.shape[1],
        basis_tolerance=basis_tolerance,
    )
    candidates = []
    metric_columns = metric
    for coordinate in range(vectors.shape[0]):
        coefficients = orthonormal.T @ metric_columns[:, coordinate]
        candidates.append(orthonormal @ coefficients)
    canonical = _metric_orthonormalize(
        candidates,
        metric=metric,
        required_count=vectors.shape[1],
        basis_tolerance=basis_tolerance,
    )
    for column in range(canonical.shape[1]):
        canonical[:, column] = canonical_mode_sign(canonical[:, column])
    return canonical


def canonical_mode_sign(vector: np.ndarray) -> np.ndarray:
    result = np.asarray(vector, dtype=np.float64).copy()
    pivot = int(np.argmax(np.abs(result)))
    if result[pivot] < 0.0:
        result *= -1.0
    return result


def max_component_normalized(vector: np.ndarray) -> tuple[float, ...]:
    values = np.asarray(vector, dtype=np.float64)
    scale = float(np.max(np.abs(values)))
    if not math.isfinite(scale) or scale <= 0.0:
        raise GeneralizedEigenContractError("mode vector cannot be normalized")
    return tuple(float(value) for value in (values / scale).tolist())


def _metric_orthonormalize(
    candidates: Iterable[np.ndarray],
    *,
    metric: np.ndarray,
    required_count: int,
    basis_tolerance: float,
) -> np.ndarray:
    accepted: list[np.ndarray] = []
    for candidate in candidates:
        vector = np.asarray(candidate, dtype=np.float64).copy()
        if vector.shape != (metric.shape[0],) or not np.all(np.isfinite(vector)):
            continue
        for _ in range(2):
            for prior in accepted:
                vector -= prior * float(prior @ metric @ vector)
        norm_squared = float(vector @ metric @ vector)
        if not math.isfinite(norm_squared) or norm_squared <= basis_tolerance**2:
            continue
        vector /= math.sqrt(norm_squared)
        vector = canonical_mode_sign(vector)
        accepted.append(vector)
        if len(accepted) == required_count:
            break
    if len(accepted) != required_count:
        raise GeneralizedEigenContractError(
            "coordinate-axis eigenspace canonicalization lost rank"
        )
    return np.column_stack(accepted)


def _semantic_number(value: float) -> str:
    result = float(value)
    if not math.isfinite(result):
        raise GeneralizedEigenContractError("semantic result hash requires finite values")
    if result == 0.0:
        result = 0.0
    return format(result, ".12e")


def _result_arrays(
    eigenvalues: Iterable[float],
    vectors: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(tuple(eigenvalues), dtype=np.float64)
    modes = np.asarray(vectors, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise GeneralizedEigenContractError(
            "result eigenvalues must be a finite non-empty vector"
        )
    if (
        modes.ndim != 2
        or modes.shape[0] == 0
        or modes.shape[1] != values.size
        or not np.all(np.isfinite(modes))
    ):
        raise GeneralizedEigenContractError(
            "result mode matrix must be finite with one column per eigenvalue"
        )
    return values, modes


def _semantic_mode_column(column: np.ndarray) -> list[str]:
    scale = float(np.max(np.abs(column)))
    if not math.isfinite(scale) or scale <= 0.0:
        raise GeneralizedEigenContractError("semantic mode column cannot be zero")
    zero_threshold = 1.0e-12 * scale
    return [
        _semantic_number(0.0 if abs(float(value)) <= zero_threshold else float(value))
        for value in column.tolist()
    ]
