"""Tests for sparse matrix equilibration helpers."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import block_diag, coo_matrix, random as sparse_random

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_coupled_stiffness_unit_audit import audit_coupled_stiffness_diagonals  # noqa: E402
import mgt_sparse_linear_solver as solver_module  # noqa: E402
from mgt_sparse_linear_solver import (  # noqa: E402
    _translation_block_jacobi_precondition,
    build_node_block_jacobi_preconditioner,
    solve_newton_correction,
)
from mgt_sparse_matrix_equilibration import (  # noqa: E402
    symmetric_sqrt_diagonal_scaling,
    unscale_solution,
)


def test_symmetric_scaling_reduces_diagonal_spread() -> None:
    k = coo_matrix(
        (
            [1.0e12, 1.0e12, 1.0, 1.0],
            ([0, 1, 2, 3], [0, 1, 2, 3]),
        ),
        shape=(4, 4),
    ).tocsr()
    rhs = np.asarray([1.0e6, 1.0e6, 1.0, 1.0], dtype=np.float64)
    k_scaled, rhs_scaled, scale, meta = symmetric_sqrt_diagonal_scaling(k, rhs)
    assert meta["applied"] is True
    assert float(np.max(np.abs(k_scaled.diagonal()))) < float(np.max(np.abs(k.diagonal())))
  # true solution x = rhs / diag
    x_true = rhs / np.asarray([1.0e12, 1.0e12, 1.0, 1.0], dtype=np.float64)
    x_scaled = np.linalg.solve(k_scaled.toarray(), rhs_scaled)
    np.testing.assert_allclose(unscale_solution(x_scaled, scale), x_true, rtol=1.0e-9, atol=1.0e-12)


def test_host_ilu_device_gmres_equilibrates_regularized_matrix(monkeypatch) -> None:
    class StopAfterScaling(RuntimeError):
        pass

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

    class FakeTorch:
        cuda = FakeCuda()

        @staticmethod
        def device(name: str) -> str:
            return name

    captured: dict[str, np.ndarray] = {}

    def fake_scaling(k_mat, rhs):
        captured["diag"] = np.asarray(k_mat.diagonal(), dtype=np.float64)
        raise StopAfterScaling()

    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    monkeypatch.setattr(solver_module, "symmetric_sqrt_diagonal_scaling", fake_scaling)

    k = coo_matrix(([0.0, 2.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsr()
    rhs = np.ones(2, dtype=np.float64)
    with pytest.raises(StopAfterScaling):
        solver_module.solve_host_ilu_device_gmres(
            k,
            rhs,
            regularization_factor=0.5,
            equilibrate=True,
        )

    np.testing.assert_allclose(captured["diag"], [0.5, 2.5], rtol=1.0e-12)


def _random_block_spd_matrix(n_nodes: int, seed: int = 7):
    """Random block-sparse SPD-ish matrix with 6x6 nodal diagonal blocks."""
    rng = np.random.default_rng(seed)
    blocks = []
    for _ in range(n_nodes):
        a = rng.standard_normal((6, 6))
        blocks.append(a @ a.T + 6.0 * np.eye(6))
    k = block_diag(blocks, format="csr")
    n = 6 * n_nodes
    off = sparse_random(n, n, density=2.0 / n, random_state=rng, format="csr")
    k = (k + 0.01 * (off + off.T)).tocsr()
    return k


def test_block_jacobi_preconditioner_matches_per_block_solve() -> None:
    n_nodes = 25
    k = _random_block_spd_matrix(n_nodes)
    n = 6 * n_nodes
    free = np.arange(n, dtype=np.int64)
    m_csr, meta = build_node_block_jacobi_preconditioner(k, free_global_dofs=free)
    assert meta["block_count"] == n_nodes
    rng = np.random.default_rng(3)
    v = rng.standard_normal(n)
    applied = m_csr @ v
    expected = np.zeros(n)
    dense = k.toarray()
    for node in range(n_nodes):
        sl = slice(6 * node, 6 * node + 6)
        expected[sl] = np.linalg.solve(dense[sl, sl], v[sl])
    np.testing.assert_allclose(applied, expected, rtol=1.0e-10, atol=1.0e-12)
    # backward-compatible one-shot helper must agree
    legacy = _translation_block_jacobi_precondition(k, v, free_global_dofs=free)
    np.testing.assert_allclose(legacy, expected, rtol=1.0e-10, atol=1.0e-12)


def test_block_jacobi_preconditioner_handles_partial_free_blocks() -> None:
    """Free DOFs that cover only part of a node's 6 components."""
    n_nodes = 4
    k_full = _random_block_spd_matrix(n_nodes, seed=11)
    # restrain a few global DOFs (drop them from the free set)
    restrained = np.asarray([1, 8, 9, 22], dtype=np.int64)
    free = np.setdiff1d(np.arange(6 * n_nodes, dtype=np.int64), restrained)
    k_ff = k_full[free, :][:, free].tocsr()
    m_csr, _meta = build_node_block_jacobi_preconditioner(k_ff, free_global_dofs=free)
    rng = np.random.default_rng(5)
    v = rng.standard_normal(free.size)
    applied = m_csr @ v
    dense = k_ff.toarray()
    expected = np.zeros(free.size)
    node_of = free // 6
    for node in np.unique(node_of):
        rows = np.flatnonzero(node_of == node)
        expected[rows] = np.linalg.solve(dense[np.ix_(rows, rows)], v[rows])
    np.testing.assert_allclose(applied, expected, rtol=1.0e-10, atol=1.0e-12)


