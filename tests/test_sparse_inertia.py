"""Analytical tests of the independent exact sparse inertia utility."""

from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags

from structural_analysis.solvers.sparse_inertia import (
    SparseInertiaBudget,
    SparseInertiaBudgetExceeded,
    SparseInertiaError,
    compute_sparse_inertia,
    count_sparse_generalized_eigenvalues,
)


def matrix(n, entries):
    rows = [[] for _ in range(n)]
    for i, j, value in entries:
        rows[i].append((j, value))
    data, indices, pointers = [], [], [0]
    for row in rows:
        for j, value in sorted(row):
            indices.append(j)
            data.append(value)
        pointers.append(len(data))
    return csr_matrix(
        (np.asarray(data, dtype=np.float64), indices, pointers), shape=(n, n)
    )


def path(lengths):
    n = sum(lengths)
    entries = {}
    offset = 0
    for length in lengths:
        for i in range(offset, offset + length - 1):
            for a, b, value in [
                (i, i, 1),
                (i + 1, i + 1, 1),
                (i, i + 1, -1),
                (i + 1, i, -1),
            ]:
                entries[a, b] = entries.get((a, b), 0) + value
        offset += length
    return matrix(n, [(i, j, value) for (i, j), value in entries.items()])


def counts(result):
    return result.negative, result.zero, result.positive


def test_path_component_nullity_is_exact_and_input_is_unmodified():
    stiffness = path([4, 5, 7])
    original = tuple(
        x.tobytes() for x in (stiffness.data, stiffness.indices, stiffness.indptr)
    )
    result = compute_sparse_inertia(stiffness)
    # An incidence B of three paths has rank n-3; K=B^T B.
    assert counts(result) == (0, 3, 13)
    assert result.statistics.completed_inertia_calls == 1
    assert result.statistics.current_stored_entries == 0
    assert (
        tuple(
            x.tobytes() for x in (stiffness.data, stiffness.indices, stiffness.indptr)
        )
        == original
    )


def test_rank_one_outer_product_has_two_exact_zeros():
    vector = [1, 2, 3]
    result = compute_sparse_inertia(
        matrix(
            3,
            [(i, j, a * b) for i, a in enumerate(vector) for j, b in enumerate(vector)],
        )
    )
    assert counts(result) == (0, 2, 1)


@pytest.mark.parametrize("c", [0, 3, -5])
def test_zero_diagonal_two_by_two_pivot_counts_both_signs(c):
    # det([[0,1],[1,c]])=-1, independently of c.
    result = compute_sparse_inertia(matrix(2, [(0, 1, 1), (1, 0, 1), (1, 1, c)]))
    assert counts(result) == (1, 0, 1)
    assert result.statistics.two_by_two_pivots == 1


def test_two_by_two_schur_update_preserves_remaining_zero():
    # [[0,1,2],[1,0,3],[2,3,12]] has a congruent final Schur value12-12=0.
    result = compute_sparse_inertia(
        matrix(
            3,
            [
                (0, 1, 1),
                (1, 0, 1),
                (0, 2, 2),
                (2, 0, 2),
                (1, 2, 3),
                (2, 1, 3),
                (2, 2, 12),
            ],
        )
    )
    assert counts(result) == (1, 1, 1)
    assert result.statistics.peak_workspace_entries >= 4
    assert result.statistics.current_workspace_entries == 0
    assert result.statistics.current_workspace_bits == 0


@pytest.mark.parametrize(
    "shift,expected", [(0, (0, 1, 3)), (2, (1, 2, 1)), (3, (3, 0, 1)), (5, (3, 1, 0))]
)
def test_strict_inclusive_shift_counts_and_exact_singular_endpoints(shift, expected):
    mass = diags([1.0, 2.0, 3.0, 4.0], format="csr")
    stiffness = diags([0.0, 4.0, 6.0, 20.0], format="csr")
    result = count_sparse_generalized_eigenvalues(stiffness, mass, shift=shift)
    assert counts(result) == expected
    assert result.less_than_shift == expected[0]
    assert result.equal_to_shift == expected[1]
    assert result.less_than_or_equal_to_shift == sum(expected[:2])
    assert counts(result.mass_inertia) == (0, 0, 4)
    assert result.statistics.completed_inertia_calls == 2


