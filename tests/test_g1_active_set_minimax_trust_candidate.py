from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_g1_active_set_minimax_trust_candidate import (  # noqa: E402
    _active_set_minimax_direction,
    run_active_set_minimax_trust_iterations,
)


def test_active_set_minimax_direction_minimizes_linear_inf_residual() -> None:
    stiffness = coo_matrix(([2.0, 4.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsc()
    free = np.asarray([0, 1], dtype=np.int64)
    residual = np.asarray([-1.0, -2.0], dtype=np.float64)

    direction, meta = _active_set_minimax_direction(
        stiffness=stiffness,
        free=free,
        residual=residual,
        active_rows=np.asarray([0, 1], dtype=np.int64),
        dof_count=2,
        trust_radius_m=1.0,
        support_strongest_per_row=1,
    )

    linear_residual = np.asarray(stiffness @ direction, dtype=np.float64) + residual
    assert meta["solver"] == "scipy_linprog_highs_active_set_minimax_cpu_diagnostic"
    assert meta["support_column_count"] == 2
    assert meta["active_linear_residual_inf_n"] <= 1.0e-10
    assert float(np.max(np.abs(linear_residual))) <= 1.0e-10


def test_active_set_minimax_iterations_accepts_residual_descent() -> None:
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

    payload = run_active_set_minimax_trust_iterations(
        assemble_residual=assemble_residual,
        u0=np.asarray([1.0, 1.0], dtype=np.float64),
        max_steps=4,
        active_row_count=2,
        support_strongest_per_row=1,
        trust_radius_m=1.0,
        alpha_values=(1.0, 0.5),
        residual_gate_n=1.0e-8,
    )

    assert payload["summary"]["initial_residual_n"] == 2.0
    assert payload["summary"]["final_residual_n"] <= 1.0e-10
    assert payload["summary"]["residual_gate_passed"] is True
    assert payload["summary"]["steps_taken"] >= 1
    assert payload["history"][0]["accepted"] is True
    assert payload["history"][0]["direction"]["active_linear_residual_inf_n"] <= 1.0e-10


def test_active_set_minimax_iterations_records_active_row_schedule() -> None:
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

    payload = run_active_set_minimax_trust_iterations(
        assemble_residual=assemble_residual,
        u0=np.asarray([1.0, 1.0], dtype=np.float64),
        max_steps=1,
        active_row_count=1,
        active_row_counts=(1, 2),
        support_strongest_per_row=1,
        trust_radius_m=1.0,
        alpha_values=(1.0,),
        residual_gate_n=1.0e-8,
    )

    assert payload["summary"]["active_row_count_schedule"] == [1, 2]
    assert payload["summary"]["support_strongest_per_row"] == 1
    assert len(payload["history"][0]["direction_attempts"]) == 2
    assert payload["summary"]["final_residual_n"] <= 1.0e-10
