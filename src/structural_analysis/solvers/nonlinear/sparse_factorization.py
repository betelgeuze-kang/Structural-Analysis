"""Bounded public sparse factorization policy for the medium planar corpus.

The audited v1 implementation remains byte-identical in
``_sparse_factorization_v1``. This public module only extends the exact
condition-diagnostic scope to the declared medium corpus boundary; it does not
introduce an estimator, regularization, or fallback path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import _sparse_factorization_v1 as _v1


SPARSE_FACTORIZATION_DIAGNOSTIC_SCHEMA_VERSION = (
    _v1.SPARSE_FACTORIZATION_DIAGNOSTIC_SCHEMA_VERSION
)
SPARSE_FACTORIZATION_BACKEND = _v1.SPARSE_FACTORIZATION_BACKEND
SPARSE_FACTORIZATION_ORDERING = _v1.SPARSE_FACTORIZATION_ORDERING
SPARSE_FACTORIZATION_POLICY_ID = _v1.SPARSE_FACTORIZATION_POLICY_ID
SPARSE_FACTORIZATION_CONDITION_METHOD = _v1.SPARSE_FACTORIZATION_CONDITION_METHOD

SparseFactorizationDiagnostic = _v1.SparseFactorizationDiagnostic
SparseFactorizationError = _v1.SparseFactorizationError
SparseFactorizationSolve = _v1.SparseFactorizationSolve
validate_sparse_factorization_diagnostic_manifest = (
    _v1.validate_sparse_factorization_diagnostic_manifest
)


@dataclass(frozen=True)
class SparseFactorizationPolicy(_v1.SparseFactorizationPolicy):
    """Fail-closed exact diagnostic policy bounded to 512 equations.

    The prior 256-equation default remains available by explicitly supplying
    ``maximum_exact_condition_equations=256``. The higher default is narrowly
    sized for the declared M1-M5/L1-L2 corpus and remains an exact inverse-column
    diagnostic rather than an estimated condition number.
    """

    maximum_exact_condition_equations: int = 512


def factorize_and_solve_sparse(
    matrix: Any,
    rhs: Any,
    *,
    policy: SparseFactorizationPolicy | _v1.SparseFactorizationPolicy | None = None,
) -> SparseFactorizationSolve:
    """Factor and solve with the bounded exact public diagnostic policy."""

    selected = policy or SparseFactorizationPolicy()
    return _v1.factorize_and_solve_sparse(matrix, rhs, policy=selected)


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
