"""Analytical global-rank tests, with no numerical eigenvalue oracle."""

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction

import numpy as np
import pytest
from scipy.sparse import block_diag, csr_matrix, diags, eye

from structural_analysis.solvers import sparse_modal_certificate as certificate
from structural_analysis.solvers.sparse_inertia import SparseInertiaBudget
from structural_analysis.solvers.sparse_modal_certificate import (
    SparseModalCertificateBudget,
    SparseModalCertificateBudgetExceeded,
    SparseModalCertificateError,
    certify_sparse_modal_spectrum,
)


def congruence(values):
    """Unit upper triangular integer Q: (Q^T D Q,Q^T Q) has spectrum D."""
    n = len(values)
    q = eye(n, format="csr") + diags(np.ones(n - 1), 1, shape=(n, n), format="csr")
    return (q.T @ diags(values, format="csr") @ q).tocsr(), (q.T @ q).tocsr()


def assert_encloses(interval, value):
    assert interval.lower <= value <= interval.upper


def path_three_consistent():
    # Integer six-times consistent element mass. Characteristic eigenvalues
    # of these assembled 3-node free bars are exactly 0,1/2,2.
    return (
        csr_matrix([[1.0, -1.0, 0.0], [-1.0, 2.0, -1.0], [0.0, -1.0, 1.0]]),
        csr_matrix([[2.0, 1.0, 0.0], [1.0, 4.0, 1.0], [0.0, 1.0, 2.0]]),
    )


def test_coupled_congruence_certifies_global_ranks_and_nearest_guards():
    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    before = tuple(a.tobytes() for x in (k, m) for a in (x.data, x.indices, x.indptr))
    result = certify_sparse_modal_spectrum(k, m, mode_count=2)
    assert result.rigid_mode_count == 1
    assert result.largest.lower == result.largest.upper == 8
    for interval, value in zip(result.positive_intervals, [1, 2, 5], strict=True):
        assert_encloses(interval, value)
    assert [x.multiplicity for x in result.selected_clusters] == [1, 1]
    for index, group in enumerate(result.selected_clusters):
        assert group.lower_guard.less == index + 1
        assert group.upper_guard.less_or_equal == index + 2
        assert group.preceding_guard.less_or_equal == index + 1
        assert group.following_guard.less == index + 2
        assert group.outside_gap_lower_bound > 0
    assert result.mass_lower_bound > 0
    assert result.mass_lower_bound_guard.less_or_equal == 0
    assert result.mass_bound_stiffness_input_hash == result.mass_input_hash
    assert not result.vectors_verified
    assert not result.caller_numerical_admission_verified
    assert before == tuple(
        a.tobytes() for x in (k, m) for a in (x.data, x.indices, x.indptr)
    )


def test_repeated_consistent_bar_cluster_and_component_nullity_are_complete():
    k0, m0 = path_three_consistent()
    k = block_diag([k0, k0], format="csr")
    m = block_diag([m0, m0], format="csr")
    result = certify_sparse_modal_spectrum(k, m, mode_count=2)
    assert result.rigid_mode_count == 2
    assert len(result.selected_clusters) == 1
    group = result.selected_clusters[0]
    assert_encloses(group, Fraction(1, 2))
    assert group.upper - group.lower <= Fraction(1, 1 << 40)
    assert group.multiplicity == 2
    assert group.lower_guard.less == 2
    assert group.upper_guard.less_or_equal == 4
    assert group.following_guard.less == 4
    assert_encloses(result.positive_intervals[2], Fraction(2))


def test_requested_boundary_cannot_cut_the_complete_repeated_space():
    k0, m0 = path_three_consistent()
    with pytest.raises(SparseModalCertificateError, match="cuts a repeated") as caught:
        certify_sparse_modal_spectrum(
            block_diag([k0, k0], format="csr"),
            block_diag([m0, m0], format="csr"),
            mode_count=1,
        )
    assert caught.value.statistics.provider_calls_completed > 0


def test_fixed_permutation_keeps_count_proof_for_coupled_nonuniform_mass():
    k, m = congruence([0.0, 0.0, 1.0, 1.0, 3.0, 7.0])
    perm = [4, 1, 5, 0, 3, 2]
    result = certify_sparse_modal_spectrum(
        k[perm][:, perm], m[perm][:, perm], mode_count=2
    )
    assert result.rigid_mode_count == 2
    assert result.selected_clusters[0].multiplicity == 2
    assert_encloses(result.selected_clusters[0], Fraction(1))


