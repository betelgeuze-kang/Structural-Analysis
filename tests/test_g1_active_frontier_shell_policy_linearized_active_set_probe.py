from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_g1_active_frontier_shell_policy_linearized_active_set_probe as probe  # noqa: E402


def test_row_descriptor_maps_global_dof_to_node_and_label() -> None:
    row = probe._row_descriptor(
        free=np.asarray([0, 13, 20], dtype=np.int64),
        residual=np.asarray([1.0, -2.0, 3.0], dtype=np.float64),
        row=1,
    )

    assert row == {
        "reduced_row": 1,
        "global_dof": 13,
        "node_index": 2,
        "node_id": 3,
        "dof_label": "UY",
        "residual_n": -2.0,
    }


def test_linearized_active_set_probe_reports_best_linear_descent() -> None:
    stiffness = coo_matrix(([2.0, 4.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsc()
    free = np.asarray([0, 1], dtype=np.int64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray(
            [2.0 * float(u[0]) - 3.0, 4.0 * float(u[1]) - 6.0],
            dtype=np.float64,
        )
        return (
            stiffness,
            np.asarray([3.0, 6.0], dtype=np.float64),
            free,
            residual,
            np.asarray([3.0, 6.0], dtype=np.float64),
            {"load_scale": 1.0},
        )

    payload = probe.run_linearized_active_set_probe(
        assemble_residual=assemble_residual,
        u0=np.asarray([1.0, 1.0], dtype=np.float64),
        active_row_counts=(1, 2),
        trust_radius_m=1.0,
        max_lsmr_iterations=8,
        residual_gate_n=1.0e-8,
    )

    assert payload["summary"]["base_residual_inf_n"] == 2.0
    assert payload["summary"]["evaluated_active_row_count_schedule"] == [1, 2]
    assert payload["summary"]["best_active_row_count"] in {1, 2}
    assert payload["summary"]["linearized_active_descent_observed"] is True
    assert payload["summary"]["best_linear_active_residual_after_inf_n"] <= 1.0e-10
    assert payload["summary"]["direct_replay_attempted"] is False
    assert payload["summary"]["direct_replay_required_for_candidate"] is True
    assert len(payload["attempts"]) == 2