def test_general_sparse_congruence_has_known_spectrum_under_permutation():
    # Q=[[1,1,0],[0,1,1],[0,0,1]], K=Q^T diag(0,2,2) Q, M=Q^T Q.
    stiffness = matrix(3, [(1, 1, 2), (1, 2, 2), (2, 1, 2), (2, 2, 4)])
    mass = matrix(
        3, [(0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 2), (1, 2, 1), (2, 1, 1), (2, 2, 2)]
    )
    perm = [2, 0, 1]
    for k, m in [(stiffness, mass), (stiffness[perm][:, perm], mass[perm][:, perm])]:
        assert counts(count_sparse_generalized_eigenvalues(k, m, shift=2)) == (1, 2, 0)
        assert counts(
            count_sparse_generalized_eigenvalues(k, m, shift=Fraction(3, 2))
        ) == (1, 0, 2)


def test_exact_expression_does_not_round_shift_product_before_subtraction():
    # Binary64(0.1)*10 rounds to1 in floating arithmetic, but exact product>1.
    stiffness = diags([1.0], format="csr")
    mass = diags([0.1], format="csr")
    result = count_sparse_generalized_eigenvalues(stiffness, mass, shift=10)
    assert counts(result) == (1, 0, 0)
    exact_endpoint = Fraction(1) / Fraction.from_float(0.1)
    assert counts(
        count_sparse_generalized_eigenvalues(stiffness, mass, shift=exact_endpoint)
    ) == (0, 1, 0)


def test_explicit_signed_zeros_and_represented_subnormal_keep_exact_signs():
    tiny = np.nextafter(0.0, 1.0)
    result = compute_sparse_inertia(diags([-tiny, -0.0, 0.0, tiny], format="csr"))
    assert counts(result) == (1, 2, 1)


def test_duplicate_entries_are_summed_as_exact_stored_values():
    # 1e16+1-1e16 is mathematically1, not a floating summed zero.
    data = csr_matrix(
        (np.array([1e16, 1.0, -1e16]), np.array([0, 0, 0]), np.array([0, 3])),
        shape=(1, 1),
    )
    assert counts(compute_sparse_inertia(data)) == (0, 0, 1)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, "2"])
def test_invalid_shift_is_rejected(invalid):
    identity = diags([1.0, 1.0], format="csr")
    with pytest.raises(SparseInertiaError, match="shift"):
        count_sparse_generalized_eigenvalues(identity, identity, shift=invalid)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_spd_mass_has_no_generalized_count_authority(bad):
    identity = diags([1.0, 1.0], format="csr")
    with pytest.raises(
        SparseInertiaError, match="mass must be exactly positive definite"
    ):
        count_sparse_generalized_eigenvalues(
            identity, diags([1.0, bad], format="csr"), shift=0
        )


def test_invalid_storage_shape_dtype_symmetry_and_finite_data():
    with pytest.raises(SparseInertiaError, match="CSR"):
        compute_sparse_inertia([[1.0]])
    with pytest.raises(SparseInertiaError, match="square"):
        compute_sparse_inertia(csr_matrix((2, 3), dtype=np.float64))
    with pytest.raises(SparseInertiaError, match="nonempty"):
        compute_sparse_inertia(csr_matrix((0, 0), dtype=np.float64))
    with pytest.raises(SparseInertiaError, match="binary64"):
        compute_sparse_inertia(diags([1, 2], dtype=np.int64, format="csr"))
    with pytest.raises(SparseInertiaError, match="symmetric"):
        compute_sparse_inertia(matrix(2, [(0, 1, 1)]))
    with pytest.raises(SparseInertiaError, match="finite"):
        compute_sparse_inertia(diags([1.0, np.nan], format="csr"))
    malformed = diags([1.0, 2.0], format="csr")
    malformed.indices[0] = 5
    with pytest.raises(SparseInertiaError, match="index"):
        compute_sparse_inertia(malformed)
    with pytest.raises(SparseInertiaError, match="same shape"):
        count_sparse_generalized_eigenvalues(
            diags([1.0], format="csr"), diags([1.0, 1.0], format="csr"), shift=0
        )


@pytest.mark.parametrize(
    "field,limit",
    [
        ("maximum_dimension", 1),
        ("maximum_input_entries", 1),
        ("maximum_stored_entries", 1),
        ("maximum_coefficient_bits", 2),
        ("maximum_total_stored_bits", 2),
        ("maximum_work_units", 1),
        ("maximum_bit_operation_cost", 1),
        ("maximum_pivots", 1),
    ],
)
def test_actual_budget_exhaustion_preserves_partial_counters(field, limit):
    budget = replace(SparseInertiaBudget(), **{field: limit})
    with pytest.raises(SparseInertiaBudgetExceeded) as raised:
        compute_sparse_inertia(path([5]), budget=budget)
    assert raised.value.statistics is not None


