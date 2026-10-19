"""Source custody and independent analytical counts, not extraction acceptance."""

from dataclasses import replace
from fractions import Fraction
import math

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags, eye

from structural_analysis.solvers.sparse_cached_interval_pencil import (
    CACHED_INTERVAL_PENCIL_PROFILE,
    SparseCachedIntervalPencil,
    SparseCachedIntervalPencilBudget,
    SparseCachedIntervalPencilBudgetExceeded,
    SparseCachedIntervalPencilError,
    SparseCachedIntervalPencilUncertain,
)
from structural_analysis.solvers.sparse_inertia import SparseInertiaBudget


def triple(result):
    return result.negative, result.zero, result.positive


def matrices():
    return diags([0.0, 4.0, 6.0, 20.0], format="csr"), diags(
        [1.0, 2.0, 3.0, 4.0], format="csr"
    )


@pytest.mark.parametrize(
    "shift,expected", [(0, (0, 1, 3)), (2, (1, 2, 1)), (3, (3, 0, 1)), (5, (3, 1, 0))]
)
def test_diagonal_analytic_strict_and_inclusive_counts(shift, expected):
    k, m = matrices()
    session = SparseCachedIntervalPencil(k, m)
    result = session.count(shift)
    assert triple(result) == expected
    assert result.less_than_shift == expected[0]
    assert result.equal_to_shift == expected[1]
    assert result.less_than_or_equal_to_shift == sum(expected[:2])
    assert result.algorithm_profile == CACHED_INTERVAL_PENCIL_PROFILE
    assert triple(result.mass_inertia) == (0, 0, 4)
    assert result.statistics.inertia_call_attempts == 2
    assert not result.custody.external_or_durable_authority_verified
    assert not result.custody.caller_numerical_admission_verified
    session.close()
    assert session.statistics.inertia.current_stored_entries == 0


def test_one_mass_proof_and_first_query_additive_accounting():
    k, m = matrices()
    session = SparseCachedIntervalPencil(k, m)
    construction = session.constructor_statistics
    assert construction.inertia_call_attempts == 1
    assert construction.current_stored_entries > 0
    first = session.count(Fraction(1))
    second = session.count(Fraction(3))
    assert first.statistics.input_entries == len(k.data) + len(m.data)
    assert second.statistics.input_entries == 0
    assert first.statistics.inertia_call_attempts == 2
    assert second.statistics.inertia_call_attempts == 1
    assert second.cumulative_statistics.mass_proof_reuse_count == 2
    for name in (
        "work_units",
        "bit_operation_cost",
        "pivot_attempts",
        "input_entries",
        "inertia_call_attempts",
    ):
        assert getattr(first.statistics, name) + getattr(
            second.statistics, name
        ) == getattr(session.statistics.inertia, name)
    spent = session.statistics.inertia.bit_operation_cost
    cleanup = session.close()
    assert cleanup.bit_operation_cost == 0
    assert session.close().work_units == 0
    assert session.statistics.inertia.bit_operation_cost == spent


@pytest.mark.parametrize("perm", [[0, 1], [1, 0]])
def test_general_nondiagonal_non_dd_spd_mass_remains_admitted(perm):
    # det M=1 and M11>0 proves SPD; not diagonally dominant. K=M,
    # hence every generalized eigenvalue is exactly1, independently of solver.
    m = csr_matrix([[1.0, 2.0], [2.0, 5.0]])[perm][:, perm]
    session = SparseCachedIntervalPencil(m, m)
    assert session.exact_mass_lower_bound_hint is None
    assert triple(session.count(1)) == (0, 2, 0)
    assert triple(session.count(2)) == (2, 0, 0)
    session.close()


def test_source_snapshot_immutable_after_caller_mutations():
    k, m = matrices()
    original = (k.data.tobytes(), m.data.tobytes())
    session = SparseCachedIntervalPencil(k, m)
    assert original == (k.data.tobytes(), m.data.tobytes())
    custody = session.custody
    k.data[:] = 1000
    m.data[:] = -1000
    result = session.count(2)
    assert triple(result) == (1, 2, 1)
    assert result.custody == custody
    assert result.stiffness_input_hash == custody.stiffness_input_hash
    assert result.mass_input_hash == custody.mass_input_hash
    session.close()


def test_initial_shift_uses_exact_binary64_expression():
    # Exact stored .1 times10 exceeds1, though float multiplication is1.
    session = SparseCachedIntervalPencil(
        diags([1.0], format="csr"), diags([0.1], format="csr")
    )
    assert triple(session.count(10)) == (1, 0, 0)
    session.close()


