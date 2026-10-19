"""Exact diagonal spectra certify full rigid multiplicity before extraction."""

from fractions import Fraction

import numpy as np
import pytest
from scipy.sparse import csr_matrix, diags

from structural_analysis.solvers import sparse_generalized_eigen as sparse


def _rank_diagonal(zeros):
    stiffness = np.zeros(80)
    positive = [index for index in range(80) if index not in zeros]
    stiffness[positive] = np.arange(1.0, len(positive) + 1.0)
    return stiffness


@pytest.mark.parametrize(
    "zeros,mass_kind",
    [
        ([0, 40, 79], "identity"),
        ([0, 20, 40, 79], "scalar"),
        ([0, 40, 79], "nonuniform"),
    ],
)
def test_known_coordinate_zero_multiplicity_counterexamples(zeros, mass_kind):
    stiffness = _rank_diagonal(zeros)
    if mass_kind == "identity":
        masses = np.ones(80)
    elif mass_kind == "scalar":
        masses = np.full(80, 0.125)
    else:
        masses = np.exp2((np.arange(80) % 7) - 3)
        stiffness *= masses
    exact = sorted(
        Fraction.from_float(float(k)) / Fraction.from_float(float(m))
        for k, m in zip(stiffness, masses)
    )
    result = sparse.solve_sparse_modal_modes(
        diags(stiffness, format="csr"), diags(masses, format="csr"), mode_count=3
    )
    assert result.rigid_mode_count == len(zeros)
    assert [mode.eigenvalue_rad2_per_s2 for mode in result.modes] == pytest.approx(
        [float(value) for value in exact if value > 0][:3], rel=1e-10, abs=1e-12
    )
    assert result.backend_profile == sparse.SPARSE_DIAGONAL_MODAL_PROFILE
    assert result.candidate_eigenpair_count == 80
    assert result.contract_pass and not result.fallback_used
    assert not result.regularization_applied


def _forbid_arpack_and_factorization(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Exact diagonal input must select its route in advance")

    monkeypatch.setattr(sparse, "eigsh", forbidden)
    monkeypatch.setattr(sparse, "splu", forbidden)


@pytest.mark.parametrize("zeros", [[0], [40], [79], list(range(20))])
def test_direct_coordinate_route_knows_all_rigid_modes(monkeypatch, zeros):
    _forbid_arpack_and_factorization(monkeypatch)
    stiffness = _rank_diagonal(zeros)
    masses = np.linspace(0.5, 2.0, 80)
    result = sparse.solve_sparse_modal_modes(
        diags(stiffness * masses, format="csr"),
        diags(masses, format="csr"),
        mode_count=3,
    )
    assert result.rigid_mode_count == len(zeros)
    assert result.candidate_eigenpair_count == 80
    assert [mode.eigenvalue_rad2_per_s2 for mode in result.modes] == pytest.approx(
        [1, 2, 3]
    )


def test_full_spectrum_scale_classifies_both_sides_of_rigid_boundary(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    spectrum = np.arange(1.0, 81.0)
    spectrum[:4] = [0, np.nextafter(1.0, 0.0), 1.0, np.nextafter(1.0, 2.0)]
    spectrum[-1] = 1e10
    result = sparse.solve_sparse_modal_modes(
        diags(spectrum, format="csr"),
        diags(np.ones(80), format="csr"),
        mode_count=1,
    )
    assert result.rigid_mode_count == 3
    assert result.modes[0].eigenvalue_rad2_per_s2 == np.nextafter(1.0, 2.0)


def test_explicitly_stored_zero_entries_are_exact_diagonal_input(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    diagonal = _rank_diagonal([0, 40, 79])
    indices = np.arange(80)
    stiffness = csr_matrix((diagonal, (indices, indices)), shape=(80, 80))
    mass = csr_matrix(
        (np.r_[np.ones(80), 0.0], (np.r_[indices, 0], np.r_[indices, 1])),
        shape=(80, 80),
    )
    assert stiffness.nnz == 80 and mass.nnz == 81
    result = sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3)
    assert result.rigid_mode_count == 3
    assert result.backend_profile == sparse.SPARSE_DIAGONAL_MODAL_PROFILE


def test_zero_rigid_tolerance_retains_a_small_positive_mode(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    spectrum = np.arange(1.0, 81.0)
    spectrum[:2] = [0, 1e-12]
    result = sparse.solve_sparse_modal_modes(
        diags(spectrum, format="csr"),
        diags(np.ones(80), format="csr"),
        mode_count=2,
        rigid_mode_relative_tolerance=0,
    )
    assert result.rigid_mode_count == 1
    assert [mode.eigenvalue_rad2_per_s2 for mode in result.modes] == [1e-12, 3.0]


def test_repeated_diagonal_modes_keep_metric_coordinate_order_and_cluster_gate(
    monkeypatch,
):
    _forbid_arpack_and_factorization(monkeypatch)
    masses = np.exp2((np.arange(80) % 7) - 3)
    spectrum = np.arange(20.0, 100.0)
    spectrum[0] = 0
    spectrum[[20, 40]] = 4
    stiffness = diags(spectrum * masses, format="csr")
    mass = diags(masses, format="csr")
    result = sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=2)
    expected = np.zeros((2, 80))
    expected[0, 20] = 1 / np.sqrt(masses[20])
    expected[1, 40] = 1 / np.sqrt(masses[40])
    np.testing.assert_allclose(
        [mode.mass_normalized_shape for mode in result.modes], expected, atol=1e-15
    )
    np.testing.assert_allclose(
        [mode.generalized_mass for mode in result.modes], [1, 1], atol=1e-15
    )
    assert sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=2) == result
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="cuts a repeated"):
        sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=1)


