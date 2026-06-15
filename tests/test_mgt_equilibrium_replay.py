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


def test_equilibrium_newton_uses_residual_only_line_search_when_supported() -> None:
    k = 4.0
    u_star = 0.25
    f_ext = k * u_star
    full_assembly_calls = 0
    residual_only_calls = 0

    def assemble_residual(
        u: np.ndarray,
        *,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
        external_load_override: np.ndarray | None = None,
        **_: object,
    ):
        nonlocal full_assembly_calls, residual_only_calls
        stiffness = sp.csc_matrix(np.asarray([[k]], dtype=np.float64))
        free = np.asarray([0], dtype=np.int64)
        if residual_only:
            residual_only_calls += 1
            assert free_override is not None
            free = np.asarray(free_override, dtype=np.int64)
            stiffness_out = None
        else:
            full_assembly_calls += 1
            stiffness_out = stiffness
        f_full = (
            np.asarray(external_load_override, dtype=np.float64)
            if external_load_override is not None
            else np.asarray([f_ext], dtype=np.float64)
        )
        residual = np.asarray([k * float(u[0]) - f_full[0]], dtype=np.float64)
        rhs = np.asarray([f_full[0]], dtype=np.float64)
        return stiffness_out, f_full.copy(), free.copy(), residual, rhs, {
            "residual_only_assembly": bool(residual_only),
            "shell_operator_cache_size": 1,
            "shell_meta": {
                "shell_internal_force_cache_enabled": True,
                "shell_internal_force_cache_hit": bool(residual_only),
            },
        }

    assemble_residual.supports_residual_only = True  # type: ignore[attr-defined]

    result = run_equilibrium_newton(
        u0=np.asarray([0.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        max_newton_iterations=1,
        residual_tolerance_n=1.0e-9,
        prefer_host_ilu=False,
        linear_solver_profile="regularized_direct",
        line_search_alphas=(1.0, 0.5),
    )

    assert result["converged"] is True
    assert result["line_search_residual_only_supported"] is True
    assert full_assembly_calls == 2
    assert residual_only_calls == 2
    assert all(
        trial["residual_only_assembly"]
        for trial in result["iterations"][0]["trial_rows"]
    )
    assert all(
        trial["shell_internal_force_cache_hit"]
        for trial in result["iterations"][0]["trial_rows"]
    )
    assert all(
        trial["shell_operator_cache_size"] == 1
        for trial in result["iterations"][0]["trial_rows"]
    )
    np.testing.assert_allclose(result["final_u"], [u_star], rtol=1.0e-6, atol=1.0e-9)


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


def test_equilibrium_newton_can_force_increment_gate_after_residual_gate() -> None:
    stiffness = sp.csc_matrix(np.asarray([[1.0]], dtype=np.float64))
    f_ext = 1.0

    def assemble_residual(u: np.ndarray, **_: object):
        free = np.asarray([0], dtype=np.int64)
        residual = np.asarray([float(u[0]) - f_ext], dtype=np.float64)
        rhs = np.asarray([f_ext], dtype=np.float64)
        return stiffness, rhs, free, residual, rhs, {}

    result = run_equilibrium_newton(
        u0=np.asarray([0.99], dtype=np.float64),
        assemble_residual=assemble_residual,
        max_newton_iterations=2,
        residual_tolerance_n=2.0e-2,
        relative_increment_tolerance=2.0e-2,
        prefer_host_ilu=False,
        linear_solver_profile="regularized_direct",
        min_newton_iterations_before_residual_stop=1,
        require_relative_increment_gate_for_convergence=True,
    )

    assert result["converged"] is True
    assert "best_residual_inf_n" in result["iterations"][0]
    assert result["iterations"][0]["relative_increment"] <= 2.0e-2
    assert result["final_residual_inf_n"] <= 2.0e-2


def test_equilibrium_newton_signed_alpha_recovers_from_opposite_tangent_direction() -> None:
    f_ext = 1.0

    def assemble_residual(u: np.ndarray, **_: object):
        stiffness = sp.csc_matrix(np.asarray([[-1.0]], dtype=np.float64))
        free = np.asarray([0], dtype=np.int64)
        residual = np.asarray([float(u[0]) - f_ext], dtype=np.float64)
        rhs = np.asarray([f_ext], dtype=np.float64)
        return stiffness, rhs, free, residual, rhs, {}

    positive_only = run_equilibrium_newton(
        u0=np.asarray([0.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        max_newton_iterations=3,
        residual_tolerance_n=1.0e-9,
        prefer_host_ilu=False,
    )
    signed = run_equilibrium_newton(
        u0=np.asarray([0.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        max_newton_iterations=3,
        residual_tolerance_n=1.0e-9,
        prefer_host_ilu=False,
        allow_negative_alphas=True,
    )

    assert positive_only["converged"] is False
    assert signed["converged"] is True
    assert signed["allow_negative_alphas"] is True
    np.testing.assert_allclose(signed["final_u"], [f_ext], rtol=1.0e-6, atol=1.0e-8)
    assert any(
        any(trial["alpha"] < 0.0 for trial in row["trial_rows"])
        for row in signed["iterations"]
    )


def test_equilibrium_newton_state_scale_line_search_can_rescue_bad_checkpoint() -> None:
    stiffness = sp.csc_matrix(np.asarray([[100.0]], dtype=np.float64))
    f_ext = 1.0

    def assemble_residual(u: np.ndarray, **_: object):
        free = np.asarray([0], dtype=np.int64)
        residual = np.asarray([100.0 * float(u[0]) - f_ext], dtype=np.float64)
        rhs = np.asarray([f_ext], dtype=np.float64)
        return stiffness, rhs, free, residual, rhs, {}

    result = run_equilibrium_newton(
        u0=np.asarray([1.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        max_newton_iterations=1,
        residual_tolerance_n=1.0e-9,
        prefer_host_ilu=False,
        state_scale_line_search_values=(0.0, 0.01, 0.1),
    )

    assert result["converged"] is True
    assert result["iterations"][0]["update_mode"] == "state_scale_line_search"
    assert result["iterations"][0]["state_scale"] == 0.01
    np.testing.assert_allclose(result["final_u"], [0.01], rtol=1.0e-12, atol=1.0e-12)


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
