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
    run_mgt_equilibrium_preconditioned_zero_probe,
    run_iterative_preconditioned_search,
)
from run_mgt_direct_residual_newton_probe import _load_checkpoint  # noqa: E402


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


def test_preconditioned_zero_probe_writes_standard_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsr()
    free = np.asarray([0], dtype=np.int64)
    input_checkpoint = tmp_path / "input_checkpoint.npz"
    np.savez_compressed(
        input_checkpoint,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        load_scale=np.asarray(1.0, dtype=np.float64),
        displacement_u=np.asarray([0.0], dtype=np.float64),
        residual_inf_n=np.asarray(1.0, dtype=np.float64),
    )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray):
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = np.asarray(stiffness @ u - rhs, dtype=np.float64)
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), {}

        return assemble_residual, {
            "u0": np.asarray([0.0], dtype=np.float64),
            "checkpoint": {"path": str(input_checkpoint)},
            "load_scale": 1.0,
        }

    import run_mgt_equilibrium_preconditioned_zero_probe as probe_module  # noqa: E402

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    output_checkpoint = tmp_path / "preconditioned_checkpoint.npz"

    payload = run_mgt_equilibrium_preconditioned_zero_probe(
        checkpoint_npz=input_checkpoint,
        output_json=None,
        output_final_checkpoint_npz=output_checkpoint,
        start_mode="zero",
        iterative_mode="diagonal_jacobi",
        iterative_alpha_values=(0.0, 1.0),
        max_iterative_corrections=1,
    )

    assert payload["output_final_checkpoint"]["written"] is True
    assert payload["output_final_checkpoint"]["schema"] == "mgt-direct-residual-newton-state.v1"

    meta, u, state_history, residual_history = _load_checkpoint(output_checkpoint)
    assert meta["checkpoint_schema"] == "mgt-direct-residual-newton-state.v1"
    assert meta["residual_inf_n"] <= 1.0e-12
    np.testing.assert_allclose(u, np.asarray([0.1], dtype=np.float64))
    assert state_history is not None
    assert residual_history is not None
    assert state_history.shape[0] == 2
    assert residual_history.shape[0] == 2