def test_block_jacobi_preconditioner_build_is_fast() -> None:
    n_nodes = 1000  # 6000 DOF
    k = _random_block_spd_matrix(n_nodes, seed=2)
    free = np.arange(6 * n_nodes, dtype=np.int64)
    started = time.perf_counter()
    m_csr, meta = build_node_block_jacobi_preconditioner(k, free_global_dofs=free)
    build_seconds = time.perf_counter() - started
    assert build_seconds < 3.0, f"block preconditioner build too slow: {build_seconds:.2f}s"
    assert m_csr.shape == (6 * n_nodes, 6 * n_nodes)
    assert meta["block_count"] == n_nodes
    # singular fallback path stays bounded
    v = np.ones(6 * n_nodes)
    out = m_csr @ v
    assert np.all(np.isfinite(out))


def test_block_jacobi_preconditioner_singular_block_fallback() -> None:
    """An exactly singular nodal block falls back to the diagonal inverse."""
    block = np.zeros((6, 6))
    block[0, 0] = 4.0
    block[1, 1] = 4.0
    block[0, 1] = block[1, 0] = 4.0  # rows 0/1 identical -> singular
    for i in range(2, 6):
        block[i, i] = 2.0
    k = coo_matrix(block).tocsr()
    free = np.arange(6, dtype=np.int64)
    m_csr, meta = build_node_block_jacobi_preconditioner(k, free_global_dofs=free)
    assert meta["singular_block_count"] == 1
    v = np.ones(6)
    out = m_csr @ v
    # fallback is diag(1/|diag|)
    np.testing.assert_allclose(out, v / np.abs(np.diag(block)), rtol=1.0e-12)


def test_newton_correction_regularized_direct_profile_bypasses_iterative_attempts() -> None:
    k = coo_matrix(([4.0], ([0], [0])), shape=(1, 1)).tocsc()
    residual = np.asarray([-1.0], dtype=np.float64)
    correction, meta = solve_newton_correction(
        k,
        residual,
        prefer_host_ilu=True,
        free_global_dofs=np.asarray([0], dtype=np.int64),
        solver_profile="regularized_direct",
    )
    np.testing.assert_allclose(correction, [0.25], rtol=1.0e-10, atol=1.0e-12)
    assert meta["linear_solver_profile"] == "regularized_direct"
    assert meta["linear_solver_regularization_factor"] == 1.0e-12
    assert meta["linear_solver_direct_profile_bypassed_iterative_attempts"] is True
    assert meta["linear_solver_backend"] == "scipy_sparse_spsolve_cpu_regularized_refined"


def test_newton_correction_regularized_direct_profile_accepts_factor_override() -> None:
    k = coo_matrix(([4.0], ([0], [0])), shape=(1, 1)).tocsc()
    residual = np.asarray([-1.0], dtype=np.float64)
    correction, meta = solve_newton_correction(
        k,
        residual,
        prefer_host_ilu=True,
        free_global_dofs=np.asarray([0], dtype=np.int64),
        solver_profile="regularized_direct",
        direct_regularization_factor=1.0e-15,
    )
    np.testing.assert_allclose(correction, [0.25], rtol=1.0e-10, atol=1.0e-12)
    assert meta["linear_solver_regularization_factor"] == 1.0e-15


