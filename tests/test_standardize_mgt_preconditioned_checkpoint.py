from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import standardize_mgt_preconditioned_checkpoint as standardize_module  # noqa: E402
from run_mgt_direct_residual_newton_probe import _load_checkpoint  # noqa: E402


def test_standardize_preconditioned_checkpoint_writes_resume_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsr()
    free = np.asarray([0], dtype=np.int64)
    source_checkpoint = tmp_path / "source_checkpoint.npz"
    source_u = np.asarray([0.1], dtype=np.float64)
    np.savez_compressed(
        source_checkpoint,
        load_scale=np.asarray(1.0, dtype=np.float64),
        displacement_u=source_u,
        residual_inf_n=np.asarray(0.0, dtype=np.float64),
    )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray):
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = np.asarray(stiffness @ u - rhs, dtype=np.float64)
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), {}

        return assemble_residual, {
            "u0": source_u.copy(),
            "checkpoint": {"path": str(source_checkpoint)},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(
        standardize_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    output_checkpoint = tmp_path / "standard_checkpoint.npz"

    payload = standardize_module.run_mgt_preconditioned_checkpoint_standardization(
        source_checkpoint_npz=source_checkpoint,
        output_checkpoint_npz=output_checkpoint,
        output_json=None,
    )

    assert payload["ready"] is True
    assert payload["state_vector_equal"] is True
    assert payload["output_checkpoint"]["schema"] == "mgt-direct-residual-newton-state.v1"

    meta, u, state_history, residual_history = _load_checkpoint(output_checkpoint)
    assert meta["checkpoint_schema"] == "mgt-direct-residual-newton-state.v1"
    assert meta["residual_inf_n"] <= 1.0e-12
    np.testing.assert_allclose(u, source_u)
    assert state_history is not None
    assert residual_history is not None
    assert state_history.shape[0] == 1
    assert residual_history.shape[0] == 1
