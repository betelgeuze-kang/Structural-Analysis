"""Fail-closed sparse factorization and conditioning diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from jsonschema import Draft202012Validator
from scipy.sparse import csc_matrix, csr_matrix, issparse
from scipy.sparse.linalg import splu

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)


SPARSE_FACTORIZATION_DIAGNOSTIC_SCHEMA_VERSION = (
    "sparse-superlu-factorization-diagnostic.v1"
)
SPARSE_FACTORIZATION_BACKEND = "scipy_superlu_splu_cpu"
SPARSE_FACTORIZATION_ORDERING = "COLAMD"
SPARSE_FACTORIZATION_POLICY_ID = "public_sparse_factorization_fail_closed.v1"
SPARSE_FACTORIZATION_CONDITION_METHOD = "exact_inverse_column_solve_matrix_1_norm.v1"

_HASH_ZERO = "sha256:" + "0" * 64


@dataclass(frozen=True)
class SparseFactorizationPolicy:
    policy_id: str = SPARSE_FACTORIZATION_POLICY_ID
    maximum_condition_number_1: float = 1.0e12
    minimum_normalized_absolute_pivot: float = 1.0e-14
    maximum_backward_error: float = 1.0e-12
    maximum_exact_condition_equations: int = 256

    def __post_init__(self) -> None:
        for name in (
            "maximum_condition_number_1",
            "minimum_normalized_absolute_pivot",
            "maximum_backward_error",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite positive number")
            normalized = float(value)
            if not math.isfinite(normalized) or normalized <= 0.0:
                raise ValueError(f"{name} must be a finite positive number")
            object.__setattr__(self, name, normalized)
        if (
            type(self.maximum_exact_condition_equations) is not int
            or self.maximum_exact_condition_equations < 1
        ):
            raise ValueError(
                "maximum_exact_condition_equations must be a positive integer"
            )
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")

    @property
    def policy_hash(self) -> str:
        return canonical_hash(self.to_manifest(include_hash=False))

    def to_manifest(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "policy_id": self.policy_id,
            "maximum_condition_number_1": self.maximum_condition_number_1,
            "minimum_normalized_absolute_pivot": (
                self.minimum_normalized_absolute_pivot
            ),
            "maximum_backward_error": self.maximum_backward_error,
            "maximum_exact_condition_equations": (
                self.maximum_exact_condition_equations
            ),
            "regularization_allowed": False,
            "fallback_allowed": False,
        }
        if include_hash:
            payload["policy_hash"] = self.policy_hash
        return payload


@dataclass(frozen=True)
class SparseFactorizationDiagnostic:
    schema_version: str
    diagnostic_hash: str
    status: str
    failure_code: str | None
    backend: str
    ordering: str
    condition_estimate_method: str
    policy: Mapping[str, Any]
    equation_count: int
    input_nnz: int
    input_pattern_hash: str
    input_numeric_hash: str
    rhs_hash: str
    factor_l_nnz: int
    factor_u_nnz: int
    factor_fill_ratio: float
    absolute_pivot_minimum: float
    absolute_pivot_maximum: float
    normalized_absolute_pivot_minimum: float
    condition_number_1: float
    backward_error: float
    solution_hash: str
    permutation_row_hash: str
    permutation_column_hash: str
    checks: Mapping[str, bool]
    regularization_used: bool = False
    fallback_used: bool = False

    @property
    def contract_pass(self) -> bool:
        return bool(self.status == "pass" and all(self.checks.values()))

    def to_manifest(self) -> dict[str, Any]:
        payload = _diagnostic_payload(self, include_hash=True)
        expected = canonical_hash(_diagnostic_payload(self, include_hash=False))
        if self.diagnostic_hash != expected:
            raise ValueError("sparse factorization diagnostic hash mismatch")
        if self.contract_pass != bool(payload["contract_pass"]):
            raise ValueError("sparse factorization diagnostic status mismatch")
        return validate_sparse_factorization_diagnostic_manifest(payload)


@dataclass(frozen=True)
class SparseFactorizationSolve:
    solution: np.ndarray
    diagnostic: SparseFactorizationDiagnostic


class SparseFactorizationError(np.linalg.LinAlgError):
    """Factorization or a required diagnostic gate failed."""

    def __init__(
        self,
        code: str,
        message: str,
        diagnostic: SparseFactorizationDiagnostic | None = None,
    ) -> None:
        self.code = code
        self.diagnostic = diagnostic
        super().__init__(f"{code}: {message}")


def factorize_and_solve_sparse(
    matrix: Any,
    rhs: Any,
    *,
    policy: SparseFactorizationPolicy | None = None,
) -> SparseFactorizationSolve:
    """Factor a finite square sparse matrix and enforce diagnostic policy."""

    selected = policy or SparseFactorizationPolicy()
    csr = _canonical_csr(matrix)
    vector = np.asarray(rhs, dtype=np.float64)
    size = csr.shape[0]
    if vector.shape != (size,) or not np.all(np.isfinite(vector)):
        raise SparseFactorizationError(
            "sparse_factorization_rhs_invalid",
            "rhs must be one finite value per equation",
        )
    if size > selected.maximum_exact_condition_equations:
        raise SparseFactorizationError(
            "sparse_condition_diagnostic_scope_exceeded",
            "equation count exceeds the exact condition-diagnostic policy limit",
        )

    pattern_hash = canonical_hash(
        {
            "shape": [size, size],
            "row_ptr": csr.indptr.tolist(),
            "column_indices": csr.indices.tolist(),
        }
    )
    numeric_hash = array_data_hash(np.asarray(csr.data, dtype="<f8"))
    rhs_hash = array_data_hash(np.asarray(vector, dtype="<f8"))
    try:
        factor = splu(
            csc_matrix(csr),
            permc_spec=SPARSE_FACTORIZATION_ORDERING,
            diag_pivot_thresh=1.0,
            options={"Equil": True},
        )
    except (RuntimeError, ValueError) as exc:
        raise SparseFactorizationError(
            "sparse_factorization_singular",
            "SuperLU could not factor the unregularized tangent",
        ) from exc

    solution = np.asarray(factor.solve(vector), dtype=np.float64)
    pivots = np.abs(np.asarray(factor.U.diagonal(), dtype=np.float64))
    if (
        solution.shape != vector.shape
        or not np.all(np.isfinite(solution))
        or pivots.shape != vector.shape
        or not np.all(np.isfinite(pivots))
    ):
        raise SparseFactorizationError(
            "sparse_factorization_nonfinite_output",
            "SuperLU returned non-finite solution or pivot data",
        )

    pivot_minimum = float(np.min(pivots)) if pivots.size else 0.0
    pivot_maximum = float(np.max(pivots)) if pivots.size else 0.0
    normalized_pivot = pivot_minimum / pivot_maximum if pivot_maximum > 0.0 else 0.0
    matrix_norm_1 = _sparse_matrix_one_norm(csr)
    inverse_norm_1 = _exact_inverse_one_norm(factor, size)
    condition_number_1 = matrix_norm_1 * inverse_norm_1
    residual = np.asarray(csr @ solution - vector, dtype=np.float64)
    matrix_norm_inf = _sparse_matrix_infinity_norm(csr)
    denominator = matrix_norm_inf * _linf(solution) + _linf(vector)
    backward_error = _linf(residual) / max(
        denominator, float(np.finfo(np.float64).tiny)
    )
    factor_nnz = int(factor.L.nnz + factor.U.nnz)
    fill_ratio = float(factor_nnz / max(csr.nnz, 1))
    checks = MappingProxyType(
        {
            "factorization_succeeded": True,
            "solution_finite": bool(np.all(np.isfinite(solution))),
            "condition_number_within_policy": bool(
                math.isfinite(condition_number_1)
                and condition_number_1 <= selected.maximum_condition_number_1
            ),
            "normalized_pivot_within_policy": bool(
                normalized_pivot >= selected.minimum_normalized_absolute_pivot
            ),
            "backward_error_within_policy": bool(
                math.isfinite(backward_error)
                and backward_error <= selected.maximum_backward_error
            ),
            "regularization_not_used": True,
            "fallback_not_used": True,
        }
    )
    failure_code = next(
        (
            code
            for check, code in (
                (
                    "condition_number_within_policy",
                    "sparse_condition_number_policy_exceeded",
                ),
                (
                    "normalized_pivot_within_policy",
                    "sparse_pivot_quality_policy_exceeded",
                ),
                (
                    "backward_error_within_policy",
                    "sparse_backward_error_policy_exceeded",
                ),
            )
            if not checks[check]
        ),
        None,
    )
    provisional = SparseFactorizationDiagnostic(
        schema_version=SPARSE_FACTORIZATION_DIAGNOSTIC_SCHEMA_VERSION,
        diagnostic_hash=_HASH_ZERO,
        status="pass" if failure_code is None else "blocked",
        failure_code=failure_code,
        backend=SPARSE_FACTORIZATION_BACKEND,
        ordering=SPARSE_FACTORIZATION_ORDERING,
        condition_estimate_method=SPARSE_FACTORIZATION_CONDITION_METHOD,
        policy=MappingProxyType(selected.to_manifest()),
        equation_count=size,
        input_nnz=int(csr.nnz),
        input_pattern_hash=pattern_hash,
        input_numeric_hash=numeric_hash,
        rhs_hash=rhs_hash,
        factor_l_nnz=int(factor.L.nnz),
        factor_u_nnz=int(factor.U.nnz),
        factor_fill_ratio=fill_ratio,
        absolute_pivot_minimum=pivot_minimum,
        absolute_pivot_maximum=pivot_maximum,
        normalized_absolute_pivot_minimum=normalized_pivot,
        condition_number_1=float(condition_number_1),
        backward_error=float(backward_error),
        solution_hash=array_data_hash(np.asarray(solution, dtype="<f8")),
        permutation_row_hash=array_data_hash(np.asarray(factor.perm_r, dtype="<i8")),
        permutation_column_hash=array_data_hash(np.asarray(factor.perm_c, dtype="<i8")),
        checks=checks,
    )
    diagnostic = replace(
        provisional,
        diagnostic_hash=canonical_hash(
            _diagnostic_payload(provisional, include_hash=False)
        ),
    )
    if not diagnostic.contract_pass:
        raise SparseFactorizationError(
            failure_code or "sparse_factorization_diagnostic_failed",
            "unregularized sparse factorization failed a required diagnostic gate",
            diagnostic,
        )
    frozen_solution = immutable_array(solution, dtype="<f8")
    return SparseFactorizationSolve(solution=frozen_solution, diagnostic=diagnostic)


def validate_sparse_factorization_diagnostic_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a detached diagnostic against schema, hash, and policy rules."""

    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    errors = sorted(
        _diagnostic_schema_validator().iter_errors(normalized),
        key=lambda row: list(row.path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        raise ValueError(
            f"sparse factorization diagnostic schema invalid at {path}: {first.message}"
        )
    claimed = str(normalized["diagnostic_hash"])
    body = dict(normalized)
    body.pop("diagnostic_hash")
    if claimed != canonical_hash(body):
        raise ValueError("sparse factorization diagnostic hash mismatch")

    policy = dict(normalized["policy"])
    policy_hash = str(policy.pop("policy_hash"))
    if policy_hash != canonical_hash(policy):
        raise ValueError("sparse factorization policy hash mismatch")
    if int(normalized["equation_count"]) > int(
        normalized["policy"]["maximum_exact_condition_equations"]
    ):
        raise ValueError("sparse factorization diagnostic exceeds policy scope")

    expected_fill = (
        int(normalized["factor_l_nnz"]) + int(normalized["factor_u_nnz"])
    ) / int(normalized["input_nnz"])
    if not math.isclose(
        float(normalized["factor_fill_ratio"]),
        expected_fill,
        rel_tol=1.0e-15,
        abs_tol=0.0,
    ):
        raise ValueError("sparse factorization diagnostic fill ratio mismatch")

    checks = normalized["checks"]
    expected_quality_checks = {
        "condition_number_within_policy": bool(
            float(normalized["condition_number_1"])
            <= float(normalized["policy"]["maximum_condition_number_1"])
        ),
        "normalized_pivot_within_policy": bool(
            float(normalized["normalized_absolute_pivot_minimum"])
            >= float(normalized["policy"]["minimum_normalized_absolute_pivot"])
        ),
        "backward_error_within_policy": bool(
            float(normalized["backward_error"])
            <= float(normalized["policy"]["maximum_backward_error"])
        ),
    }
    if any(
        checks[name] is not expected
        for name, expected in expected_quality_checks.items()
    ):
        raise ValueError("sparse factorization diagnostic policy relationship mismatch")
    if not all(
        checks[name] is True
        for name in (
            "factorization_succeeded",
            "solution_finite",
            "regularization_not_used",
            "fallback_not_used",
        )
    ):
        raise ValueError("sparse factorization diagnostic invariant check failed")

    failure_code = next(
        (
            code
            for check, code in (
                (
                    "condition_number_within_policy",
                    "sparse_condition_number_policy_exceeded",
                ),
                (
                    "normalized_pivot_within_policy",
                    "sparse_pivot_quality_policy_exceeded",
                ),
                (
                    "backward_error_within_policy",
                    "sparse_backward_error_policy_exceeded",
                ),
            )
            if checks[check] is not True
        ),
        None,
    )
    expected_status = "pass" if failure_code is None else "blocked"
    if normalized["status"] != expected_status:
        raise ValueError("sparse factorization diagnostic status mismatch")
    if normalized["failure_code"] != failure_code:
        raise ValueError("sparse factorization diagnostic failure code mismatch")
    expected_pass = expected_status == "pass" and all(
        bool(value) for value in checks.values()
    )
    if normalized["contract_pass"] is not expected_pass:
        raise ValueError("sparse factorization diagnostic status mismatch")
    return normalized


@lru_cache(maxsize=1)
def _diagnostic_schema_validator() -> Draft202012Validator:
    path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("sparse_factorization_diagnostic_v1.schema.json")
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise TypeError("packaged sparse factorization schema must be an object")
    return Draft202012Validator(schema)


def _canonical_csr(matrix: Any) -> csr_matrix:
    csr = (
        matrix.tocsr(copy=True)
        if issparse(matrix)
        else csr_matrix(np.asarray(matrix, dtype=np.float64))
    )
    csr.sum_duplicates()
    csr.eliminate_zeros()
    csr.sort_indices()
    if (
        len(csr.shape) != 2
        or csr.shape[0] != csr.shape[1]
        or csr.shape[0] == 0
        or not np.all(np.isfinite(csr.data))
    ):
        raise SparseFactorizationError(
            "sparse_factorization_matrix_invalid",
            "matrix must be finite, square, and non-empty",
        )
    return csr


def _sparse_matrix_one_norm(matrix: csr_matrix) -> float:
    return float(np.max(np.asarray(np.abs(matrix).sum(axis=0)).reshape(-1)))


def _sparse_matrix_infinity_norm(matrix: csr_matrix) -> float:
    return float(np.max(np.asarray(np.abs(matrix).sum(axis=1)).reshape(-1)))


def _exact_inverse_one_norm(factor: Any, size: int) -> float:
    maximum = 0.0
    basis = np.zeros(size, dtype=np.float64)
    for column in range(size):
        basis.fill(0.0)
        basis[column] = 1.0
        inverse_column = np.asarray(factor.solve(basis), dtype=np.float64)
        if inverse_column.shape != (size,) or not np.all(np.isfinite(inverse_column)):
            return math.inf
        maximum = max(maximum, float(np.sum(np.abs(inverse_column))))
    return maximum


def _linf(values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(array))) if array.size else 0.0


def _diagnostic_payload(
    diagnostic: SparseFactorizationDiagnostic,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": diagnostic.schema_version,
        "status": diagnostic.status,
        "contract_pass": diagnostic.contract_pass,
        "failure_code": diagnostic.failure_code,
        "backend": diagnostic.backend,
        "ordering": diagnostic.ordering,
        "condition_estimate_method": diagnostic.condition_estimate_method,
        "policy": dict(diagnostic.policy),
        "equation_count": diagnostic.equation_count,
        "input_nnz": diagnostic.input_nnz,
        "input_pattern_hash": diagnostic.input_pattern_hash,
        "input_numeric_hash": diagnostic.input_numeric_hash,
        "rhs_hash": diagnostic.rhs_hash,
        "factor_l_nnz": diagnostic.factor_l_nnz,
        "factor_u_nnz": diagnostic.factor_u_nnz,
        "factor_fill_ratio": diagnostic.factor_fill_ratio,
        "absolute_pivot_minimum": diagnostic.absolute_pivot_minimum,
        "absolute_pivot_maximum": diagnostic.absolute_pivot_maximum,
        "normalized_absolute_pivot_minimum": (
            diagnostic.normalized_absolute_pivot_minimum
        ),
        "condition_number_1": diagnostic.condition_number_1,
        "backward_error": diagnostic.backward_error,
        "solution_hash": diagnostic.solution_hash,
        "permutation_row_hash": diagnostic.permutation_row_hash,
        "permutation_column_hash": diagnostic.permutation_column_hash,
        "checks": dict(diagnostic.checks),
        "regularization_used": diagnostic.regularization_used,
        "fallback_used": diagnostic.fallback_used,
    }
    if include_hash:
        payload["diagnostic_hash"] = diagnostic.diagnostic_hash
    return payload


__all__ = [
    "SPARSE_FACTORIZATION_BACKEND",
    "SPARSE_FACTORIZATION_CONDITION_METHOD",
    "SPARSE_FACTORIZATION_DIAGNOSTIC_SCHEMA_VERSION",
    "SPARSE_FACTORIZATION_ORDERING",
    "SPARSE_FACTORIZATION_POLICY_ID",
    "SparseFactorizationDiagnostic",
    "SparseFactorizationError",
    "SparseFactorizationPolicy",
    "SparseFactorizationSolve",
    "factorize_and_solve_sparse",
    "validate_sparse_factorization_diagnostic_manifest",
]
