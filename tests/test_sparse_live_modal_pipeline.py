"""Analytical small matrices only; no original80 case or external owner state."""

from dataclasses import replace
from fractions import Fraction
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from scipy.sparse import diags, eye, csr_matrix

from structural_analysis.solvers import sparse_modal_certificate as c
from structural_analysis.solvers import sparse_modal_subspace as s
from structural_analysis.solvers import sparse_live_modal_pipeline as p
from structural_analysis.solvers.sparse_cached_interval_pencil import (
    SparseCachedIntervalPencil,
    SparseCachedIntervalPencilUncertain,
)
from structural_analysis.solvers.sparse_inertia import (
    SparseInertiaBudget,
    SparseInertiaBudgetExceeded,
)


def matrices(values=(0.0, 0.0, 2.0, 2.0, 5.0, 9.0)):
    return diags(values, format="csr"), eye(len(values), format="csr")


def session(budget=None):
    trial = p._TrialLedger(budget or p.LiveModalPipelineBudget())
    return p._LiveCountSession(p._TOKEN, trial)


def make_certificate(ctx, k, m, mode_count=2, rigid=1e-10):
    cert = c.certify_sparse_modal_spectrum(
        k,
        m,
        mode_count=mode_count,
        rigid_mode_relative_tolerance=rigid,
        budget=c.SparseModalCertificateBudget(),
        _live_session=ctx,
    )
    ctx.mint(cert)
    return cert


def extract_in_context(ctx, k, m, cert):
    return s.extract_certified_sparse_modal_subspace(
        k,
        m,
        cert,
        budget=s.SparseModalSubspaceBudget(
            provider_budget=SparseInertiaBudget(),
            maximum_total_provider_calls=256,
            maximum_total_bit_operation_cost=64_000_000_000,
            maximum_total_inertia_calls=512,
        ),
        _live_session=ctx,
    )


def test_actual_cold_full_repeated_space_and_no_borrowed_authority():
    k, m = matrices()
    before = tuple(a.tobytes() for x in (k, m) for a in (x.data, x.indices, x.indptr))
    pipe = p.LiveModalProofPipeline()
    result = pipe.run(k, m, 2)
    assert result.certificate.rigid_mode_count == 2
    assert result.certificate.selected_clusters[0].multiplicity == 2
    block = result.subspace.clusters[0]
    v = np.asarray(block.mass_normalized_vectors).T
    assert v.shape == (6, 2)
    target = np.eye(6)[:, 2:4]
    assert np.max(np.abs(v @ v.T - target @ target.T)) < 1e-8
    assert np.max(np.abs(k @ v - (m @ v) * np.asarray(block.eigenvalues))) < 1e-9
    assert np.max(np.abs(v.T @ (m @ v) - np.eye(2))) < 1e-8
    assert np.allclose(block.eigenvalues, [2, 2], rtol=1e-9, atol=0)
    assert pipe.statistics["proof_cache_hits"] >= 4
    assert pipe.statistics["count_requests"] > pipe.statistics["provider_attempts"]
    assert pipe.statistics["constructors"] == pipe.statistics["closes"] == 2
    assert not result.public_integration_verified
    assert not result.subspace.rounded_residual_error_enclosure_verified
    assert not result.subspace.certificate_cost_provenance_verified
    assert before == tuple(
        a.tobytes() for x in (k, m) for a in (x.data, x.indices, x.indptr)
    )


def test_sequential_sources_keep_cumulative_spend_and_close_pairs():
    pipe = p.LiveModalProofPipeline()
    a = pipe.run(*matrices((0.0, 3.0, 6.0, 9.0)), 1)
    first = a.cumulative_cost.copy()
    b = pipe.run(*matrices((0.0, 4.0, 8.0, 12.0)), 1)
    assert b.cumulative_cost["provider_attempts"] > first["provider_attempts"]
    assert b.cumulative_cost["work_units"] > first["work_units"]
    assert b.cumulative_cost["constructors"] == b.cumulative_cost["closes"] == 4
    assert b.certificate.rigid_mode_count == 1


