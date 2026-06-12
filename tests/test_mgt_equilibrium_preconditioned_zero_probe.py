from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_equilibrium_preconditioned_zero_probe import (  # noqa: E402
    diagonal_jacobi_correction,
    evaluate_correction_line_search,
    node_block_jacobi_correction,
    run_iterative_preconditioned_search,
)


def test_diagonal_jacobi_correction_solves_diagonal_fixture() -> None:
    stiffness = coo_matrix(([4.0, 2.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsr()
    free = np.asarray([0, 1], dtype=np.int64)
    residual = np.asarray([-8.0, 6.0], dtype=np.float64)

    delta, meta = diagonal_jacobi_correction(
        stiffness=stiffness,
        free=free,
        residual=residual,
    )

    np.testing.assert_allclose(delta, [2.0, -3.0], rtol=1.0e-12, atol=1.0e-12)
    assert meta["correction_mode"] == "diagonal_jacobi"
    assert meta["zero_or_tiny_diag_count"] == 0


def test_node_block_jacobi_correction_solves_single_node_block_fixture() -> None:
    block = np.asarray([[4.0, 1.0], [1.0, 3.0]], dtype=np.float64)
    stiffness = coo_matrix(block).tocsr()
    free = np.asarray([0, 1], dtype=np.int64)
    residual = np.asarray([-5.0, -7.0], dtype=np.float64)

    delta, meta = node_block_jacobi_correction(
        stiffness=stiffness,
        free=free,
        residual=residual,
    )

    np.testing.assert_allclose(block @ delta, -residual, rtol=1.0e-12, atol=1.0e-12)
    assert meta["correction_mode"] == "node_block_jacobi"
    assert meta["preconditioner_block_count"] == 1


def test_evaluate_correction_line_search_selects_descent_alpha() -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsr()
    f_ext = np.asarray([1.0], dtype=np.float64)
    free = np.asarray([0], dtype=np.int64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray(stiffness @ u - f_ext, dtype=np.float64)
        return stiffness, f_ext, free, residual, f_ext, {}

    result = evaluate_correction_line_search(
        base_u=np.asarray([0.0], dtype=np.float64),
        base_free=free,
        base_residual_inf=1.0,
        delta=np.asarray([0.1], dtype=np.float64),
        assemble_residual=assemble_residual,
        alpha_values=(0.5, 1.0, 2.0),
    )

    assert result["best_alpha"] == 1.0
    assert result["best_residual_inf_n"] == 0.0
    assert result["residual_descent"] is True


def test_run_iterative_preconditioned_search_accepts_descent_step() -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsr()
    f_ext = np.asarray([1.0], dtype=np.float64)
    free = np.asarray([0], dtype=np.int64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray(stiffness @ u - f_ext, dtype=np.float64)
        return stiffness, f_ext, free, residual, f_ext, {}

    result = run_iterative_preconditioned_search(
        u0=np.asarray([0.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        mode="diagonal_jacobi",
        alpha_values=(0.0, 1.0),
        max_iterations=2,
    )

    assert result["accepted_iteration_count"] == 1
    assert result["final_residual_inf_n"] == 0.0
    assert result["residual_gate_passed"] is True
