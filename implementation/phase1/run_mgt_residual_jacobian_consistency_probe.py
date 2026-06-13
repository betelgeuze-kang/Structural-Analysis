#!/usr/bin/env python3
"""Probe full-model residual/Jacobian consistency without solving Newton."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_mgt_direct_residual_newton_probe import DEFAULT_CHECKPOINT, PRODUCTIZATION  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    FrameElement,
    _element_end_points,
    _frame_props,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402
from mgt_frame_force_based_assembly import _element_force_based_end_forces  # noqa: E402


SCHEMA_VERSION = "mgt-residual-jacobian-consistency-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_residual_jacobian_consistency_probe.json"


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _direction_top_residual_sign(
    *,
    residual: np.ndarray,
    free: np.ndarray,
    dof_count: int,
    top_count: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    row_count = min(max(int(top_count), 1), int(residual.size))
    top_rows = np.argpartition(np.abs(residual), -row_count)[-row_count:]
    top_rows = top_rows[np.argsort(-np.abs(residual[top_rows]))]
    direction = np.zeros(int(dof_count), dtype=np.float64)
    for row in top_rows.tolist():
        direction[int(free[int(row)])] = float(np.sign(residual[int(row)]) or 1.0)
    return direction, {
        "direction": "top_residual_sign",
        "top_count": int(row_count),
        "selected_free_rows": [int(row) for row in top_rows.tolist()],
        "selected_global_dofs": [int(free[int(row)]) for row in top_rows.tolist()],
        "selected_residual_inf_n": float(max(abs(float(residual[int(row)])) for row in top_rows.tolist()))
        if top_rows.size
        else 0.0,
    }


def _direction_deterministic_free_sample(
    *,
    free: np.ndarray,
    dof_count: int,
    sample_count: int,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    count = min(max(int(sample_count), 1), int(free.size))
    rng = np.random.default_rng(int(seed))
    selected = np.sort(rng.choice(np.arange(int(free.size)), size=count, replace=False))
    values = rng.standard_normal(count)
    direction = np.zeros(int(dof_count), dtype=np.float64)
    direction[free[selected]] = values
    return direction, {
        "direction": "deterministic_free_sample",
        "sample_count": int(count),
        "seed": int(seed),
        "selected_free_rows_head": [int(row) for row in selected[:20].tolist()],
        "selected_global_dofs_head": [int(free[int(row)]) for row in selected[:20].tolist()],
    }


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
        name: _max_abs(values[free_idx]) if free_idx.size else 0.0
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
                "node_index": int(global_dof // 6),
                "dof": dof_names[global_dof % 6],
                "residual_n": float(residual_np[int(local_row)]),
                "external_load_n": float(rhs_np[int(local_row)]) if int(local_row) < rhs_np.size else 0.0,
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


def _scalar_load_balance_diagnostics(
    *,
    top_rows: list[dict[str, Any]],
    shell_component_names: tuple[str, ...] = ("shell_bending_drilling", "shell_membrane", "shell"),
) -> dict[str, Any]:
    selected = [
        row
        for row in top_rows
        if str(row.get("dominant_component") or "") in set(shell_component_names)
    ]
    if not selected:
        return {
            "evaluated": False,
            "reason": "no_shell_dominant_top_rows",
            "row_count": 0,
            "rows": [],
        }
    external = np.asarray([float(row.get("external_load_n") or 0.0) for row in selected], dtype=np.float64)
    internal = np.asarray([float(row.get("internal_sum_n") or 0.0) for row in selected], dtype=np.float64)
    residual = internal - external
    denom = float(np.dot(external, external))
    best_scale = float(np.dot(external, internal) / denom) if denom > 1.0e-30 else 0.0
    scaled_residual = internal - best_scale * external
    nonzero = np.abs(external) > 1.0e-30
    required_scales = internal[nonzero] / external[nonzero] if np.any(nonzero) else np.asarray([], dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for row, ext, fint, res in zip(selected, external.tolist(), internal.tolist(), residual.tolist()):
        component_values = row.get("component_values_n") if isinstance(row.get("component_values_n"), dict) else {}
        shell_sum = sum(float(component_values.get(name, 0.0)) for name in shell_component_names)
        rows.append(
            {
                "free_row": int(row.get("free_row", -1)),
                "global_dof": int(row.get("global_dof", -1)),
                "node_index": int(row.get("node_index", -1)),
                "dof": str(row.get("dof") or ""),
                "dominant_component": str(row.get("dominant_component") or ""),
                "external_load_n": float(ext),
                "internal_sum_n": float(fint),
                "shell_component_sum_n": float(shell_sum),
                "residual_n": float(res),
                "required_external_scale_for_zero_row_residual": (
                    float(fint / ext) if abs(float(ext)) > 1.0e-30 else None
                ),
            }
        )
    rounded_external_counts: dict[str, int] = {}
    for value in external.tolist():
        key = f"{float(value):.12g}"
        rounded_external_counts[key] = rounded_external_counts.get(key, 0) + 1
    return {
        "evaluated": True,
        "row_count": int(len(selected)),
        "base_residual_inf_n": _max_abs(residual),
        "external_load_inf_n": _max_abs(external),
        "internal_sum_inf_n": _max_abs(internal),
        "best_l2_external_scale": best_scale,
        "best_l2_scaled_residual_inf_n": _max_abs(scaled_residual),
        "best_l2_scaled_residual_l2_n": float(np.linalg.norm(scaled_residual)) if scaled_residual.size else 0.0,
        "required_external_scale_min": float(np.min(required_scales)) if required_scales.size else None,
        "required_external_scale_median": float(np.median(required_scales)) if required_scales.size else None,
        "required_external_scale_max": float(np.max(required_scales)) if required_scales.size else None,
        "rounded_external_load_counts": rounded_external_counts,
        "rows": rows,
        "claim_boundary": (
            "Diagnostic only: fits a scalar multiplier on the displayed top-row external loads. "
            "It does not prove that the full load path should be rescaled."
        ),
    }


def _local_row_projection_diagnostics(
    *,
    stiffness: Any,
    free: np.ndarray,
    residual: np.ndarray,
    top_rows: list[dict[str, Any]],
    max_rows: int = 8,
    support_strongest_per_row: int = 0,
    node_block_support: bool = False,
    component_filter: tuple[str, ...] = ("shell_bending_drilling", "shell_membrane", "shell"),
) -> dict[str, Any]:
    selected = [
        row
        for row in top_rows
        if str(row.get("dominant_component") or "") in set(component_filter)
    ][: max(int(max_rows), 0)]
    if not selected:
        return {
            "evaluated": False,
            "reason": "no_matching_top_rows",
            "selected_row_count": 0,
        }
    free_idx = np.asarray(free, dtype=np.int64)
    residual_np = np.asarray(residual, dtype=np.float64)
    k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
    target_rows = np.asarray([int(row["free_row"]) for row in selected], dtype=np.int64)
    support: set[int] = set(int(row) for row in target_rows.tolist())
    strongest_per_row = max(int(support_strongest_per_row), 0)
    if strongest_per_row > 0:
        for target_row in target_rows.tolist():
            start = int(k_ff.indptr[int(target_row)])
            end = int(k_ff.indptr[int(target_row) + 1])
            cols = k_ff.indices[start:end]
            vals = np.abs(k_ff.data[start:end])
            if cols.size:
                take = min(strongest_per_row, int(cols.size))
                strongest = np.argpartition(vals, -take)[-take:]
                support.update(int(cols[int(index)]) for index in strongest.tolist())
    if node_block_support:
        selected_nodes = {
            int(free_idx[int(row)]) // 6
            for row in support
            if 0 <= int(row) < int(free_idx.size)
        }
        support.update(
            int(local_col)
            for local_col, global_dof in enumerate(free_idx.tolist())
            if int(global_dof) // 6 in selected_nodes
        )
    support_cols = np.asarray(sorted(support), dtype=np.int64)
    submatrix = k_ff[target_rows, :][:, support_cols].toarray()
    rhs_rows = -residual_np[target_rows]
    try:
        coeffs, residual_sum, rank, singular_values = np.linalg.lstsq(submatrix, rhs_rows, rcond=None)
        solve_error = ""
    except np.linalg.LinAlgError as exc:
        coeffs = np.zeros(int(support_cols.size), dtype=np.float64)
        residual_sum = np.asarray([], dtype=np.float64)
        rank = 0
        singular_values = np.asarray([], dtype=np.float64)
        solve_error = str(exc)
    projected = np.asarray(submatrix @ coeffs, dtype=np.float64) if submatrix.size else np.asarray([], dtype=np.float64)
    projection_residual = projected - rhs_rows
    rhs_inf = _max_abs(rhs_rows)
    projection_residual_inf = _max_abs(projection_residual)
    rows = [
        {
            "free_row": int(row.get("free_row", -1)),
            "global_dof": int(row.get("global_dof", -1)),
            "node_index": int(row.get("node_index", -1)),
            "dof": str(row.get("dof") or ""),
            "dominant_component": str(row.get("dominant_component") or ""),
            "residual_n": float(row.get("residual_n") or 0.0),
        }
        for row in selected
    ]
    return {
        "evaluated": True,
        "selected_row_count": int(target_rows.size),
        "support_size": int(support_cols.size),
        "support_strongest_per_row": int(strongest_per_row),
        "node_block_support": bool(node_block_support),
        "rank": int(rank),
        "rhs_inf_n": rhs_inf,
        "projected_action_inf_n": _max_abs(projected),
        "projection_residual_inf_n": projection_residual_inf,
        "relative_projection_residual_inf": projection_residual_inf / max(rhs_inf, 1.0e-30),
        "coefficient_linf": _max_abs(coeffs),
        "coefficient_l2": float(np.linalg.norm(coeffs)) if coeffs.size else 0.0,
        "singular_values": [float(value) for value in singular_values.tolist()],
        "linear_least_squares_residual_sum": [float(value) for value in residual_sum.tolist()],
        "solve_error": solve_error,
        "selected_rows": rows,
        "claim_boundary": (
            "Diagnostic only: measures whether selected residual rows can be represented by "
            "the current tangent submatrix on a local support."
        ),
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


def _triangulate_conn(conn: list[int]) -> list[tuple[int, int, int]]:
    if len(conn) == 3:
        return [(conn[0], conn[1], conn[2])]
    if len(conn) == 4:
        return [(conn[0], conn[1], conn[2]), (conn[0], conn[2], conn[3])]
    return []


def _shell_membrane_hotspot_diagnostics(
    *,
    top_rows: list[dict[str, Any]],
    u: np.ndarray,
    setup_meta: dict[str, Any],
    max_rows: int = 12,
    max_elements_per_row: int = 8,
) -> list[dict[str, Any]]:
    node_xyz = setup_meta.get("_node_xyz")
    elem_id = setup_meta.get("_elem_id")
    elem_type_code = setup_meta.get("_elem_type_code")
    conn_ptr = setup_meta.get("_conn_ptr")
    conn_idx = setup_meta.get("_conn_idx")
    if not all(isinstance(value, np.ndarray) for value in (node_xyz, elem_id, elem_type_code, conn_ptr, conn_idx)):
        return []
    xyz = np.asarray(node_xyz, dtype=np.float64)
    ids = np.asarray(elem_id, dtype=np.int64)
    type_code = np.asarray(elem_type_code, dtype=np.int32)
    ptr = np.asarray(conn_ptr, dtype=np.int64)
    idx = np.asarray(conn_idx, dtype=np.int64)
    u_np = np.asarray(u, dtype=np.float64)
    trans = u_np.reshape((-1, 6))[:, :3] if u_np.size == int(xyz.shape[0]) * 6 else np.zeros_like(xyz)
    surface_indices = np.where(type_code == 2)[0]
    incident_by_node: dict[int, list[int]] = {}
    for elem_index in surface_indices.tolist():
        start = int(ptr[int(elem_index)])
        end = int(ptr[int(elem_index) + 1])
        if start < 0 or end < start or end > int(idx.size):
            continue
        conn = [int(node) for node in idx[start:end].tolist()]
        if len(conn) not in {3, 4}:
            continue
        for node in conn:
            incident_by_node.setdefault(node, []).append(int(elem_index))
    axis_by_dof = {
        "ux": np.asarray([1.0, 0.0, 0.0], dtype=np.float64),
        "uy": np.asarray([0.0, 1.0, 0.0], dtype=np.float64),
        "uz": np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
    }
    rows: list[dict[str, Any]] = []
    for row in top_rows[: max(int(max_rows), 0)]:
        node = int(row.get("node_index", -1))
        dof = str(row.get("dof") or "")
        incident = incident_by_node.get(node, [])
        axis = axis_by_dof.get(dof)
        element_rows: list[dict[str, Any]] = []
        max_participation = 0.0
        max_normal_participation = 0.0
        max_rel_membrane = 0.0
        max_rel_normal = 0.0
        for elem_index in incident[: max(int(max_elements_per_row), 0)]:
            conn = [int(n) for n in idx[int(ptr[elem_index]) : int(ptr[elem_index + 1])].tolist()]
            tri_rows: list[dict[str, Any]] = []
            for tri in _triangulate_conn(conn):
                if node not in tri:
                    continue
                basis = _local_shell_basis(np.asarray([xyz[n] for n in tri], dtype=np.float64))
                if basis is None:
                    continue
                e1, e2, e3 = basis
                participation = (
                    float(np.sqrt(float(np.dot(axis, e1)) ** 2 + float(np.dot(axis, e2)) ** 2))
                    if axis is not None
                    else 0.0
                )
                normal_participation = float(abs(float(np.dot(axis, e3)))) if axis is not None else 0.0
                rel_membrane = 0.0
                rel_normal = 0.0
                for other in tri:
                    delta = trans[int(other)] - trans[node]
                    rel_membrane = max(
                        rel_membrane,
                        float(
                            np.sqrt(float(np.dot(delta, e1)) ** 2 + float(np.dot(delta, e2)) ** 2)
                        ),
                    )
                    rel_normal = max(rel_normal, float(abs(float(np.dot(delta, e3)))))
                max_participation = max(max_participation, participation)
                max_normal_participation = max(max_normal_participation, normal_participation)
                max_rel_membrane = max(max_rel_membrane, rel_membrane)
                max_rel_normal = max(max_rel_normal, rel_normal)
                tri_rows.append(
                    {
                        "tri_nodes": [int(n) for n in tri],
                        "global_dof_membrane_participation": participation,
                        "global_dof_normal_participation": normal_participation,
                        "max_relative_membrane_displacement_m": rel_membrane,
                        "max_relative_normal_displacement_m": rel_normal,
                        "normal": [float(v) for v in e3.tolist()],
                    }
                )
            if tri_rows:
                element_rows.append(
                    {
                        "elem_index": int(elem_index),
                        "elem_id": int(ids[elem_index]) if elem_index < int(ids.size) else int(elem_index),
                        "conn": conn,
                        "triangles": tri_rows,
                    }
                )
        rows.append(
            {
                "free_row": row.get("free_row"),
                "global_dof": row.get("global_dof"),
                "node_index": node,
                "dof": dof,
                "dominant_component": row.get("dominant_component"),
                "residual_n": row.get("residual_n"),
                "node_xyz_m": [float(v) for v in xyz[node].tolist()] if 0 <= node < int(xyz.shape[0]) else [],
                "node_translation_m": [float(v) for v in trans[node].tolist()] if 0 <= node < int(trans.shape[0]) else [],
                "incident_surface_element_count": int(len(incident)),
                "max_global_dof_membrane_participation": max_participation,
                "max_global_dof_normal_participation": max_normal_participation,
                "max_relative_membrane_displacement_m": max_rel_membrane,
                "max_relative_normal_displacement_m": max_rel_normal,
                "sample_incident_elements": element_rows,
            }
        )
    return rows


def _frame_hotspot_diagnostics(
    *,
    top_rows: list[dict[str, Any]],
    u: np.ndarray,
    setup_meta: dict[str, Any],
    max_rows: int = 16,
    max_elements_per_row: int = 12,
) -> list[dict[str, Any]]:
    node_xyz = setup_meta.get("_node_xyz")
    node_id = setup_meta.get("_node_id")
    frame_elements = setup_meta.get("_frame_elements")
    section_props = setup_meta.get("_section_props")
    material_props = setup_meta.get("_material_props")
    base_axial_forces = setup_meta.get("_base_axial_forces")
    if not isinstance(node_xyz, np.ndarray) or not isinstance(frame_elements, list):
        return []
    if not isinstance(section_props, dict) or not isinstance(material_props, dict):
        return []
    if not isinstance(base_axial_forces, dict):
        base_axial_forces = {}
    xyz = np.asarray(node_xyz, dtype=np.float64)
    raw_node_id = np.asarray(node_id, dtype=np.int64) if isinstance(node_id, np.ndarray) else None
    u_np = np.asarray(u, dtype=np.float64)
    trans = (
        u_np.reshape((-1, 6))[:, :3]
        if u_np.size == int(xyz.shape[0]) * 6
        else np.zeros_like(xyz)
    )
    load_scale = float(setup_meta.get("load_scale") or 1.0)
    frame_gravity_load_scale = float(setup_meta.get("frame_gravity_load_scale") or 0.01)
    incident_by_node: dict[int, list[FrameElement]] = {}
    for elem in frame_elements:
        if not isinstance(elem, FrameElement):
            continue
        incident_by_node.setdefault(int(elem.node_i), []).append(elem)
        incident_by_node.setdefault(int(elem.node_j), []).append(elem)
    dof_names = ("ux", "uy", "uz", "rx", "ry", "rz")
    diagnostics: list[dict[str, Any]] = []
    for row in top_rows[: max(int(max_rows), 0)]:
        if str(row.get("dominant_component") or "") != "frame":
            continue
        node = int(row.get("node_index", -1))
        global_dof = int(row.get("global_dof", -1))
        dof_index = global_dof % 6 if global_dof >= 0 else -1
        if node < 0 or dof_index < 0:
            continue
        incident = incident_by_node.get(node, [])
        element_rows: list[dict[str, Any]] = []
        contribution_sum = 0.0
        for elem in incident:
            props, used_real_props = _frame_props(
                elem,
                section_props=section_props,
                material_props=material_props,
            )
            axial_force_n = (
                float(base_axial_forces.get(int(elem.elem_id), 0.0))
                * frame_gravity_load_scale
                * load_scale
            )
            force_node = _element_force_based_end_forces(
                elem=elem,
                node_xyz=xyz,
                u=u_np,
                props=props,
                axial_force_n=axial_force_n,
                include_geometric=True,
            )
            end_offset = 0 if int(elem.node_i) == node else 6
            contribution = float(force_node[end_offset + dof_index])
            contribution_sum += contribution
            pi, pj = _element_end_points(elem, xyz)
            chord = np.asarray(pj - pi, dtype=np.float64)
            length = max(float(np.linalg.norm(chord)), 1.0e-12)
            verticality = abs(float(chord[2])) / length
            element_rows.append(
                {
                    "elem_id": int(elem.elem_id),
                    "end": "i" if int(elem.node_i) == node else "j",
                    "other_node_index": int(elem.node_j if int(elem.node_i) == node else elem.node_i),
                    "section_id": int(elem.section_id),
                    "material_id": int(elem.material_id),
                    "used_real_props": bool(used_real_props),
                    "length_m": float(elem.length_m),
                    "verticality_abs_dz_over_length": float(verticality),
                    "local_axis_angle_deg": float(elem.local_axis_angle_deg),
                    "axial_force_n": float(axial_force_n),
                    "target_dof_force_contribution_n": contribution,
                }
            )
        element_rows.sort(
            key=lambda item: abs(float(item["target_dof_force_contribution_n"])),
            reverse=True,
        )
        sampled = element_rows[: max(int(max_elements_per_row), 0)]
        diagnostics.append(
            {
                "free_row": row.get("free_row"),
                "global_dof": global_dof,
                "node_index": node,
                "raw_node_id": int(raw_node_id[node])
                if raw_node_id is not None and 0 <= node < int(raw_node_id.size)
                else None,
                "dof": dof_names[dof_index] if 0 <= dof_index < len(dof_names) else str(row.get("dof") or ""),
                "residual_n": row.get("residual_n"),
                "external_load_n": row.get("external_load_n"),
                "component_frame_n": (
                    row.get("component_values_n", {}).get("frame")
                    if isinstance(row.get("component_values_n"), dict)
                    else None
                ),
                "incident_frame_element_count": int(len(incident)),
                "incident_frame_target_dof_contribution_sum_n": float(contribution_sum),
                "component_reconstruction_error_n": (
                    float(contribution_sum - float(row["component_values_n"]["frame"]))
                    if isinstance(row.get("component_values_n"), dict)
                    and "frame" in row["component_values_n"]
                    else None
                ),
                "node_xyz_m": [float(v) for v in xyz[node].tolist()]
                if 0 <= node < int(xyz.shape[0])
                else [],
                "node_translation_m": [float(v) for v in trans[node].tolist()]
                if 0 <= node < int(trans.shape[0])
                else [],
                "max_abs_sample_contribution_n": max(
                    (abs(float(item["target_dof_force_contribution_n"])) for item in sampled),
                    default=0.0,
                ),
                "sample_incident_frame_elements": sampled,
            }
        )
    return diagnostics


def _state_scale_sweep(
    *,
    u: np.ndarray,
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    scale_values: tuple[float, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_u = np.asarray(u, dtype=np.float64)
    for scale in scale_values:
        scaled_u = float(scale) * base_u
        _k, _f_ext, free, residual, rhs, meta = assemble_residual(
            scaled_u,
            include_component_forces=True,
        )
        component_forces = meta.pop("component_forces", {})
        component_breakdown = _component_breakdown(
            component_forces=component_forces if isinstance(component_forces, dict) else {},
            free=np.asarray(free, dtype=np.int64),
            residual=np.asarray(residual, dtype=np.float64),
            rhs=np.asarray(rhs, dtype=np.float64),
            top_count=8,
        )
        residual_inf = _max_abs(residual)
        rhs_inf = _max_abs(rhs)
        rows.append(
            {
                "state_scale": float(scale),
                "residual_inf_n": residual_inf,
                "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
                "rhs_inf_n": rhs_inf,
                "max_abs_displacement_m": _max_abs(scaled_u),
                "component_inf_n": component_breakdown.get("component_inf_n"),
                "top_row_dominant_component_counts": component_breakdown.get(
                    "top_row_dominant_component_counts"
                ),
            }
        )
    return rows


def _hotspot_signed_displacement_sweep(
    *,
    u: np.ndarray,
    free: np.ndarray,
    top_rows: list[dict[str, Any]],
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    step_values: tuple[float, ...],
    relative_increment_tolerance: float = 1.0e-4,
    residual_tolerance_n: float = 1.0e-3,
) -> dict[str, Any]:
    base_u = np.asarray(u, dtype=np.float64)
    free_idx = np.asarray(free, dtype=np.int64)
    selected_rows = [
        row
        for row in top_rows
        if str(row.get("dominant_component") or "") == "frame"
        and str(row.get("dof") or "") in {"ux", "uy", "uz"}
    ]
    direction = np.zeros_like(base_u)
    for row in selected_rows:
        global_dof = int(row.get("global_dof", -1))
        if 0 <= global_dof < int(direction.size):
            residual_value = float(row.get("residual_n") or 0.0)
            direction[global_dof] = -float(np.sign(residual_value) or 1.0)
    direction_inf = _max_abs(direction)
    if direction_inf <= 0.0:
        return {
            "enabled": True,
            "evaluated": False,
            "reason": "no_frame_translation_hotspot_rows",
            "candidate_rows": [],
            "best_candidate": {},
        }
    direction /= direction_inf
    _base_k, _base_f, base_free, base_residual, base_rhs, _base_meta = assemble_residual(
        base_u
    )
    base_free_idx = np.asarray(base_free, dtype=np.int64)
    base_residual_inf = _max_abs(base_residual)
    base_rhs_inf = _max_abs(base_rhs)
    max_abs_u = max(_max_abs(base_u), 1.0e-12)
    candidate_rows: list[dict[str, Any]] = []
    for step in step_values:
        step_float = float(step)
        trial_u = base_u + step_float * direction
        _trial_k, _trial_f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
            trial_u
        )
        trial_free_idx = np.asarray(trial_free, dtype=np.int64)
        free_stable = bool(
            trial_free_idx.shape == base_free_idx.shape
            and np.array_equal(trial_free_idx, base_free_idx)
        )
        residual_inf = _max_abs(trial_residual)
        rhs_inf = _max_abs(trial_rhs)
        relative_increment = abs(step_float) / max_abs_u
        candidate_rows.append(
            {
                "step_m": step_float,
                "free_dof_set_stable": free_stable,
                "direct_residual_inf_n": residual_inf,
                "direct_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
                "improvement_inf_n": base_residual_inf - residual_inf,
                "relative_improvement": (base_residual_inf - residual_inf)
                / max(base_residual_inf, 1.0),
                "relative_increment": relative_increment,
                "residual_gate_passed": residual_inf <= float(residual_tolerance_n),
                "relative_increment_gate_passed": relative_increment
                <= float(relative_increment_tolerance),
            }
        )
    best_candidate = min(
        (
            row
            for row in candidate_rows
            if bool(row.get("free_dof_set_stable"))
        ),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    best_gate_eligible_candidate = min(
        (
            row
            for row in candidate_rows
            if bool(row.get("free_dof_set_stable"))
            and bool(row.get("relative_increment_gate_passed"))
        ),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    return {
        "enabled": True,
        "evaluated": True,
        "direction": "negative_residual_sign_on_frame_translation_hotspots",
        "selected_hotspot_row_count": int(len(selected_rows)),
        "selected_global_dofs": sorted(
            {
                int(row.get("global_dof", -1))
                for row in selected_rows
                if int(row.get("global_dof", -1)) >= 0
            }
        ),
        "base_direct_residual_inf_n": base_residual_inf,
        "base_relative_residual_inf": base_residual_inf / max(base_rhs_inf, 1.0),
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "residual_tolerance_n": float(residual_tolerance_n),
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate,
        "best_gate_eligible_candidate": best_gate_eligible_candidate,
    }


def _hotspot_tangent_fd_jvp_rows(
    *,
    u: np.ndarray,
    stiffness: Any,
    free: np.ndarray,
    residual: np.ndarray,
    top_rows: list[dict[str, Any]],
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    fd_step: float,
    max_rows: int = 6,
    component_filter: str = "frame",
) -> list[dict[str, Any]]:
    component_filter = str(component_filter or "frame")
    if component_filter not in {"frame", "shell_bending_drilling", "shell_membrane", "translation", "all"}:
        raise ValueError(
            "hotspot_jvp_component_filter must be one of frame, shell_bending_drilling, "
            "shell_membrane, translation, or all"
        )
    free_idx = np.asarray(free, dtype=np.int64)
    base_residual = np.asarray(residual, dtype=np.float64)
    base_u = np.asarray(u, dtype=np.float64)
    local_row_by_global = {
        int(global_dof): int(local_row)
        for local_row, global_dof in enumerate(free_idx.tolist())
    }
    selected_rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in top_rows:
        dominant = str(row.get("dominant_component") or "")
        if component_filter not in {"translation", "all"} and dominant != component_filter:
            continue
        if str(row.get("dof") or "") not in {"ux", "uy", "uz"}:
            continue
        global_dof = int(row.get("global_dof", -1))
        if global_dof < 0 or global_dof in seen or global_dof not in local_row_by_global:
            continue
        selected_rows.append(row)
        seen.add(global_dof)
        if len(selected_rows) >= max(int(max_rows), 0):
            break
    rows: list[dict[str, Any]] = []
    for row in selected_rows:
        global_dof = int(row["global_dof"])
        local_row = int(local_row_by_global[global_dof])
        direction = np.zeros_like(base_u)
        direction[global_dof] = 1.0
        trial_u = base_u + float(fd_step) * direction
        used_residual_only = False
        try:
            _trial_k, _trial_f, trial_free, trial_residual, _trial_rhs, trial_meta = assemble_residual(
                trial_u,
                residual_only=True,
                free_override=free_idx,
            )
            used_residual_only = True
        except TypeError:
            _trial_k, _trial_f, trial_free, trial_residual, _trial_rhs, trial_meta = assemble_residual(
                trial_u
            )
        trial_free_idx = np.asarray(trial_free, dtype=np.int64)
        free_stable = bool(
            trial_free_idx.shape == free_idx.shape
            and np.array_equal(trial_free_idx, free_idx)
        )
        if not free_stable:
            rows.append(
                {
                    "evaluated": False,
                    "reason": "free_dof_set_changed",
                    "fd_step": float(fd_step),
                    "global_dof": global_dof,
                    "free_row": row.get("free_row"),
                    "node_index": row.get("node_index"),
                    "dof": row.get("dof"),
                }
            )
            continue
        tangent_column = stiffness[free_idx, global_dof]
        tangent_action = np.asarray(
            tangent_column.toarray() if hasattr(tangent_column, "toarray") else tangent_column,
            dtype=np.float64,
        ).reshape(-1)
        fd_action = (np.asarray(trial_residual, dtype=np.float64) - base_residual) / float(fd_step)
        diff = tangent_action - fd_action
        tangent_inf = _max_abs(tangent_action)
        fd_inf = _max_abs(fd_action)
        diff_inf = _max_abs(diff)
        tangent_l2 = float(np.linalg.norm(tangent_action)) if tangent_action.size else 0.0
        fd_l2 = float(np.linalg.norm(fd_action)) if fd_action.size else 0.0
        diff_l2 = float(np.linalg.norm(diff)) if diff.size else 0.0
        denom = tangent_l2 * fd_l2
        cosine = float(np.dot(tangent_action, fd_action) / denom) if denom > 0.0 else 0.0
        selected_tangent = float(tangent_action[local_row]) if local_row < tangent_action.size else 0.0
        selected_fd = float(fd_action[local_row]) if local_row < fd_action.size else 0.0
        selected_diff = selected_tangent - selected_fd
        rows.append(
            {
                "evaluated": True,
                "direction": "unit_global_dof",
                "fd_step": float(fd_step),
                "global_dof": global_dof,
                "free_row": row.get("free_row"),
                "node_index": row.get("node_index"),
                "dof": row.get("dof"),
                "dominant_component": row.get("dominant_component"),
                "base_residual_n": row.get("residual_n"),
                "component_frame_n": (
                    row.get("component_values_n", {}).get("frame")
                    if isinstance(row.get("component_values_n"), dict)
                    else None
                ),
                "component_value_n": (
                    row.get("component_values_n", {}).get(str(row.get("dominant_component") or ""))
                    if isinstance(row.get("component_values_n"), dict)
                    else None
                ),
                "free_dof_set_stable": True,
                "residual_only_assembly": bool(used_residual_only),
                "selected_row_tangent_action_n_per_m": selected_tangent,
                "selected_row_fd_action_n_per_m": selected_fd,
                "selected_row_diff_n_per_m": selected_diff,
                "selected_row_relative_error": abs(selected_diff)
                / max(abs(selected_fd), 1.0),
                "tangent_action_inf_n_per_m": tangent_inf,
                "fd_action_inf_n_per_m": fd_inf,
                "diff_inf_n_per_m": diff_inf,
                "relative_inf_error": diff_inf / max(fd_inf, 1.0),
                "tangent_action_l2_n_per_m": tangent_l2,
                "fd_action_l2_n_per_m": fd_l2,
                "diff_l2_n_per_m": diff_l2,
                "relative_l2_error": diff_l2 / max(fd_l2, 1.0),
                "action_cosine": cosine,
                "trial_physical_internal_force_model": trial_meta.get(
                    "physical_internal_force_model"
                ),
            }
        )
    return rows


def _hotspot_diagonal_newton_sweep(
    *,
    u: np.ndarray,
    stiffness: Any,
    free: np.ndarray,
    top_rows: list[dict[str, Any]],
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    alpha_values: tuple[float, ...],
    relative_increment_tolerance: float = 1.0e-4,
    residual_tolerance_n: float = 1.0e-3,
    max_rows: int = 8,
) -> dict[str, Any]:
    free_idx = np.asarray(free, dtype=np.int64)
    base_u = np.asarray(u, dtype=np.float64)
    _base_k, _base_f, base_free, base_residual, base_rhs, _base_meta = assemble_residual(
        base_u
    )
    base_free_idx = np.asarray(base_free, dtype=np.int64)
    free_stable = bool(
        base_free_idx.shape == free_idx.shape and np.array_equal(base_free_idx, free_idx)
    )
    local_row_by_global = {
        int(global_dof): int(local_row)
        for local_row, global_dof in enumerate(free_idx.tolist())
    }
    selected_rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in top_rows:
        if str(row.get("dominant_component") or "") != "frame":
            continue
        if str(row.get("dof") or "") not in {"ux", "uy", "uz"}:
            continue
        global_dof = int(row.get("global_dof", -1))
        if global_dof < 0 or global_dof in seen or global_dof not in local_row_by_global:
            continue
        selected_rows.append(row)
        seen.add(global_dof)
        if len(selected_rows) >= max(int(max_rows), 0):
            break
    correction = np.zeros_like(base_u)
    selected_corrections: list[dict[str, Any]] = []
    for row in selected_rows:
        global_dof = int(row["global_dof"])
        local_row = int(local_row_by_global[global_dof])
        tangent_value = float(stiffness[global_dof, global_dof])
        residual_value = float(base_residual[local_row])
        delta = -residual_value / tangent_value if abs(tangent_value) > 1.0e-12 else 0.0
        correction[global_dof] = delta
        selected_corrections.append(
            {
                "global_dof": global_dof,
                "free_row": row.get("free_row"),
                "node_index": row.get("node_index"),
                "dof": row.get("dof"),
                "base_residual_n": residual_value,
                "diagonal_tangent_n_per_m": tangent_value,
                "unit_alpha_correction_m": float(delta),
            }
        )
    correction_inf = _max_abs(correction)
    if not selected_corrections or correction_inf <= 0.0:
        return {
            "enabled": True,
            "evaluated": False,
            "reason": "no_nonzero_frame_hotspot_diagonal_correction",
            "selected_corrections": selected_corrections,
            "candidate_rows": [],
            "best_candidate": {},
            "best_gate_eligible_candidate": {},
        }
    base_residual_inf = _max_abs(base_residual)
    base_rhs_inf = _max_abs(base_rhs)
    max_abs_u = max(_max_abs(base_u), 1.0e-12)
    candidate_rows: list[dict[str, Any]] = []
    for alpha in alpha_values:
        alpha_float = float(alpha)
        trial_u = base_u + alpha_float * correction
        _trial_k, _trial_f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
            trial_u
        )
        trial_free_idx = np.asarray(trial_free, dtype=np.int64)
        trial_free_stable = bool(
            trial_free_idx.shape == base_free_idx.shape
            and np.array_equal(trial_free_idx, base_free_idx)
        )
        residual_inf = _max_abs(trial_residual)
        rhs_inf = _max_abs(trial_rhs)
        relative_increment = abs(alpha_float) * correction_inf / max_abs_u
        candidate_rows.append(
            {
                "alpha": alpha_float,
                "free_dof_set_stable": trial_free_stable,
                "direct_residual_inf_n": residual_inf,
                "direct_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
                "improvement_inf_n": base_residual_inf - residual_inf,
                "relative_improvement": (base_residual_inf - residual_inf)
                / max(base_residual_inf, 1.0),
                "relative_increment": relative_increment,
                "residual_gate_passed": residual_inf <= float(residual_tolerance_n),
                "relative_increment_gate_passed": relative_increment
                <= float(relative_increment_tolerance),
            }
        )
    best_candidate = min(
        (
            row
            for row in candidate_rows
            if bool(row.get("free_dof_set_stable"))
        ),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    best_gate_eligible_candidate = min(
        (
            row
            for row in candidate_rows
            if bool(row.get("free_dof_set_stable"))
            and bool(row.get("relative_increment_gate_passed"))
        ),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    return {
        "enabled": True,
        "evaluated": bool(free_stable),
        "direction": "diagonal_newton_on_frame_translation_hotspots",
        "selected_hotspot_row_count": int(len(selected_corrections)),
        "base_direct_residual_inf_n": base_residual_inf,
        "base_relative_residual_inf": base_residual_inf / max(base_rhs_inf, 1.0),
        "correction_inf_m": correction_inf,
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "residual_tolerance_n": float(residual_tolerance_n),
        "selected_corrections": selected_corrections,
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate,
        "best_gate_eligible_candidate": best_gate_eligible_candidate,
    }


def evaluate_residual_jacobian_direction(
    *,
    u: np.ndarray,
    stiffness: Any,
    free: np.ndarray,
    residual: np.ndarray,
    direction: np.ndarray,
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    fd_step: float,
    direction_meta: dict[str, Any],
) -> dict[str, Any]:
    """Compare tangent action K*d with finite-difference residual action."""
    free_idx = np.asarray(free, dtype=np.int64)
    base_residual = np.asarray(residual, dtype=np.float64)
    raw_direction = np.asarray(direction, dtype=np.float64)
    direction_inf = _max_abs(raw_direction)
    if direction_inf <= 0.0:
        return {
            **direction_meta,
            "evaluated": False,
            "reason": "zero_direction",
        }
    normalized_direction = raw_direction / direction_inf
    step = float(fd_step)
    trial_u = np.asarray(u, dtype=np.float64) + step * normalized_direction
    _trial_k, _trial_f, trial_free, trial_residual, _trial_rhs, trial_meta = assemble_residual(trial_u)
    free_stable = bool(
        np.asarray(trial_free, dtype=np.int64).shape == free_idx.shape
        and np.array_equal(np.asarray(trial_free, dtype=np.int64), free_idx)
    )
    if not free_stable:
        return {
            **direction_meta,
            "evaluated": False,
            "reason": "free_dof_set_changed",
            "fd_step": step,
        }
    tangent_action = np.asarray(stiffness[free_idx, :][:, free_idx] @ normalized_direction[free_idx], dtype=np.float64)
    fd_action = (np.asarray(trial_residual, dtype=np.float64) - base_residual) / step
    diff = tangent_action - fd_action
    tangent_l2 = float(np.linalg.norm(tangent_action)) if tangent_action.size else 0.0
    fd_l2 = float(np.linalg.norm(fd_action)) if fd_action.size else 0.0
    diff_l2 = float(np.linalg.norm(diff)) if diff.size else 0.0
    tangent_inf = _max_abs(tangent_action)
    fd_inf = _max_abs(fd_action)
    diff_inf = _max_abs(diff)
    denom = tangent_l2 * fd_l2
    cosine = float(np.dot(tangent_action, fd_action) / denom) if denom > 0.0 else 0.0
    return {
        **direction_meta,
        "evaluated": True,
        "fd_step": step,
        "free_dof_set_stable": True,
        "tangent_action_inf_n": tangent_inf,
        "fd_action_inf_n": fd_inf,
        "diff_inf_n": diff_inf,
        "relative_inf_error": diff_inf / max(fd_inf, 1.0),
        "tangent_action_l2_n": tangent_l2,
        "fd_action_l2_n": fd_l2,
        "diff_l2_n": diff_l2,
        "relative_l2_error": diff_l2 / max(fd_l2, 1.0),
        "action_cosine": cosine,
        "trial_physical_internal_force_model": trial_meta.get("physical_internal_force_model"),
    }


def run_mgt_residual_jacobian_consistency_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    fd_step: float = 1.0e-6,
    top_residual_count: int = 32,
    sample_count: int = 96,
    sample_seed: int = 1701,
    state_scale_values: tuple[float, ...] = (0.0, 0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
    relative_error_threshold: float = 0.25,
    cosine_threshold: float = 0.80,
    component_only: bool = False,
    hotspot_sweep: bool = False,
    hotspot_sweep_step_values: tuple[float, ...] = (1.0e-10, 3.0e-10, 1.0e-9),
    hotspot_jvp: bool = False,
    hotspot_jvp_max_rows: int = 6,
    hotspot_jvp_component_filter: str = "frame",
    hotspot_diagonal_newton_sweep: bool = False,
    hotspot_diagonal_newton_alpha_values: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.1,
        0.01,
        0.001,
    ),
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    assembly_started = time.perf_counter()
    stiffness, _f_ext, free, residual, rhs, base_meta = assemble_residual(
        u0,
        include_component_forces=True,
    )
    assembly_seconds = time.perf_counter() - assembly_started
    component_forces = base_meta.pop("component_forces", {})
    residual_component_breakdown = _component_breakdown(
        component_forces=component_forces if isinstance(component_forces, dict) else {},
        free=np.asarray(free, dtype=np.int64),
        residual=np.asarray(residual, dtype=np.float64),
        rhs=np.asarray(rhs, dtype=np.float64),
        top_count=int(top_residual_count),
    )
    shell_load_balance = _scalar_load_balance_diagnostics(
        top_rows=residual_component_breakdown.get("top_rows", []),
    )
    shell_local_projection = {
        "self_rows": _local_row_projection_diagnostics(
            stiffness=stiffness,
            free=np.asarray(free, dtype=np.int64),
            residual=np.asarray(residual, dtype=np.float64),
            top_rows=residual_component_breakdown.get("top_rows", []),
            max_rows=8,
            support_strongest_per_row=0,
            node_block_support=False,
        ),
        "node_block_strongest8": _local_row_projection_diagnostics(
            stiffness=stiffness,
            free=np.asarray(free, dtype=np.int64),
            residual=np.asarray(residual, dtype=np.float64),
            top_rows=residual_component_breakdown.get("top_rows", []),
            max_rows=8,
            support_strongest_per_row=8,
            node_block_support=True,
        ),
    }
    shell_membrane_hotspots = _shell_membrane_hotspot_diagnostics(
        top_rows=residual_component_breakdown.get("top_rows", []),
        u=u0,
        setup_meta=setup_meta,
    )
    frame_hotspots = _frame_hotspot_diagnostics(
        top_rows=residual_component_breakdown.get("top_rows", []),
        u=u0,
        setup_meta=setup_meta,
    )
    hotspot_signed_sweep = (
        _hotspot_signed_displacement_sweep(
            u=u0,
            free=np.asarray(free, dtype=np.int64),
            top_rows=residual_component_breakdown.get("top_rows", []),
            assemble_residual=assemble_residual,
            step_values=hotspot_sweep_step_values,
        )
        if hotspot_sweep
        else {"enabled": False}
    )
    hotspot_jvp_rows = (
        _hotspot_tangent_fd_jvp_rows(
            u=u0,
            stiffness=stiffness,
            free=np.asarray(free, dtype=np.int64),
            residual=np.asarray(residual, dtype=np.float64),
            top_rows=residual_component_breakdown.get("top_rows", []),
            assemble_residual=assemble_residual,
            fd_step=float(fd_step),
            max_rows=int(hotspot_jvp_max_rows),
            component_filter=str(hotspot_jvp_component_filter),
        )
        if hotspot_jvp
        else []
    )
    hotspot_diagonal_sweep = (
        _hotspot_diagonal_newton_sweep(
            u=u0,
            stiffness=stiffness,
            free=np.asarray(free, dtype=np.int64),
            top_rows=residual_component_breakdown.get("top_rows", []),
            assemble_residual=assemble_residual,
            alpha_values=hotspot_diagonal_newton_alpha_values,
        )
        if hotspot_diagonal_newton_sweep
        else {"enabled": False}
    )
    base_residual_inf = _max_abs(residual)
    rhs_inf = _max_abs(rhs)
    if component_only:
        direction_rows = []
        state_scale_sweep = []
    else:
        directions = [
            _direction_top_residual_sign(
                residual=np.asarray(residual, dtype=np.float64),
                free=np.asarray(free, dtype=np.int64),
                dof_count=int(u0.size),
                top_count=int(top_residual_count),
            ),
            _direction_deterministic_free_sample(
                free=np.asarray(free, dtype=np.int64),
                dof_count=int(u0.size),
                sample_count=int(sample_count),
                seed=int(sample_seed),
            ),
        ]
        direction_rows = [
            evaluate_residual_jacobian_direction(
                u=u0,
                stiffness=stiffness,
                free=np.asarray(free, dtype=np.int64),
                residual=np.asarray(residual, dtype=np.float64),
                direction=direction,
                assemble_residual=assemble_residual,
                fd_step=float(fd_step),
                direction_meta=meta,
            )
            for direction, meta in directions
        ]
        state_scale_sweep = _state_scale_sweep(
            u=u0,
            assemble_residual=assemble_residual,
            scale_values=state_scale_values,
        )
    evaluated = [row for row in direction_rows if bool(row.get("evaluated"))]
    consistency_ready = bool(
        not component_only
        and evaluated
        and all(
            float(row.get("relative_l2_error") or float("inf")) <= float(relative_error_threshold)
            and float(row.get("relative_inf_error") or float("inf")) <= float(relative_error_threshold)
            and float(row.get("action_cosine") or 0.0) >= float(cosine_threshold)
            for row in evaluated
        )
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if consistency_ready else "partial",
        "residual_jacobian_consistency_ready": consistency_ready,
        "checkpoint": setup_meta.get("checkpoint"),
        "load_scale": setup_meta.get("load_scale"),
        "base_residual_inf_n": base_residual_inf,
        "base_relative_residual_inf": base_residual_inf / max(rhs_inf, 1.0),
        "rhs_inf_n": rhs_inf,
        "free_dof_count": int(np.asarray(free).size),
        "top_residual_count": int(top_residual_count),
        "residual_component_breakdown": residual_component_breakdown,
        "residual_shell_load_balance": shell_load_balance,
        "residual_shell_local_projection": shell_local_projection,
        "residual_hotspot_shell_membrane_diagnostics": shell_membrane_hotspots,
        "residual_hotspot_frame_diagnostics": frame_hotspots,
        "residual_hotspot_signed_displacement_sweep": hotspot_signed_sweep,
        "residual_hotspot_tangent_fd_jvp_rows": hotspot_jvp_rows,
        "residual_hotspot_tangent_fd_jvp_component_filter": str(
            hotspot_jvp_component_filter
        ),
        "residual_hotspot_diagonal_newton_sweep": hotspot_diagonal_sweep,
        "fd_step": float(fd_step),
        "relative_error_threshold": float(relative_error_threshold),
        "cosine_threshold": float(cosine_threshold),
        "direction_rows": direction_rows,
        "state_scale_sweep": state_scale_sweep,
        "component_only": bool(component_only),
        "base_meta": {
            "physical_internal_force_model": base_meta.get("physical_internal_force_model"),
            "newton_tangent_model": base_meta.get("newton_tangent_model"),
            "equilibrium_geometry_contract": base_meta.get("equilibrium_geometry_contract"),
            "stiffness_unit_audit": base_meta.get("stiffness_unit_audit"),
        },
        "runtime_metrics": {
            "setup_and_reference_seconds": float(assembly_started - started),
            "base_assembly_seconds": assembly_seconds,
            "total_seconds": time.perf_counter() - started,
        },
        "claim_boundary": (
            "Full-model diagnostic comparing assembled tangent K*d against finite-difference "
            "physical residual action dR/du*d. This is not a nonlinear equilibrium closure."
        ),
        "blockers": []
        if consistency_ready
        else ["component_only_diagnostic_not_consistency_closure"]
        if component_only
        else ["residual_jacobian_consistency_not_closed"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--fd-step", type=float, default=1.0e-6)
    parser.add_argument("--top-residual-count", type=int, default=32)
    parser.add_argument("--sample-count", type=int, default=96)
    parser.add_argument("--sample-seed", type=int, default=1701)
    parser.add_argument(
        "--state-scale-values",
        default="0,0.001,0.01,0.05,0.1,0.25,0.5,1",
        help="Comma-separated checkpoint displacement scale sweep values.",
    )
    parser.add_argument(
        "--component-only",
        action="store_true",
        help="Only assemble base residual/component diagnostics; skip JVP and state-scale sweeps.",
    )
    parser.add_argument(
        "--hotspot-sweep",
        action="store_true",
        help="Evaluate tiny signed-displacement residual sweeps on frame-dominant translation hotspots.",
    )
    parser.add_argument(
        "--hotspot-sweep-step-values",
        default="1e-10,3e-10,1e-9",
        help="Comma-separated displacement steps in meters for --hotspot-sweep.",
    )
    parser.add_argument(
        "--hotspot-jvp",
        action="store_true",
        help="Evaluate tangent-vs-finite-difference JVP rows for frame-dominant hotspot DOFs.",
    )
    parser.add_argument(
        "--hotspot-jvp-max-rows",
        type=int,
        default=6,
        help="Maximum hotspot DOFs to evaluate for --hotspot-jvp.",
    )
    parser.add_argument(
        "--hotspot-jvp-component-filter",
        choices=("frame", "shell_bending_drilling", "shell_membrane", "translation", "all"),
        default="frame",
        help="Dominant component filter for --hotspot-jvp rows.",
    )
    parser.add_argument(
        "--hotspot-diagonal-newton-sweep",
        action="store_true",
        help="Evaluate diagonal Newton correction candidates on frame-dominant hotspot DOFs.",
    )
    parser.add_argument(
        "--hotspot-diagonal-newton-alpha-values",
        default="1,0.5,0.25,0.1,0.01,0.001",
        help="Comma-separated alpha values for --hotspot-diagonal-newton-sweep.",
    )
    args = parser.parse_args(argv)
    state_scale_values = tuple(
        float(value.strip())
        for value in str(args.state_scale_values).split(",")
        if value.strip()
    )
    payload = run_mgt_residual_jacobian_consistency_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        fd_step=float(args.fd_step),
        top_residual_count=int(args.top_residual_count),
        sample_count=int(args.sample_count),
        sample_seed=int(args.sample_seed),
        state_scale_values=state_scale_values,
        component_only=bool(args.component_only),
        hotspot_sweep=bool(args.hotspot_sweep),
        hotspot_sweep_step_values=tuple(
            float(value.strip())
            for value in str(args.hotspot_sweep_step_values).split(",")
            if value.strip()
        ),
        hotspot_jvp=bool(args.hotspot_jvp),
        hotspot_jvp_max_rows=int(args.hotspot_jvp_max_rows),
        hotspot_jvp_component_filter=str(args.hotspot_jvp_component_filter),
        hotspot_diagonal_newton_sweep=bool(args.hotspot_diagonal_newton_sweep),
        hotspot_diagonal_newton_alpha_values=tuple(
            float(value.strip())
            for value in str(args.hotspot_diagonal_newton_alpha_values).split(",")
            if value.strip()
        ),
    )
    print(
        "mgt-residual-jacobian-consistency:",
        payload["status"],
        f"base={payload.get('base_residual_inf_n')}",
        "->",
        args.output_json,
    )
    if payload.get("component_only"):
        return 0
    return 0 if payload.get("residual_jacobian_consistency_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
