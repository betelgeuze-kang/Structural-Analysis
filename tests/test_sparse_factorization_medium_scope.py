from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import diags

from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SPARSE_FACTORIZATION_CONDITION_METHOD,
    SparseFactorizationError,
    SparseFactorizationPolicy,
    factorize_and_solve_sparse,
    validate_sparse_factorization_diagnostic_manifest,
)


def test_default_exact_condition_scope_covers_medium_corpus_equation_count() -> None:
    size = 257
    diagonal = np.linspace(1.0, 2.0, size, dtype=np.float64)
    matrix = diags(diagonal, format="csr")
    rhs = np.ones(size, dtype=np.float64)

    solved = factorize_and_solve_sparse(matrix, rhs)

    assert np.allclose(solved.solution, 1.0 / diagonal)
    assert solved.diagnostic.equation_count == size
    assert (
        solved.diagnostic.condition_estimate_method
        == SPARSE_FACTORIZATION_CONDITION_METHOD
    )
    assert solved.diagnostic.policy["maximum_exact_condition_equations"] == 512
    assert solved.diagnostic.contract_pass is True
    assert (
        validate_sparse_factorization_diagnostic_manifest(
            solved.diagnostic.to_manifest()
        )["contract_pass"]
        is True
    )


def test_explicit_legacy_scope_remains_fail_closed() -> None:
    size = 257
    matrix = diags(np.ones(size, dtype=np.float64), format="csr")
    rhs = np.ones(size, dtype=np.float64)
    policy = SparseFactorizationPolicy(maximum_exact_condition_equations=256)

    with pytest.raises(SparseFactorizationError) as captured:
        factorize_and_solve_sparse(matrix, rhs, policy=policy)

    assert captured.value.code == "sparse_condition_diagnostic_scope_exceeded"
    assert captured.value.diagnostic is None
