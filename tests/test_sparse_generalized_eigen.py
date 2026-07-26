"""Contract tests for sparse modal and linear-buckling extraction."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags

from structural_analysis.solvers.buckling import solve_linear_buckling
from structural_analysis.solvers.modal import solve_modal_modes
from structural_analysis.solvers.sparse_generalized_eigen import (
    SPARSE_BUCKLING_PROFILE,
    SPARSE_MODAL_PROFILE,
    SparseGeneralizedEigenError,
    solve_sparse_linear_buckling,
    solve_sparse_modal_modes,
)


def test_sparse_modal_matches_dense_reference_without_fallback() -> None:
    diagonal = np.arange(1.0, 81.0, dtype=np.float64)
    stiffness = diags(diagonal, format="csr")
    mass = diags(np.ones(80), format="csr")

    sparse = solve_sparse_modal_modes(stiffness, mass, mode_count=3)
    dense = solve_modal_modes(stiffness.toarray(), mass.toarray(), mode_count=3)

    assert [mode.eigenvalue_rad2_per_s2 for mode in sparse.modes] == pytest.approx(
        [mode.eigenvalue_rad2_per_s2 for mode in dense.modes],
        rel=1.0e-11,
        abs=1.0e-12,
    )
    assert sparse.backend_profile == SPARSE_MODAL_PROFILE
    assert sparse.native_sparse_input is True
    assert sparse.regularization_applied is False
    assert sparse.fallback_used is False
    assert sparse.contract_pass is True
    assert sparse.candidate_eigenpair_count < sparse.dof_count
    assert max(mode.residual_relative_inf for mode in sparse.modes) <= 1.0e-9


def test_sparse_modal_is_repeatable_and_canonicalizes_complete_cluster() -> None:
    stiffness = diags([4.0, 4.0, *np.arange(9.0, 87.0)], format="csr")
    mass = diags(np.ones(80), format="csr")

    first = solve_sparse_modal_modes(stiffness, mass, mode_count=2)
    second = solve_sparse_modal_modes(stiffness, mass, mode_count=2)

    assert first.to_dict() == second.to_dict()
    np.testing.assert_allclose(
        np.asarray([mode.mass_normalized_shape for mode in first.modes]),
        np.eye(2, 80),
        atol=1.0e-11,
    )
    assert first.raw_result_hash == second.raw_result_hash
    assert first.semantic_result_hash == second.semantic_result_hash


def test_sparse_modal_rejects_cluster_cut_and_invalid_matrices() -> None:
    repeated = diags([4.0, 4.0, *np.arange(9.0, 87.0)], format="csr")
    identity = diags(np.ones(80), format="csr")
    with pytest.raises(
        SparseGeneralizedEigenError,
        match="cuts a repeated or clustered",
    ):
        solve_sparse_modal_modes(repeated, identity, mode_count=1)

    asymmetric_dense = np.eye(80, dtype=np.float64)
    asymmetric_dense[0, 1] = 0.1
    asymmetric = csr_matrix(asymmetric_dense)
    with pytest.raises(SparseGeneralizedEigenError, match="symmetry error"):
        solve_sparse_modal_modes(asymmetric, identity, mode_count=1)

    singular_mass = diags([0.0, *np.ones(79)], format="csr")
    with pytest.raises(SparseGeneralizedEigenError, match="positive definite"):
        solve_sparse_modal_modes(identity, singular_mass, mode_count=1)

    nonfinite = identity.copy()
    nonfinite.data[0] = np.nan
    with pytest.raises(SparseGeneralizedEigenError, match="finite values"):
        solve_sparse_modal_modes(nonfinite, identity, mode_count=1)


def test_sparse_buckling_matches_dense_finite_factors_for_singular_kg() -> None:
    stiffness = diags(np.ones(80), format="csr")
    geometric_diagonal = np.zeros(80, dtype=np.float64)
    geometric_diagonal[:20] = 1.0 / np.arange(1.0, 21.0)
    geometric = diags(geometric_diagonal, format="csr")

    sparse = solve_sparse_linear_buckling(stiffness, geometric, mode_count=3)
    dense = solve_linear_buckling(
        stiffness.toarray(),
        geometric.toarray(),
        mode_count=3,
    )

    assert [mode.load_factor for mode in sparse.modes] == pytest.approx(
        [mode.load_factor for mode in dense.modes],
        rel=1.0e-8,
        abs=1.0e-10,
    )
    assert sparse.backend_profile == SPARSE_BUCKLING_PROFILE
    assert sparse.native_sparse_input is True
    assert sparse.regularization_applied is False
    assert sparse.fallback_used is False
    assert sparse.contract_pass is True
    assert sparse.finite_positive_eigenvalue_count_lower_bound >= 3
    assert sparse.geometric_stiffness_positive_rank_lower_bound >= 3
    assert sparse.candidate_eigenpair_count < sparse.dof_count


def test_sparse_buckling_is_repeatable_and_rejects_cluster_cut() -> None:
    stiffness = diags([4.0, 4.0, *np.arange(9.0, 87.0)], format="csr")
    geometric = diags(np.ones(80), format="csr")

    first = solve_sparse_linear_buckling(stiffness, geometric, mode_count=2)
    second = solve_sparse_linear_buckling(stiffness, geometric, mode_count=2)

    assert first.to_dict() == second.to_dict()
    np.testing.assert_allclose(
        np.asarray([mode.max_component_normalized_shape for mode in first.modes]),
        np.eye(2, 80),
        atol=1.0e-8,
    )
    with pytest.raises(
        SparseGeneralizedEigenError,
        match="cuts a repeated or clustered",
    ):
        solve_sparse_linear_buckling(stiffness, geometric, mode_count=1)


def test_sparse_buckling_rejects_dense_fallback_scope_and_invalid_kg() -> None:
    with pytest.raises(SparseGeneralizedEigenError, match="mode_count <= dof_count"):
        solve_sparse_linear_buckling(
            diags(np.ones(2), format="csr"),
            diags(np.ones(2), format="csr"),
            mode_count=1,
        )

    stiffness = diags(np.ones(80), format="csr")
    indefinite_geometric = diags([-1.0, *np.ones(79)], format="csr")
    with pytest.raises(
        SparseGeneralizedEigenError,
        match="positive-semidefinite contract",
    ):
        solve_sparse_linear_buckling(
            stiffness,
            indefinite_geometric,
            mode_count=1,
        )
