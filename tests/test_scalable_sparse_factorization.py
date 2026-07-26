from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    SCALABLE_SPARSE_FACTORIZATION_BACKEND,
    ScalableSparseFactorizationError,
    ScalableSparseFactorizationPolicy,
    factorize_and_solve_scalable_sparse,
    validate_scalable_sparse_factorization_manifest,
)


def test_blocked_exact_factorization_supports_more_than_256_equations() -> None:
    size = 300
    diagonal = np.linspace(2.0, 11.0, size, dtype=np.float64)
    matrix = diags(diagonal, format="csr")
    rhs = np.linspace(-3.0, 7.0, size, dtype=np.float64)

    first = factorize_and_solve_scalable_sparse(matrix, rhs)
    repeated = factorize_and_solve_scalable_sparse(matrix, rhs)
    manifest = first.diagnostic.to_manifest()

    np.testing.assert_allclose(first.solution, rhs / diagonal, rtol=0.0, atol=0.0)
    assert first.solution.flags.writeable is False
    assert manifest["backend"] == SCALABLE_SPARSE_FACTORIZATION_BACKEND
    assert manifest["equation_count"] == size
    assert manifest["inverse_solve_block_size"] == 32
    assert manifest["inverse_solve_block_count"] == 10
    assert manifest["condition_estimate_is_exact"] is True
    assert manifest["checks"]["condition_number_exact"] is True
    assert manifest["condition_number_1"] == pytest.approx(11.0 / 2.0)
    assert manifest["regularization_used"] is False
    assert manifest["fallback_used"] is False
    assert manifest["claims"] == {
        "bounded_larger_system_exact_diagnostic_only": True,
        "production_scale_sparse_policy": False,
        "integrated_nonlinear_3d_backend": True,
        "external_vv": False,
        "release_authority": False,
    }
    assert (
        "integrated only into the bounded experimental 3D graph candidate"
        in manifest["claim_boundary"]
    )
    assert (
        "not a public or production-scale sparse policy" in manifest["claim_boundary"]
    )
    assert first.diagnostic.diagnostic_hash == repeated.diagnostic.diagnostic_hash
    assert validate_scalable_sparse_factorization_manifest(manifest) == manifest

    manifest["condition_number_1"] = 1.0
    with pytest.raises(ValueError, match="diagnostic hash mismatch"):
        validate_scalable_sparse_factorization_manifest(manifest)


def test_blocked_exact_factorization_matches_dense_non_diagonal_reference() -> None:
    size = 257
    matrix = diags(
        (-np.ones(size - 1), 4.0 * np.ones(size), -np.ones(size - 1)),
        offsets=(-1, 0, 1),
        format="csr",
    )
    rhs = np.sin(np.linspace(0.0, 3.0, size, dtype=np.float64))

    solved = factorize_and_solve_scalable_sparse(matrix, rhs)
    dense = matrix.toarray()

    np.testing.assert_allclose(
        solved.solution,
        np.linalg.solve(dense, rhs),
        rtol=1.0e-12,
        atol=1.0e-12,
    )
    assert solved.diagnostic.condition_number_1 == pytest.approx(
        np.linalg.cond(dense, p=1),
        rel=1.0e-12,
    )
    assert solved.diagnostic.inverse_solve_block_count == 9


def _rehash_manifest(payload: dict) -> dict:
    body = dict(payload)
    body.pop("diagnostic_hash", None)
    payload["diagnostic_hash"] = canonical_hash(body)
    return payload


def test_rehashed_scope_status_and_block_relationship_tampering_is_rejected() -> None:
    solved = factorize_and_solve_scalable_sparse(
        diags(np.linspace(2.0, 3.0, 300), format="csr"),
        np.ones(300),
    )
    manifest = solved.diagnostic.to_manifest()

    out_of_scope = deepcopy(manifest)
    out_of_scope["policy"]["maximum_equations"] = 299
    policy_body = dict(out_of_scope["policy"])
    policy_body.pop("policy_hash")
    out_of_scope["policy"]["policy_hash"] = canonical_hash(policy_body)
    _rehash_manifest(out_of_scope)
    with pytest.raises(ValueError, match="exceeds policy scope"):
        validate_scalable_sparse_factorization_manifest(out_of_scope)

    wrong_policy_hash = deepcopy(manifest)
    wrong_policy_hash["policy"]["maximum_condition_number_1"] = 1.0e12
    _rehash_manifest(wrong_policy_hash)
    with pytest.raises(ValueError, match="policy hash mismatch"):
        validate_scalable_sparse_factorization_manifest(wrong_policy_hash)

    wrong_block_size = deepcopy(manifest)
    wrong_block_size["inverse_solve_block_size"] = 16
    _rehash_manifest(wrong_block_size)
    with pytest.raises(ValueError, match="block size mismatch"):
        validate_scalable_sparse_factorization_manifest(wrong_block_size)

    wrong_blocks = deepcopy(manifest)
    wrong_blocks["inverse_solve_block_count"] = 9
    _rehash_manifest(wrong_blocks)
    with pytest.raises(ValueError, match="block count mismatch"):
        validate_scalable_sparse_factorization_manifest(wrong_blocks)

    wrong_fill = deepcopy(manifest)
    wrong_fill["factor_fill_ratio"] = 1.0
    _rehash_manifest(wrong_fill)
    with pytest.raises(ValueError, match="fill ratio mismatch"):
        validate_scalable_sparse_factorization_manifest(wrong_fill)

    false_block = deepcopy(manifest)
    false_block["status"] = "blocked"
    false_block["contract_pass"] = False
    _rehash_manifest(false_block)
    with pytest.raises(ValueError, match="status mismatch"):
        validate_scalable_sparse_factorization_manifest(false_block)

    false_condition = deepcopy(manifest)
    false_condition["condition_number_1"] = 1.0e15
    _rehash_manifest(false_condition)
    with pytest.raises(ValueError, match="policy relationship mismatch"):
        validate_scalable_sparse_factorization_manifest(false_condition)


