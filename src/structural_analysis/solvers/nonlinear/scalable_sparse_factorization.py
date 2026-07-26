"""Blockwise exact-condition sparse factorization for larger bounded systems.

The public sparse policy intentionally keeps a 256-equation exact diagnostic.
This experimental P2 backend extends the same fail-closed semantics by solving
identity columns in deterministic multi-RHS blocks.  It remains an exact
matrix 1-norm condition calculation, not a lower-bound estimator.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import numpy as np
from scipy.sparse import csc_matrix, csr_matrix, issparse
from scipy.sparse.linalg import splu

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)


SCALABLE_SPARSE_FACTORIZATION_SCHEMA_VERSION = (
    "sparse-superlu-blocked-exact-factorization-diagnostic.v1"
)
SCALABLE_SPARSE_FACTORIZATION_BACKEND = "scipy_superlu_splu_cpu"
SCALABLE_SPARSE_FACTORIZATION_ORDERING = "COLAMD"
SCALABLE_SPARSE_FACTORIZATION_POLICY_ID = (
    "experimental_blocked_exact_sparse_factorization_fail_closed.v1"
)
SCALABLE_SPARSE_FACTORIZATION_CONDITION_METHOD = (
    "blocked_exact_inverse_column_solve_matrix_1_norm.v1"
)
SCALABLE_SPARSE_FACTORIZATION_CLAIM_BOUNDARY = (
    "Experimental CPU-only exact conditioning for at most 1536 equations. "
    "The blockwise inverse-column solve remains quadratic-work diagnostic "
    "evidence and is integrated only into the bounded experimental 3D graph "
    "candidate; it is not a public or production-scale sparse policy, external "
    "V&V, performance evidence, or release authority."
)
_ZERO_HASH = "sha256:" + "0" * 64


@dataclass(frozen=True)
class ScalableSparseFactorizationPolicy:
    policy_id: str = SCALABLE_SPARSE_FACTORIZATION_POLICY_ID
    maximum_condition_number_1: float = 1.0e14
    minimum_normalized_absolute_pivot: float = 1.0e-16
    maximum_backward_error: float = 1.0e-12
    maximum_equations: int = 1536
    inverse_solve_block_size: int = 32

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
        for name in ("maximum_equations", "inverse_solve_block_size"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.inverse_solve_block_size > self.maximum_equations:
            raise ValueError(
                "inverse_solve_block_size may not exceed maximum_equations"
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
            "maximum_equations": self.maximum_equations,
            "inverse_solve_block_size": self.inverse_solve_block_size,
            "condition_estimate_is_exact": True,
            "regularization_allowed": False,
            "fallback_allowed": False,
        }
        if include_hash:
            payload["policy_hash"] = self.policy_hash
        return payload


@dataclass(frozen=True)
class ScalableSparseFactorizationDiagnostic:
    schema_version: str
    diagnostic_hash: str
    status: str
    failure_code: str | None
    backend: str
    ordering: str
    condition_estimate_method: str
    condition_estimate_is_exact: bool
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
    inverse_solve_block_size: int
    inverse_solve_block_count: int
    condition_number_1: float
    backward_error: float
    solution_hash: str
    permutation_row_hash: str
    permutation_column_hash: str
    checks: Mapping[str, bool]
    claims: Mapping[str, bool]
    claim_boundary: str = SCALABLE_SPARSE_FACTORIZATION_CLAIM_BOUNDARY
    regularization_used: bool = False
    fallback_used: bool = False

    @property
    def contract_pass(self) -> bool:
        return bool(self.status == "pass" and all(self.checks.values()))

    def to_manifest(self) -> dict[str, Any]:
        payload = _diagnostic_payload(self, include_hash=True)
        expected = canonical_hash(_diagnostic_payload(self, include_hash=False))
        if self.diagnostic_hash != expected:
            raise ValueError("scalable sparse diagnostic hash mismatch")
        if self.contract_pass != bool(payload["contract_pass"]):
            raise ValueError("scalable sparse diagnostic status mismatch")
        return validate_scalable_sparse_factorization_manifest(payload)


@dataclass(frozen=True)
class ScalableSparseFactorizationSolve:
    solution: np.ndarray
    diagnostic: ScalableSparseFactorizationDiagnostic


class ScalableSparseFactorizationError(np.linalg.LinAlgError):
    """Factorization or a required scalable diagnostic gate failed."""

    def __init__(
        self,
        code: str,
        message: str,
        diagnostic: ScalableSparseFactorizationDiagnostic | None = None,
    ) -> None:
        self.code = code
        self.diagnostic = diagnostic
        super().__init__(f"{code}: {message}")


def factorize_and_solve_scalable_sparse(
    matrix: Any,
    rhs: Any,
    *,
    policy: ScalableSparseFactorizationPolicy | None = None,
) -> ScalableSparseFactorizationSolve:
    """Factor a bounded larger sparse matrix with exact blocked conditioning."""

    selected = policy or ScalableSparseFactorizationPolicy()
    csr = _canonical_csr(matrix)
    vector = np.asarray(rhs, dtype=np.float64)
    size = csr.shape[0]
    if vector.shape != (size,) or not np.all(np.isfinite(vector)):
        raise ScalableSparseFactorizationError(
            "scalable_sparse_rhs_invalid",
            "rhs must be one finite value per equation",
        )
    if size > selected.maximum_equations:
        raise ScalableSparseFactorizationError(
            "scalable_sparse_equation_scope_exceeded",
            "equation count exceeds the blocked exact-condition policy limit",
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
            permc_spec=SCALABLE_SPARSE_FACTORIZATION_ORDERING,
            diag_pivot_thresh=1.0,
            options={"Equil": True},
        )
    except (RuntimeError, ValueError) as error:
        raise ScalableSparseFactorizationError(
            "scalable_sparse_factorization_singular",
            "SuperLU could not factor the unregularized tangent",
        ) from error
    solution = np.asarray(factor.solve(vector), dtype=np.float64)
    pivots = np.abs(np.asarray(factor.U.diagonal(), dtype=np.float64))
    if (
        solution.shape != vector.shape
        or not np.all(np.isfinite(solution))
        or pivots.shape != vector.shape
        or not np.all(np.isfinite(pivots))
    ):
        raise ScalableSparseFactorizationError(
            "scalable_sparse_nonfinite_output",
            "SuperLU returned non-finite solution or pivot data",
        )
    pivot_minimum = float(np.min(pivots)) if pivots.size else 0.0
    pivot_maximum = float(np.max(pivots)) if pivots.size else 0.0
    normalized_pivot = pivot_minimum / pivot_maximum if pivot_maximum > 0.0 else 0.0
    inverse_norm_1, block_count = _blocked_exact_inverse_one_norm(
        factor,
        size,
        block_size=selected.inverse_solve_block_size,
    )
    condition_number_1 = _sparse_matrix_one_norm(csr) * inverse_norm_1
    residual = np.asarray(csr @ solution - vector, dtype=np.float64)
    denominator = _sparse_matrix_infinity_norm(csr) * _linf(solution) + _linf(vector)
    backward_error = _linf(residual) / max(
        denominator,
        float(np.finfo(np.float64).tiny),
    )
    factor_nnz = int(factor.L.nnz + factor.U.nnz)
    fill_ratio = float(factor_nnz / max(csr.nnz, 1))
    checks = MappingProxyType(
        {
            "factorization_succeeded": True,
            "solution_finite": bool(np.all(np.isfinite(solution))),
            "condition_number_exact": True,
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
                    "scalable_sparse_condition_number_policy_exceeded",
                ),
                (
                    "normalized_pivot_within_policy",
                    "scalable_sparse_pivot_quality_policy_exceeded",
                ),
                (
                    "backward_error_within_policy",
                    "scalable_sparse_backward_error_policy_exceeded",
                ),
            )
            if not checks[check]
        ),
        None,
    )
    provisional = ScalableSparseFactorizationDiagnostic(
        schema_version=SCALABLE_SPARSE_FACTORIZATION_SCHEMA_VERSION,
        diagnostic_hash=_ZERO_HASH,
        status="pass" if failure_code is None else "blocked",
        failure_code=failure_code,
        backend=SCALABLE_SPARSE_FACTORIZATION_BACKEND,
        ordering=SCALABLE_SPARSE_FACTORIZATION_ORDERING,
        condition_estimate_method=SCALABLE_SPARSE_FACTORIZATION_CONDITION_METHOD,
        condition_estimate_is_exact=True,
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
        inverse_solve_block_size=selected.inverse_solve_block_size,
        inverse_solve_block_count=block_count,
        condition_number_1=float(condition_number_1),
        backward_error=float(backward_error),
        solution_hash=array_data_hash(np.asarray(solution, dtype="<f8")),
        permutation_row_hash=array_data_hash(np.asarray(factor.perm_r, dtype="<i8")),
        permutation_column_hash=array_data_hash(np.asarray(factor.perm_c, dtype="<i8")),
        checks=checks,
        claims=MappingProxyType(
            {
                "bounded_larger_system_exact_diagnostic_only": True,
                "production_scale_sparse_policy": False,
                "integrated_nonlinear_3d_backend": True,
                "external_vv": False,
                "release_authority": False,
            }
        ),
    )
    diagnostic = replace(
        provisional,
        diagnostic_hash=canonical_hash(
            _diagnostic_payload(provisional, include_hash=False)
        ),
    )
    if not diagnostic.contract_pass:
        raise ScalableSparseFactorizationError(
            failure_code or "scalable_sparse_diagnostic_failed",
            "unregularized scalable sparse factorization failed a required gate",
            diagnostic,
        )
    return ScalableSparseFactorizationSolve(
        solution=immutable_array(solution, dtype="<f8"),
        diagnostic=diagnostic,
    )


def validate_scalable_sparse_factorization_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    errors = sorted(
        _schema_validator().iter_errors(normalized),
        key=lambda row: list(row.path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        raise ValueError(
            f"scalable sparse diagnostic schema invalid at {path}: {first.message}"
        )
    claimed = str(normalized["diagnostic_hash"])
    body = dict(normalized)
    body.pop("diagnostic_hash")
    if claimed != canonical_hash(body):
        raise ValueError("scalable sparse diagnostic hash mismatch")
    policy = dict(normalized["policy"])
    policy_hash = str(policy.pop("policy_hash"))
    if policy_hash != canonical_hash(policy):
        raise ValueError("scalable sparse policy hash mismatch")
    maximum_equations = int(normalized["policy"]["maximum_equations"])
    block_size = int(normalized["policy"]["inverse_solve_block_size"])
    equation_count = int(normalized["equation_count"])
    if block_size > maximum_equations or equation_count > maximum_equations:
        raise ValueError("scalable sparse diagnostic exceeds policy scope")
    if int(normalized["inverse_solve_block_size"]) != block_size:
        raise ValueError("scalable sparse diagnostic block size mismatch")
    expected_block_count = (equation_count + block_size - 1) // block_size
    if int(normalized["inverse_solve_block_count"]) != expected_block_count:
        raise ValueError("scalable sparse diagnostic block count mismatch")
    expected_fill = (
        int(normalized["factor_l_nnz"]) + int(normalized["factor_u_nnz"])
    ) / int(normalized["input_nnz"])
    if not math.isclose(
        float(normalized["factor_fill_ratio"]),
        expected_fill,
        rel_tol=1.0e-15,
        abs_tol=0.0,
    ):
        raise ValueError("scalable sparse diagnostic fill ratio mismatch")
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
        raise ValueError("scalable sparse diagnostic policy relationship mismatch")
    always_required = (
        "factorization_succeeded",
        "solution_finite",
        "condition_number_exact",
        "regularization_not_used",
        "fallback_not_used",
    )
    if not all(checks[key] is True for key in always_required):
        raise ValueError("scalable sparse diagnostic invariant check failed")
    failure_code = next(
        (
            code
            for check, code in (
                (
                    "condition_number_within_policy",
                    "scalable_sparse_condition_number_policy_exceeded",
                ),
                (
                    "normalized_pivot_within_policy",
                    "scalable_sparse_pivot_quality_policy_exceeded",
                ),
                (
                    "backward_error_within_policy",
                    "scalable_sparse_backward_error_policy_exceeded",
                ),
            )
            if checks[check] is not True
        ),
        None,
    )
    expected_status = "pass" if failure_code is None else "blocked"
    if normalized["status"] != expected_status:
        raise ValueError("scalable sparse diagnostic status mismatch")
    if normalized["failure_code"] != failure_code:
        raise ValueError("scalable sparse diagnostic failure code mismatch")
    expected_pass = expected_status == "pass" and all(
        bool(value) for value in checks.values()
    )
    if normalized["contract_pass"] is not expected_pass:
        raise ValueError("scalable sparse diagnostic status mismatch")
    return normalized


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("scalable_sparse_factorization_diagnostic_v1.schema.json")
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise TypeError("packaged scalable sparse schema must be an object")
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
        raise ScalableSparseFactorizationError(
            "scalable_sparse_matrix_invalid",
            "matrix must be finite, square, and non-empty",
        )
    return csr


def _blocked_exact_inverse_one_norm(
    factor: Any,
    size: int,
    *,
    block_size: int,
) -> tuple[float, int]:
    maximum = 0.0
    block_count = 0
    for start in range(0, size, block_size):
        width = min(block_size, size - start)
        identity_columns = np.zeros((size, width), dtype=np.float64)
        offsets = np.arange(width)
        identity_columns[start + offsets, offsets] = 1.0
        inverse_columns = np.asarray(
            factor.solve(identity_columns),
            dtype=np.float64,
        )
        if inverse_columns.shape != (size, width) or not np.all(
            np.isfinite(inverse_columns)
        ):
            return math.inf, block_count + 1
        maximum = max(
            maximum,
            float(np.max(np.sum(np.abs(inverse_columns), axis=0))),
        )
        block_count += 1
    return maximum, block_count


def _sparse_matrix_one_norm(matrix: csr_matrix) -> float:
    return float(np.max(np.asarray(np.abs(matrix).sum(axis=0)).reshape(-1)))


def _sparse_matrix_infinity_norm(matrix: csr_matrix) -> float:
    return float(np.max(np.asarray(np.abs(matrix).sum(axis=1)).reshape(-1)))


def _linf(values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(array))) if array.size else 0.0


def _diagnostic_payload(
    diagnostic: ScalableSparseFactorizationDiagnostic,
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
        "condition_estimate_is_exact": diagnostic.condition_estimate_is_exact,
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
        "inverse_solve_block_size": diagnostic.inverse_solve_block_size,
        "inverse_solve_block_count": diagnostic.inverse_solve_block_count,
        "condition_number_1": diagnostic.condition_number_1,
        "backward_error": diagnostic.backward_error,
        "solution_hash": diagnostic.solution_hash,
        "permutation_row_hash": diagnostic.permutation_row_hash,
        "permutation_column_hash": diagnostic.permutation_column_hash,
        "checks": dict(diagnostic.checks),
        "claims": dict(diagnostic.claims),
        "claim_boundary": diagnostic.claim_boundary,
        "regularization_used": diagnostic.regularization_used,
        "fallback_used": diagnostic.fallback_used,
    }
    if include_hash:
        payload["diagnostic_hash"] = diagnostic.diagnostic_hash
    return payload


__all__ = [
    "SCALABLE_SPARSE_FACTORIZATION_BACKEND",
    "SCALABLE_SPARSE_FACTORIZATION_CLAIM_BOUNDARY",
    "SCALABLE_SPARSE_FACTORIZATION_CONDITION_METHOD",
    "SCALABLE_SPARSE_FACTORIZATION_ORDERING",
    "SCALABLE_SPARSE_FACTORIZATION_POLICY_ID",
    "SCALABLE_SPARSE_FACTORIZATION_SCHEMA_VERSION",
    "ScalableSparseFactorizationDiagnostic",
    "ScalableSparseFactorizationError",
    "ScalableSparseFactorizationPolicy",
    "ScalableSparseFactorizationSolve",
    "factorize_and_solve_scalable_sparse",
    "validate_scalable_sparse_factorization_manifest",
]