def test_analytic_counts_hit_fees_constructor_and_exact_once_delta():
    ctx = session()
    k, m = matrices((0.0, 2.0, 2.0, 5.0))
    try:
        a = ctx.acquire(k, m, shift=Fraction(1))
        paid = ctx.trial.values.copy()
        b = ctx.acquire(k.copy(), m.copy(), shift=Fraction(1))
        assert (a.negative, a.zero, a.positive) == (1, 0, 3)
        assert (b.negative, b.zero, b.positive) == (1, 0, 3)
        assert ctx.trial.values["provider_attempts"] == paid["provider_attempts"] == 1
        assert ctx.trial.values["proof_cache_hits"] == 1
        assert b.statistics.inertia_call_attempts == 0
        assert b.statistics.bit_operation_cost == 0
        assert b.statistics.work_units > 0
        for name in p._SUM:
            assert (
                getattr(a.statistics, name) + getattr(b.statistics, name)
                == ctx.trial.values[name]
            )
        assert ctx.trial.values["inertia_call_attempts"] == 2  # mass once + pencil once
    finally:
        ctx.close()
    assert all(
        e["pencil"].statistics.inertia.current_stored_entries == 0
        for e in ctx.pairs.values()
    )
    assert ctx.trial.values["closes"] == 1


def test_shift_and_profile_are_not_interchangeable(monkeypatch):
    ctx = session()
    k, m = matrices((0.0, 2.0, 2.0, 5.0))
    try:
        a = ctx.acquire(k, m, shift=Fraction(2))
        b = ctx.acquire(k, m, shift=Fraction(3))
        assert (a.negative, a.zero) == (1, 2)
        assert (b.negative, b.zero) == (3, 0)
        monkeypatch.setattr(SparseCachedIntervalPencil, "count", lambda *a, **kw: None)
        with pytest.raises(p.LiveModalPipelineError, match="provider/profile changed"):
            ctx.acquire(k, m, shift=Fraction(2))
    finally:
        ctx.close()


def test_closed_and_stale_pair_do_not_receive_old_proof():
    ctx = session()
    k, m = matrices((0.0, 2.0, 2.0, 5.0))
    a = ctx.acquire(k, m, shift=Fraction(1))
    k.data[1] = 3
    b = ctx.acquire(k, m, shift=Fraction(1))
    assert b.stiffness_input_hash != a.stiffness_input_hash
    assert ctx.trial.values["proof_cache_hits"] == 0
    ctx.close()
    with pytest.raises(p.LiveModalPipelineError, match="closed/sealed"):
        ctx.acquire(k, m, shift=Fraction(1))


def test_real_provider_cap_refuses_before_dispatch_without_refund():
    ctx = session(p.LiveModalPipelineBudget(maximum_provider_calls=1))
    k, m = matrices()
    ctx.acquire(k, m, shift=Fraction(1))
    work = ctx.trial.values["work_units"]
    with pytest.raises(p.LiveModalPipelineBudgetExceeded, match="before dispatch"):
        ctx.acquire(k, m, shift=Fraction(2))
    assert ctx.trial.values["provider_attempts"] == 1
    assert ctx.trial.values["prospective_provider_refusals"] == 1
    assert ctx.trial.values["work_units"] > work
    assert ctx.trial.sealed
    ctx.close()


def test_global_work_refusal_and_future_runs_cannot_reset():
    pipe = p.LiveModalProofPipeline(
        budget=p.LiveModalPipelineBudget(maximum_aggregate_work_units=1)
    )
    with pytest.raises(p.LiveModalPipelineBudgetExceeded):
        pipe.run(*matrices(), 2)
    spent = pipe.statistics["work_units"]
    assert spent > 1
    with pytest.raises(p.LiveModalPipelineError, match="sealed"):
        pipe.run(*matrices(), 2)
    assert pipe.statistics["work_units"] == spent


