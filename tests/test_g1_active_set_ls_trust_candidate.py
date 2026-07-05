from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_g1_active_set_ls_trust_candidate import (  # noqa: E402
    CHECKPOINT_SCHEMA,
    _write_checkpoint,
    run_active_set_ls_trust_iterations,
)


def test_active_set_ls_trust_iterations_accepts_residual_descent() -> None:
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
            {},
        )

    payload = run_active_set_ls_trust_iterations(
        assemble_residual=assemble_residual,
        u0=np.asarray([1.0, 1.0], dtype=np.float64),
        max_steps=4,
        active_row_count=2,
        trust_radius_m=1.0,
        max_lsmr_iterations=8,
        alpha_values=(1.0, 0.5),
        residual_gate_n=1.0e-8,
    )

    assert payload["summary"]["initial_residual_n"] == 2.0
    assert payload["summary"]["final_residual_n"] <= 1.0e-10
    assert payload["summary"]["residual_gate_passed"] is True
    assert payload["summary"]["steps_taken"] >= 1
    assert payload["history"][0]["accepted"] is True


def test_active_set_ls_trust_iterations_selects_best_active_row_count() -> None:
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
            {},
        )

    payload = run_active_set_ls_trust_iterations(
        assemble_residual=assemble_residual,
        u0=np.asarray([1.0, 1.0], dtype=np.float64),
        max_steps=1,
        active_row_count=1,
        active_row_counts=(1, 2),
        trust_radius_m=1.0,
        max_lsmr_iterations=8,
        alpha_values=(1.0,),
        residual_gate_n=1.0e-8,
    )

    assert payload["summary"]["active_row_count_schedule"] == [1, 2]
    assert payload["history"][0]["selected_active_row_count"] == 2
    assert len(payload["history"][0]["direction_attempts"]) == 2
    assert payload["summary"]["final_residual_n"] <= 1.0e-10


def test_write_checkpoint_marks_active_set_candidate_non_promoting(tmp_path: Path) -> None:
    out = tmp_path / "candidate.npz"
    row = _write_checkpoint(
        path=out,
        load_scale=1.0,
        displacement_u=np.asarray([1.5, 1.5], dtype=np.float64),
        final_residual=np.asarray([0.0, 0.0], dtype=np.float64),
        final_rhs=np.asarray([3.0, 6.0], dtype=np.float64),
        steps_taken=2,
        residual_gate_n=5.0e-4,
        frame_tangent_source="force_based_residual_tangent",
        shell_pressure_load_path_policy="all_components",
    )

    assert row["written"] is True
    assert row["schema"] == CHECKPOINT_SCHEMA
    assert row["promotes_g1_closure"] is False
    with np.load(out, allow_pickle=False) as archive:
        assert str(np.asarray(archive["checkpoint_schema"]).item()) == CHECKPOINT_SCHEMA
        assert bool(np.asarray(archive["active_set_ls_candidate_only"]).item()) is True
        assert bool(np.asarray(archive["promotes_g1_closure"]).item()) is False
        assert float(np.asarray(archive["direct_residual_inf_n"]).item()) == 0.0
