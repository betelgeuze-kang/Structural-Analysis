#!/usr/bin/env python3
"""Probe uncoarsened frame-shell boundary tangent in a deformed-state P-Delta loop."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any

import numpy as np

from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from mgt_equilibrium_shell_assembly import assemble_equilibrium_surface_shell_6dof
from run_mgt_coupled_frame_surface_sparse_equilibrium import (
    _select_frame_elements,
    _solve_active_system,
    _translation_metrics,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    _assemble_sparse_frame,
    _beam_end_offset_lookup,
    _component_gravity_axial_forces,
    _element_angle_array_from_props,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import (
    DEFAULT_MGT,
    PRODUCTIZATION,
    _assemble_elastic_link_springs,
    _authored_support_restraints,
    _run_uncoarsened_parser,
)
from mgt_equilibrium_geometry_contract import EQUILIBRIUM_GEOMETRY_CONTRACT
from mgt_equilibrium_replay import (
    annotate_equilibrium_gates,
    equilibrium_replay_residual_inf,
    run_equilibrium_newton,
)
from mgt_equilibrium_step_assembly import build_equilibrium_step_assembler


SCHEMA_VERSION = "mgt-uncoarsened-boundary-pdelta-probe.v1"
CHECKPOINT_SCHEMA_VERSION = "mgt-uncoarsened-boundary-pdelta-checkpoint.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_probe.json"


def _checkpoint_load_label(load_scale: float) -> str:
    text = f"{float(load_scale):.12g}"
    return text.replace("-", "m").replace(".", "p")


def _write_accepted_checkpoint(
    *,
    checkpoint_dir: Path,
    load_scale: float,
    displacement_u: np.ndarray,
    node_id: np.ndarray,
    step_row: dict[str, Any],
) -> dict[str, Any]:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = checkpoint_dir / f"accepted_load_{_checkpoint_load_label(load_scale)}.npz"
    u = np.asarray(displacement_u, dtype=np.float64)
    nodes = np.asarray(node_id, dtype=np.int64)
    np.savez_compressed(
        path,
        schema_version=np.asarray(CHECKPOINT_SCHEMA_VERSION),
        load_scale=np.asarray(float(load_scale), dtype=np.float64),
        dof_per_node=np.asarray(DOF_PER_NODE, dtype=np.int32),
        node_id=nodes,
        displacement_u=u,
        residual_inf_n=np.asarray(float(step_row.get("best_residual_inf_n") or 0.0), dtype=np.float64),
        equilibrium_replay_residual_inf_n=np.asarray(
            float(
                step_row.get("best_equilibrium_replay_residual_inf_n")
                or step_row.get("best_residual_inf_n")
                or 0.0
            ),
            dtype=np.float64,
        ),
        solver_residual_inf_n=np.asarray(
            float(step_row.get("best_solver_residual_inf_n") or 0.0),
            dtype=np.float64,
        ),
        equilibrium_replay_gate_passed=np.asarray(
            bool(step_row.get("equilibrium_replay_gate_passed")),
            dtype=np.bool_,
        ),
        fixed_point_relative_increment=np.asarray(
            float(step_row.get("best_fixed_point_relative_increment") or 0.0),
            dtype=np.float64,
        ),
        max_translation_m=np.asarray(float(step_row.get("final_max_translation_m") or 0.0), dtype=np.float64),
    )
    return {
        "path": str(path),
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "load_scale": float(load_scale),
        "dof_count": int(u.size),
        "node_count": int(nodes.size),
        "residual_inf_n": step_row.get("best_residual_inf_n"),
        "equilibrium_replay_residual_inf_n": step_row.get("best_equilibrium_replay_residual_inf_n"),
        "solver_residual_inf_n": step_row.get("best_solver_residual_inf_n"),
        "equilibrium_replay_gate_passed": bool(step_row.get("equilibrium_replay_gate_passed")),
        "fixed_point_relative_increment": step_row.get("best_fixed_point_relative_increment"),
        "max_translation_m": step_row.get("final_max_translation_m"),
    }


def _load_accepted_checkpoint(
    *,
    checkpoint_npz: Path,
    expected_node_id: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray]:
    with np.load(checkpoint_npz, allow_pickle=False) as archive:
        schema_version = str(np.asarray(archive["schema_version"]).item())
        if schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported checkpoint schema {schema_version!r}; expected {CHECKPOINT_SCHEMA_VERSION!r}"
            )
        dof_per_node = int(np.asarray(archive["dof_per_node"]).item())
        if dof_per_node != DOF_PER_NODE:
            raise ValueError(f"checkpoint dof_per_node={dof_per_node} does not match {DOF_PER_NODE}")
        node_id = np.asarray(archive["node_id"], dtype=np.int64)
        expected = np.asarray(expected_node_id, dtype=np.int64)
        if node_id.shape != expected.shape or not np.array_equal(node_id, expected):
            raise ValueError("checkpoint node_id vector does not match current uncoarsened parse")
        displacement_u = np.asarray(archive["displacement_u"], dtype=np.float64)
        expected_dof = int(expected.size) * DOF_PER_NODE
        if displacement_u.shape != (expected_dof,):
            raise ValueError(
                f"checkpoint displacement shape {displacement_u.shape} does not match {(expected_dof,)}"
            )
        load_scale = float(np.asarray(archive["load_scale"]).item())
        meta = {
            "path": str(checkpoint_npz),
            "schema_version": schema_version,
            "load_scale": load_scale,
            "dof_count": int(displacement_u.size),
            "node_count": int(node_id.size),
            "residual_inf_n": float(np.asarray(archive["residual_inf_n"]).item())
            if "residual_inf_n" in archive.files
            else None,
            "fixed_point_relative_increment": float(
                np.asarray(archive["fixed_point_relative_increment"]).item()
            )
            if "fixed_point_relative_increment" in archive.files
            else None,
            "max_translation_m": float(np.asarray(archive["max_translation_m"]).item())
            if "max_translation_m" in archive.files
            else None,
        }
    return meta, displacement_u


def _secant_predict_displacement(
    *,
    previous_load_scale: float,
    previous_u: np.ndarray,
    current_load_scale: float,
    current_u: np.ndarray,
    target_load_scale: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    previous = np.asarray(previous_u, dtype=np.float64)
    current = np.asarray(current_u, dtype=np.float64)
    if previous.shape != current.shape:
        raise ValueError("secant predictor checkpoint displacement shapes do not match")
    denominator = float(current_load_scale) - float(previous_load_scale)
    if abs(denominator) <= 1.0e-12:
        raise ValueError("secant predictor requires distinct checkpoint load scales")
    factor = (float(target_load_scale) - float(current_load_scale)) / denominator
    delta = current - previous
    predicted = current + factor * delta
    return predicted, {
        "enabled": True,
        "previous_load_scale": float(previous_load_scale),
        "current_load_scale": float(current_load_scale),
        "target_load_scale": float(target_load_scale),
        "extrapolation_factor": float(factor),
        "seed_delta_inf_m": float(np.max(np.abs(predicted - current))) if predicted.size else 0.0,
        "checkpoint_delta_inf_m": float(np.max(np.abs(delta))) if delta.size else 0.0,
        "claim_boundary": (
            "Secant prediction only changes the initial displacement seed for the next load step. "
            "The step is promoted only if the existing residual and unrelaxed fixed-point "
            "increment gates pass after remapping through the P-Delta operator."
        ),
    }


def _linear_tangent_warm_start_u(
    *,
    load_scale: float,
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
    restrained: set[int],
    base_axial_forces: dict[int, float],
    base_frame_gravity_scale: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """One-shot linear tangent solve used only as a Newton initial guess."""
    axial_forces = {
        int(elem_id): float(force) * float(base_frame_gravity_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_stiffness, frame_f, frame_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    shell_stiffness, shell_f, shell_meta, _surface_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    stiffness = frame_stiffness + shell_stiffness + spring_stiffness
    f_ext = (frame_f * float(base_frame_gravity_scale) + shell_f) * float(load_scale)
    _active, free, u_free, residual_inf, rhs_inf, regularization = _solve_active_system(
        stiffness=stiffness,
        f_ext=f_ext,
        restrained=restrained,
    )
    warm_start = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
    warm_start[free] = np.asarray(u_free, dtype=np.float64)
    metrics = _translation_metrics(warm_start, node_xyz)
    return warm_start, {
        "linear_warm_start": True,
        "solver_residual_inf_n": float(residual_inf),
        "rhs_inf_n": float(rhs_inf),
        "regularization": float(regularization),
        "max_translation_m": metrics["max_translation_m"],
        "frame_stiffness_nnz": int(frame_stiffness.nnz),
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "frame_total_gravity_n": float(frame_meta.get("total_gravity_n") or 0.0),
        "surface_total_area_m2": float(shell_meta.get("surface_total_area_m2") or 0.0),
    }


def _annotate_convergence_gates(
    row: dict[str, Any],
    *,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
) -> dict[str, Any]:
    return annotate_equilibrium_gates(
        row,
        residual_tolerance_n=residual_tolerance_n,
        relative_increment_tolerance=relative_increment_tolerance,
    )


def _compact_seed_candidate_row(row: dict[str, Any], *, alpha: float) -> dict[str, Any]:
    return {
        "alpha": float(alpha),
        "residual_inf_n": row.get("residual_inf_n"),
        "equilibrium_replay_residual_inf_n": row.get("equilibrium_replay_residual_inf_n"),
        "solver_residual_inf_n": row.get("solver_residual_inf_n"),
        "fixed_point_increment_m": row.get("fixed_point_increment_m"),
        "fixed_point_relative_increment": row.get("fixed_point_relative_increment"),
        "max_translation_m": row.get("max_translation_m"),
        "residual_gate_passed": bool(row.get("residual_gate_passed")),
        "equilibrium_replay_gate_passed": bool(row.get("equilibrium_replay_gate_passed")),
        "solver_residual_gate_passed": bool(row.get("solver_residual_gate_passed")),
        "relative_increment_gate_passed": bool(row.get("relative_increment_gate_passed")),
        "ready": bool(row.get("ready")),
    }


def _seed_alpha_scan(
    *,
    load_scale: float,
    seed_u: np.ndarray,
    alpha_values: tuple[float, ...],
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
    displacement_cap_m: float,
    **kwargs: Any,
) -> tuple[dict[str, Any], np.ndarray]:
    iteration_kwargs = dict(kwargs)
    iteration_kwargs.pop("residual_tolerance_n", None)
    iteration_kwargs.pop("relative_increment_tolerance", None)
    started = time.perf_counter()
    base_row, fixed_point_u = _iteration_row(
        iteration=0,
        load_scale=load_scale,
        previous_u=seed_u,
        relaxation_factor=1.0,
        residual_tolerance_n=residual_tolerance_n,
        relative_increment_tolerance=relative_increment_tolerance,
        displacement_cap_m=displacement_cap_m,
        **iteration_kwargs,
    )
    _annotate_convergence_gates(
        base_row,
        residual_tolerance_n=residual_tolerance_n,
        relative_increment_tolerance=relative_increment_tolerance,
    )
    direction = np.asarray(fixed_point_u, dtype=np.float64) - np.asarray(seed_u, dtype=np.float64)
    candidate_rows: list[dict[str, Any]] = []
    candidate_vectors: list[np.ndarray] = []
    for alpha in alpha_values:
        candidate_u = np.asarray(seed_u, dtype=np.float64) + float(alpha) * direction
        candidate_row, _ = _iteration_row(
            iteration=0,
            load_scale=load_scale,
            previous_u=candidate_u,
            relaxation_factor=0.0,
            residual_tolerance_n=residual_tolerance_n,
            relative_increment_tolerance=relative_increment_tolerance,
            displacement_cap_m=displacement_cap_m,
            **iteration_kwargs,
        )
        _annotate_convergence_gates(
            candidate_row,
            residual_tolerance_n=residual_tolerance_n,
            relative_increment_tolerance=relative_increment_tolerance,
        )
        candidate_rows.append(_compact_seed_candidate_row(candidate_row, alpha=float(alpha)))
        candidate_vectors.append(candidate_u)
    if candidate_rows:
        best_index, best_row = min(
            enumerate(candidate_rows),
            key=lambda item: float(item[1].get("fixed_point_relative_increment") or float("inf")),
        )
        best_u = candidate_vectors[best_index]
    else:
        best_row = _compact_seed_candidate_row(base_row, alpha=0.0)
        best_u = np.asarray(seed_u, dtype=np.float64)
    scan = {
        "enabled": True,
        "load_scale": float(load_scale),
        "requested_alpha_values": [float(value) for value in alpha_values],
        "evaluation_count": int(len(candidate_rows) + 1),
        "base_fixed_point_relative_increment": base_row.get("fixed_point_relative_increment"),
        "base_residual_inf_n": base_row.get("residual_inf_n"),
        "direction_inf_m": float(np.max(np.abs(direction))) if direction.size else 0.0,
        "best_alpha": best_row.get("alpha"),
        "best_residual_inf_n": best_row.get("residual_inf_n"),
        "best_fixed_point_relative_increment": best_row.get("fixed_point_relative_increment"),
        "best_max_translation_m": best_row.get("max_translation_m"),
        "best_ready": bool(best_row.get("ready")),
        "candidate_rows": candidate_rows,
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "Seed alpha scan is a one-step globalization diagnostic. It builds candidates along the "
            "first fixed-point correction direction and remaps each candidate through the same P-Delta "
            "operator. It is closure only if the remapped residual and unrelaxed fixed-point gates pass."
        ),
    }
    return scan, best_u


def _iteration_row(
    *,
    iteration: int,
    load_scale: float,
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
    restrained: set[int],
    base_axial_forces: dict[int, float],
    base_frame_gravity_scale: float,
    previous_u: np.ndarray,
    relaxation_factor: float,
    displacement_cap_m: float,
    residual_tolerance_n: float = 5.0e-4,
    relative_increment_tolerance: float = 1.0e-4,
    equilibrium_assembler: Any | None = None,
    max_equilibrium_newton_iterations: int = 0,
    outer_solver_mode: str = "newton_only",
    use_linear_warm_start: bool = True,
    equilibrium_newton_allow_negative_alphas: bool = False,
) -> tuple[dict[str, Any], np.ndarray]:
    iter_started = time.perf_counter()
    if str(outer_solver_mode).strip().lower() == "newton_only":
        if equilibrium_assembler is None:
            raise ValueError("newton_only outer mode requires equilibrium_assembler")
        candidate = np.asarray(previous_u, dtype=np.float64)
        warm_start_meta: dict[str, Any] | None = None
        if use_linear_warm_start and float(np.max(np.abs(candidate))) <= 1.0e-12:
            candidate, warm_start_meta = _linear_tangent_warm_start_u(
                load_scale=load_scale,
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
                restrained=restrained,
                base_axial_forces=base_axial_forces,
                base_frame_gravity_scale=base_frame_gravity_scale,
            )
        equilibrium_newton_outer = run_equilibrium_newton(
            u0=candidate,
            assemble_residual=equilibrium_assembler,
            max_newton_iterations=max(1, int(max_equilibrium_newton_iterations)),
            residual_tolerance_n=float(residual_tolerance_n),
            relative_increment_tolerance=float(relative_increment_tolerance),
            displacement_cap_m=float(displacement_cap_m),
            node_xyz=node_xyz,
            use_trust_region_line_search=True,
            allow_negative_alphas=bool(equilibrium_newton_allow_negative_alphas),
        )
        candidate = np.asarray(equilibrium_newton_outer["final_u"], dtype=np.float64)
        _eq_stiffness, f_ext_frozen, free_eq, residual_eq, rhs_eq, equilibrium_meta = equilibrium_assembler(
            candidate
        )
        equilibrium_inf = float(np.max(np.abs(residual_eq))) if residual_eq.size else 0.0
        rhs_inf = float(np.max(np.abs(rhs_eq))) if rhs_eq.size else 0.0
        free = free_eq
        metrics = _translation_metrics(candidate, node_xyz)
        last_iteration = (
            equilibrium_newton_outer.get("iterations") or [{}]
        )[-1]
        newton_relative_increment = float(last_iteration.get("relative_increment") or 0.0)
        row = {
            "iteration": int(iteration),
            "load_scale": float(load_scale),
            "outer_solver_mode": "newton_only",
            "solver_residual_inf_n": float(equilibrium_inf),
            "equilibrium_replay_residual_inf_n": float(equilibrium_inf),
            "residual_inf_n": float(equilibrium_inf),
            "relative_residual_inf": float(equilibrium_inf / max(rhs_inf, 1.0)),
            "solver_relative_residual_inf": float(equilibrium_inf / max(rhs_inf, 1.0)),
            "rhs_inf_n": float(rhs_inf),
            "regularization": 0.0,
            "active_dof_count": int(free.size),
            "free_dof_count": int(free.size),
            "fixed_point_increment_m": float(
                np.max(np.abs(candidate - previous_u)) if candidate.size else 0.0
            ),
            "fixed_point_relative_increment": newton_relative_increment,
            "relaxed_increment_m": float(
                np.max(np.abs(candidate - previous_u)) if candidate.size else 0.0
            ),
            "relaxed_relative_increment": newton_relative_increment,
            "max_abs_displacement_m": metrics["max_abs_displacement_m"],
            "max_translation_m": metrics["max_translation_m"],
            "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
            "displacement_cap_m": float(displacement_cap_m),
            "displacement_cap_exceeded": bool(metrics["max_translation_m"] > float(displacement_cap_m)),
            "seconds": time.perf_counter() - iter_started,
            **equilibrium_meta,
            "equilibrium_newton_outer": {
                "converged": bool(equilibrium_newton_outer.get("converged")),
                "initial_residual_inf_n": equilibrium_newton_outer.get("initial_residual_inf_n"),
                "final_residual_inf_n": equilibrium_newton_outer.get("final_residual_inf_n"),
                "accepted_newton_iteration_count": equilibrium_newton_outer.get(
                    "accepted_newton_iteration_count"
                ),
                "max_newton_iterations": int(max_equilibrium_newton_iterations),
                "max_newton_translation_increment_m": equilibrium_newton_outer.get(
                    "max_newton_translation_increment_m"
                ),
                "line_search": "trust_region_arc_length",
                "allow_negative_alphas": bool(equilibrium_newton_allow_negative_alphas),
                "iterations": equilibrium_newton_outer.get("iterations"),
            },
        }
        if warm_start_meta is not None:
            row["linear_warm_start"] = warm_start_meta
        return row, candidate
    axial_forces = {
        int(elem_id): float(force) * float(base_frame_gravity_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_stiffness, frame_f, frame_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    shell_stiffness, shell_f, shell_meta, _surface_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    stiffness = frame_stiffness + shell_stiffness + spring_stiffness
    f_ext = (frame_f * float(base_frame_gravity_scale) + shell_f) * float(load_scale)
    active, free, u_free, residual_inf, rhs_inf, regularization = _solve_active_system(
        stiffness=stiffness,
        f_ext=f_ext,
        restrained=restrained,
    )
    fixed_point = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
    fixed_point[free] = np.asarray(u_free, dtype=np.float64)
    fixed_point_increment = (
        float(np.max(np.abs(fixed_point - previous_u))) if fixed_point.size else 0.0
    )
    fixed_point_max_abs = max(
        float(np.max(np.abs(fixed_point))) if fixed_point.size else 0.0,
        1.0e-9,
    )
    fixed_point_relative_increment = fixed_point_increment / fixed_point_max_abs
    candidate = (1.0 - float(relaxation_factor)) * previous_u + float(relaxation_factor) * fixed_point
    relaxed_increment = float(np.max(np.abs(candidate - previous_u))) if candidate.size else 0.0
    relaxed_max_abs = max(float(np.max(np.abs(candidate))) if candidate.size else 0.0, 1.0e-9)
    relaxed_relative_increment = relaxed_increment / relaxed_max_abs
    metrics = _translation_metrics(candidate, node_xyz)
    equilibrium_newton_inner: dict[str, Any] | None = None
    if equilibrium_assembler is not None and int(max_equilibrium_newton_iterations) > 0:
        _pre_stiffness, _pre_f_ext, _pre_free, pre_residual, pre_rhs, _pre_meta = equilibrium_assembler(
            candidate
        )
        pre_equilibrium_inf = float(np.max(np.abs(pre_residual))) if pre_residual.size else float("inf")
        if pre_equilibrium_inf > float(residual_tolerance_n):
            equilibrium_newton_inner = run_equilibrium_newton(
                u0=candidate,
                assemble_residual=equilibrium_assembler,
                max_newton_iterations=int(max_equilibrium_newton_iterations),
                residual_tolerance_n=float(residual_tolerance_n),
                relative_increment_tolerance=float(relative_increment_tolerance),
                displacement_cap_m=float(displacement_cap_m),
                node_xyz=node_xyz,
                use_trust_region_line_search=True,
                allow_negative_alphas=bool(equilibrium_newton_allow_negative_alphas),
            )
            candidate = np.asarray(equilibrium_newton_inner["final_u"], dtype=np.float64)
            metrics = _translation_metrics(candidate, node_xyz)
    if equilibrium_assembler is not None:
        _eq_stiffness, f_ext_frozen, free_eq, residual_eq, rhs_eq, equilibrium_meta = equilibrium_assembler(
            candidate
        )
        equilibrium_inf = float(np.max(np.abs(residual_eq))) if residual_eq.size else 0.0
        rhs_inf = float(np.max(np.abs(rhs_eq))) if rhs_eq.size else float(rhs_inf)
        free = free_eq
        f_ext = f_ext_frozen
    else:
        equilibrium_inf, equilibrium_meta = equilibrium_replay_residual_inf(
            u=candidate,
            f_ext=f_ext,
            free=free,
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
            frame_gravity_load_scale=base_frame_gravity_scale,
            load_scale=load_scale,
        )
    row = {
        "iteration": int(iteration),
        "load_scale": float(load_scale),
        "solver_residual_inf_n": float(residual_inf),
        "equilibrium_replay_residual_inf_n": float(equilibrium_inf),
        "residual_inf_n": float(equilibrium_inf),
        "relative_residual_inf": float(equilibrium_inf / max(rhs_inf, 1.0)),
        "solver_relative_residual_inf": float(residual_inf / max(rhs_inf, 1.0)),
        "rhs_inf_n": float(rhs_inf),
        "regularization": float(regularization),
        "active_dof_count": int(active.size),
        "free_dof_count": int(free.size),
        "fixed_point_increment_m": fixed_point_increment,
        "fixed_point_relative_increment": fixed_point_relative_increment,
        "relaxed_increment_m": relaxed_increment,
        "relaxed_relative_increment": relaxed_relative_increment,
        "max_abs_displacement_m": metrics["max_abs_displacement_m"],
        "max_translation_m": metrics["max_translation_m"],
        "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
        "displacement_cap_m": float(displacement_cap_m),
        "displacement_cap_exceeded": bool(metrics["max_translation_m"] > float(displacement_cap_m)),
        "frame_stiffness_nnz": int(frame_stiffness.nnz),
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "spring_stiffness_nnz": int(spring_stiffness.nnz),
        "coupled_stiffness_nnz": int(stiffness.nnz),
        "frame_total_gravity_n": float(frame_meta.get("total_gravity_n") or 0.0),
        "surface_total_area_m2": float(shell_meta.get("surface_total_area_m2") or 0.0),
        "seconds": time.perf_counter() - iter_started,
        **equilibrium_meta,
    }
    if equilibrium_newton_inner is not None:
        row["equilibrium_newton_inner"] = {
            "converged": bool(equilibrium_newton_inner.get("converged")),
            "initial_residual_inf_n": equilibrium_newton_inner.get("initial_residual_inf_n"),
            "final_residual_inf_n": equilibrium_newton_inner.get("final_residual_inf_n"),
            "accepted_newton_iteration_count": equilibrium_newton_inner.get(
                "accepted_newton_iteration_count"
            ),
            "max_newton_iterations": int(max_equilibrium_newton_iterations),
            "allow_negative_alphas": bool(equilibrium_newton_allow_negative_alphas),
        }
    return row, candidate


def _run_load_step(
    *,
    load_scale: float,
    seed_u: np.ndarray,
    max_iterations: int,
    relaxation_factor: float,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
    displacement_cap_m: float,
    seed_alpha_scan_values: tuple[float, ...] = (),
    max_equilibrium_newton_iterations_per_iteration: int = 6,
    outer_solver_mode: str = "newton_only",
    equilibrium_newton_allow_negative_alphas: bool = False,
    **kwargs: Any,
) -> tuple[dict[str, Any], np.ndarray]:
    step_started = time.perf_counter()
    u = np.asarray(seed_u, dtype=np.float64).copy()
    equilibrium_assembler, equilibrium_step_meta = build_equilibrium_step_assembler(
        node_xyz=kwargs["node_xyz"],
        frame_elements=kwargs["frame_elements"],
        elem_type_code=kwargs["elem_type_code"],
        elem_section_id=kwargs["elem_section_id"],
        elem_material_id=kwargs["elem_material_id"],
        conn_ptr=kwargs["conn_ptr"],
        conn_idx=kwargs["conn_idx"],
        section_props=kwargs["section_props"],
        material_props=kwargs["material_props"],
        plate_thickness_props=kwargs["plate_thickness_props"],
        spring_stiffness=kwargs["spring_stiffness"],
        base_axial_forces=kwargs["base_axial_forces"],
        frame_gravity_load_scale=kwargs["base_frame_gravity_scale"],
        load_scale=float(load_scale),
        restrained=kwargs["restrained"],
    )
    kwargs = {
        **kwargs,
        "equilibrium_assembler": equilibrium_assembler,
        "residual_tolerance_n": residual_tolerance_n,
        "relative_increment_tolerance": relative_increment_tolerance,
        "max_equilibrium_newton_iterations": int(max_equilibrium_newton_iterations_per_iteration),
        "outer_solver_mode": str(outer_solver_mode),
        "equilibrium_newton_allow_negative_alphas": bool(equilibrium_newton_allow_negative_alphas),
    }
    rows: list[dict[str, Any]] = []
    seed_alpha_scan: dict[str, Any] | None = None
    if seed_alpha_scan_values:
        seed_scan_kwargs = dict(kwargs)
        seed_scan_kwargs.pop("residual_tolerance_n", None)
        seed_scan_kwargs.pop("relative_increment_tolerance", None)
        seed_alpha_scan, scanned_u = _seed_alpha_scan(
            load_scale=load_scale,
            seed_u=u,
            alpha_values=seed_alpha_scan_values,
            residual_tolerance_n=residual_tolerance_n,
            relative_increment_tolerance=relative_increment_tolerance,
            displacement_cap_m=displacement_cap_m,
            **seed_scan_kwargs,
        )
        u = np.asarray(scanned_u, dtype=np.float64)
        if bool(seed_alpha_scan.get("best_ready")) or int(max_iterations) <= 0:
            return {
                "load_scale": float(load_scale),
                "ready": bool(seed_alpha_scan.get("best_ready")),
                "converged": bool(seed_alpha_scan.get("best_ready")),
                "iteration_count": 0,
                "max_iterations": int(max_iterations),
                "relaxation_factor": float(relaxation_factor),
                "residual_tolerance_n": float(residual_tolerance_n),
                "relative_increment_tolerance": float(relative_increment_tolerance),
                "best_residual_inf_n": seed_alpha_scan.get("best_residual_inf_n"),
                "best_relative_residual_inf": None,
                "best_fixed_point_relative_increment": seed_alpha_scan.get(
                    "best_fixed_point_relative_increment"
                ),
                "final_residual_inf_n": seed_alpha_scan.get("best_residual_inf_n"),
                "final_fixed_point_relative_increment": seed_alpha_scan.get(
                    "best_fixed_point_relative_increment"
                ),
                "final_max_translation_m": seed_alpha_scan.get("best_max_translation_m"),
                "rows": rows,
                "seed_alpha_scan": seed_alpha_scan,
                "initial_seed_strategy": "seed_alpha_scan_best_candidate",
                "seconds": time.perf_counter() - step_started,
                "blockers": []
                if bool(seed_alpha_scan.get("best_ready"))
                else [
                    "uncoarsened_boundary_pdelta_step_not_converged",
                ],
            }, u
    ready = False
    for iteration in range(1, int(max_iterations) + 1):
        row, next_u = _iteration_row(
            iteration=iteration,
            load_scale=load_scale,
            previous_u=u,
            relaxation_factor=relaxation_factor,
            displacement_cap_m=displacement_cap_m,
            **kwargs,
        )
        _annotate_convergence_gates(
            row,
            residual_tolerance_n=residual_tolerance_n,
            relative_increment_tolerance=relative_increment_tolerance,
        )
        rows.append(row)
        u = next_u
        ready = bool(row["ready"])
        if ready or bool(row["displacement_cap_exceeded"]):
            break
    scan_best_as_row = {
        "residual_inf_n": seed_alpha_scan.get("best_residual_inf_n"),
        "fixed_point_relative_increment": seed_alpha_scan.get("best_fixed_point_relative_increment"),
        "relative_residual_inf": None,
    } if seed_alpha_scan else None
    residual_candidates = list(rows)
    increment_candidates = list(rows)
    if scan_best_as_row is not None:
        residual_candidates.append(scan_best_as_row)
        increment_candidates.append(scan_best_as_row)
    best_residual_row = (
        min(
            residual_candidates,
            key=lambda row: float(
                row.get("equilibrium_replay_residual_inf_n")
                or row.get("residual_inf_n")
                or float("inf")
            ),
        )
        if residual_candidates
        else {}
    )
    best_solver_residual_row = (
        min(
            residual_candidates,
            key=lambda row: float(row.get("solver_residual_inf_n") or float("inf")),
        )
        if residual_candidates
        else {}
    )
    best_increment_row = (
        min(
            increment_candidates,
            key=lambda row: float(row.get("fixed_point_relative_increment") or float("inf")),
        )
        if increment_candidates
        else {}
    )
    final = rows[-1] if rows else {}
    out = {
        "load_scale": float(load_scale),
        "ready": bool(ready),
        "converged": bool(ready),
        "iteration_count": int(len(rows)),
        "max_iterations": int(max_iterations),
        "relaxation_factor": float(relaxation_factor),
        "residual_tolerance_n": float(residual_tolerance_n),
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "best_residual_inf_n": best_residual_row.get("equilibrium_replay_residual_inf_n")
        or best_residual_row.get("residual_inf_n"),
        "best_equilibrium_replay_residual_inf_n": best_residual_row.get(
            "equilibrium_replay_residual_inf_n"
        )
        or best_residual_row.get("residual_inf_n"),
        "best_solver_residual_inf_n": best_solver_residual_row.get("solver_residual_inf_n"),
        "best_relative_residual_inf": best_residual_row.get("relative_residual_inf"),
        "equilibrium_replay_gate_passed": bool(best_residual_row.get("equilibrium_replay_gate_passed")),
        "best_fixed_point_relative_increment": best_increment_row.get(
            "fixed_point_relative_increment"
        ),
        "final_residual_inf_n": final.get("residual_inf_n"),
        "final_fixed_point_relative_increment": final.get("fixed_point_relative_increment"),
        "final_max_translation_m": final.get("max_translation_m"),
        "rows": rows,
        "seconds": time.perf_counter() - step_started,
        "blockers": []
        if ready
        else [
            "uncoarsened_boundary_pdelta_step_not_converged",
        ],
        "equilibrium_step_meta": equilibrium_step_meta,
        "frozen_external_load_per_load_step": True,
        "outer_solver_mode": str(outer_solver_mode),
    }
    if seed_alpha_scan is not None:
        out["seed_alpha_scan"] = seed_alpha_scan
        out["initial_seed_strategy"] = "seed_alpha_scan_best_candidate"
    return out, u


def run_mgt_uncoarsened_boundary_pdelta_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    output_json: Path | None = None,
    checkpoint_dir: Path | None = None,
    resume_checkpoint_npz: Path | None = None,
    secant_seed_checkpoint_npz: Path | None = None,
    load_steps: tuple[float, ...] = (
        0.05,
        0.1,
        0.2,
        0.25,
        0.3,
        0.35,
        0.36,
        0.37,
        0.38,
        0.39,
        0.4,
        0.41,
        0.42,
        0.43,
        0.44,
        0.45,
        0.455,
    ),
    max_iterations_per_step: int = 5,
    max_equilibrium_newton_iterations_per_iteration: int = 6,
    outer_solver_mode: str = "newton_only",
    relaxation_factor: float = 1.0,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    residual_tolerance_n: float = 5.0e-4,
    relative_increment_tolerance: float = 1.0e-4,
    displacement_cap_m: float = 5.0,
    seed_alpha_scan_values: tuple[float, ...] = (),
    equilibrium_newton_allow_negative_alphas: bool = False,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    if not mgt_path.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_missing"],
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    try:
        temp_context = tempfile.TemporaryDirectory(prefix="mgt-uncoarsened-boundary-pdelta-")
        work_dir = Path(temp_context.name)
        roundtrip_json, roundtrip_npz, parser_report, parser_run = _run_uncoarsened_parser(
            mgt_path=mgt_path,
            work_dir=work_dir,
        )
        props = load_mgt_section_material_properties(mgt_path)
        section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
        material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
        plate_thickness_props = (
            props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
        )
        beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

        with np.load(roundtrip_npz, allow_pickle=False) as archive:
            node_id = np.asarray(archive["node_id"], dtype=np.int64)
            node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
            edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
            elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
            elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
            elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
            elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
            elem_angle_deg = (
                np.asarray(archive["elem_angle_deg"], dtype=np.float64)
                if "elem_angle_deg" in archive.files
                else _element_angle_array_from_props(props, elem_id)
            )
            conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
            conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)

        frame_elements, frame_select_meta = _select_frame_elements(
            node_xyz=node_xyz,
            edge_index=edge_index,
            elem_id=elem_id,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )
        node_index = {int(raw_node_id): int(index) for index, raw_node_id in enumerate(node_id.tolist())}
        restrained, support_meta = _authored_support_restraints(
            constraints=constraints,
            node_index=node_index,
        )
        spring_stiffness, spring_meta = _assemble_elastic_link_springs(
            links=elastic_links,
            node_index=node_index,
            dof_count=int(node_xyz.shape[0]) * DOF_PER_NODE,
            stiffness_scale_to_si=stiffness_scale_to_si,
        )
        base_axial_forces = _component_gravity_axial_forces(
            elements=frame_elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
        )
        n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
        resume_meta: dict[str, Any] | None = None
        if resume_checkpoint_npz is not None:
            resume_meta, u = _load_accepted_checkpoint(
                checkpoint_npz=resume_checkpoint_npz,
                expected_node_id=node_id,
            )
        else:
            u = np.zeros(n_dof, dtype=np.float64)
        secant_seed_meta: dict[str, Any] | None = None
        secant_seed_u: np.ndarray | None = None
        if secant_seed_checkpoint_npz is not None:
            secant_seed_meta, secant_seed_u = _load_accepted_checkpoint(
                checkpoint_npz=secant_seed_checkpoint_npz,
                expected_node_id=node_id,
            )
        step_results: list[dict[str, Any]] = []
        max_converged = float((resume_meta or {}).get("load_scale") or 0.0)
        secant_previous_load = (
            float(secant_seed_meta["load_scale"]) if secant_seed_meta is not None else None
        )
        secant_previous_u = (
            np.asarray(secant_seed_u, dtype=np.float64).copy()
            if secant_seed_u is not None
            else None
        )
        first_failed: float | None = None
        skipped_load_steps = [
            float(value) for value in load_steps if float(value) <= max_converged + 1.0e-12
        ]
        attempted_load_steps = [
            float(value) for value in load_steps if float(value) > max_converged + 1.0e-12
        ]
        saved_checkpoints: list[dict[str, Any]] = []
        secant_seed_used_count = 0
        for load_scale in attempted_load_steps:
            step_seed_u = u
            secant_seed_row: dict[str, Any] = {
                "enabled": False,
                "reason": "secant_seed_checkpoint_not_provided",
            }
            if secant_previous_load is not None and secant_previous_u is not None:
                if max_converged > secant_previous_load + 1.0e-12:
                    step_seed_u, secant_seed_row = _secant_predict_displacement(
                        previous_load_scale=secant_previous_load,
                        previous_u=secant_previous_u,
                        current_load_scale=max_converged,
                        current_u=u,
                        target_load_scale=float(load_scale),
                    )
                    secant_seed_used_count += 1
                else:
                    secant_seed_row = {
                        "enabled": False,
                        "reason": "secant_seed_checkpoint_must_precede_resume_checkpoint",
                        "previous_load_scale": secant_previous_load,
                        "current_load_scale": max_converged,
                    }
            row, next_u = _run_load_step(
                load_scale=float(load_scale),
                seed_u=step_seed_u,
                max_iterations=max_iterations_per_step,
                relaxation_factor=relaxation_factor,
                residual_tolerance_n=residual_tolerance_n,
                relative_increment_tolerance=relative_increment_tolerance,
                displacement_cap_m=displacement_cap_m,
                seed_alpha_scan_values=seed_alpha_scan_values,
                max_equilibrium_newton_iterations_per_iteration=(
                    max_equilibrium_newton_iterations_per_iteration
                ),
                outer_solver_mode=outer_solver_mode,
                equilibrium_newton_allow_negative_alphas=(
                    equilibrium_newton_allow_negative_alphas
                ),
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
                restrained=restrained,
                base_axial_forces=base_axial_forces,
                base_frame_gravity_scale=frame_gravity_load_scale,
            )
            row["initial_seed_strategy"] = (
                row.get("initial_seed_strategy")
                or (
                    "secant_predicted_checkpoint_seed"
                    if bool(secant_seed_row.get("enabled"))
                    else "resume_checkpoint_seed"
                )
            )
            row["secant_seed"] = secant_seed_row
            step_results.append(row)
            if bool(row.get("ready")):
                previous_accepted_load = max_converged
                previous_accepted_u = u.copy()
                max_converged = float(load_scale)
                u = next_u
                if secant_previous_u is not None:
                    secant_previous_load = previous_accepted_load
                    secant_previous_u = previous_accepted_u
                if checkpoint_dir is not None:
                    saved_checkpoints.append(
                        _write_accepted_checkpoint(
                            checkpoint_dir=checkpoint_dir,
                            load_scale=float(load_scale),
                            displacement_u=u,
                            node_id=node_id,
                            step_row=row,
                        )
                    )
                continue
            first_failed = float(load_scale)
            break
        coarsening = parser_report.get("coarsening") if isinstance(parser_report.get("coarsening"), dict) else {}
        full_ready = max_converged >= 1.0
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "ready" if full_ready else "partial",
            "uncoarsened_boundary_pdelta_ready": bool(full_ready),
            "full_load_nonlinear_newton_ready": False,
            "roundtrip_policy": {
                "resolve_rigid_links": False,
                "drop_unreferenced_nodes": False,
                "parser_report_contract_pass": bool(parser_report.get("contract_pass")),
                "parser_coarsening": coarsening,
                "parser_run": parser_run,
            },
            "source": {
                "mgt_path": str(mgt_path),
                "source_family": "midas_mgt",
                "provenance": "repo_benchmark_bridge",
                "blocks": ["*CONSTRAINT", "*ELASTICLINK", "*ELEMENT", "*THICKNESS"],
            },
            "solve_scope": (
                "uncoarsened_frame_shell_boundary_tangent_reference_geometry_pdelta_probe"
            ),
            "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
            "outer_solver_mode": str(outer_solver_mode),
            "equilibrium_newton_allow_negative_alphas": bool(
                equilibrium_newton_allow_negative_alphas
            ),
            "unit_policy": {
                "mgt_force_unit": "kN",
                "mgt_length_unit": "m",
                "elastic_link_stiffness_scale_to_si": float(stiffness_scale_to_si),
                "base_frame_gravity_load_scale": float(frame_gravity_load_scale),
                "load_scale_multiplies_frame_gravity_and_shell_surface_probe_load": True,
            },
            "load_steps_requested": [float(value) for value in load_steps],
            "max_converged_load_scale": float(max_converged),
            "first_failed_load_scale": first_failed,
            "step_results": step_results,
            "checkpoint_resume": {
                "supported": True,
                "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
                "checkpoint_dir": str(checkpoint_dir) if checkpoint_dir is not None else None,
                "resume_checkpoint_npz": (
                    str(resume_checkpoint_npz) if resume_checkpoint_npz is not None else None
                ),
                "secant_seed_checkpoint_npz": (
                    str(secant_seed_checkpoint_npz)
                    if secant_seed_checkpoint_npz is not None
                    else None
                ),
                "resume_from_load_scale": (resume_meta or {}).get("load_scale"),
                "resume_checkpoint": resume_meta,
                "secant_seed_checkpoint": secant_seed_meta,
                "secant_seed_used_count": int(secant_seed_used_count),
                "seed_alpha_scan_values": [float(value) for value in seed_alpha_scan_values],
                "skipped_load_steps_before_resume": skipped_load_steps,
                "attempted_load_steps_after_resume": attempted_load_steps,
                "saved_checkpoint_count": int(len(saved_checkpoints)),
                "saved_checkpoints": saved_checkpoints,
                "claim_boundary": (
                    "Accepted displacement states can be written and replayed as exact seeds for later "
                    "frontier probes. This reduces rerun cost for bracket search, but it does not change "
                    "the nonlinear convergence gate or promote a failed residual/increment state."
                ),
            },
            "mesh_fingerprint": {
                **frame_select_meta,
                "node_count": int(node_xyz.shape[0]),
                "dof_count": int(n_dof),
                "element_count": int(elem_id.shape[0]),
                "elastic_link_spring_stiffness_nnz": int(spring_stiffness.nnz),
            },
            "boundary_summary": {
                **support_meta,
                **spring_meta,
            },
            "runtime_metrics": {
                "backend": "scipy_sparse_spsolve_cpu_uncoarsened_boundary_pdelta_probe",
                "total_seconds": time.perf_counter() - started,
            },
            "claim_boundary": (
                "This probe wires the uncoarsened authored support masks and finite elastic-link spring "
                "tangent into a reference-geometry frame-shell P-Delta fixed-point loop. Deformation enters "
                "only through the solved displacement state u under the equilibrium geometry contract. The "
                "frame tangent uses geometric stiffness from frame gravity axial forces. It is a nonlinear "
                "path diagnostic only; it is not a "
                "consistent Newton/Jacobian, material nonlinear, or full-load closure."
            ),
            "blockers": []
            if full_ready
            else [
                "uncoarsened_boundary_pdelta_not_full_load_closed",
                "consistent_newton_jacobian_required",
                "material_nonlinear_newton_required",
            ],
        }
    finally:
        if temp_context is not None:
            temp_context.cleanup()

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="Optional directory for accepted displacement-state checkpoints.",
    )
    parser.add_argument(
        "--resume-checkpoint-npz",
        type=Path,
        default=None,
        help="Optional accepted-state checkpoint to seed this continuation run.",
    )
    parser.add_argument(
        "--secant-seed-checkpoint-npz",
        type=Path,
        default=None,
        help=(
            "Optional earlier accepted-state checkpoint. When paired with --resume-checkpoint-npz, "
            "the probe extrapolates an initial seed for each next load step, then still requires "
            "the normal residual and unrelaxed fixed-point gates."
        ),
    )
    parser.add_argument(
        "--load-steps",
        default="0.05,0.1,0.2,0.25,0.3,0.35,0.36,0.37,0.38,0.39,0.4,0.41,0.42,0.43,0.44,0.45,0.455",
    )
    parser.add_argument("--max-iterations-per-step", type=int, default=5)
    parser.add_argument("--max-equilibrium-newton-iterations-per-iteration", type=int, default=12)
    parser.add_argument(
        "--outer-solver-mode",
        choices=("newton_only", "fixed_point_then_newton"),
        default="newton_only",
    )
    parser.add_argument("--relaxation-factor", type=float, default=1.0)
    parser.add_argument("--frame-gravity-load-scale", type=float, default=0.01)
    parser.add_argument("--stiffness-scale-to-si", type=float, default=1000.0)
    parser.add_argument("--residual-tolerance-n", type=float, default=5.0e-4)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--displacement-cap-m", type=float, default=5.0)
    parser.add_argument(
        "--equilibrium-newton-allow-negative-alphas",
        action="store_true",
        help=(
            "Opt-in signed alpha search for equilibrium Newton. This is a "
            "globalization diagnostic and does not relax residual/increment gates."
        ),
    )
    parser.add_argument(
        "--seed-alpha-scan-values",
        default="",
        help=(
            "Optional comma-separated alpha candidates for one-step seed globalization along "
            "the first fixed-point correction direction. Empty disables the scan."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_steps = tuple(float(value.strip()) for value in str(args.load_steps).split(",") if value.strip())
    seed_alpha_scan_values = tuple(
        float(value.strip())
        for value in str(args.seed_alpha_scan_values).split(",")
        if value.strip()
    )
    payload = run_mgt_uncoarsened_boundary_pdelta_probe(
        mgt_path=args.mgt_path,
        output_json=args.output_json,
        checkpoint_dir=args.checkpoint_dir,
        resume_checkpoint_npz=args.resume_checkpoint_npz,
        secant_seed_checkpoint_npz=args.secant_seed_checkpoint_npz,
        load_steps=load_steps,
        max_iterations_per_step=int(args.max_iterations_per_step),
        max_equilibrium_newton_iterations_per_iteration=int(
            args.max_equilibrium_newton_iterations_per_iteration
        ),
        outer_solver_mode=str(args.outer_solver_mode),
        relaxation_factor=float(args.relaxation_factor),
        frame_gravity_load_scale=float(args.frame_gravity_load_scale),
        stiffness_scale_to_si=float(args.stiffness_scale_to_si),
        residual_tolerance_n=float(args.residual_tolerance_n),
        relative_increment_tolerance=float(args.relative_increment_tolerance),
        displacement_cap_m=float(args.displacement_cap_m),
        seed_alpha_scan_values=seed_alpha_scan_values,
        equilibrium_newton_allow_negative_alphas=bool(
            args.equilibrium_newton_allow_negative_alphas
        ),
    )
    print(
        "mgt-uncoarsened-boundary-pdelta: "
        f"{payload['status']} max_load={payload.get('max_converged_load_scale')} "
        f"failed={payload.get('first_failed_load_scale')} -> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