def test_actual_uncertainty_is_not_cached_and_partial_work_remains():
    # Exact binary64 .09 - .3**2 is positive but Schur enclosure overlaps zero.
    # No count may be substituted for a rigorous uncertain outcome.
    k = csr_matrix([[1.0, 0.3], [0.3, 0.09]])
    m = eye(2, format="csr")
    ctx = session()
    try:
        with pytest.raises(SparseCachedIntervalPencilUncertain):
            ctx.acquire(k, m, shift=Fraction(0))
        assert not ctx.proofs
        assert ctx.trial.values["provider_attempts"] == 1
        assert ctx.trial.values["work_units"] > 0
    finally:
        ctx.close()


def test_non_diagonally_dominant_positive_mass_count_is_not_banned():
    m = csr_matrix([[1.0, 2.0], [2.0, 5.0]])
    k = 3 * m
    ctx = session()
    try:
        a = ctx.acquire(k, m, shift=Fraction(1))
        assert (a.negative, a.zero, a.positive) == (0, 0, 2)
        assert (
            next(iter(ctx.pairs.values()))["pencil"].exact_mass_lower_bound_hint is None
        )
    finally:
        ctx.close()


@pytest.mark.parametrize("change", ["source", "rigid", "threshold", "guard"])
def test_coherently_mutated_internal_certificate_still_runs_all_guards(change):
    k, m = matrices()
    ctx = session()
    try:
        cert = make_certificate(ctx, k, m)
        if change == "source":
            object.__setattr__(cert, "stiffness_input_hash", "0" * 64)
        elif change == "rigid":
            object.__setattr__(cert, "rigid_mode_count", 3)
        elif change == "threshold":
            object.__setattr__(cert, "threshold_upper", Fraction(1))
        else:
            guard = replace(cert.threshold_lower_guard, less=0, less_or_equal=0)
            object.__setattr__(cert, "threshold_lower_guard", guard)
        with pytest.raises(s.SparseModalSubspaceError):
            extract_in_context(ctx, k, m, cert)
    finally:
        ctx.close()


def test_replaced_or_cost_forged_certificate_is_not_live_minted_authority():
    k, m = matrices()
    ctx = session()
    try:
        cert = make_certificate(ctx, k, m)
        with pytest.raises(p.LiveModalPipelineError, match="not minted"):
            extract_in_context(ctx, k, m, replace(cert))
        object.__setattr__(
            cert, "statistics", replace(cert.statistics, aggregate_work_units=0)
        )
        with pytest.raises(p.LiveModalPipelineError, match="cost changed"):
            extract_in_context(ctx, k, m, cert)
    finally:
        ctx.close()


def test_external_plaintext_path_freshly_counts_and_rejects_forged_source(monkeypatch):
    k, m = matrices()
    ctx = session()
    try:
        cert = make_certificate(ctx, k, m)
    finally:
        ctx.close()
    calls = []
    native = s.count_sparse_generalized_eigenvalues

    def fresh(*args, **kw):
        calls.append(kw["shift"])
        return native(*args, **kw)

    monkeypatch.setattr(s, "count_sparse_generalized_eigenvalues", fresh)
    actual = s.extract_certified_sparse_modal_subspace(k, m, cert)
    assert actual.vectors_verified and calls
    prefix = len(calls)
    with pytest.raises(s.SparseModalSubspaceError):
        s.extract_certified_sparse_modal_subspace(
            k, m, replace(cert, stiffness_input_hash="f" * 64)
        )
    assert len(calls) > prefix and not hasattr(s, "_LIVE_PROOF_CONTEXT")


