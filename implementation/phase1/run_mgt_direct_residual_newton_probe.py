#!/usr/bin/env python3
"""Probe direct residual Newton behavior for the uncoarsened MGT frame-shell model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

import numpy as np
from scipy.sparse import eye
from scipy.sparse.linalg import LinearOperator, gmres, spsolve

from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from run_mgt_coupled_frame_surface_sparse_equilibrium import _select_frame_elements, _translation_metrics
from run_mgt_frame_material_nonlinear_tangent import (
    _axial_strain,
    _material_tangent_state,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
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
from mgt_physical_residual_assembly import (
    assemble_newton_tangent_stiffness,
    assemble_physical_internal_forces,
    assemble_physical_internal_forces_batch,
    assemble_physical_residual,
)
from mgt_frame_force_based_assembly import prepack_frame_force_based_assembly
from mgt_hip_full_residual_backend import (
    HipFullResidualBatchBackend,
    HipFullResidualResidentWorkerBackend,
    HipFullResidualRustFfiBackend,
)
from mgt_shell_force_based_assembly import _cached_shell_operator
from mgt_shell_material_tangent import shell_material_tangent_by_surface_index
from mgt_shell_load_path import surface_pressure_load_path_filter


SCHEMA_VERSION = "mgt-direct-residual-newton-probe.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
DEFAULT_OUT = PRODUCTIZATION / "mgt_direct_residual_newton_probe.json"
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_relaxed_checkpoints/accepted_load_0p656.npz"
)
HIP_RESIDUAL_BATCH_REPLAY_BACKENDS = {
    "hip_full_residual",
    "hip_full_residual_resident",
    "rust_hip_full_residual_ffi",
}
GLOBAL_TANGENT_REFRESH_DEFERRED_TO_ROW = "current_tangent_residual_row_correction"
GLOBAL_TANGENT_REFRESH_DEFERRED_BACKEND = (
    "deferred_to_current_tangent_residual_row_hip_fd_jvp"
)
GLOBAL_TANGENT_REFRESH_DEFERRED_BLOCKER = (
    "rocm_hip_deferred_row_tangent_refresh_not_closed"
)
ROCM_VISIBILITY_SETTING_KEYS = (
    "HIP_VISIBLE_DEVICES",
    "ROCR_VISIBLE_DEVICES",
    "CUDA_VISIBLE_DEVICES",
    "HSA_OVERRIDE_GFX_VERSION",
)


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _load_checkpoint(path: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray | None, np.ndarray | None]:
    with np.load(path, allow_pickle=False) as archive:
        load_scale = float(np.asarray(archive["load_scale"]).item())
        u = np.asarray(archive["displacement_u"], dtype=np.float64)
        state_history = (
            np.asarray(archive["accepted_state_history_u"], dtype=np.float64)
            if "accepted_state_history_u" in archive.files
            else None
        )
        residual_history = (
            np.asarray(archive["accepted_residual_history"], dtype=np.float64)
            if "accepted_residual_history" in archive.files
            else None
        )
        return (
            {
                "path": str(path),
                "load_scale": load_scale,
                "dof_count": int(u.size),
                "checkpoint_schema": str(np.asarray(archive["checkpoint_schema"]).item())
                if "checkpoint_schema" in archive.files
                else None,
                "accepted_state_history_count": int(state_history.shape[0])
                if state_history is not None and state_history.ndim == 2
                else 0,
                "accepted_residual_history_count": int(residual_history.shape[0])
                if residual_history is not None and residual_history.ndim == 2
                else 0,
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
            },
            u,
            state_history,
            residual_history,
        )


def _skipped_output_final_checkpoint_meta(
    *,
    output_final_checkpoint_npz: Path,
    checkpoint_npz: Path,
    final_direct_residual_inf: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "written": False,
        "path": str(output_final_checkpoint_npz),
        "reason": reason,
        "direct_residual_inf_n": float(final_direct_residual_inf),
        "source_checkpoint_path": str(checkpoint_npz),
    }


def _full_load_closure_gate(
    load_scale: float,
    *,
    required_load_scale: float = 1.0,
    tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    observed = float(load_scale)
    required = float(required_load_scale)
    tol = float(tolerance)
    passed = bool(np.isfinite(observed) and observed >= required - tol)
    return {
        "required": True,
        "required_load_scale": required,
        "observed_load_scale": observed,
        "tolerance": tol,
        "passed": passed,
        "claim_boundary": (
            "Full G1 closure requires the representative full mesh at full load "
            "scale 1.0. A sub-full-load checkpoint can be diagnostic evidence, "
            "but it must not be promoted to full-mesh/full-load nonlinear "
            "equilibrium closure."
        ),
    }


def _active_free(stiffness: Any, restrained: set[int]) -> tuple[np.ndarray, np.ndarray]:
    diag = np.asarray(stiffness.diagonal(), dtype=np.float64)
    active = np.asarray(np.where(np.abs(diag) > 1.0e-9)[0], dtype=np.int64)
    free = np.asarray([idx for idx in active.tolist() if idx not in restrained], dtype=np.int64)
    return active, free


def _service_tangent_by_element(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    u: np.ndarray,
    material_props: dict[int, dict[str, Any]],
) -> tuple[dict[int, float], dict[str, Any]]:
    tangent_by_element: dict[int, float] = {}
    ratios: list[float] = []
    family_counts: dict[str, int] = {}
    for elem in elements:
        mat = material_props.get(int(elem.material_id), {})
        state = _material_tangent_state(mat, _axial_strain(elem, node_xyz, u))
        tangent_by_element[int(elem.elem_id)] = float(state.solver_tangent_mpa)
        ratios.append(float(state.tangent_ratio))
        family_counts[state.material_family] = family_counts.get(state.material_family, 0) + 1
    return tangent_by_element, {
        "service_material_tangent_element_count": int(len(tangent_by_element)),
        "service_material_family_counts": family_counts,
        "service_min_tangent_ratio": float(min(ratios)) if ratios else 1.0,
        "service_mean_tangent_ratio": float(np.mean(ratios)) if ratios else 1.0,
    }


def _unique_positive_alphas(
    values: list[tuple[str, float]],
    *,
    min_alpha: float,
    max_alpha: float,
) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()
    for source, raw_value in values:
        value = float(raw_value)
        if not np.isfinite(value) or value <= 0.0:
            continue
        value = min(max(value, min_alpha), max_alpha)
        key = f"{value:.15g}"
        if key in seen:
            continue
        seen.add(key)
        rows.append((source, value))
    return rows


def _parse_matrix_free_basis_sources(raw: str | tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if raw is None:
        return ("history",)
    if isinstance(raw, str):
        tokens = [part.strip() for part in raw.split(",")]
    else:
        tokens = [str(part).strip() for part in raw]
    aliases = {
        "history": "history",
        "accepted_history": "history",
        "secant_history": "history",
        "newton": "current_newton",
        "current_newton": "current_newton",
        "current_newton_correction": "current_newton",
    }
    parsed: list[str] = []
    for token in tokens:
        if not token:
            continue
        normalized = aliases.get(token.lower())
        if normalized is None:
            raise ValueError(
                "matrix-free Jacobian basis sources must be drawn from "
                "'history' and 'current_newton'"
            )
        if normalized not in parsed:
            parsed.append(normalized)
    return tuple(parsed or ("history",))


def _expand_support_to_node_blocks(
    support_cols: np.ndarray,
    current_free: np.ndarray,
    *,
    dof_per_node: int = DOF_PER_NODE,
) -> np.ndarray:
    if support_cols.size == 0 or current_free.size == 0:
        return np.asarray(sorted(set(int(col) for col in support_cols.tolist())), dtype=np.int64)
    selected_nodes = {
        int(current_free[int(col)]) // int(dof_per_node)
        for col in support_cols.tolist()
        if 0 <= int(col) < int(current_free.size)
    }
    if not selected_nodes:
        return np.asarray(sorted(set(int(col) for col in support_cols.tolist())), dtype=np.int64)
    expanded = {
        int(local_col)
        for local_col, global_dof in enumerate(current_free.tolist())
        if int(global_dof) // int(dof_per_node) in selected_nodes
    }
    expanded.update(int(col) for col in support_cols.tolist())
    return np.asarray(sorted(expanded), dtype=np.int64)


def _select_residual_node_block_rows(
    residual: np.ndarray,
    current_free: np.ndarray,
    *,
    target_node_count: int,
    dof_per_node: int = DOF_PER_NODE,
) -> tuple[np.ndarray, dict[str, Any]]:
    if residual.size == 0 or current_free.size == 0 or target_node_count <= 0:
        return np.asarray([], dtype=np.int64), {
            "target_node_count": 0,
            "selected_nodes": [],
        }
    if residual.size != current_free.size:
        raise ValueError("residual and current_free must describe the same free DOF rows")
    node_scores: dict[int, float] = {}
    node_row_order: dict[int, list[int]] = {}
    for local_row, global_dof in enumerate(current_free.tolist()):
        node = int(global_dof) // int(dof_per_node)
        value = abs(float(residual[int(local_row)]))
        node_scores[node] = node_scores.get(node, 0.0) + value
        node_row_order.setdefault(node, []).append(int(local_row))
    ranked_nodes = sorted(node_scores, key=lambda node: (-node_scores[node], node))
    selected_nodes = ranked_nodes[: min(int(target_node_count), len(ranked_nodes))]
    selected_node_set = set(selected_nodes)
    rows = [
        int(local_row)
        for local_row, global_dof in enumerate(current_free.tolist())
        if int(global_dof) // int(dof_per_node) in selected_node_set
    ]
    rows.sort(key=lambda local_row: (int(current_free[int(local_row)]) // int(dof_per_node), int(current_free[int(local_row)])))
    return np.asarray(rows, dtype=np.int64), {
        "target_node_count": int(len(selected_nodes)),
        "selected_nodes": [int(node) for node in selected_nodes],
        "selected_node_score_sum": float(sum(node_scores[node] for node in selected_nodes)),
        "selected_node_scores": [
            {"node": int(node), "residual_l1_n": float(node_scores[node])}
            for node in selected_nodes
        ],
        "selected_node_row_counts": [
            {"node": int(node), "row_count": int(len(node_row_order[node]))}
            for node in selected_nodes
        ],
    }


def _load_frontier_component_top_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    probe_path = Path(path)
    if not probe_path.is_file():
        return []
    try:
        payload = json.loads(probe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    breakdown = payload.get("residual_component_breakdown")
    if not isinstance(breakdown, dict):
        final_residual = payload.get("final_direct_residual")
        if isinstance(final_residual, dict):
            breakdown = final_residual.get("residual_component_breakdown")
    if not isinstance(breakdown, dict):
        base_residual = payload.get("base_direct_residual")
        if isinstance(base_residual, dict):
            breakdown = base_residual.get("residual_component_breakdown")
    if not isinstance(breakdown, dict):
        return []
    rows = breakdown.get("top_rows")
    if not isinstance(rows, list):
        return []
    clean_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("global_dof") is None:
            continue
        try:
            global_dof = int(row["global_dof"])
        except (TypeError, ValueError):
            continue
        clean_rows.append(
            {
                **row,
                "global_dof": global_dof,
                "node_index": int(row.get("node_index", global_dof // DOF_PER_NODE)),
                "dominant_component": str(row.get("dominant_component", "unknown")),
                "residual_n": float(row.get("residual_n", 0.0)),
            }
        )
    return clean_rows


def _component_breakdown(
    *,
    component_forces: dict[str, np.ndarray],
    free: np.ndarray,
    residual: np.ndarray,
    rhs: np.ndarray,
    top_count: int = 24,
) -> dict[str, Any]:
    free_idx = np.asarray(free, dtype=np.int64)
    residual_np = np.asarray(residual, dtype=np.float64)
    rhs_np = np.asarray(rhs, dtype=np.float64)
    components = {
        str(name): np.asarray(values, dtype=np.float64)
        for name, values in component_forces.items()
        if isinstance(values, np.ndarray)
    }
    component_inf = {
        name: (
            float(np.max(np.abs(values[free_idx])))
            if free_idx.size and values.size
            else 0.0
        )
        for name, values in components.items()
    }
    if not residual_np.size:
        return {
            "component_inf_n": component_inf,
            "top_rows": [],
            "top_row_dominant_component_counts": {},
        }
    row_count = min(max(int(top_count), 1), int(residual_np.size))
    top_rows = np.argpartition(np.abs(residual_np), -row_count)[-row_count:]
    top_rows = top_rows[np.argsort(-np.abs(residual_np[top_rows]))]
    dof_names = ("ux", "uy", "uz", "rx", "ry", "rz")
    rows: list[dict[str, Any]] = []
    dominant_counts: dict[str, int] = {}
    for local_row in top_rows.tolist():
        global_dof = int(free_idx[int(local_row)])
        component_values = {
            name: float(values[global_dof])
            for name, values in components.items()
            if 0 <= global_dof < int(values.size)
        }
        max_component_abs = max(
            (abs(float(value)) for value in component_values.values()),
            default=0.0,
        )
        external_load = float(rhs_np[int(local_row)]) if int(local_row) < rhs_np.size else 0.0
        if max_component_abs <= 1.0e-12 and abs(external_load) > 1.0e-12:
            dominant = "external_only_unassembled"
        else:
            dominant = max(
                component_values,
                key=lambda name: abs(float(component_values[name])),
                default="none",
            )
        dominant_counts[dominant] = dominant_counts.get(dominant, 0) + 1
        rows.append(
            {
                "free_row": int(local_row),
                "global_dof": global_dof,
                "node_index": int(global_dof // DOF_PER_NODE),
                "dof": dof_names[global_dof % DOF_PER_NODE],
                "residual_n": float(residual_np[int(local_row)]),
                "external_load_n": external_load,
                "component_values_n": component_values,
                "internal_sum_n": float(sum(component_values.values())),
                "dominant_component": dominant,
            }
        )
    return {
        "component_inf_n": component_inf,
        "top_rows": rows,
        "top_row_dominant_component_counts": dominant_counts,
    }


def _select_frontier_component_rows(
    current_free: np.ndarray,
    frontier_rows: list[dict[str, Any]],
    *,
    target_row_count: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if current_free.size == 0 or target_row_count <= 0 or not frontier_rows:
        return np.asarray([], dtype=np.int64), {
            "target_frontier_row_count": 0,
            "selected_frontier_rows": [],
        }
    free_lookup = {int(global_dof): int(index) for index, global_dof in enumerate(current_free.tolist())}
    component_order = ("frame", "shell_membrane", "shell_bending_drilling")
    grouped: dict[str, list[dict[str, Any]]] = {component: [] for component in component_order}
    grouped["other"] = []
    for row in frontier_rows:
        component = str(row.get("dominant_component", "other"))
        key = component if component in grouped else "other"
        grouped[key].append(row)

    selected: list[dict[str, Any]] = []
    seen_global_dofs: set[int] = set()
    max_count = int(target_row_count)
    while len(selected) < max_count:
        progressed = False
        for component in (*component_order, "other"):
            rows = grouped.get(component, [])
            while rows:
                row = rows.pop(0)
                global_dof = int(row["global_dof"])
                if global_dof in seen_global_dofs or global_dof not in free_lookup:
                    continue
                selected.append(row)
                seen_global_dofs.add(global_dof)
                progressed = True
                break
            if len(selected) >= max_count:
                break
        if not progressed:
            break

    if len(selected) < max_count:
        for row in frontier_rows:
            global_dof = int(row["global_dof"])
            if global_dof in seen_global_dofs or global_dof not in free_lookup:
                continue
            selected.append(row)
            seen_global_dofs.add(global_dof)
            if len(selected) >= max_count:
                break

    target_rows = np.asarray(
        [free_lookup[int(row["global_dof"])] for row in selected],
        dtype=np.int64,
    )
    return target_rows, {
        "target_frontier_row_count": int(len(selected)),
        "configured_frontier_row_count": int(target_row_count),
        "selected_frontier_rows": [
            {
                "global_dof": int(row["global_dof"]),
                "node_index": int(row.get("node_index", int(row["global_dof"]) // DOF_PER_NODE)),
                "dof": row.get("dof"),
                "dominant_component": str(row.get("dominant_component", "unknown")),
                "residual_n": float(row.get("residual_n", 0.0)),
                "component_values_n": row.get("component_values_n")
                if isinstance(row.get("component_values_n"), dict)
                else {},
            }
            for row in selected
        ],
    }


def _frontier_component_row_weights(
    target_meta: dict[str, Any],
    *,
    mode: str,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    scale_mode = str(mode).strip()
    if scale_mode in {"", "none"}:
        return None, {"mode": "none", "enabled": False}
    selected_rows = target_meta.get("selected_frontier_rows")
    if not isinstance(selected_rows, list) or not selected_rows:
        return None, {
            "mode": scale_mode,
            "enabled": False,
            "reason": "frontier_rows_unavailable",
        }
    weights: list[float] = []
    denominators: list[float] = []
    for row in selected_rows:
        if not isinstance(row, dict):
            denominators.append(1.0)
            weights.append(1.0)
            continue
        component_values = row.get("component_values_n")
        component = str(row.get("dominant_component", "unknown"))
        if not isinstance(component_values, dict):
            component_values = {}
        if scale_mode == "dominant_component_magnitude":
            denominator = abs(float(component_values.get(component, 0.0)))
        elif scale_mode == "total_component_magnitude":
            denominator = sum(abs(float(value)) for value in component_values.values())
        else:
            denominator = 1.0
        denominator = max(float(denominator), 1.0)
        denominators.append(denominator)
        weights.append(1.0 / denominator)
    if not weights:
        return None, {
            "mode": scale_mode,
            "enabled": False,
            "reason": "empty_weight_vector",
        }
    return np.asarray(weights, dtype=np.float64), {
        "mode": scale_mode,
        "enabled": True,
        "min_weight": float(min(weights)),
        "max_weight": float(max(weights)),
        "denominators": [float(value) for value in denominators],
    }


def _local_shell_basis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape != (3, 3):
        return None
    v1 = pts[1] - pts[0]
    v2 = pts[2] - pts[0]
    normal = np.cross(v1, v2)
    normal_norm = float(np.linalg.norm(normal))
    v1_norm = float(np.linalg.norm(v1))
    if normal_norm <= 1.0e-10 or v1_norm <= 1.0e-12:
        return None
    e1 = v1 / v1_norm
    e3 = normal / normal_norm
    e2 = np.cross(e3, e1)
    e2 /= max(float(np.linalg.norm(e2)), 1.0e-12)
    return e1, e2, e3


def _triangulate_shell_conn(conn: list[int]) -> list[tuple[int, int, int]]:
    if len(conn) == 3:
        return [(conn[0], conn[1], conn[2])]
    if len(conn) == 4:
        return [(conn[0], conn[1], conn[2]), (conn[0], conn[2], conn[3])]
    return []


def _shell_geometry_normal_translation_dofs_by_node(
    *,
    nodes: list[int],
    node_xyz: np.ndarray,
    participation_threshold: float,
) -> dict[int, set[int]]:
    xyz = np.asarray(node_xyz, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        return {}
    axis_by_dof = (
        np.asarray([1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([0.0, 1.0, 0.0], dtype=np.float64),
        np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
    )
    threshold = max(float(participation_threshold), 0.0)
    selected: dict[int, set[int]] = {int(node): set() for node in nodes}
    for tri in _triangulate_shell_conn([int(node) for node in nodes]):
        if any(node < 0 or node >= int(xyz.shape[0]) for node in tri):
            continue
        basis = _local_shell_basis(np.asarray([xyz[node] for node in tri], dtype=np.float64))
        if basis is None:
            continue
        _e1, _e2, e3 = basis
        for dof_index, axis in enumerate(axis_by_dof):
            if abs(float(np.dot(axis, e3))) >= threshold:
                for node in tri:
                    selected.setdefault(int(node), set()).add(int(dof_index))
    return selected


def _select_residual_element_block_rows(
    residual: np.ndarray,
    current_free: np.ndarray,
    *,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    node_xyz: np.ndarray | None = None,
    elem_id: np.ndarray | None = None,
    elem_type_code: np.ndarray | None = None,
    target_element_count: int,
    neighbor_depth: int = 0,
    allowed_element_type_codes: set[int] | None = None,
    target_dof_indices: set[int] | None = None,
    target_shell_geometry_normal_translation_rows: bool = False,
    shell_normal_participation_threshold: float = 0.7071067811865476,
    dof_per_node: int = DOF_PER_NODE,
) -> tuple[np.ndarray, dict[str, Any]]:
    if (
        residual.size == 0
        or current_free.size == 0
        or target_element_count <= 0
        or conn_ptr.size < 2
    ):
        return np.asarray([], dtype=np.int64), {
            "target_element_count": 0,
            "selected_elements": [],
        }
    if residual.size != current_free.size:
        raise ValueError("residual and current_free must describe the same free DOF rows")

    node_to_rows: dict[int, list[int]] = {}
    for local_row, global_dof in enumerate(current_free.tolist()):
        node = int(global_dof) // int(dof_per_node)
        node_to_rows.setdefault(node, []).append(int(local_row))

    element_scores: dict[int, float] = {}
    element_rows: dict[int, list[int]] = {}
    element_nodes: dict[int, list[int]] = {}
    element_type_counts: dict[str, int] = {}
    node_to_elements: dict[int, set[int]] = {}
    element_count = int(conn_ptr.size - 1)
    allowed_types = (
        {int(value) for value in allowed_element_type_codes}
        if allowed_element_type_codes is not None
        else None
    )
    target_dofs = (
        {int(value) for value in target_dof_indices}
        if target_dof_indices is not None
        else None
    )
    use_shell_geometry_normals = bool(target_shell_geometry_normal_translation_rows)
    for element_index in range(element_count):
        start = int(conn_ptr[element_index])
        end = int(conn_ptr[element_index + 1])
        if start < 0 or end < start or end > int(conn_idx.size):
            continue
        element_type = (
            int(elem_type_code[element_index])
            if elem_type_code is not None and element_index < int(elem_type_code.size)
            else None
        )
        if allowed_types is not None and element_type not in allowed_types:
            continue
        nodes = sorted({int(node) for node in conn_idx[start:end].tolist()})
        shell_normal_dofs_by_node: dict[int, set[int]] = {}
        if use_shell_geometry_normals and node_xyz is not None:
            shell_normal_dofs_by_node = _shell_geometry_normal_translation_dofs_by_node(
                nodes=nodes,
                node_xyz=node_xyz,
                participation_threshold=shell_normal_participation_threshold,
            )
        rows = sorted(
            {
                row
                for node in nodes
                for row in node_to_rows.get(node, [])
                if target_dofs is None
                or int(current_free[int(row)]) % int(dof_per_node) in target_dofs
            }
        )
        if use_shell_geometry_normals:
            rows = [
                int(row)
                for row in rows
                if int(current_free[int(row)]) % int(dof_per_node)
                in shell_normal_dofs_by_node.get(
                    int(current_free[int(row)]) // int(dof_per_node),
                    set(),
                )
            ]
        if not rows:
            continue
        score = float(np.sum(np.abs(residual[np.asarray(rows, dtype=np.int64)])))
        element_scores[element_index] = score
        element_rows[element_index] = rows
        element_nodes[element_index] = nodes
        for node in nodes:
            node_to_elements.setdefault(int(node), set()).add(int(element_index))
        if elem_type_code is not None and element_index < int(elem_type_code.size):
            key = str(int(elem_type_code[element_index]))
            element_type_counts[key] = element_type_counts.get(key, 0) + 1

    ranked_elements = sorted(
        element_scores,
        key=lambda element_index: (-element_scores[element_index], element_index),
    )
    seed_elements = ranked_elements[: min(int(target_element_count), len(ranked_elements))]
    selected_element_set = set(int(element_index) for element_index in seed_elements)
    neighbor_depth = max(int(neighbor_depth), 0)
    for _depth in range(neighbor_depth):
        expanded = set(selected_element_set)
        for element_index in selected_element_set:
            for node in element_nodes.get(int(element_index), []):
                expanded.update(node_to_elements.get(int(node), set()))
        selected_element_set = expanded
    selected_elements = sorted(
        selected_element_set,
        key=lambda element_index: (-element_scores.get(element_index, 0.0), element_index),
    )
    selected_row_set = {
        int(row)
        for element_index in selected_elements
        for row in element_rows.get(int(element_index), [])
    }
    rows = sorted(
        selected_row_set,
        key=lambda local_row: (
            int(current_free[int(local_row)]) // int(dof_per_node),
            int(current_free[int(local_row)]),
        ),
    )

    selected_meta: list[dict[str, Any]] = []
    selected_element_type_counts: dict[str, int] = {}
    for element_index in selected_elements:
        raw_elem_id = (
            int(elem_id[element_index])
            if elem_id is not None and element_index < int(elem_id.size)
            else int(element_index)
        )
        if elem_type_code is not None and element_index < int(elem_type_code.size):
            selected_type_key = str(int(elem_type_code[element_index]))
            selected_element_type_counts[selected_type_key] = (
                selected_element_type_counts.get(selected_type_key, 0) + 1
            )
        selected_meta.append(
            {
                "element_index": int(element_index),
                "element_id": raw_elem_id,
                "elem_type_code": int(elem_type_code[element_index])
                if elem_type_code is not None and element_index < int(elem_type_code.size)
                else None,
                "node_count": int(len(element_nodes.get(element_index, []))),
                "row_count": int(len(element_rows.get(element_index, []))),
                "residual_l1_n": float(element_scores.get(element_index, 0.0)),
            }
        )

    return np.asarray(rows, dtype=np.int64), {
        "target_element_count": int(len(selected_elements)),
        "seed_element_count": int(len(seed_elements)),
        "neighbor_depth": int(neighbor_depth),
        "selected_elements": selected_meta,
        "selected_element_score_sum": float(
            sum(element_scores[element_index] for element_index in selected_elements)
        ),
        "candidate_element_type_counts": element_type_counts,
        "selected_element_type_counts": selected_element_type_counts,
        "allowed_element_type_codes": sorted(allowed_types) if allowed_types is not None else None,
        "target_dof_indices": sorted(target_dofs) if target_dofs is not None else None,
        "target_shell_geometry_normal_translation_rows": use_shell_geometry_normals,
        "shell_normal_participation_threshold": (
            float(shell_normal_participation_threshold) if use_shell_geometry_normals else None
        ),
    }


def _truncated_svd_lstsq(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    relative_cutoff: float = 0.0,
    max_condition: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, int, np.ndarray, dict[str, Any]]:
    a = np.asarray(matrix, dtype=np.float64)
    b = np.asarray(rhs, dtype=np.float64)
    column_count = int(a.shape[1]) if a.ndim == 2 else 0
    if a.ndim != 2 or b.ndim != 1 or a.shape[0] != b.shape[0] or column_count == 0:
        return (
            np.zeros(column_count, dtype=np.float64),
            np.asarray([], dtype=np.float64),
            0,
            np.asarray([], dtype=np.float64),
            {
                "solve_method": "truncated_svd",
                "svd_truncation_enabled": True,
                "svd_truncation_reason": "invalid_or_empty_system",
            },
        )

    u, singular_values, vh = np.linalg.svd(a, full_matrices=False)
    spectral_scale = float(np.max(singular_values)) if singular_values.size else 0.0
    cutoff = 0.0
    relative_cutoff = max(float(relative_cutoff), 0.0)
    max_condition = max(float(max_condition), 0.0)
    if spectral_scale > 0.0:
        if relative_cutoff > 0.0:
            cutoff = max(cutoff, relative_cutoff * spectral_scale)
        if max_condition > 0.0:
            cutoff = max(cutoff, spectral_scale / max_condition)
    keep = np.asarray(
        [(float(value) > cutoff and float(value) > 0.0) for value in singular_values],
        dtype=bool,
    )
    rank = int(np.count_nonzero(keep))
    if rank:
        projected = u[:, keep].T @ b
        coeffs = vh[keep, :].T @ (projected / singular_values[keep])
    else:
        coeffs = np.zeros(column_count, dtype=np.float64)
    residual_vector = a @ coeffs - b
    residual_sum = np.asarray([float(np.dot(residual_vector, residual_vector))], dtype=np.float64)
    meta = {
        "solve_method": "truncated_svd",
        "svd_truncation_enabled": True,
        "svd_relative_cutoff": float(relative_cutoff),
        "svd_max_condition": float(max_condition),
        "svd_effective_cutoff": float(cutoff),
        "svd_spectral_scale": float(spectral_scale),
        "svd_kept_singular_value_count": int(rank),
        "svd_dropped_singular_value_count": int(singular_values.size - rank),
    }
    return coeffs, residual_sum, rank, singular_values, meta


def _torch_hip_gmres_once(
    matvec: Any,
    rhs: np.ndarray,
    *,
    restart: int,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Run one restarted GMRES cycle with vector algebra on a ROCm torch device."""
    b_cpu = np.asarray(rhs, dtype=np.float64)
    meta: dict[str, Any] = {
        "linear_solver_backend": "torch_hip_gmres",
        "torch_hip_vector_algebra": False,
        "hip_krylov_solver_used": False,
        "python_matvec_orchestration": True,
        "host_vector_transfer_for_matvec": True,
        "krylov_restart": int(max(restart, 0)),
    }
    if b_cpu.ndim != 1:
        meta["unavailable_reason"] = "rhs_must_be_1d"
        return np.zeros_like(b_cpu, dtype=np.float64), 1, meta
    n = int(b_cpu.size)
    if n == 0:
        meta["torch_hip_vector_algebra"] = True
        meta["hip_krylov_solver_used"] = True
        return np.zeros_like(b_cpu, dtype=np.float64), 0, meta
    try:
        import torch  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on runtime image
        meta["unavailable_reason"] = "torch_import_failed"
        meta["torch_import_error"] = str(exc)
        return np.zeros_like(b_cpu, dtype=np.float64), 1, meta
    meta["torch_version"] = str(getattr(torch, "__version__", ""))
    meta["torch_rocm_version"] = str(getattr(torch.version, "hip", None))
    if getattr(torch.version, "hip", None) is None:
        meta["unavailable_reason"] = "torch_build_is_not_rocm"
        return np.zeros_like(b_cpu, dtype=np.float64), 1, meta
    try:
        hip_available = bool(torch.cuda.is_available())
    except Exception as exc:  # pragma: no cover - depends on ROCm runtime
        meta["unavailable_reason"] = "torch_hip_availability_check_failed"
        meta["torch_hip_availability_error"] = str(exc)
        return np.zeros_like(b_cpu, dtype=np.float64), 1, meta
    meta["torch_hip_device_available"] = hip_available
    if not hip_available:
        meta["unavailable_reason"] = "torch_hip_device_unavailable"
        return np.zeros_like(b_cpu, dtype=np.float64), 1, meta
    try:
        device = torch.device("cuda")
        device_name = torch.cuda.get_device_name(0)
        b = torch.as_tensor(b_cpu, dtype=torch.float64, device=device)
        beta = torch.linalg.vector_norm(b)
        beta_value = float(beta.detach().cpu().item())
        meta["torch_hip_device_name"] = str(device_name)
        meta["rhs_l2"] = beta_value
        if beta_value <= 1.0e-30:
            meta["torch_hip_vector_algebra"] = True
            meta["hip_krylov_solver_used"] = True
            meta["arnoldi_column_count"] = 0
            return np.zeros_like(b_cpu, dtype=np.float64), 0, meta
        m = max(1, min(int(restart), n))
        v = torch.zeros((n, m + 1), dtype=torch.float64, device=device)
        h = torch.zeros((m + 1, m), dtype=torch.float64, device=device)
        v[:, 0] = b / beta
        used_cols = 0
        breakdown = False
        for col in range(m):
            direction_cpu = v[:, col].detach().cpu().numpy()
            action_cpu = np.asarray(matvec(direction_cpu), dtype=np.float64)
            if action_cpu.shape != b_cpu.shape:
                meta["unavailable_reason"] = "matvec_shape_mismatch"
                meta["matvec_shape"] = list(action_cpu.shape)
                return np.zeros_like(b_cpu, dtype=np.float64), 1, meta
            w = torch.as_tensor(action_cpu, dtype=torch.float64, device=device)
            for row in range(col + 1):
                h[row, col] = torch.dot(v[:, row], w)
                w = w - h[row, col] * v[:, row]
            h[col + 1, col] = torch.linalg.vector_norm(w)
            used_cols = col + 1
            h_next = float(h[col + 1, col].detach().cpu().item())
            if h_next <= 1.0e-30:
                breakdown = True
                break
            if col + 1 < m:
                v[:, col + 1] = w / h[col + 1, col]
        e1 = torch.zeros((used_cols + 1,), dtype=torch.float64, device=device)
        e1[0] = beta
        h_used = h[: used_cols + 1, :used_cols]
        y = torch.linalg.lstsq(h_used, e1).solution
        x = v[:, :used_cols] @ y
        correction = x.detach().cpu().numpy().astype(np.float64, copy=False)
        residual_vec = h_used @ y - e1
        meta.update(
            {
                "torch_hip_vector_algebra": True,
                "hip_krylov_solver_used": True,
                "arnoldi_column_count": int(used_cols),
                "arnoldi_breakdown": bool(breakdown),
                "least_squares_residual_l2": float(
                    torch.linalg.vector_norm(residual_vec).detach().cpu().item()
                ),
            }
        )
        return correction, 0, meta
    except Exception as exc:  # pragma: no cover - depends on ROCm linalg support
        meta["unavailable_reason"] = "torch_hip_gmres_failed"
        meta["torch_hip_gmres_error"] = str(exc)
        return np.zeros_like(b_cpu, dtype=np.float64), 1, meta


def _normalize_residual_batch_replay_backend(value: str) -> str:
    backend = str(value).strip()
    if backend in {"cpu", *HIP_RESIDUAL_BATCH_REPLAY_BACKENDS}:
        return backend
    return "cpu"


def _normalize_global_krylov_linear_solver_backend(value: str) -> str:
    backend = str(value).strip().lower()
    if backend in {"scipy_host_gmres", "torch_hip_gmres"}:
        return backend
    return "scipy_host_gmres"


def _device_path_status(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not payload["exists"]:
        return payload
    try:
        stat_result = path.stat()
    except Exception as exc:
        payload["stat_error"] = exc.__class__.__name__
        return payload
    payload.update(
        {
            "is_dir": path.is_dir(),
            "is_char_device": bool(os.stat(path).st_mode and path.is_char_device()),
            "mode_octal": f"{stat_result.st_mode & 0o7777:04o}",
            "uid": int(stat_result.st_uid),
            "gid": int(stat_result.st_gid),
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
        }
    )
    if path.is_dir():
        try:
            entries = sorted(child.name for child in path.iterdir())
        except Exception as exc:
            payload["list_error"] = exc.__class__.__name__
        else:
            payload["entry_count"] = len(entries)
            payload["entries_sample"] = entries[:20]
            payload["render_nodes"] = [
                name for name in entries if name.startswith("renderD")
            ]
    return payload


def _rocm_device_runtime_diagnostics(
    *,
    kfd_path: Path = Path("/dev/kfd"),
    dri_path: Path = Path("/dev/dri"),
) -> dict[str, Any]:
    kfd = _device_path_status(kfd_path)
    dri = _device_path_status(dri_path)
    blockers: list[str] = []
    if not kfd.get("exists"):
        blockers.append("dev_kfd_missing")
    elif not (kfd.get("readable") and kfd.get("writable")):
        blockers.append("dev_kfd_not_readable_writable")
    if not dri.get("exists"):
        blockers.append("dev_dri_missing")
    elif not dri.get("render_nodes"):
        blockers.append("dev_dri_render_nodes_missing")
    return {
        "device_nodes": {
            "kfd": kfd,
            "dri": dri,
        },
        "process_group_ids": sorted(int(group) for group in os.getgroups()),
        "rocm_commands": {
            "rocminfo": shutil.which("rocminfo"),
            "rocm_smi": shutil.which("rocm-smi"),
            "hipcc": shutil.which("hipcc"),
        },
        "visibility_settings": {
            key: os.environ.get(key)
            for key in ROCM_VISIBILITY_SETTING_KEYS
            if key in os.environ
        },
        "runtime_blockers": blockers,
    }


def _rocm_hip_runtime_preflight() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "hip_available": False,
        "torch_importable": False,
        "torch_rocm_build": False,
        "torch_hip_device_available": False,
    }
    payload.update(_rocm_device_runtime_diagnostics())
    try:
        import torch  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on runtime image
        payload["unavailable_reason"] = "torch_import_failed"
        payload["torch_import_error"] = str(exc)
        return payload

    payload["torch_importable"] = True
    payload["torch_version"] = str(getattr(torch, "__version__", ""))
    torch_rocm_version = getattr(torch.version, "hip", None)
    payload["torch_rocm_version"] = str(torch_rocm_version)
    if torch_rocm_version is None:
        payload["unavailable_reason"] = "torch_build_is_not_rocm"
        return payload
    payload["torch_rocm_build"] = True

    try:
        hip_available = bool(torch.cuda.is_available())
    except Exception as exc:  # pragma: no cover - depends on ROCm runtime
        payload["unavailable_reason"] = "torch_hip_availability_check_failed"
        payload["torch_hip_availability_error"] = str(exc)
        return payload
    payload["torch_hip_device_available"] = hip_available
    if not hip_available:
        payload["unavailable_reason"] = "torch_hip_device_unavailable"
        return payload
    runtime_blockers = payload.get("runtime_blockers")
    if isinstance(runtime_blockers, list) and runtime_blockers:
        payload["unavailable_reason"] = "rocm_device_runtime_blocked"
        return payload

    payload["hip_available"] = True
    try:
        payload["torch_hip_device_count"] = int(torch.cuda.device_count())
        payload["torch_hip_device_name"] = str(torch.cuda.get_device_name(0))
    except Exception as exc:  # pragma: no cover - depends on ROCm runtime
        payload["torch_hip_device_metadata_error"] = str(exc)
    return payload


