"""Exact-matrix invocation reuse; tiny numerical systems, no performance run."""

from contextvars import copy_context
from dataclasses import replace
import builtins
import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix, eye

from structural_analysis.solvers.nonlinear import sparse_factorization as module
from structural_analysis.solvers.nonlinear._factorization_cache import (
    _factorization_lease,
)


def matrix():
    return csr_matrix([[3.0, 0.125], [0.125, 2.0]])


def solve(a=None, rhs=None, **kwargs):
    return module.factorize_and_solve_sparse(
        matrix() if a is None else a,
        np.array([1.0, -2.0]) if rhs is None else rhs,
        **kwargs,
    )


def stats():
    return module.sparse_factorization_reuse_statistics()


def test_exact_matrix_new_rhs_solution_and_receipt_are_fresh_and_uncached_equivalent():
    a = matrix()
    rhs = np.array([1.0, -2.0])
    expected = solve(a, rhs)
    with module.reuse_sparse_factorizations() as handle:
        assert handle is None
        first = solve(a, rhs)
        assert first.diagnostic.to_manifest() == expected.diagnostic.to_manifest()
        before = first.solution.tobytes()
        rhs[:] = [0.3, 0.7]
        second = solve(a, rhs)
        np.testing.assert_allclose(
            second.solution, np.linalg.solve(a.toarray(), rhs), rtol=1e-14, atol=1e-15
        )
        assert second.diagnostic.rhs_hash != first.diagnostic.rhs_hash
        assert second.diagnostic.solution_hash != first.diagnostic.solution_hash
        assert first.solution.tobytes() == before
        assert stats()["hits"] == 1 and stats()["misses"] == 1
        assert stats()["publications"] == 1 and stats()["entries"] == 1
    assert stats() == {"active": False}
    uncached = solve(a, rhs)
    np.testing.assert_array_equal(second.solution, uncached.solution)
    assert second.diagnostic.to_manifest() == uncached.diagnostic.to_manifest()


def test_one_numeric_value_changed_by_about_1e_minus_16_cannot_hit():
    a = matrix()
    with module.reuse_sparse_factorizations():
        first = solve(a)
        a.data[1] += 1e-16
        second = solve(a)
        assert (
            first.diagnostic.input_numeric_hash != second.diagnostic.input_numeric_hash
        )
        assert stats()["misses"] == 2 and stats()["hits"] == 0


def test_policy_is_bound_and_failure_is_never_published():
    with module.reuse_sparse_factorizations():
        solve()
        solve(policy=module.SparseFactorizationPolicy(maximum_backward_error=2e-12))
        assert stats()["misses"] == 2 and stats()["entries"] == 2
        strict = module.SparseFactorizationPolicy(maximum_condition_number_1=0.5)
        for _ in range(2):
            with pytest.raises(
                module.SparseFactorizationError, match="condition_number_policy"
            ):
                solve(policy=strict)
        assert stats()["misses"] == 4 and stats()["publications"] == 2
        assert stats()["entries"] == 2


@pytest.mark.parametrize("kind", ["singular", "pivot", "backward"])
def test_failed_factor_or_diagnostic_gates_are_not_cached(kind):
    a, policy = matrix(), module.SparseFactorizationPolicy()
    if kind == "singular":
        a = csr_matrix([[1.0, 1.0], [1.0, 1.0]])
        code = "sparse_factorization_singular"
    elif kind == "pivot":
        policy = replace(policy, minimum_normalized_absolute_pivot=0.99)
        code = "sparse_pivot_quality_policy_exceeded"
    else:
        a = csr_matrix([[1.1, 0.314159], [0.271828, 0.7]])
        policy = replace(policy, maximum_backward_error=1e-30)
        code = "sparse_backward_error_policy_exceeded"
    with module.reuse_sparse_factorizations():
        for _ in range(2):
            with pytest.raises(module.SparseFactorizationError) as error:
                solve(a, np.array([np.pi, np.e]), policy=policy)
            assert error.value.code == code
        assert stats()["entries"] == stats()["publications"] == 0
        assert stats()["misses"] == 2


def test_rhs_matrix_and_original_256_equation_scope_admission_precede_reuse(
    monkeypatch,
):
    def prohibited(*args, **kwargs):
        pytest.fail("invalid input reached factorization")

    monkeypatch.setattr(module, "splu", prohibited)
    with module.reuse_sparse_factorizations():
        for rhs in ([float("nan"), 1.0], [1.0]):
            with pytest.raises(module.SparseFactorizationError, match="rhs_invalid"):
                solve(rhs=np.asarray(rhs))
        with pytest.raises(module.SparseFactorizationError, match="matrix_invalid"):
            solve(csr_matrix([[float("inf"), 0.0], [0.0, 1.0]]))
        with pytest.raises(module.SparseFactorizationError, match="scope_exceeded"):
            solve(eye(257, format="csr"), np.ones(257))
        assert stats()["entries"] == stats()["publications"] == 0


