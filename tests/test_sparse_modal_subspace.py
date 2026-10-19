"""Independent analytical witnesses for certified complete-space extraction."""

from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags

from structural_analysis.solvers.sparse_modal_certificate import (
    CountEndpoint,
    certify_sparse_modal_spectrum,
)
from structural_analysis.solvers.sparse_modal_subspace import (
    SparseModalSubspaceBudget,
    SparseModalSubspaceBudgetExceeded,
    SparseModalSubspaceError,
    extract_certified_sparse_modal_subspace,
)


def diagonal_case():
    return (
        diags([0, 0, 0.5, 0.5, 3, 6, 8, 9], format="csr", dtype=float),
        diags(np.ones(8), format="csr"),
    )


def vector_matrix(result):
    return np.column_stack(
        [v for cluster in result.clusters for v in cluster.mass_normalized_vectors]
    )


def test_fixed_coordinate_scan_recovers_a_repeated_space_missed_by_first_seeds():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    result = extract_certified_sparse_modal_subspace(stiffness, mass, certificate)
    vectors = vector_matrix(result)
    assert result.clusters[0].eigenvalues == pytest.approx((0.5, 0.5))
    assert result.statistics.coordinate_attempts >= 4
    assert vectors[:2].tolist() == [[0, 0], [0, 0]]
    assert np.linalg.norm(vectors[4:]) == 0
    assert np.max(np.abs(vectors.T @ vectors - np.eye(2))) < 1e-12
    assert (
        result.statistics.total_provider_calls
        > certificate.statistics.provider_call_attempts
    )
    assert (
        result.statistics.certificate_provider_calls
        == certificate.statistics.provider_call_attempts
    )
    assert result.public_modal_integration_verified is False


def test_missing_provisional_direction_is_actually_extracted():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    provisional = np.zeros((8, 1))
    provisional[2, 0] = 1
    result = extract_certified_sparse_modal_subspace(
        stiffness, mass, certificate, provisional_vectors=provisional
    )
    vectors = vector_matrix(result)
    expected = np.zeros((8, 2))
    expected[2, 0] = expected[3, 1] = 1
    assert np.linalg.norm(vectors - expected @ (expected.T @ vectors)) < 1e-12
    assert np.linalg.matrix_rank(expected.T @ vectors) == 2


def test_non_chain_integer_congruence_has_correct_complete_generalized_space():
    # Q is unit lower bidiagonal, so Q^-1 e_j has exact alternating entries.
    # K=Q^T D Q, M=Q^T Q has the independent generalized spectrum D.
    n = 12
    q = diags([np.ones(n), np.ones(n - 1)], [0, -1], format="csr")
    values = [0, 0, 0.5, 0.5, 2, 4, 8, 16, 20, 24, 32, 64]
    stiffness = (q.T @ diags(values) @ q).tocsr()
    mass = (q.T @ q).tocsr()
    before = tuple(
        x.tobytes() for a in (stiffness, mass) for x in (a.data, a.indices, a.indptr)
    )
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    result = extract_certified_sparse_modal_subspace(stiffness, mass, certificate)
    vectors = vector_matrix(result)
    expected = np.zeros((n, 2))
    for column, j in enumerate((2, 3)):
        for i in range(j, n):
            expected[i, column] = (-1) ** (i - j)
    assert result.clusters[0].eigenvalues == pytest.approx((0.5, 0.5), abs=1e-10)
    assert np.linalg.norm(vectors - expected @ (expected.T @ (mass @ vectors))) < 1e-7
    assert np.max(np.abs(vectors.T @ (mass @ vectors) - np.eye(2))) < 1e-8
    assert result.clusters[0].subspace_error_bound < 1e-8
    assert before == tuple(
        x.tobytes() for a in (stiffness, mass) for x in (a.data, a.indices, a.indptr)
    )


def test_stale_certificate_is_refused_for_changed_original_stiffness():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    changed = stiffness.copy()
    changed.data[-1] += 1
    with pytest.raises(SparseModalSubspaceError, match="identity mismatch"):
        extract_certified_sparse_modal_subspace(changed, mass, certificate)