def test_newton_correction_block_jacobi_profile_bypasses_ilu() -> None:
    k = coo_matrix(([4.0, 3.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsc()
    residual = np.asarray([-8.0, 6.0], dtype=np.float64)
    correction, meta = solve_newton_correction(
        k,
        residual,
        prefer_host_ilu=True,
        free_global_dofs=np.asarray([0, 1], dtype=np.int64),
        solver_profile="block_jacobi_gmres",
    )
    np.testing.assert_allclose(correction, [2.0, -2.0], rtol=1.0e-10, atol=1.0e-12)
    assert meta["linear_solver_profile"] == "block_jacobi_gmres"
    assert meta["linear_solver_diagnostic_profile_bypassed_ilu"] is True
    assert meta["linear_solver_backend"] == "cpu_block_jacobi_gmres"


def test_newton_correction_host_ilu_device_profile_bypasses_cpu_attempts(
    monkeypatch,
) -> None:
    k = coo_matrix(([4.0, 3.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsc()
    residual = np.asarray([-8.0, 6.0], dtype=np.float64)
    calls: list[str] = []

    def fake_host_ilu_device_gmres(*_args, **_kwargs):
        calls.append("host_ilu_device_gmres")
        return {
            "backend": "rocm_torch_sparse_host_ilu_device_gmres",
            "preconditioner": "node_block_jacobi_plus_equilibrated_spilu_host",
            "converged": True,
            "residual_inf_n": 1.0e-9,
            "solve_seconds": 0.125,
            "solution": np.asarray([2.0, -2.0], dtype=np.float64),
            "equilibration": {"applied": True},
        }

    monkeypatch.setattr(
        solver_module,
        "solve_host_ilu_device_gmres",
        fake_host_ilu_device_gmres,
    )

    correction, meta = solve_newton_correction(
        k,
        residual,
        prefer_host_ilu=True,
        free_global_dofs=np.asarray([0, 1], dtype=np.int64),
        solver_profile="host_ilu_device_gmres",
    )

    np.testing.assert_allclose(correction, [2.0, -2.0], rtol=1.0e-10, atol=1.0e-12)
    assert calls == ["host_ilu_device_gmres"]
    assert meta["linear_solver_profile"] == "host_ilu_device_gmres"
    assert meta["linear_solver_backend"] == "rocm_torch_sparse_host_ilu_device_gmres"
    assert meta["linear_solver_attempt"] == "host_ilu_device_gmres_only"
    assert meta["linear_solver_gpu_first_profile"] is True
    assert meta["linear_solver_cpu_attempt_bypassed"] is True


def test_newton_correction_host_ilu_device_profile_reports_unavailable(
    monkeypatch,
) -> None:
    k = coo_matrix(([4.0], ([0], [0])), shape=(1, 1)).tocsc()

    def fake_host_ilu_device_gmres(*_args, **_kwargs):
        raise RuntimeError("No HIP GPUs are available")

    monkeypatch.setattr(
        solver_module,
        "solve_host_ilu_device_gmres",
        fake_host_ilu_device_gmres,
    )

    correction, meta = solve_newton_correction(
        k,
        np.asarray([-1.0], dtype=np.float64),
        free_global_dofs=np.asarray([0], dtype=np.int64),
        solver_profile="host_ilu_device_gmres",
    )

    assert not np.all(np.isfinite(correction))
    assert meta["linear_solver_profile"] == "host_ilu_device_gmres"
    assert meta["linear_solver_breakdown"] == "host_ilu_device_gmres_unavailable"
    assert meta["linear_solver_cpu_attempt_bypassed"] is True


def test_newton_correction_rejects_unknown_solver_profile() -> None:
    k = coo_matrix(([1.0], ([0], [0])), shape=(1, 1)).tocsc()
    with pytest.raises(ValueError, match="solver_profile"):
        solve_newton_correction(
            k,
            np.asarray([1.0], dtype=np.float64),
            solver_profile="surprise",
        )


def test_audit_coupled_stiffness_diagonals_flags_imbalance() -> None:
    frame = coo_matrix(([1.0e3], ([0], [0])), shape=(2, 2)).tocsr()
    spring = coo_matrix(([1.0e12], ([1], [1])), shape=(2, 2)).tocsr()
    audit = audit_coupled_stiffness_diagonals(
        components={"frame": frame, "spring": spring},
        free_global_dofs=np.asarray([0, 1], dtype=np.int64),
        imbalance_ratio_threshold=1.0e6,
    )
    assert audit["unit_consistency_warning"] is True
    assert audit["cross_component_diag_max_ratio"] >= 1.0e9