def test_live_proof_keys_share_real_retention_budget():
    ctx = session(
        p.LiveModalPipelineBudget(
            provider_budget=SparseInertiaBudget(maximum_stored_entries=20)
        )
    )
    k, m = matrices((2.0, 5.0))
    try:
        with pytest.raises(SparseInertiaBudgetExceeded):
            for i in range(1, 30):
                ctx.acquire(k, m, shift=Fraction(i))
        assert ctx.trial.sealed
        assert ctx.trial.values["work_units"] > 0
        assert ctx.trial.values["provider_attempts"] > 0
    finally:
        ctx.close()
    assert not ctx.proofs
    assert all(
        e["pencil"].statistics.inertia.current_stored_entries == 0
        for e in ctx.pairs.values()
    )


def test_exact_fraction_and_explicit_zero_storage_remain_distinct():
    ctx = session()
    k, m = matrices((0.5, 2.0, 5.0, 9.0))
    try:
        a = ctx.acquire(k, m, shift=Fraction(1, 2))
        shift = Fraction(1, 2) + Fraction(1, 1 << 54)
        assert float(shift) == 0.5
        b = ctx.acquire(k, m, shift=shift)
        assert (a.negative, a.zero, a.positive) == (0, 1, 3)
        assert (b.negative, b.zero, b.positive) == (1, 0, 3)
        z = csr_matrix(
            (
                np.array([0.5, 0.0, 2.0, 5.0, 9.0]),
                np.array([0, 1, 1, 2, 3]),
                np.array([0, 2, 3, 4, 5]),
            ),
            shape=(4, 4),
        )
        d = ctx.acquire(z, m, shift=Fraction(1, 2))
        assert d.stiffness_input_hash != a.stiffness_input_hash
        assert ctx.trial.values["provider_attempts"] == 3
        assert ctx.trial.values["proof_cache_hits"] == 0
    finally:
        ctx.close()


def test_coherent_higher_threshold_real_second_mode_cannot_skip_first():
    k, m = matrices((2.0, 3.0, 5.0, 9.0))
    ctx = session()
    other = session()
    try:
        original = make_certificate(ctx, k, m, mode_count=1)
        high = make_certificate(other, k, m, mode_count=1, rigid=Fraction(3, 10))
        assert high.rigid_mode_count == 1
        assert high.positive_intervals[0].target_global_ordinal == 2
        assert high.positive_intervals[0].lower <= 3 <= high.positive_intervals[0].upper
        # Every replacement field comes from a real count certificate for SAME
        # original pair, but a different explicit policy; authentic paid stats kept.
        for f in p.fields(original):
            if f.name != "statistics":
                object.__setattr__(original, f.name, getattr(high, f.name))
        before = ctx.trial.values["work_units"]
        with pytest.raises(s.SparseModalSubspaceError, match="threshold"):
            extract_in_context(ctx, k, m, original)
        assert ctx.trial.values["work_units"] >= before
    finally:
        ctx.close()
        other.close()


