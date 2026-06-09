#!/usr/bin/env python3
"""Equilibrium replay residual ||F_int(u) - F_ext|| for accept gates."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from mgt_physical_residual_assembly import assemble_physical_internal_forces


def equilibrium_replay_residual_inf(
    *,
    u: np.ndarray,
    f_ext: np.ndarray,
    free: np.ndarray,
    node_xyz: np.ndarray,
    frame_elements: list[Any],
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    spring_stiffness: Any,
    base_axial_forces: dict[int, float],
    frame_gravity_load_scale: float,
    load_scale: float,
) -> tuple[float, dict[str, Any]]:
    f_int, meta = assemble_physical_internal_forces(
        u=np.asarray(u, dtype=np.float64),
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        spring_stiffness=spring_stiffness,
        base_axial_forces=base_axial_forces,
        frame_gravity_load_scale=frame_gravity_load_scale,
        load_scale=load_scale,
    )
    free_idx = np.asarray(free, dtype=np.int64)
    residual = np.asarray(f_int[free_idx] - np.asarray(f_ext, dtype=np.float64)[free_idx], dtype=np.float64)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    rhs_inf = float(np.max(np.abs(f_ext[free_idx]))) if free_idx.size else 0.0
    return residual_inf, {
        **meta,
        "equilibrium_replay_residual_inf_n": residual_inf,
        "equilibrium_replay_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
        "equilibrium_replay_rhs_inf_n": rhs_inf,
    }


def annotate_equilibrium_gates(
    row: dict[str, Any],
    *,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
) -> dict[str, Any]:
    equilibrium_inf = float(
        row.get("equilibrium_replay_residual_inf_n")
        if row.get("equilibrium_replay_residual_inf_n") is not None
        else row.get("residual_inf_n") or float("inf")
    )
    solver_inf = float(
        row.get("solver_residual_inf_n")
        if row.get("solver_residual_inf_n") is not None
        else row.get("residual_inf_n") or float("inf")
    )
    row["equilibrium_replay_residual_inf_n"] = equilibrium_inf
    row["solver_residual_inf_n"] = solver_inf
    row["equilibrium_replay_gate_passed"] = equilibrium_inf <= float(residual_tolerance_n)
    row["solver_residual_gate_passed"] = solver_inf <= float(residual_tolerance_n)
    row["residual_gate_passed"] = bool(row["equilibrium_replay_gate_passed"])
    row["relative_increment_gate_passed"] = bool(
        row.get("fixed_point_relative_increment", float("inf")) <= float(relative_increment_tolerance)
    )
    row["ready"] = bool(
        row["residual_gate_passed"]
        and row["relative_increment_gate_passed"]
        and not bool(row.get("displacement_cap_exceeded"))
    )
    row["residual_inf_n"] = equilibrium_inf
    return row


def run_equilibrium_newton(
    *,
    u0: np.ndarray,
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    max_newton_iterations: int = 12,
    residual_tolerance_n: float = 5.0e-4,
    relative_increment_tolerance: float = 1.0e-4,
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    ),
    prefer_host_ilu: bool = True,
) -> dict[str, Any]:
    from mgt_sparse_linear_solver import solve_newton_correction

    u = np.asarray(u0, dtype=np.float64).copy()
    iterations: list[dict[str, Any]] = []
    converged = False
    initial_residual_inf = float("nan")
    for iteration in range(1, int(max_newton_iterations) + 1):
        stiffness, _f_ext, free, residual, _rhs, meta = assemble_residual(u)
        residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        if iteration == 1:
            initial_residual_inf = residual_inf
        increment_inf = 0.0
        relative_increment = 0.0
        if residual_inf <= float(residual_tolerance_n):
            converged = True
            iterations.append(
                {
                    "iteration": iteration,
                    "accepted": True,
                    "stop_reason": "residual_gate_already_met",
                    "residual_inf_n": residual_inf,
                    "relative_increment": 0.0,
                }
            )
            break
        k_ff = stiffness[free, :][:, free].tocsc()
        delta_free, solver_meta = solve_newton_correction(
            k_ff,
            residual,
            prefer_host_ilu=prefer_host_ilu,
        )
        if not np.all(np.isfinite(delta_free)):
            iterations.append(
                {
                    "iteration": iteration,
                    "accepted": False,
                    "stop_reason": "newton_linear_solve_non_finite",
                    "start_residual_inf_n": residual_inf,
                    **solver_meta,
                }
            )
            break
        delta = np.zeros_like(u)
        delta[free] = np.asarray(delta_free, dtype=np.float64)
        best_alpha = 0.0
        best_residual_inf = residual_inf
        best_u = u
        trial_rows: list[dict[str, Any]] = []
        for alpha in line_search_alphas:
            candidate = u + float(alpha) * delta
            _k, _f, _free, trial_residual, _rhs, _meta = assemble_residual(candidate)
            trial_inf = float(np.max(np.abs(trial_residual))) if trial_residual.size else float("inf")
            trial_rows.append({"alpha": float(alpha), "residual_inf_n": trial_inf})
            if trial_inf < best_residual_inf:
                best_residual_inf = trial_inf
                best_alpha = float(alpha)
                best_u = candidate
        accepted = best_alpha > 0.0 and best_residual_inf < residual_inf
        if accepted:
            u = best_u
            increment_inf = float(np.max(np.abs(float(best_alpha) * delta))) if delta.size else 0.0
            max_abs = max(float(np.max(np.abs(u))) if u.size else 0.0, 1.0e-9)
            relative_increment = increment_inf / max_abs
        iteration_row = {
            "iteration": iteration,
            "accepted": bool(accepted),
            "alpha": best_alpha,
            "start_residual_inf_n": residual_inf,
            "best_residual_inf_n": best_residual_inf,
            "relative_increment": relative_increment,
            "trial_rows": trial_rows,
            **solver_meta,
        }
        iterations.append(iteration_row)
        if best_residual_inf <= float(residual_tolerance_n):
            converged = True
            break
        if not accepted:
            iteration_row["stop_reason"] = "no_residual_descent"
            break
        if relative_increment <= float(relative_increment_tolerance):
            _k, _f, _free, final_residual, _rhs, _meta = assemble_residual(u)
            final_inf = float(np.max(np.abs(final_residual))) if final_residual.size else float("inf")
            if final_inf <= float(residual_tolerance_n):
                converged = True
                break
    final_stiffness, _f_ext, final_free, final_residual, final_rhs, final_meta = assemble_residual(u)
    final_residual_inf = float(np.max(np.abs(final_residual))) if final_residual.size else 0.0
    return {
        "converged": converged,
        "residual_gate_passed": final_residual_inf <= float(residual_tolerance_n),
        "final_residual_inf_n": final_residual_inf,
        "initial_residual_inf_n": initial_residual_inf
        if np.isfinite(initial_residual_inf)
        else final_residual_inf,
        "accepted_newton_iteration_count": sum(1 for row in iterations if bool(row.get("accepted"))),
        "iterations": iterations,
        "final_u": u,
        "final_meta": final_meta,
        "residual_tolerance_n": float(residual_tolerance_n),
        "relative_increment_tolerance": float(relative_increment_tolerance),
    }
