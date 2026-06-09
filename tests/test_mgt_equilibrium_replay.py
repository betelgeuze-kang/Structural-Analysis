"""Tests for equilibrium replay gates and Newton loop."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_equilibrium_replay import (  # noqa: E402
    annotate_equilibrium_gates,
    run_equilibrium_newton,
)


def test_equilibrium_newton_converges_linear_spring() -> None:
    k = 4.0
    u_star = 0.25
    f_ext = k * u_star

    def assemble_residual(u: np.ndarray, **_: object):
        stiffness = sp.csc_matrix(np.asarray([[k]], dtype=np.float64))
        free = np.asarray([0], dtype=np.int64)
        residual = np.asarray([k * float(u[0]) - f_ext], dtype=np.float64)
        rhs = np.asarray([f_ext], dtype=np.float64)
        return stiffness, rhs, free, residual, rhs, {}

    result = run_equilibrium_newton(
        u0=np.asarray([0.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        max_newton_iterations=6,
        residual_tolerance_n=1.0e-9,
        prefer_host_ilu=False,
    )

    assert result["converged"] is True
    np.testing.assert_allclose(result["final_u"], [u_star], rtol=1.0e-6, atol=1.0e-9)
    assert result["initial_residual_inf_n"] == f_ext
    assert result["final_residual_inf_n"] <= 1.0e-9


def test_equilibrium_newton_stops_when_already_converged() -> None:
    u0 = np.asarray([0.1], dtype=np.float64)

    def assemble_residual(u: np.ndarray, **_: object):
        stiffness = sp.csc_matrix(np.asarray([[1.0]], dtype=np.float64))
        free = np.asarray([0], dtype=np.int64)
        residual = np.asarray([float(u[0])], dtype=np.float64)
        rhs = np.zeros(1, dtype=np.float64)
        return stiffness, rhs, free, residual, rhs, {}

    result = run_equilibrium_newton(
        u0=u0,
        assemble_residual=assemble_residual,
        max_newton_iterations=4,
        residual_tolerance_n=0.5,
        prefer_host_ilu=False,
    )

    assert result["converged"] is True
    assert result["initial_residual_inf_n"] == 0.1
    assert result["accepted_newton_iteration_count"] == 1


def test_annotate_equilibrium_gates_prefers_replay_over_solver() -> None:
    row = {
        "equilibrium_replay_residual_inf_n": 1.0e-3,
        "solver_residual_inf_n": 1.0e-5,
        "fixed_point_relative_increment": 1.0e-5,
        "displacement_cap_exceeded": False,
    }
    annotate_equilibrium_gates(
        row,
        residual_tolerance_n=5.0e-4,
        relative_increment_tolerance=1.0e-4,
    )
    assert row["equilibrium_replay_gate_passed"] is False
    assert row["solver_residual_gate_passed"] is True
    assert row["ready"] is False