@pytest.mark.parametrize("invalid", [0.0, -1.0, 1e-20, float("nan"), float("inf")])
def test_diagonal_route_does_not_relax_mass_admission(monkeypatch, invalid):
    _forbid_arpack_and_factorization(monkeypatch)
    masses = np.ones(80)
    masses[40] = invalid
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="mass"):
        sparse.solve_sparse_modal_modes(
            diags(np.arange(1.0, 81.0), format="csr"),
            diags(masses, format="csr"),
            mode_count=3,
        )


@pytest.mark.parametrize("invalid", [-1.0, float("nan"), float("inf")])
def test_diagonal_route_does_not_relax_stiffness_admission(monkeypatch, invalid):
    _forbid_arpack_and_factorization(monkeypatch)
    stiffness = np.arange(1.0, 81.0)
    stiffness[0] = invalid
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="stiffness"):
        sparse.solve_sparse_modal_modes(
            diags(stiffness, format="csr"),
            diags(np.ones(80), format="csr"),
            mode_count=3,
        )


def test_existing_psd_tolerance_is_used_before_full_diagonal_classification(
    monkeypatch,
):
    _forbid_arpack_and_factorization(monkeypatch)
    stiffness = _rank_diagonal([0])
    stiffness[0] = -1e-9
    mass = diags(np.ones(80), format="csr")
    result = sparse.solve_sparse_modal_modes(
        diags(stiffness, format="csr"), mass, mode_count=3
    )
    assert result.rigid_mode_count == 1
    with pytest.raises(
        sparse.SparseGeneralizedEigenError, match="positive-semidefinite"
    ):
        sparse.solve_sparse_modal_modes(
            diags(stiffness, format="csr"),
            mass,
            mode_count=3,
            positive_semidefinite_relative_tolerance=0,
        )


def test_rigid_scale_includes_a_negative_ratio_permitted_by_k_psd_tolerance(
    monkeypatch,
):
    _forbid_arpack_and_factorization(monkeypatch)
    stiffness = np.arange(1.0, 81.0)
    stiffness[:2] = [-1e-9, 5e-8]
    masses = np.ones(80)
    masses[0] = 1e-12
    result = sparse.solve_sparse_modal_modes(
        diags(stiffness, format="csr"),
        diags(masses, format="csr"),
        mode_count=3,
    )
    # K's configured PSD tolerance admits its small negative diagonal. Its
    # generalized ratio has magnitude1000, defining the full spectral cutoff.
    assert result.rigid_mode_count == 2
    assert [mode.eigenvalue_rad2_per_s2 for mode in result.modes] == [3, 4, 5]


@pytest.mark.parametrize("factor,admitted", [(0.5, False), (2.0, True)])
def test_diagonal_mass_preserves_existing_numerical_spd_boundary(
    monkeypatch,
    factor,
    admitted,
):
    _forbid_arpack_and_factorization(monkeypatch)
    masses = np.ones(80)
    masses[40] = factor * np.finfo(float).eps * 80
    stiffness = diags(_rank_diagonal([40]), format="csr")
    mass = diags(masses, format="csr")
    if admitted:
        result = sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3)
        assert result.rigid_mode_count == 1
    else:
        with pytest.raises(sparse.SparseGeneralizedEigenError, match="mass"):
            sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3)


def test_all_rigid_diagonal_input_fails_without_retry(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="only 0"):
        sparse.solve_sparse_modal_modes(
            diags(np.zeros(80), format="csr"),
            diags(np.ones(80), format="csr"),
            mode_count=3,
        )


def test_nonfinite_diagonal_ratio_is_rejected_without_retry(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="spectrum.*finite"):
        sparse.solve_sparse_modal_modes(
            diags(np.ones(80), format="csr"),
            diags(np.full(80, 1e-310), format="csr"),
            mode_count=3,
        )


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_nonzero_diagonal_ratio_sign_loss_is_rejected(monkeypatch, sign):
    _forbid_arpack_and_factorization(monkeypatch)
    stiffness = [sign * 1e-310, 1e30, 2e30, 3e30, 4e30]
    masses = np.full(5, 1e30)
    exact = Fraction.from_float(stiffness[0]) / Fraction.from_float(masses[0])
    assert exact != 0 and (exact > 0) == (sign > 0)
    with pytest.raises(sparse.SparseGeneralizedEigenError, match="not representable"):
        sparse.solve_sparse_modal_modes(
            diags(stiffness, format="csr"),
            diags(masses, format="csr"),
            mode_count=1,
            rigid_mode_relative_tolerance=0,
        )


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_representable_subnormal_ratio_preserves_sign_and_original_gates(
    monkeypatch,
    sign,
):
    _forbid_arpack_and_factorization(monkeypatch)
    tiny = np.nextafter(0.0, 1.0)
    result = sparse.solve_sparse_modal_modes(
        diags([sign * tiny, 1, 2, 3, 4], format="csr"),
        diags(np.ones(5), format="csr"),
        mode_count=1,
        rigid_mode_relative_tolerance=0,
    )
    assert result.stiffness_minimum_eigenvalue_estimate == sign * tiny
    assert result.rigid_mode_count == (0 if sign > 0 else 1)
    assert result.modes[0].eigenvalue_rad2_per_s2 == (tiny if sign > 0 else 1)