def test_complete_repeated_space_with_non_dd_positive_mass():
    m = csr_matrix(
        [
            [1.0, 1.0, 0.0, 0.0],
            [1.0, 2.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    k = csr_matrix(
        [
            [2.0, 2.0, 0.0, 0.0],
            [2.0, 4.0, 0.0, 0.0],
            [0.0, 0.0, 5.0, 0.0],
            [0.0, 0.0, 0.0, 9.0],
        ]
    )
    result = p.LiveModalProofPipeline().run(k, m, 2)
    block = result.subspace.clusters[0]
    v = np.asarray(block.mass_normalized_vectors).T
    assert np.max(np.abs(v.T @ (m @ v) - np.eye(2))) < 1e-8
    assert np.max(np.abs(v @ v.T @ m.toarray() - np.diag([1, 1, 0, 0]))) < 1e-8
    assert np.max(np.abs(k @ v - (m @ v) * np.asarray(block.eigenvalues))) < 1e-9
    assert np.allclose(block.eigenvalues, [2, 2], rtol=1e-9, atol=0)
    assert result.certificate.mass_lower_bound <= Fraction(1, 4)


def test_second_context_cannot_replenish_global_inertia_allowance():
    ctx = session(p.LiveModalPipelineBudget(maximum_aggregate_inertia_calls=2))
    k, m = matrices()
    try:
        ctx.acquire(k, m, shift=Fraction(1))
        assert ctx.trial.values["inertia_call_attempts"] == 2
        other = k.copy()
        other.data *= 2
        with pytest.raises(p.LiveModalPipelineBudgetExceeded):
            ctx.acquire(other, m, shift=Fraction(1))
        assert ctx.trial.sealed
        assert ctx.trial.values["inertia_call_attempts"] == 2
    finally:
        ctx.close()


def test_same_pair_spent_inertia_refuses_before_actual_dispatch():
    ctx = session(p.LiveModalPipelineBudget(maximum_aggregate_inertia_calls=2))
    k, m = matrices()
    try:
        ctx.acquire(k, m, shift=Fraction(1))
        with pytest.raises(p.LiveModalPipelineBudgetExceeded, match="remaining"):
            ctx.acquire(k, m, shift=Fraction(2))
        assert ctx.trial.values["provider_attempts"] == 1
        assert ctx.trial.values["prospective_provider_refusals"] == 1
        assert ctx.trial.values["inertia_call_attempts"] == 2
        assert (
            next(iter(ctx.pairs.values()))["pencil"].statistics.provider_call_attempts
            == 1
        )
    finally:
        ctx.close()


def test_all_completed_hits_and_predispatch_refusals_have_bounded_truthful_events():
    ctx = session(p.LiveModalPipelineBudget(maximum_provider_calls=1))
    k, m = matrices()
    try:
        ctx.acquire(k, m, shift=Fraction(1))
        ctx.acquire(k, m, shift=Fraction(1))
        with pytest.raises(p.LiveModalPipelineBudgetExceeded):
            ctx.acquire(k, m, shift=Fraction(2))
        assert [e["status"] for e in ctx.trial.events] == ["computed", "hit", "refused"]
        assert [e["actual_provider_attempts"] for e in ctx.trial.events] == [1, 1, 1]
        assert [e["request"] for e in ctx.trial.events] == [1, 2, 3]
    finally:
        ctx.close()


def test_over_cap_lookup_failure_still_closes_both_retained_pencils():
    ctx = session(p.LiveModalPipelineBudget(maximum_aggregate_work_units=5000))
    k, m = matrices()
    try:
        ctx.acquire(k, m, shift=Fraction(1))
        ctx.acquire(m, m, shift=Fraction(2))
        assert len(ctx.pairs) == 2
        with pytest.raises(p.LiveModalPipelineBudgetExceeded):
            for _ in range(200):
                ctx.acquire(k, m, shift=Fraction(1))
        assert ctx.trial.sealed
        spent = ctx.trial.values["work_units"]
        assert spent > 5000
    finally:
        ctx.close()
    assert ctx.trial.values["work_units"] == spent
    assert ctx.trial.values["closes"] == 2
    assert ctx.trial.values["count_requests"] == len(ctx.trial.events)
    assert all(
        e["pencil"].statistics.inertia.current_stored_entries == 0
        for e in ctx.pairs.values()
    )


def test_certificate_local_oracle_hit_uses_paid_live_lookup_no_fresh_native():
    k, m = matrices()
    ctx = session()
    try:
        ledger = c._Ledger(c.SparseModalCertificateBudget(), live_session=ctx)
        oracle = c._Oracle(k, m, ledger)
        a = oracle.count(Fraction(1))
        before = ctx.trial.values.copy()
        b = oracle.count(Fraction(1))
        assert (a.negative, a.zero) == (b.negative, b.zero) == (2, 0)
        assert ctx.trial.values["provider_attempts"] == before["provider_attempts"] == 1
        assert ctx.trial.values["count_requests"] == before["count_requests"] + 1
        assert ctx.trial.values["work_units"] > before["work_units"]
        assert ledger.snapshot().provider_call_attempts == 1
        assert ledger.snapshot().count_cache_hits == 1
        assert ledger.snapshot().aggregate_work_units == ctx.trial.values["work_units"]
    finally:
        ctx.close()


def test_public_binary64_threshold_point_has_same_source_rank_and_paid_prefix():
    pipe = p.LiveModalProofPipeline()
    result = pipe.run(*matrices(), 2, public_rigid_threshold=0.1)
    guard = result.public_threshold_guard
    assert guard.threshold == 0.1 and guard.exact_shift == Fraction.from_float(0.1)
    assert guard.exact_shift != Fraction(1, 10)
    assert guard.less_or_equal == result.certificate.rigid_mode_count == 2
    assert guard.dimension == 6
    assert (guard.stiffness_input_hash, guard.mass_input_hash) == (
        result.certificate.stiffness_input_hash,
        result.certificate.mass_input_hash,
    )
    assert not guard.largest_estimate_error_enclosure_verified
    assert (
        result.subspace.statistics.certificate_provider_calls
        == result.certificate.statistics.provider_call_attempts
    )
    assert not result.caller_numerical_admission_verified
    assert not result.rounded_vector_error_enclosure_verified


def test_public_inclusive_threshold_mismatch_refuses_before_vectors():
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineError, match="threshold prefix") as caught:
        pipe.run(*matrices(), 2, public_rigid_threshold=2.0)
    assert caught.value.stage == "public_threshold_guard"
    assert caught.value.cumulative_cost["provider_attempts"] > 0
    assert pipe.statistics["constructors"] == pipe.statistics["closes"] == 2


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, True, 0])
def test_invalid_public_policy_threshold_not_silently_defaulted(value):
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineError, match="binary64"):
        pipe.run(*matrices(), 2, public_rigid_threshold=value)
    assert pipe.statistics["provider_attempts"] == 0