def test_coordinate_exhaustion_preserves_spent_certificate_and_attempts():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    with pytest.raises(SparseModalSubspaceBudgetExceeded) as info:
        extract_certified_sparse_modal_subspace(
            stiffness,
            mass,
            certificate,
            budget=replace(SparseModalSubspaceBudget(), maximum_coordinate_attempts=1),
        )
    stats = info.value.statistics
    assert stats.coordinate_attempts == 2
    assert stats.total_provider_calls > certificate.statistics.provider_call_attempts
    assert stats.total_work_units > certificate.statistics.aggregate_work_units


def test_provider_budget_does_not_reset_after_certificate():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    spent = certificate.statistics.provider_call_attempts
    with pytest.raises(SparseModalSubspaceBudgetExceeded) as info:
        extract_certified_sparse_modal_subspace(
            stiffness,
            mass,
            certificate,
            budget=replace(
                SparseModalSubspaceBudget(), maximum_total_provider_calls=spent
            ),
        )
    assert info.value.statistics.certificate_provider_calls == spent
    assert info.value.statistics.total_provider_calls == spent + 1


def test_duplicate_certified_cluster_cannot_masquerade_as_four_modes():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    invalid = replace(
        certificate,
        requested_mode_count=4,
        selected_clusters=certificate.selected_clusters * 2,
    )
    with pytest.raises(SparseModalSubspaceError, match="ordered positive prefix"):
        extract_certified_sparse_modal_subspace(stiffness, mass, invalid)


def test_forged_rigid_count_cannot_skip_the_true_first_positive_space():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    prototype = certificate.selected_clusters[0]
    clusters = tuple(
        replace(
            prototype,
            lower=Fraction(value),
            upper=Fraction(value),
            positive_ordinal_start=ordinal,
            positive_ordinal_stop=ordinal,
            multiplicity=1,
            lower_guard=CountEndpoint(Fraction(value), below, 1, below + 1),
            upper_guard=CountEndpoint(Fraction(value), below, 1, below + 1),
            preceding_guard=CountEndpoint(Fraction(value - 1), below, 0, below),
            following_guard=CountEndpoint(Fraction(value + 1), below + 1, 0, below + 1),
            outside_gap_lower_bound=Fraction(1),
        )
        for ordinal, value, below in ((1, 3, 4), (2, 6, 5))
    )
    invalid = replace(certificate, rigid_mode_count=4, selected_clusters=clusters)
    with pytest.raises(SparseModalSubspaceError, match="fresh threshold proof"):
        extract_certified_sparse_modal_subspace(stiffness, mass, invalid)


def test_forged_threshold_cannot_silently_change_the_caller_rigid_policy():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    invalid = replace(
        certificate,
        threshold_lower=Fraction(1),
        threshold_upper=Fraction(1),
        rigid_mode_count=4,
        threshold_lower_guard=CountEndpoint(Fraction(1), 4, 0, 4),
        threshold_upper_guard=CountEndpoint(Fraction(1), 4, 0, 4),
    )
    with pytest.raises(SparseModalSubspaceError, match="caller policy"):
        extract_certified_sparse_modal_subspace(stiffness, mass, invalid)


def test_forged_largest_endpoint_cannot_change_the_global_threshold_scale():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    invalid = replace(
        certificate,
        largest=replace(certificate.largest, upper=Fraction(4)),
    )
    with pytest.raises(SparseModalSubspaceError, match="fresh global count proof"):
        extract_certified_sparse_modal_subspace(stiffness, mass, invalid)


def test_explicit_custom_rigid_policy_requires_the_same_policy_on_extraction():
    stiffness, mass = diagonal_case()
    tolerance = Fraction(1, 8)
    certificate = certify_sparse_modal_spectrum(
        stiffness, mass, mode_count=2, rigid_mode_relative_tolerance=tolerance
    )
    with pytest.raises(SparseModalSubspaceError, match="caller policy"):
        extract_certified_sparse_modal_subspace(stiffness, mass, certificate)
    result = extract_certified_sparse_modal_subspace(
        stiffness, mass, certificate, rigid_mode_relative_tolerance=tolerance
    )
    assert tuple(v for c in result.clusters for v in c.eigenvalues) == pytest.approx(
        (3, 6)
    )
    assert result.rounded_residual_error_enclosure_verified is False


def test_retained_vectors_share_the_thin_coefficient_budget_with_next_block():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=3)
    with pytest.raises(SparseModalSubspaceBudgetExceeded, match="thin_entries") as info:
        extract_certified_sparse_modal_subspace(
            stiffness,
            mass,
            certificate,
            budget=replace(SparseModalSubspaceBudget(), maximum_thin_entries=32),
        )
    assert info.value.statistics.peak_thin_entries > 32