def test_inertia_calls_share_one_budget_and_no_reset():
    identity = diags([1.0, 2.0], format="csr")
    with pytest.raises(
        SparseInertiaBudgetExceeded, match="inertia_call_attempts"
    ) as raised:
        count_sparse_generalized_eigenvalues(
            identity,
            identity,
            shift=0,
            budget=replace(SparseInertiaBudget(), maximum_inertia_calls=1),
        )
    assert raised.value.statistics.inertia_call_attempts == 2
    assert raised.value.statistics.completed_inertia_calls == 1


def test_actual_schur_fill_budget_is_checked_after_input_loading():
    # A star has10 entries; eliminating its center creates three leaf couplings.
    star = matrix(
        4,
        [
            (0, 0, 3),
            (1, 1, 1),
            (2, 2, 1),
            (3, 3, 1),
            (0, 1, -1),
            (1, 0, -1),
            (0, 2, -1),
            (2, 0, -1),
            (0, 3, -1),
            (3, 0, -1),
        ],
    )
    with pytest.raises(SparseInertiaBudgetExceeded, match="stored_entries") as raised:
        compute_sparse_inertia(
            star, budget=replace(SparseInertiaBudget(), maximum_stored_entries=10)
        )
    assert raised.value.statistics.pivot_attempts == 1


def test_budget_configuration_requires_positive_non_bool_integers():
    with pytest.raises(ValueError, match="maximum_pivots"):
        SparseInertiaBudget(maximum_pivots=False)


def test_retained_two_by_two_workspace_shares_the_storage_budget():
    data = matrix(
        3,
        [(0, 1, 1), (1, 0, 1), (0, 2, 2), (2, 0, 2), (1, 2, 3), (2, 1, 3), (2, 2, 12)],
    )
    # Seven input entries fit; two inverse-workspace entries consume the next
    # two slots, so retaining the first applied coefficient must refuse.
    with pytest.raises(SparseInertiaBudgetExceeded, match="stored_entries") as raised:
        compute_sparse_inertia(
            data, budget=replace(SparseInertiaBudget(), maximum_stored_entries=9)
        )
    assert raised.value.statistics.two_by_two_pivots == 1
    assert raised.value.statistics.current_workspace_entries == 2
    assert raised.value.statistics.peak_stored_entries == 9


@pytest.mark.parametrize("lengths", [[11, 17, 23, 29], [40, 40]])
def test_actual_consistent_mass_block_witness_nullity_is_globally_counted(lengths):
    # These are the two admitted block classes whose modal extraction missed
    # multiplicity. This test exercises only the independent count utility.
    n = sum(lengths)
    entries = {}
    offset = 0
    for length in lengths:
        for i in range(offset, offset + length - 1):
            for a, b, value in [
                (i, i, 2),
                (i + 1, i + 1, 2),
                (i, i + 1, 1),
                (i + 1, i, 1),
            ]:
                entries[a, b] = entries.get((a, b), 0) + value
        offset += length
    mass = matrix(n, [(i, j, value / 6) for (i, j), value in entries.items()])
    result = count_sparse_generalized_eigenvalues(path(lengths), mass, shift=0)
    assert counts(result) == (0, len(lengths), n - len(lengths))


def test_no_dense_or_numeric_eigen_or_lu_backend_is_used(monkeypatch):
    import scipy.linalg
    import scipy.sparse.linalg

    def forbidden(*args, **kwargs):
        raise AssertionError("numeric/dense backend is forbidden for exact inertia")

    monkeypatch.setattr(csr_matrix, "toarray", forbidden)
    monkeypatch.setattr(csr_matrix, "todense", forbidden)
    monkeypatch.setattr(scipy.linalg, "eigh", forbidden)
    monkeypatch.setattr(scipy.linalg, "ldl", forbidden)
    monkeypatch.setattr(scipy.sparse.linalg, "eigsh", forbidden)
    monkeypatch.setattr(scipy.sparse.linalg, "splu", forbidden)
    mass = diags([1.0, 2.0, 3.0, 4.0, 5.0], format="csr")
    original = tuple(x.tobytes() for x in (mass.data, mass.indices, mass.indptr))
    result = count_sparse_generalized_eigenvalues(path([5]), mass, shift=0)
    assert counts(result) == (0, 1, 4)
    assert (
        tuple(x.tobytes() for x in (mass.data, mass.indices, mass.indptr)) == original
    )