def _hip_runtime_unavailable_direct_probe_payload(
    *,
    generated_at: str,
    started: float,
    mgt_path: Path,
    checkpoint_npz: Path,
    enable_matrix_free_global_krylov: bool,
    global_batch_backend: str,
    global_require_hip_batch_replay: bool,
    global_linear_solver_backend: str,
    global_linear_solver_auto_reason: str | None,
    enable_current_tangent_residual_row_correction: bool,
    row_batch_backend: str,
    row_require_hip_batch_replay: bool,
    hip_preflight: dict[str, Any],
) -> dict[str, Any]:
    fallback_zero_audit = {
        "fallback_zero_passed": False,
        "fallback_zero_boundary_count": 1,
        "fallback_zero_boundaries": [
            {
                "boundary": "direct_probe_rocm_hip_runtime_unavailable",
                "path": "direct_residual_newton_probe",
                "detail": "hip_runtime_required_preflight_failed_before_cpu_assembly",
                "reason": hip_preflight.get("unavailable_reason"),
            }
        ],
    }
    matrix_free_global_krylov: dict[str, Any] = {
        "enabled": bool(enable_matrix_free_global_krylov),
        "attempted": False,
        "accepted": False,
        "promoted_to_final_state": False,
        "batch_replay_backend": str(global_batch_backend),
        "require_hip_batch_replay": bool(global_require_hip_batch_replay),
        "linear_solver_backend": str(global_linear_solver_backend),
        "require_hip_krylov_solver": bool(
            global_linear_solver_backend == "torch_hip_gmres"
            or global_require_hip_batch_replay
        ),
        "hip_runtime_preflight": hip_preflight,
        "stop_reason": "rocm_hip_runtime_unavailable",
    }
    if global_linear_solver_auto_reason is not None:
        matrix_free_global_krylov[
            "linear_solver_backend_auto_selected_reason"
        ] = global_linear_solver_auto_reason
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "status": "partial",
        "direct_residual_newton_ready": False,
        "source": {
            "mgt_path": str(mgt_path),
            "checkpoint_npz": str(checkpoint_npz),
            "provenance": "repo_benchmark_bridge",
        },
        "rocm_hip_runtime_preflight": hip_preflight,
        "residual_contract": {
            "definition": "R(u, lambda) = F_int(u) - lambda * F_ext",
            "material_newton_gate_passed": False,
            "state_dependent_material_newton_closure_passed": False,
            "consistent_residual_jacobian_newton_gate_passed": False,
            "consistent_residual_jacobian_newton_blockers": [
                "rocm_hip_runtime_unavailable",
                "consistent_residual_jacobian_newton_not_executed",
            ],
            "material_newton_breadth_blockers": [
                "rocm_hip_runtime_unavailable",
                "material_newton_not_executed",
            ],
            "hip_residual_engine_contract_passed": False,
            "hip_residual_engine_required": bool(
                global_require_hip_batch_replay or row_require_hip_batch_replay
            ),
            "hip_residual_engine_required_lane_count": int(
                bool(enable_matrix_free_global_krylov and global_require_hip_batch_replay)
            )
            + int(
                bool(
                    enable_current_tangent_residual_row_correction
                    and row_require_hip_batch_replay
                )
            ),
            "hip_residual_engine_passed_lane_count": 0,
            "hip_residual_engine_backends": sorted(
                {
                    backend
                    for backend in (str(global_batch_backend), str(row_batch_backend))
                    if backend in HIP_RESIDUAL_REPLAY_BACKENDS
                }
            ),
            "hip_residual_engine_blockers": ["rocm_hip_runtime_unavailable"],
        },
        "matrix_free_global_krylov": matrix_free_global_krylov,
        "current_tangent_residual_row_correction": {
            "enabled": bool(enable_current_tangent_residual_row_correction),
            "attempted": False,
            "accepted": False,
            "promoted_to_final_state": False,
            "batch_replay_backend": str(row_batch_backend),
            "require_hip_batch_replay": bool(row_require_hip_batch_replay),
            "hip_runtime_preflight": hip_preflight,
            "stop_reason": "rocm_hip_runtime_unavailable",
        },
        "gate_assessment": {
            "direct_residual_gate_passed": False,
            "relative_increment_gate_verified": False,
            "relative_increment_gate_passed": False,
            "material_newton_breadth_passed": False,
            "material_newton_breadth_blockers": [
                "rocm_hip_runtime_unavailable",
                "material_newton_not_executed",
            ],
            "consistent_residual_jacobian_newton_passed": False,
            "consistent_residual_jacobian_newton_blockers": [
                "rocm_hip_runtime_unavailable",
                "consistent_residual_jacobian_newton_not_executed",
            ],
            "rocm_hip_runtime_available": False,
            "fallback_zero_audit": fallback_zero_audit,
            "fallback_zero_passed": False,
        },
        "runtime_metrics": {
            "initial_assembly_seconds": 0.0,
            "total_seconds": time.perf_counter() - started,
        },
        "claim_boundary": (
            "HIP-required direct residual Newton probe stopped before MGT parsing, "
            "checkpoint loading, child execution, and CPU residual/tangent assembly "
            "because the ROCm/HIP runtime preflight failed. This receipt is not G1 "
            "closure evidence."
        ),
        "blockers": [
            "rocm_hip_runtime_unavailable",
            "g1_fallback_zero_audit_not_closed",
            "direct_residual_gate_not_closed",
            "relative_increment_gate_not_closed_or_not_verified",
        ],
    }


def _cpu_acceptance_refresh_closure_blocked(component: dict[str, Any]) -> bool:
    return bool(
        component.get("promoted_to_final_state")
        and component.get("require_hip_batch_replay")
        and (
            component.get("accepted_state_refresh_cpu_used")
            or component.get("accepted_state_tangent_refresh_cpu_used")
        )
    )


def _can_use_hip_acceptance_residual_refresh(
    candidate_meta: dict[str, Any],
    *,
    require_hip_batch_replay: bool,
) -> bool:
    return bool(
        require_hip_batch_replay
        and candidate_meta.get("hip_full_residual_batch_replay")
        and candidate_meta.get("residual_only_free_override")
    )


def _row_tangent_refresh_closes_global_defer(row_correction: dict[str, Any]) -> bool:
    backend = str(row_correction.get("accepted_state_tangent_refresh_backend", "") or "")
    return bool(
        row_correction.get("accepted_state_tangent_refresh_hip_used")
        and not row_correction.get("accepted_state_tangent_refresh_cpu_used")
        and not row_correction.get("accepted_state_tangent_refresh_closure_blocked")
        and not row_correction.get("hip_required_tangent_refresh_unavailable_after_promotion")
        and not row_correction.get("frozen_support_graph_after_hip_residual_promotion")
        and not backend.startswith("not_refreshed")
        and not backend.startswith("frozen_")
    )


def _component_tangent_refresh_missing(
    component: dict[str, Any],
    *,
    downstream_hip_tangent_refresh: bool = False,
) -> bool:
    backend = str(component.get("accepted_state_tangent_refresh_backend", "") or "")
    if (
        component.get("accepted_state_tangent_refresh_deferred_to")
        == GLOBAL_TANGENT_REFRESH_DEFERRED_TO_ROW
    ):
        return not downstream_hip_tangent_refresh
    return bool(
        component.get("accepted_state_tangent_refresh_closure_blocked")
        or component.get("hip_required_tangent_refresh_unavailable_after_promotion")
        or component.get("frozen_support_graph_after_hip_residual_promotion")
        or backend.startswith("not_refreshed")
        or backend.startswith("frozen_")
    )


def _g1_fallback_zero_audit(
    global_krylov: dict[str, Any],
    row_correction: dict[str, Any],
) -> dict[str, Any]:
    boundaries: list[dict[str, Any]] = []

    def _hip_required_residual_refresh_missing(component: dict[str, Any]) -> bool:
        if not component.get("promoted_to_final_state"):
            return False
        backend = str(component.get("accepted_state_refresh_backend", "") or "")
        return bool(
            not component.get("accepted_state_refresh_hip_used")
            or backend not in HIP_RESIDUAL_REPLAY_BACKENDS
        )

    def _list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def _per_state_replay_non_hip_trial(component: dict[str, Any]) -> dict[str, Any] | None:
        for pass_index, row_pass in enumerate(_list(component.get("passes"))):
            if not isinstance(row_pass, dict):
                continue
            for trial_index, trial in enumerate(_list(row_pass.get("trial_rows"))):
                if not isinstance(trial, dict):
                    continue
                if trial.get("per_state_batch_replay") and not trial.get(
                    "hip_full_residual_batch_replay"
                ):
                    return {
                        "pass_index": int(pass_index),
                        "trial_index": int(trial_index),
                        "residual_batch_backend": trial.get("residual_batch_backend"),
                    }
        return None

    global_promoted = bool(global_krylov.get("promoted_to_final_state"))
    global_attempted = bool(global_krylov.get("attempted"))
    global_hip_required = bool(
        global_krylov.get("require_hip_batch_replay")
        or global_krylov.get("require_hip_krylov_solver")
    )
    row_promoted = bool(row_correction.get("promoted_to_final_state"))
    row_attempted = bool(row_correction.get("attempted"))
    row_hip_required = bool(row_correction.get("require_hip_batch_replay"))
    row_tangent_refresh_closes_global_defer = (
        _row_tangent_refresh_closes_global_defer(row_correction)
    )

    if (global_promoted or global_attempted) and global_hip_required:
        if global_krylov.get("host_krylov_solver_used"):
            boundaries.append(
                {
                    "boundary": "global_krylov_host_gmres_used_with_hip_required",
                    "path": "matrix_free_global_krylov",
                    "detail": "promoted_or_attempted_hip_required_path_used_host_gmres",
                }
            )
        if global_krylov.get("hip_batch_replay_required_unavailable"):
            boundaries.append(
                {
                    "boundary": "global_krylov_hip_replay_required_unavailable",
                    "path": "matrix_free_global_krylov",
                    "detail": "hip_batch_replay_required_unavailable",
                    "reason": global_krylov.get("hip_batch_replay_required_unavailable_reason"),
                }
            )
        if global_krylov.get("hip_krylov_solver_required_unavailable"):
            boundaries.append(
                {
                    "boundary": "global_krylov_hip_krylov_solver_required_unavailable",
                    "path": "matrix_free_global_krylov",
                    "detail": "hip_krylov_solver_required_unavailable",
                    "reason": global_krylov.get("hip_krylov_solver_required_unavailable_reason"),
                }
            )
        if global_krylov.get("host_krylov_solver_closure_blocked"):
            boundaries.append(
                {
                    "boundary": "global_krylov_host_solver_closure_blocked",
                    "path": "matrix_free_global_krylov",
                    "detail": "host_krylov_solver_closure_blocked",
                }
            )
        if global_krylov.get("cpu_batch_replay_fallback_suppressed"):
            boundaries.append(
                {
                    "boundary": "global_krylov_cpu_batch_replay_fallback_suppressed",
                    "path": "matrix_free_global_krylov",
                    "detail": "cpu_linear_fallback_suppressed",
                }
            )
        if global_krylov.get("accepted_state_refresh_cpu_used"):
            boundaries.append(
                {
                    "boundary": "global_krylov_cpu_residual_acceptance_refresh_used",
                    "path": "matrix_free_global_krylov",
                    "detail": "cpu_residual_acceptance_refresh_used",
                }
            )
        if _hip_required_residual_refresh_missing(global_krylov):
            boundaries.append(
                {
                    "boundary": "global_krylov_hip_required_residual_refresh_missing",
                    "path": "matrix_free_global_krylov",
                    "detail": "hip_required_residual_acceptance_refresh_missing",
                    "backend": global_krylov.get("accepted_state_refresh_backend"),
                }
            )
        if global_krylov.get("accepted_state_tangent_refresh_cpu_used"):
            boundaries.append(
                {
                    "boundary": "global_krylov_cpu_tangent_refresh_used",
                    "path": "matrix_free_global_krylov",
                    "detail": "cpu_tangent_refresh_used",
                }
            )
        if _component_tangent_refresh_missing(
            global_krylov,
            downstream_hip_tangent_refresh=row_tangent_refresh_closes_global_defer,
        ):
            boundaries.append(
                {
                    "boundary": "global_krylov_hip_required_tangent_refresh_missing",
                    "path": "matrix_free_global_krylov",
                    "detail": "hip_required_tangent_refresh_missing",
                    "backend": global_krylov.get("accepted_state_tangent_refresh_backend"),
                    "reason": (
                        global_krylov.get("accepted_state_tangent_refresh_closure_blocker")
                        or global_krylov.get("accepted_state_tangent_refresh_skipped_reason")
                        or global_krylov.get("accepted_state_tangent_refresh_deferred_reason")
                    ),
                    "deferred_to": global_krylov.get(
                        "accepted_state_tangent_refresh_deferred_to"
                    ),
                }
            )

    if (row_promoted or row_attempted) and row_hip_required:
        if row_correction.get("hip_batch_replay_required_unavailable"):
            boundaries.append(
                {
                    "boundary": "row_correction_hip_replay_required_unavailable",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "row_hip_replay_required_unavailable",
                    "reason": row_correction.get("hip_batch_replay_required_unavailable_reason"),
                }
            )
        if row_correction.get("cpu_batch_replay_fallback_suppressed"):
            boundaries.append(
                {
                    "boundary": "row_correction_cpu_batch_replay_fallback_suppressed",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "row_cpu_linear_fallback_suppressed",
                }
            )
        if row_correction.get("accepted_state_refresh_cpu_used"):
            boundaries.append(
                {
                    "boundary": "row_correction_cpu_residual_acceptance_refresh_used",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "row_cpu_residual_acceptance_refresh_used",
                }
            )
        if _hip_required_residual_refresh_missing(row_correction):
            boundaries.append(
                {
                    "boundary": "row_correction_hip_required_residual_refresh_missing",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "row_hip_required_residual_acceptance_refresh_missing",
                    "backend": row_correction.get("accepted_state_refresh_backend"),
                }
            )
        if row_correction.get("accepted_state_tangent_refresh_cpu_used"):
            boundaries.append(
                {
                    "boundary": "row_correction_cpu_tangent_refresh_used",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "row_cpu_tangent_refresh_used",
                }
            )
        if _component_tangent_refresh_missing(row_correction):
            boundaries.append(
                {
                    "boundary": "row_correction_hip_required_tangent_refresh_missing",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "row_hip_required_tangent_refresh_missing",
                    "backend": row_correction.get("accepted_state_tangent_refresh_backend"),
                    "reason": (
                        row_correction.get("accepted_state_tangent_refresh_closure_blocker")
                        or row_correction.get("accepted_state_tangent_refresh_skipped_reason")
                    ),
                }
            )
        non_hip_per_state_trial = _per_state_replay_non_hip_trial(row_correction)
        if non_hip_per_state_trial is not None:
            boundaries.append(
                {
                    "boundary": "row_correction_per_state_replay_non_hip_trial",
                    "path": "current_tangent_residual_row_correction",
                    "detail": "per_state_replay_trial_did_not_use_hip_residual_backend",
                    **non_hip_per_state_trial,
                }
            )

    fallback_zero_passed = not bool(boundaries)
    return {
        "fallback_zero_passed": fallback_zero_passed,
        "fallback_zero_boundary_count": len(boundaries),
        "fallback_zero_boundaries": boundaries,
    }


HIP_RESIDUAL_REPLAY_BACKENDS = {
    "hip_full_residual",
    "hip_full_residual_resident",
    "rust_hip_full_residual_ffi",
}