def test_irrational_free_path_uses_count_guard_not_a_dense_spectral_oracle():
    # Four-node free equal-spring path spectrum: 0,2-sqrt(2),2,2+sqrt(2).
    k = csr_matrix(
        [
            [1.0, -1.0, 0.0, 0.0],
            [-1.0, 2.0, -1.0, 0.0],
            [0.0, -1.0, 2.0, -1.0],
            [0.0, 0.0, -1.0, 1.0],
        ]
    )
    result = certify_sparse_modal_spectrum(k, eye(4, format="csr"), mode_count=2)
    with localcontext() as context:
        context.prec = 80
        low = Fraction(Decimal(2) - Decimal(2).sqrt())
        high = Fraction(Decimal(2) + Decimal(2).sqrt())
    assert result.rigid_mode_count == 1
    assert_encloses(result.positive_intervals[0], low)
    assert_encloses(result.positive_intervals[1], Fraction(2))
    assert_encloses(result.largest, high)
    assert result.selected_clusters[0].outside_gap_lower_bound > 0


def test_threshold_is_inclusive_and_largest_uncertainty_is_refined():
    tol = Fraction(1, 1 << 30)
    k = diags([0.0, float(3 * tol), float(4 * tol), 1.0, 3.0], format="csr")
    result = certify_sparse_modal_spectrum(
        k,
        eye(5, format="csr"),
        mode_count=1,
        rigid_mode_relative_tolerance=tol,
        cluster_relative_tolerance=0,
    )
    assert result.largest.lower == result.largest.upper == 3
    assert result.threshold_lower == result.threshold_upper == 3 * tol
    assert result.threshold_lower_guard.equal == 1
    assert result.rigid_mode_count == 2
    assert_encloses(result.positive_intervals[0], 4 * tol)


def test_adjacent_cluster_rule_is_transitive_with_floor_one():
    values = [0.0, 1.0, 1.0 + 0.75e-9, 1.0 + 1.5e-9, 3.0, 4.0]
    result = certify_sparse_modal_spectrum(
        diags(values, format="csr"), eye(6, format="csr"), mode_count=3
    )
    assert len(result.selected_clusters) == 1
    assert result.selected_clusters[0].multiplicity == 3
    assert result.selected_clusters[0].outside_gap_lower_bound > 0
    with pytest.raises(SparseModalCertificateError, match="cuts a repeated"):
        certify_sparse_modal_spectrum(
            diags(values, format="csr"), eye(6, format="csr"), mode_count=2
        )


def test_strict_positive_mass_bound_is_below_smallest_mass_eigenvalue():
    mass = diags([0.125, 0.25, 0.5, 1.0, 2.0], format="csr")
    stiffness = diags([0.0, 0.25, 1.0, 3.0, 8.0], format="csr")
    result = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    assert result.mass_lower_bound == Fraction(1, 16)
    assert result.mass_lower_bound_guard.less_or_equal == 0
    assert result.mass_bound_stiffness_input_hash == result.mass_input_hash


def test_negative_spectrum_does_not_grant_caller_psd_or_vector_admission():
    result = certify_sparse_modal_spectrum(
        diags([-2.0, 0.0, 1.0, 2.0, 3.0], format="csr"),
        eye(5, format="csr"),
        mode_count=1,
    )
    assert result.rigid_mode_count == 2
    assert not result.caller_numerical_admission_verified
    assert not result.vectors_verified


def test_all_actual_provider_costs_are_aggregated_including_mass_bound(monkeypatch):
    original = certificate.count_sparse_generalized_eigenvalues
    observed = []

    def observe(*args, **kwargs):
        value = original(*args, **kwargs)
        observed.append(value.statistics)
        return value

    monkeypatch.setattr(certificate, "count_sparse_generalized_eigenvalues", observe)
    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    result = certify_sparse_modal_spectrum(k, m, mode_count=2)
    stats = result.statistics
    assert (
        stats.provider_call_attempts == stats.provider_calls_completed == len(observed)
    )
    assert stats.aggregate_work_units == sum(x.work_units for x in observed)
    assert stats.aggregate_bit_operation_cost == sum(
        x.bit_operation_cost for x in observed
    )
    assert stats.aggregate_inertia_calls == sum(
        x.inertia_call_attempts for x in observed
    )
    assert stats.aggregate_input_entries == sum(x.input_entries for x in observed)
    assert stats.count_cache_hits > 0


@pytest.mark.parametrize(
    "budget",
    [
        SparseModalCertificateBudget(maximum_provider_calls=1),
        SparseModalCertificateBudget(maximum_aggregate_work_units=3),
        SparseModalCertificateBudget(maximum_aggregate_bit_operation_cost=1),
        SparseModalCertificateBudget(maximum_aggregate_inertia_calls=1),
        SparseModalCertificateBudget(maximum_aggregate_input_entries=3),
        SparseModalCertificateBudget(maximum_total_refinements=1),
        SparseModalCertificateBudget(maximum_shift_bits=1),
    ],
)
def test_budget_failure_retains_real_partial_costs_and_typed_refusal(budget):
    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    with pytest.raises(SparseModalCertificateBudgetExceeded) as caught:
        certify_sparse_modal_spectrum(k, m, mode_count=2, budget=budget)
    assert caught.value.statistics is not None
    assert not hasattr(caught.value, "vectors_verified")


