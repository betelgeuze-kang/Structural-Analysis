"""Positive diagonal mass must preserve rigid modes and the original metric."""
import numpy as np
import pytest
from scipy.sparse import diags

from structural_analysis.solvers import sparse_generalized_eigen as sparse
from structural_analysis.solvers.modal import solve_modal_modes


def test_nonuniform_diagonal_mass_preserves_rigid_and_repeated_modes():
    masses = np.linspace(0.5, 2.0, 80)
    scale = diags(np.sqrt(masses), format="csr")
    spectrum = np.array([0.0, 4.0, 4.0, *np.arange(9.0, 86.0)])
    stiffness = scale @ diags(spectrum, format="csr") @ scale
    mass = diags(masses, format="csr")
    result = sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=2)
    assert result.rigid_mode_count == 1
    assert [m.eigenvalue_rad2_per_s2 for m in result.modes] == pytest.approx([4, 4])
    assert sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=2) == result
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="cuts a repeated"):
        sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=1)


@pytest.mark.parametrize("mass_range", [(0.5, 2.0), (0.1, 10.0)])
def test_nonuniform_diagonal_mass_matches_dense_metric_and_subspace(mass_range):
    n = 80
    masses = np.geomspace(*mass_range, n)
    scale = diags(np.sqrt(masses), format="csr")
    chain = diags([-np.ones(n - 1), np.full(n, 3.0), -np.ones(n - 1)],
                  [-1, 0, 1], format="csr")
    stiffness, mass = scale @ chain @ scale, diags(masses, format="csr")
    result = sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3,
                                           residual_relative_tolerance=1e-10,
                                           orthogonality_tolerance=1e-10)
    reference = solve_modal_modes(stiffness.toarray(), mass.toarray(), mode_count=3)
    np.testing.assert_allclose([m.eigenvalue_rad2_per_s2 for m in result.modes],
                               [m.eigenvalue_rad2_per_s2 for m in reference.modes],
                               rtol=1e-10, atol=1e-12)
    vectors = np.array([m.mass_normalized_shape for m in result.modes]).T
    np.testing.assert_allclose(vectors.T @ (mass @ vectors), np.eye(3), atol=1e-10)
    for actual, expected in zip(result.modes, reference.modes):
        a, b = np.array(actual.mass_normalized_shape), np.array(expected.mass_normalized_shape)
        assert min(np.linalg.norm(a - b), np.linalg.norm(a + b)) < 1e-8
    assert sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3,
                                          residual_relative_tolerance=1e-10,
                                          orthogonality_tolerance=1e-10) == result


def test_off_diagonal_mass_keeps_generalized_path(monkeypatch):
    n = 40
    stiffness = diags(np.arange(1.0, n + 1), format="csr")
    mass = diags([np.full(n - 1, 0.01), np.linspace(1, 2, n), np.full(n - 1, 0.01)],
                 [-1, 0, 1], format="csr")
    original = sparse.eigsh
    generalized = []

    def observed(*args, **kwargs):
        if kwargs.get("M") is not None:
            generalized.append(kwargs["which"])
        return original(*args, **kwargs)

    monkeypatch.setattr(sparse, "eigsh", observed)
    assert sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3).contract_pass
    assert generalized == ["SM", "LA"]


@pytest.mark.parametrize("invalid", [0.0, -1.0, 1e-20, float("nan")])
def test_diagonal_transform_cannot_admit_invalid_mass(invalid):
    masses = np.linspace(0.5, 2, 40)
    masses[0] = invalid
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="mass"):
        sparse.solve_sparse_modal_modes(diags(np.arange(1.0, 41), format="csr"),
                                        diags(masses, format="csr"), mode_count=3)
