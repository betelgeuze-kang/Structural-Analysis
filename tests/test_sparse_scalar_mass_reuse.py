"""Scalar mass preserves the complete spectrum under division by its scalar."""
import numpy as np
import pytest
from scipy.sparse import diags

from structural_analysis.solvers import sparse_generalized_eigen as sparse
from structural_analysis.solvers.modal import solve_modal_modes


@pytest.mark.parametrize("scale", [0.125, 1.0, 7.0])
def test_scalar_mass_reuses_stiffness_extreme_without_losing_accuracy(monkeypatch, scale):
    n = 80
    k = diags([-np.ones(n-1), np.full(n, 3.0), -np.ones(n-1)], [-1, 0, 1], format="csr")
    m = diags(np.full(n, scale), format="csr")
    original = sparse.eigsh
    redundant = []

    def observed(*args, **kwargs):
        if kwargs.get("which") == "LA" and "M" in kwargs:
            redundant.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(sparse, "eigsh", observed)
    result = sparse.solve_sparse_modal_modes(k, m, mode_count=3,
                                           residual_relative_tolerance=1e-10,
                                           orthogonality_tolerance=1e-10)
    reference = solve_modal_modes(k.toarray(), m.toarray(), mode_count=3,
                                 residual_relative_tolerance=1e-10,
                                 orthogonality_tolerance=1e-10)
    assert result.contract_pass and reference.contract_pass
    assert not redundant
    np.testing.assert_allclose(
        [r.eigenvalue_rad2_per_s2 for r in result.modes],
        [r.eigenvalue_rad2_per_s2 for r in reference.modes], rtol=1e-10, atol=1e-12)
    for actual, expected in zip(result.modes, reference.modes):
        a, b = np.array(actual.mass_normalized_shape), np.array(expected.mass_normalized_shape)
        assert min(np.linalg.norm(a-b), np.linalg.norm(a+b)) < 1e-8
    assert sparse.solve_sparse_modal_modes(k, m, mode_count=3,
                                          residual_relative_tolerance=1e-10,
                                          orthogonality_tolerance=1e-10).to_dict() == result.to_dict()


@pytest.mark.parametrize("change", ["one_ulp", "off_diagonal"])
def test_nearly_scalar_mass_keeps_generalized_extreme_path(monkeypatch, change):
    n = 80
    k = diags(np.arange(1.0, n+1), format="csr")
    diagonal = np.ones(n)
    if change == "one_ulp":
        diagonal[0] = np.nextafter(1.0, 2.0)
    m = diags(diagonal, format="csr")
    if change == "off_diagonal":
        m = m + diags([np.full(n-1, 1e-6), np.full(n-1, 1e-6)], [-1, 1])
    original = sparse.eigsh
    calls = []

    def observed(*args, **kwargs):
        if kwargs.get("which") == "LA" and "M" in kwargs:
            calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(sparse, "eigsh", observed)
    assert sparse.solve_sparse_modal_modes(k, m, mode_count=3).contract_pass
    assert len(calls) == 1


@pytest.mark.parametrize("scale", [0.125, 7.0])
def test_scalar_reuse_preserves_rigid_modes_and_cluster_rejection(scale):
    m = diags(np.full(80, scale), format="csr")
    k = diags([0.0, 4.0, 4.0, *np.arange(9.0, 86.0)], format="csr")
    result = sparse.solve_sparse_modal_modes(k, m, mode_count=2)
    assert result.rigid_mode_count == 1
    assert [r.eigenvalue_rad2_per_s2 for r in result.modes] == pytest.approx([4/scale]*2)
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="cuts a repeated or clustered"):
        sparse.solve_sparse_modal_modes(k, m, mode_count=1)
    k = diags([-1.0, *np.arange(1.0, 80.0)], format="csr")
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="positive-semidefinite"):
        sparse.solve_sparse_modal_modes(k, m, mode_count=2)