def test_cumulative_budget_is_not_reset_at_the_second_provider_call():
    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    # Each complete pencil call needs two inertias: one for M, one for K-tM.
    # Only one further inertia attempt remains after the first complete call.
    budget = SparseModalCertificateBudget(maximum_aggregate_inertia_calls=3)
    with pytest.raises(SparseModalCertificateBudgetExceeded) as caught:
        certify_sparse_modal_spectrum(k, m, mode_count=2, budget=budget)
    stats = caught.value.statistics
    assert stats.provider_calls_completed == 1
    assert stats.provider_call_attempts == 2
    assert stats.aggregate_inertia_calls == 4
    assert stats.aggregate_work_units > 0
    assert stats.aggregate_bit_operation_cost > 0
    assert stats.aggregate_inertia_calls > budget.maximum_aggregate_inertia_calls


def test_original_caller_mutation_cannot_change_private_count_snapshot(monkeypatch):
    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    original = certificate.count_sparse_generalized_eigenvalues
    mutated = False

    def observe(*args, **kwargs):
        nonlocal mutated
        if not mutated:
            k.data[:] *= 100
            mutated = True
        return original(*args, **kwargs)

    monkeypatch.setattr(certificate, "count_sparse_generalized_eigenvalues", observe)
    result = certify_sparse_modal_spectrum(k, m, mode_count=2)
    assert result.largest.lower == result.largest.upper == 8
    assert_encloses(result.positive_intervals[0], Fraction(1))


@pytest.mark.parametrize("bad", [True, 0, -1, 4])
def test_invalid_mode_count_has_no_certificate(bad):
    with pytest.raises(SparseModalCertificateError, match="mode_count"):
        certify_sparse_modal_spectrum(
            diags([0.0, 1.0, 2.0, 3.0, 4.0], format="csr"),
            eye(5, format="csr"),
            mode_count=bad,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, -1])
def test_invalid_tolerance_has_no_certificate(bad):
    with pytest.raises(SparseModalCertificateError, match="rigid tolerance"):
        certify_sparse_modal_spectrum(
            eye(4, format="csr"),
            eye(4, format="csr"),
            mode_count=1,
            rigid_mode_relative_tolerance=bad,
        )


def test_exact_count_provider_refuses_nonsymmetric_and_non_spd_inputs():
    with pytest.raises(SparseModalCertificateError, match="symmetric"):
        certify_sparse_modal_spectrum(
            csr_matrix([[1.0, 1.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]]),
            eye(3, format="csr"),
            mode_count=1,
        )
    with pytest.raises(SparseModalCertificateError, match="positive definite"):
        certify_sparse_modal_spectrum(
            eye(4, format="csr"),
            diags([0.0, 1.0, 1.0, 1.0], format="csr"),
            mode_count=1,
        )


def test_invalid_shapes_and_sparse_storage_fail_before_count():
    for k, m in [
        (np.eye(4), eye(4, format="csr")),
        (eye(4, format="csc"), eye(4, format="csr")),
        (eye(4, format="csr"), eye(5, format="csr")),
    ]:
        with pytest.raises(SparseModalCertificateError):
            certify_sparse_modal_spectrum(k, m, mode_count=1)


def test_provider_budget_validation_is_not_silently_replaced():
    with pytest.raises(ValueError):
        SparseModalCertificateBudget(provider_budget=None)
    with pytest.raises(ValueError):
        SparseModalCertificateBudget(maximum_provider_calls=True)
    assert (
        replace(
            SparseModalCertificateBudget(), provider_budget=SparseInertiaBudget()
        ).provider_budget.maximum_inertia_calls
        == 2
    )


def test_plaintext_live_session_object_is_rejected_before_count():
    from scipy.sparse import diags, eye

    with pytest.raises(SparseModalCertificateError, match="session"):
        certify_sparse_modal_spectrum(
            diags([0.0, 1.0, 2.0, 3.0], format="csr"),
            eye(4, format="csr"),
            mode_count=1,
            _live_session={"source": "self-hash"},
        )


