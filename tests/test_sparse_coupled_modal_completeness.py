"""Public count and complete-space checks against free-chain closed forms."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import math

import numpy as np
import pytest
from scipy.sparse import coo_matrix, csr_matrix, eye

from structural_analysis.solvers import sparse_generalized_eigen as public


def _chains(sizes: tuple[int, ...]):
    n = sum(sizes)
    rows, cols, k_values, m_values = [], [], [], []
    q = float(1 / 6)
    offset = 0
    references = []
    for size in sizes:
        for j in range(size - 1):
            a, b = offset + j, offset + j + 1
            rows.extend((a, b, a, b))
            cols.extend((a, b, b, a))
            k_values.extend((1.0, 1.0, -1.0, -1.0))
            m_values.extend((2 * q, 2 * q, q, q))
        for ordinal in range(1, size):
            theta = ordinal * math.pi / (size - 1)
            eigenvalue = 6 * (1 - math.cos(theta)) / (2 + math.cos(theta))
            eigenvalue /= float(6 * Fraction.from_float(q))
            vector = np.zeros(n)
            vector[offset : offset + size] = [math.cos(j * theta) for j in range(size)]
            references.append((eigenvalue, vector))
        offset += size
    k = coo_matrix((k_values, (rows, cols)), shape=(n, n)).tocsr()
    m = coo_matrix((m_values, (rows, cols)), shape=(n, n)).tocsr()
    references.sort(key=lambda entry: entry[0])
    return k, m, references


def _assert_complete_space(k, m, solution, references, requested):
    values = [mode.eigenvalue_rad2_per_s2 for mode in solution.modes]
    vectors = np.asarray([mode.mass_normalized_shape for mode in solution.modes]).T
    expected = np.column_stack([vector for _, vector in references[:requested]])
    for i in range(requested):
        expected[:, i] /= math.sqrt(float(expected[:, i] @ (m @ expected[:, i])))
    np.testing.assert_allclose(
        values, [value for value, _ in references[:requested]], rtol=1e-9, atol=0
    )
    np.testing.assert_allclose(vectors.T @ (m @ vectors), np.eye(requested), atol=1e-8)
    # Both directions matter: returning one repeated direction twice cannot pass.
    for directions, basis in ((expected, vectors), (vectors, expected)):
        difference = directions - basis @ (basis.T @ (m @ directions))
        for column in difference.T:
            assert math.sqrt(max(0.0, float(column @ (m @ column)))) <= 1e-7
    for value, vector in zip(values, vectors.T, strict=True):
        kv, mv = k @ vector, m @ vector
        scale = max(np.max(np.abs(kv)) + abs(value) * np.max(np.abs(mv)), 1e-300)
        assert np.max(np.abs(kv - value * mv)) / scale <= 1e-9
    assert solution.backend_profile == public.SPARSE_COUNT_GUARDED_MODAL_PROFILE
    assert solution.contract_pass
    assert not solution.fallback_used and not solution.regularization_applied
    assert solution.candidate_eigenpair_count == requested


@pytest.mark.parametrize("sizes,requested", [((40, 40), 2), ((11, 17, 23, 29), 3)])
def test_public_original_coupled_counts_and_whole_requested_space(
    sizes, requested, monkeypatch
):
    k, m, references = _chains(sizes)
    original = public.eigsh
    calls = []

    def admission_only(*args, **kwargs):
        calls.append(kwargs["which"])
        assert kwargs["which"] != "SM", (
            "A partial low-mode estimate cannot prove the prefix"
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(public, "eigsh", admission_only)
    result = public.solve_sparse_modal_modes(k, m, mode_count=requested)
    assert result.rigid_mode_count == len(sizes)
    assert "SA" in calls and "LA" in calls
    _assert_complete_space(k, m, result, references, requested)


def test_public_complete_repeated_space_is_canonical_and_repeatable():
    k, m, references = _chains((7, 7))
    first = public.solve_sparse_modal_modes(k, m, mode_count=2)
    second = public.solve_sparse_modal_modes(k, m, mode_count=2)
    assert first.to_dict() == second.to_dict()
    assert first.rigid_mode_count == 2
    _assert_complete_space(k, m, first, references, 2)
    with pytest.raises(public.SparseGeneralizedEigenError, match="cuts|cluster"):
        public.solve_sparse_modal_modes(k, m, mode_count=1)


def test_public_permutation_retains_rank_and_selected_full_space():
    k, m, references = _chains((8, 9, 5, 7))
    p = np.r_[np.arange(0, k.shape[0], 2), np.arange(1, k.shape[0], 2)]
    kp, mp = k[p, :][:, p].tocsr(), m[p, :][:, p].tocsr()
    result = public.solve_sparse_modal_modes(kp, mp, mode_count=3)
    assert result.rigid_mode_count == 4
    _assert_complete_space(kp, mp, result, [(x, v[p]) for x, v in references], 3)


def test_public_keeps_numeric_mass_and_stiffness_policy(monkeypatch):
    k, m, _ = _chains((6,))

    def never_extract(*args, **kwargs):
        raise AssertionError(
            "Rejected numeric policy must stop before proof extraction"
        )

    monkeypatch.setattr(public, "_count_guarded_coupled_modal_prefix", never_extract)
    bad_mass = m.copy()
    bad_mass[0, 0] = -2.0
    with pytest.raises(public.SparseGeneralizedEigenError, match="positive definite"):
        public.solve_sparse_modal_modes(k, bad_mass, mode_count=1)
    bad_k = -k
    with pytest.raises(
        public.SparseGeneralizedEigenError, match="positive-semidefinite"
    ):
        public.solve_sparse_modal_modes(bad_k, m, mode_count=1)


def test_public_counts_all_stiffness_directions_when_numeric_estimate_misses_one(
    monkeypatch,
):
    k = csr_matrix(
        [
            [1.0, 2.0, 0, 0, 0, 0],
            [2.0, 1.0, 0, 0, 0, 0],
            [0, 0, 3.0, 0, 0, 0],
            [0, 0, 0, 4.0, 0, 0],
            [0, 0, 0, 0, 5.0, 0],
            [0, 0, 0, 0, 0, 6.0],
        ]
    )
    m = eye(6, format="csr", dtype=np.float64)

    def missed_direction(matrix, **kwargs):
        maximum = float(np.max(matrix.diagonal()))
        return 1.0, maximum, maximum

    monkeypatch.setattr(public, "_extreme_eigenvalues", missed_direction)
    # The coupled 2x2 stiffness block has exact eigenvalues -1 and 3.
    with pytest.raises(public.SparseGeneralizedEigenError, match="stiffness"):
        public.solve_sparse_modal_modes(k, m, mode_count=1)


def test_public_counts_the_strict_mass_policy_even_when_estimate_is_positive(
    monkeypatch,
):
    delta = float(2.0**-50)
    m = csr_matrix(
        [
            [1.0, 1.0 - delta, 0, 0, 0, 0],
            [1.0 - delta, 1.0, 0, 0, 0, 0],
            [0, 0, 1.0, 0, 0, 0],
            [0, 0, 0, 1.0, 0, 0],
            [0, 0, 0, 0, 1.0, 0],
            [0, 0, 0, 0, 0, 1.0],
        ]
    )
    k = eye(6, format="csr", dtype=np.float64)
    monkeypatch.setattr(
        public, "_extreme_eigenvalues", lambda *a, **kw: (1.0, 2.0, 2.0)
    )
    monkeypatch.setattr(public, "eigsh", lambda *a, **kw: np.asarray([1.0]))
    # M is positive definite, but its smallest exact eigenvalue 2^-50 is
    # below the unchanged conditioning cutoff eps*6*2.
    with pytest.raises(public.SparseGeneralizedEigenError, match="mass"):
        public.solve_sparse_modal_modes(k, m, mode_count=1)


def test_public_rejects_wrong_source_or_rounded_threshold_custody(monkeypatch):
    from structural_analysis.solvers import sparse_live_modal_pipeline as live

    k, m, _ = _chains((6,))
    original = live.LiveModalProofPipeline.run

    def changed_guard(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        guard = replace(
            result.public_threshold_guard, stiffness_input_hash="sha256:" + "0" * 64
        )
        return replace(result, public_threshold_guard=guard)

    monkeypatch.setattr(live.LiveModalProofPipeline, "run", changed_guard)
    with pytest.raises(public.SparseGeneralizedEigenError, match="threshold custody"):
        public.solve_sparse_modal_modes(k, m, mode_count=1)


def test_public_iteration_cap_is_forwarded_without_a_retry(monkeypatch):
    from structural_analysis.solvers import sparse_live_modal_pipeline as live

    k, m, _ = _chains((6,))
    # Isolate forwarding from the already separate numeric admission policy.
    seen = []
    original = live.LiveModalProofPipeline.run

    def recorded(self, *args, **kwargs):
        seen.append(kwargs["maximum_iterations"])
        return original(self, *args, **kwargs)

    def admitted(matrix, **kwargs):
        values = np.linalg.eigvalsh(matrix.toarray())
        return float(values[0]), float(np.max(np.abs(values))), float(values[-1])

    monkeypatch.setattr(public, "_extreme_eigenvalues", admitted)
    # The free-chain largest eigenvalue is 12 for this nominal consistent mass.
    monkeypatch.setattr(public, "eigsh", lambda *args, **kwargs: np.asarray([12.0]))
    monkeypatch.setattr(live.LiveModalProofPipeline, "run", recorded)
    with pytest.raises(public.SparseGeneralizedEigenError):
        public.solve_sparse_modal_modes(k, m, mode_count=1, maximum_iterations=1)
    assert seen == [1]
