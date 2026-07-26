from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SPARSE_FACTORIZATION_BACKEND,
    SparseFactorizationError,
    SparseFactorizationPolicy,
    factorize_and_solve_sparse,
    validate_sparse_factorization_diagnostic_manifest,
)


def test_superlu_factorization_receipt_binds_solution_and_conditioning() -> None:
    matrix = csr_matrix(
        np.asarray(
            [
                [12.0, -2.0, 0.0, 0.0],
                [-2.0, 10.0, -1.0, 0.0],
                [0.0, -1.0, 8.0, -1.0],
                [0.0, 0.0, -1.0, 6.0],
            ],
            dtype=np.float64,
        )
    )
    rhs = np.asarray([1.0, 2.0, -1.0, 3.0], dtype=np.float64)

    first = factorize_and_solve_sparse(matrix, rhs)
    repeated = factorize_and_solve_sparse(matrix, rhs)
    manifest = first.diagnostic.to_manifest()

    np.testing.assert_allclose(first.solution, np.linalg.solve(matrix.toarray(), rhs))
    assert first.solution.flags.writeable is False
    assert first.diagnostic.contract_pass is True
    assert manifest["backend"] == SPARSE_FACTORIZATION_BACKEND
    assert manifest["ordering"] == "COLAMD"
    assert manifest["regularization_used"] is False
    assert manifest["fallback_used"] is False
    assert manifest["condition_number_1"] == pytest.approx(
        np.linalg.cond(matrix.toarray(), p=1), rel=1.0e-12
    )
    assert manifest["backward_error"] <= 1.0e-12
    assert first.diagnostic.diagnostic_hash == repeated.diagnostic.diagnostic_hash
    assert validate_sparse_factorization_diagnostic_manifest(manifest) == manifest

    manifest["condition_number_1"] = 1.0
    with pytest.raises(ValueError, match="diagnostic hash mismatch"):
        validate_sparse_factorization_diagnostic_manifest(manifest)


def test_condition_policy_blocks_ill_conditioned_unregularized_factorization() -> None:
    matrix = csr_matrix(np.diag([1.0, 1.0e-10]))
    policy = SparseFactorizationPolicy(maximum_condition_number_1=1.0e8)

    with pytest.raises(
        SparseFactorizationError,
        match="sparse_condition_number_policy_exceeded",
    ) as caught:
        factorize_and_solve_sparse(matrix, [1.0, 1.0], policy=policy)

    diagnostic = caught.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.status == "blocked"
    assert diagnostic.contract_pass is False
    assert diagnostic.failure_code == "sparse_condition_number_policy_exceeded"
    assert diagnostic.checks["condition_number_within_policy"] is False
    assert diagnostic.regularization_used is False
    assert diagnostic.fallback_used is False
    assert diagnostic.to_manifest()["contract_pass"] is False


def test_singular_matrix_and_diagnostic_scope_fail_closed() -> None:
    with pytest.raises(SparseFactorizationError, match="sparse_factorization_singular"):
        factorize_and_solve_sparse(csr_matrix([[1.0, 1.0], [1.0, 1.0]]), [1, 1])

    policy = replace(SparseFactorizationPolicy(), maximum_exact_condition_equations=1)
    with pytest.raises(
        SparseFactorizationError,
        match="sparse_condition_diagnostic_scope_exceeded",
    ):
        factorize_and_solve_sparse(csr_matrix(np.eye(2)), [1.0, 1.0], policy=policy)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"maximum_condition_number_1": 0.0},
        {"minimum_normalized_absolute_pivot": float("nan")},
        {"maximum_backward_error": True},
        {"maximum_exact_condition_equations": 0},
    ),
)
def test_sparse_factorization_policy_rejects_false_pass_values(kwargs) -> None:
    with pytest.raises(ValueError):
        SparseFactorizationPolicy(**kwargs)
