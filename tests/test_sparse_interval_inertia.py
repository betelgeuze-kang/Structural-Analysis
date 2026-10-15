"""Independent analytical inertia and endpoint containment checks."""

from fractions import Fraction
import math
import sys

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags, eye

from structural_analysis.solvers import sparse_inertia as exact
from structural_analysis.solvers import sparse_interval_inertia as interval


def counts(result):
    return result.negative, result.zero, result.positive


def test_free_path_component_nullity_and_input_bytes_are_preserved():
    # Disconnected 3-node +4-node incidence graphs, nullity exactly2.
    k = diags(
        [-np.ones(6), [1, 2, 1, 1, 2, 2, 1], -np.ones(6)], [-1, 0, 1], format="csr"
    )
    k[2, 3] = 0
    k[3, 2] = 0
    before = tuple(x.tobytes() for x in (k.data, k.indices, k.indptr))
    result = interval.compute_sparse_interval_inertia(k)
    assert counts(result) == (0, 2, 5)
    assert result.algorithm_profile == interval.INTERVAL_SPARSE_INERTIA_PROFILE
    assert tuple(x.tobytes() for x in (k.data, k.indices, k.indptr)) == before
    assert result.statistics.current_stored_entries == 0


def test_rank_one_integer_outer_product_has_exact_two_zeros():
    v = np.array([1.0, 2.0, 3.0])
    assert counts(
        interval.compute_sparse_interval_inertia(csr_matrix(np.outer(v, v)))
    ) == (0, 2, 1)


@pytest.mark.parametrize("c", [0.0, 3.0, -5.0])
def test_certified_negative_two_by_two_determinant_has_one_each(c):
    # determinant -1 independent of c, not a numeric LU sign oracle.
    result = interval.compute_sparse_interval_inertia(
        csr_matrix([[0.0, 1.0], [1.0, c]])
    )
    assert counts(result) == (1, 0, 1)
    if c == 0:
        assert result.statistics.two_by_two_pivots == 1


