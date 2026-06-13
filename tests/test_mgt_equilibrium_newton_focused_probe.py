from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_equilibrium_newton_focused_probe as probe_module  # noqa: E402
from run_mgt_direct_residual_newton_probe import _load_checkpoint  # noqa: E402


def test_equilibrium_newton_focused_writes_resumable_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    u0 = np.asarray([0.3], dtype=np.float64)
    checkpoint = tmp_path / "input_checkpoint.npz"
    np.savez_compressed(
        checkpoint,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        load_scale=np.asarray(1.0, dtype=np.float64),
        displacement_u=u0,
        residual_inf_n=np.asarray(2.0, dtype=np.float64),
        max_translation_m=np.asarray(0.3, dtype=np.float64),
        accepted_state_history_u=np.vstack([u0]),
        accepted_residual_history=np.vstack([np.asarray([2.0], dtype=np.float64)]),
    )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = internal - rhs
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), {}

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": str(checkpoint)},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    output_checkpoint = tmp_path / "focused_checkpoint.npz"
    payload = probe_module.run_mgt_equilibrium_newton_focused_probe(
        checkpoint_npz=checkpoint,
        output_json=None,
        output_final_checkpoint_npz=output_checkpoint,
        max_newton_iterations=1,
        linear_solver_profile="regularized_direct",
    )

    assert payload["status"] == "ready"
    assert payload["equilibrium_newton_ready"] is True
    assert payload["final_residual_inf_n"] <= 1.0e-9
    assert payload["output_final_checkpoint"]["written"] is True
    assert payload["output_final_checkpoint"]["path"] == str(output_checkpoint)

    meta, u, state_history, residual_history = _load_checkpoint(output_checkpoint)
    assert meta["checkpoint_schema"] == "mgt-direct-residual-newton-state.v1"
    assert meta["residual_inf_n"] <= 1.0e-9
    assert np.allclose(u, np.asarray([0.1], dtype=np.float64))
    assert state_history is not None
    assert residual_history is not None
    assert state_history.shape[0] == 2
    assert residual_history.shape[0] == 2