def test_largest_bracket_moves_past_uncertain_optional_point_without_refund(monkeypatch):
    from structural_analysis.solvers.sparse_interval_inertia import (
        SparseIntervalInertiaUncertain,
    )

    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    ledger = certificate._Ledger(SparseModalCertificateBudget())
    oracle = certificate._Oracle(k, m, ledger)
    original = certificate.count_sparse_generalized_eigenvalues
    seen = []
    paid_at_uncertainty = []

    def counted(*args, shift, **kwargs):
        seen.append(shift)
        result = original(*args, shift=shift, **kwargs)
        if shift == 1:
            paid_at_uncertainty.append(result.statistics)
            # Delivery of a count is refused after paid provider work. The
            # oracle must absorb the work without caching any returned count.
            raise SparseIntervalInertiaUncertain(
                "synthetic optional-point uncertainty", result.statistics
            )
        return result

    monkeypatch.setattr(certificate, "count_sparse_generalized_eigenvalues", counted)
    result = certificate._largest(oracle)
    assert result.lower == result.upper == 8
    assert seen == [0, 1, 2, 4, 8]
    assert Fraction(1) not in oracle.cache
    assert ledger.snapshot().growth_steps == 3
    assert paid_at_uncertainty[0].work_units > 0
    assert ledger.snapshot().aggregate_work_units > paid_at_uncertainty[0].work_units
    assert ledger.snapshot().provider_call_attempts == 5
    assert ledger.snapshot().provider_calls_completed == 4


@pytest.mark.parametrize(
    "failure_type", [SparseModalCertificateBudgetExceeded, SparseModalCertificateError]
)
def test_largest_bracket_never_expands_past_a_budget_or_other_refusal(
    monkeypatch, failure_type
):
    from structural_analysis.solvers.sparse_inertia import SparseInertiaBudgetExceeded

    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    ledger = certificate._Ledger(SparseModalCertificateBudget())
    oracle = certificate._Oracle(k, m, ledger)
    original = oracle.count
    seen = []

    def counted(shift):
        seen.append(shift)
        result = original(shift)
        if shift == 1:
            try:
                raise SparseInertiaBudgetExceeded("synthetic exhausted provider")
            except SparseInertiaBudgetExceeded as cause:
                raise failure_type("spent budget", ledger.snapshot()) from cause
        return result

    monkeypatch.setattr(oracle, "count", counted)
    with pytest.raises(failure_type, match="spent budget"):
        certificate._largest(oracle)
    assert seen == [0, 1]
    assert ledger.snapshot().growth_steps == 0
    assert ledger.snapshot().aggregate_work_units > 0



def test_uncertain_upper_search_still_ends_at_original_growth_cap(monkeypatch):
    from structural_analysis.solvers.sparse_interval_inertia import (
        SparseIntervalInertiaUncertain,
    )

    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    ledger = certificate._Ledger(SparseModalCertificateBudget(maximum_growth_steps=2))
    oracle = certificate._Oracle(k, m, ledger)
    original = oracle.count
    seen = []

    def counted(shift):
        seen.append(shift)
        result = original(shift)
        if shift > 0:
            try:
                raise SparseIntervalInertiaUncertain("unresolved optional upper")
            except SparseIntervalInertiaUncertain as cause:
                raise SparseModalCertificateError("no count", ledger.snapshot()) from cause
        return result

    monkeypatch.setattr(oracle, "count", counted)
    with pytest.raises(SparseModalCertificateBudgetExceeded, match="growth_steps"):
        certificate._largest(oracle)
    assert seen == [0, 1, 2, 4]
    assert ledger.snapshot().growth_steps == 3
    assert ledger.snapshot().aggregate_work_units > 0


@pytest.mark.parametrize("operation", ["lower", "refinement"])
def test_uncertain_required_search_points_remain_terminal(monkeypatch, operation):
    from structural_analysis.solvers.sparse_interval_inertia import (
        SparseIntervalInertiaUncertain,
    )

    k, m = congruence([0.0, 1.0, 2.0, 5.0, 8.0])
    ledger = certificate._Ledger(SparseModalCertificateBudget())
    oracle = certificate._Oracle(k, m, ledger)
    original = oracle.count
    seen = []

    def counted(shift):
        seen.append(shift)
        original(shift)
        try:
            raise SparseIntervalInertiaUncertain("required point uncertain")
        except SparseIntervalInertiaUncertain as cause:
            raise SparseModalCertificateError("no count", ledger.snapshot()) from cause

    monkeypatch.setattr(oracle, "count", counted)
    with pytest.raises(SparseModalCertificateError, match="no count"):
        if operation == "lower":
            certificate._largest(oracle)
        else:
            certificate._refine_interval(
                oracle, certificate.CertifiedEigenvalueInterval(
                    Fraction(0), Fraction(8), 1, 5, 4
                )
            )
    assert len(seen) == 1
    assert ledger.snapshot().growth_steps == 0
    assert ledger.snapshot().aggregate_work_units > 0