def test_literal_zero_residual_and_orthogonality_targets_are_applied():
    result = p.LiveModalProofPipeline().run(
        *matrices((1.0, 2.0, 5.0, 9.0)),
        1,
        residual_relative_tolerance=0.0,
        orthogonality_tolerance=0.0,
    )
    group = result.subspace.clusters[0]
    assert group.residual_relative_inf_maximum == 0.0
    assert group.mass_orthogonality_error_inf == 0.0


def test_user_iteration_budget_is_not_ignored_or_renewed():
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineBudgetExceeded) as caught:
        pipe.run(*matrices(), 2, maximum_iterations=1)
    assert caught.value.stage == "extraction"
    assert (
        caught.value.statistics.iterations <= 2
    )  # attempted refusing operation remains spent
    assert pipe.statistics["sealed"]
    assert pipe.statistics["constructors"] == pipe.statistics["closes"]


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_maximum_iterations_rejected_before_native_work(value):
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineError, match="maximum_iterations"):
        pipe.run(*matrices(), 2, maximum_iterations=value)
    assert pipe.statistics["provider_attempts"] == 0


def test_explicit_sessions_do_not_accept_arbitrary_callbacks_or_plaintext():
    k, m = matrices()
    with pytest.raises(c.SparseModalCertificateError, match="session"):
        c.certify_sparse_modal_spectrum(
            k, m, mode_count=2, _live_session=lambda *a: None
        )
    cert = c.certify_sparse_modal_spectrum(k, m, mode_count=2)
    with pytest.raises(s.SparseModalSubspaceError, match="context"):
        s.extract_certified_sparse_modal_subspace(k, m, cert, _live_session=object())