def test_oversized_provisional_columns_are_refused_before_copy(monkeypatch):
    import structural_analysis.solvers.sparse_modal_subspace as module

    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    provisional = np.zeros((8, 65))
    original = module.np.array

    def guarded_array(value, *args, **kwargs):
        assert value is not provisional, "unadmitted provisional copied"
        return original(value, *args, **kwargs)

    monkeypatch.setattr(module.np, "array", guarded_array)
    with pytest.raises(
        SparseModalSubspaceBudgetExceeded, match="provisional_block_columns"
    ):
        extract_certified_sparse_modal_subspace(
            stiffness, mass, certificate, provisional_vectors=provisional
        )


def test_negative_certificate_spend_cannot_increase_remaining_budget():
    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    invalid = replace(
        certificate,
        statistics=replace(certificate.statistics, aggregate_work_units=-1),
    )
    with pytest.raises(SparseModalSubspaceError, match="nonnegative integers"):
        extract_certified_sparse_modal_subspace(stiffness, mass, invalid)


def test_full_sparse_models_never_use_dense_conversion(monkeypatch):
    import structural_analysis.solvers.sparse_modal_subspace as module

    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=2)
    original = module.eigh

    def thin_eigh(a, b, **kwargs):
        assert a.shape == b.shape
        assert (
            a.shape[0] <= certificate.requested_mode_count < certificate.dimension - 1
        )
        return original(a, b, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("full sparse model dense conversion")

    monkeypatch.setattr(csr_matrix, "toarray", forbidden)
    monkeypatch.setattr(csr_matrix, "todense", forbidden)
    monkeypatch.setattr(module, "eigh", thin_eigh)
    result = extract_certified_sparse_modal_subspace(stiffness, mass, certificate)
    assert len(result.clusters[0].mass_normalized_vectors) == 2


def test_external_zero_targets_are_literal_and_live_duck_context_is_rejected():
    stiffness = diags([1.0, 2.0, 5.0, 9.0], format="csr")
    mass = diags(np.ones(4), format="csr")
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=1)
    result = extract_certified_sparse_modal_subspace(
        stiffness,
        mass,
        certificate,
        residual_relative_tolerance=0.0,
        orthogonality_tolerance=0.0,
    )
    assert result.clusters[0].residual_relative_inf_maximum == 0.0
    assert result.clusters[0].mass_orthogonality_error_inf == 0.0
    with pytest.raises(SparseModalSubspaceError, match="context"):
        extract_certified_sparse_modal_subspace(
            stiffness, mass, certificate, _live_session={"minted": True}
        )


def test_requested_prefix_can_exceed_each_certified_block_cap(monkeypatch):
    import structural_analysis.solvers.sparse_modal_subspace as module

    stiffness, mass = diagonal_case()
    certificate = certify_sparse_modal_spectrum(stiffness, mass, mode_count=3)
    budget = replace(SparseModalSubspaceBudget(), maximum_block_columns=2)
    original = module.eigh
    projected_widths = []

    def bounded_ritz(a, b, **kwargs):
        assert a.shape == b.shape
        projected_widths.append(a.shape[0])
        assert a.shape[0] <= budget.maximum_block_columns
        return original(a, b, **kwargs)

    monkeypatch.setattr(module, "eigh", bounded_ritz)
    result = extract_certified_sparse_modal_subspace(
        stiffness, mass, certificate, budget=budget
    )
    assert result.requested_mode_count == 3 > budget.maximum_block_columns
    assert [len(group.eigenvalues) for group in result.clusters] == [2, 1]
    assert projected_widths and max(projected_widths) == 2
    vectors = vector_matrix(result)
    np.testing.assert_allclose(vectors.T @ (mass @ vectors), np.eye(3), atol=1e-12)
    values = np.asarray([value for group in result.clusters for value in group.eigenvalues])
    np.testing.assert_allclose(values, [0.5, 0.5, 3.0], atol=1e-12)
    np.testing.assert_allclose(
        vectors.T @ (stiffness @ vectors), np.diag(values), atol=1e-12
    )
    assert result.statistics.peak_thin_entries <= budget.maximum_thin_entries