def test_scalable_factorization_condition_gate_is_fail_closed() -> None:
    policy = ScalableSparseFactorizationPolicy(maximum_condition_number_1=1.0e6)

    with pytest.raises(
        ScalableSparseFactorizationError,
        match="scalable_sparse_condition_number_policy_exceeded",
    ) as caught:
        factorize_and_solve_scalable_sparse(
            csr_matrix(np.diag([1.0, 1.0e-8])),
            [1.0, 1.0],
            policy=policy,
        )

    diagnostic = caught.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.contract_pass is False
    assert diagnostic.failure_code == "scalable_sparse_condition_number_policy_exceeded"
    assert diagnostic.to_manifest()["contract_pass"] is False


def test_scalable_pivot_and_backward_error_gates_fail_closed() -> None:
    pivot_policy = ScalableSparseFactorizationPolicy(
        maximum_condition_number_1=1.0e10,
        minimum_normalized_absolute_pivot=1.0e-6,
    )
    with pytest.raises(
        ScalableSparseFactorizationError,
        match="scalable_sparse_pivot_quality_policy_exceeded",
    ) as pivot_caught:
        factorize_and_solve_scalable_sparse(
            csr_matrix(np.diag([1.0, 1.0e-8])),
            [1.0, 1.0],
            policy=pivot_policy,
        )
    assert pivot_caught.value.diagnostic is not None
    assert pivot_caught.value.diagnostic.fallback_used is False

    backward_policy = ScalableSparseFactorizationPolicy(maximum_backward_error=1.0e-18)
    with pytest.raises(
        ScalableSparseFactorizationError,
        match="scalable_sparse_backward_error_policy_exceeded",
    ) as backward_caught:
        factorize_and_solve_scalable_sparse(
            csr_matrix(np.asarray([[0.1, 0.2], [0.3, 0.7]])),
            [0.1, 0.2],
            policy=backward_policy,
        )
    diagnostic = backward_caught.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.backward_error > backward_policy.maximum_backward_error
    assert diagnostic.regularization_used is False
    assert diagnostic.fallback_used is False


def test_scalable_factorization_scope_and_singular_matrix_fail_closed() -> None:
    policy = replace(
        ScalableSparseFactorizationPolicy(),
        maximum_equations=2,
        inverse_solve_block_size=2,
    )
    with pytest.raises(
        ScalableSparseFactorizationError,
        match="scalable_sparse_equation_scope_exceeded",
    ):
        factorize_and_solve_scalable_sparse(
            csr_matrix(np.eye(3)), np.ones(3), policy=policy
        )

    with pytest.raises(
        ScalableSparseFactorizationError,
        match="scalable_sparse_factorization_singular",
    ):
        factorize_and_solve_scalable_sparse(
            csr_matrix([[1.0, 1.0], [1.0, 1.0]]),
            [1.0, 1.0],
        )

    with pytest.raises(ScalableSparseFactorizationError, match="rhs_invalid"):
        factorize_and_solve_scalable_sparse(csr_matrix(np.eye(2)), [1.0])

    with pytest.raises(ScalableSparseFactorizationError, match="matrix_invalid"):
        factorize_and_solve_scalable_sparse(csr_matrix(np.ones((2, 3))), np.ones(2))


@pytest.mark.parametrize(
    "kwargs",
    (
        {"maximum_condition_number_1": 0.0},
        {"minimum_normalized_absolute_pivot": float("nan")},
        {"maximum_backward_error": True},
        {"maximum_equations": 0},
        {"inverse_solve_block_size": 0},
        {"maximum_equations": 2, "inverse_solve_block_size": 3},
        {"policy_id": ""},
    ),
)
def test_scalable_factorization_policy_rejects_false_pass_values(
    kwargs: object,
) -> None:
    with pytest.raises(ValueError):
        ScalableSparseFactorizationPolicy(**kwargs)  # type: ignore[arg-type]