def test_independent_simultaneous_callers_have_no_shared_global_binding(monkeypatch):
    barrier = threading.Barrier(2)
    original = p._LiveCountSession.isolated

    def rendezvous(self, matrix):
        if not getattr(self, "_test_seen", False):
            self._test_seen = True
            barrier.wait(timeout=5)
        return original(self, matrix)

    monkeypatch.setattr(p._LiveCountSession, "isolated", rendezvous)
    bindings = (
        c.count_sparse_generalized_eigenvalues,
        s.count_sparse_generalized_eigenvalues,
    )

    def run(values):
        return p.LiveModalProofPipeline().run(
            *matrices(values), 1, public_rigid_threshold=0.1
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [(0.0, 3.0, 6.0, 9.0), (0.0, 4.0, 8.0, 12.0)]))
    assert [x.subspace.clusters[0].eigenvalues[0] for x in results] == pytest.approx(
        [3.0, 4.0]
    )
    assert (
        results[0].certificate.stiffness_input_hash
        != results[1].certificate.stiffness_input_hash
    )
    assert all(
        x.cumulative_cost["constructors"] == x.cumulative_cost["closes"] == 2
        for x in results
    )
    assert bindings == (
        c.count_sparse_generalized_eigenvalues,
        s.count_sparse_generalized_eigenvalues,
    )
    assert not hasattr(c, "_LIVE_PROOF_CONTEXT") and not hasattr(
        s, "_LIVE_PROOF_CONTEXT"
    )


def test_same_instance_overlap_refuses_without_overwriting_owner(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original = p._LiveCountSession.isolated

    def block(self, matrix):
        if not getattr(self, "_test_seen", False):
            self._test_seen = True
            entered.set()
            assert release.wait(timeout=5)
        return original(self, matrix)

    monkeypatch.setattr(p._LiveCountSession, "isolated", block)
    pipe = p.LiveModalProofPipeline()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(pipe.run, *matrices((0.0, 3.0, 6.0, 9.0)), 1)
        assert entered.wait(timeout=5)
        try:
            with pytest.raises(p.LiveModalPipelineError, match="already active"):
                pipe.run(*matrices((0.0, 4.0, 8.0, 12.0)), 1)
        finally:
            release.set()
        result = future.result(timeout=10)
    assert result.subspace.clusters[0].eigenvalues[0] == pytest.approx(3.0)
    assert pipe.statistics["constructors"] == pipe.statistics["closes"] == 2


def test_foreign_thread_cannot_borrow_even_live_explicit_session():
    ctx = session()
    k, m = matrices()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(ctx.acquire, k, m, shift=Fraction(1))
            with pytest.raises(p.LiveModalPipelineError, match="process/thread"):
                future.result(timeout=5)
        assert ctx.trial.values["provider_attempts"] == 0
    finally:
        ctx.close()


def test_hidden_negative_direction_refuses_actual_stiffness_policy_point():
    # The coupled 2x2 block has eigenvalues -1e-4 and 2 exactly by its
    # sum/difference directions. A positive estimate cannot certify its PSD.
    a, b = (2.0 - 1e-4) / 2, (2.0 + 1e-4) / 2
    k = diags([1.0, 1.0, 3.0, 4.0, 5.0, 6.0], format="lil")
    k[0, 0] = k[1, 1] = a
    k[0, 1] = k[1, 0] = b
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineError, match="stiffness_psd") as caught:
        pipe.run(k.tocsr(), eye(6, format="csr"), 1, stiffness_psd_threshold=-1e-8)
    assert caught.value.stage == "stiffness_psd_guard"
    assert pipe.statistics["provider_attempts"] == 1
    assert pipe.statistics["constructors"] == pipe.statistics["closes"] == 1
    assert pipe.proof_events[-1]["status"] == "computed"


def test_positive_but_poor_mass_direction_refuses_actual_conditioning_point():
    # Both diagonal entries are 1, but the [1,-1] mass direction has
    # eigenvalue 1-a <1e-8. Its positive largest/minimum estimates are irrelevant.
    a = 1.0 - 1e-10
    m = eye(6, format="lil")
    m[0, 1] = m[1, 0] = a
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineError, match="mass_spd") as caught:
        pipe.run(eye(6, format="csr"), m.tocsr(), 1, mass_spd_threshold=1e-8)
    assert caught.value.stage == "mass_spd_guard"
    assert pipe.statistics["provider_attempts"] == 1
    assert pipe.statistics["constructors"] == pipe.statistics["closes"] == 1


