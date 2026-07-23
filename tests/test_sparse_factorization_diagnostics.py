from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SPARSE_FACTORIZATION_BACKEND,
    SparseFactorizationError,
    SparseFactorizationPolicy,
    factorize_and_solve_sparse,
    validate_sparse_factorization_diagnostic_manifest,
)
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
    newton_raphson_vector,
)


def _rehash_manifest(payload: dict) -> dict:
    body = dict(payload)
    body.pop("diagnostic_hash", None)
    payload["diagnostic_hash"] = canonical_hash(body)
    return payload


class _IllConditionedSparseProblem:
    case_id = "ill_conditioned_sparse_newton_contract"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(2, dtype=np.float64)

    def assemble(self, free_displacements_m: np.ndarray):
        matrix = csr_matrix(np.diag([1.0, 1.0e-13]))
        residual = matrix @ free_displacements_m - np.ones(2, dtype=np.float64)
        return np.asarray(residual, dtype=np.float64), matrix


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


def test_sparse_newton_propagates_blocked_diagnostic_without_fallback() -> None:
    solution = newton_raphson_vector(
        _IllConditionedSparseProblem(),
        config=NewtonRaphsonConfig(matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND),
    )

    assert solution.status == "blocked"
    assert solution.metrics["terminal_reason"] == (
        "sparse_condition_number_policy_exceeded"
    )
    assert solution.metrics["sparse_factorization_count"] == 1
    assert solution.metrics["sparse_factorization_diagnostics_passed"] is False
    assert len(solution.metrics["sparse_factorization_diagnostics"]) == 1
    assert solution.metrics["fallback_used"] is False
    assert solution.metrics["regularization_used"] is False


def test_pivot_and_backward_error_policies_fail_closed_without_fallback() -> None:
    pivot_policy = SparseFactorizationPolicy(
        maximum_condition_number_1=1.0e10,
        minimum_normalized_absolute_pivot=1.0e-6,
    )
    with pytest.raises(
        SparseFactorizationError,
        match="sparse_pivot_quality_policy_exceeded",
    ) as pivot_caught:
        factorize_and_solve_sparse(
            csr_matrix(np.diag([1.0, 1.0e-8])),
            [1.0, 1.0],
            policy=pivot_policy,
        )
    assert pivot_caught.value.diagnostic is not None
    assert pivot_caught.value.diagnostic.fallback_used is False
    assert pivot_caught.value.diagnostic.regularization_used is False

    backward_policy = SparseFactorizationPolicy(maximum_backward_error=1.0e-18)
    with pytest.raises(
        SparseFactorizationError,
        match="sparse_backward_error_policy_exceeded",
    ) as backward_caught:
        factorize_and_solve_sparse(
            csr_matrix(np.asarray([[0.1, 0.2], [0.3, 0.7]])),
            [0.1, 0.2],
            policy=backward_policy,
        )
    diagnostic = backward_caught.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.backward_error > backward_policy.maximum_backward_error
    assert diagnostic.fallback_used is False
    assert diagnostic.regularization_used is False


def test_rehashed_policy_scope_fill_status_and_relationship_tampering_is_rejected() -> (
    None
):
    manifest = factorize_and_solve_sparse(
        csr_matrix(np.asarray([[4.0, -1.0], [-1.0, 3.0]])),
        [1.0, 2.0],
    ).diagnostic.to_manifest()

    wrong_policy_hash = deepcopy(manifest)
    wrong_policy_hash["policy"]["maximum_condition_number_1"] = 1.0e10
    _rehash_manifest(wrong_policy_hash)
    with pytest.raises(ValueError, match="policy hash mismatch"):
        validate_sparse_factorization_diagnostic_manifest(wrong_policy_hash)

    out_of_scope = deepcopy(manifest)
    out_of_scope["policy"]["maximum_exact_condition_equations"] = 1
    policy_body = dict(out_of_scope["policy"])
    policy_body.pop("policy_hash")
    out_of_scope["policy"]["policy_hash"] = canonical_hash(policy_body)
    _rehash_manifest(out_of_scope)
    with pytest.raises(ValueError, match="exceeds policy scope"):
        validate_sparse_factorization_diagnostic_manifest(out_of_scope)

    wrong_fill = deepcopy(manifest)
    wrong_fill["factor_fill_ratio"] = 1.0
    _rehash_manifest(wrong_fill)
    with pytest.raises(ValueError, match="fill ratio mismatch"):
        validate_sparse_factorization_diagnostic_manifest(wrong_fill)

    false_condition = deepcopy(manifest)
    false_condition["condition_number_1"] = 1.0e15
    _rehash_manifest(false_condition)
    with pytest.raises(ValueError, match="policy relationship mismatch"):
        validate_sparse_factorization_diagnostic_manifest(false_condition)

    false_block = deepcopy(manifest)
    false_block["status"] = "blocked"
    false_block["contract_pass"] = False
    _rehash_manifest(false_block)
    with pytest.raises(ValueError, match="status mismatch"):
        validate_sparse_factorization_diagnostic_manifest(false_block)


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
