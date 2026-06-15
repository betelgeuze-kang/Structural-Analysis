#!/usr/bin/env python3
"""Equilibrium replay residual ||F_int(u) - F_ext|| for accept gates."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from mgt_equilibrium_line_search import (
    select_residual_descent_alpha,
    trust_region_line_search_alphas,
)
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
    initial_assembly: tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None = None,
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
    displacement_cap_m: float | None = None,
    max_newton_translation_increment_m: float | None = None,
    node_xyz: np.ndarray | None = None,
    use_trust_region_line_search: bool = True,
    allow_negative_alphas: bool = False,
    linear_solver_profile: str = "production",
    direct_regularization_factor: float | None = None,
    state_scale_line_search_values: tuple[float, ...] = (),
    state_scale_only: bool = False,
    min_newton_iterations_before_residual_stop: int = 0,
    require_relative_increment_gate_for_convergence: bool = False,
) -> dict[str, Any]:
    from mgt_sparse_linear_solver import solve_newton_correction
    from run_mgt_coupled_frame_surface_sparse_equilibrium import _translation_metrics

    per_step_increment_cap = max_newton_translation_increment_m
    if (
        per_step_increment_cap is None
        and displacement_cap_m is not None
        and float(displacement_cap_m) > 0.0
    ):
        per_step_increment_cap = max(
            float(displacement_cap_m) / max(4.0, float(max_newton_iterations)),
            min(1.0, 0.2 * float(displacement_cap_m)),
        )

    u = np.asarray(u0, dtype=np.float64).copy()
    iterations: list[dict[str, Any]] = []
    converged = False
    initial_residual_inf = float("nan")
    latest_assembly: tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None = None
    latest_assembly_u: np.ndarray | None = None
    for iteration in range(1, int(max_newton_iterations) + 1):
        if iteration == 1 and initial_assembly is not None:
            stiffness, _f_ext, free, residual, _rhs, meta = initial_assembly
        else:
            stiffness, _f_ext, free, residual, _rhs, meta = assemble_residual(u)
        latest_assembly = (stiffness, _f_ext, free, residual, _rhs, meta)
        latest_assembly_u = np.asarray(u, dtype=np.float64).copy()
        residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        if iteration == 1:
            initial_residual_inf = residual_inf
        increment_inf = 0.0
        relative_increment = 0.0
        force_residual_gate_followup = iteration <= max(
            int(min_newton_iterations_before_residual_stop), 0
        )
        if residual_inf <= float(residual_tolerance_n) and not force_residual_gate_followup:
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
        state_scale_rows: list[dict[str, Any]] = []
        best_state_scale = 1.0
        best_state_scale_residual = residual_inf
        best_state_scale_u = u
        best_state_scale_assembly = latest_assembly
        for state_scale in state_scale_line_search_values:
            scale = float(state_scale)
            if not np.isfinite(scale) or abs(scale - 1.0) <= 1.0e-15:
                continue
            candidate = scale * u
            scale_k, scale_f, scale_free, scale_residual, scale_rhs, scale_meta = assemble_residual(
                candidate
            )
            free_stable = bool(
                np.asarray(scale_free, dtype=np.int64).shape == np.asarray(free, dtype=np.int64).shape
                and np.array_equal(np.asarray(scale_free, dtype=np.int64), np.asarray(free, dtype=np.int64))
            )
            scale_residual_inf = (
                float(np.max(np.abs(scale_residual))) if scale_residual.size else float("inf")
            )
            state_scale_rows.append(
                {
                    "state_scale": scale,
                    "residual_inf_n": scale_residual_inf,
                    "free_dof_set_stable": free_stable,
                }
            )
            if free_stable and scale_residual_inf < best_state_scale_residual:
                best_state_scale = scale
                best_state_scale_residual = scale_residual_inf
                best_state_scale_u = candidate
                best_state_scale_assembly = (
                    scale_k,
                    scale_f,
                    scale_free,
                    scale_residual,
                    scale_rhs,
                    scale_meta,
                )
        if abs(best_state_scale - 1.0) > 1.0e-15 and best_state_scale_residual < residual_inf:
            increment_inf = (
                float(np.max(np.abs(best_state_scale_u - u))) if best_state_scale_u.size else 0.0
            )
            max_abs = max(float(np.max(np.abs(best_state_scale_u))) if best_state_scale_u.size else 0.0, 1.0e-9)
            relative_increment = increment_inf / max_abs
            u = np.asarray(best_state_scale_u, dtype=np.float64)
            latest_assembly = best_state_scale_assembly
            latest_assembly_u = np.asarray(u, dtype=np.float64).copy()
            iterations.append(
                {
                    "iteration": iteration,
                    "accepted": True,
                    "update_mode": "state_scale_line_search",
                    "state_scale": float(best_state_scale),
                    "start_residual_inf_n": residual_inf,
                    "best_residual_inf_n": best_state_scale_residual,
                    "relative_increment": relative_increment,
                    "trial_rows": state_scale_rows,
                    "state_scale_only": bool(state_scale_only),
                    "allow_negative_alphas": bool(allow_negative_alphas),
                    **(
                        {"stop_reason": "state_scale_only_accepted"}
                        if state_scale_only
                        else {}
                    ),
                }
            )
            if best_state_scale_residual <= float(residual_tolerance_n):
                converged = True
                break
            if state_scale_only:
                break
            continue
        if state_scale_only:
            iterations.append(
                {
                    "iteration": iteration,
                    "accepted": False,
                    "update_mode": "state_scale_line_search",
                    "stop_reason": "state_scale_only_no_residual_descent",
                    "start_residual_inf_n": residual_inf,
                    "best_residual_inf_n": best_state_scale_residual,
                    "relative_increment": 0.0,
                    "trial_rows": state_scale_rows,
                    "state_scale_only": True,
                    "allow_negative_alphas": bool(allow_negative_alphas),
                }
            )
            break
        k_ff = stiffness[free, :][:, free].tocsc()
        delta_free, solver_meta = solve_newton_correction(
            k_ff,
            residual,
            prefer_host_ilu=prefer_host_ilu,
            free_global_dofs=np.asarray(free, dtype=np.int64),
            solver_profile=linear_solver_profile,
            direct_regularization_factor=direct_regularization_factor,
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
        search_displacement_cap = displacement_cap_m
        if (
            use_trust_region_line_search
            and displacement_cap_m is not None
            and residual_inf > float(residual_tolerance_n)
        ):
            search_displacement_cap = float(displacement_cap_m) * 0.85
        search_alphas = (
            trust_region_line_search_alphas(
                u=u,
                delta=delta,
                node_xyz=node_xyz,
                displacement_cap_m=search_displacement_cap,
                translation_metrics=_translation_metrics,
                max_translation_increment_m=per_step_increment_cap,
                base_alphas=line_search_alphas,
                include_negative=bool(allow_negative_alphas),
            )
            if use_trust_region_line_search
            else (
                line_search_alphas
                if not allow_negative_alphas
                else tuple(
                    list(line_search_alphas)
                    + [
                        -float(alpha)
                        for alpha in line_search_alphas
                        if float(alpha) > 0.0
                    ]
                )
            )
        )
        best_alpha, best_residual_inf, best_u, trial_rows = select_residual_descent_alpha(
            u=u,
            delta=delta,
            residual_inf=residual_inf,
            assemble_residual=assemble_residual,
            alphas=search_alphas,
            node_xyz=node_xyz,
            displacement_cap_m=displacement_cap_m,
            max_translation_increment_m=per_step_increment_cap,
            translation_metrics=_translation_metrics if displacement_cap_m is not None else None,
            residual_only_free=np.asarray(free, dtype=np.int64),
            residual_only_external_load=np.asarray(_f_ext, dtype=np.float64),
        )
        accepted = abs(float(best_alpha)) > 0.0 and best_residual_inf < residual_inf
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
            "allow_negative_alphas": bool(allow_negative_alphas),
            **solver_meta,
        }
        iterations.append(iteration_row)
        increment_gate_passed = relative_increment <= float(relative_increment_tolerance)
        if (
            accepted
            and best_residual_inf <= float(residual_tolerance_n)
            and (
                increment_gate_passed
                or not bool(require_relative_increment_gate_for_convergence)
            )
        ):
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
    if (
        latest_assembly is not None
        and latest_assembly_u is not None
        and latest_assembly_u.shape == np.asarray(u, dtype=np.float64).shape
        and np.array_equal(latest_assembly_u, np.asarray(u, dtype=np.float64))
    ):
        final_stiffness, _f_ext, final_free, final_residual, final_rhs, final_meta = latest_assembly
    else:
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
        "final_residual": final_residual,
        "final_rhs": final_rhs,
        "final_free": final_free,
        "final_meta": final_meta,
        "residual_tolerance_n": float(residual_tolerance_n),
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "max_newton_translation_increment_m": per_step_increment_cap,
        "line_search_residual_only_supported": bool(
            getattr(assemble_residual, "supports_residual_only", False)
        ),
        "allow_negative_alphas": bool(allow_negative_alphas),
        "linear_solver_profile": str(linear_solver_profile or "production"),
        "direct_regularization_factor": (
            None
            if direct_regularization_factor is None
            else float(direct_regularization_factor)
        ),
        "state_scale_line_search_values": [
            float(value) for value in state_scale_line_search_values
        ],
        "state_scale_only": bool(state_scale_only),
        "min_newton_iterations_before_residual_stop": int(
            min_newton_iterations_before_residual_stop
        ),
        "require_relative_increment_gate_for_convergence": bool(
            require_relative_increment_gate_for_convergence
        ),
    }