def test_guard_equality_is_psd_admissible_but_mass_strictly_rejected():
    pipe = p.LiveModalProofPipeline()
    result = pipe.run(
        *matrices((0.0, 2.0, 5.0, 9.0)),
        1,
        stiffness_psd_threshold=0.0,
        mass_spd_threshold=0.1,
    )
    kg, mg = result.stiffness_psd_guard, result.mass_spd_guard
    assert (kg.less, kg.equal, kg.less_or_equal) == (0, 1, 1)
    assert (mg.less, mg.equal, mg.less_or_equal) == (0, 0, 0)
    assert kg.policy_role == "stiffness_psd" and mg.policy_role == "mass_spd"
    assert kg.exact_shift == Fraction(0) and mg.exact_shift == Fraction.from_float(0.1)
    assert kg.stiffness_input_hash == result.certificate.stiffness_input_hash
    assert mg.stiffness_input_hash == result.certificate.mass_input_hash
    assert kg.mass_input_hash == mg.mass_input_hash
    assert not kg.numerical_estimate_error_enclosure_verified
    assert not result.caller_numerical_admission_verified
    assert (
        result.cumulative_cost["constructors"] == result.cumulative_cost["closes"] == 3
    )
    assert (
        result.certificate.statistics.provider_call_attempts
        <= result.cumulative_cost["provider_attempts"]
    )
    assert (
        result.subspace.statistics.certificate_provider_calls
        == result.certificate.statistics.provider_call_attempts
    )
    with pytest.raises(p.LiveModalPipelineError, match="mass_spd"):
        p.LiveModalProofPipeline().run(*matrices(), 2, mass_spd_threshold=1.0)


@pytest.mark.parametrize(
    "name,value",
    [
        ("stiffness_psd_threshold", float("nan")),
        ("stiffness_psd_threshold", -float("inf")),
        ("stiffness_psd_threshold", 0.1),
        ("stiffness_psd_threshold", True),
        ("stiffness_psd_threshold", 0),
        ("mass_spd_threshold", float("nan")),
        ("mass_spd_threshold", float("inf")),
        ("mass_spd_threshold", -0.1),
        ("mass_spd_threshold", False),
        ("mass_spd_threshold", 0),
    ],
)
def test_invalid_matrix_policy_points_refuse_before_native_work(name, value):
    pipe = p.LiveModalProofPipeline()
    with pytest.raises(p.LiveModalPipelineError, match="binary64"):
        pipe.run(*matrices(), 2, **{name: value})
    assert pipe.statistics["provider_attempts"] == 0


def test_retiring_admission_pair_keeps_cost_and_releases_keys_storage():
    ctx = session()
    k, m = matrices((0.0, 2.0, 5.0, 9.0))
    try:
        ctx.acquire(k, m, shift=Fraction(1))
        pair = ctx._hash(k), ctx._hash(m)
        before = ctx.trial.values.copy()
        entry = ctx.pairs[pair]
        ctx.retire_pair(pair)
        assert not ctx.pairs and not ctx.proofs
        assert entry["pencil"].statistics.inertia.current_stored_entries == 0
        assert ctx.trial.values["provider_attempts"] == before["provider_attempts"]
        assert ctx.trial.values["bit_operation_cost"] == before["bit_operation_cost"]
        assert ctx.trial.values["closes"] == 1
        ctx.acquire(k, m, shift=Fraction(1))
        assert ctx.trial.values["provider_attempts"] == before["provider_attempts"] + 1
        assert ctx.trial.values["proof_cache_hits"] == 0
    finally:
        ctx.close()
    assert ctx.trial.values["closes"] == 2
