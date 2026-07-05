from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_g1_active_frontier_shell_rotation_row_probe as probe  # noqa: E402


def test_select_rotation_rows_prefers_shell_bending_ownership_rows() -> None:
    residual = np.asarray([1.0, -3.0, 2.0], dtype=np.float64)
    free = np.asarray([0, 9, 14], dtype=np.int64)
    ownership = {
        "residual_ownership_breakdown": {
            "top_rows": [
                {
                    "global_dof": 9,
                    "dof_label": "RX",
                    "dominant_internal_component": "shell_bending_drilling",
                },
                {
                    "global_dof": 14,
                    "dof_label": "UZ",
                    "dominant_internal_component": "shell_bending_drilling",
                },
            ]
        }
    }

    rows = probe._select_rotation_rows(
        residual=residual,
        free=free,
        max_rows=2,
        ownership_payload=ownership,
    )

    assert rows[0]["global_dof"] == 9
    assert rows[0]["dof_label"] == "RX"
    assert rows[0]["base_residual_n"] == -3.0
    assert len(rows) == 1


def test_shell_rotation_row_probe_reduces_linear_rotation_residual() -> None:
    stiffness = coo_matrix(
        ([2.0, 4.0], ([3, 9], [3, 9])),
        shape=(12, 12),
    ).tocsc()
    free = np.asarray([3, 9], dtype=np.int64)
    rhs = np.asarray([2.0, 4.0], dtype=np.float64)

    def assemble_residual(u: np.ndarray, **_kwargs):
        residual = np.asarray(
            [2.0 * float(u[3]) - 1.0, 4.0 * float(u[9]) + 2.0],
            dtype=np.float64,
        )
        return stiffness, np.zeros(12, dtype=np.float64), free, residual, rhs, {}

    ownership = {
        "residual_ownership_breakdown": {
            "top_rows": [
                {
                    "global_dof": 9,
                    "dof_label": "RX",
                    "dominant_internal_component": "shell_bending_drilling",
                },
                {
                    "global_dof": 3,
                    "dof_label": "RX",
                    "dominant_internal_component": "shell_bending_drilling",
                },
            ]
        }
    }

    result = probe.run_shell_rotation_row_probe(
        assemble_residual=assemble_residual,
        u0=np.zeros(12, dtype=np.float64),
        ownership_payload=ownership,
        max_rows=2,
        fd_step=1.0e-6,
        alpha_values=(1.0,),
        residual_gate_n=1.0e-8,
    )

    assert result["summary"]["selected_rotation_row_count"] == 2
    assert result["summary"]["fd_consistent"] is True
    assert result["summary"]["direct_descent_observed"] is True
    assert result["summary"]["best_direct_residual_inf_n"] <= 1.0e-10
    assert result["best_candidate"]["residual_gate_passed"] is True


def test_write_checkpoint_marks_rotation_candidate_non_promoting(tmp_path: Path) -> None:
    out = tmp_path / "rotation-candidate.npz"

    row = probe._write_checkpoint(
        path=out,
        load_scale=1.0,
        displacement_u=np.zeros(12, dtype=np.float64),
        final_residual=np.asarray([0.25, 0.0], dtype=np.float64),
        final_rhs=np.asarray([2.0, 4.0], dtype=np.float64),
        residual_gate_n=5.0e-4,
        shell_pressure_load_path_policy="structural_components_only",
        best_alpha=0.25,
    )

    assert row["written"] is True
    assert row["promotes_g1_closure"] is False
    assert row["shell_pressure_load_path_policy"] == "structural_components_only"
    with np.load(out, allow_pickle=False) as archive:
        assert str(np.asarray(archive["checkpoint_schema"]).item()) == (
            probe.CHECKPOINT_SCHEMA
        )
        assert bool(np.asarray(archive["shell_rotation_row_candidate_only"]).item()) is True
        assert bool(np.asarray(archive["promotes_g1_closure"]).item()) is False
        assert float(np.asarray(archive["direct_residual_inf_n"]).item()) == 0.25