def test_custom_splu_is_uncached_even_when_a_matching_real_factor_exists(monkeypatch):
    original, calls = module.splu, []

    def custom(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    with module.reuse_sparse_factorizations():
        solve()
        monkeypatch.setattr(module, "splu", custom)
        solve()
        solve()
        assert len(calls) == 2 and stats()["hits"] == 0
        assert stats()["publications"] == 1


def test_dynamic_inverse_implementation_cannot_borrow_a_previous_norm(monkeypatch):
    original, calls = module._exact_inverse_one_norm, []

    def custom(factor, size):
        calls.append(1)
        return original(factor, size)

    with module.reuse_sparse_factorizations():
        solve()
        monkeypatch.setattr(module, "_exact_inverse_one_norm", custom)
        solve()
        solve()
        assert len(calls) == 2 and stats()["hits"] == 0


def test_reused_factor_rechecks_gates_and_failure_evicts_the_previous_entry(
    monkeypatch,
):
    with module.reuse_sparse_factorizations():
        solve()
        with monkeypatch.context() as changed:
            changed.setattr(module, "_sparse_matrix_one_norm", lambda _: 1e20)
            with pytest.raises(
                module.SparseFactorizationError, match="condition_number_policy"
            ):
                solve()
        assert stats()["hits"] == 1 and stats()["entries"] == 0
        solve()
        assert stats()["misses"] == stats()["publications"] == 2


def test_underlying_superlu_implementation_change_is_uncached(monkeypatch):
    original, calls = module._superlu.gstrf, []

    def custom(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    with module.reuse_sparse_factorizations():
        solve()
        monkeypatch.setattr(module._superlu, "gstrf", custom)
        solve()
        solve()
        assert len(calls) == 2 and stats()["hits"] == 0
        assert stats()["entries"] == stats()["publications"] == 1


def test_rebound_splu_backend_module_cannot_borrow_an_existing_factor(monkeypatch):
    original, calls = module._superlu.gstrf, []

    def custom(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    with module.reuse_sparse_factorizations():
        solve()
        monkeypatch.setattr(module.linsolve, "_superlu", SimpleNamespace(gstrf=custom))
        solve()
        solve()
        assert len(calls) == 2 and stats()["hits"] == 0
        assert stats()["entries"] == stats()["publications"] == 1


def test_missing_private_scipy_identity_import_keeps_original_uncached_solve(
    monkeypatch,
):
    original_import = builtins.__import__

    def without_private_identity(name, *args, **kwargs):
        if name == "scipy.sparse.linalg._dsolve":
            raise ImportError("simulated private module layout change")
        return original_import(name, *args, **kwargs)

    name = "structural_analysis.solvers.nonlinear._sparse_portability_probe"
    spec = importlib.util.spec_from_file_location(name, Path(module.__file__))
    probe = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, probe)
    with monkeypatch.context() as changed:
        changed.setattr(builtins, "__import__", without_private_identity)
        spec.loader.exec_module(probe)
    assert probe._REFERENCE_SUPERLU_MODULE is None
    with probe.reuse_sparse_factorizations():
        first = probe.factorize_and_solve_sparse(matrix(), [1.0, -2.0])
        second = probe.factorize_and_solve_sparse(matrix(), [0.3, 0.7])
        assert probe.sparse_factorization_reuse_statistics()["publications"] == 0
        assert probe.sparse_factorization_reuse_statistics()["hits"] == 0
    assert first.diagnostic.contract_pass and second.diagnostic.contract_pass
    np.testing.assert_allclose(second.solution, solve(rhs=[0.3, 0.7]).solution)


def test_invocations_and_nested_scopes_do_not_share_factors():
    for _ in range(2):
        with module.reuse_sparse_factorizations():
            solve()
            assert stats()["misses"] == 1 and stats()["hits"] == 0
            with module.reuse_sparse_factorizations():
                solve()
                assert stats()["misses"] == 1 and stats()["hits"] == 0
            solve()
            assert stats()["hits"] == 1


def test_scope_is_thread_owned_and_closed_context_cannot_reuse_handles():
    errors = []
    with module.reuse_sparse_factorizations():
        solve()
        context = copy_context()

        def wrong_thread():
            try:
                context.run(solve)
            except RuntimeError as error:
                errors.append(str(error))

        thread = threading.Thread(target=wrong_thread)
        thread.start()
        thread.join()
        assert len(errors) == 1 and "another thread" in errors[0]
        solve()
        assert stats()["hits"] == 1
        closed = copy_context()
    with pytest.raises(RuntimeError, match="closed"):
        closed.run(solve)


def test_scope_forbids_reentrant_factor_use():
    with module.reuse_sparse_factorizations():
        with _factorization_lease(None):
            with pytest.raises(RuntimeError, match="already in use"):
                solve()


def test_cache_is_entry_bounded_with_lru_eviction():
    with module.reuse_sparse_factorizations(max_entries=4):
        for index in range(5):
            solve(csr_matrix([[3.0 + index, 0.125], [0.125, 2.0]]))
        assert stats()["entries"] == 4 and stats()["evictions"] == 1
        solve()
        assert stats()["misses"] == 6


@pytest.mark.parametrize("maximum", [True, 0, 9, 1.0])
def test_invalid_cache_budget_is_rejected(maximum):
    with pytest.raises(ValueError, match="max_entries"):
        with module.reuse_sparse_factorizations(max_entries=maximum):
            pytest.fail("invalid cache scope admitted")
