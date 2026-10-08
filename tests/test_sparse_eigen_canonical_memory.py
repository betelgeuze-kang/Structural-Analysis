"""Sparse low-mode canonicalization must not allocate all n coordinate vectors."""

import tracemalloc

import numpy as np
import pytest
from scipy.sparse import diags

from structural_analysis.solvers.sparse_generalized_eigen import (
    _canonicalize_sparse_eigenspace,
)


@pytest.mark.parametrize("offset", [0, 2046])
def test_low_rank_canonicalization_has_bounded_peak_allocation(offset):
    n = 2048
    basis = np.zeros((n, 2))
    basis[offset, 0] = basis[offset + 1, 1] = 1.0
    metric = diags(np.ones(n), format="csr")
    tracing_before = tracemalloc.is_tracing()
    if not tracing_before:
        tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    try:
        actual = _canonicalize_sparse_eigenspace(basis, metric)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        if not tracing_before:
            tracemalloc.stop()
    np.testing.assert_array_equal(actual, basis)
    # A generous 2 MiB bound for a 32 KiB basis; an eager n-by-n candidate
    # collection uses over 32 MiB. This bounds traced allocations of this stage,
    # not whole-process RSS or full eigen-solver memory.
    assert peak - baseline < 2 * 1024 * 1024