def test_uncertain_work_stays_spent_then_different_shift_can_succeed():
    k = csr_matrix([[0.0, 1.0, 2.0], [1.0, 0.0, 3.0], [2.0, 3.0, 12.0]])
    session = SparseCachedIntervalPencil(k, eye(3, format="csr"))
    retained = session.constructor_statistics.current_stored_entries
    with pytest.raises(SparseCachedIntervalPencilUncertain) as caught:
        session.count(0)
    partial = caught.value.statistics
    assert partial.work_units > 0 and partial.inertia_call_attempts == 2
    assert not session.statistics.sealed
    assert session.statistics.inertia.current_stored_entries == retained
    assert (
        session.statistics.inertia.current_workspace_entries == 1
    )  # persistent Gershgorin hint
    result = session.count(
        20
    )  # each eigenvalue<20 by independent row absolute bound<=17
    assert triple(result) == (3, 0, 0)
    assert result.statistics.inertia_call_attempts == 1
    assert session.statistics.uncertain_provider_calls == 1
    assert (
        partial.bit_operation_cost + result.statistics.bit_operation_cost
        == session.statistics.inertia.bit_operation_cost
    )
    session.close()


def test_two_by_two_workspace_and_cache_charged_then_released():
    # Exact congruence inertia of [[0,1],[1,0]] directsum[0].
    k = csr_matrix([[0.0, 1.0, 2.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    session = SparseCachedIntervalPencil(k, eye(3, format="csr"))
    result = session.count(0)
    assert triple(result) == (1, 1, 1)
    assert result.statistics.two_by_two_pivots == 1
    assert (
        result.statistics.peak_workspace_entries
        > result.statistics.current_workspace_entries
    )
    assert (
        result.statistics.peak_stored_entries
        > session.constructor_statistics.current_stored_entries
    )
    session.close()
    assert session.statistics.inertia.current_stored_entries == 0
    assert session.statistics.inertia.current_workspace_entries == 0


def test_gershgorin_strict_hint_is_exact_and_not_a_fresh_count():
    m = csr_matrix([[4.0, -1.0], [-1.0, 3.0]])
    session = SparseCachedIntervalPencil(m, m)
    assert session.exact_mass_lower_bound_hint == Fraction(1)
    assert session.constructor_statistics.inertia_call_attempts == 1
    assert not session.custody.caller_numerical_admission_verified
    session.close()


@pytest.mark.parametrize(
    "name,value",
    [
        ("maximum_work_units", 1),
        ("maximum_bit_operation_cost", 1),
        ("maximum_inertia_calls", 1),
        ("maximum_stored_entries", 1),
        ("maximum_coefficient_bits", 1),
        ("maximum_input_entries", 1),
    ],
)
def test_stricter_first_query_refusal_seals_and_releases_cache(name, value):
    k, m = matrices()
    session = SparseCachedIntervalPencil(k, m)
    with pytest.raises(SparseCachedIntervalPencilBudgetExceeded) as caught:
        session.count(2, budget=replace(SparseInertiaBudget(), **{name: value}))
    assert (
        caught.value.statistics.work_units > 0
    )  # includes construction, never refunded
    assert caught.value.cumulative_statistics.sealed
    assert session.statistics.inertia.current_stored_entries == 0
    assert session.statistics.inertia.current_workspace_entries == 0
    spent = session.statistics.inertia.bit_operation_cost
    with pytest.raises(SparseCachedIntervalPencilError):
        session.count(3)
    assert session.statistics.inertia.bit_operation_cost == spent


def test_second_query_local_cap_does_not_reset_aggregate_spend():
    session = SparseCachedIntervalPencil(*matrices())
    first = session.count(1)
    with pytest.raises(SparseCachedIntervalPencilBudgetExceeded) as caught:
        session.count(
            3, budget=replace(SparseInertiaBudget(), maximum_bit_operation_cost=1)
        )
    delta = caught.value.statistics
    assert delta.bit_operation_cost > 1  # refusing operation is charged, not clipped
    assert (
        session.statistics.inertia.bit_operation_cost
        == first.statistics.bit_operation_cost + delta.bit_operation_cost
    )
    assert session.statistics.sealed and session.statistics.closed


@pytest.mark.parametrize(
    "cap_name,cap_value",
    [("maximum_provider_calls", 1), ("maximum_aggregate_inertia_calls", 2)],
)
def test_global_call_limits_do_not_reset_between_queries(cap_name, cap_value):
    session = SparseCachedIntervalPencil(
        *matrices(),
        budget=replace(SparseCachedIntervalPencilBudget(), **{cap_name: cap_value}),
    )
    first = session.count(1)
    with pytest.raises(SparseCachedIntervalPencilBudgetExceeded) as caught:
        session.count(3)
    assert caught.value.cumulative_statistics.provider_call_attempts == 2
    assert (
        session.statistics.inertia.bit_operation_cost
        >= first.statistics.bit_operation_cost
    )
    assert session.statistics.sealed


def test_constructor_failure_keeps_cost_and_rejects_indefinite_mass():
    with pytest.raises(SparseCachedIntervalPencilError) as caught:
        SparseCachedIntervalPencil(
            eye(2, format="csr"), csr_matrix([[0.0, 1.0], [1.0, 0.0]])
        )
    assert caught.value.statistics.input_entries == 4
    assert caught.value.statistics.inertia_call_attempts == 1
    assert caught.value.statistics.two_by_two_pivots == 1
    assert caught.value.cumulative_statistics.closed
    assert caught.value.cumulative_statistics.inertia.current_stored_entries == 0


def test_close_without_query_returns_unreported_constructor_cost_once():
    session = SparseCachedIntervalPencil(*matrices())
    spent = session.constructor_statistics
    final = session.close()
    assert final.work_units == spent.work_units
    assert final.input_entries == spent.input_entries
    assert final.inertia_call_attempts == 1
    assert session.close().input_entries == 0
    assert session.exact_mass_lower_bound_hint is None


@pytest.mark.parametrize("shift", [True, float("nan"), float("inf"), "1"])
def test_invalid_shift_has_no_count_but_retains_constructor_cost(shift):
    session = SparseCachedIntervalPencil(*matrices())
    with pytest.raises(SparseCachedIntervalPencilError) as caught:
        session.count(shift)
    assert caught.value.statistics.inertia_call_attempts == 1
    assert session.statistics.provider_calls_completed == 0
    session.close()


@pytest.mark.parametrize(
    "kind", ["asymmetric", "nonfinite", "shape", "dense", "float32"]
)
def test_invalid_original_input_fails_closed(kind):
    k, m = matrices()
    if kind == "asymmetric":
        k = csr_matrix([[1.0, 1.0], [0.0, 1.0]])
        m = eye(2, format="csr")
    elif kind == "nonfinite":
        k.data[0] = math.nan
    elif kind == "shape":
        m = eye(3, format="csr")
    elif kind == "dense":
        k = np.eye(4)
    else:
        k = k.astype(np.float32)
    with pytest.raises(SparseCachedIntervalPencilError):
        SparseCachedIntervalPencil(k, m)


def test_default_caps_cannot_be_increased_by_prototype():
    with pytest.raises(ValueError, match="cannot raise"):
        SparseCachedIntervalPencilBudget(
            provider_budget=replace(
                SparseInertiaBudget(), maximum_bit_operation_cost=1_000_000_001
            )
        )
    with pytest.raises(ValueError):
        SparseCachedIntervalPencilBudget(maximum_provider_calls=257)


def test_global_bit_cap_is_enforced_after_success_without_reset():
    # K=0,M=1: first count at0 exactzero, second at1 exactnegative.
    # Small fixed global cap admits construction+first count and refuses the
    # second arithmetic operation; per-query providercap remains1e9.
    session = SparseCachedIntervalPencil(
        diags([0.0], format="csr"),
        eye(1, format="csr"),
        budget=SparseCachedIntervalPencilBudget(
            maximum_aggregate_bit_operation_cost=60
        ),
    )
    first = session.count(0)
    assert triple(first) == (0, 1, 0)
    with pytest.raises(SparseCachedIntervalPencilBudgetExceeded) as caught:
        session.count(1)
    assert caught.value.cumulative_statistics.inertia.bit_operation_cost > 60
    assert (
        first.statistics.bit_operation_cost + caught.value.statistics.bit_operation_cost
        == session.statistics.inertia.bit_operation_cost
    )
    assert session.statistics.inertia.current_stored_entries == 0


def test_malformed_pointers_refused_before_csr_copy(monkeypatch):
    k = eye(2, format="csr")
    k.indptr[-1] += 1
    monkeypatch.setattr(k, "copy", lambda: pytest.fail("invalid storage copied"))
    with pytest.raises(SparseCachedIntervalPencilError, match="before snapshot"):
        SparseCachedIntervalPencil(k, eye(2, format="csr"))


@pytest.mark.parametrize(
    "name,left,right",
    [
        ("add", 0.1, 0.2),
        ("subtract", 0.1, 1.0),
        ("multiply", -0.1, 0.2),
        ("divide", 1.0, 3.0),
        ("square", -0.1, None),
        ("multiply", math.ulp(0.0), 0.5),
    ],
)
def test_point_arithmetic_encloses_exact_result_with_one_charged_operation(
    name, left, right
):
    from structural_analysis.solvers import sparse_cached_interval_pencil as cached
    from structural_analysis.solvers import sparse_inertia as exact
    from structural_analysis.solvers import sparse_interval_inertia as interval

    ledger = exact._Ledger(SparseInertiaBudget())
    ops = cached._DistinctEndpointOps(ledger)
    a = interval.Binary64Interval(left, left)
    b = None if right is None else interval.Binary64Interval(right, right)
    x = Fraction.from_float(left)
    y = x if right is None else Fraction.from_float(right)
    expected = {
        "add": lambda: x + y,
        "subtract": lambda: x - y,
        "multiply": lambda: x * y,
        "divide": lambda: x / y,
        "square": lambda: x * x,
    }[name]()
    result = getattr(ops, name)(a) if b is None else getattr(ops, name)(a, b)

    assert Fraction.from_float(result.lower) <= expected
    assert expected <= Fraction.from_float(result.upper)
    # An inexact point result must remain an outward interval, not round to
    # one binary64 value merely because both operands were points.
    assert result.lower < result.upper
    statistics = ledger.snapshot()
    assert statistics.fraction_operation_attempts == 1
    operand_bits = sum(
        abs(value.numerator).bit_length() + value.denominator.bit_length()
        for value in (x, y)
    )
    assert statistics.bit_operation_cost == operand_bits**2


@pytest.mark.parametrize("name", ["multiply", "divide"])
@pytest.mark.parametrize("point_on_left", [True, False])
@pytest.mark.parametrize("sign", [-1.0, 1.0])
def test_single_point_endpoint_keeps_the_full_other_interval(name, point_on_left, sign):
    from structural_analysis.solvers import sparse_cached_interval_pencil as cached
    from structural_analysis.solvers import sparse_inertia as exact
    from structural_analysis.solvers import sparse_interval_inertia as interval

    point = interval.Binary64Interval(0.1 * sign, 0.1 * sign)
    wide = interval.Binary64Interval(-3.0, -1.0)
    a, b = (point, wide) if point_on_left else (wide, point)
    ledger = exact._Ledger(SparseInertiaBudget())
    result = getattr(cached._DistinctEndpointOps(ledger), name)(a, b)
    reference = getattr(
        interval._IntervalOps(exact._Ledger(SparseInertiaBudget())), name
    )(a, b)
    assert result == reference
    assert ledger.snapshot().fraction_operation_attempts == 2


def test_distinct_endpoint_arithmetic_keeps_zero_and_overflow_refusals():
    from structural_analysis.solvers import sparse_cached_interval_pencil as cached
    from structural_analysis.solvers import sparse_inertia as exact
    from structural_analysis.solvers import sparse_interval_inertia as interval

    ledger = exact._Ledger(SparseInertiaBudget())
    ops = cached._DistinctEndpointOps(ledger)
    one = interval.Binary64Interval(1.0, 1.0)
    with pytest.raises(interval.SparseIntervalInertiaUncertain, match="includes zero"):
        ops.divide(one, interval.Binary64Interval(-1.0, 1.0))
    assert ledger.snapshot().fraction_operation_attempts == 0
    tiny = interval.Binary64Interval(math.ulp(0.0), math.ulp(0.0))
    with pytest.raises(interval.SparseIntervalInertiaUncertain, match="overflow"):
        ops.divide(one, tiny)
    assert ledger.snapshot().fraction_operation_attempts == 1
    assert ledger.snapshot().bit_operation_cost > 0


def test_distinct_endpoint_budget_refusal_keeps_the_attempted_charge():
    from structural_analysis.solvers import sparse_cached_interval_pencil as cached
    from structural_analysis.solvers import sparse_inertia as exact
    from structural_analysis.solvers import sparse_interval_inertia as interval

    ledger = exact._Ledger(SparseInertiaBudget(maximum_bit_operation_cost=1))
    ops = cached._DistinctEndpointOps(ledger)
    point = interval.Binary64Interval(0.1, 0.1)
    with pytest.raises(exact.SparseInertiaBudgetExceeded):
        ops.multiply(point, point)
    assert ledger.snapshot().fraction_operation_attempts == 1
    assert ledger.snapshot().bit_operation_cost > 1