def test_two_by_two_schur_workspace_is_charged_and_released():
    # Congruent to [[0,1],[1,0]] direct-sum[0]: final Schur12-12=0.
    # Choosing the definite diagonal12 first requires nonbinary1/12. The
    # singular remainder is not an exactzero interval; refusal is necessary.
    with pytest.raises(interval.SparseIntervalInertiaUncertain) as caught:
        interval.compute_sparse_interval_inertia(
            csr_matrix([[0.0, 1.0, 2.0], [1.0, 0.0, 3.0], [2.0, 3.0, 12.0]])
        )
    assert caught.value.statistics.completed_inertia_calls == 0
    assert caught.value.statistics.zero_dimensions == 0
    # A second matrix forces2x2 elimination and an exactlyzero final Schur.
    other = interval.compute_sparse_interval_inertia(
        csr_matrix([[0.0, 1.0, 2.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    )
    assert counts(other) == (1, 1, 1)
    assert other.statistics.two_by_two_pivots == 1
    assert other.statistics.peak_workspace_entries > 0
    assert other.statistics.current_workspace_entries == 0
    assert other.statistics.current_workspace_bits == 0


@pytest.mark.parametrize("perm", [[0, 1, 2, 3], [3, 1, 0, 2], [2, 0, 3, 1]])
def test_dyadic_congruence_mixed_sign_and_nullity_under_fixed_permutation(perm):
    # Invertible unit-upper Q, Sylvester inertia of Q^T diag(-2,0,4,8) Q.
    q = csr_matrix(
        [
            [1.0, 0.5, 0.0, 0.0],
            [0.0, 1.0, 0.5, 0.0],
            [0.0, 0.0, 1.0, 0.5],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    k = (q.T @ diags([-2.0, 0.0, 4.0, 8.0], format="csr") @ q).tocsr()
    result = interval.compute_sparse_interval_inertia(k[perm][:, perm])
    assert counts(result) == (1, 1, 2)


@pytest.mark.parametrize(
    "shift,expected", [(0, (0, 1, 3)), (2, (1, 2, 1)), (3, (3, 0, 1)), (5, (3, 1, 0))]
)
def test_complete_strict_inclusive_generalized_counts_with_spd_mass(shift, expected):
    k = diags([0.0, 4.0, 6.0, 20.0], format="csr")
    m = diags([1.0, 2.0, 3.0, 4.0], format="csr")
    result = interval.count_sparse_interval_generalized_eigenvalues(k, m, shift=shift)
    assert counts(result) == expected
    assert result.less_than_shift == expected[0]
    assert result.less_than_or_equal_to_shift == sum(expected[:2])
    assert counts(result.mass_inertia) == (0, 0, 4)
    assert (
        result.statistics.inertia_call_attempts
        == result.statistics.completed_inertia_calls
        == 2
    )


def test_exact_original_shift_expression_does_not_use_float_subtraction():
    # Float10*.1 rounds to1; exact binary64 .1 times10 exceeds1.
    result = interval.count_sparse_interval_generalized_eigenvalues(
        diags([1.0], format="csr"), diags([0.1], format="csr"), shift=10
    )
    assert counts(result) == (1, 0, 0)
    endpoint = 1 / Fraction.from_float(0.1)
    result = interval.count_sparse_interval_generalized_eigenvalues(
        diags([1.0], format="csr"), diags([0.1], format="csr"), shift=endpoint
    )
    assert counts(result) == (0, 1, 0)


def test_input_hash_is_compatible_but_filter_profile_is_distinct():
    k = diags([-1.0, 0.0, 2.0], format="csr")
    a = exact.compute_sparse_inertia(k)
    b = interval.compute_sparse_interval_inertia(k)
    assert a.input_hash == b.input_hash
    assert a.algorithm_profile != b.algorithm_profile


def test_duplicate_exact_sum_and_signed_zero_hash_preserve_storage_identity():
    k = csr_matrix(
        (np.array([1e16, 1.0, -1e16]), np.array([0, 0, 0]), np.array([0, 3])),
        shape=(1, 1),
    )
    assert counts(interval.compute_sparse_interval_inertia(k)) == (0, 0, 1)
    a = interval.compute_sparse_interval_inertia(
        csr_matrix((np.array([0.0]), np.array([0]), np.array([0, 1])), shape=(1, 1))
    )
    b = interval.compute_sparse_interval_inertia(
        csr_matrix((np.array([-0.0]), np.array([0]), np.array([0, 1])), shape=(1, 1))
    )
    assert counts(a) == counts(b) == (0, 1, 0)
    assert a.input_hash != b.input_hash


def test_represented_subnormals_preserve_sign_but_unrepresented_shift_is_uncertain():
    tiny = math.nextafter(0.0, 1.0)
    assert counts(
        interval.compute_sparse_interval_inertia(
            diags([-tiny, -0.0, 0.0, tiny], format="csr")
        )
    ) == (1, 2, 1)
    with pytest.raises(
        interval.SparseIntervalInertiaUncertain, match="zero is unproved"
    ) as caught:
        interval.count_sparse_interval_generalized_eigenvalues(
            diags([tiny], format="csr"),
            eye(1, format="csr"),
            shift=Fraction(2, 3) * Fraction.from_float(tiny),
        )
    assert caught.value.statistics.completed_inertia_calls == 1


def test_near_singular_interval_does_not_invent_a_zero():
    # Exact .09 - exact .3^2 is positive, but rounded Schur bounds overlap0.
    assert Fraction.from_float(0.09) - Fraction.from_float(0.3) ** 2 > 0
    with pytest.raises(
        interval.SparseIntervalInertiaUncertain, match="zero is unproved"
    ) as caught:
        interval.compute_sparse_interval_inertia(csr_matrix([[1.0, 0.3], [0.3, 0.09]]))
    assert caught.value.statistics.completed_inertia_calls == 0
    assert caught.value.statistics.zero_dimensions == 0


def test_outward_endpoint_enclosure_underflow_cancellation_and_overflow():
    ops = interval._IntervalOps(exact._Ledger(exact.SparseInertiaBudget()))
    tiny = Fraction.from_float(math.nextafter(0.0, 1.0))
    for value in [Fraction(1, 3), Fraction(-1, 3), tiny / 3, -tiny / 3, Fraction(0)]:
        box = ops.enclose(value)
        assert Fraction.from_float(box.lower) <= value <= Fraction.from_float(box.upper)
    box = ops.subtract(
        interval.Binary64Interval(0.1, 0.1), interval.Binary64Interval(0.1, 0.1)
    )
    assert box.exact_zero
    with pytest.raises(interval.SparseIntervalInertiaUncertain, match="overflow"):
        ops.enclose(Fraction.from_float(sys.float_info.max) * 3)
    with pytest.raises(interval.SparseIntervalInertiaUncertain, match="overflow"):
        interval.count_sparse_interval_generalized_eigenvalues(
            diags([sys.float_info.max], format="csr"),
            diags([sys.float_info.max], format="csr"),
            shift=-2,
        )


@pytest.mark.parametrize(
    "a,b",
    [
        ((-0.3, 0.1), (0.2, 1.0)),
        ((-2.0, -0.5), (-0.3, -0.1)),
        ((0.0, 0.0), (-1.0, 2.0)),
        ((1.0, 2.0), (3.0, 4.0)),
    ],
)
def test_operation_enclosures_contain_all_exact_endpoint_extrema(a, b):
    ops = interval._IntervalOps(exact._Ledger(exact.SparseInertiaBudget()))
    x = interval.Binary64Interval(*a)
    y = interval.Binary64Interval(*b)
    af = [Fraction.from_float(z) for z in a]
    bf = [Fraction.from_float(z) for z in b]
    candidates = [
        (ops.add(x, y), [u + v for u in af for v in bf]),
        (ops.subtract(x, y), [u - v for u in af for v in bf]),
        (ops.multiply(x, y), [u * v for u in af for v in bf]),
    ]
    if not b[0] <= 0 <= b[1]:
        candidates.append((ops.divide(x, y), [u / v for u in af for v in bf]))
    candidates.append(
        (
            ops.square(x),
            [u * u for u in af] + ([Fraction(0)] if a[0] <= 0 <= a[1] else []),
        )
    )
    for box, values in candidates:
        assert Fraction.from_float(box.lower) <= min(values)
        assert Fraction.from_float(box.upper) >= max(values)


@pytest.mark.parametrize(
    "budget",
    [
        exact.SparseInertiaBudget(maximum_work_units=1),
        exact.SparseInertiaBudget(maximum_bit_operation_cost=1),
        exact.SparseInertiaBudget(maximum_stored_entries=1),
        exact.SparseInertiaBudget(maximum_total_stored_bits=1),
        exact.SparseInertiaBudget(maximum_pivots=1),
    ],
)
def test_real_budget_refusal_has_partial_spend(budget):
    with pytest.raises(interval.SparseIntervalInertiaBudgetExceeded) as caught:
        interval.compute_sparse_interval_inertia(
            diags([1.0, 2.0, 3.0], format="csr"), budget=budget
        )
    assert caught.value.statistics is not None


def test_same_ledger_spend_survives_between_mass_and_pencil_stages():
    with pytest.raises(interval.SparseIntervalInertiaBudgetExceeded) as caught:
        interval.count_sparse_interval_generalized_eigenvalues(
            diags([1.0, 2.0, 3.0], format="csr"),
            eye(3, format="csr"),
            shift=0,
            budget=exact.SparseInertiaBudget(maximum_inertia_calls=1),
        )
    stats = caught.value.statistics
    assert stats.completed_inertia_calls == 1
    assert stats.inertia_call_attempts == 2
    assert stats.work_units > 0 and stats.bit_operation_cost > 0


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_spd_mass_cannot_grant_generalized_count(bad):
    with pytest.raises(interval.SparseIntervalInertiaError, match="positive definite"):
        interval.count_sparse_interval_generalized_eigenvalues(
            eye(3, format="csr"), diags([bad, 1.0, 1.0], format="csr"), shift=0
        )


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), "1"])
def test_invalid_shift_is_rejected(bad):
    with pytest.raises(interval.SparseIntervalInertiaError, match="shift"):
        interval.count_sparse_interval_generalized_eigenvalues(
            eye(3, format="csr"), eye(3, format="csr"), shift=bad
        )


def test_exact_symmetry_validation_precedes_interval_projection():
    with pytest.raises(interval.SparseIntervalInertiaError, match="exactly symmetric"):
        interval.compute_sparse_interval_inertia(csr_matrix([[1.0, 1e-18], [0.0, 1.0]]))
    with pytest.raises(interval.SparseIntervalInertiaError, match="binary64"):
        interval.compute_sparse_interval_inertia(eye(3, format="csr", dtype=np.float32))