def _g1_hip_residual_engine_contract(
    global_krylov: dict[str, Any],
    row_correction: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    row_tangent_refresh_closes_global_defer = (
        _row_tangent_refresh_closes_global_defer(row_correction)
    )

    def _component_row(
        name: str,
        component: dict[str, Any],
        *,
        downstream_hip_tangent_refresh: bool = False,
    ) -> None:
        active = bool(
            component.get("enabled")
            or component.get("attempted")
            or component.get("promoted_to_final_state")
        )
        attempted_or_promoted = bool(
            component.get("attempted") or component.get("promoted_to_final_state")
        )
        require_hip = bool(
            component.get("require_hip_batch_replay")
            or component.get("require_hip_krylov_solver")
        )
        backend = str(component.get("batch_replay_backend", "") or "")
        backend_is_hip = backend in HIP_RESIDUAL_REPLAY_BACKENDS
        blockers: list[str] = []
        if not active:
            blockers.append("component_not_active")
        if not require_hip:
            blockers.append("hip_not_required")
        if active and require_hip and not attempted_or_promoted:
            blockers.append("hip_required_component_not_attempted")
        if require_hip and not backend_is_hip:
            blockers.append("residual_replay_backend_not_hip")
        if component.get("host_krylov_solver_used"):
            blockers.append("host_krylov_solver_used")
        if component.get("hip_batch_replay_required_unavailable"):
            blockers.append("hip_batch_replay_required_unavailable")
        if component.get("hip_krylov_solver_required_unavailable"):
            blockers.append("hip_krylov_solver_required_unavailable")
        if component.get("host_krylov_solver_closure_blocked"):
            blockers.append("host_krylov_solver_closure_blocked")
        if component.get("cpu_batch_replay_fallback_suppressed"):
            blockers.append("cpu_batch_replay_fallback_suppressed")
        if component.get("accepted_state_refresh_cpu_used"):
            blockers.append("accepted_state_refresh_cpu_used")
        if component.get("accepted_state_tangent_refresh_cpu_used"):
            blockers.append("accepted_state_tangent_refresh_cpu_used")
        if attempted_or_promoted and require_hip and _component_tangent_refresh_missing(
            component,
            downstream_hip_tangent_refresh=downstream_hip_tangent_refresh,
        ):
            blockers.append("accepted_state_tangent_refresh_not_hip")
        require_hip_krylov = bool(component.get("require_hip_krylov_solver"))
        if require_hip_krylov and not component.get("hip_krylov_solver_used"):
            blockers.append("hip_krylov_solver_not_used")

        row_passed = bool(active and require_hip and backend_is_hip and not blockers)
        rows.append(
            {
                "component": name,
                "active": active,
                "attempted": bool(component.get("attempted")),
                "promoted_to_final_state": bool(
                    component.get("promoted_to_final_state")
                ),
                "require_hip": require_hip,
                "batch_replay_backend": backend,
                "backend_is_hip": backend_is_hip,
                "require_hip_krylov_solver": require_hip_krylov,
                "hip_krylov_solver_used": bool(component.get("hip_krylov_solver_used")),
                "passed": row_passed,
                "blockers": blockers,
            }
        )

    _component_row(
        "matrix_free_global_krylov",
        global_krylov,
        downstream_hip_tangent_refresh=row_tangent_refresh_closes_global_defer,
    )
    _component_row("current_tangent_residual_row_correction", row_correction)

    required_rows = [row for row in rows if row["active"] and row["require_hip"]]
    passed_rows = [row for row in required_rows if row["passed"]]
    blockers = [
        f"{row['component']}::{blocker}"
        for row in required_rows
        for blocker in row["blockers"]
    ]
    return {
        "hip_residual_engine_contract_passed": bool(
            required_rows and len(passed_rows) == len(required_rows) and not blockers
        ),
        "hip_residual_engine_required": bool(required_rows),
        "hip_residual_engine_required_lane_count": len(required_rows),
        "hip_residual_engine_passed_lane_count": len(passed_rows),
        "hip_residual_engine_backends": sorted(
            {str(row["batch_replay_backend"]) for row in required_rows if row["batch_replay_backend"]}
        ),
        "hip_residual_engine_rows": rows,
        "hip_residual_engine_blockers": blockers,
    }


def run_mgt_direct_residual_newton_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = None,
    output_final_checkpoint_npz: Path | None = None,
    compact_output_final_checkpoint: bool = False,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    shell_pressure_load_path_policy: str = "all_components",
    apply_shell_material_tangent: bool = False,
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
    include_residual_component_breakdown: bool = False,
    residual_component_breakdown_top_count: int = 24,
    residual_tolerance_n: float = 5.0e-4,
    relative_increment_tolerance: float = 1.0e-4,
    max_trust_iterations: int = 6,
    directional_jacobian_probe_alpha: float = 0.0000078125,
    enable_secant_subspace_globalization: bool = True,
    max_secant_subspace_promotions: int = 6,
    enable_secant_family_globalization: bool = False,
    max_secant_family_promotions: int = 2,
    secant_family_window_sizes: tuple[int, ...] = (4, 8, 16),
    secant_family_ridge_factors: tuple[float, ...] = (0.0, 1.0e-8),
    secant_family_alpha_values: tuple[float, ...] = (
        0.03125,
        0.015625,
        0.0078125,
        0.00390625,
    ),
    secant_family_min_relative_improvement: float = 1.0e-5,
    enable_matrix_free_jacobian_subspace: bool = True,
    matrix_free_jacobian_subspace_basis_size: int = 2,
    max_matrix_free_jacobian_subspace_promotions: int = 8,
    matrix_free_jacobian_probe_scale: float = 0.25,
    matrix_free_jacobian_probe_scales: tuple[float, ...] | None = None,
    matrix_free_jacobian_difference_scheme: str = "forward",
    matrix_free_jacobian_basis_sources: tuple[str, ...] = ("history",),
    matrix_free_jacobian_probe_max_step: float = 0.0,
    matrix_free_jacobian_ridge_factors: tuple[float, ...] = (0.0,),
    matrix_free_jacobian_allow_negative_alphas: bool = False,
    matrix_free_jacobian_max_alpha: float = 1.0,
    matrix_free_jacobian_min_relative_improvement: float = 1.0e-5,
    enable_matrix_free_global_krylov: bool = False,
    matrix_free_global_krylov_max_iterations: int = 4,
    matrix_free_global_krylov_difference_scheme: str = "forward",
    matrix_free_global_krylov_probe_epsilon: float = 1.0e-6,
    matrix_free_global_krylov_probe_max_step: float = 1.0e-5,
    matrix_free_global_krylov_scaling_mode: str = "none",
    matrix_free_global_krylov_displacement_scale: float = 1.0e-4,
    matrix_free_global_krylov_residual_scale_floor: float = 1.0,
    matrix_free_global_krylov_preconditioner_mode: str = "none",
    matrix_free_global_krylov_preconditioner_input_scale: float = 1.0,
    matrix_free_global_krylov_tangent_regularization_factor: float = 1.0e-8,
    matrix_free_global_krylov_allow_negative_alphas: bool = False,
    matrix_free_global_krylov_max_alpha: float = 1.0,
    matrix_free_global_krylov_alpha_values: tuple[float, ...] = (
        0.03125,
        0.015625,
        0.0078125,
        0.00390625,
    ),
    matrix_free_global_krylov_min_relative_improvement: float = 1.0e-6,
    matrix_free_global_krylov_full_assembly_trial_replay: bool = False,
    matrix_free_global_krylov_batch_replay_backend: str = "cpu",
    matrix_free_global_krylov_require_hip_batch_replay: bool = False,
    matrix_free_global_krylov_linear_solver_backend: str = "scipy_host_gmres",
    enable_current_tangent_residual_row_correction: bool = False,
    max_current_tangent_residual_row_corrections: int = 2,
    current_tangent_residual_row_min_relative_improvement: float = 1.0e-5,
    current_tangent_residual_row_target_counts: tuple[int, ...] = (1, 2),
    current_tangent_residual_row_target_mode: str = "largest_rows",
    current_tangent_residual_row_frontier_probe_json: Path | None = None,
    current_tangent_residual_row_frontier_component_scale_mode: str = "none",
    current_tangent_residual_row_element_neighbor_depth: int = 0,
    current_tangent_residual_row_support_column_counts: tuple[int, ...] = (4, 8),
    current_tangent_residual_row_support_expansion_depth: int = 0,
    current_tangent_residual_row_support_selection: str = "row_strongest",
    current_tangent_residual_row_node_block_support: bool = False,
    current_tangent_residual_row_jacobian_mode: str = "current_tangent",
    current_tangent_residual_row_fd_epsilon: float = 1.0e-6,
    current_tangent_residual_row_fd_max_support_columns: int = 12,
    current_tangent_residual_row_ridge_factor: float = 0.0,
    current_tangent_residual_row_svd_relative_cutoff: float = 0.0,
    current_tangent_residual_row_svd_max_condition: float = 0.0,
    current_tangent_residual_row_directional_probe_alpha: float = 0.0,
    current_tangent_residual_row_shell_normal_participation_threshold: float = 0.7071067811865476,
    current_tangent_residual_row_use_residual_only_assembly: bool = False,
    current_tangent_residual_row_per_state_batch_replay: bool = False,
    current_tangent_residual_row_batch_alpha_replay: bool = False,
    current_tangent_residual_row_batch_fd_replay: bool = False,
    current_tangent_residual_row_batch_fd_replay_chunk_size: int = 64,
    current_tangent_residual_row_batch_replay_backend: str = "cpu",
    current_tangent_residual_row_require_hip_batch_replay: bool = False,
    current_tangent_residual_row_hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    current_tangent_residual_row_force_rebuild_hip: bool = False,
    current_tangent_residual_row_allow_negative_alphas: bool = False,
    current_tangent_residual_row_alpha_values: tuple[float, ...] = (
        0.03125,
        0.015625,
    ),
    matrix_free_jacobian_alpha_values: tuple[float, ...] = (
        0.03125,
        0.015625,
        0.0078125,
        0.00390625,
    ),
    alpha_values: tuple[float, ...] = (
        0.001,
        0.0005,
        0.00025,
        0.000125,
        0.0000625,
        0.00003125,
        0.000015625,
        0.0000078125,
    ),
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    global_batch_backend = _normalize_residual_batch_replay_backend(
        matrix_free_global_krylov_batch_replay_backend
    )
    global_linear_solver_backend = _normalize_global_krylov_linear_solver_backend(
        matrix_free_global_krylov_linear_solver_backend
    )
    global_require_hip_batch_replay = bool(
        matrix_free_global_krylov_require_hip_batch_replay
        and global_batch_backend in HIP_RESIDUAL_BATCH_REPLAY_BACKENDS
    )
    global_linear_solver_auto_reason: str | None = None
    if (
        global_require_hip_batch_replay
        and global_linear_solver_backend == "scipy_host_gmres"
    ):
        global_linear_solver_backend = "torch_hip_gmres"
        global_linear_solver_auto_reason = "hip_batch_replay_required_suppresses_host_gmres"
    row_batch_backend = _normalize_residual_batch_replay_backend(
        current_tangent_residual_row_batch_replay_backend
    )
    row_require_hip_batch_replay = bool(
        current_tangent_residual_row_require_hip_batch_replay
        and row_batch_backend in HIP_RESIDUAL_BATCH_REPLAY_BACKENDS
    )
    row_hip_fd_tangent_refresh_configured = bool(
        enable_current_tangent_residual_row_correction
        and row_require_hip_batch_replay
        and row_batch_backend in HIP_RESIDUAL_BATCH_REPLAY_BACKENDS
        and str(current_tangent_residual_row_jacobian_mode).strip()
        == "finite_difference"
        and str(current_tangent_residual_row_support_selection).strip()
        == "target_rows"
        and current_tangent_residual_row_use_residual_only_assembly
        and current_tangent_residual_row_batch_fd_replay
    )
    if (
        matrix_free_global_krylov_require_hip_batch_replay
        and global_batch_backend == "cpu"
    ):
        raise ValueError(
            "matrix_free_global_krylov_require_hip_batch_replay is True "
            "but the matrix_free_global_krylov_batch_replay_backend "
            "normalized to 'cpu'. HIP-required residual paths must use "
            "a HIP batch replay backend ("
            + ", ".join(sorted(HIP_RESIDUAL_BATCH_REPLAY_BACKENDS))
            + ")."
        )
    if (
        current_tangent_residual_row_require_hip_batch_replay
        and row_batch_backend == "cpu"
    ):
        raise ValueError(
            "current_tangent_residual_row_require_hip_batch_replay is True "
            "but the current_tangent_residual_row_batch_replay_backend "
            "normalized to 'cpu'. HIP-required residual paths must use "
            "a HIP batch replay backend ("
            + ", ".join(sorted(HIP_RESIDUAL_BATCH_REPLAY_BACKENDS))
            + ")."
        )
    hip_runtime_required = bool(
        (
            enable_matrix_free_global_krylov
            and (
                global_require_hip_batch_replay
                or global_linear_solver_backend == "torch_hip_gmres"
            )
        )
        or (
            enable_current_tangent_residual_row_correction
            and row_require_hip_batch_replay
        )
    )
    if hip_runtime_required:
        hip_preflight = _rocm_hip_runtime_preflight()
        if not bool(hip_preflight.get("hip_available")):
            payload = _hip_runtime_unavailable_direct_probe_payload(
                generated_at=generated_at,
                started=started,
                mgt_path=mgt_path,
                checkpoint_npz=checkpoint_npz,
                enable_matrix_free_global_krylov=enable_matrix_free_global_krylov,
                global_batch_backend=global_batch_backend,
                global_require_hip_batch_replay=global_require_hip_batch_replay,
                global_linear_solver_backend=global_linear_solver_backend,
                global_linear_solver_auto_reason=global_linear_solver_auto_reason,
                enable_current_tangent_residual_row_correction=(
                    enable_current_tangent_residual_row_correction
                ),
                row_batch_backend=row_batch_backend,
                row_require_hip_batch_replay=row_require_hip_batch_replay,
                hip_preflight=hip_preflight,
            )
            if output_json is not None:
                output_json.parent.mkdir(parents=True, exist_ok=True)
                output_json.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            return payload
    if not mgt_path.is_file():
        return {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "status": "blocked", "blockers": ["mgt_missing"]}
    if not checkpoint_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["checkpoint_missing"],
        }

    checkpoint_meta, u0, checkpoint_state_history, checkpoint_residual_history = _load_checkpoint(
        checkpoint_npz
    )
    load_scale = float(checkpoint_meta["load_scale"])
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    props = load_mgt_section_material_properties(mgt_path)
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    plate_thickness_props = props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

    with tempfile.TemporaryDirectory(prefix="mgt-direct-residual-newton-") as temp_dir:
        _roundtrip_json, roundtrip_npz, parser_report, parser_run = _run_uncoarsened_parser(
            mgt_path=mgt_path,
            work_dir=Path(temp_dir),
        )
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
        (
            pressure_allowed_surface_elements,
            pressure_load_path_meta,
        ) = surface_pressure_load_path_filter(
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            restrained=restrained,
            policy=shell_pressure_load_path_policy,
        )
        base_axial_forces = _component_gravity_axial_forces(
            elements=frame_elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
        )
        shell_operator_cache: dict[str, Any] = {}
        frame_force_axial_forces = {
            int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
            for elem_id, force in base_axial_forces.items()
        }
        frame_force_cache = prepack_frame_force_based_assembly(
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=material_props,
            element_axial_forces=frame_force_axial_forces,
            include_geometric=True,
        )

        def assemble_residual(
            u: np.ndarray,
            *,
            external_load_override: np.ndarray | None = None,
            include_component_forces: bool = False,
            residual_only: bool = False,
            free_override: np.ndarray | None = None,
        ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
            if (
                residual_only
                and external_load_override is not None
                and free_override is not None
            ):
                f_int, physical_meta = assemble_physical_internal_forces(
                    u=u,
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
                    apply_shell_material_tangent=apply_shell_material_tangent,
                    include_component_forces=include_component_forces,
                    shell_operator_cache=shell_operator_cache,
                    frame_force_cache=frame_force_cache,
                )
                f_ext = np.asarray(external_load_override, dtype=np.float64)
                free = np.asarray(free_override, dtype=np.int64)
                residual, rhs = assemble_physical_residual(
                    u=u,
                    f_ext=f_ext,
                    free=free,
                    f_int=f_int,
                )
                return None, f_ext, free, residual, rhs, {
                    **physical_meta,
                    "residual_only_assembly": True,
                    "residual_only_free_override": True,
                    "free_dof_count": int(free.size),
                    "shell_operator_cache_size": int(len(shell_operator_cache)),
                    "shell_pressure_load_path_meta": pressure_load_path_meta,
                    "physical_internal_force_inf_n": float(np.max(np.abs(f_int[free])))
                    if free.size
                    else 0.0,
                    "external_load_source": "reference_configuration",
                    "assembled_external_load_inf_n": None,
                    "used_external_load_inf_n": float(np.max(np.abs(f_ext))) if f_ext.size else 0.0,
                }
            translations = np.asarray(u, dtype=np.float64).reshape((-1, DOF_PER_NODE))[:, :3]
            deformed_xyz = node_xyz + translations
            service_tangent_by_element, service_material_meta = _service_tangent_by_element(
                elements=frame_elements,
                node_xyz=deformed_xyz,
                u=u,
                material_props=material_props,
            )
            service_shell_tangent_by_surface_index = None
            service_shell_material_meta: dict[str, Any] | None = None
            if apply_shell_material_tangent:
                (
                    service_shell_tangent_by_surface_index,
                    service_shell_material_meta,
                ) = shell_material_tangent_by_surface_index(
                    node_xyz=node_xyz,
                    u=u,
                    elem_type_code=elem_type_code,
                    elem_material_id=elem_material_id,
                    conn_ptr=conn_ptr,
                    conn_idx=conn_idx,
                    material_props=material_props,
                    controlled_probe=False,
                )
                service_shell_material_meta = {
                    **service_shell_material_meta,
                    "shell_material_tangent_applied": True,
                }
            stiffness, assembled_f_ext, tangent_meta = assemble_newton_tangent_stiffness(
                u=u,
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
                service_tangent_by_element=service_tangent_by_element,
                service_material_meta=service_material_meta,
                service_shell_tangent_by_surface_index_mpa=(
                    service_shell_tangent_by_surface_index
                ),
                service_shell_material_meta=service_shell_material_meta,
                shell_pressure_load_allowed_surface_elements=pressure_allowed_surface_elements,
            )
            f_int, physical_meta = assemble_physical_internal_forces(
                u=u,
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
                apply_shell_material_tangent=apply_shell_material_tangent,
                include_component_forces=include_component_forces,
                shell_operator_cache=shell_operator_cache,
                frame_force_cache=frame_force_cache,
            )
            f_ext = (
                np.asarray(external_load_override, dtype=np.float64)
                if external_load_override is not None
                else assembled_f_ext
            )
            active, free = _active_free(stiffness, restrained)
            residual, rhs = assemble_physical_residual(
                u=u,
                f_ext=f_ext,
                free=free,
                f_int=f_int,
            )
            quasi_residual = np.asarray(stiffness[free, :] @ u - f_ext[free], dtype=np.float64)
            return stiffness, f_ext, free, residual, rhs, {
                "active_dof_count": int(active.size),
                "free_dof_count": int(free.size),
                **tangent_meta,
                **physical_meta,
                "physical_internal_force_inf_n": float(np.max(np.abs(f_int[free])))
                if free.size
                else 0.0,
                "quasi_tangent_residual_inf_n": float(np.max(np.abs(quasi_residual)))
                if quasi_residual.size
                else 0.0,
                "external_load_source": "reference_configuration"
                if external_load_override is not None
                else "assembled_configuration",
                "assembled_external_load_inf_n": float(np.max(np.abs(assembled_f_ext)))
                if assembled_f_ext.size
                else 0.0,
                "used_external_load_inf_n": float(np.max(np.abs(f_ext))) if f_ext.size else 0.0,
                "residual_only_assembly": False,
                "shell_pressure_load_path_meta": pressure_load_path_meta,
                "shell_operator_cache_size": int(len(shell_operator_cache)),
            }
        assemble_residual.supports_residual_only = True  # type: ignore[attr-defined]

        assembly_started = time.perf_counter()
        (
            _reference_stiffness,
            reference_f_ext,
            _reference_free,
            _reference_residual,
            _reference_rhs,
            reference_meta,
        ) = assemble_residual(np.zeros_like(u0))
        stiffness, f_ext, free, residual, rhs, assembly_meta = assemble_residual(
            u0,
            external_load_override=reference_f_ext,
            include_component_forces=bool(include_residual_component_breakdown),
        )
        base_component_breakdown: dict[str, Any] | None = None
        if include_residual_component_breakdown:
            component_forces = assembly_meta.pop("component_forces", {})
            base_component_breakdown = _component_breakdown(
                component_forces=(
                    component_forces if isinstance(component_forces, dict) else {}
                ),
                free=np.asarray(free, dtype=np.int64),
                residual=np.asarray(residual, dtype=np.float64),
                rhs=np.asarray(rhs, dtype=np.float64),
                top_count=int(residual_component_breakdown_top_count),
            )
        base_residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        base_residual_l2 = float(np.linalg.norm(residual)) if residual.size else 0.0
        rhs_inf = float(np.max(np.abs(rhs))) if rhs.size else 0.0
        assembly_seconds = time.perf_counter() - assembly_started

        base_k_ff = stiffness[free, :][:, free].tocsc()
        base_diag = np.asarray(base_k_ff.diagonal(), dtype=np.float64)
        base_regularization = 1.0e-8 * max(float(np.mean(np.abs(base_diag))), 1.0)
        regularized_residual = np.asarray(
            (base_k_ff + eye(base_k_ff.shape[0], format="csc") * base_regularization) @ u0[free]
            - rhs
        )
        current_u = np.asarray(u0, dtype=np.float64).copy()
        current_stiffness = stiffness
        current_free = free
        current_residual = residual
        current_rhs = rhs
        loaded_state_history: list[np.ndarray] = []
        if (
            checkpoint_state_history is not None
            and checkpoint_state_history.ndim == 2
            and checkpoint_state_history.shape[1] == current_u.size
        ):
            loaded_state_history = [
                np.asarray(row, dtype=np.float64).copy() for row in checkpoint_state_history
            ]
        if not loaded_state_history or not np.allclose(loaded_state_history[-1], current_u):
            loaded_state_history.append(np.asarray(current_u, dtype=np.float64).copy())

        loaded_residual_history: list[np.ndarray] = []
        if (
            checkpoint_residual_history is not None
            and checkpoint_residual_history.ndim == 2
            and checkpoint_residual_history.shape[1] == current_residual.size
            and checkpoint_residual_history.shape[0] == len(loaded_state_history)
        ):
            loaded_residual_history = [
                np.asarray(row, dtype=np.float64).copy() for row in checkpoint_residual_history
            ]
        if len(loaded_residual_history) != len(loaded_state_history):
            loaded_state_history = [np.asarray(current_u, dtype=np.float64).copy()]
            loaded_residual_history = [np.asarray(current_residual, dtype=np.float64).copy()]
        else:
            loaded_residual_history[-1] = np.asarray(current_residual, dtype=np.float64).copy()

        accepted_state_history = loaded_state_history
        accepted_residual_history = loaded_residual_history
        trust_iterations: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []
        accepted_count = 0
        last_regularization = 0.0
        last_solve_seconds = 0.0
        last_correction_inf = 0.0
        for iteration in range(1, max(int(max_trust_iterations), 0) + 1):
            start_residual_inf = (
                float(np.max(np.abs(current_residual))) if current_residual.size else 0.0
            )
            k_ff = current_stiffness[current_free, :][:, current_free].tocsc()
            diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
            regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
            solve_started = time.perf_counter()
            correction_free = np.asarray(
                spsolve(k_ff + eye(k_ff.shape[0], format="csc") * regularization, -current_residual),
                dtype=np.float64,
            )
            solve_seconds = time.perf_counter() - solve_started
            correction = np.zeros_like(current_u)
            correction[current_free] = correction_free
            last_regularization = float(regularization)
            last_solve_seconds = float(solve_seconds)
            last_correction_inf = (
                float(np.max(np.abs(correction_free))) if correction_free.size else 0.0
            )
            current_max_abs = max(
                float(np.max(np.abs(current_u))) if current_u.size else 0.0,
                1.0e-9,
            )
            gate_limited_alpha = (
                0.95
                * float(relative_increment_tolerance)
                * current_max_abs
                / last_correction_inf
                if last_correction_inf > 0.0
                else 0.0
            )
            min_alpha = min(float(value) for value in alpha_values) if alpha_values else 0.0
            max_alpha = max(float(value) for value in alpha_values) if alpha_values else 0.0
            directional_jacobian_meta: dict[str, Any] = {
                "enabled": False,
                "probe_alpha": float(directional_jacobian_probe_alpha),
                "candidate_alphas": [],
            }
            dynamic_alphas: list[tuple[str, float]] = []
            if (
                directional_jacobian_probe_alpha > 0.0
                and current_residual.size
                and min_alpha > 0.0
                and max_alpha > 0.0
            ):
                probe_u = current_u + float(directional_jacobian_probe_alpha) * correction
                _probe_k, _probe_f, probe_free, probe_residual, _probe_rhs, _probe_meta = assemble_residual(
                    probe_u,
                    external_load_override=reference_f_ext,
                )
                free_is_stable = bool(
                    probe_free.shape == current_free.shape
                    and np.array_equal(probe_free, current_free)
                )
                directional_jacobian_meta["enabled"] = True
                directional_jacobian_meta["free_dof_set_stable"] = free_is_stable
                directional_jacobian_meta["probe_direct_residual_inf_n"] = (
                    float(np.max(np.abs(probe_residual))) if probe_residual.size else 0.0
                )
                if free_is_stable:
                    jacobian_action = (probe_residual - current_residual) / float(
                        directional_jacobian_probe_alpha
                    )
                    denom = float(np.dot(jacobian_action, jacobian_action))
                    directional_jacobian_meta["jacobian_action_inf_n"] = (
                        float(np.max(np.abs(jacobian_action))) if jacobian_action.size else 0.0
                    )
                    directional_jacobian_meta["jacobian_action_l2_n"] = (
                        float(np.linalg.norm(jacobian_action)) if jacobian_action.size else 0.0
                    )
                    if denom > 0.0:
                        dynamic_alphas.append(
                            (
                                "directional_residual_jacobian_l2",
                                -float(np.dot(current_residual, jacobian_action)) / denom,
                            )
                        )
                    row_count = min(32, int(current_residual.size))
                    if row_count:
                        top = np.argpartition(np.abs(current_residual), -row_count)[-row_count:]
                        ratios = [
                            -float(current_residual[idx]) / float(jacobian_action[idx])
                            for idx in top.tolist()
                            if abs(float(jacobian_action[idx])) > 1.0e-30
                        ]
                        positive = [value for value in ratios if np.isfinite(value) and value > 0.0]
                        if positive:
                            dynamic_alphas.append(
                                (
                                    "directional_residual_jacobian_top_row_median",
                                    float(np.median(positive)),
                                )
                            )
                            dynamic_alphas.append(
                                (
                                    "directional_residual_jacobian_top_row_min",
                                    float(min(positive)),
                                )
                            )
                else:
                    directional_jacobian_meta["reason"] = "free_dof_set_changed"
            iteration_alpha_rows = _unique_positive_alphas(
                [("configured_trust_region", float(value)) for value in alpha_values]
                + [
                    ("trust_region_gate_limited", gate_limited_alpha),
                    ("trust_region_half_gate_limited", 0.5 * gate_limited_alpha),
                ]
                + dynamic_alphas,
                min_alpha=min(min_alpha, gate_limited_alpha, 0.5 * gate_limited_alpha)
                if gate_limited_alpha > 0.0
                else min_alpha,
                max_alpha=max_alpha,
            )
            directional_jacobian_meta["candidate_alphas"] = [
                {"source": source, "alpha": float(alpha)} for source, alpha in iteration_alpha_rows
            ]
            iteration_rows: list[dict[str, Any]] = []
            candidate_vectors: list[np.ndarray] = []
            for alpha_source, alpha in iteration_alpha_rows:
                candidate_u = current_u + float(alpha) * correction
                _k, _f, candidate_free, candidate_residual, candidate_rhs, _meta = assemble_residual(
                    candidate_u,
                    external_load_override=reference_f_ext,
                )
                residual_inf = (
                    float(np.max(np.abs(candidate_residual))) if candidate_residual.size else 0.0
                )
                increment = float(np.max(np.abs(candidate_u - current_u))) if candidate_u.size else 0.0
                max_abs = max(float(np.max(np.abs(candidate_u))) if candidate_u.size else 0.0, 1.0e-9)
                metrics = _translation_metrics(candidate_u, node_xyz)
                free_is_stable = bool(
                    candidate_free.shape == current_free.shape
                    and np.array_equal(candidate_free, current_free)
                )
                row = {
                    "iteration": int(iteration),
                    "alpha_source": alpha_source,
                    "alpha": float(alpha),
                    "direct_residual_inf_n": residual_inf,
                    "direct_relative_residual_inf": residual_inf
                    / max(float(np.max(np.abs(candidate_rhs))) if candidate_rhs.size else 0.0, 1.0),
                    "relative_increment": increment / max_abs,
                    "max_increment_m": increment,
                    "max_translation_m": metrics["max_translation_m"],
                    "residual_gate_passed": bool(residual_inf <= residual_tolerance_n),
                    "relative_increment_gate_passed": bool(increment / max_abs <= relative_increment_tolerance),
                    "free_dof_set_stable": free_is_stable,
                }
                iteration_rows.append(row)
                candidate_rows.append(row)
                candidate_vectors.append(candidate_u)
            best_index, best_row = min(
                enumerate(iteration_rows),
                key=lambda item: float(item[1]["direct_residual_inf_n"]),
            )
            gate_eligible_rows = [
                (index, row)
                for index, row in enumerate(iteration_rows)
                if bool(row.get("relative_increment_gate_passed"))
                and bool(row.get("free_dof_set_stable", True))
            ]
            best_gate_index, best_gate_row = min(
                gate_eligible_rows,
                key=lambda item: float(item[1]["direct_residual_inf_n"]),
                default=(None, None),
            )
            accepted = bool(
                best_gate_row is not None
                and float(best_gate_row["direct_residual_inf_n"]) < start_residual_inf
            )
            trust_iterations.append(
                {
                    "iteration": int(iteration),
                    "start_direct_residual_inf_n": start_residual_inf,
                    "regularization": float(regularization),
                    "correction_inf_m": last_correction_inf,
                    "gate_limited_alpha": float(gate_limited_alpha),
                    "linear_solve_seconds": float(solve_seconds),
                    "directional_residual_jacobian": directional_jacobian_meta,
                    "candidate_rows": iteration_rows,
                    "best_candidate": best_row,
                    "best_gate_eligible_candidate": best_gate_row,
                    "accepted": accepted,
                }
            )
            if not accepted:
                break
            accepted_count += 1
            current_u = candidate_vectors[int(best_gate_index)]
            (
                current_stiffness,
                _current_f_ext,
                current_free,
                current_residual,
                current_rhs,
                _current_meta,
            ) = assemble_residual(current_u, external_load_override=reference_f_ext)
            current_residual_inf = (
                float(np.max(np.abs(current_residual))) if current_residual.size else 0.0
            )
            accepted_state_history.append(np.asarray(current_u, dtype=np.float64).copy())
            accepted_residual_history.append(np.asarray(current_residual, dtype=np.float64).copy())
            if current_residual_inf <= residual_tolerance_n and best_gate_row is not None:
                break

        secant_subspace_globalization: dict[str, Any] = {
            "enabled": bool(enable_secant_subspace_globalization),
            "attempted": False,
            "accepted": False,
            "promotion_count": 0,
            "passes": [],
        }
        if (
            enable_secant_subspace_globalization
            and len(accepted_state_history) >= 3
            and current_residual.size
        ):
            all_trial_rows: list[dict[str, Any]] = []
            all_gate_candidates: list[dict[str, Any]] = []
            pass_rows: list[dict[str, Any]] = []
            promotion_count = 0
            for secant_pass in range(1, max(int(max_secant_subspace_promotions), 0) + 1):
                if len(accepted_state_history) < 3 or not current_residual.size:
                    break
                secant_subspace_globalization["attempted"] = True
                delta_u_columns = [
                    accepted_state_history[index + 1] - accepted_state_history[index]
                    for index in range(len(accepted_state_history) - 1)
                ]
                delta_r_columns = [
                    accepted_residual_history[index + 1] - accepted_residual_history[index]
                    for index in range(len(accepted_residual_history) - 1)
                ]
                delta_r = np.column_stack(delta_r_columns)
                secant_started = time.perf_counter()
                coeffs, residual_sum, rank, singular_values = np.linalg.lstsq(
                    delta_r,
                    -current_residual,
                    rcond=None,
                )
                solve_seconds = time.perf_counter() - secant_started
                candidate_delta_u = np.zeros_like(current_u)
                for coeff, delta_u in zip(coeffs.tolist(), delta_u_columns):
                    candidate_delta_u += float(coeff) * delta_u
                candidate_delta_inf = (
                    float(np.max(np.abs(candidate_delta_u))) if candidate_delta_u.size else 0.0
                )
                current_max_abs = max(
                    float(np.max(np.abs(current_u))) if current_u.size else 0.0,
                    1.0e-9,
                )
                gate_limited_alpha = (
                    0.95 * float(relative_increment_tolerance) * current_max_abs / candidate_delta_inf
                    if candidate_delta_inf > 0.0
                    else 0.0
                )
                raw_secant_alphas = [
                    1.0,
                    0.5,
                    0.25,
                    0.125,
                    0.0625,
                    0.03125,
                    0.015625,
                    0.0078125,
                    0.00390625,
                    gate_limited_alpha,
                    0.5 * gate_limited_alpha,
                ]
                secant_alphas = [
                    alpha
                    for _source, alpha in _unique_positive_alphas(
                        [("secant", alpha) for alpha in raw_secant_alphas],
                        min_alpha=1.0e-8,
                        max_alpha=1.0,
                    )
                ]
                trial_rows: list[dict[str, Any]] = []
                trial_vectors: list[np.ndarray] = []
                previous_residual_inf = (
                    float(np.max(np.abs(current_residual)))
                    if current_residual.size
                    else base_residual_inf
                )
                for alpha in secant_alphas:
                    candidate_u = current_u + float(alpha) * candidate_delta_u
                    _k, _f, _free, candidate_residual, candidate_rhs, _meta = assemble_residual(
                        candidate_u,
                        external_load_override=reference_f_ext,
                    )
                    residual_inf = (
                        float(np.max(np.abs(candidate_residual)))
                        if candidate_residual.size
                        else 0.0
                    )
                    increment = (
                        float(np.max(np.abs(candidate_u - current_u)))
                        if candidate_u.size
                        else 0.0
                    )
                    max_abs = max(
                        float(np.max(np.abs(candidate_u))) if candidate_u.size else current_max_abs,
                        1.0e-9,
                    )
                    metrics = _translation_metrics(candidate_u, node_xyz)
                    row = {
                        "secant_pass": int(secant_pass),
                        "alpha": float(alpha),
                        "direct_residual_inf_n": residual_inf,
                        "direct_relative_residual_inf": residual_inf
                        / max(float(np.max(np.abs(candidate_rhs))) if candidate_rhs.size else 0.0, 1.0),
                        "relative_increment": increment / max_abs,
                        "max_increment_m": increment,
                        "max_translation_m": metrics["max_translation_m"],
                        "residual_gate_passed": bool(residual_inf <= residual_tolerance_n),
                        "relative_increment_gate_passed": bool(
                            increment / max_abs <= relative_increment_tolerance
                        ),
                    }
                    trial_rows.append(row)
                    trial_vectors.append(candidate_u)
                best_trial_index, best_trial = min(
                    enumerate(trial_rows),
                    key=lambda item: float(item[1]["direct_residual_inf_n"]),
                )
                gate_eligible_trials = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                ]
                best_gate_trial_index: int | None = None
                best_gate_trial: dict[str, Any] | None = None
                if gate_eligible_trials:
                    best_gate_trial_index, best_gate_trial = min(
                        gate_eligible_trials,
                        key=lambda item: float(item[1]["direct_residual_inf_n"]),
                    )
                    all_gate_candidates.append(best_gate_trial)
                residual_descent_secant = bool(
                    float(best_trial["direct_residual_inf_n"]) < previous_residual_inf
                )
                promoted_secant = best_gate_trial is not None
                pass_payload = {
                    "secant_pass": int(secant_pass),
                    "residual_descent": residual_descent_secant,
                    "promoted_to_final_state": promoted_secant,
                    "history_state_count": int(len(accepted_state_history)),
                    "subspace_dimension": int(delta_r.shape[1]),
                    "rank": int(rank),
                    "singular_values": [float(value) for value in singular_values.tolist()],
                    "coefficient_l2": float(np.linalg.norm(coeffs)),
                    "coefficient_linf": float(np.max(np.abs(coeffs))) if coeffs.size else 0.0,
                    "candidate_delta_inf_m": candidate_delta_inf,
                    "gate_limited_alpha": float(gate_limited_alpha),
                    "secant_alpha_values": [float(alpha) for alpha in secant_alphas],
                    "linear_least_squares_residual_sum": [
                        float(value) for value in np.ravel(residual_sum).tolist()
                    ],
                    "linear_solve_seconds": float(solve_seconds),
                    "previous_direct_residual_inf_n": previous_residual_inf,
                    "trial_rows": trial_rows,
                    "best_candidate": best_trial,
                    "best_gate_eligible_candidate": best_gate_trial,
                }
                pass_rows.append(pass_payload)
                all_trial_rows.extend(trial_rows)
                if not promoted_secant:
                    break
                assert best_gate_trial_index is not None
                promotion_count += 1
                current_u = trial_vectors[best_gate_trial_index]
                (
                    current_stiffness,
                    _current_f_ext,
                    current_free,
                    current_residual,
                    current_rhs,
                    _current_meta,
                ) = assemble_residual(current_u, external_load_override=reference_f_ext)
                accepted_state_history.append(np.asarray(current_u, dtype=np.float64).copy())
                accepted_residual_history.append(np.asarray(current_residual, dtype=np.float64).copy())
            best_candidate_secant = (
                min(all_trial_rows, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_trial_rows
                else None
            )
            best_gate_candidate_secant = (
                min(all_gate_candidates, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_gate_candidates
                else None
            )
            secant_subspace_globalization.update(
                {
                    "accepted": bool(promotion_count),
                    "residual_descent": bool(
                        best_candidate_secant
                        and float(best_candidate_secant["direct_residual_inf_n"])
                        < base_residual_inf
                    ),
                    "promoted_to_final_state": bool(promotion_count),
                    "promotion_count": int(promotion_count),
                    "max_promotions": int(max_secant_subspace_promotions),
                    "passes": pass_rows,
                    "trial_rows": all_trial_rows,
                    "best_candidate": best_candidate_secant,
                    "best_gate_eligible_candidate": best_gate_candidate_secant,
                }
            )

        secant_family_globalization: dict[str, Any] = {
            "enabled": bool(enable_secant_family_globalization),
            "attempted": False,
            "accepted": False,
            "promoted_to_final_state": False,
            "promotion_count": 0,
            "max_promotions": int(max_secant_family_promotions),
            "window_sizes": [
                int(value) for value in secant_family_window_sizes if int(value) > 0
            ],
            "ridge_factors": [
                float(value) for value in secant_family_ridge_factors if float(value) >= 0.0
            ],
            "alpha_values": [
                float(value) for value in secant_family_alpha_values if float(value) > 0.0
            ],
            "minimum_relative_improvement": float(
                max(secant_family_min_relative_improvement, 0.0)
            ),
            "stop_reason": "not_attempted",
            "passes": [],
            "trial_rows": [],
        }
        if (
            enable_secant_family_globalization
            and len(accepted_state_history) >= 3
            and current_residual.size
        ):
            pass_rows: list[dict[str, Any]] = []
            all_trial_rows: list[dict[str, Any]] = []
            all_gate_candidates: list[dict[str, Any]] = []
            promotion_count = 0
            max_family_promotions = max(int(max_secant_family_promotions), 0)
            min_family_relative_improvement = max(
                float(secant_family_min_relative_improvement), 0.0
            )
            family_window_sizes = tuple(
                sorted({int(value) for value in secant_family_window_sizes if int(value) > 0})
            )
            family_ridge_factors = tuple(
                sorted({float(value) for value in secant_family_ridge_factors if float(value) >= 0.0})
            )
            family_alpha_values = tuple(
                float(value) for value in secant_family_alpha_values if float(value) > 0.0
            )
            for family_pass in range(1, max_family_promotions + 1):
                if len(accepted_state_history) < 3 or not current_residual.size:
                    break
                previous_residual_inf = (
                    float(np.max(np.abs(current_residual))) if current_residual.size else 0.0
                )
                secant_family_globalization["attempted"] = True
                delta_u_columns = [
                    accepted_state_history[index + 1] - accepted_state_history[index]
                    for index in range(len(accepted_state_history) - 1)
                ]
                delta_r_columns = [
                    accepted_residual_history[index + 1] - accepted_residual_history[index]
                    for index in range(len(accepted_residual_history) - 1)
                ]
                available_columns = min(len(delta_u_columns), len(delta_r_columns))
                pass_payload: dict[str, Any] = {
                    "secant_family_pass": int(family_pass),
                    "previous_direct_residual_inf_n": previous_residual_inf,
                    "history_state_count": int(len(accepted_state_history)),
                    "available_secant_columns": int(available_columns),
                }
                trial_rows: list[dict[str, Any]] = []
                trial_vectors: list[np.ndarray] = []
                family_candidate_rows: list[dict[str, Any]] = []
                current_max_abs = max(
                    float(np.max(np.abs(current_u))) if current_u.size else 0.0,
                    1.0e-9,
                )
                for raw_window_size in family_window_sizes:
                    window_size = min(int(raw_window_size), int(available_columns))
                    if window_size <= 0:
                        continue
                    window_delta_u = delta_u_columns[-window_size:]
                    window_delta_r = delta_r_columns[-window_size:]
                    delta_r = np.column_stack(window_delta_r)
                    for ridge_factor in family_ridge_factors:
                        solve_started = time.perf_counter()
                        solve_matrix = delta_r
                        solve_rhs = -current_residual
                        ridge_lambda = 0.0
                        if ridge_factor > 0.0:
                            singular_probe = np.linalg.svd(delta_r, compute_uv=False)
                            spectral_scale = (
                                float(np.max(singular_probe))
                                if singular_probe.size
                                else float(np.linalg.norm(delta_r))
                            )
                            ridge_lambda = float(ridge_factor) * max(spectral_scale, 1.0)
                            if ridge_lambda > 0.0:
                                solve_matrix = np.vstack(
                                    [
                                        delta_r,
                                        np.eye(window_size, dtype=np.float64) * ridge_lambda,
                                    ]
                                )
                                solve_rhs = np.concatenate(
                                    [
                                        -current_residual,
                                        np.zeros(window_size, dtype=np.float64),
                                    ]
                                )
                        coeffs, residual_sum, rank, singular_values = np.linalg.lstsq(
                            solve_matrix,
                            solve_rhs,
                            rcond=None,
                        )
                        solve_seconds = time.perf_counter() - solve_started
                        candidate_delta_u = np.zeros_like(current_u)
                        for coeff, delta_u in zip(coeffs.tolist(), window_delta_u):
                            candidate_delta_u += float(coeff) * delta_u
                        candidate_delta_inf = (
                            float(np.max(np.abs(candidate_delta_u)))
                            if candidate_delta_u.size
                            else 0.0
                        )
                        gate_limited_alpha = (
                            0.95
                            * float(relative_increment_tolerance)
                            * current_max_abs
                            / candidate_delta_inf
                            if candidate_delta_inf > 0.0
                            else 0.0
                        )
                        family_alphas = [
                            alpha
                            for _source, alpha in _unique_positive_alphas(
                                [
                                    ("secant_family", alpha)
                                    for alpha in family_alpha_values
                                ]
                                + [
                                    ("secant_family_gate_limited", gate_limited_alpha),
                                    (
                                        "secant_family_half_gate_limited",
                                        0.5 * gate_limited_alpha,
                                    ),
                                    (
                                        "secant_family_quarter_gate_limited",
                                        0.25 * gate_limited_alpha,
                                    ),
                                ],
                                min_alpha=1.0e-8,
                                max_alpha=1.0,
                            )
                        ]
                        candidate_start_index = len(trial_rows)
                        for alpha in family_alphas:
                            candidate_u = current_u + float(alpha) * candidate_delta_u
                            (
                                _k,
                                _f,
                                _free,
                                candidate_residual,
                                candidate_rhs,
                                _meta,
                            ) = assemble_residual(
                                candidate_u,
                                external_load_override=reference_f_ext,
                            )
                            residual_inf = (
                                float(np.max(np.abs(candidate_residual)))
                                if candidate_residual.size
                                else 0.0
                            )
                            improvement_inf = previous_residual_inf - residual_inf
                            relative_improvement = improvement_inf / max(
                                previous_residual_inf,
                                1.0e-30,
                            )
                            increment = (
                                float(np.max(np.abs(candidate_u - current_u)))
                                if candidate_u.size
                                else 0.0
                            )
                            max_abs = max(
                                float(np.max(np.abs(candidate_u)))
                                if candidate_u.size
                                else current_max_abs,
                                1.0e-9,
                            )
                            metrics = _translation_metrics(candidate_u, node_xyz)
                            row = {
                                "secant_family_pass": int(family_pass),
                                "window_size": int(window_size),
                                "requested_window_size": int(raw_window_size),
                                "ridge_factor": float(ridge_factor),
                                "ridge_lambda": float(ridge_lambda),
                                "alpha": float(alpha),
                                "direct_residual_inf_n": residual_inf,
                                "improvement_inf_n": float(improvement_inf),
                                "relative_improvement": float(relative_improvement),
                                "direct_relative_residual_inf": residual_inf
                                / max(
                                    float(np.max(np.abs(candidate_rhs)))
                                    if candidate_rhs.size
                                    else 0.0,
                                    1.0,
                                ),
                                "relative_increment": increment / max_abs,
                                "max_increment_m": increment,
                                "max_translation_m": metrics["max_translation_m"],
                                "residual_gate_passed": bool(
                                    residual_inf <= residual_tolerance_n
                                ),
                                "relative_increment_gate_passed": bool(
                                    increment / max_abs <= relative_increment_tolerance
                                ),
                            }
                            trial_rows.append(row)
                            trial_vectors.append(candidate_u)
                        candidate_trials = trial_rows[candidate_start_index:]
                        best_candidate = min(
                            candidate_trials,
                            key=lambda row: float(row["direct_residual_inf_n"]),
                        )
                        family_candidate_rows.append(
                            {
                                "window_size": int(window_size),
                                "requested_window_size": int(raw_window_size),
                                "ridge_factor": float(ridge_factor),
                                "ridge_lambda": float(ridge_lambda),
                                "rank": int(rank),
                                "singular_values": [
                                    float(value) for value in singular_values.tolist()
                                ],
                                "coefficient_l2": float(np.linalg.norm(coeffs)),
                                "coefficient_linf": (
                                    float(np.max(np.abs(coeffs))) if coeffs.size else 0.0
                                ),
                                "candidate_delta_inf_m": candidate_delta_inf,
                                "gate_limited_alpha": float(gate_limited_alpha),
                                "alpha_values": [float(alpha) for alpha in family_alphas],
                                "linear_least_squares_residual_sum": [
                                    float(value)
                                    for value in np.ravel(residual_sum).tolist()
                                ],
                                "linear_solve_seconds": float(solve_seconds),
                                "best_candidate": best_candidate,
                                "residual_descent": bool(
                                    float(best_candidate["direct_residual_inf_n"])
                                    < previous_residual_inf
                                ),
                            }
                        )
                if not trial_rows:
                    pass_payload["promoted_to_final_state"] = False
                    pass_payload["reason"] = "secant_family_candidates_unavailable"
                    pass_rows.append(pass_payload)
                    secant_family_globalization["stop_reason"] = str(pass_payload["reason"])
                    break
                best_trial_index, best_trial = min(
                    enumerate(trial_rows),
                    key=lambda item: float(item[1]["direct_residual_inf_n"]),
                )
                gate_eligible_trials = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                    and float(row.get("relative_improvement", 0.0))
                    >= min_family_relative_improvement
                ]
                gate_eligible_without_floor = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                ]
                best_gate_trial_index: int | None = None
                best_gate_trial: dict[str, Any] | None = None
                if gate_eligible_trials:
                    best_gate_trial_index, best_gate_trial = min(
                        gate_eligible_trials,
                        key=lambda item: float(item[1]["direct_residual_inf_n"]),
                    )
                    all_gate_candidates.append(best_gate_trial)
                promoted = best_gate_trial is not None
                pass_payload.update(
                    {
                        "candidate_rows": family_candidate_rows,
                        "trial_rows": trial_rows,
                        "best_candidate": best_trial,
                        "best_gate_eligible_candidate": best_gate_trial,
                        "residual_descent": bool(
                            float(best_trial["direct_residual_inf_n"])
                            < previous_residual_inf
                        ),
                        "promoted_to_final_state": promoted,
                    }
                )
                if best_gate_trial is not None:
                    pass_payload["accepted_improvement_inf_n"] = float(
                        best_gate_trial["improvement_inf_n"]
                    )
                    pass_payload["accepted_relative_improvement"] = float(
                        best_gate_trial["relative_improvement"]
                    )
                elif gate_eligible_without_floor:
                    pass_payload["reason"] = "relative_improvement_floor_not_met"
                elif not bool(pass_payload["residual_descent"]):
                    pass_payload["reason"] = "no_residual_descent"
                else:
                    pass_payload["reason"] = "no_gate_eligible_residual_descent"
                pass_rows.append(pass_payload)
                all_trial_rows.extend(trial_rows)
                if not promoted:
                    secant_family_globalization["stop_reason"] = str(pass_payload["reason"])
                    break
                assert best_gate_trial_index is not None
                promotion_count += 1
                current_u = trial_vectors[best_gate_trial_index]
                (
                    current_stiffness,
                    _current_f_ext,
                    current_free,
                    current_residual,
                    current_rhs,
                    _current_meta,
                ) = assemble_residual(current_u, external_load_override=reference_f_ext)
                accepted_state_history.append(np.asarray(current_u, dtype=np.float64).copy())
                accepted_residual_history.append(
                    np.asarray(current_residual, dtype=np.float64).copy()
                )
            if max_family_promotions == 0:
                secant_family_globalization["stop_reason"] = "max_promotions_zero"
            elif promotion_count >= max_family_promotions:
                secant_family_globalization["stop_reason"] = "max_promotions_exhausted"
            best_candidate_family = (
                min(all_trial_rows, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_trial_rows
                else None
            )
            best_gate_candidate_family = (
                min(all_gate_candidates, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_gate_candidates
                else None
            )
            secant_family_globalization.update(
                {
                    "accepted": bool(promotion_count),
                    "promoted_to_final_state": bool(promotion_count),
                    "promotion_count": int(promotion_count),
                    "passes": pass_rows,
                    "trial_rows": all_trial_rows,
                    "best_candidate": best_candidate_family,
                    "best_gate_eligible_candidate": best_gate_candidate_family,
                    "residual_descent": bool(
                        best_candidate_family
                        and float(best_candidate_family["direct_residual_inf_n"])
                        < base_residual_inf
                    ),
                }
            )

        matrix_free_jacobian_subspace: dict[str, Any] = {
            "enabled": bool(enable_matrix_free_jacobian_subspace),
            "attempted": False,
            "accepted": False,
            "promoted_to_final_state": False,
            "basis_size": 0,
            "promotion_count": 0,
            "max_promotions": int(max_matrix_free_jacobian_subspace_promotions),
            "probe_scale": float(matrix_free_jacobian_probe_scale),
            "probe_scales": [
                float(value)
                for value in (
                    matrix_free_jacobian_probe_scales
                    if matrix_free_jacobian_probe_scales
                    else (matrix_free_jacobian_probe_scale,)
                )
                if float(value) > 0.0
            ],
            "difference_scheme": str(matrix_free_jacobian_difference_scheme),
            "basis_sources": list(_parse_matrix_free_basis_sources(matrix_free_jacobian_basis_sources)),
            "probe_max_step_m": float(max(matrix_free_jacobian_probe_max_step, 0.0)),
            "ridge_factors": [
                float(value)
                for value in (matrix_free_jacobian_ridge_factors or (0.0,))
                if float(value) >= 0.0
            ],
            "allow_negative_alphas": bool(matrix_free_jacobian_allow_negative_alphas),
            "max_alpha": float(max(matrix_free_jacobian_max_alpha, 1.0e-8)),
            "minimum_relative_improvement": float(
                max(matrix_free_jacobian_min_relative_improvement, 0.0)
            ),
            "stop_reason": "not_attempted",
            "passes": [],
            "trial_rows": [],
        }
        if (
            enable_matrix_free_jacobian_subspace
            and current_residual.size
            and len(accepted_state_history) >= 2
        ):
            pass_rows: list[dict[str, Any]] = []
            all_jvp_rows: list[dict[str, Any]] = []
            all_trial_rows: list[dict[str, Any]] = []
            all_gate_candidates: list[dict[str, Any]] = []
            promotion_count = 0
            max_matrix_free_promotions = max(
                int(max_matrix_free_jacobian_subspace_promotions), 0
            )
            min_matrix_free_relative_improvement = max(
                float(matrix_free_jacobian_min_relative_improvement), 0.0
            )
            matrix_free_probe_scales = tuple(
                float(value)
                for value in matrix_free_jacobian_subspace["probe_scales"]
                if float(value) > 0.0
            )
            matrix_free_difference_scheme = str(matrix_free_jacobian_difference_scheme).strip()
            if matrix_free_difference_scheme not in {"forward", "central"}:
                matrix_free_difference_scheme = "forward"
            matrix_free_jacobian_subspace["difference_scheme"] = matrix_free_difference_scheme
            matrix_free_basis_sources = _parse_matrix_free_basis_sources(
                matrix_free_jacobian_basis_sources
            )
            matrix_free_jacobian_subspace["basis_sources"] = [
                str(source) for source in matrix_free_basis_sources
            ]
            matrix_free_probe_max_step = max(float(matrix_free_jacobian_probe_max_step), 0.0)
            matrix_free_jacobian_subspace["probe_max_step_m"] = matrix_free_probe_max_step
            matrix_free_ridge_factors = tuple(
                float(value)
                for value in (matrix_free_jacobian_ridge_factors or (0.0,))
                if float(value) >= 0.0
            ) or (0.0,)
            matrix_free_jacobian_subspace["ridge_factors"] = [
                float(value) for value in matrix_free_ridge_factors
            ]
            matrix_free_jacobian_subspace["allow_negative_alphas"] = bool(
                matrix_free_jacobian_allow_negative_alphas
            )
            matrix_free_max_alpha = max(float(matrix_free_jacobian_max_alpha), 1.0e-8)
            matrix_free_jacobian_subspace["max_alpha"] = matrix_free_max_alpha
            for matrix_free_pass in range(
                1,
                max_matrix_free_promotions + 1,
            ):
                previous_residual_inf = (
                    float(np.max(np.abs(current_residual))) if current_residual.size else 0.0
                )
                basis_pairs: list[tuple[dict[str, Any], np.ndarray]] = []
                if "history" in matrix_free_basis_sources:
                    raw_basis = [
                        accepted_state_history[index + 1] - accepted_state_history[index]
                        for index in range(len(accepted_state_history) - 1)
                    ]
                    history_pairs: list[tuple[dict[str, Any], np.ndarray]] = []
                    for history_offset, vector in enumerate(reversed(raw_basis), start=1):
                        vector_inf = float(np.max(np.abs(vector))) if vector.size else 0.0
                        if vector_inf <= 1.0e-14:
                            continue
                        history_pairs.append(
                            (
                                {
                                    "source": "history",
                                    "history_reverse_index": int(history_offset),
                                    "basis_inf_m": vector_inf,
                                },
                                np.asarray(vector, dtype=np.float64),
                            )
                        )
                        if len(history_pairs) >= max(int(matrix_free_jacobian_subspace_basis_size), 0):
                            break
                    basis_pairs.extend(reversed(history_pairs))
                if "current_newton" in matrix_free_basis_sources:
                    k_ff = current_stiffness[current_free, :][:, current_free].tocsc()
                    diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
                    regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
                    solve_started = time.perf_counter()
                    correction_free = np.asarray(
                        spsolve(
                            k_ff + eye(k_ff.shape[0], format="csc") * regularization,
                            -current_residual,
                        ),
                        dtype=np.float64,
                    )
                    solve_seconds = time.perf_counter() - solve_started
                    correction = np.zeros_like(current_u)
                    correction[current_free] = correction_free
                    correction_inf = (
                        float(np.max(np.abs(correction_free))) if correction_free.size else 0.0
                    )
                    if correction_inf > 1.0e-14:
                        basis_pairs.append(
                            (
                                {
                                    "source": "current_newton",
                                    "regularization": float(regularization),
                                    "linear_solve_seconds": float(solve_seconds),
                                    "basis_inf_m": correction_inf,
                                },
                                correction,
                            )
                        )
                basis_limit = max(int(matrix_free_jacobian_subspace_basis_size), 0)
                basis_pairs = basis_pairs[-basis_limit:] if basis_limit else []
                basis_vectors = [vector for _meta, vector in basis_pairs]
                basis_meta_rows = [
                    {**meta, "basis_index": int(index)}
                    for index, (meta, _vector) in enumerate(basis_pairs, start=1)
                ]
                basis_size = int(len(basis_vectors))
                matrix_free_jacobian_subspace["basis_size"] = max(
                    int(matrix_free_jacobian_subspace["basis_size"]),
                    basis_size,
                )
                matrix_free_jacobian_subspace["attempted"] = bool(
                    matrix_free_jacobian_subspace["attempted"] or basis_vectors
                )
                pass_payload: dict[str, Any] = {
                    "matrix_free_pass": int(matrix_free_pass),
                    "previous_direct_residual_inf_n": previous_residual_inf,
                    "history_state_count": int(len(accepted_state_history)),
                    "basis_size": basis_size,
                    "basis_rows": basis_meta_rows,
                    "probe_scale": float(matrix_free_jacobian_probe_scale),
                    "probe_scales": [float(value) for value in matrix_free_probe_scales],
                }
                jvp_columns: list[np.ndarray] = []
                jvp_rows: list[dict[str, Any]] = []
                if basis_vectors and matrix_free_probe_scales:
                    for basis_index, basis_vector in enumerate(basis_vectors, start=1):
                        basis_meta = basis_meta_rows[basis_index - 1]
                        basis_inf = float(np.max(np.abs(basis_vector))) if basis_vector.size else 0.0
                        scale_options: list[tuple[dict[str, Any], np.ndarray]] = []
                        for probe_scale in matrix_free_probe_scales:
                            effective_probe_scale = float(probe_scale)
                            if matrix_free_probe_max_step > 0.0 and basis_inf > 0.0:
                                effective_probe_scale = min(
                                    effective_probe_scale,
                                    matrix_free_probe_max_step / basis_inf,
                                )
                            plus_probe_u = current_u + effective_probe_scale * basis_vector
                            (
                                _plus_probe_k,
                                _plus_probe_f,
                                plus_probe_free,
                                plus_probe_residual,
                                _plus_probe_rhs,
                                _plus_probe_meta,
                            ) = assemble_residual(
                                plus_probe_u,
                                external_load_override=reference_f_ext,
                            )
                            plus_free_is_stable = bool(
                                plus_probe_free.shape == current_free.shape
                                and np.array_equal(plus_probe_free, current_free)
                            )
                            plus_probe_residual_inf = (
                                float(np.max(np.abs(plus_probe_residual)))
                                if plus_probe_residual.size
                                else 0.0
                            )
                            row = {
                                "matrix_free_pass": int(matrix_free_pass),
                                "basis_index": int(basis_index),
                                "basis_source": str(basis_meta.get("source", "unknown")),
                                "basis_inf_m": basis_inf,
                                "probe_scale": float(probe_scale),
                                "effective_probe_scale": float(effective_probe_scale),
                                "probe_step_inf_m": float(effective_probe_scale * basis_inf),
                                "difference_scheme": matrix_free_difference_scheme,
                                "free_dof_set_stable": plus_free_is_stable,
                                "probe_direct_residual_inf_n": plus_probe_residual_inf,
                                "plus_probe_direct_residual_inf_n": plus_probe_residual_inf,
                                "selected_for_basis": False,
                            }
                            minus_probe_residual: np.ndarray | None = None
                            if matrix_free_difference_scheme == "central":
                                minus_probe_u = current_u - effective_probe_scale * basis_vector
                                (
                                    _minus_probe_k,
                                    _minus_probe_f,
                                    minus_probe_free,
                                    minus_probe_residual_candidate,
                                    _minus_probe_rhs,
                                    _minus_probe_meta,
                                ) = assemble_residual(
                                    minus_probe_u,
                                    external_load_override=reference_f_ext,
                                )
                                minus_probe_residual = minus_probe_residual_candidate
                                minus_free_is_stable = bool(
                                    minus_probe_free.shape == current_free.shape
                                    and np.array_equal(minus_probe_free, current_free)
                                )
                                minus_probe_residual_inf = (
                                    float(np.max(np.abs(minus_probe_residual)))
                                    if minus_probe_residual.size
                                    else 0.0
                                )
                                row["minus_probe_direct_residual_inf_n"] = minus_probe_residual_inf
                                row["free_dof_set_stable"] = bool(
                                    plus_free_is_stable and minus_free_is_stable
                                )
                                if not minus_free_is_stable:
                                    row["reason"] = "minus_free_dof_set_changed"
                            if bool(row["free_dof_set_stable"]):
                                if matrix_free_difference_scheme == "central":
                                    assert minus_probe_residual is not None
                                    jvp = (
                                        plus_probe_residual - minus_probe_residual
                                    ) / (2.0 * effective_probe_scale)
                                else:
                                    jvp = (
                                        plus_probe_residual - current_residual
                                    ) / effective_probe_scale
                                row["jacobian_action_inf_n"] = (
                                    float(np.max(np.abs(jvp))) if jvp.size else 0.0
                                )
                                row["jacobian_action_l2_n"] = (
                                    float(np.linalg.norm(jvp)) if jvp.size else 0.0
                                )
                                scale_options.append((row, jvp))
                            else:
                                row.setdefault("reason", "plus_free_dof_set_changed")
                            jvp_rows.append(row)
                        if scale_options:
                            selected_row, selected_jvp = min(
                                scale_options,
                                key=lambda item: float(item[0]["probe_direct_residual_inf_n"]),
                            )
                            selected_row["selected_for_basis"] = True
                            jvp_columns.append(selected_jvp)
                pass_payload["jvp_rows"] = jvp_rows
                all_jvp_rows.extend(jvp_rows)
                if not jvp_columns:
                    pass_payload["promoted_to_final_state"] = False
                    pass_payload["reason"] = (
                        "jvp_basis_unavailable"
                        if basis_vectors
                        else "accepted_history_basis_unavailable"
                    )
                    matrix_free_jacobian_subspace["stop_reason"] = pass_payload["reason"]
                    pass_rows.append(pass_payload)
                    break

                current_max_abs = max(
                    float(np.max(np.abs(current_u))) if current_u.size else 0.0,
                    1.0e-9,
                )
                basis_candidate_rows: list[dict[str, Any]] = []
                trial_rows: list[dict[str, Any]] = []
                trial_vectors: list[np.ndarray] = []
                for basis_count in range(1, len(jvp_columns) + 1):
                    selected_jvp_columns = jvp_columns[-basis_count:]
                    selected_basis_vectors = basis_vectors[-basis_count:]
                    jacobian_basis = np.column_stack(selected_jvp_columns)
                    basis_singular_values = np.linalg.svd(
                        jacobian_basis,
                        compute_uv=False,
                        full_matrices=False,
                    )
                    basis_scale = (
                        float(np.max(basis_singular_values))
                        if basis_singular_values.size
                        else 1.0
                    )
                    for ridge_factor in matrix_free_ridge_factors:
                        ridge_factor = float(ridge_factor)
                        ridge_lambda = ridge_factor * max(basis_scale, 1.0)
                        least_squares_started = time.perf_counter()
                        if ridge_lambda > 0.0:
                            augmented_basis = np.vstack(
                                [
                                    jacobian_basis,
                                    np.eye(jacobian_basis.shape[1], dtype=np.float64)
                                    * ridge_lambda,
                                ]
                            )
                            augmented_rhs = np.concatenate(
                                [
                                    -current_residual,
                                    np.zeros(jacobian_basis.shape[1], dtype=np.float64),
                                ]
                            )
                            coeffs, residual_sum, rank, singular_values = np.linalg.lstsq(
                                augmented_basis,
                                augmented_rhs,
                                rcond=None,
                            )
                        else:
                            coeffs, residual_sum, rank, singular_values = np.linalg.lstsq(
                                jacobian_basis,
                                -current_residual,
                                rcond=None,
                            )
                        linear_solve_seconds = time.perf_counter() - least_squares_started
                        candidate_delta_u = np.zeros_like(current_u)
                        for coeff, basis_vector in zip(coeffs.tolist(), selected_basis_vectors):
                            candidate_delta_u += float(coeff) * basis_vector
                        candidate_delta_inf = (
                            float(np.max(np.abs(candidate_delta_u)))
                            if candidate_delta_u.size
                            else 0.0
                        )
                        gate_limited_alpha = (
                            0.95
                            * float(relative_increment_tolerance)
                            * current_max_abs
                            / candidate_delta_inf
                            if candidate_delta_inf > 0.0
                            else 0.0
                        )
                        positive_alpha_rows = _unique_positive_alphas(
                            [
                                ("matrix_free_jacobian_subspace", alpha)
                                for alpha in matrix_free_jacobian_alpha_values
                            ]
                            + [
                                ("matrix_free_jacobian_subspace", gate_limited_alpha),
                                ("matrix_free_jacobian_subspace", 0.5 * gate_limited_alpha),
                            ],
                            min_alpha=1.0e-8,
                            max_alpha=matrix_free_max_alpha,
                        )
                        matrix_free_alpha_rows: list[tuple[str, float]] = list(
                            positive_alpha_rows
                        )
                        if matrix_free_jacobian_allow_negative_alphas:
                            matrix_free_alpha_rows.extend(
                                (f"{source}_negative", -float(alpha))
                                for source, alpha in positive_alpha_rows
                            )
                        candidate_start_index = len(trial_rows)
                        for alpha_source, alpha in matrix_free_alpha_rows:
                            candidate_u = current_u + float(alpha) * candidate_delta_u
                            (
                                _k,
                                _f,
                                _free,
                                candidate_residual,
                                candidate_rhs,
                                _meta,
                            ) = assemble_residual(
                                candidate_u,
                                external_load_override=reference_f_ext,
                            )
                            residual_inf = (
                                float(np.max(np.abs(candidate_residual)))
                                if candidate_residual.size
                                else 0.0
                            )
                            improvement_inf = previous_residual_inf - residual_inf
                            relative_improvement = improvement_inf / max(
                                previous_residual_inf, 1.0e-30
                            )
                            increment = (
                                float(np.max(np.abs(candidate_u - current_u)))
                                if candidate_u.size
                                else 0.0
                            )
                            max_abs = max(
                                float(np.max(np.abs(candidate_u)))
                                if candidate_u.size
                                else current_max_abs,
                                1.0e-9,
                            )
                            metrics = _translation_metrics(candidate_u, node_xyz)
                            row = {
                                "matrix_free_pass": int(matrix_free_pass),
                                "basis_size_used": int(basis_count),
                                "ridge_factor": float(ridge_factor),
                                "ridge_lambda": float(ridge_lambda),
                                "alpha_source": str(alpha_source),
                                "alpha": float(alpha),
                                "alpha_abs": abs(float(alpha)),
                                "alpha_sign": -1 if float(alpha) < 0.0 else 1,
                                "direct_residual_inf_n": residual_inf,
                                "improvement_inf_n": float(improvement_inf),
                                "relative_improvement": float(relative_improvement),
                                "direct_relative_residual_inf": residual_inf
                                / max(
                                    float(np.max(np.abs(candidate_rhs)))
                                    if candidate_rhs.size
                                    else 0.0,
                                    1.0,
                                ),
                                "relative_increment": increment / max_abs,
                                "max_increment_m": increment,
                                "max_translation_m": metrics["max_translation_m"],
                                "residual_gate_passed": bool(residual_inf <= residual_tolerance_n),
                                "relative_increment_gate_passed": bool(
                                    increment / max_abs <= relative_increment_tolerance
                                ),
                            }
                            trial_rows.append(row)
                            trial_vectors.append(candidate_u)
                        basis_trials = trial_rows[candidate_start_index:]
                        best_basis_trial = min(
                            basis_trials,
                            key=lambda row: float(row["direct_residual_inf_n"]),
                        )
                        basis_candidate_rows.append(
                            {
                                "basis_size_used": int(basis_count),
                                "ridge_factor": float(ridge_factor),
                                "ridge_lambda": float(ridge_lambda),
                                "rank": int(rank),
                                "basis_singular_values": [
                                    float(value) for value in basis_singular_values.tolist()
                                ],
                                "singular_values": [
                                    float(value) for value in singular_values.tolist()
                                ],
                                "coefficient_l2": float(np.linalg.norm(coeffs)),
                                "coefficient_linf": (
                                    float(np.max(np.abs(coeffs))) if coeffs.size else 0.0
                                ),
                                "candidate_delta_inf_m": candidate_delta_inf,
                                "gate_limited_alpha": float(gate_limited_alpha),
                                "alpha_values": [
                                    float(alpha) for _source, alpha in matrix_free_alpha_rows
                                ],
                                "linear_least_squares_residual_sum": [
                                    float(value) for value in np.ravel(residual_sum).tolist()
                                ],
                                "linear_solve_seconds": float(linear_solve_seconds),
                                "best_candidate": best_basis_trial,
                                "residual_descent": bool(
                                    float(best_basis_trial["direct_residual_inf_n"])
                                    < previous_residual_inf
                                ),
                            }
                        )
                best_trial_index, best_trial = min(
                    enumerate(trial_rows),
                    key=lambda item: float(item[1]["direct_residual_inf_n"]),
                )
                gate_eligible_trials = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                    and float(row.get("relative_improvement", 0.0))
                    >= min_matrix_free_relative_improvement
                ]
                gate_eligible_without_floor = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                ]
                best_gate_trial_index: int | None = None
                best_gate_trial: dict[str, Any] | None = None
                if gate_eligible_trials:
                    best_gate_trial_index, best_gate_trial = min(
                        gate_eligible_trials,
                        key=lambda item: float(item[1]["direct_residual_inf_n"]),
                    )
                    all_gate_candidates.append(best_gate_trial)
                promoted = best_gate_trial is not None
                selected_basis_candidate = next(
                    (
                        row
                        for row in basis_candidate_rows
                        if best_gate_trial is not None
                        and int(row["basis_size_used"]) == int(best_gate_trial["basis_size_used"])
                        and abs(
                            float(row.get("ridge_factor", 0.0))
                            - float(best_gate_trial.get("ridge_factor", 0.0))
                        )
                        <= 1.0e-15
                    ),
                    min(
                        basis_candidate_rows,
                        key=lambda row: float(row["best_candidate"]["direct_residual_inf_n"]),
                    ),
                )
                pass_payload.update(
                    {
                        "selected_basis_size": int(selected_basis_candidate["basis_size_used"]),
                        "selected_ridge_factor": float(
                            selected_basis_candidate.get("ridge_factor", 0.0)
                        ),
                        "selected_ridge_lambda": float(
                            selected_basis_candidate.get("ridge_lambda", 0.0)
                        ),
                        "basis_candidate_rows": basis_candidate_rows,
                        "rank": int(selected_basis_candidate["rank"]),
                        "basis_singular_values": selected_basis_candidate[
                            "basis_singular_values"
                        ],
                        "singular_values": selected_basis_candidate["singular_values"],
                        "coefficient_l2": float(selected_basis_candidate["coefficient_l2"]),
                        "coefficient_linf": float(selected_basis_candidate["coefficient_linf"]),
                        "candidate_delta_inf_m": float(
                            selected_basis_candidate["candidate_delta_inf_m"]
                        ),
                        "gate_limited_alpha": float(selected_basis_candidate["gate_limited_alpha"]),
                        "alpha_values": selected_basis_candidate["alpha_values"],
                        "linear_least_squares_residual_sum": selected_basis_candidate[
                            "linear_least_squares_residual_sum"
                        ],
                        "linear_solve_seconds": float(
                            selected_basis_candidate["linear_solve_seconds"]
                        ),
                        "trial_rows": trial_rows,
                        "best_candidate": best_trial,
                        "best_gate_eligible_candidate": best_gate_trial,
                        "residual_descent": bool(
                            float(best_trial["direct_residual_inf_n"]) < previous_residual_inf
                        ),
                        "promoted_to_final_state": promoted,
                    }
                )
                if best_gate_trial is not None:
                    pass_payload["accepted_improvement_inf_n"] = float(
                        best_gate_trial["improvement_inf_n"]
                    )
                    pass_payload["accepted_relative_improvement"] = float(
                        best_gate_trial["relative_improvement"]
                    )
                elif gate_eligible_without_floor:
                    pass_payload["reason"] = "relative_improvement_floor_not_met"
                elif not bool(pass_payload["residual_descent"]):
                    pass_payload["reason"] = "no_residual_descent"
                else:
                    pass_payload["reason"] = "no_gate_eligible_residual_descent"
                pass_rows.append(pass_payload)
                all_trial_rows.extend(trial_rows)
                if not promoted:
                    matrix_free_jacobian_subspace["stop_reason"] = str(pass_payload["reason"])
                    break
                assert best_gate_trial_index is not None
                promotion_count += 1
                current_u = trial_vectors[best_gate_trial_index]
                (
                    current_stiffness,
                    _current_f_ext,
                    current_free,
                    current_residual,
                    current_rhs,
                    _current_meta,
                ) = assemble_residual(current_u, external_load_override=reference_f_ext)
                accepted_state_history.append(np.asarray(current_u, dtype=np.float64).copy())
                accepted_residual_history.append(np.asarray(current_residual, dtype=np.float64).copy())
            if max_matrix_free_promotions == 0:
                matrix_free_jacobian_subspace["stop_reason"] = "max_promotions_zero"
            elif (
                int(matrix_free_jacobian_subspace.get("promotion_count") or 0)
                < promotion_count
                and promotion_count >= max_matrix_free_promotions
            ):
                matrix_free_jacobian_subspace["stop_reason"] = "max_promotions_exhausted"
            best_candidate_matrix_free = (
                min(all_trial_rows, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_trial_rows
                else None
            )
            best_gate_candidate_matrix_free = (
                min(all_gate_candidates, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_gate_candidates
                else None
            )
            matrix_free_jacobian_subspace.update(
                {
                    "accepted": bool(promotion_count),
                    "promoted_to_final_state": bool(promotion_count),
                    "promotion_count": int(promotion_count),
                    "stop_reason": matrix_free_jacobian_subspace["stop_reason"],
                    "passes": pass_rows,
                    "jvp_rows": all_jvp_rows,
                    "trial_rows": all_trial_rows,
                    "best_candidate": best_candidate_matrix_free,
                    "best_gate_eligible_candidate": best_gate_candidate_matrix_free,
                    "residual_descent": bool(
                        best_candidate_matrix_free
                        and float(best_candidate_matrix_free["direct_residual_inf_n"])
                        < base_residual_inf
                    ),
                }
            )

        matrix_free_global_krylov: dict[str, Any] = {
            "enabled": bool(enable_matrix_free_global_krylov),
            "attempted": False,
            "accepted": False,
            "promoted_to_final_state": False,
            "method": "gmres",
            "max_iterations": int(max(matrix_free_global_krylov_max_iterations, 0)),
            "difference_scheme": str(matrix_free_global_krylov_difference_scheme),
            "probe_epsilon": float(matrix_free_global_krylov_probe_epsilon),
            "probe_max_step_m": float(max(matrix_free_global_krylov_probe_max_step, 0.0)),
            "scaling_mode": str(matrix_free_global_krylov_scaling_mode),
            "displacement_scale_m": float(matrix_free_global_krylov_displacement_scale),
            "residual_scale_floor_n": float(matrix_free_global_krylov_residual_scale_floor),
            "preconditioner_mode": str(matrix_free_global_krylov_preconditioner_mode),
            "preconditioner_input_scale_n": float(
                matrix_free_global_krylov_preconditioner_input_scale
            ),
            "tangent_regularization_factor": float(
                matrix_free_global_krylov_tangent_regularization_factor
            ),
            "allow_negative_alphas": bool(matrix_free_global_krylov_allow_negative_alphas),
            "max_alpha": float(matrix_free_global_krylov_max_alpha),
            "minimum_relative_improvement": float(
                max(matrix_free_global_krylov_min_relative_improvement, 0.0)
            ),
            "full_assembly_trial_replay": bool(
                matrix_free_global_krylov_full_assembly_trial_replay
            ),
            "batch_replay_backend": str(
                matrix_free_global_krylov_batch_replay_backend
            ),
            "require_hip_batch_replay": bool(
                matrix_free_global_krylov_require_hip_batch_replay
            ),
            "linear_solver_backend": str(
                matrix_free_global_krylov_linear_solver_backend
            ),
            "hip_batch_replay_required_unavailable": False,
            "hip_krylov_solver_required_unavailable": False,
            "cpu_batch_replay_fallback_suppressed": False,
            "alpha_values": [
                float(value)
                for value in matrix_free_global_krylov_alpha_values
                if float(value) > 0.0
            ],
            "matvec_count": 0,
            "unstable_free_dof_probe_count": 0,
            "trial_rows": [],
            "best_candidate": None,
            "best_gate_eligible_candidate": None,
            "stop_reason": "not_attempted",
        }
        if (
            apply_shell_material_tangent
            and allow_state_dependent_shell_material_tangent_hip_replay
            and global_batch_backend in {
                "hip_full_residual",
                "hip_full_residual_resident",
                "rust_hip_full_residual_ffi",
            }
        ):
            matrix_free_global_krylov[
                "state_dependent_shell_material_tangent_hip_replay"
            ] = True
            matrix_free_global_krylov[
                "state_dependent_shell_material_tangent_operator_refresh_backend"
            ] = "host_shell_operator_refresh"
        if (
            enable_matrix_free_global_krylov
            and current_residual.size
            and int(matrix_free_global_krylov_max_iterations) > 0
        ):
            matrix_free_global_krylov["attempted"] = True
            previous_residual_inf = (
                float(np.max(np.abs(current_residual))) if current_residual.size else 0.0
            )
            base_u_for_krylov = np.asarray(current_u, dtype=np.float64).copy()
            base_free_for_krylov = np.asarray(current_free, dtype=np.int64).copy()
            base_residual_for_krylov = np.asarray(current_residual, dtype=np.float64).copy()
            n_free = int(base_residual_for_krylov.size)
            matvec_count = 0
            unstable_probe_count = 0
            jvp_rows: list[dict[str, Any]] = []
            probe_epsilon = max(float(matrix_free_global_krylov_probe_epsilon), 1.0e-12)
            probe_max_step = max(float(matrix_free_global_krylov_probe_max_step), 0.0)
            global_difference_scheme = (
                str(matrix_free_global_krylov_difference_scheme).strip().lower()
            )
            if global_difference_scheme not in {"forward", "central"}:
                global_difference_scheme = "forward"
            scaling_mode = str(matrix_free_global_krylov_scaling_mode).strip().lower()
            if scaling_mode not in {"none", "residual_diagonal_displacement"}:
                scaling_mode = "none"
            preconditioner_mode = (
                str(matrix_free_global_krylov_preconditioner_mode).strip().lower()
            )
            if preconditioner_mode not in {"none", "current_tangent"}:
                preconditioner_mode = "none"
            displacement_scale = max(float(matrix_free_global_krylov_displacement_scale), 1.0e-12)
            preconditioner_input_scale = max(
                float(matrix_free_global_krylov_preconditioner_input_scale),
                1.0e-30,
            )
            residual_scale_floor = max(float(matrix_free_global_krylov_residual_scale_floor), 1.0e-30)
            max_global_krylov_alpha = max(
                float(matrix_free_global_krylov_max_alpha),
                1.0e-10,
            )
            matrix_free_global_krylov["max_alpha"] = float(max_global_krylov_alpha)
            if scaling_mode == "residual_diagonal_displacement":
                row_scale = 1.0 / np.maximum(
                    np.abs(base_residual_for_krylov),
                    residual_scale_floor,
                )
            else:
                row_scale = np.ones(n_free, dtype=np.float64)
            if preconditioner_mode == "current_tangent":
                column_scale = np.full(n_free, preconditioner_input_scale, dtype=np.float64)
            elif scaling_mode == "residual_diagonal_displacement":
                column_scale = np.full(n_free, displacement_scale, dtype=np.float64)
            else:
                column_scale = np.ones(n_free, dtype=np.float64)
            matrix_free_global_krylov["scaling_mode"] = scaling_mode
            matrix_free_global_krylov["difference_scheme"] = global_difference_scheme
            matrix_free_global_krylov["preconditioner_mode"] = preconditioner_mode
            matrix_free_global_krylov["preconditioner_input_scale_n"] = (
                preconditioner_input_scale
            )
            matrix_free_global_krylov["row_scale_inf"] = (
                float(np.max(np.abs(row_scale))) if row_scale.size else 0.0
            )
            matrix_free_global_krylov["row_scale_min"] = (
                float(np.min(np.abs(row_scale))) if row_scale.size else 0.0
            )
            matrix_free_global_krylov["column_scale_inf_m"] = (
                float(np.max(np.abs(column_scale))) if column_scale.size else 0.0
            )
            matrix_free_global_krylov["column_scale_units"] = (
                "preconditioner_input_n"
                if preconditioner_mode == "current_tangent"
                else "displacement_m"
            )
            preconditioner_solve_count = 0
            preconditioner_solve_seconds = 0.0
            preconditioner_regularization = 0.0
            preconditioner_matrix = None
            residual_only_matvec_count = 0
            full_assembly_matvec_count = 0
            residual_only_trial_count = 0
            full_assembly_trial_count = 0
            full_assembly_trial_replay_count = 0
            global_batch_backend = str(
                matrix_free_global_krylov_batch_replay_backend
            ).strip()
            if global_batch_backend not in {
                "cpu",
                "hip_full_residual",
                "hip_full_residual_resident",
                "rust_hip_full_residual_ffi",
            }:
                global_batch_backend = "cpu"
            global_linear_solver_backend = str(
                matrix_free_global_krylov_linear_solver_backend
            ).strip().lower()
            if global_linear_solver_backend not in {
                "scipy_host_gmres",
                "torch_hip_gmres",
            }:
                global_linear_solver_backend = "scipy_host_gmres"
            global_require_hip_batch_replay = bool(
                matrix_free_global_krylov_require_hip_batch_replay
                and global_batch_backend
                in {
                    "hip_full_residual",
                    "hip_full_residual_resident",
                    "rust_hip_full_residual_ffi",
                }
            )
            if (
                global_require_hip_batch_replay
                and global_linear_solver_backend == "scipy_host_gmres"
            ):
                global_linear_solver_backend = "torch_hip_gmres"
                matrix_free_global_krylov[
                    "linear_solver_backend_auto_selected_reason"
                ] = "hip_batch_replay_required_suppresses_host_gmres"
            effective_full_assembly_trial_replay = bool(
                matrix_free_global_krylov_full_assembly_trial_replay
                and not global_require_hip_batch_replay
            )
            global_hip_batch_eval_count = 0
            global_hip_batch_state_count = 0
            global_hip_batch_seconds = 0.0
            global_hip_backend: Any | None = None
            global_hip_backend_error = ""
            matrix_free_global_krylov["batch_replay_backend"] = global_batch_backend
            matrix_free_global_krylov[
                "linear_solver_backend"
            ] = global_linear_solver_backend
            matrix_free_global_krylov["require_hip_batch_replay"] = (
                global_require_hip_batch_replay
            )
            matrix_free_global_krylov["require_hip_krylov_solver"] = bool(
                global_linear_solver_backend == "torch_hip_gmres"
                or global_require_hip_batch_replay
            )
            if (
                global_require_hip_batch_replay
                and preconditioner_mode == "current_tangent"
            ):
                matrix_free_global_krylov[
                    "preconditioner_mode_requested"
                ] = "current_tangent"
                matrix_free_global_krylov[
                    "preconditioner_mode_disabled_reason"
                ] = (
                    "hip_batch_replay_required_suppresses_cpu_current_tangent_"
                    "preconditioner"
                )
                preconditioner_mode = "none"
                matrix_free_global_krylov["preconditioner_mode"] = preconditioner_mode
            if (
                global_require_hip_batch_replay
                and matrix_free_global_krylov_full_assembly_trial_replay
            ):
                matrix_free_global_krylov["full_assembly_trial_replay"] = False
                matrix_free_global_krylov[
                    "full_assembly_trial_replay_disabled_reason"
                ] = "hip_batch_replay_required_suppresses_cpu_full_assembly_replay"
            if preconditioner_mode == "current_tangent":
                preconditioner_k_ff = current_stiffness[current_free, :][:, current_free].tocsc()
                preconditioner_diag = np.asarray(preconditioner_k_ff.diagonal(), dtype=np.float64)
                tangent_regularization_factor = max(
                    float(matrix_free_global_krylov_tangent_regularization_factor),
                    0.0,
                )
                preconditioner_regularization = tangent_regularization_factor * max(
                    float(np.mean(np.abs(preconditioner_diag))) if preconditioner_diag.size else 0.0,
                    1.0,
                )
                preconditioner_matrix = (
                    preconditioner_k_ff
                    + eye(preconditioner_k_ff.shape[0], format="csc")
                    * preconditioner_regularization
                )
            matrix_free_global_krylov["preconditioner_regularization"] = float(
                preconditioner_regularization
            )

            def _global_hip_residual_backend() -> Any | None:
                nonlocal global_hip_backend, global_hip_backend_error
                if apply_shell_material_tangent:
                    if allow_state_dependent_shell_material_tangent_hip_replay:
                        matrix_free_global_krylov[
                            "state_dependent_shell_material_tangent_hip_replay"
                        ] = True
                        matrix_free_global_krylov[
                            "state_dependent_shell_material_tangent_operator_refresh_backend"
                        ] = "host_shell_operator_refresh"
                    elif not allow_frozen_shell_material_tangent_hip_replay:
                        matrix_free_global_krylov[
                            "batch_replay_backend_disabled_reason"
                        ] = "state_dependent_shell_material_tangent_requires_cpu_batch"
                        return None
                    else:
                        matrix_free_global_krylov[
                            "frozen_shell_material_tangent_hip_replay"
                        ] = True
                        matrix_free_global_krylov[
                            "shell_material_tangent_frozen_from_current_state"
                        ] = True
                if global_batch_backend not in {
                    "hip_full_residual",
                    "hip_full_residual_resident",
                    "rust_hip_full_residual_ffi",
                }:
                    return None
                if global_hip_backend is not None:
                    return global_hip_backend
                try:
                    global_frozen_shell_tangent = None
                    if apply_shell_material_tangent and (
                        allow_frozen_shell_material_tangent_hip_replay
                        or allow_state_dependent_shell_material_tangent_hip_replay
                    ):
                        global_frozen_shell_tangent, _frozen_shell_meta = shell_material_tangent_by_surface_index(
                            node_xyz=node_xyz,
                            u=current_u,
                            elem_type_code=elem_type_code,
                            elem_material_id=elem_material_id,
                            conn_ptr=conn_ptr,
                            conn_idx=conn_idx,
                            material_props=material_props,
                            controlled_probe=False,
                        )
                    shell_stiffness, _shell_meta, _cache_hit = _cached_shell_operator(
                        u=current_u,
                        node_xyz=node_xyz,
                        elem_type_code=elem_type_code,
                        elem_section_id=elem_section_id,
                        elem_material_id=elem_material_id,
                        conn_ptr=conn_ptr,
                        conn_idx=conn_idx,
                        material_props=material_props,
                        plate_thickness_props=plate_thickness_props,
                        include_membrane=True,
                        shell_operator_cache=shell_operator_cache,
                        material_tangent_by_surface_index_mpa=global_frozen_shell_tangent,
                    )
                    backend_cls = (
                        HipFullResidualResidentWorkerBackend
                        if global_batch_backend == "hip_full_residual_resident"
                        else HipFullResidualRustFfiBackend
                        if global_batch_backend == "rust_hip_full_residual_ffi"
                        else HipFullResidualBatchBackend
                    )
                    global_hip_backend = backend_cls.prepare(
                        frame_dofs=frame_force_cache.dofs,
                        frame_stiffness=frame_force_cache.element_stiffness,
                        shell_csr=shell_stiffness.tocsr(),
                        spring_csr=spring_stiffness.tocsr(),
                        f_ext=reference_f_ext,
                        free=base_free_for_krylov,
                        hipcc=current_tangent_residual_row_hipcc,
                        force_rebuild=bool(
                            current_tangent_residual_row_force_rebuild_hip
                        ),
                    )
                except Exception as exc:  # pragma: no cover - recorded in probe JSON
                    global_hip_backend_error = str(exc)
                    matrix_free_global_krylov["batch_replay_backend_error"] = (
                        global_hip_backend_error
                    )
                    return None
                return global_hip_backend

            def _global_hip_replay_required_unavailable(reason: str) -> bool:
                if not global_require_hip_batch_replay:
                    return False
                matrix_free_global_krylov[
                    "hip_batch_replay_required_unavailable"
                ] = True
                matrix_free_global_krylov[
                    "hip_batch_replay_required_unavailable_reason"
                ] = str(reason)
                matrix_free_global_krylov[
                    "cpu_batch_replay_fallback_suppressed"
                ] = True
                return True

            def _evaluate_global_residual_candidate(
                candidate_u: np.ndarray,
                *,
                replay_role: str,
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None:
                nonlocal global_hip_batch_eval_count
                nonlocal global_hip_batch_state_count
                nonlocal global_hip_batch_seconds
                if global_batch_backend in {
                    "hip_full_residual",
                    "hip_full_residual_resident",
                    "rust_hip_full_residual_ffi",
                }:
                    batch_started = time.perf_counter()
                    state_dependent_role = bool(
                        apply_shell_material_tangent
                        and allow_state_dependent_shell_material_tangent_hip_replay
                    )
                    if state_dependent_role:
                        try:
                            (
                                sd_shell_tangent,
                                _sd_shell_meta,
                            ) = shell_material_tangent_by_surface_index(
                                node_xyz=node_xyz,
                                u=candidate_u,
                                elem_type_code=elem_type_code,
                                elem_material_id=elem_material_id,
                                conn_ptr=conn_ptr,
                                conn_idx=conn_idx,
                                material_props=material_props,
                                controlled_probe=False,
                            )
                            shell_stiffness, _shell_meta, _cache_hit = _cached_shell_operator(
                                u=candidate_u,
                                node_xyz=node_xyz,
                                elem_type_code=elem_type_code,
                                elem_section_id=elem_section_id,
                                elem_material_id=elem_material_id,
                                conn_ptr=conn_ptr,
                                conn_idx=conn_idx,
                                material_props=material_props,
                                plate_thickness_props=plate_thickness_props,
                                include_membrane=True,
                                shell_operator_cache=shell_operator_cache,
                                material_tangent_by_surface_index_mpa=sd_shell_tangent,
                            )
                            backend_cls = (
                                HipFullResidualResidentWorkerBackend
                                if global_batch_backend == "hip_full_residual_resident"
                                else HipFullResidualRustFfiBackend
                                if global_batch_backend == "rust_hip_full_residual_ffi"
                                else HipFullResidualBatchBackend
                            )
                            sd_backend = backend_cls.prepare(
                                frame_dofs=frame_force_cache.dofs,
                                frame_stiffness=frame_force_cache.element_stiffness,
                                shell_csr=shell_stiffness.tocsr(),
                                spring_csr=spring_stiffness.tocsr(),
                                f_ext=reference_f_ext,
                                free=base_free_for_krylov,
                                hipcc=current_tangent_residual_row_hipcc,
                                force_rebuild=bool(
                                    current_tangent_residual_row_force_rebuild_hip
                                ),
                            )
                            residual_batch, batch_meta = sd_backend.evaluate(
                                np.asarray([candidate_u], dtype=np.float64),
                                reps=1,
                            )
                            elapsed = float(time.perf_counter() - batch_started)
                            global_hip_batch_eval_count += 1
                            global_hip_batch_state_count += 1
                            global_hip_batch_seconds += elapsed
                            matrix_free_global_krylov[
                                "state_dependent_shell_material_tangent_hip_replay"
                            ] = True
                            matrix_free_global_krylov[
                                "state_dependent_shell_material_tangent_operator_refresh_backend"
                            ] = "host_shell_operator_refresh"
                            meta = {
                                **batch_meta,
                                "residual_batch_backend": global_batch_backend,
                                "hip_full_residual_batch_replay": True,
                                "hip_full_residual_resident_worker": bool(
                                    global_batch_backend
                                    == "hip_full_residual_resident"
                                ),
                                "rust_hip_full_residual_ffi_worker": bool(
                                    global_batch_backend
                                    == "rust_hip_full_residual_ffi"
                                ),
                                "residual_only_assembly": True,
                                "residual_only_free_override": True,
                                "global_krylov_replay_role": str(replay_role),
                                "state_dependent_shell_material_tangent_hip_replay": True,
                                "state_dependent_shell_material_tangent_operator_refresh_backend": (
                                    "host_shell_operator_refresh"
                                ),
                            }
                            rhs = np.asarray(
                                reference_f_ext[base_free_for_krylov],
                                dtype=np.float64,
                            )
                            return (
                                base_free_for_krylov,
                                np.asarray(residual_batch[0], dtype=np.float64),
                                rhs,
                                meta,
                            )
                        except Exception as exc:  # pragma: no cover - recorded in probe JSON
                            matrix_free_global_krylov[
                                "batch_replay_backend_error"
                            ] = str(exc)
                            if _global_hip_replay_required_unavailable(
                                "hip_backend_prepare_or_evaluate_failed_state_dependent"
                            ):
                                return None
                    else:
                        hip_backend = _global_hip_residual_backend()
                        if hip_backend is not None:
                            try:
                                residual_batch, batch_meta = hip_backend.evaluate(
                                    np.asarray([candidate_u], dtype=np.float64),
                                    reps=1,
                                )
                                elapsed = float(time.perf_counter() - batch_started)
                                global_hip_batch_eval_count += 1
                                global_hip_batch_state_count += 1
                                global_hip_batch_seconds += elapsed
                                meta = {
                                    **batch_meta,
                                    "residual_batch_backend": global_batch_backend,
                                    "hip_full_residual_batch_replay": True,
                                    "hip_full_residual_resident_worker": bool(
                                        global_batch_backend
                                        == "hip_full_residual_resident"
                                    ),
                                    "rust_hip_full_residual_ffi_worker": bool(
                                        global_batch_backend
                                        == "rust_hip_full_residual_ffi"
                                    ),
                                    "residual_only_assembly": True,
                                    "residual_only_free_override": True,
                                    "global_krylov_replay_role": str(replay_role),
                                }
                                rhs = np.asarray(
                                    reference_f_ext[base_free_for_krylov],
                                    dtype=np.float64,
                                )
                                return (
                                    base_free_for_krylov,
                                    np.asarray(residual_batch[0], dtype=np.float64),
                                    rhs,
                                    meta,
                                )
                            except Exception as exc:  # pragma: no cover - recorded in probe JSON
                                matrix_free_global_krylov[
                                    "batch_replay_backend_error"
                                ] = str(exc)
                                if _global_hip_replay_required_unavailable(
                                    "hip_backend_evaluate_failed"
                                ):
                                    return None
                        elif _global_hip_replay_required_unavailable(
                            "hip_backend_prepare_failed_or_disabled"
                        ):
                            return None
                (
                    _candidate_k,
                    _candidate_f,
                    candidate_free,
                    candidate_residual,
                    candidate_rhs,
                    candidate_meta,
                ) = assemble_residual(
                    candidate_u,
                    external_load_override=reference_f_ext,
                    residual_only=True,
                    free_override=base_free_for_krylov,
                )
                meta = candidate_meta if isinstance(candidate_meta, dict) else {}
                return (
                    np.asarray(candidate_free, dtype=np.int64),
                    np.asarray(candidate_residual, dtype=np.float64),
                    np.asarray(candidate_rhs, dtype=np.float64),
                    meta,
                )

            def _evaluate_global_residual_candidates(
                candidate_us: list[np.ndarray],
                *,
                replay_role: str,
            ) -> list[
                tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None
            ]:
                nonlocal global_hip_batch_eval_count
                nonlocal global_hip_batch_state_count
                nonlocal global_hip_batch_seconds
                if not candidate_us:
                    return []
                state_dependent_role = bool(
                    apply_shell_material_tangent
                    and allow_state_dependent_shell_material_tangent_hip_replay
                )
                if (
                    not state_dependent_role
                    and global_batch_backend
                    in {
                        "hip_full_residual",
                        "hip_full_residual_resident",
                        "rust_hip_full_residual_ffi",
                    }
                ):
                    batch_started = time.perf_counter()
                    hip_backend = _global_hip_residual_backend()
                    if hip_backend is not None:
                        try:
                            state_batch = np.asarray(candidate_us, dtype=np.float64)
                            residual_batch, batch_meta = hip_backend.evaluate(
                                state_batch,
                                reps=1,
                            )
                            elapsed = float(time.perf_counter() - batch_started)
                            global_hip_batch_eval_count += 1
                            global_hip_batch_state_count += int(state_batch.shape[0])
                            global_hip_batch_seconds += elapsed
                            rhs = np.asarray(
                                reference_f_ext[base_free_for_krylov],
                                dtype=np.float64,
                            )
                            results: list[
                                tuple[
                                    np.ndarray,
                                    np.ndarray,
                                    np.ndarray,
                                    dict[str, Any],
                                ]
                                | None
                            ] = []
                            for batch_index, residual in enumerate(residual_batch):
                                meta = {
                                    **batch_meta,
                                    "residual_batch_backend": global_batch_backend,
                                    "hip_full_residual_batch_replay": True,
                                    "hip_full_residual_resident_worker": bool(
                                        global_batch_backend
                                        == "hip_full_residual_resident"
                                    ),
                                    "rust_hip_full_residual_ffi_worker": bool(
                                        global_batch_backend
                                        == "rust_hip_full_residual_ffi"
                                    ),
                                    "residual_only_assembly": True,
                                    "residual_only_free_override": True,
                                    "global_krylov_replay_role": str(replay_role),
                                    "hip_batch_group_size": int(state_batch.shape[0]),
                                    "hip_batch_group_index": int(batch_index),
                                }
                                results.append(
                                    (
                                        base_free_for_krylov,
                                        np.asarray(residual, dtype=np.float64),
                                        rhs,
                                        meta,
                                    )
                                )
                            return results
                        except Exception as exc:  # pragma: no cover - recorded in probe JSON
                            matrix_free_global_krylov[
                                "batch_replay_backend_error"
                            ] = str(exc)
                            if _global_hip_replay_required_unavailable(
                                "hip_backend_batch_evaluate_failed"
                            ):
                                return [None for _ in candidate_us]
                    elif _global_hip_replay_required_unavailable(
                        "hip_backend_prepare_failed_or_disabled"
                    ):
                        return [None for _ in candidate_us]
                return [
                    _evaluate_global_residual_candidate(
                        candidate_u,
                        replay_role=replay_role,
                    )
                    for candidate_u in candidate_us
                ]

            if global_require_hip_batch_replay:
                base_replay = _evaluate_global_residual_candidate(
                    base_u_for_krylov,
                    replay_role="base",
                )
                if base_replay is None:
                    matrix_free_global_krylov[
                        "base_residual_hip_replay_required_unavailable"
                    ] = True
                    matrix_free_global_krylov[
                        "base_residual_source"
                    ] = "unavailable_required_hip_batch_replay"
                    matrix_free_global_krylov[
                        "cpu_base_residual_for_krylov_suppressed"
                    ] = True
                    base_residual_for_krylov = np.zeros_like(
                        base_residual_for_krylov
                    )
                    previous_residual_inf = 0.0
                else:
                    (
                        base_replay_free,
                        base_replay_residual,
                        _base_replay_rhs,
                        base_replay_meta,
                    ) = base_replay
                    base_free_is_stable = bool(
                        base_replay_free.shape == base_free_for_krylov.shape
                        and np.array_equal(base_replay_free, base_free_for_krylov)
                    )
                    matrix_free_global_krylov[
                        "base_residual_hip_replay_free_dof_set_stable"
                    ] = base_free_is_stable
                    matrix_free_global_krylov["base_residual_source"] = (
                        "hip_full_residual_batch_replay"
                        if base_free_is_stable
                        else "unstable_required_hip_batch_replay"
                    )
                    matrix_free_global_krylov[
                        "base_residual_hip_full_residual_batch_replay"
                    ] = bool(
                        isinstance(base_replay_meta, dict)
                        and base_replay_meta.get("hip_full_residual_batch_replay")
                    )
                    if base_free_is_stable:
                        base_residual_for_krylov = np.asarray(
                            base_replay_residual,
                            dtype=np.float64,
                        )
                        previous_residual_inf = (
                            float(np.max(np.abs(base_residual_for_krylov)))
                            if base_residual_for_krylov.size
                            else 0.0
                        )
                    else:
                        _global_hip_replay_required_unavailable(
                            "hip_base_replay_free_dof_set_changed"
                        )
                        base_residual_for_krylov = np.zeros_like(
                            base_residual_for_krylov
                        )
                        previous_residual_inf = 0.0
            else:
                matrix_free_global_krylov[
                    "base_residual_source"
                ] = "cpu_direct_residual_assembly"
            if scaling_mode == "residual_diagonal_displacement":
                row_scale = 1.0 / np.maximum(
                    np.abs(base_residual_for_krylov),
                    residual_scale_floor,
                )
            else:
                row_scale = np.ones(n_free, dtype=np.float64)
            matrix_free_global_krylov["base_residual_inf_n_for_krylov"] = (
                float(np.max(np.abs(base_residual_for_krylov)))
                if base_residual_for_krylov.size
                else 0.0
            )
            matrix_free_global_krylov["row_scale_inf"] = (
                float(np.max(np.abs(row_scale))) if row_scale.size else 0.0
            )
            matrix_free_global_krylov["row_scale_min"] = (
                float(np.min(np.abs(row_scale))) if row_scale.size else 0.0
            )

            def _global_residual_jvp_physical(vector: np.ndarray) -> np.ndarray:
                nonlocal matvec_count, unstable_probe_count
                nonlocal residual_only_matvec_count, full_assembly_matvec_count
                matvec_count += 1
                direction = np.asarray(vector, dtype=np.float64)
                direction_inf = float(np.max(np.abs(direction))) if direction.size else 0.0
                if direction_inf <= 1.0e-30:
                    return np.zeros_like(base_residual_for_krylov)
                scale = probe_epsilon / direction_inf
                if probe_max_step > 0.0:
                    scale = min(scale, probe_max_step / direction_inf)

                def _probe_state(sign: float) -> np.ndarray:
                    probe_u = base_u_for_krylov.copy()
                    probe_u[base_free_for_krylov] += float(sign) * scale * direction
                    return probe_u

                def _probe_residual_from_result(
                    probe_result: tuple[
                        np.ndarray,
                        np.ndarray,
                        np.ndarray,
                        dict[str, Any],
                    ]
                    | None,
                ) -> tuple[np.ndarray, np.ndarray, bool, float, dict[str, Any]]:
                    if probe_result is None:
                        matrix_free_global_krylov[
                            "matvec_replay_required_unavailable"
                        ] = True
                        return (
                            base_free_for_krylov,
                            base_residual_for_krylov.copy(),
                            False,
                            float(previous_residual_inf),
                            {},
                        )
                    probe_free, probe_residual, _probe_rhs, _probe_meta = probe_result
                    probe_meta = _probe_meta if isinstance(_probe_meta, dict) else {}
                    used_residual_only = bool(
                        probe_meta.get("residual_only_assembly")
                    )
                    probe_residual_inf = (
                        float(np.max(np.abs(probe_residual)))
                        if probe_residual.size
                        else 0.0
                    )
                    return (
                        np.asarray(probe_free, dtype=np.int64),
                        np.asarray(probe_residual, dtype=np.float64),
                        used_residual_only,
                        probe_residual_inf,
                        probe_meta,
                    )

                probe_signs = [1.0]
                if global_difference_scheme == "central":
                    probe_signs.append(-1.0)
                probe_results = _evaluate_global_residual_candidates(
                    [_probe_state(sign) for sign in probe_signs],
                    replay_role="matvec",
                )
                (
                    probe_free,
                    probe_residual,
                    used_residual_only,
                    probe_residual_inf,
                    probe_meta,
                ) = _probe_residual_from_result(probe_results[0] if probe_results else None)
                if used_residual_only:
                    residual_only_matvec_count += 1
                else:
                    full_assembly_matvec_count += 1
                free_is_stable = bool(
                    probe_free.shape == base_free_for_krylov.shape
                    and np.array_equal(probe_free, base_free_for_krylov)
                )
                row = {
                    "matvec_index": int(matvec_count),
                    "difference_scheme": global_difference_scheme,
                    "direction_inf_m": float(direction_inf),
                    "effective_probe_scale": float(scale),
                    "probe_step_inf_m": float(scale * direction_inf),
                    "free_dof_set_stable": free_is_stable,
                    "residual_only_assembly": bool(used_residual_only),
                    "probe_direct_residual_inf_n": probe_residual_inf,
                    "hip_full_residual_batch_replay": bool(
                        probe_meta.get("hip_full_residual_batch_replay")
                    ),
                    "hip_batch_group_size": (
                        int(probe_meta.get("hip_batch_group_size"))
                        if probe_meta.get("hip_batch_group_size") is not None
                        else None
                    ),
                    "hip_batch_group_index": (
                        int(probe_meta.get("hip_batch_group_index"))
                        if probe_meta.get("hip_batch_group_index") is not None
                        else None
                    ),
                }
                if global_difference_scheme == "central" and free_is_stable:
                    (
                        minus_free,
                        minus_residual,
                        minus_used_residual_only,
                        minus_residual_inf,
                        minus_probe_meta,
                    ) = _probe_residual_from_result(
                        probe_results[1] if len(probe_results) > 1 else None
                    )
                    if minus_used_residual_only:
                        residual_only_matvec_count += 1
                    else:
                        full_assembly_matvec_count += 1
                    minus_free_is_stable = bool(
                        minus_free.shape == base_free_for_krylov.shape
                        and np.array_equal(minus_free, base_free_for_krylov)
                    )
                    free_is_stable = bool(free_is_stable and minus_free_is_stable)
                    row.update(
                        {
                            "minus_free_dof_set_stable": minus_free_is_stable,
                            "minus_residual_only_assembly": bool(
                                minus_used_residual_only
                            ),
                            "minus_probe_direct_residual_inf_n": minus_residual_inf,
                            "minus_hip_full_residual_batch_replay": bool(
                                minus_probe_meta.get("hip_full_residual_batch_replay")
                            ),
                            "minus_hip_batch_group_size": (
                                int(minus_probe_meta.get("hip_batch_group_size"))
                                if minus_probe_meta.get("hip_batch_group_size")
                                is not None
                                else None
                            ),
                            "minus_hip_batch_group_index": (
                                int(minus_probe_meta.get("hip_batch_group_index"))
                                if minus_probe_meta.get("hip_batch_group_index")
                                is not None
                                else None
                            ),
                        }
                    )
                if not free_is_stable:
                    unstable_probe_count += 1
                    row["reason"] = "free_dof_set_changed"
                    jvp_rows.append(row)
                    return np.zeros_like(base_residual_for_krylov)
                if global_difference_scheme == "central":
                    jvp = (probe_residual - minus_residual) / (2.0 * scale)
                else:
                    jvp = (probe_residual - base_residual_for_krylov) / scale
                row["jacobian_action_inf_n"] = (
                    float(np.max(np.abs(jvp))) if jvp.size else 0.0
                )
                row["jacobian_action_l2_n"] = float(np.linalg.norm(jvp)) if jvp.size else 0.0
                jvp_rows.append(row)
                return jvp

            def _right_preconditioned_direction(vector: np.ndarray) -> np.ndarray:
                nonlocal preconditioner_solve_count, preconditioner_solve_seconds
                scaled_direction = np.asarray(vector, dtype=np.float64)
                preconditioner_input = column_scale * scaled_direction
                if preconditioner_mode != "current_tangent":
                    return preconditioner_input
                assert preconditioner_matrix is not None
                solve_started = time.perf_counter()
                physical_direction = np.asarray(
                    spsolve(preconditioner_matrix, preconditioner_input),
                    dtype=np.float64,
                )
                preconditioner_solve_seconds += time.perf_counter() - solve_started
                preconditioner_solve_count += 1
                return physical_direction

            def _global_scaled_matvec(vector: np.ndarray) -> np.ndarray:
                physical_direction = _right_preconditioned_direction(vector)
                return row_scale * _global_residual_jvp_physical(physical_direction)

            host_krylov_solver_closure_blocked = bool(
                global_require_hip_batch_replay
                and global_linear_solver_backend == "scipy_host_gmres"
            )
            hip_krylov_solver_required_unavailable = False
            matrix_free_global_krylov["host_krylov_solver_used"] = bool(
                global_linear_solver_backend == "scipy_host_gmres"
            )
            matrix_free_global_krylov["hip_krylov_solver_used"] = False
            matrix_free_global_krylov["host_krylov_solver_closure_blocked"] = (
                host_krylov_solver_closure_blocked
            )
            if host_krylov_solver_closure_blocked:
                matrix_free_global_krylov[
                    "host_krylov_solver_closure_blocker"
                ] = "rocm_hip_krylov_solver_required_for_closure"
            operator = LinearOperator(
                (n_free, n_free),
                matvec=_global_scaled_matvec,
                dtype=np.float64,
            )
            scaled_rhs = -row_scale * base_residual_for_krylov
            solve_started = time.perf_counter()
            if global_linear_solver_backend == "torch_hip_gmres":
                (
                    correction_free_scaled,
                    krylov_info,
                    hip_solver_meta,
                ) = _torch_hip_gmres_once(
                    _global_scaled_matvec,
                    scaled_rhs,
                    restart=max(1, int(matrix_free_global_krylov_max_iterations)),
                )
                matrix_free_global_krylov.update(hip_solver_meta)
                if not bool(hip_solver_meta.get("hip_krylov_solver_used")):
                    hip_krylov_solver_required_unavailable = True
                    matrix_free_global_krylov[
                        "hip_krylov_solver_required_unavailable"
                    ] = True
                    matrix_free_global_krylov[
                        "hip_krylov_solver_required_unavailable_reason"
                    ] = str(
                        hip_solver_meta.get(
                            "unavailable_reason",
                            "torch_hip_gmres_unavailable",
                        )
                    )
                    matrix_free_global_krylov[
                        "cpu_linear_solver_fallback_suppressed"
                    ] = True
                matrix_free_global_krylov["host_krylov_solver_used"] = False
                matrix_free_global_krylov["hip_krylov_solver_used"] = bool(
                    hip_solver_meta.get("hip_krylov_solver_used")
                )
            else:
                try:
                    correction_free_scaled, krylov_info = gmres(
                        operator,
                        scaled_rhs,
                        restart=max(1, int(matrix_free_global_krylov_max_iterations)),
                        maxiter=1,
                        rtol=0.0,
                        atol=0.0,
                    )
                except TypeError:
                    correction_free_scaled, krylov_info = gmres(
                        operator,
                        scaled_rhs,
                        restart=max(1, int(matrix_free_global_krylov_max_iterations)),
                        maxiter=1,
                        tol=0.0,
                    )
            solve_seconds = time.perf_counter() - solve_started
            correction_free_scaled = np.asarray(correction_free_scaled, dtype=np.float64)
            correction_free = _right_preconditioned_direction(correction_free_scaled)
            correction = np.zeros_like(current_u)
            correction[base_free_for_krylov] = correction_free
            correction_inf = (
                float(np.max(np.abs(correction_free))) if correction_free.size else 0.0
            )
            correction_scaled_inf = (
                float(np.max(np.abs(correction_free_scaled)))
                if correction_free_scaled.size
                else 0.0
            )
            current_max_abs = max(
                float(np.max(np.abs(current_u))) if current_u.size else 0.0,
                1.0e-9,
            )
            gate_limited_alpha = (
                0.95
                * float(relative_increment_tolerance)
                * current_max_abs
                / correction_inf
                if correction_inf > 0.0
                else 0.0
            )
            alpha_rows = _unique_positive_alphas(
                [
                    ("matrix_free_global_krylov", float(alpha))
                    for alpha in matrix_free_global_krylov_alpha_values
                ]
                + [
                    ("matrix_free_global_krylov_gate_limited", gate_limited_alpha),
                    ("matrix_free_global_krylov_half_gate_limited", 0.5 * gate_limited_alpha),
                ],
                min_alpha=1.0e-10,
                max_alpha=max_global_krylov_alpha,
            )
            if hip_krylov_solver_required_unavailable:
                alpha_rows = []
            if matrix_free_global_krylov_allow_negative_alphas:
                alpha_rows.extend(
                    (f"{source}_negative", -float(alpha))
                    for source, alpha in list(alpha_rows)
                )
            trial_rows: list[dict[str, Any]] = []
            trial_vectors: list[np.ndarray] = []
            trial_specs = [
                (str(alpha_source), float(alpha), current_u + float(alpha) * correction)
                for alpha_source, alpha in alpha_rows
            ]
            trial_results = _evaluate_global_residual_candidates(
                [candidate_u for _alpha_source, _alpha, candidate_u in trial_specs],
                replay_role="trial",
            )
            for (alpha_source, alpha, candidate_u), candidate_result in zip(
                trial_specs,
                trial_results,
            ):
                if candidate_result is None:
                    continue
                _free, candidate_residual, candidate_rhs, candidate_meta = (
                    candidate_result
                )
                used_residual_only = bool(
                    isinstance(candidate_meta, dict)
                    and candidate_meta.get("residual_only_assembly")
                )
                if used_residual_only:
                    residual_only_trial_count += 1
                else:
                    full_assembly_trial_count += 1
                residual_inf_residual_only = (
                    float(np.max(np.abs(candidate_residual)))
                    if candidate_residual.size
                    else 0.0
                )
                residual_inf = residual_inf_residual_only
                rhs_for_trial = candidate_rhs
                full_replay_meta: dict[str, Any] = {}
                if (
                    effective_full_assembly_trial_replay
                ):
                    (
                        _full_k,
                        _full_f,
                        full_free,
                        full_residual,
                        full_rhs,
                        full_meta,
                    ) = assemble_residual(
                        candidate_u,
                        external_load_override=reference_f_ext,
                    )
                    full_assembly_trial_replay_count += 1
                    full_free_is_stable = bool(
                        full_free.shape == base_free_for_krylov.shape
                        and np.array_equal(full_free, base_free_for_krylov)
                    )
                    full_residual_inf = (
                        float(np.max(np.abs(full_residual))) if full_residual.size else 0.0
                    )
                    full_replay_meta = {
                        "full_assembly_trial_replay": True,
                        "full_assembly_free_dof_set_stable": full_free_is_stable,
                        "full_assembly_direct_residual_inf_n": full_residual_inf,
                        "full_assembly_free_dof_count": int(full_free.size),
                        "full_assembly_residual_only_assembly": bool(
                            isinstance(full_meta, dict)
                            and full_meta.get("residual_only_assembly")
                        ),
                    }
                    if full_free_is_stable:
                        residual_inf = full_residual_inf
                        rhs_for_trial = full_rhs
                    else:
                        residual_inf = max(residual_inf_residual_only, full_residual_inf)
                improvement_inf = previous_residual_inf - residual_inf
                relative_improvement = improvement_inf / max(previous_residual_inf, 1.0e-30)
                increment = (
                    float(np.max(np.abs(candidate_u - current_u)))
                    if candidate_u.size
                    else 0.0
                )
                max_abs = max(
                    float(np.max(np.abs(candidate_u))) if candidate_u.size else current_max_abs,
                    1.0e-9,
                )
                metrics = _translation_metrics(candidate_u, node_xyz)
                row = {
                    "alpha_source": str(alpha_source),
                    "alpha": float(alpha),
                    "residual_only_assembly": bool(used_residual_only),
                    "trial_residual_source": (
                        "full_assembly_replay"
                        if effective_full_assembly_trial_replay
                        else "residual_only"
                    ),
                    "residual_only_direct_residual_inf_n": residual_inf_residual_only,
                    "residual_batch_backend": str(
                        candidate_meta.get("residual_batch_backend")
                        if isinstance(candidate_meta, dict)
                        else ""
                    ),
                    "hip_full_residual_batch_replay": bool(
                        isinstance(candidate_meta, dict)
                        and candidate_meta.get("hip_full_residual_batch_replay")
                    ),
                    "hip_batch_group_size": (
                        int(candidate_meta.get("hip_batch_group_size"))
                        if isinstance(candidate_meta, dict)
                        and candidate_meta.get("hip_batch_group_size") is not None
                        else None
                    ),
                    "hip_batch_group_index": (
                        int(candidate_meta.get("hip_batch_group_index"))
                        if isinstance(candidate_meta, dict)
                        and candidate_meta.get("hip_batch_group_index") is not None
                        else None
                    ),
                    **full_replay_meta,
                    "direct_residual_inf_n": residual_inf,
                    "improvement_inf_n": float(improvement_inf),
                    "relative_improvement": float(relative_improvement),
                    "direct_relative_residual_inf": residual_inf
                    / max(
                        float(np.max(np.abs(rhs_for_trial))) if rhs_for_trial.size else 0.0,
                        1.0,
                    ),
                    "relative_increment": increment / max_abs,
                    "max_increment_m": increment,
                    "max_translation_m": metrics["max_translation_m"],
                    "residual_gate_passed": bool(residual_inf <= residual_tolerance_n),
                    "relative_increment_gate_passed": bool(
                        increment / max_abs <= relative_increment_tolerance
                    ),
                }
                trial_rows.append(row)
                trial_vectors.append(candidate_u)
                candidate_rows.append(row)
            best_trial_index: int | None = None
            best_trial: dict[str, Any] | None = None
            if trial_rows:
                best_trial_index, best_trial = min(
                    enumerate(trial_rows),
                    key=lambda item: float(item[1]["direct_residual_inf_n"]),
                )
            gate_eligible_trials = [
                (index, row)
                for index, row in enumerate(trial_rows)
                if bool(row.get("relative_increment_gate_passed"))
                and bool(row.get("full_assembly_free_dof_set_stable", True))
                and not host_krylov_solver_closure_blocked
                and float(row["direct_residual_inf_n"]) < previous_residual_inf
                and float(row.get("relative_improvement", 0.0))
                >= max(float(matrix_free_global_krylov_min_relative_improvement), 0.0)
            ]
            gate_eligible_without_floor = [
                (index, row)
                for index, row in enumerate(trial_rows)
                if bool(row.get("relative_increment_gate_passed"))
                and bool(row.get("full_assembly_free_dof_set_stable", True))
                and not host_krylov_solver_closure_blocked
                and float(row["direct_residual_inf_n"]) < previous_residual_inf
            ]
            best_gate_trial_index: int | None = None
            best_gate_trial: dict[str, Any] | None = None
            if gate_eligible_trials:
                best_gate_trial_index, best_gate_trial = min(
                    gate_eligible_trials,
                    key=lambda item: float(item[1]["direct_residual_inf_n"]),
                )
            promoted = best_gate_trial_index is not None
            if promoted:
                current_u = trial_vectors[int(best_gate_trial_index)]
                hip_acceptance_refresh_used = False
                if global_require_hip_batch_replay:
                    accepted_replay = _evaluate_global_residual_candidate(
                        current_u,
                        replay_role="accepted_refresh",
                    )
                    if accepted_replay is not None:
                        (
                            accepted_free,
                            accepted_residual,
                            accepted_rhs,
                            accepted_meta,
                        ) = accepted_replay
                        if _can_use_hip_acceptance_residual_refresh(
                            accepted_meta if isinstance(accepted_meta, dict) else {},
                            require_hip_batch_replay=global_require_hip_batch_replay,
                        ):
                            hip_acceptance_refresh_used = True
                            current_free = np.asarray(accepted_free, dtype=np.int64)
                            current_residual = np.asarray(accepted_residual, dtype=np.float64)
                            current_rhs = np.asarray(accepted_rhs, dtype=np.float64)
                            matrix_free_global_krylov[
                                "accepted_state_refresh_backend"
                            ] = str(
                                accepted_meta.get(
                                    "residual_batch_backend",
                                    "hip_batch_replay",
                                )
                            ) if isinstance(accepted_meta, dict) else "hip_batch_replay"
                            matrix_free_global_krylov[
                                "accepted_state_refresh_hip_used"
                            ] = True
                            matrix_free_global_krylov[
                                "accepted_state_refresh_cpu_used"
                            ] = False
                            matrix_free_global_krylov[
                                "accepted_state_refresh_tangent_note"
                            ] = (
                                "tangent_stiffness_not_refreshed_from_hip_acceptance_path"
                            )
                            if enable_current_tangent_residual_row_correction:
                                if row_hip_fd_tangent_refresh_configured:
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_backend"
                                    ] = GLOBAL_TANGENT_REFRESH_DEFERRED_BACKEND
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_cpu_used"
                                    ] = False
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_deferred_to"
                                    ] = GLOBAL_TANGENT_REFRESH_DEFERRED_TO_ROW
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_deferred_reason"
                                    ] = (
                                        "row_target_finite_difference_hip_batch_replay_configured"
                                    )
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_closure_blocked"
                                    ] = True
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_closure_blocker"
                                    ] = GLOBAL_TANGENT_REFRESH_DEFERRED_BLOCKER
                                else:
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_backend"
                                    ] = "cpu_full_assembly"
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_cpu_used"
                                    ] = True
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_closure_blocked"
                                    ] = True
                                    matrix_free_global_krylov[
                                        "accepted_state_tangent_refresh_closure_blocker"
                                    ] = (
                                        "rocm_hip_acceptance_tangent_refresh_required_for_closure"
                                    )
                                    (
                                        current_stiffness,
                                        _current_f_ext,
                                        _cpu_free,
                                        _cpu_residual,
                                        _cpu_rhs,
                                        _current_meta,
                                    ) = assemble_residual(
                                        current_u, external_load_override=reference_f_ext
                                    )
                            else:
                                matrix_free_global_krylov[
                                    "accepted_state_tangent_refresh_backend"
                                ] = "not_refreshed_not_needed_after_global_krylov"
                                matrix_free_global_krylov[
                                    "accepted_state_tangent_refresh_cpu_used"
                                ] = False
                                matrix_free_global_krylov[
                                    "accepted_state_tangent_refresh_skipped_reason"
                                ] = (
                                    "no_downstream_current_tangent_row_correction"
                                )
                    else:
                        matrix_free_global_krylov[
                            "accepted_state_refresh_hip_unavailable"
                        ] = True
                if not hip_acceptance_refresh_used:
                    matrix_free_global_krylov[
                        "accepted_state_refresh_backend"
                    ] = "cpu_full_assembly"
                    matrix_free_global_krylov["accepted_state_refresh_cpu_used"] = True
                    if global_require_hip_batch_replay:
                        matrix_free_global_krylov[
                            "accepted_state_refresh_closure_blocked"
                        ] = True
                        matrix_free_global_krylov[
                            "accepted_state_refresh_closure_blocker"
                        ] = (
                            "rocm_hip_acceptance_refresh_required_for_closure"
                        )
                    (
                        current_stiffness,
                        _current_f_ext,
                        current_free,
                        current_residual,
                        current_rhs,
                        _current_meta,
                    ) = assemble_residual(
                        current_u, external_load_override=reference_f_ext
                    )
                accepted_state_history.append(np.asarray(current_u, dtype=np.float64).copy())
                accepted_residual_history.append(np.asarray(current_residual, dtype=np.float64).copy())
            if best_gate_trial is not None:
                stop_reason = "accepted"
            elif gate_eligible_without_floor:
                stop_reason = "relative_improvement_floor_not_met"
            elif best_trial is not None and float(best_trial["direct_residual_inf_n"]) < previous_residual_inf:
                stop_reason = "no_gate_eligible_residual_descent"
            elif best_trial is not None:
                stop_reason = "no_residual_descent"
            elif hip_krylov_solver_required_unavailable:
                stop_reason = "rocm_hip_krylov_solver_unavailable"
            else:
                stop_reason = "trial_candidate_unavailable"
            matrix_free_global_krylov.update(
                {
                    "accepted": bool(promoted),
                    "promoted_to_final_state": bool(promoted),
                    "krylov_info": int(krylov_info),
                    "linear_solve_seconds": float(solve_seconds),
                    "preconditioner_solve_count": int(preconditioner_solve_count),
                    "preconditioner_solve_seconds": float(preconditioner_solve_seconds),
                    "residual_only_matvec_count": int(residual_only_matvec_count),
                    "full_assembly_matvec_count": int(full_assembly_matvec_count),
                    "residual_only_trial_count": int(residual_only_trial_count),
                    "full_assembly_trial_count": int(full_assembly_trial_count),
                    "full_assembly_trial_replay_count": int(
                        full_assembly_trial_replay_count
                    ),
                    "hip_batch_eval_count": int(global_hip_batch_eval_count),
                    "hip_batch_state_count": int(global_hip_batch_state_count),
                    "hip_batch_seconds": float(global_hip_batch_seconds),
                    "correction_inf_m": correction_inf,
                    "correction_scaled_inf": correction_scaled_inf,
                    "gate_limited_alpha": float(gate_limited_alpha),
                    "matvec_count": int(matvec_count),
                    "unstable_free_dof_probe_count": int(unstable_probe_count),
                    "jvp_rows": jvp_rows,
                    "trial_rows": trial_rows,
                    "best_candidate": best_trial,
                    "best_gate_eligible_candidate": best_gate_trial,
                    "stop_reason": stop_reason,
                    "residual_descent": bool(
                        best_trial
                        and float(best_trial["direct_residual_inf_n"]) < previous_residual_inf
                    ),
                }
            )

        current_tangent_residual_row_correction: dict[str, Any] = {
            "enabled": bool(enable_current_tangent_residual_row_correction),
            "attempted": False,
            "accepted": False,
            "promoted_to_final_state": False,
            "promotion_count": 0,
            "max_promotions": int(max_current_tangent_residual_row_corrections),
            "minimum_relative_improvement": float(
                max(current_tangent_residual_row_min_relative_improvement, 0.0)
            ),
            "target_row_counts": [int(value) for value in current_tangent_residual_row_target_counts],
            "target_mode": str(current_tangent_residual_row_target_mode),
            "frontier_component_scale_mode": str(
                current_tangent_residual_row_frontier_component_scale_mode
            ),
            "element_neighbor_depth": int(
                current_tangent_residual_row_element_neighbor_depth
            ),
            "support_column_counts": [
                int(value) for value in current_tangent_residual_row_support_column_counts
            ],
            "support_expansion_depth": int(current_tangent_residual_row_support_expansion_depth),
            "support_selection": str(current_tangent_residual_row_support_selection),
            "node_block_support": bool(current_tangent_residual_row_node_block_support),
            "jacobian_mode": str(current_tangent_residual_row_jacobian_mode),
            "finite_difference_epsilon": float(current_tangent_residual_row_fd_epsilon),
            "finite_difference_max_support_columns": int(
                current_tangent_residual_row_fd_max_support_columns
            ),
            "ridge_factor": float(current_tangent_residual_row_ridge_factor),
            "svd_relative_cutoff": float(
                current_tangent_residual_row_svd_relative_cutoff
            ),
            "svd_max_condition": float(
                current_tangent_residual_row_svd_max_condition
            ),
            "directional_probe_alpha": float(
                current_tangent_residual_row_directional_probe_alpha
            ),
            "use_residual_only_assembly": bool(
                current_tangent_residual_row_use_residual_only_assembly
            ),
            "batch_alpha_replay": bool(
                current_tangent_residual_row_batch_alpha_replay
            ),
            "batch_fd_replay": bool(current_tangent_residual_row_batch_fd_replay),
            "batch_fd_replay_chunk_size": int(
                current_tangent_residual_row_batch_fd_replay_chunk_size
            ),
            "allow_negative_alphas": bool(
                current_tangent_residual_row_allow_negative_alphas
            ),
            "residual_only_eval_count": 0,
            "full_assembly_eval_count": 0,
            "batch_alpha_replay_batch_count": 0,
            "batch_alpha_replay_state_count": 0,
            "batch_alpha_replay_seconds": 0.0,
            "batch_fd_replay_batch_count": 0,
            "batch_fd_replay_state_count": 0,
            "batch_fd_replay_seconds": 0.0,
            "configured_alpha_values": [
                float(value)
                for value in current_tangent_residual_row_alpha_values
                if float(value) > 0.0
            ],
            "stop_reason": "not_attempted",
            "passes": [],
            "trial_rows": [],
        }
        if (
            apply_shell_material_tangent
            and allow_state_dependent_shell_material_tangent_hip_replay
            and row_batch_backend in {
                "hip_full_residual",
                "hip_full_residual_resident",
                "rust_hip_full_residual_ffi",
            }
        ):
            current_tangent_residual_row_correction[
                "state_dependent_shell_material_tangent_hip_replay"
            ] = True
            current_tangent_residual_row_correction[
                "state_dependent_shell_material_tangent_operator_refresh_backend"
            ] = "host_shell_operator_refresh"
        if enable_current_tangent_residual_row_correction and current_residual.size:
            pass_rows: list[dict[str, Any]] = []
            all_trial_rows: list[dict[str, Any]] = []
            all_gate_candidates: list[dict[str, Any]] = []
            promotion_count = 0
            max_row_promotions = max(int(max_current_tangent_residual_row_corrections), 0)
            min_row_relative_improvement = max(
                float(current_tangent_residual_row_min_relative_improvement), 0.0
            )
            target_mode = str(current_tangent_residual_row_target_mode).strip()
            if target_mode not in {
                "largest_rows",
                "residual_node_blocks",
                "residual_element_blocks",
                "residual_frame_element_blocks",
                "residual_shell_element_blocks",
                "residual_shell_bending_drilling_rows",
                "residual_shell_normal_rows",
                "residual_shell_geometry_normal_rows",
                "residual_shell_geometry_normal_bending_rows",
                "frontier_component_rows",
                "current_component_rows",
            }:
                target_mode = "largest_rows"
            current_tangent_residual_row_correction["target_mode"] = target_mode
            frontier_component_rows = _load_frontier_component_top_rows(
                current_tangent_residual_row_frontier_probe_json
            )
            current_tangent_residual_row_correction[
                "frontier_component_probe_json"
            ] = (
                str(current_tangent_residual_row_frontier_probe_json)
                if current_tangent_residual_row_frontier_probe_json is not None
                else None
            )
            current_tangent_residual_row_correction[
                "frontier_component_row_count"
            ] = int(len(frontier_component_rows))
            frontier_component_scale_mode = str(
                current_tangent_residual_row_frontier_component_scale_mode
            ).strip()
            if frontier_component_scale_mode not in {
                "none",
                "dominant_component_magnitude",
                "total_component_magnitude",
            }:
                frontier_component_scale_mode = "none"
            current_tangent_residual_row_correction[
                "frontier_component_scale_mode"
            ] = frontier_component_scale_mode
            element_neighbor_depth = max(
                int(current_tangent_residual_row_element_neighbor_depth),
                0,
            )
            current_tangent_residual_row_correction["element_neighbor_depth"] = (
                element_neighbor_depth
            )
            support_selection_mode = str(current_tangent_residual_row_support_selection).strip()
            if support_selection_mode not in {
                "row_strongest",
                "residual_weighted",
                "target_rows",
            }:
                support_selection_mode = "row_strongest"
            jacobian_mode = str(current_tangent_residual_row_jacobian_mode).strip()
            if jacobian_mode not in {"current_tangent", "finite_difference"}:
                jacobian_mode = "current_tangent"
            if support_selection_mode == "target_rows" and jacobian_mode != "finite_difference":
                current_tangent_residual_row_correction[
                    "support_selection_disabled_reason"
                ] = "target_rows_requires_finite_difference_jacobian"
                support_selection_mode = "row_strongest"
            current_tangent_residual_row_correction["support_selection"] = support_selection_mode
            current_tangent_residual_row_correction["jacobian_mode"] = jacobian_mode
            fd_epsilon_base = max(float(current_tangent_residual_row_fd_epsilon), 1.0e-12)
            fd_max_support_columns = max(
                int(current_tangent_residual_row_fd_max_support_columns),
                0,
            )
            row_ridge_factor = max(float(current_tangent_residual_row_ridge_factor), 0.0)
            row_svd_relative_cutoff = max(
                float(current_tangent_residual_row_svd_relative_cutoff),
                0.0,
            )
            row_svd_max_condition = max(
                float(current_tangent_residual_row_svd_max_condition),
                0.0,
            )
            row_svd_truncation_enabled = bool(
                row_svd_relative_cutoff > 0.0 or row_svd_max_condition > 0.0
            )
            use_row_residual_only = bool(
                current_tangent_residual_row_use_residual_only_assembly
            )
            row_batch_alpha_replay_requested = bool(
                current_tangent_residual_row_batch_alpha_replay
            )
            row_per_state_replay_requested = bool(
                current_tangent_residual_row_per_state_batch_replay
            )
            row_per_state_replay = bool(
                row_per_state_replay_requested and use_row_residual_only
            )
            row_batch_alpha_replay = bool(
                row_batch_alpha_replay_requested and use_row_residual_only
            )
            row_batch_fd_replay_requested = bool(
                current_tangent_residual_row_batch_fd_replay
            )
            row_batch_fd_replay = bool(
                row_batch_fd_replay_requested and use_row_residual_only
            )
            row_batch_fd_replay_chunk_size = max(
                int(current_tangent_residual_row_batch_fd_replay_chunk_size),
                1,
            )
            row_batch_backend = str(
                current_tangent_residual_row_batch_replay_backend
            ).strip()
            if row_batch_backend not in {
                "cpu",
                "hip_full_residual",
                "hip_full_residual_resident",
                "rust_hip_full_residual_ffi",
            }:
                row_batch_backend = "cpu"
            current_tangent_residual_row_correction["batch_alpha_replay_enabled"] = (
                row_batch_alpha_replay
            )
            current_tangent_residual_row_correction["per_state_batch_replay_enabled"] = (
                row_per_state_replay
            )
            current_tangent_residual_row_correction["batch_fd_replay_enabled"] = (
                row_batch_fd_replay
            )
            current_tangent_residual_row_correction["batch_fd_replay_chunk_size"] = (
                row_batch_fd_replay_chunk_size
            )
            current_tangent_residual_row_correction["batch_replay_backend"] = (
                row_batch_backend
            )
            row_require_hip_batch_replay = bool(
                current_tangent_residual_row_require_hip_batch_replay
                and row_batch_backend
                in {
                    "hip_full_residual",
                    "hip_full_residual_resident",
                    "rust_hip_full_residual_ffi",
                }
            )
            current_tangent_residual_row_correction[
                "require_hip_batch_replay"
            ] = row_require_hip_batch_replay
            if row_batch_alpha_replay_requested and not use_row_residual_only:
                current_tangent_residual_row_correction[
                    "batch_alpha_replay_disabled_reason"
                ] = "requires_residual_only_assembly"
            if row_per_state_replay_requested and not use_row_residual_only:
                current_tangent_residual_row_correction[
                    "per_state_batch_replay_disabled_reason"
                ] = "requires_residual_only_assembly"
            if row_batch_fd_replay_requested and not use_row_residual_only:
                current_tangent_residual_row_correction[
                    "batch_fd_replay_disabled_reason"
                ] = "requires_residual_only_assembly"
            row_residual_only_eval_count = 0
            row_full_assembly_eval_count = 0
            row_per_state_replay_batch_count = 0
            row_per_state_replay_state_count = 0
            row_per_state_replay_seconds = 0.0
            row_batch_alpha_replay_batch_count = 0
            row_batch_alpha_replay_state_count = 0
            row_batch_alpha_replay_seconds = 0.0
            row_batch_fd_replay_batch_count = 0
            row_batch_fd_replay_state_count = 0
            row_batch_fd_replay_seconds = 0.0
            row_hip_backend: Any | None = None
            row_hip_backend_error = ""

            def row_hip_residual_backend() -> Any | None:
                nonlocal row_hip_backend, row_hip_backend_error
                if apply_shell_material_tangent:
                    if allow_state_dependent_shell_material_tangent_hip_replay:
                        current_tangent_residual_row_correction[
                            "state_dependent_shell_material_tangent_hip_replay"
                        ] = True
                        current_tangent_residual_row_correction[
                            "state_dependent_shell_material_tangent_operator_refresh_backend"
                        ] = "host_shell_operator_refresh"
                    elif not allow_frozen_shell_material_tangent_hip_replay:
                        current_tangent_residual_row_correction[
                            "batch_replay_backend_disabled_reason"
                        ] = "state_dependent_shell_material_tangent_requires_cpu_batch"
                        return None
                    else:
                        current_tangent_residual_row_correction[
                            "frozen_shell_material_tangent_hip_replay"
                        ] = True
                        current_tangent_residual_row_correction[
                            "shell_material_tangent_frozen_from_current_state"
                        ] = True
                if row_batch_backend not in {
                    "hip_full_residual",
                    "hip_full_residual_resident",
                    "rust_hip_full_residual_ffi",
                }:
                    return None
                if row_hip_backend is not None:
                    return row_hip_backend
                try:
                    row_frozen_shell_tangent = None
                    if apply_shell_material_tangent and (
                        allow_frozen_shell_material_tangent_hip_replay
                        or allow_state_dependent_shell_material_tangent_hip_replay
                    ):
                        row_frozen_shell_tangent, _row_frozen_shell_meta = shell_material_tangent_by_surface_index(
                            node_xyz=node_xyz,
                            u=current_u,
                            elem_type_code=elem_type_code,
                            elem_material_id=elem_material_id,
                            conn_ptr=conn_ptr,
                            conn_idx=conn_idx,
                            material_props=material_props,
                            controlled_probe=False,
                        )
                    shell_stiffness, _shell_meta, _cache_hit = _cached_shell_operator(
                        u=current_u,
                        node_xyz=node_xyz,
                        elem_type_code=elem_type_code,
                        elem_section_id=elem_section_id,
                        elem_material_id=elem_material_id,
                        conn_ptr=conn_ptr,
                        conn_idx=conn_idx,
                        material_props=material_props,
                        plate_thickness_props=plate_thickness_props,
                        include_membrane=True,
                        shell_operator_cache=shell_operator_cache,
                        material_tangent_by_surface_index_mpa=row_frozen_shell_tangent,
                    )
                    backend_cls = (
                        HipFullResidualResidentWorkerBackend
                        if row_batch_backend == "hip_full_residual_resident"
                        else HipFullResidualRustFfiBackend
                        if row_batch_backend == "rust_hip_full_residual_ffi"
                        else HipFullResidualBatchBackend
                    )
                    row_hip_backend = backend_cls.prepare(
                        frame_dofs=frame_force_cache.dofs,
                        frame_stiffness=frame_force_cache.element_stiffness,
                        shell_csr=shell_stiffness.tocsr(),
                        spring_csr=spring_stiffness.tocsr(),
                        f_ext=reference_f_ext,
                        free=current_free,
                        hipcc=current_tangent_residual_row_hipcc,
                        force_rebuild=bool(
                            current_tangent_residual_row_force_rebuild_hip
                        ),
                    )
                except Exception as exc:  # pragma: no cover - recorded in probe JSON
                    row_hip_backend_error = str(exc)
                    current_tangent_residual_row_correction[
                        "batch_replay_backend_error"
                    ] = row_hip_backend_error
                    return None
                return row_hip_backend

            def hip_batch_replay_required_unavailable(reason: str) -> bool:
                if not row_require_hip_batch_replay:
                    return False
                current_tangent_residual_row_correction[
                    "hip_batch_replay_required_unavailable"
                ] = True
                current_tangent_residual_row_correction[
                    "hip_batch_replay_required_unavailable_reason"
                ] = str(reason)
                current_tangent_residual_row_correction[
                    "cpu_batch_replay_fallback_suppressed"
                ] = True
                return True

            def evaluate_row_candidate_cpu(
                candidate_u: np.ndarray,
            ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
                nonlocal row_residual_only_eval_count, row_full_assembly_eval_count
                if use_row_residual_only:
                    result = assemble_residual(
                        candidate_u,
                        external_load_override=reference_f_ext,
                        residual_only=True,
                        free_override=current_free,
                    )
                else:
                    result = assemble_residual(
                        candidate_u,
                        external_load_override=reference_f_ext,
                    )
                meta = result[5] if len(result) >= 6 and isinstance(result[5], dict) else {}
                if bool(meta.get("residual_only_assembly")):
                    row_residual_only_eval_count += 1
                else:
                    row_full_assembly_eval_count += 1
                return result

            def evaluate_row_candidate(
                candidate_u: np.ndarray,
            ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
                if not row_per_state_replay:
                    return evaluate_row_candidate_cpu(candidate_u)
                results = evaluate_row_candidates_batch(
                    [np.asarray(candidate_u, dtype=np.float64)],
                    replay_role="per_state",
                )
                if len(results) == 1:
                    return results[0]
                if row_require_hip_batch_replay:
                    raise RuntimeError("hip_required_per_state_replay_unavailable")
                return evaluate_row_candidate_cpu(candidate_u)

            def _evaluate_row_candidates_state_dependent(
                candidate_us: list[np.ndarray],
                *,
                replay_role: str,
            ) -> list[tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]]:
                nonlocal row_residual_only_eval_count
                nonlocal row_per_state_replay_batch_count
                nonlocal row_per_state_replay_state_count
                nonlocal row_per_state_replay_seconds
                nonlocal row_batch_alpha_replay_batch_count
                nonlocal row_batch_alpha_replay_state_count
                nonlocal row_batch_alpha_replay_seconds
                nonlocal row_batch_fd_replay_batch_count
                nonlocal row_batch_fd_replay_state_count
                nonlocal row_batch_fd_replay_seconds
                f_ext = np.asarray(reference_f_ext, dtype=np.float64)
                free = np.asarray(current_free, dtype=np.int64)
                backend_cls = (
                    HipFullResidualResidentWorkerBackend
                    if row_batch_backend == "hip_full_residual_resident"
                    else HipFullResidualRustFfiBackend
                    if row_batch_backend == "rust_hip_full_residual_ffi"
                    else HipFullResidualBatchBackend
                )
                results: list[tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]] = []
                for candidate_u in candidate_us:
                    batch_started = time.perf_counter()
                    try:
                        (
                            sd_shell_tangent,
                            _sd_shell_meta,
                        ) = shell_material_tangent_by_surface_index(
                            node_xyz=node_xyz,
                            u=candidate_u,
                            elem_type_code=elem_type_code,
                            elem_material_id=elem_material_id,
                            conn_ptr=conn_ptr,
                            conn_idx=conn_idx,
                            material_props=material_props,
                            controlled_probe=False,
                        )
                        shell_stiffness, _shell_meta, _cache_hit = _cached_shell_operator(
                            u=candidate_u,
                            node_xyz=node_xyz,
                            elem_type_code=elem_type_code,
                            elem_section_id=elem_section_id,
                            elem_material_id=elem_material_id,
                            conn_ptr=conn_ptr,
                            conn_idx=conn_idx,
                            material_props=material_props,
                            plate_thickness_props=plate_thickness_props,
                            include_membrane=True,
                            shell_operator_cache=shell_operator_cache,
                            material_tangent_by_surface_index_mpa=sd_shell_tangent,
                        )
                        sd_backend = backend_cls.prepare(
                            frame_dofs=frame_force_cache.dofs,
                            frame_stiffness=frame_force_cache.element_stiffness,
                            shell_csr=shell_stiffness.tocsr(),
                            spring_csr=spring_stiffness.tocsr(),
                            f_ext=reference_f_ext,
                            free=free,
                            hipcc=current_tangent_residual_row_hipcc,
                            force_rebuild=bool(
                                current_tangent_residual_row_force_rebuild_hip
                            ),
                        )
                        residual_batch, batch_meta = sd_backend.evaluate(
                            np.asarray([candidate_u], dtype=np.float64),
                            reps=1,
                        )
                        elapsed = float(time.perf_counter() - batch_started)
                        current_tangent_residual_row_correction[
                            "state_dependent_shell_material_tangent_hip_replay"
                        ] = True
                        current_tangent_residual_row_correction[
                            "state_dependent_shell_material_tangent_operator_refresh_backend"
                        ] = "host_shell_operator_refresh"
                        row_residual_only_eval_count += 1
                        if replay_role == "per_state":
                            row_per_state_replay_batch_count += 1
                            row_per_state_replay_state_count += 1
                            row_per_state_replay_seconds += elapsed
                        elif replay_role == "finite_difference":
                            row_batch_fd_replay_batch_count += 1
                            row_batch_fd_replay_state_count += 1
                            row_batch_fd_replay_seconds += elapsed
                        else:
                            row_batch_alpha_replay_batch_count += 1
                            row_batch_alpha_replay_state_count += 1
                            row_batch_alpha_replay_seconds += elapsed
                        rhs = np.asarray(f_ext[free], dtype=np.float64)
                        meta = {
                            **batch_meta,
                            "residual_batch_backend": row_batch_backend,
                            "hip_full_residual_batch_replay": True,
                            "hip_batch_group_size": 1,
                            "hip_batch_group_index": 0,
                            "hip_full_residual_resident_worker": bool(
                                row_batch_backend == "hip_full_residual_resident"
                            ),
                            "rust_hip_full_residual_ffi_worker": bool(
                                row_batch_backend == "rust_hip_full_residual_ffi"
                            ),
                            "residual_only_assembly": True,
                            "residual_only_free_override": True,
                            "per_state_batch_replay": bool(replay_role == "per_state"),
                            "batch_alpha_replay": bool(replay_role == "alpha"),
                            "batch_fd_replay": bool(replay_role == "finite_difference"),
                            "residual_row_per_state_batch_replay": bool(
                                replay_role == "per_state"
                            ),
                            "residual_row_batch_alpha_replay": bool(replay_role == "alpha"),
                            "residual_row_batch_fd_replay": bool(replay_role == "finite_difference"),
                            "residual_row_batch_replay_role": replay_role,
                            "residual_row_batch_group_size": 1,
                            "residual_row_batch_group_index": 0,
                            "per_state_batch_replay_seconds": elapsed
                            if replay_role == "per_state"
                            else 0.0,
                            "batch_alpha_replay_seconds": elapsed if replay_role == "alpha" else 0.0,
                            "batch_fd_replay_seconds": elapsed if replay_role == "finite_difference" else 0.0,
                            "batch_size": 1,
                            "free_dof_count": int(free.size),
                            "shell_operator_cache_size": int(len(shell_operator_cache)),
                            "physical_internal_force_inf_n": None,
                            "external_load_source": "reference_configuration",
                            "assembled_external_load_inf_n": None,
                            "used_external_load_inf_n": float(np.max(np.abs(f_ext))) if f_ext.size else 0.0,
                            "state_dependent_shell_material_tangent_hip_replay": True,
                            "state_dependent_shell_material_tangent_operator_refresh_backend": (
                                "host_shell_operator_refresh"
                            ),
                        }
                        results.append(
                            (
                                None,
                                f_ext,
                                free,
                                np.asarray(residual_batch[0], dtype=np.float64),
                                rhs,
                                meta,
                            )
                        )
                    except Exception as exc:  # pragma: no cover - recorded in probe JSON
                        current_tangent_residual_row_correction[
                            "batch_replay_backend_error"
                        ] = str(exc)
                        if hip_batch_replay_required_unavailable(
                            "hip_backend_prepare_or_evaluate_failed_state_dependent"
                        ):
                            return []
                return results

            def evaluate_row_candidates_batch(
                candidate_us: list[np.ndarray],
                *,
                replay_role: str = "alpha",
            ) -> list[tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]]:
                nonlocal row_residual_only_eval_count
                nonlocal row_full_assembly_eval_count
                nonlocal row_per_state_replay_batch_count
                nonlocal row_per_state_replay_state_count
                nonlocal row_per_state_replay_seconds
                nonlocal row_batch_alpha_replay_batch_count
                nonlocal row_batch_alpha_replay_state_count
                nonlocal row_batch_alpha_replay_seconds
                nonlocal row_batch_fd_replay_batch_count
                nonlocal row_batch_fd_replay_state_count
                nonlocal row_batch_fd_replay_seconds
                if not candidate_us:
                    return []
                replay_role = str(replay_role)
                state_dependent_hip = bool(
                    apply_shell_material_tangent
                    and allow_state_dependent_shell_material_tangent_hip_replay
                    and row_batch_backend
                    in {
                        "hip_full_residual",
                        "hip_full_residual_resident",
                        "rust_hip_full_residual_ffi",
                    }
                )
                if state_dependent_hip:
                    current_tangent_residual_row_correction[
                        "state_dependent_shell_material_tangent_hip_replay"
                    ] = True
                    current_tangent_residual_row_correction[
                        "state_dependent_shell_material_tangent_operator_refresh_backend"
                    ] = "host_shell_operator_refresh"
                    return _evaluate_row_candidates_state_dependent(
                        candidate_us,
                        replay_role=replay_role,
                    )
                batch_enabled = (
                    row_per_state_replay
                    if replay_role == "per_state"
                    else row_batch_fd_replay
                    if replay_role == "finite_difference"
                    else row_batch_alpha_replay
                )
                if not batch_enabled:
                    if replay_role != "per_state" and row_per_state_replay:
                        return [evaluate_row_candidate(candidate_u) for candidate_u in candidate_us]
                    return [evaluate_row_candidate_cpu(candidate_u) for candidate_u in candidate_us]
                states = np.asarray(candidate_us, dtype=np.float64)
                if states.ndim != 2:
                    if replay_role != "per_state" and row_per_state_replay:
                        return [evaluate_row_candidate(candidate_u) for candidate_u in candidate_us]
                    return [evaluate_row_candidate_cpu(candidate_u) for candidate_u in candidate_us]
                batch_started = time.perf_counter()
                hip_backend = row_hip_residual_backend()
                elapsed = float(time.perf_counter() - batch_started)
                f_ext = np.asarray(reference_f_ext, dtype=np.float64)
                free = np.asarray(current_free, dtype=np.int64)
                f_int_batch: np.ndarray | None = None
                if hip_backend is not None:
                    try:
                        residual_batch, batch_meta = hip_backend.evaluate(states, reps=1)
                        elapsed = float(time.perf_counter() - batch_started)
                        batch_meta = {
                            **batch_meta,
                            "residual_batch_backend": row_batch_backend,
                            "hip_full_residual_batch_replay": True,
                            "hip_full_residual_resident_worker": bool(
                                row_batch_backend == "hip_full_residual_resident"
                            ),
                            "rust_hip_full_residual_ffi_worker": bool(
                                row_batch_backend == "rust_hip_full_residual_ffi"
                            ),
                        }
                    except Exception as exc:  # pragma: no cover - recorded in probe JSON
                        current_tangent_residual_row_correction[
                            "batch_replay_backend_error"
                        ] = str(exc)
                        if hip_batch_replay_required_unavailable("hip_backend_evaluate_failed"):
                            return []
                        return [evaluate_row_candidate_cpu(candidate_u) for candidate_u in candidate_us]
                else:
                    if hip_batch_replay_required_unavailable("hip_backend_prepare_failed_or_disabled"):
                        return []
                    f_int_batch, batch_meta = assemble_physical_internal_forces_batch(
                        u_batch=states,
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
                        shell_operator_cache=shell_operator_cache,
                        frame_force_cache=frame_force_cache,
                        apply_shell_material_tangent=apply_shell_material_tangent,
                    )
                    elapsed = float(time.perf_counter() - batch_started)
                    residual_batch = np.asarray(
                        f_int_batch[:, free] - f_ext[free],
                        dtype=np.float64,
                    )
                    batch_meta = {
                        **batch_meta,
                        "residual_batch_backend": "cpu_physical_internal_force_batch",
                        "hip_full_residual_batch_replay": False,
                        "hip_full_residual_resident_worker": False,
                    }
                rhs = np.asarray(f_ext[free], dtype=np.float64)
                row_residual_only_eval_count += int(states.shape[0])
                if replay_role == "per_state":
                    row_per_state_replay_batch_count += 1
                    row_per_state_replay_state_count += int(states.shape[0])
                    row_per_state_replay_seconds += elapsed
                elif replay_role == "finite_difference":
                    row_batch_fd_replay_batch_count += 1
                    row_batch_fd_replay_state_count += int(states.shape[0])
                    row_batch_fd_replay_seconds += elapsed
                else:
                    row_batch_alpha_replay_batch_count += 1
                    row_batch_alpha_replay_state_count += int(states.shape[0])
                    row_batch_alpha_replay_seconds += elapsed
                meta_base = {
                    **batch_meta,
                    "residual_only_assembly": True,
                    "residual_only_free_override": True,
                    "per_state_batch_replay": bool(replay_role == "per_state"),
                    "batch_alpha_replay": bool(replay_role == "alpha"),
                    "batch_fd_replay": bool(replay_role == "finite_difference"),
                    "residual_row_per_state_batch_replay": bool(
                        replay_role == "per_state"
                    ),
                    "residual_row_batch_alpha_replay": bool(replay_role == "alpha"),
                    "residual_row_batch_fd_replay": bool(
                        replay_role == "finite_difference"
                    ),
                    "residual_row_batch_replay_role": replay_role,
                    "residual_row_batch_group_size": int(states.shape[0]),
                    "per_state_batch_replay_seconds": elapsed
                    if replay_role == "per_state"
                    else 0.0,
                    "batch_alpha_replay_seconds": elapsed
                    if replay_role == "alpha"
                    else 0.0,
                    "batch_fd_replay_seconds": elapsed
                    if replay_role == "finite_difference"
                    else 0.0,
                    "batch_size": int(states.shape[0]),
                    "free_dof_count": int(free.size),
                    "shell_operator_cache_size": int(len(shell_operator_cache)),
                    "physical_internal_force_inf_n": (
                        float(np.max(np.abs(f_int_batch[:, free])))
                        if (
                            f_int_batch is not None
                            and free.size
                            and f_int_batch.size
                        )
                        else None
                    ),
                    "external_load_source": "reference_configuration",
                    "assembled_external_load_inf_n": None,
                    "used_external_load_inf_n": float(np.max(np.abs(f_ext)))
                    if f_ext.size
                    else 0.0,
                }
                hip_batch_replay = bool(meta_base.get("hip_full_residual_batch_replay"))
                return [
                    (
                        None,
                        f_ext,
                        free,
                        np.asarray(residual_batch[index], dtype=np.float64),
                        rhs,
                        {
                            **meta_base,
                            "batch_alpha_replay_index": int(index)
                            if replay_role == "alpha"
                            else None,
                            "batch_fd_replay_index": int(index)
                            if replay_role == "finite_difference"
                            else None,
                            "residual_row_batch_group_index": int(index),
                            "hip_batch_group_size": int(states.shape[0])
                            if hip_batch_replay
                            else None,
                            "hip_batch_group_index": int(index)
                            if hip_batch_replay
                            else None,
                        },
                    )
                    for index in range(int(states.shape[0]))
                ]

            for row_pass in range(1, max_row_promotions + 1):
                previous_residual_inf = (
                    float(np.max(np.abs(current_residual))) if current_residual.size else 0.0
                )
                stiffness_free_target_support = bool(
                    jacobian_mode == "finite_difference"
                    and support_selection_mode == "target_rows"
                )
                k_ff = (
                    None
                    if stiffness_free_target_support
                    else current_stiffness[current_free, :][:, current_free].tocsr()
                )
                current_tangent_residual_row_correction["attempted"] = True
                current_max_abs = max(
                    float(np.max(np.abs(current_u))) if current_u.size else 0.0,
                    1.0e-9,
                )
                pass_payload: dict[str, Any] = {
                    "row_correction_pass": int(row_pass),
                    "previous_direct_residual_inf_n": previous_residual_inf,
                    "free_dof_count": int(current_free.size),
                    "stiffness_free_target_support": bool(
                        stiffness_free_target_support
                    ),
                }
                support_graph = (
                    None
                    if k_ff is None
                    else (abs(k_ff) + abs(k_ff.T)).tocsr()
                )
                trial_rows: list[dict[str, Any]] = []
                trial_vectors: list[np.ndarray] = []
                trial_frees: list[np.ndarray] = []
                trial_residuals: list[np.ndarray] = []
                trial_rhs_vectors: list[np.ndarray] = []
                candidate_rows_meta: list[dict[str, Any]] = []
                fd_jvp_cache: dict[int, tuple[np.ndarray, float]] = {}
                fd_cache_hits = 0
                fd_cache_misses = 0
                residual_abs = np.abs(current_residual)
                current_component_rows: list[dict[str, Any]] = []
                current_component_breakdown_meta: dict[str, Any] | None = None
                if target_mode == "current_component_rows":
                    (
                        _component_k,
                        _component_f,
                        component_free,
                        component_residual,
                        component_rhs,
                        component_meta,
                    ) = assemble_residual(
                        current_u,
                        external_load_override=reference_f_ext,
                        include_component_forces=True,
                    )
                    component_forces = component_meta.pop("component_forces", {})
                    component_breakdown = _component_breakdown(
                        component_forces=(
                            component_forces
                            if isinstance(component_forces, dict)
                            else {}
                        ),
                        free=np.asarray(component_free, dtype=np.int64),
                        residual=np.asarray(component_residual, dtype=np.float64),
                        rhs=np.asarray(component_rhs, dtype=np.float64),
                        top_count=max(
                            24,
                            2
                            * max(
                                (
                                    int(value)
                                    for value in current_tangent_residual_row_target_counts
                                ),
                                default=12,
                            ),
                        ),
                    )
                    current_component_rows = [
                        row
                        for row in component_breakdown.get("top_rows", [])
                        if isinstance(row, dict)
                    ]
                    current_component_breakdown_meta = {
                        "component_inf_n": component_breakdown.get(
                            "component_inf_n", {}
                        ),
                        "top_row_dominant_component_counts": (
                            component_breakdown.get(
                                "top_row_dominant_component_counts", {}
                            )
                        ),
                        "top_row_count": int(len(current_component_rows)),
                    }
                    pass_payload[
                        "current_component_residual_breakdown"
                    ] = current_component_breakdown_meta
                for target_row_count in current_tangent_residual_row_target_counts:
                    target_meta: dict[str, Any] = {}
                    if target_mode == "residual_node_blocks":
                        target_rows, target_meta = _select_residual_node_block_rows(
                            current_residual,
                            current_free,
                            target_node_count=int(target_row_count),
                            dof_per_node=DOF_PER_NODE,
                        )
                        actual_target_count = int(target_rows.size)
                    elif target_mode == "frontier_component_rows":
                        target_rows, target_meta = _select_frontier_component_rows(
                            current_free,
                            frontier_component_rows,
                            target_row_count=int(target_row_count),
                        )
                        actual_target_count = int(target_rows.size)
                    elif target_mode == "current_component_rows":
                        target_rows, target_meta = _select_frontier_component_rows(
                            current_free,
                            current_component_rows,
                            target_row_count=int(target_row_count),
                        )
                        target_meta = {
                            **target_meta,
                            "source": "current_component_residual_breakdown",
                            "current_component_breakdown": (
                                current_component_breakdown_meta or {}
                            ),
                        }
                        actual_target_count = int(target_rows.size)
                    elif target_mode in {
                        "residual_element_blocks",
                        "residual_frame_element_blocks",
                        "residual_shell_element_blocks",
                        "residual_shell_bending_drilling_rows",
                        "residual_shell_normal_rows",
                        "residual_shell_geometry_normal_rows",
                        "residual_shell_geometry_normal_bending_rows",
                    }:
                        if target_mode == "residual_shell_geometry_normal_bending_rows":
                            normal_rows, normal_meta = _select_residual_element_block_rows(
                                current_residual,
                                current_free,
                                conn_ptr=conn_ptr,
                                conn_idx=conn_idx,
                                node_xyz=node_xyz,
                                elem_id=elem_id,
                                elem_type_code=elem_type_code,
                                target_element_count=int(target_row_count),
                                neighbor_depth=element_neighbor_depth,
                                allowed_element_type_codes={2},
                                target_dof_indices={0, 1, 2},
                                target_shell_geometry_normal_translation_rows=True,
                                shell_normal_participation_threshold=(
                                    current_tangent_residual_row_shell_normal_participation_threshold
                                ),
                                dof_per_node=DOF_PER_NODE,
                            )
                            bending_rows, bending_meta = _select_residual_element_block_rows(
                                current_residual,
                                current_free,
                                conn_ptr=conn_ptr,
                                conn_idx=conn_idx,
                                node_xyz=node_xyz,
                                elem_id=elem_id,
                                elem_type_code=elem_type_code,
                                target_element_count=int(target_row_count),
                                neighbor_depth=element_neighbor_depth,
                                allowed_element_type_codes={2},
                                target_dof_indices={3, 4, 5},
                                target_shell_geometry_normal_translation_rows=False,
                                shell_normal_participation_threshold=(
                                    current_tangent_residual_row_shell_normal_participation_threshold
                                ),
                                dof_per_node=DOF_PER_NODE,
                            )
                            target_rows = np.unique(
                                np.concatenate([normal_rows, bending_rows])
                            ).astype(np.int64)
                            target_rows = target_rows[
                                np.argsort(current_free[target_rows], kind="stable")
                            ]
                            target_meta = {
                                "target_mode": target_mode,
                                "geometry_normal_rows": normal_meta,
                                "bending_drilling_rows": bending_meta,
                                "geometry_normal_row_count": int(normal_rows.size),
                                "bending_drilling_row_count": int(bending_rows.size),
                            }
                        else:
                            target_rows, target_meta = _select_residual_element_block_rows(
                                current_residual,
                                current_free,
                                conn_ptr=conn_ptr,
                                conn_idx=conn_idx,
                                node_xyz=node_xyz,
                                elem_id=elem_id,
                                elem_type_code=elem_type_code,
                                target_element_count=int(target_row_count),
                                neighbor_depth=element_neighbor_depth,
                                allowed_element_type_codes=(
                                    {1}
                                    if target_mode == "residual_frame_element_blocks"
                                    else {2}
                                    if target_mode
                                    in {
                                        "residual_shell_element_blocks",
                                        "residual_shell_bending_drilling_rows",
                                        "residual_shell_normal_rows",
                                        "residual_shell_geometry_normal_rows",
                                    }
                                    else None
                                ),
                                target_dof_indices={3, 4, 5}
                                if target_mode == "residual_shell_bending_drilling_rows"
                                else {2}
                                if target_mode == "residual_shell_normal_rows"
                                else {0, 1, 2}
                                if target_mode == "residual_shell_geometry_normal_rows"
                                else None,
                                target_shell_geometry_normal_translation_rows=(
                                    target_mode == "residual_shell_geometry_normal_rows"
                                ),
                                shell_normal_participation_threshold=(
                                    current_tangent_residual_row_shell_normal_participation_threshold
                                ),
                                dof_per_node=DOF_PER_NODE,
                            )
                        actual_target_count = int(target_rows.size)
                    else:
                        actual_target_count = min(int(target_row_count), int(current_residual.size))
                        if actual_target_count <= 0:
                            continue
                        target_rows = np.argpartition(residual_abs, -actual_target_count)[
                            -actual_target_count:
                        ]
                        target_rows = target_rows[
                            np.argsort(-residual_abs[target_rows], kind="stable")
                        ].astype(np.int64)
                        target_meta = {
                            "target_node_count": 0,
                            "selected_nodes": [],
                        }
                    if actual_target_count <= 0 or target_rows.size == 0:
                        continue
                    for support_column_count in current_tangent_residual_row_support_column_counts:
                        support: set[int] = set(int(row) for row in target_rows.tolist())
                        stiffness_free_support_selection = bool(
                            stiffness_free_target_support
                        )
                        if support_selection_mode == "target_rows":
                            pass
                        elif support_selection_mode == "residual_weighted":
                            assert k_ff is not None
                            scores: dict[int, float] = {}
                            for target_row in target_rows.tolist():
                                start = int(k_ff.indptr[int(target_row)])
                                end = int(k_ff.indptr[int(target_row) + 1])
                                cols = k_ff.indices[start:end]
                                vals = np.abs(k_ff.data[start:end])
                                weight = abs(float(current_residual[int(target_row)]))
                                for col, value in zip(cols.tolist(), vals.tolist()):
                                    scores[int(col)] = scores.get(int(col), 0.0) + weight * float(value)
                            if scores:
                                max_take = min(
                                    int(support_column_count) * int(actual_target_count),
                                    len(scores),
                                )
                                ranked_cols = sorted(
                                    scores,
                                    key=lambda col: (-scores[col], col),
                                )[:max_take]
                                support.update(int(col) for col in ranked_cols)
                        else:
                            assert k_ff is not None
                            for target_row in target_rows.tolist():
                                start = int(k_ff.indptr[int(target_row)])
                                end = int(k_ff.indptr[int(target_row) + 1])
                                cols = k_ff.indices[start:end]
                                vals = np.abs(k_ff.data[start:end])
                                if cols.size:
                                    take = min(int(support_column_count), int(cols.size))
                                    strongest = np.argpartition(vals, -take)[-take:]
                                    support.update(int(cols[index]) for index in strongest.tolist())
                        for _depth in range(
                            max(0, int(current_tangent_residual_row_support_expansion_depth))
                        ):
                            if support_graph is None:
                                break
                            frontier = sorted(support)
                            expanded: set[int] = set(support)
                            for support_col in frontier:
                                start = int(support_graph.indptr[int(support_col)])
                                end = int(support_graph.indptr[int(support_col) + 1])
                                cols = support_graph.indices[start:end]
                                vals = np.abs(support_graph.data[start:end])
                                if cols.size:
                                    take = min(int(support_column_count), int(cols.size))
                                    strongest = np.argpartition(vals, -take)[-take:]
                                    expanded.update(int(cols[index]) for index in strongest.tolist())
                            support = expanded
                        support_cols = np.asarray(sorted(support), dtype=np.int64)
                        pre_node_block_support_size = int(support_cols.size)
                        if current_tangent_residual_row_node_block_support:
                            support_cols = _expand_support_to_node_blocks(
                                support_cols,
                                current_free,
                                dof_per_node=DOF_PER_NODE,
                            )
                        if support_cols.size == 0:
                            continue
                        tangent_submatrix = (
                            np.zeros(
                                (int(target_rows.size), int(support_cols.size)),
                                dtype=np.float64,
                            )
                            if stiffness_free_support_selection
                            else k_ff[target_rows, :][:, support_cols].toarray()
                        )
                        pre_fd_support_size = int(support_cols.size)
                        support_trimmed_by_fd_limit = False
                        if (
                            jacobian_mode == "finite_difference"
                            and fd_max_support_columns > 0
                            and support_cols.size > fd_max_support_columns
                        ):
                            column_scores = (
                                np.asarray(
                                    [
                                        abs(float(current_residual[int(col)]))
                                        for col in support_cols.tolist()
                                    ],
                                    dtype=np.float64,
                                )
                                if stiffness_free_support_selection
                                else np.linalg.norm(tangent_submatrix, axis=0)
                            )
                            take = min(int(fd_max_support_columns), int(support_cols.size))
                            strongest = np.argpartition(column_scores, -take)[-take:]
                            strongest = strongest[
                                np.argsort(-column_scores[strongest], kind="stable")
                            ]
                            support_cols = support_cols[strongest].astype(np.int64)
                            tangent_submatrix = tangent_submatrix[:, strongest]
                            support_trimmed_by_fd_limit = True
                        submatrix = tangent_submatrix
                        jacobian_meta: dict[str, Any] = {
                            "mode": jacobian_mode,
                            "source": "current_tangent",
                            "finite_difference_attempted": False,
                            "finite_difference_epsilon_base": float(fd_epsilon_base),
                            "pre_finite_difference_support_size": pre_fd_support_size,
                            "support_trimmed_by_fd_limit": bool(support_trimmed_by_fd_limit),
                            "post_finite_difference_support_size": int(support_cols.size),
                            "stiffness_free_support_selection": bool(
                                stiffness_free_support_selection
                            ),
                            "support_selection_uses_tangent_stiffness": bool(
                                not stiffness_free_support_selection
                            ),
                            "free_dof_set_stable": True,
                        }
                        if jacobian_mode == "finite_difference":
                            jacobian_meta["finite_difference_attempted"] = True
                            fd_submatrix = np.zeros(
                                (int(target_rows.size), int(support_cols.size)),
                                dtype=np.float64,
                            )
                            fd_epsilons: list[float] = []
                            fd_started = time.perf_counter()
                            fd_stable = True
                            fd_cache_hits_before = fd_cache_hits
                            fd_cache_misses_before = fd_cache_misses
                            fd_batch_count_before = row_batch_fd_replay_batch_count
                            fd_batch_state_count_before = row_batch_fd_replay_state_count
                            fd_batch_seconds_before = row_batch_fd_replay_seconds
                            fd_batch_meta_rows: list[dict[str, Any]] = []
                            missing_fd_entries: list[
                                tuple[int, int, float, np.ndarray]
                            ] = []
                            for fd_col, support_col in enumerate(support_cols.tolist()):
                                support_col = int(support_col)
                                cached = fd_jvp_cache.get(support_col)
                                if cached is None:
                                    global_dof = int(current_free[support_col])
                                    epsilon = fd_epsilon_base * max(
                                        abs(float(current_u[global_dof])),
                                        1.0,
                                    )
                                    probe_u = np.asarray(current_u, dtype=np.float64).copy()
                                    probe_u[global_dof] += epsilon
                                    missing_fd_entries.append(
                                        (
                                            int(fd_col),
                                            int(support_col),
                                            float(epsilon),
                                            probe_u,
                                        )
                                    )
                                else:
                                    fd_cache_hits += 1
                            for chunk_start in range(
                                0,
                                len(missing_fd_entries),
                                row_batch_fd_replay_chunk_size,
                            ):
                                fd_chunk = missing_fd_entries[
                                    chunk_start : chunk_start
                                    + row_batch_fd_replay_chunk_size
                                ]
                                fd_chunk_results = evaluate_row_candidates_batch(
                                    [
                                        np.asarray(probe_u, dtype=np.float64)
                                        for _fd_col, _support_col, _epsilon, probe_u
                                        in fd_chunk
                                    ],
                                    replay_role="finite_difference",
                                )
                                if len(fd_chunk_results) != len(fd_chunk):
                                    fd_stable = False
                                    current_tangent_residual_row_correction[
                                        "stop_reason"
                                    ] = "hip_required_fd_replay_unavailable"
                                    break
                                for (
                                    _fd_col,
                                    support_col,
                                    epsilon,
                                    _probe_u,
                                ), fd_result in zip(fd_chunk, fd_chunk_results):
                                    (
                                        _fd_k,
                                        _fd_f,
                                        fd_free,
                                        fd_residual,
                                        _fd_rhs,
                                        _fd_meta,
                                    ) = fd_result
                                    fd_batch_meta_rows.append(dict(_fd_meta))
                                    if not (
                                        fd_free.shape == current_free.shape
                                        and np.array_equal(fd_free, current_free)
                                    ):
                                        fd_stable = False
                                        break
                                    full_jvp = (fd_residual - current_residual) / epsilon
                                    fd_jvp_cache[int(support_col)] = (
                                        np.asarray(full_jvp, dtype=np.float64),
                                        float(epsilon),
                                    )
                                    fd_cache_misses += 1
                                if not fd_stable:
                                    break
                            if fd_stable:
                                for fd_col, support_col in enumerate(
                                    support_cols.tolist()
                                ):
                                    cached = fd_jvp_cache.get(int(support_col))
                                    if cached is None:
                                        fd_stable = False
                                        break
                                    full_jvp, epsilon = cached
                                    fd_submatrix[:, int(fd_col)] = (
                                        np.asarray(full_jvp, dtype=np.float64)[
                                            target_rows
                                        ]
                                    )
                                    fd_epsilons.append(float(epsilon))
                            jacobian_meta.update(
                                {
                                    "source": "finite_difference_residual",
                                    "free_dof_set_stable": bool(fd_stable),
                                    "finite_difference_column_count": int(len(fd_epsilons)),
                                    "finite_difference_seconds": float(
                                        time.perf_counter() - fd_started
                                    ),
                                    "finite_difference_min_epsilon": float(min(fd_epsilons))
                                    if fd_epsilons
                                    else 0.0,
                                    "finite_difference_max_epsilon": float(max(fd_epsilons))
                                    if fd_epsilons
                                    else 0.0,
                                    "finite_difference_cache_hits": int(
                                        fd_cache_hits - fd_cache_hits_before
                                    ),
                                    "finite_difference_cache_misses": int(
                                        fd_cache_misses - fd_cache_misses_before
                                    ),
                                    "finite_difference_cache_size": int(len(fd_jvp_cache)),
                                    "finite_difference_batch_replay": bool(
                                        row_batch_fd_replay
                                    ),
                                    "finite_difference_batch_replay_backend": (
                                        row_batch_backend
                                        if row_batch_fd_replay
                                        else "disabled"
                                    ),
                                    "finite_difference_batch_chunk_size": int(
                                        row_batch_fd_replay_chunk_size
                                    ),
                                    "finite_difference_batch_count": int(
                                        row_batch_fd_replay_batch_count
                                        - fd_batch_count_before
                                    ),
                                    "finite_difference_batch_state_count": int(
                                        row_batch_fd_replay_state_count
                                        - fd_batch_state_count_before
                                    ),
                                    "finite_difference_batch_seconds": float(
                                        row_batch_fd_replay_seconds
                                        - fd_batch_seconds_before
                                    ),
                                    "finite_difference_hip_batch_replay": any(
                                        bool(meta.get("hip_full_residual_batch_replay"))
                                        for meta in fd_batch_meta_rows
                                    ),
                                    "finite_difference_hip_batch_group_sizes": sorted(
                                        {
                                            int(meta["hip_batch_group_size"])
                                            for meta in fd_batch_meta_rows
                                            if meta.get("hip_batch_group_size")
                                            is not None
                                        }
                                    ),
                                    "finite_difference_residual_batch_backends": sorted(
                                        {
                                            str(meta.get("residual_batch_backend"))
                                            for meta in fd_batch_meta_rows
                                            if meta.get("residual_batch_backend")
                                        }
                                    ),
                                }
                            )
                            if not fd_stable or len(fd_epsilons) != int(support_cols.size):
                                continue
                            submatrix = fd_submatrix
                        rhs_rows = -current_residual[target_rows]
                        row_equation_weights: np.ndarray | None = None
                        row_equation_scale_meta: dict[str, Any] = {
                            "mode": "none",
                            "enabled": False,
                        }
                        if target_mode in {
                            "frontier_component_rows",
                            "current_component_rows",
                        }:
                            (
                                row_equation_weights,
                                row_equation_scale_meta,
                            ) = _frontier_component_row_weights(
                                target_meta,
                                mode=frontier_component_scale_mode,
                            )
                        solve_started = time.perf_counter()
                        ridge_lambda = 0.0
                        solve_matrix = submatrix
                        solve_rhs = rhs_rows
                        if row_equation_weights is not None:
                            solve_matrix = submatrix * row_equation_weights[:, None]
                            solve_rhs = rhs_rows * row_equation_weights
                        if row_ridge_factor > 0.0 and submatrix.size:
                            singular_probe = np.linalg.svd(
                                solve_matrix,
                                compute_uv=False,
                            )
                            spectral_scale = (
                                float(np.max(singular_probe))
                                if singular_probe.size
                                else float(np.linalg.norm(solve_matrix))
                            )
                            ridge_lambda = row_ridge_factor * max(spectral_scale, 1.0)
                            if ridge_lambda > 0.0:
                                solve_matrix = np.vstack(
                                    [
                                        solve_matrix,
                                        np.eye(int(support_cols.size), dtype=np.float64)
                                        * ridge_lambda,
                                    ]
                                )
                                solve_rhs = np.concatenate(
                                    [
                                        solve_rhs,
                                        np.zeros(int(support_cols.size), dtype=np.float64),
                                    ]
                                )
                        try:
                            if row_svd_truncation_enabled:
                                (
                                    coeffs,
                                    residual_sum,
                                    rank,
                                    singular_values,
                                    solve_meta,
                                ) = _truncated_svd_lstsq(
                                    solve_matrix,
                                    solve_rhs,
                                    relative_cutoff=row_svd_relative_cutoff,
                                    max_condition=row_svd_max_condition,
                                )
                            else:
                                (
                                    coeffs,
                                    residual_sum,
                                    rank,
                                    singular_values,
                                ) = np.linalg.lstsq(
                                    solve_matrix,
                                    solve_rhs,
                                    rcond=None,
                                )
                                solve_meta = {
                                    "solve_method": "lstsq",
                                    "svd_truncation_enabled": False,
                                    "svd_relative_cutoff": float(row_svd_relative_cutoff),
                                    "svd_max_condition": float(row_svd_max_condition),
                                }
                            solve_error = ""
                        except np.linalg.LinAlgError as exc:
                            coeffs = np.zeros(int(support_cols.size), dtype=np.float64)
                            residual_sum = np.asarray([], dtype=np.float64)
                            rank = 0
                            singular_values = np.asarray([], dtype=np.float64)
                            solve_meta = {
                                "solve_method": "failed",
                                "svd_truncation_enabled": bool(
                                    row_svd_truncation_enabled
                                ),
                                "svd_relative_cutoff": float(row_svd_relative_cutoff),
                                "svd_max_condition": float(row_svd_max_condition),
                            }
                            solve_error = str(exc)
                        solve_seconds = time.perf_counter() - solve_started
                        candidate_delta_free = np.zeros(int(current_free.size), dtype=np.float64)
                        candidate_delta_free[support_cols] = np.asarray(coeffs, dtype=np.float64)
                        candidate_delta_u = np.zeros_like(current_u)
                        candidate_delta_u[current_free] = candidate_delta_free
                        candidate_delta_inf = (
                            float(np.max(np.abs(candidate_delta_u)))
                            if candidate_delta_u.size
                            else 0.0
                        )
                        gate_limited_alpha = (
                            0.95
                            * float(relative_increment_tolerance)
                            * current_max_abs
                            / candidate_delta_inf
                            if candidate_delta_inf > 0.0
                            else 0.0
                        )
                        directional_probe_meta: dict[str, Any] = {
                            "enabled": bool(
                                current_tangent_residual_row_directional_probe_alpha > 0.0
                                and candidate_delta_inf > 0.0
                            ),
                            "probe_alpha": float(
                                current_tangent_residual_row_directional_probe_alpha
                            ),
                            "candidate_alphas": [],
                        }
                        dynamic_alpha_candidates: list[tuple[str, float]] = []
                        reverse_alpha_candidates: list[tuple[str, float]] = []
                        if bool(directional_probe_meta["enabled"]):
                            probe_alpha = float(
                                current_tangent_residual_row_directional_probe_alpha
                            )
                            probe_u = current_u + probe_alpha * candidate_delta_u
                            (
                                _probe_k,
                                _probe_f,
                                probe_free,
                                probe_residual,
                                _probe_rhs,
                                _probe_meta,
                            ) = evaluate_row_candidate(probe_u)
                            free_is_stable_probe = bool(
                                probe_free.shape == current_free.shape
                                and np.array_equal(probe_free, current_free)
                            )
                            directional_probe_meta["free_dof_set_stable"] = (
                                free_is_stable_probe
                            )
                            directional_probe_meta["probe_direct_residual_inf_n"] = (
                                float(np.max(np.abs(probe_residual)))
                                if probe_residual.size
                                else 0.0
                            )
                            if free_is_stable_probe:
                                full_jvp = (
                                    probe_residual - current_residual
                                ) / probe_alpha
                                full_residual = current_residual
                                full_denom = float(np.dot(full_jvp, full_jvp))
                                directional_probe_meta[
                                    "global_jacobian_action_l2_n"
                                ] = (
                                    float(np.linalg.norm(full_jvp))
                                    if full_jvp.size
                                    else 0.0
                                )
                                directional_probe_meta[
                                    "global_jacobian_action_inf_n"
                                ] = (
                                    float(np.max(np.abs(full_jvp)))
                                    if full_jvp.size
                                    else 0.0
                                )
                                if full_denom > 0.0:
                                    global_alpha = (
                                        -float(np.dot(full_residual, full_jvp))
                                        / full_denom
                                    )
                                    directional_probe_meta[
                                        "global_directional_l2_alpha_raw"
                                    ] = float(global_alpha)
                                    if global_alpha > 0.0:
                                        dynamic_alpha_candidates.append(
                                            (
                                                "current_tangent_residual_row_global_directional_l2",
                                                global_alpha,
                                            )
                                        )
                                    elif global_alpha < 0.0:
                                        reverse_alpha_candidates.append(
                                            (
                                                "current_tangent_residual_row_reverse_global_directional_l2",
                                                abs(global_alpha),
                                            )
                                        )
                                row_jvp = (
                                    probe_residual[target_rows] - current_residual[target_rows]
                                ) / probe_alpha
                                row_residual = current_residual[target_rows]
                                denom = float(np.dot(row_jvp, row_jvp))
                                directional_probe_meta["row_jacobian_action_l2_n"] = (
                                    float(np.linalg.norm(row_jvp)) if row_jvp.size else 0.0
                                )
                                directional_probe_meta["row_jacobian_action_inf_n"] = (
                                    float(np.max(np.abs(row_jvp))) if row_jvp.size else 0.0
                                )
                                if denom > 0.0:
                                    dynamic_alpha_candidates.append(
                                        (
                                            "current_tangent_residual_row_directional_l2",
                                            -float(np.dot(row_residual, row_jvp)) / denom,
                                        )
                                    )
                                ratios = [
                                    -float(residual_value) / float(jacobian_value)
                                    for residual_value, jacobian_value in zip(
                                        row_residual.tolist(),
                                        row_jvp.tolist(),
                                    )
                                    if abs(float(jacobian_value)) > 1.0e-30
                                ]
                                positive_ratios = [
                                    value
                                    for value in ratios
                                    if np.isfinite(value) and value > 0.0
                                ]
                                if positive_ratios:
                                    dynamic_alpha_candidates.append(
                                        (
                                            "current_tangent_residual_row_directional_median",
                                            float(np.median(positive_ratios)),
                                        )
                                    )
                                    dynamic_alpha_candidates.append(
                                        (
                                            "current_tangent_residual_row_directional_min",
                                            float(min(positive_ratios)),
                                        )
                                    )
                            else:
                                directional_probe_meta["reason"] = "free_dof_set_changed"
                        row_alpha_rows = _unique_positive_alphas(
                            [
                                ("current_tangent_residual_row", float(alpha))
                                for alpha in current_tangent_residual_row_alpha_values
                                if float(alpha) > 0.0
                            ]
                            + [
                                ("current_tangent_residual_row", gate_limited_alpha),
                                ("current_tangent_residual_row", 0.5 * gate_limited_alpha),
                            ]
                            + dynamic_alpha_candidates,
                            min_alpha=1.0e-8,
                            max_alpha=1.0,
                        )
                        reverse_row_alpha_rows = _unique_positive_alphas(
                            reverse_alpha_candidates,
                            min_alpha=1.0e-8,
                            max_alpha=1.0,
                        )
                        signed_row_alpha_rows = [
                            (source, alpha, 1.0) for source, alpha in row_alpha_rows
                        ] + [
                            (source, alpha, -1.0)
                            for source, alpha in reverse_row_alpha_rows
                        ]
                        if current_tangent_residual_row_allow_negative_alphas:
                            signed_row_alpha_rows.extend(
                                (f"{source}_negative", alpha, -1.0)
                                for source, alpha in row_alpha_rows
                            )
                        directional_probe_meta["candidate_alphas"] = [
                            {
                                "source": source,
                                "alpha": float(alpha),
                                "direction_sign": float(direction_sign),
                            }
                            for source, alpha, direction_sign in signed_row_alpha_rows
                        ]
                        candidate_start = len(trial_rows)
                        candidate_row_index = int(len(candidate_rows_meta))
                        candidate_eval_inputs: list[tuple[str, float, float, np.ndarray]] = []
                        for alpha_source, alpha, direction_sign in signed_row_alpha_rows:
                            candidate_eval_inputs.append(
                                (
                                    alpha_source,
                                    float(alpha),
                                    float(direction_sign),
                                    current_u
                                    + (
                                        float(direction_sign)
                                        * float(alpha)
                                        * candidate_delta_u
                                    ),
                                )
                            )
                        candidate_eval_results = evaluate_row_candidates_batch(
                            [
                                np.asarray(candidate_u, dtype=np.float64)
                                for _alpha_source, _alpha, _direction_sign, candidate_u
                                in candidate_eval_inputs
                            ]
                        )
                        for (
                            alpha_source,
                            alpha,
                            direction_sign,
                            candidate_u,
                        ), candidate_result in zip(
                            candidate_eval_inputs,
                            candidate_eval_results,
                        ):
                            (
                                _k,
                                _f,
                                candidate_free,
                                candidate_residual,
                                candidate_rhs,
                                candidate_meta,
                            ) = candidate_result
                            residual_inf = (
                                float(np.max(np.abs(candidate_residual)))
                                if candidate_residual.size
                                else 0.0
                            )
                            improvement_inf = previous_residual_inf - residual_inf
                            relative_improvement = improvement_inf / max(
                                previous_residual_inf, 1.0e-30
                            )
                            increment = (
                                float(np.max(np.abs(candidate_u - current_u)))
                                if candidate_u.size
                                else 0.0
                            )
                            max_abs = max(
                                float(np.max(np.abs(candidate_u)))
                                if candidate_u.size
                                else current_max_abs,
                                1.0e-9,
                            )
                            metrics = _translation_metrics(candidate_u, node_xyz)
                            free_is_stable = bool(
                                candidate_free.shape == current_free.shape
                                and np.array_equal(candidate_free, current_free)
                            )
                            trial_row = {
                                "row_correction_pass": int(row_pass),
                                "candidate_row_index": int(candidate_row_index),
                                "target_mode": target_mode,
                                "target_row_count": int(actual_target_count),
                                "configured_target_count": int(target_row_count),
                                "support_column_count": int(support_column_count),
                                "support_size": int(support_cols.size),
                                "jacobian_mode": jacobian_mode,
                                "jacobian_source": str(jacobian_meta.get("source", "")),
                                "alpha_source": alpha_source,
                                "alpha": float(alpha),
                                "direction_sign": float(direction_sign),
                                "direct_residual_inf_n": residual_inf,
                                "improvement_inf_n": float(improvement_inf),
                                "relative_improvement": float(relative_improvement),
                                "direct_relative_residual_inf": residual_inf
                                / max(
                                    float(np.max(np.abs(candidate_rhs)))
                                    if candidate_rhs.size
                                    else 0.0,
                                    1.0,
                                ),
                                "relative_increment": increment / max_abs,
                                "max_increment_m": increment,
                                "max_translation_m": metrics["max_translation_m"],
                                "residual_gate_passed": bool(residual_inf <= residual_tolerance_n),
                                "relative_increment_gate_passed": bool(
                                    increment / max_abs <= relative_increment_tolerance
                                ),
                                "free_dof_set_stable": free_is_stable,
                                "residual_only_assembly": bool(
                                    candidate_meta.get("residual_only_assembly")
                                ),
                                "per_state_batch_replay": bool(
                                    candidate_meta.get(
                                        "residual_row_per_state_batch_replay"
                                    )
                                ),
                                "batch_alpha_replay": bool(
                                    candidate_meta.get(
                                        "residual_row_batch_alpha_replay"
                                    )
                                ),
                                "batch_alpha_replay_index": (
                                    int(candidate_meta["batch_alpha_replay_index"])
                                    if candidate_meta.get("batch_alpha_replay_index")
                                    is not None
                                    else None
                                ),
                                "residual_row_batch_group_size": (
                                    int(candidate_meta["residual_row_batch_group_size"])
                                    if candidate_meta.get("residual_row_batch_group_size")
                                    is not None
                                    else None
                                ),
                                "residual_row_batch_group_index": (
                                    int(candidate_meta["residual_row_batch_group_index"])
                                    if candidate_meta.get("residual_row_batch_group_index")
                                    is not None
                                    else None
                                ),
                                "residual_batch_backend": str(
                                    candidate_meta.get("residual_batch_backend") or ""
                                ),
                                "hip_full_residual_batch_replay": bool(
                                    candidate_meta.get(
                                        "hip_full_residual_batch_replay"
                                    )
                                ),
                                "hip_batch_group_size": (
                                    int(candidate_meta["hip_batch_group_size"])
                                    if candidate_meta.get("hip_batch_group_size")
                                    is not None
                                    else None
                                ),
                                "hip_batch_group_index": (
                                    int(candidate_meta["hip_batch_group_index"])
                                    if candidate_meta.get("hip_batch_group_index")
                                    is not None
                                    else None
                                ),
                                "hip_kernel_mean_seconds": (
                                    float(candidate_meta["hip_kernel_mean_seconds"])
                                    if candidate_meta.get("hip_kernel_mean_seconds")
                                    is not None
                                    else None
                                ),
                                "hip_subprocess_seconds": (
                                    float(candidate_meta["hip_subprocess_seconds"])
                                    if candidate_meta.get("hip_subprocess_seconds")
                                    is not None
                                    else None
                                ),
                                "single_subprocess_boundary": bool(
                                    candidate_meta.get("single_subprocess_boundary")
                                ),
                            }
                            trial_rows.append(trial_row)
                            trial_vectors.append(candidate_u)
                            trial_frees.append(
                                np.asarray(candidate_free, dtype=np.int64).copy()
                            )
                            trial_residuals.append(
                                np.asarray(candidate_residual, dtype=np.float64).copy()
                            )
                            trial_rhs_vectors.append(
                                np.asarray(candidate_rhs, dtype=np.float64).copy()
                            )
                        candidate_trials = trial_rows[candidate_start:]
                        if candidate_trials:
                            best_candidate_trial = min(
                                candidate_trials,
                                key=lambda row: float(row["direct_residual_inf_n"]),
                            )
                            candidate_rows_meta.append(
                                {
                                    "candidate_row_index": int(candidate_row_index),
                                    "target_mode": target_mode,
                                    "target_row_count": int(actual_target_count),
                                    "configured_target_count": int(target_row_count),
                                    "target_meta": target_meta,
                                    "support_column_count": int(support_column_count),
                                    "support_expansion_depth": int(
                                        current_tangent_residual_row_support_expansion_depth
                                    ),
                                    "support_selection": support_selection_mode,
                                    "node_block_support": bool(
                                        current_tangent_residual_row_node_block_support
                                    ),
                                    "pre_node_block_support_size": pre_node_block_support_size,
                                    "support_size": int(support_cols.size),
                                    "support_columns": [
                                        int(value) for value in support_cols.tolist()
                                    ],
                                    "support_free_dof_indices": [
                                        int(value)
                                        for value in current_free[support_cols].tolist()
                                    ],
                                    "support_coefficients_m": [
                                        float(value) for value in coeffs.tolist()
                                    ],
                                    "jacobian": jacobian_meta,
                                    "row_equation_scale": row_equation_scale_meta,
                                    "ridge_factor": float(row_ridge_factor),
                                    "ridge_lambda": float(ridge_lambda),
                                    "ridge_augmented": bool(ridge_lambda > 0.0),
                                    "linear_solve": solve_meta,
                                    "rank": int(rank),
                                    "singular_values": [
                                        float(value) for value in singular_values.tolist()
                                    ],
                                    "coefficient_l2": float(np.linalg.norm(coeffs)),
                                    "coefficient_linf": (
                                        float(np.max(np.abs(coeffs))) if coeffs.size else 0.0
                                    ),
                                    "candidate_delta_inf_m": candidate_delta_inf,
                                    "gate_limited_alpha": float(gate_limited_alpha),
                                    "alpha_values": [
                                        float(alpha)
                                        for _source, alpha, _direction_sign in signed_row_alpha_rows
                                    ],
                                    "alpha_sources": [
                                        str(source)
                                        for source, _alpha, _direction_sign in signed_row_alpha_rows
                                    ],
                                    "alpha_direction_signs": [
                                        float(direction_sign)
                                        for _source, _alpha, direction_sign in signed_row_alpha_rows
                                    ],
                                    "directional_residual_jacobian": directional_probe_meta,
                                    "linear_least_squares_residual_sum": [
                                        float(value) for value in np.ravel(residual_sum).tolist()
                                    ],
                                    "linear_solve_seconds": float(solve_seconds),
                                    "solve_error": solve_error,
                                    "best_candidate": best_candidate_trial,
                                }
                            )
                if not trial_rows:
                    pass_payload["promoted_to_final_state"] = False
                    pass_payload["reason"] = "row_candidate_unavailable"
                    current_tangent_residual_row_correction["stop_reason"] = pass_payload[
                        "reason"
                    ]
                    pass_rows.append(pass_payload)
                    break
                best_trial_index, best_trial = min(
                    enumerate(trial_rows),
                    key=lambda item: float(item[1]["direct_residual_inf_n"]),
                )
                gate_eligible_trials = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("free_dof_set_stable"))
                    and bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                    and float(row.get("relative_improvement", 0.0))
                    >= min_row_relative_improvement
                ]
                gate_eligible_without_floor = [
                    (index, row)
                    for index, row in enumerate(trial_rows)
                    if bool(row.get("free_dof_set_stable"))
                    and bool(row.get("relative_increment_gate_passed"))
                    and float(row["direct_residual_inf_n"]) < previous_residual_inf
                ]
                best_gate_trial_index: int | None = None
                best_gate_trial: dict[str, Any] | None = None
                if gate_eligible_trials:
                    best_gate_trial_index, best_gate_trial = min(
                        gate_eligible_trials,
                        key=lambda item: float(item[1]["direct_residual_inf_n"]),
                    )
                    all_gate_candidates.append(best_gate_trial)
                promoted = best_gate_trial is not None
                pass_payload.update(
                    {
                        "candidate_rows": candidate_rows_meta,
                        "trial_rows": trial_rows,
                        "best_candidate": best_trial,
                        "best_gate_eligible_candidate": best_gate_trial,
                        "residual_descent": bool(
                            float(best_trial["direct_residual_inf_n"]) < previous_residual_inf
                        ),
                        "promoted_to_final_state": promoted,
                    }
                )
                if best_gate_trial is not None:
                    pass_payload["accepted_improvement_inf_n"] = float(
                        best_gate_trial["improvement_inf_n"]
                    )
                    pass_payload["accepted_relative_improvement"] = float(
                        best_gate_trial["relative_improvement"]
                    )
                elif gate_eligible_without_floor:
                    pass_payload["reason"] = "relative_improvement_floor_not_met"
                elif not bool(pass_payload["residual_descent"]):
                    pass_payload["reason"] = "no_residual_descent"
                else:
                    pass_payload["reason"] = "no_gate_eligible_residual_descent"
                pass_rows.append(pass_payload)
                all_trial_rows.extend(trial_rows)
                if not promoted:
                    current_tangent_residual_row_correction["stop_reason"] = str(
                        pass_payload["reason"]
                    )
                    break
                assert best_gate_trial_index is not None
                promotion_count += 1
                current_u = trial_vectors[best_gate_trial_index]
                accepted_trial = trial_rows[best_gate_trial_index]
                accepted_candidate_meta = next(
                    (
                        candidate_meta
                        for candidate_meta in candidate_rows_meta
                        if int(candidate_meta.get("candidate_row_index", -1))
                        == int(accepted_trial.get("candidate_row_index", -2))
                    ),
                    None,
                )
                terminal_row_promotion = bool(promotion_count >= max_row_promotions)
                stop_after_row_promotion = False
                hip_residual_refresh_available = bool(
                    row_require_hip_batch_replay
                    and accepted_trial.get("hip_full_residual_batch_replay")
                    and best_gate_trial_index < len(trial_frees)
                    and best_gate_trial_index < len(trial_residuals)
                    and best_gate_trial_index < len(trial_rhs_vectors)
                    and trial_frees[best_gate_trial_index].shape == current_free.shape
                    and np.array_equal(
                        trial_frees[best_gate_trial_index],
                        current_free,
                    )
                )
                if hip_residual_refresh_available:
                    current_free = trial_frees[best_gate_trial_index]
                    current_residual = trial_residuals[best_gate_trial_index]
                    current_rhs = trial_rhs_vectors[best_gate_trial_index]
                    row_acceptance_refresh_meta = {
                        "accepted_state_refresh_backend": str(
                            accepted_trial.get("residual_batch_backend")
                            or row_batch_backend
                        ),
                        "accepted_state_refresh_hip_used": True,
                        "accepted_state_refresh_cpu_used": False,
                        "accepted_state_refresh_source": (
                            "accepted_row_candidate_hip_batch_replay"
                        ),
                    }
                    if terminal_row_promotion:
                        row_acceptance_refresh_meta.update(
                            {
                                "accepted_state_tangent_refresh_backend": (
                                    "not_refreshed_terminal_row_correction"
                                ),
                                "accepted_state_tangent_refresh_cpu_used": False,
                                "accepted_state_tangent_refresh_skipped_reason": (
                                    "terminal_row_correction_uses_accepted_hip_residual"
                                ),
                            }
                        )
                    else:
                        if jacobian_mode == "finite_difference":
                            refresh_support_cols = (
                                list(accepted_candidate_meta.get("support_columns", []))
                                if isinstance(accepted_candidate_meta, dict)
                                else []
                            )
                            refresh_support_cols = [
                                int(value)
                                for value in refresh_support_cols
                                if 0 <= int(value) < int(current_free.size)
                            ]
                            refresh_meta_rows: list[dict[str, Any]] = []
                            refresh_jvp_norms: list[float] = []
                            refresh_stable = bool(row_batch_fd_replay and refresh_support_cols)
                            refresh_reason = ""
                            if refresh_stable:
                                refresh_entries: list[tuple[int, float, np.ndarray]] = []
                                for support_col in refresh_support_cols:
                                    global_dof = int(current_free[int(support_col)])
                                    epsilon = fd_epsilon_base * max(
                                        abs(float(current_u[global_dof])),
                                        1.0,
                                    )
                                    probe_u = np.asarray(current_u, dtype=np.float64).copy()
                                    probe_u[global_dof] += float(epsilon)
                                    refresh_entries.append(
                                        (int(support_col), float(epsilon), probe_u)
                                    )
                                refresh_results = evaluate_row_candidates_batch(
                                    [
                                        np.asarray(probe_u, dtype=np.float64)
                                        for _support_col, _epsilon, probe_u in refresh_entries
                                    ],
                                    replay_role="finite_difference",
                                )
                                if len(refresh_results) != len(refresh_entries):
                                    refresh_stable = False
                                    refresh_reason = "hip_fd_refresh_result_count_mismatch"
                                for (
                                    support_col,
                                    epsilon,
                                    _probe_u,
                                ), refresh_result in zip(
                                    refresh_entries,
                                    refresh_results,
                                ):
                                    (
                                        _refresh_k,
                                        _refresh_f,
                                        refresh_free,
                                        refresh_residual,
                                        _refresh_rhs,
                                        refresh_meta,
                                    ) = refresh_result
                                    refresh_meta_rows.append(dict(refresh_meta))
                                    if not (
                                        refresh_free.shape == current_free.shape
                                        and np.array_equal(refresh_free, current_free)
                                    ):
                                        refresh_stable = False
                                        refresh_reason = "hip_fd_refresh_free_dof_changed"
                                        break
                                    if not refresh_meta.get("hip_full_residual_batch_replay"):
                                        refresh_stable = False
                                        refresh_reason = "hip_fd_refresh_non_hip_residual_backend"
                                        break
                                    full_jvp = (
                                        np.asarray(refresh_residual, dtype=np.float64)
                                        - np.asarray(current_residual, dtype=np.float64)
                                    ) / float(epsilon)
                                    fd_jvp_cache[int(support_col)] = (
                                        np.asarray(full_jvp, dtype=np.float64),
                                        float(epsilon),
                                    )
                                    refresh_jvp_norms.append(float(np.linalg.norm(full_jvp)))
                            else:
                                refresh_reason = (
                                    "hip_fd_batch_replay_disabled_or_empty_support"
                                )
                            if refresh_stable:
                                row_acceptance_refresh_meta.update(
                                    {
                                        "accepted_state_tangent_refresh_backend": (
                                            "hip_finite_difference_residual_jvp"
                                        ),
                                        "accepted_state_tangent_refresh_hip_used": True,
                                        "accepted_state_tangent_refresh_cpu_used": False,
                                        "accepted_state_tangent_refresh_column_count": int(
                                            len(refresh_support_cols)
                                        ),
                                        "accepted_state_tangent_refresh_support_source": (
                                            "accepted_candidate_support_columns"
                                        ),
                                        "accepted_state_tangent_refresh_residual_batch_backends": sorted(
                                            {
                                                str(meta.get("residual_batch_backend"))
                                                for meta in refresh_meta_rows
                                                if meta.get("residual_batch_backend")
                                            }
                                        ),
                                        "accepted_state_tangent_refresh_jvp_l2_min": float(
                                            min(refresh_jvp_norms)
                                        )
                                        if refresh_jvp_norms
                                        else 0.0,
                                        "accepted_state_tangent_refresh_jvp_l2_max": float(
                                            max(refresh_jvp_norms)
                                        )
                                        if refresh_jvp_norms
                                        else 0.0,
                                    }
                                )
                            else:
                                row_acceptance_refresh_meta.update(
                                    {
                                        "accepted_state_tangent_refresh_backend": (
                                            "frozen_previous_support_graph_fd_residual_jvp"
                                        ),
                                        "accepted_state_tangent_refresh_cpu_used": False,
                                        "accepted_state_tangent_refresh_skipped_reason": (
                                            refresh_reason
                                        ),
                                        "frozen_support_graph_after_hip_residual_promotion": True,
                                        "frozen_support_graph_scope": (
                                            "support_selection_scaffold_only"
                                        ),
                                    }
                                )
                        else:
                            stop_after_row_promotion = True
                            row_acceptance_refresh_meta.update(
                                {
                                    "accepted_state_tangent_refresh_backend": (
                                        "not_refreshed_hip_required_row_correction"
                                    ),
                                    "accepted_state_tangent_refresh_cpu_used": False,
                                    "accepted_state_tangent_refresh_skipped_reason": (
                                        "hip_required_row_tangent_refresh_unavailable"
                                    ),
                                    "hip_required_tangent_refresh_unavailable_after_promotion": True,
                                    "stop_after_hip_residual_promotion": True,
                                }
                            )
                else:
                    row_acceptance_refresh_meta = {
                        "accepted_state_refresh_backend": "cpu_full_assembly",
                        "accepted_state_refresh_cpu_used": True,
                        "accepted_state_tangent_refresh_backend": "cpu_full_assembly",
                        "accepted_state_tangent_refresh_cpu_used": True,
                    }
                    if row_require_hip_batch_replay:
                        row_acceptance_refresh_meta.update(
                            {
                                "accepted_state_refresh_closure_blocked": True,
                                "accepted_state_refresh_closure_blocker": (
                                    "rocm_hip_row_acceptance_refresh_required_for_closure"
                                ),
                                "accepted_state_tangent_refresh_closure_blocked": True,
                                "accepted_state_tangent_refresh_closure_blocker": (
                                    "rocm_hip_row_tangent_refresh_required_for_closure"
                                ),
                            }
                        )
                    (
                        current_stiffness,
                        _current_f_ext,
                        current_free,
                        current_residual,
                        current_rhs,
                        _current_meta,
                    ) = assemble_residual(
                        current_u,
                        external_load_override=reference_f_ext,
                    )
                    if (
                        row_require_hip_batch_replay
                        and not (
                            current_free.shape == trial_frees[best_gate_trial_index].shape
                            and np.array_equal(
                                current_free,
                                trial_frees[best_gate_trial_index],
                            )
                        )
                    ):
                        row_acceptance_refresh_meta.update(
                            {
                                "accepted_state_refresh_closure_blocker": (
                                    "rocm_hip_row_acceptance_refresh_free_dof_mismatch"
                                )
                            }
                        )
                prior_cpu_residual_refresh = bool(
                    current_tangent_residual_row_correction.get(
                        "accepted_state_refresh_cpu_used"
                    )
                )
                prior_cpu_tangent_refresh = bool(
                    current_tangent_residual_row_correction.get(
                        "accepted_state_tangent_refresh_cpu_used"
                    )
                )
                if (
                    prior_cpu_residual_refresh
                    and not row_acceptance_refresh_meta.get(
                        "accepted_state_refresh_cpu_used"
                    )
                ):
                    row_acceptance_refresh_meta[
                        "accepted_state_refresh_prior_cpu_used"
                    ] = True
                    row_acceptance_refresh_meta[
                        "accepted_state_refresh_cpu_used"
                    ] = True
                if (
                    prior_cpu_tangent_refresh
                    and not row_acceptance_refresh_meta.get(
                        "accepted_state_tangent_refresh_cpu_used"
                    )
                ):
                    row_acceptance_refresh_meta[
                        "accepted_state_tangent_refresh_prior_cpu_used"
                    ] = True
                    row_acceptance_refresh_meta[
                        "accepted_state_tangent_refresh_cpu_used"
                    ] = True
                pass_payload.update(row_acceptance_refresh_meta)
                current_tangent_residual_row_correction.update(
                    row_acceptance_refresh_meta
                )
                accepted_state_history.append(np.asarray(current_u, dtype=np.float64).copy())
                accepted_residual_history.append(np.asarray(current_residual, dtype=np.float64).copy())
                if stop_after_row_promotion:
                    pass_payload["reason"] = (
                        "hip_required_row_tangent_refresh_unavailable_after_promotion"
                    )
                    current_tangent_residual_row_correction["stop_reason"] = str(
                        pass_payload["reason"]
                    )
                    break
            if max_row_promotions == 0:
                current_tangent_residual_row_correction["stop_reason"] = "max_promotions_zero"
            elif promotion_count >= max_row_promotions:
                current_tangent_residual_row_correction["stop_reason"] = (
                    "max_promotions_exhausted"
                )
            best_candidate_row = (
                min(all_trial_rows, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_trial_rows
                else None
            )
            best_gate_candidate_row = (
                min(all_gate_candidates, key=lambda row: float(row["direct_residual_inf_n"]))
                if all_gate_candidates
                else None
            )
            current_tangent_residual_row_correction.update(
                {
                    "accepted": bool(promotion_count),
                    "promoted_to_final_state": bool(promotion_count),
                    "promotion_count": int(promotion_count),
                    "passes": pass_rows,
                    "trial_rows": all_trial_rows,
                    "best_candidate": best_candidate_row,
                    "best_gate_eligible_candidate": best_gate_candidate_row,
                    "residual_only_eval_count": int(row_residual_only_eval_count),
                    "full_assembly_eval_count": int(row_full_assembly_eval_count),
                    "per_state_batch_replay_batch_count": int(
                        row_per_state_replay_batch_count
                    ),
                    "per_state_batch_replay_state_count": int(
                        row_per_state_replay_state_count
                    ),
                    "per_state_batch_replay_seconds": float(
                        row_per_state_replay_seconds
                    ),
                    "batch_alpha_replay_batch_count": int(
                        row_batch_alpha_replay_batch_count
                    ),
                    "batch_alpha_replay_state_count": int(
                        row_batch_alpha_replay_state_count
                    ),
                    "batch_alpha_replay_seconds": float(row_batch_alpha_replay_seconds),
                    "batch_fd_replay_batch_count": int(row_batch_fd_replay_batch_count),
                    "batch_fd_replay_state_count": int(row_batch_fd_replay_state_count),
                    "batch_fd_replay_seconds": float(row_batch_fd_replay_seconds),
                    "residual_descent": bool(
                        best_candidate_row
                        and float(best_candidate_row["direct_residual_inf_n"])
                        < base_residual_inf
                    ),
                }
            )

    if (
        matrix_free_global_krylov.get("accepted_state_tangent_refresh_deferred_to")
        == GLOBAL_TANGENT_REFRESH_DEFERRED_TO_ROW
    ):
        row_tangent_backend = str(
            current_tangent_residual_row_correction.get(
                "accepted_state_tangent_refresh_backend", ""
            )
            or ""
        )
        if _row_tangent_refresh_closes_global_defer(
            current_tangent_residual_row_correction
        ):
            matrix_free_global_krylov.update(
                {
                    "accepted_state_tangent_refresh_backend": (
                        "current_tangent_residual_row_hip_finite_difference_residual_jvp"
                    ),
                    "accepted_state_tangent_refresh_hip_used": True,
                    "accepted_state_tangent_refresh_cpu_used": False,
                    "accepted_state_tangent_refresh_deferred_satisfied": True,
                    "accepted_state_tangent_refresh_deferred_backend": row_tangent_backend,
                    "accepted_state_tangent_refresh_deferred_column_count": int(
                        current_tangent_residual_row_correction.get(
                            "accepted_state_tangent_refresh_column_count", 0
                        )
                        or 0
                    ),
                }
            )
            matrix_free_global_krylov.pop(
                "accepted_state_tangent_refresh_closure_blocked", None
            )
            matrix_free_global_krylov.pop(
                "accepted_state_tangent_refresh_closure_blocker", None
            )
        else:
            matrix_free_global_krylov[
                "accepted_state_tangent_refresh_closure_blocked"
            ] = True
            matrix_free_global_krylov[
                "accepted_state_tangent_refresh_closure_blocker"
            ] = GLOBAL_TANGENT_REFRESH_DEFERRED_BLOCKER
            matrix_free_global_krylov[
                "accepted_state_tangent_refresh_deferred_backend"
            ] = row_tangent_backend
            matrix_free_global_krylov[
                "accepted_state_tangent_refresh_deferred_satisfied"
            ] = False

    best_candidate = (
        min(candidate_rows, key=lambda row: float(row["direct_residual_inf_n"])) if candidate_rows else {}
    )
    best_improved = bool(
        best_candidate and float(best_candidate["direct_residual_inf_n"]) < base_residual_inf
    )
    final_gate_candidate = best_candidate
    if bool(secant_subspace_globalization.get("promoted_to_final_state")) and isinstance(
        secant_subspace_globalization.get("best_gate_eligible_candidate"), dict
    ):
        final_gate_candidate = secant_subspace_globalization["best_gate_eligible_candidate"]
    if bool(matrix_free_jacobian_subspace.get("promoted_to_final_state")) and isinstance(
        matrix_free_jacobian_subspace.get("best_gate_eligible_candidate"), dict
    ):
        final_gate_candidate = matrix_free_jacobian_subspace["best_gate_eligible_candidate"]
    if bool(matrix_free_global_krylov.get("promoted_to_final_state")) and isinstance(
        matrix_free_global_krylov.get("best_gate_eligible_candidate"), dict
    ):
        final_gate_candidate = matrix_free_global_krylov["best_gate_eligible_candidate"]
    if bool(current_tangent_residual_row_correction.get("promoted_to_final_state")) and isinstance(
        current_tangent_residual_row_correction.get("best_gate_eligible_candidate"), dict
    ):
        final_gate_candidate = current_tangent_residual_row_correction[
            "best_gate_eligible_candidate"
        ]
    final_direct_residual_inf = (
        float(np.max(np.abs(current_residual))) if current_residual.size else base_residual_inf
    )
    final_component_breakdown: dict[str, Any] | None = None
    if include_residual_component_breakdown:
        (
            _component_stiffness,
            _component_f_ext,
            component_free,
            component_residual,
            component_rhs,
            component_meta,
        ) = assemble_residual(
            current_u,
            external_load_override=reference_f_ext,
            include_component_forces=True,
        )
        component_forces = component_meta.pop("component_forces", {})
        final_component_breakdown = _component_breakdown(
            component_forces=(
                component_forces if isinstance(component_forces, dict) else {}
            ),
            free=np.asarray(component_free, dtype=np.int64),
            residual=np.asarray(component_residual, dtype=np.float64),
            rhs=np.asarray(component_rhs, dtype=np.float64),
            top_count=int(residual_component_breakdown_top_count),
        )
    direct_residual_gate_passed = bool(final_direct_residual_inf <= residual_tolerance_n)
    relative_increment_gate_verified = bool(final_gate_candidate)
    relative_increment_gate_passed = bool(
        final_gate_candidate.get("relative_increment_gate_passed")
    )
    cpu_acceptance_refresh_closure_blocked = bool(
        _cpu_acceptance_refresh_closure_blocked(matrix_free_global_krylov)
        or _cpu_acceptance_refresh_closure_blocked(
            current_tangent_residual_row_correction
        )
    )
    fallback_zero_audit = _g1_fallback_zero_audit(
        matrix_free_global_krylov,
        current_tangent_residual_row_correction,
    )
    fallback_zero_passed = bool(fallback_zero_audit["fallback_zero_passed"])
    hip_residual_engine_contract = _g1_hip_residual_engine_contract(
        matrix_free_global_krylov,
        current_tangent_residual_row_correction,
    )
    hip_residual_engine_contract_passed = bool(
        hip_residual_engine_contract["hip_residual_engine_contract_passed"]
    )
    hip_residual_engine_required = bool(
        hip_residual_engine_contract["hip_residual_engine_required"]
    )
    hip_residual_engine_gate_passed = bool(
        not hip_residual_engine_required or hip_residual_engine_contract_passed
    )
    full_load_closure_gate = _full_load_closure_gate(load_scale)
    full_load_closure_passed = bool(full_load_closure_gate["passed"])
    converged = bool(
        best_improved
        and direct_residual_gate_passed
        and relative_increment_gate_passed
        and full_load_closure_passed
        and not cpu_acceptance_refresh_closure_blocked
        and fallback_zero_passed
        and hip_residual_engine_gate_passed
    )
    output_final_checkpoint_meta: dict[str, Any] | None = None
    final_state_improved = final_direct_residual_inf < base_residual_inf
    if output_final_checkpoint_npz is not None and final_state_improved:
        output_final_checkpoint_npz.parent.mkdir(parents=True, exist_ok=True)
        final_translation_metrics = _translation_metrics(current_u, node_xyz)
        checkpoint_payload: dict[str, Any] = {
            "checkpoint_schema": np.asarray("mgt-direct-residual-newton-state.v1"),
            "source_schema_version": np.asarray(SCHEMA_VERSION),
            "load_scale": np.asarray(load_scale, dtype=np.float64),
            "displacement_u": np.asarray(current_u, dtype=np.float64),
            "residual_inf_n": np.asarray(final_direct_residual_inf, dtype=np.float64),
            "direct_residual_inf_n": np.asarray(final_direct_residual_inf, dtype=np.float64),
            "direct_relative_residual_inf": np.asarray(
                final_direct_residual_inf
                / max(float(np.max(np.abs(current_rhs))) if current_rhs.size else rhs_inf, 1.0),
                dtype=np.float64,
            ),
            "max_translation_m": np.asarray(
                final_translation_metrics["max_translation_m"],
                dtype=np.float64,
            ),
            "accepted_history_count": np.asarray(0, dtype=np.int64),
            "source_checkpoint_path": np.asarray(str(checkpoint_npz)),
            "shell_pressure_load_path_policy": np.asarray(str(shell_pressure_load_path_policy)),
            "compact_checkpoint": np.asarray(bool(compact_output_final_checkpoint)),
        }
        accepted_history_count = 0
        if not compact_output_final_checkpoint:
            accepted_state_history_array = np.vstack(
                [np.asarray(row, dtype=np.float64) for row in accepted_state_history]
            )
            accepted_residual_history_array = np.vstack(
                [np.asarray(row, dtype=np.float64) for row in accepted_residual_history]
            )
            accepted_history_count = int(accepted_state_history_array.shape[0])
            checkpoint_payload.update(
                {
                    "accepted_state_history_u": accepted_state_history_array,
                    "accepted_residual_history": accepted_residual_history_array,
                    "accepted_history_count": np.asarray(
                        accepted_history_count,
                        dtype=np.int64,
                    ),
                }
            )
        np.savez_compressed(output_final_checkpoint_npz, **checkpoint_payload)
        output_final_checkpoint_meta = {
            "written": True,
            "path": str(output_final_checkpoint_npz),
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": float(load_scale),
            "dof_count": int(current_u.size),
            "direct_residual_inf_n": float(final_direct_residual_inf),
            "max_translation_m": float(final_translation_metrics["max_translation_m"]),
            "accepted_history_count": int(accepted_history_count),
            "compact_checkpoint": bool(compact_output_final_checkpoint),
            "source_checkpoint_path": str(checkpoint_npz),
            "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        }
    elif output_final_checkpoint_npz is not None:
        output_final_checkpoint_meta = _skipped_output_final_checkpoint_meta(
            output_final_checkpoint_npz=output_final_checkpoint_npz,
            checkpoint_npz=checkpoint_npz,
            final_direct_residual_inf=final_direct_residual_inf,
            reason="no_residual_descent",
        )
    hip_batch_replay_required_unavailable = bool(
        matrix_free_global_krylov.get("hip_batch_replay_required_unavailable")
        or current_tangent_residual_row_correction.get(
            "hip_batch_replay_required_unavailable"
        )
    )
    hip_krylov_solver_required_unavailable = bool(
        matrix_free_global_krylov.get("hip_krylov_solver_required_unavailable")
    )
    host_krylov_solver_closure_blocked = bool(
        matrix_free_global_krylov.get("host_krylov_solver_closure_blocked")
    )
    material_newton_breadth_blockers = [
        "material_newton_breadth_not_proven",
    ]
    consistent_residual_jacobian_newton_blockers = [
        "consistent_residual_jacobian_newton_not_proven",
    ]
    if apply_shell_material_tangent and allow_state_dependent_shell_material_tangent_hip_replay:
        material_newton_breadth_blockers.append(
            "state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency"
        )
        consistent_residual_jacobian_newton_blockers.append(
            "state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "status": "ready" if converged else "partial",
        "direct_residual_newton_ready": converged,
        "checkpoint": checkpoint_meta,
        "source": {
            "mgt_path": str(mgt_path),
            "provenance": "repo_benchmark_bridge",
        },
        "residual_contract": {
            "definition": "R(u, lambda) = F_int(u) - lambda * F_ext",
            "physical_internal_force_model": assembly_meta.get("physical_internal_force_model"),
            "direct_residual_uses_solver_regularization": False,
            "regularization_used_only_for_linear_correction_direction": True,
            "external_load_vector_configuration": "reference",
            "external_load_vector_reassembled_with_displacement": False,
            "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
            "shell_pressure_load_path_meta": pressure_load_path_meta,
            "shell_material_tangent_residual_applied": bool(apply_shell_material_tangent),
            "material_newton_gate_passed": False,
            "state_dependent_material_newton_closure_passed": False,
            "consistent_residual_jacobian_newton_gate_passed": False,
            "consistent_residual_jacobian_newton_blockers": (
                consistent_residual_jacobian_newton_blockers
            ),
            "material_newton_breadth_blockers": material_newton_breadth_blockers,
            "allow_frozen_shell_material_tangent_hip_replay": bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": bool(
                apply_shell_material_tangent
                and allow_frozen_shell_material_tangent_hip_replay
            ),
            "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": bool(
                apply_shell_material_tangent
                and allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "frame_geometric_equilibrium_included": True,
            "authored_support_restraints_included": True,
            "finite_elastic_link_springs_included": True,
            "shell_surface_equilibrium_included": True,
            "service_material_tangent_used_for_newton_direction_only": True,
            "quasi_tangent_residual_inf_n": assembly_meta.get("quasi_tangent_residual_inf_n"),
            "directional_residual_jacobian_globalization_included": True,
            "secant_family_globalization_included": bool(
                enable_secant_family_globalization
            ),
            "matrix_free_consistent_jacobian_subspace_included": bool(
                enable_matrix_free_jacobian_subspace
            ),
            "matrix_free_global_krylov_included": bool(enable_matrix_free_global_krylov),
            "current_tangent_residual_row_correction_included": bool(
                enable_current_tangent_residual_row_correction
            ),
            "residual_component_breakdown_included": bool(
                include_residual_component_breakdown
            ),
            "finite_difference_residual_row_jacobian_included": bool(
                enable_current_tangent_residual_row_correction
                and str(current_tangent_residual_row_jacobian_mode).strip()
                == "finite_difference"
            ),
            **hip_residual_engine_contract,
        },
        "mesh_fingerprint": {
            **frame_select_meta,
            "node_count": int(checkpoint_meta["dof_count"] // DOF_PER_NODE),
            "reference_external_load_meta": reference_meta,
            "shell_pressure_load_path_meta": pressure_load_path_meta,
            **assembly_meta,
        },
        "boundary_summary": {
            **support_meta,
            **spring_meta,
        },
        "base_direct_residual": {
            "load_scale": load_scale,
            "direct_residual_inf_n": base_residual_inf,
            "direct_residual_l2_n": base_residual_l2,
            "direct_relative_residual_inf": base_residual_inf / max(rhs_inf, 1.0),
            "rhs_inf_n": rhs_inf,
            "linear_correction_regularization": base_regularization,
            "regularized_residual_inf_n": float(np.max(np.abs(regularized_residual)))
            if regularized_residual.size
            else 0.0,
            "fixed_point_receipt_residual_inf_n": checkpoint_meta.get("residual_inf_n"),
            "fixed_point_receipt_relative_increment": checkpoint_meta.get(
                "fixed_point_relative_increment"
            ),
            "residual_component_breakdown": base_component_breakdown,
        },
        "final_direct_residual": {
            "direct_residual_inf_n": final_direct_residual_inf,
            "direct_relative_residual_inf": final_direct_residual_inf
            / max(float(np.max(np.abs(current_rhs))) if current_rhs.size else rhs_inf, 1.0),
            "residual_gate_passed": direct_residual_gate_passed,
            "accepted_trust_region_iteration_count": int(accepted_count),
            "secant_subspace_globalization_accepted": bool(
                secant_subspace_globalization.get("accepted")
            ),
            "secant_family_globalization_accepted": bool(
                secant_family_globalization.get("accepted")
            ),
            "current_tangent_residual_row_correction_accepted": bool(
                current_tangent_residual_row_correction.get("accepted")
            ),
            "matrix_free_global_krylov_accepted": bool(
                matrix_free_global_krylov.get("accepted")
            ),
            "improvement_factor": base_residual_inf / max(final_direct_residual_inf, 1.0e-30),
            "residual_component_breakdown": final_component_breakdown,
        },
        "gate_assessment": {
            "residual_tolerance_n": float(residual_tolerance_n),
            "direct_residual_gate_passed": direct_residual_gate_passed,
            "relative_increment_tolerance": float(relative_increment_tolerance),
            "relative_increment_gate_verified": relative_increment_gate_verified,
            "relative_increment_gate_passed": relative_increment_gate_passed,
            "direct_residual_newton_ready_requires_increment_gate": True,
            "full_load_closure_gate": full_load_closure_gate,
            "full_load_closure_passed": full_load_closure_passed,
            "direct_residual_newton_ready_requires_full_load": True,
            "material_newton_breadth_passed": False,
            "material_newton_breadth_blockers": material_newton_breadth_blockers,
            "consistent_residual_jacobian_newton_passed": False,
            "consistent_residual_jacobian_newton_blockers": (
                consistent_residual_jacobian_newton_blockers
            ),
            "hip_batch_replay_required_unavailable": (
                hip_batch_replay_required_unavailable
            ),
            "host_krylov_solver_closure_blocked": (
                host_krylov_solver_closure_blocked
            ),
            "hip_krylov_solver_required_unavailable": (
                hip_krylov_solver_required_unavailable
            ),
            "hip_residual_engine_gate_passed": hip_residual_engine_gate_passed,
            "cpu_acceptance_refresh_closure_blocked": (
                cpu_acceptance_refresh_closure_blocked
            ),
            "fallback_zero_audit": fallback_zero_audit,
            "fallback_zero_passed": fallback_zero_passed,
        },
        "newton_direction": {
            "linearized_tangent": (
                "current service-material frame tangent plus frame geometric delta plus "
                + (
                    "state shell material tangent"
                    if apply_shell_material_tangent
                    else "elastic shell tangent"
                )
                + " plus finite springs"
            ),
            "regularization": last_regularization,
            "correction_inf_m": last_correction_inf,
            "linear_solve_seconds": last_solve_seconds,
        },
        "trust_region_line_search": {
            "alpha_values": [float(value) for value in alpha_values],
            "directional_jacobian_probe_alpha": float(directional_jacobian_probe_alpha),
            "max_trust_iterations": int(max_trust_iterations),
            "accepted_iteration_count": int(accepted_count),
            "iterations": trust_iterations,
            "candidate_rows": candidate_rows,
            "best_candidate": best_candidate,
            "accepted": best_improved,
        },
        "secant_subspace_globalization": secant_subspace_globalization,
        "secant_family_globalization": secant_family_globalization,
        "matrix_free_consistent_jacobian_subspace": matrix_free_jacobian_subspace,
        "matrix_free_global_krylov": matrix_free_global_krylov,
        "current_tangent_residual_row_correction": current_tangent_residual_row_correction,
        "runtime_metrics": {
            "initial_assembly_seconds": assembly_seconds,
            "total_seconds": time.perf_counter() - started,
        },
        "output_final_checkpoint": output_final_checkpoint_meta,
        "claim_boundary": (
            "This is the direct residual/Jacobian bridge required before G1 closure. It evaluates "
            "the physical residual without solver regularization and iterates regularized Newton "
            "correction directions with trust-region line-search plus a directional finite-difference "
            "residual-Jacobian alpha probe, accepted-history secant subspace, an opt-in "
            "ridge/windowed secant-family subspace, and matrix-free finite-difference "
            "consistent-Jacobian subspace, an opt-in global matrix-free residual-JVP Krylov "
            "direction, plus a current-tangent residual-row least-squares correction. It is not full closure unless both direct residual and "
            "increment gates pass at full load scale 1.0."
            + (
                f" Current checkpoint load scale is {load_scale:.15g}, so this "
                "receipt is sub-full-load diagnostic evidence and cannot close "
                "full G1."
                if not full_load_closure_passed
                else ""
            )
            + (
                " Per-state residual-row HIP batch replay only routes individual "
                "diagnostic trial residual evaluations through the selected HIP "
                "residual backend; it does not close full G1, full-load/full-mesh "
                "equilibrium, material Newton breadth, or production ROCm/HIP "
                "residency."
                if current_tangent_residual_row_per_state_batch_replay
                else ""
            )
            + (
                " Frozen shell-material tangent HIP replay freezes the current accepted "
                "state shell material CSR for ROCm/HIP residual replay; it is not "
                "state-dependent material Newton closure."
                if apply_shell_material_tangent
                and allow_frozen_shell_material_tangent_hip_replay
                else ""
            )
            + (
                " State-dependent shell-material tangent HIP replay computes the "
                "shell material tangent from each candidate state and evaluates "
                "through a candidate-specific HIP backend. Shell CSR/operator refresh "
                "happens on host; this is state-dependent material tangent HIP "
                "residual replay but not full production ROCm/HIP residency closure."
                if apply_shell_material_tangent
                and allow_state_dependent_shell_material_tangent_hip_replay
                else ""
            )
        ),
        "blockers": []
        if converged
        else [
            *(
                ["rocm_hip_batch_replay_required_unavailable"]
                if hip_batch_replay_required_unavailable
                else []
            ),
            *(
                ["rocm_hip_krylov_solver_required_for_closure"]
                if host_krylov_solver_closure_blocked
                else []
            ),
            *(
                ["rocm_hip_krylov_solver_unavailable"]
                if hip_krylov_solver_required_unavailable
                else []
            ),
            *(
                ["rocm_hip_acceptance_refresh_required_for_closure"]
                if cpu_acceptance_refresh_closure_blocked
                else []
            ),
            *(
                [
                    "hip_residual_engine_contract_not_closed",
                    *[
                        f"hip_residual_engine::{blocker}"
                        for blocker in hip_residual_engine_contract[
                            "hip_residual_engine_blockers"
                        ]
                    ],
                ]
                if hip_residual_engine_required
                and not hip_residual_engine_contract_passed
                else []
            ),
            *(["g1_fallback_zero_audit_not_closed"] if not fallback_zero_passed else []),
            *([] if direct_residual_gate_passed else ["direct_residual_gate_not_closed"]),
            *([] if full_load_closure_passed else ["full_load_gate_not_closed"]),
            *(
                []
                if relative_increment_gate_passed
                else ["relative_increment_gate_not_closed_or_not_verified"]
            ),
            "consistent_jacobian_or_globalization_required",
            "regularized_fixed_point_residual_must_not_be_used_as_physical_residual",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-final-checkpoint-npz",
        type=Path,
        default=None,
        help="Optional NPZ checkpoint containing the final direct-residual displacement state.",
    )
    parser.add_argument(
        "--compact-output-final-checkpoint",
        action="store_true",
        help=(
            "Write only displacement_u and scalar metadata to the final checkpoint, "
            "omitting accepted history arrays."
        ),
    )
    parser.add_argument("--frame-gravity-load-scale", type=float, default=0.01)
    parser.add_argument("--stiffness-scale-to-si", type=float, default=1000.0)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only", "structural_components_only"),
        default="all_components",
        help=(
            "Shell pressure load-path policy. all_components preserves legacy replay; "
            "attached_components_only suppresses pressure on shell surface components "
            "without a frame/support attachment; structural_components_only uses the same "
            "filter as the production structural load-path policy."
        ),
    )
    parser.add_argument(
        "--apply-shell-material-tangent",
        action="store_true",
        help=(
            "Use state-dependent bounded shell material tangents in the physical "
            "residual and Newton tangent assembly. This is CPU diagnostic evidence "
            "until the ROCm/HIP full residual backend consumes the same tangent field."
        ),
    )
    parser.add_argument(
        "--allow-frozen-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "When --apply-shell-material-tangent is enabled and a HIP residual batch "
            "replay backend is requested, freeze the current accepted state's shell "
            "material tangent CSR as a non-closure HIP operator and use HIP batch "
            "replay instead of falling back to CPU. This is frozen_shell_material_tangent_"
            "hip_replay, not state-dependent material Newton. Do not claim full material "
            "Newton closure from this path."
        ),
    )
    parser.add_argument(
        "--allow-state-dependent-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "When --apply-shell-material-tangent is enabled and a HIP residual batch "
            "replay backend is requested, compute the shell material tangent from each "
            "candidate state, build the candidate shell CSR, and evaluate that candidate "
            "residual through the selected HIP backend. This wins over --allow-frozen-"
            "shell-material-tangent-hip-replay. HIP-required prepare/evaluate failure "
            "suppresses CPU fallback. Shell CSR/operator refresh happens on host; this "
            "is not full production ROCm/HIP residency closure."
        ),
    )
    parser.add_argument(
        "--include-residual-component-breakdown",
        action="store_true",
        help=(
            "Record base/final residual component top-row breakdowns from the same "
            "direct residual assembly used by this probe."
        ),
    )
    parser.add_argument(
        "--residual-component-breakdown-top-count",
        type=int,
        default=24,
        help="Number of top residual rows to include when component breakdown is enabled.",
    )
    parser.add_argument("--residual-tolerance-n", type=float, default=5.0e-4)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--max-trust-iterations", type=int, default=6)
    parser.add_argument("--directional-jacobian-probe-alpha", type=float, default=0.0000078125)
    parser.add_argument("--max-secant-subspace-promotions", type=int, default=6)
    parser.add_argument(
        "--disable-secant-subspace-globalization",
        action="store_true",
        help="Disable accepted-history secant subspace residual globalization.",
    )
    parser.add_argument(
        "--enable-secant-family-globalization",
        action="store_true",
        help=(
            "Enable opt-in windowed/ridge accepted-history secant family globalization. "
            "This reuses residual-correction history as a Newton auxiliary candidate, "
            "but only promotes candidates that pass residual descent and increment gates."
        ),
    )
    parser.add_argument("--max-secant-family-promotions", type=int, default=2)
    parser.add_argument(
        "--secant-family-window-sizes",
        default="4,8,16",
        help="Comma-separated recent secant-column window sizes for secant-family globalization.",
    )
    parser.add_argument(
        "--secant-family-ridge-factors",
        default="0,1e-8",
        help="Comma-separated ridge factors for secant-family least-squares candidates.",
    )
    parser.add_argument(
        "--secant-family-alpha-values",
        default="0.03125,0.015625,0.0078125,0.00390625",
        help="Comma-separated alpha candidates for secant-family globalization.",
    )
    parser.add_argument(
        "--secant-family-min-relative-improvement",
        type=float,
        default=1.0e-5,
    )
    parser.add_argument(
        "--disable-matrix-free-jacobian-subspace",
        action="store_true",
        help="Disable finite-difference consistent-Jacobian subspace correction.",
    )
    parser.add_argument("--matrix-free-jacobian-subspace-basis-size", type=int, default=2)
    parser.add_argument("--max-matrix-free-jacobian-subspace-promotions", type=int, default=8)
    parser.add_argument("--matrix-free-jacobian-probe-scale", type=float, default=0.25)
    parser.add_argument(
        "--matrix-free-jacobian-probe-scales",
        default="",
        help=(
            "Comma-separated finite-difference scales for matrix-free JVP scale selection. "
            "The legacy --matrix-free-jacobian-probe-scale is used if this is empty."
        ),
    )
    parser.add_argument(
        "--matrix-free-jacobian-difference-scheme",
        choices=("forward", "central"),
        default="forward",
        help="Finite-difference scheme for matrix-free residual JVP columns.",
    )
    parser.add_argument(
        "--matrix-free-jacobian-basis-sources",
        default="history",
        help=(
            "Comma-separated matrix-free JVP basis sources. Supported values are history "
            "and current_newton. The default preserves the accepted-history basis."
        ),
    )
    parser.add_argument(
        "--matrix-free-jacobian-probe-max-step",
        type=float,
        default=0.0,
        help=(
            "Optional cap on the infinity-norm displacement perturbation used for each "
            "matrix-free JVP probe. Zero keeps legacy scale-only behavior."
        ),
    )
    parser.add_argument(
        "--matrix-free-jacobian-ridge-factors",
        default="0",
        help=(
            "Comma-separated ridge factors for matrix-free JVP basis least-squares. "
            "lambda=factor*max(singular(J_basis),1)."
        ),
    )
    parser.add_argument(
        "--matrix-free-jacobian-allow-negative-alphas",
        action="store_true",
        help=(
            "Also evaluate negative signed line-search alphas for each matrix-free "
            "basis candidate. Candidates still need full residual replay and increment gates."
        ),
    )
    parser.add_argument(
        "--matrix-free-jacobian-max-alpha",
        type=float,
        default=1.0,
        help=(
            "Maximum absolute matrix-free JVP line-search alpha. The default preserves "
            "the legacy alpha clamp at 1.0."
        ),
    )
    parser.add_argument("--matrix-free-jacobian-min-relative-improvement", type=float, default=1.0e-5)
    parser.add_argument(
        "--enable-matrix-free-global-krylov",
        action="store_true",
        help=(
            "Enable an opt-in global GMRES direction using finite-difference direct-residual "
            "JVP matvecs. This is CPU diagnostic evidence and every candidate is replayed "
            "against the physical residual and increment gates."
        ),
    )
    parser.add_argument("--matrix-free-global-krylov-max-iterations", type=int, default=4)
    parser.add_argument(
        "--matrix-free-global-krylov-difference-scheme",
        choices=("forward", "central"),
        default="forward",
        help=(
            "Finite-difference stencil for global Krylov residual-JVP matvecs. "
            "central evaluates plus/minus residual probes and requires both free-DOF "
            "sets to remain stable."
        ),
    )
    parser.add_argument("--matrix-free-global-krylov-probe-epsilon", type=float, default=1.0e-6)
    parser.add_argument(
        "--matrix-free-global-krylov-probe-max-step",
        type=float,
        default=1.0e-5,
        help="Infinity-norm cap for each global Krylov finite-difference JVP probe.",
    )
    parser.add_argument(
        "--matrix-free-global-krylov-scaling-mode",
        choices=("none", "residual_diagonal_displacement"),
        default="none",
        help=(
            "Optional nondimensionalization for global Krylov: "
            "residual_diagonal_displacement solves D_r J D_u y = -D_r R."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-displacement-scale",
        type=float,
        default=1.0e-4,
        help="D_u scalar displacement scale in meters for scaled global Krylov.",
    )
    parser.add_argument(
        "--matrix-free-global-krylov-residual-scale-floor",
        type=float,
        default=1.0,
        help="Minimum residual magnitude used for D_r diagonal scaling.",
    )
    parser.add_argument(
        "--matrix-free-global-krylov-preconditioner-mode",
        choices=("none", "current_tangent"),
        default="none",
        help=(
            "Optional right preconditioner for global Krylov. current_tangent solves "
            "the current regularized tangent for every Krylov direction before "
            "finite-difference residual JVP replay."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-preconditioner-input-scale",
        type=float,
        default=1.0,
        help=(
            "Scalar force-like input scale applied before the current-tangent right "
            "preconditioner. Ignored when the preconditioner mode is none."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-tangent-regularization-factor",
        type=float,
        default=1.0e-8,
        help=(
            "Regularization factor for the current-tangent right preconditioner: "
            "lambda=factor*max(mean(abs(diag(K))),1)."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-allow-negative-alphas",
        action="store_true",
        help="Also evaluate negative signed line-search alphas for global matrix-free Krylov.",
    )
    parser.add_argument(
        "--matrix-free-global-krylov-max-alpha",
        type=float,
        default=1.0,
        help=(
            "Maximum absolute line-search alpha for global matrix-free Krylov. "
            "The default preserves the legacy clamp at 1.0."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-alpha-values",
        default="0.03125,0.015625,0.0078125,0.00390625",
        help="Comma-separated line-search alpha candidates for the global matrix-free Krylov direction.",
    )
    parser.add_argument(
        "--matrix-free-global-krylov-min-relative-improvement",
        type=float,
        default=1.0e-6,
    )
    parser.add_argument(
        "--matrix-free-global-krylov-full-assembly-trial-replay",
        action="store_true",
        help=(
            "Replay global matrix-free Krylov line-search candidates through the full "
            "Newton tangent/physical residual assembly and use that residual for "
            "promotion gating."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-batch-replay-backend",
        choices=("cpu", "hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"),
        default="cpu",
        help=(
            "Residual replay backend for global Krylov residual probes and line-search "
            "trials. HIP backends use the native full-residual batch engine."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-require-hip-batch-replay",
        action="store_true",
        help=(
            "Require a HIP global Krylov residual replay backend and suppress CPU "
            "batch fallback."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-linear-solver-backend",
        choices=("scipy_host_gmres", "torch_hip_gmres"),
        default="scipy_host_gmres",
        help=(
            "Linear Krylov solver backend for the global matrix-free direction. "
            "torch_hip_gmres runs the Arnoldi/least-squares vector algebra on a "
            "ROCm torch HIP device and does not fall back to SciPy GMRES if HIP is "
            "unavailable."
        ),
    )
    parser.add_argument(
        "--enable-current-tangent-residual-row-correction",
        action="store_true",
        help="Enable experimental current-tangent residual-row least-squares correction.",
    )
    parser.add_argument("--max-current-tangent-residual-row-corrections", type=int, default=2)
    parser.add_argument(
        "--current-tangent-residual-row-min-relative-improvement",
        type=float,
        default=1.0e-5,
    )
    parser.add_argument(
        "--current-tangent-residual-row-target-counts",
        default="1,2",
        help="Comma-separated counts of largest residual rows for current-tangent row correction.",
    )
    parser.add_argument(
        "--current-tangent-residual-row-target-mode",
        choices=(
            "largest_rows",
            "residual_node_blocks",
            "residual_element_blocks",
            "residual_frame_element_blocks",
            "residual_shell_element_blocks",
            "residual_shell_bending_drilling_rows",
            "residual_shell_normal_rows",
            "residual_shell_geometry_normal_rows",
            "residual_shell_geometry_normal_bending_rows",
            "frontier_component_rows",
            "current_component_rows",
        ),
        default="largest_rows",
        help=(
            "Target selection mode for current-tangent row correction. largest_rows uses scalar "
            "residual rows; residual_node_blocks selects high-residual nodes and targets every "
            "free DOF row on those nodes; residual_element_blocks selects high-residual "
            "mesh elements and targets every free DOF row on their connected nodes; "
            "residual_frame_element_blocks restricts element seeds to frame elements; "
            "residual_shell_element_blocks restricts element seeds to shell elements "
            "and targets every free DOF row on their connected nodes; "
            "residual_shell_bending_drilling_rows restricts element seeds to shell "
            "elements and targets rotational rx/ry/rz rows; "
            "residual_shell_normal_rows restricts element seeds to shell elements and targets "
            "their global-z normal translation rows; residual_shell_geometry_normal_rows "
            "uses shell element geometry to target global translation rows aligned with "
            "the local shell normal; residual_shell_geometry_normal_bending_rows unions "
            "geometry-normal translation rows with shell rx/ry/rz bending/drilling rows; "
            "frontier_component_rows loads component-balanced hotspot rows from a "
            "residual/Jacobian frontier probe JSON; current_component_rows recomputes "
            "component-balanced hotspot rows from the current pass residual."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-frontier-probe-json",
        type=Path,
        default=None,
        help=(
            "Frontier probe JSON used by frontier_component_rows target mode. "
            "Rows are read from residual_component_breakdown.top_rows."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-frontier-component-scale-mode",
        choices=("none", "dominant_component_magnitude", "total_component_magnitude"),
        default="none",
        help=(
            "Optional row-equation scaling for frontier_component_rows. "
            "The component magnitude modes divide each target equation by the "
            "selected row's dominant or total component force scale."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-shell-normal-participation-threshold",
        type=float,
        default=0.7071067811865476,
        help=(
            "Minimum |dot(global translation axis, shell normal)| for "
            "residual_shell_geometry_normal_rows target selection."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-element-neighbor-depth",
        type=int,
        default=0,
        help=(
            "When target mode is residual_element_blocks, expand selected seed elements "
            "by this many shared-node element-neighbor layers before collecting target rows."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-support-column-counts",
        default="4,8",
        help="Comma-separated strongest tangent column counts per target row.",
    )
    parser.add_argument(
        "--current-tangent-residual-row-support-expansion-depth",
        type=int,
        default=0,
        help="Graph expansion depth for current-tangent residual-row correction support columns.",
    )
    parser.add_argument(
        "--current-tangent-residual-row-support-selection",
        choices=("row_strongest", "residual_weighted", "target_rows"),
        default="row_strongest",
        help=(
            "Support selection strategy for current-tangent residual-row correction. "
            "row_strongest preserves legacy per-target-row |K| selection; residual_weighted "
            "uses target residual magnitudes to score support columns globally; target_rows "
            "is finite-difference-only and uses selected target rows as stiffness-free "
            "support columns."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-node-block-support",
        action="store_true",
        help=(
            "Expand selected support columns to all free DOF on the same structural nodes, "
            "making the row-active correction node-block consistent."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-jacobian-mode",
        choices=("current_tangent", "finite_difference"),
        default="current_tangent",
        help=(
            "Jacobian source for current-tangent row correction. finite_difference replaces "
            "the selected row/support submatrix with direct residual finite-difference JVP "
            "columns before solving the local least-squares problem."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-fd-epsilon",
        type=float,
        default=1.0e-6,
        help="Base displacement perturbation for finite-difference residual-row Jacobian columns.",
    )
    parser.add_argument(
        "--current-tangent-residual-row-fd-max-support-columns",
        type=int,
        default=12,
        help=(
            "Maximum support columns to finite-difference per row-correction candidate. "
            "If the selected support is larger, strongest tangent row-norm columns are kept."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-batch-fd-replay",
        action="store_true",
        help=(
            "Batch replay finite-difference residual-row support-column perturbations "
            "through the residual-only physical internal-force batch path. Requires "
            "--current-tangent-residual-row-use-residual-only-assembly."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-batch-fd-replay-chunk-size",
        type=int,
        default=64,
        help=(
            "Maximum finite-difference perturbation states per residual-row batch replay "
            "chunk."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-batch-replay-backend",
        choices=("cpu", "hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"),
        default="cpu",
        help=(
            "Backend for residual-row alpha/FD batch replay. hip_full_residual "
            "uses one native HIP subprocess per batch; hip_full_residual_resident "
            "keeps the native HIP worker and operator buffers resident; "
            "rust_hip_full_residual_ffi calls the native HIP C ABI through an "
            "in-process Rust FFI library."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-require-hip-batch-replay",
        action="store_true",
        help=(
            "Require a HIP residual-row batch backend and suppress CPU batch fallback. "
            "If HIP setup/evaluation fails, the row-correction attempt records a "
            "blocked HIP replay boundary instead of replaying candidates on CPU."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-hipcc",
        type=Path,
        default=Path("/opt/rocm/bin/hipcc"),
        help="hipcc path used when building the residual-row HIP batch backend.",
    )
    parser.add_argument(
        "--current-tangent-residual-row-force-rebuild-hip",
        action="store_true",
        help="Force rebuild of the residual-row HIP full residual batch backend.",
    )
    parser.add_argument(
        "--current-tangent-residual-row-ridge-factor",
        type=float,
        default=0.0,
        help=(
            "Optional ridge damping factor for row-correction least-squares. "
            "When positive, solve [A; lambda I] x ~= [b; 0] with "
            "lambda=factor*max(singular(A))."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-svd-relative-cutoff",
        type=float,
        default=0.0,
        help=(
            "Optional truncated-SVD relative cutoff for row-correction least-squares. "
            "When positive, singular directions below cutoff*max(singular(A)) are dropped."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-svd-max-condition",
        type=float,
        default=0.0,
        help=(
            "Optional truncated-SVD condition cap for row-correction least-squares. "
            "When positive, singular directions below max(singular(A))/cap are dropped."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-directional-probe-alpha",
        type=float,
        default=0.0,
        help=(
            "Optional finite-difference probe alpha used to add directional residual-Jacobian "
            "alpha candidates for current-tangent residual-row correction."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-use-residual-only-assembly",
        action="store_true",
        help=(
            "Use the residual-only assembly fast path for residual-row finite-difference "
            "columns and trial replays. Accepted-state tangent refreshes still use the full "
            "assembly path."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-per-state-batch-replay",
        action="store_true",
        help=(
            "Replay individual residual-row probe/candidate states through the selected "
            "residual batch backend when residual-only assembly is enabled. This is a "
            "diagnostic coverage path, not full G1 closure evidence."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-batch-alpha-replay",
        action="store_true",
        help=(
            "Batch replay residual-row alpha candidates through the residual-only physical "
            "internal-force batch path. Requires --current-tangent-residual-row-use-residual-only-assembly."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-allow-negative-alphas",
        action="store_true",
        help=(
            "Also replay negative signed alpha candidates for the current-tangent "
            "residual-row correction direction."
        ),
    )
    parser.add_argument(
        "--current-tangent-residual-row-alpha-values",
        default="0.03125,0.015625",
        help="Comma-separated base alpha candidates for current-tangent residual-row correction.",
    )
    parser.add_argument(
        "--matrix-free-jacobian-alpha-values",
        default="0.03125,0.015625,0.0078125,0.00390625",
    )
    parser.add_argument(
        "--alpha-values",
        default="0.001,0.0005,0.00025,0.000125,0.0000625,0.00003125,0.000015625,0.0000078125",
    )
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help=(
            "Acknowledge that this direct residual probe uses CPU SciPy sparse solves as a "
            "diagnostic only. ROCm/HIP closure evidence must come from mgt_rocm_sparse_solver_probe."
        ),
    )
    args = parser.parse_args(argv)
    if (
        args.current_tangent_residual_row_require_hip_batch_replay
        and args.current_tangent_residual_row_batch_replay_backend == "cpu"
    ):
        parser.error(
            "--current-tangent-residual-row-require-hip-batch-replay requires "
            "--current-tangent-residual-row-batch-replay-backend to be one of "
            "hip_full_residual, hip_full_residual_resident, or rust_hip_full_residual_ffi"
        )
    if (
        args.matrix_free_global_krylov_require_hip_batch_replay
        and args.matrix_free_global_krylov_batch_replay_backend == "cpu"
    ):
        parser.error(
            "--matrix-free-global-krylov-require-hip-batch-replay requires "
            "--matrix-free-global-krylov-batch-replay-backend to be one of "
            "hip_full_residual, hip_full_residual_resident, or rust_hip_full_residual_ffi"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global_cpu_diagnostic_enabled = bool(
        args.enable_matrix_free_global_krylov
        and not (
            args.matrix_free_global_krylov_require_hip_batch_replay
            and args.matrix_free_global_krylov_batch_replay_backend != "cpu"
        )
    )
    row_cpu_diagnostic_enabled = bool(
        args.enable_current_tangent_residual_row_correction
        and not (
            args.current_tangent_residual_row_require_hip_batch_replay
            and args.current_tangent_residual_row_batch_replay_backend != "cpu"
        )
    )
    explicit_hip_required = bool(
        (
            args.enable_matrix_free_global_krylov
            and args.matrix_free_global_krylov_require_hip_batch_replay
            and args.matrix_free_global_krylov_batch_replay_backend != "cpu"
        )
        or (
            args.enable_current_tangent_residual_row_correction
            and args.current_tangent_residual_row_require_hip_batch_replay
            and args.current_tangent_residual_row_batch_replay_backend != "cpu"
        )
    )
    needs_cpu_ack = bool(
        global_cpu_diagnostic_enabled
        or row_cpu_diagnostic_enabled
        or not explicit_hip_required
    )
    if needs_cpu_ack and not args.allow_cpu_diagnostic:
        print(
            "mgt-direct-residual-newton: blocked cpu diagnostic requires "
            "--allow-cpu-diagnostic; use scripts/run_mgt_rocm_sparse_solver_probe.py "
            "for ROCm/HIP closure evidence",
            file=sys.stderr,
        )
        return 2
    alpha_values = tuple(float(value.strip()) for value in str(args.alpha_values).split(",") if value.strip())
    matrix_free_jacobian_alpha_values = tuple(
        float(value.strip())
        for value in str(args.matrix_free_jacobian_alpha_values).split(",")
        if value.strip()
    )
    matrix_free_jacobian_probe_scales = tuple(
        float(value.strip())
        for value in str(args.matrix_free_jacobian_probe_scales).split(",")
        if value.strip()
    )
    matrix_free_jacobian_basis_sources = _parse_matrix_free_basis_sources(
        args.matrix_free_jacobian_basis_sources
    )
    matrix_free_jacobian_ridge_factors = tuple(
        float(value.strip())
        for value in str(args.matrix_free_jacobian_ridge_factors).split(",")
        if value.strip()
    )
    matrix_free_global_krylov_alpha_values = tuple(
        float(value.strip())
        for value in str(args.matrix_free_global_krylov_alpha_values).split(",")
        if value.strip()
    )
    secant_family_window_sizes = tuple(
        int(value.strip())
        for value in str(args.secant_family_window_sizes).split(",")
        if value.strip()
    )
    secant_family_ridge_factors = tuple(
        float(value.strip())
        for value in str(args.secant_family_ridge_factors).split(",")
        if value.strip()
    )
    secant_family_alpha_values = tuple(
        float(value.strip())
        for value in str(args.secant_family_alpha_values).split(",")
        if value.strip()
    )
    current_tangent_residual_row_target_counts = tuple(
        int(value.strip())
        for value in str(args.current_tangent_residual_row_target_counts).split(",")
        if value.strip()
    )
    current_tangent_residual_row_support_column_counts = tuple(
        int(value.strip())
        for value in str(args.current_tangent_residual_row_support_column_counts).split(",")
        if value.strip()
    )
    current_tangent_residual_row_alpha_values = tuple(
        float(value.strip())
        for value in str(args.current_tangent_residual_row_alpha_values).split(",")
        if value.strip()
    )
    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        compact_output_final_checkpoint=args.compact_output_final_checkpoint,
        frame_gravity_load_scale=args.frame_gravity_load_scale,
        stiffness_scale_to_si=args.stiffness_scale_to_si,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        apply_shell_material_tangent=args.apply_shell_material_tangent,
        allow_frozen_shell_material_tangent_hip_replay=args.allow_frozen_shell_material_tangent_hip_replay,
        allow_state_dependent_shell_material_tangent_hip_replay=(
            args.allow_state_dependent_shell_material_tangent_hip_replay
        ),
        include_residual_component_breakdown=(
            args.include_residual_component_breakdown
        ),
        residual_component_breakdown_top_count=(
            args.residual_component_breakdown_top_count
        ),
        residual_tolerance_n=args.residual_tolerance_n,
        relative_increment_tolerance=args.relative_increment_tolerance,
        max_trust_iterations=args.max_trust_iterations,
        directional_jacobian_probe_alpha=args.directional_jacobian_probe_alpha,
        enable_secant_subspace_globalization=not args.disable_secant_subspace_globalization,
        max_secant_subspace_promotions=args.max_secant_subspace_promotions,
        enable_secant_family_globalization=args.enable_secant_family_globalization,
        max_secant_family_promotions=args.max_secant_family_promotions,
        secant_family_window_sizes=secant_family_window_sizes or (4, 8, 16),
        secant_family_ridge_factors=secant_family_ridge_factors or (0.0, 1.0e-8),
        secant_family_alpha_values=(
            secant_family_alpha_values
            or (0.03125, 0.015625, 0.0078125, 0.00390625)
        ),
        secant_family_min_relative_improvement=(
            args.secant_family_min_relative_improvement
        ),
        enable_matrix_free_jacobian_subspace=not args.disable_matrix_free_jacobian_subspace,
        matrix_free_jacobian_subspace_basis_size=args.matrix_free_jacobian_subspace_basis_size,
        max_matrix_free_jacobian_subspace_promotions=args.max_matrix_free_jacobian_subspace_promotions,
        matrix_free_jacobian_probe_scale=args.matrix_free_jacobian_probe_scale,
        matrix_free_jacobian_probe_scales=matrix_free_jacobian_probe_scales,
        matrix_free_jacobian_difference_scheme=(
            args.matrix_free_jacobian_difference_scheme
        ),
        matrix_free_jacobian_basis_sources=matrix_free_jacobian_basis_sources,
        matrix_free_jacobian_probe_max_step=args.matrix_free_jacobian_probe_max_step,
        matrix_free_jacobian_ridge_factors=matrix_free_jacobian_ridge_factors,
        matrix_free_jacobian_allow_negative_alphas=(
            args.matrix_free_jacobian_allow_negative_alphas
        ),
        matrix_free_jacobian_max_alpha=args.matrix_free_jacobian_max_alpha,
        matrix_free_jacobian_min_relative_improvement=(
            args.matrix_free_jacobian_min_relative_improvement
        ),
        enable_matrix_free_global_krylov=args.enable_matrix_free_global_krylov,
        matrix_free_global_krylov_max_iterations=(
            args.matrix_free_global_krylov_max_iterations
        ),
        matrix_free_global_krylov_difference_scheme=(
            args.matrix_free_global_krylov_difference_scheme
        ),
        matrix_free_global_krylov_probe_epsilon=(
            args.matrix_free_global_krylov_probe_epsilon
        ),
        matrix_free_global_krylov_probe_max_step=(
            args.matrix_free_global_krylov_probe_max_step
        ),
        matrix_free_global_krylov_scaling_mode=(
            args.matrix_free_global_krylov_scaling_mode
        ),
        matrix_free_global_krylov_displacement_scale=(
            args.matrix_free_global_krylov_displacement_scale
        ),
        matrix_free_global_krylov_residual_scale_floor=(
            args.matrix_free_global_krylov_residual_scale_floor
        ),
        matrix_free_global_krylov_preconditioner_mode=(
            args.matrix_free_global_krylov_preconditioner_mode
        ),
        matrix_free_global_krylov_preconditioner_input_scale=(
            args.matrix_free_global_krylov_preconditioner_input_scale
        ),
        matrix_free_global_krylov_tangent_regularization_factor=(
            args.matrix_free_global_krylov_tangent_regularization_factor
        ),
        matrix_free_global_krylov_allow_negative_alphas=(
            args.matrix_free_global_krylov_allow_negative_alphas
        ),
        matrix_free_global_krylov_max_alpha=args.matrix_free_global_krylov_max_alpha,
        matrix_free_global_krylov_alpha_values=(
            matrix_free_global_krylov_alpha_values
            or (0.03125, 0.015625, 0.0078125, 0.00390625)
        ),
        matrix_free_global_krylov_min_relative_improvement=(
            args.matrix_free_global_krylov_min_relative_improvement
        ),
        matrix_free_global_krylov_full_assembly_trial_replay=(
            args.matrix_free_global_krylov_full_assembly_trial_replay
        ),
        matrix_free_global_krylov_batch_replay_backend=(
            args.matrix_free_global_krylov_batch_replay_backend
        ),
        matrix_free_global_krylov_require_hip_batch_replay=(
            args.matrix_free_global_krylov_require_hip_batch_replay
        ),
        matrix_free_global_krylov_linear_solver_backend=(
            args.matrix_free_global_krylov_linear_solver_backend
        ),
        enable_current_tangent_residual_row_correction=(
            args.enable_current_tangent_residual_row_correction
        ),
        max_current_tangent_residual_row_corrections=(
            args.max_current_tangent_residual_row_corrections
        ),
        current_tangent_residual_row_min_relative_improvement=(
            args.current_tangent_residual_row_min_relative_improvement
        ),
        current_tangent_residual_row_target_counts=(
            current_tangent_residual_row_target_counts or (1, 2)
        ),
        current_tangent_residual_row_target_mode=(
            args.current_tangent_residual_row_target_mode
        ),
        current_tangent_residual_row_frontier_probe_json=(
            args.current_tangent_residual_row_frontier_probe_json
        ),
        current_tangent_residual_row_frontier_component_scale_mode=(
            args.current_tangent_residual_row_frontier_component_scale_mode
        ),
        current_tangent_residual_row_element_neighbor_depth=(
            args.current_tangent_residual_row_element_neighbor_depth
        ),
        current_tangent_residual_row_support_column_counts=(
            current_tangent_residual_row_support_column_counts or (4, 8)
        ),
        current_tangent_residual_row_support_expansion_depth=(
            args.current_tangent_residual_row_support_expansion_depth
        ),
        current_tangent_residual_row_support_selection=(
            args.current_tangent_residual_row_support_selection
        ),
        current_tangent_residual_row_node_block_support=(
            args.current_tangent_residual_row_node_block_support
        ),
        current_tangent_residual_row_jacobian_mode=(
            args.current_tangent_residual_row_jacobian_mode
        ),
        current_tangent_residual_row_fd_epsilon=(
            args.current_tangent_residual_row_fd_epsilon
        ),
        current_tangent_residual_row_fd_max_support_columns=(
            args.current_tangent_residual_row_fd_max_support_columns
        ),
        current_tangent_residual_row_ridge_factor=(
            args.current_tangent_residual_row_ridge_factor
        ),
        current_tangent_residual_row_svd_relative_cutoff=(
            args.current_tangent_residual_row_svd_relative_cutoff
        ),
        current_tangent_residual_row_svd_max_condition=(
            args.current_tangent_residual_row_svd_max_condition
        ),
        current_tangent_residual_row_directional_probe_alpha=(
            args.current_tangent_residual_row_directional_probe_alpha
        ),
        current_tangent_residual_row_shell_normal_participation_threshold=(
            args.current_tangent_residual_row_shell_normal_participation_threshold
        ),
        current_tangent_residual_row_use_residual_only_assembly=(
            args.current_tangent_residual_row_use_residual_only_assembly
        ),
        current_tangent_residual_row_per_state_batch_replay=(
            args.current_tangent_residual_row_per_state_batch_replay
        ),
        current_tangent_residual_row_batch_alpha_replay=(
            args.current_tangent_residual_row_batch_alpha_replay
        ),
        current_tangent_residual_row_batch_fd_replay=(
            args.current_tangent_residual_row_batch_fd_replay
        ),
        current_tangent_residual_row_batch_fd_replay_chunk_size=(
            args.current_tangent_residual_row_batch_fd_replay_chunk_size
        ),
        current_tangent_residual_row_batch_replay_backend=(
            args.current_tangent_residual_row_batch_replay_backend
        ),
        current_tangent_residual_row_require_hip_batch_replay=(
            args.current_tangent_residual_row_require_hip_batch_replay
        ),
        current_tangent_residual_row_hipcc=args.current_tangent_residual_row_hipcc,
        current_tangent_residual_row_force_rebuild_hip=(
            args.current_tangent_residual_row_force_rebuild_hip
        ),
        current_tangent_residual_row_allow_negative_alphas=(
            args.current_tangent_residual_row_allow_negative_alphas
        ),
        current_tangent_residual_row_alpha_values=(
            current_tangent_residual_row_alpha_values or (0.03125, 0.015625)
        ),
        matrix_free_jacobian_alpha_values=matrix_free_jacobian_alpha_values,
        alpha_values=alpha_values,
    )
    base = payload.get("base_direct_residual") if isinstance(payload.get("base_direct_residual"), dict) else {}
    best = {}
    for component_name in (
        "trust_region_line_search",
        "secant_subspace_globalization",
        "secant_family_globalization",
        "matrix_free_consistent_jacobian_subspace",
        "matrix_free_global_krylov",
        "current_tangent_residual_row_correction",
    ):
        component = payload.get(component_name)
        if not isinstance(component, dict):
            continue
        candidate = component.get("best_gate_eligible_candidate") or component.get(
            "best_candidate"
        )
        if isinstance(candidate, dict) and candidate.get("direct_residual_inf_n") is not None:
            best = candidate
    print(
        "mgt-direct-residual-newton: "
        f"{payload['status']} base={base.get('direct_residual_inf_n')} "
        f"best={best.get('direct_residual_inf_n') if isinstance(best, dict) else None} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