def test_actual_signed_zero_diagonal_entries_remain_rigid(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    result = sparse.solve_sparse_modal_modes(
        diags([0.0, -0.0, 1e30, 2e30, 3e30], format="csr"),
        diags(np.full(5, 1e30), format="csr"),
        mode_count=1,
        rigid_mode_relative_tolerance=0,
    )
    assert result.rigid_mode_count == 2
    assert result.modes[0].eigenvalue_rad2_per_s2 == pytest.approx(1)


def test_diagonal_route_materializes_only_requested_coordinate_vectors(monkeypatch):
    _forbid_arpack_and_factorization(monkeypatch)
    original = sparse.np.zeros
    allocations = []

    def observed(shape, *args, **kwargs):
        allocations.append(shape)
        assert shape != (80, 80)
        return original(shape, *args, **kwargs)

    monkeypatch.setattr(sparse.np, "zeros", observed)
    result = sparse.solve_sparse_modal_modes(
        diags(_rank_diagonal([0, 40, 79]), format="csr"),
        diags(np.ones(80), format="csr"),
        mode_count=3,
    )
    assert result.rigid_mode_count == 3
    assert (80, 3) in allocations


@pytest.mark.parametrize("coupled", ["stiffness", "mass", "projected_stiffness"])
def test_off_diagonal_input_uses_guarded_counts_after_numeric_admission(
    monkeypatch, coupled
):
    stiffness = diags(np.arange(1.0, 81.0), format="csr")
    mass = diags(np.ones(80), format="csr")
    off = diags(np.full(79, 1e-16), 1, shape=(80, 80), format="csr")
    if coupled == "stiffness":
        stiffness = stiffness + off + off.T
    elif coupled == "mass":
        mass = mass + off + off.T
    else:
        stiffness = stiffness + off - off.T
    original = sparse.eigsh
    original_prefix = sparse._count_guarded_coupled_modal_prefix
    calls = []
    prefix_inputs = []

    def observed(*args, **kwargs):
        calls.append(kwargs["which"])
        return original(*args, **kwargs)

    def observed_prefix(k_matrix, m_matrix, **kwargs):
        prefix_inputs.append((k_matrix.toarray(), m_matrix.toarray()))
        return original_prefix(k_matrix, m_matrix, **kwargs)

    monkeypatch.setattr(sparse, "eigsh", observed)
    monkeypatch.setattr(sparse, "_count_guarded_coupled_modal_prefix", observed_prefix)
    result = sparse.solve_sparse_modal_modes(stiffness, mass, mode_count=3)
    assert result.contract_pass
    assert len(prefix_inputs) == 1
    np.testing.assert_array_equal(
        prefix_inputs[0][0], (0.5 * (stiffness + stiffness.T)).toarray()
    )
    np.testing.assert_array_equal(
        prefix_inputs[0][1], (0.5 * (mass + mass.T)).toarray()
    )
    assert [mode.eigenvalue_rad2_per_s2 for mode in result.modes] == pytest.approx(
        [1.0, 2.0, 3.0]
    )
    assert result.backend_profile == sparse.SPARSE_COUNT_GUARDED_MODAL_PROFILE
    assert result.candidate_eigenpair_count < result.dof_count
    if coupled == "projected_stiffness":
        # Projected extrema are exactly diagonal, but the raw input still needs
        # the complete count guards rather than the analytic modal shortcut.
        assert calls == []
        assert result.stiffness_minimum_eigenvalue_estimate == 1.0
        assert result.mass_minimum_eigenvalue_estimate == 1.0
    else:
        assert "SA" in calls and "LA" in calls
    assert "SM" not in calls
    assert result.symmetry_projection_applied == (coupled == "projected_stiffness")
    diagnostics = result.certificate_diagnostics
    assert diagnostics is not None
    certificate = diagnostics["certificate"]
    guard = diagnostics["public_threshold_guard"]
    assert guard["stiffness_input_hash"] == certificate["stiffness_input_hash"]
    assert guard["mass_input_hash"] == certificate["mass_input_hash"]
    assert guard["less_or_equal"] == result.rigid_mode_count == 0
    assert diagnostics["stiffness_psd_guard"] is not None
    assert diagnostics["mass_spd_guard"] is not None
