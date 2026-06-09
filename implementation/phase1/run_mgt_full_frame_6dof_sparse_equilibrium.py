#!/usr/bin/env python3
"""Run a full line-element MGT sparse 6-DOF frame equilibrium solve."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, eye
from scipy.sparse.linalg import spsolve

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-full-frame-6dof-sparse-equilibrium.v1"
DOF_PER_NODE = 6  # ux, uy, uz, rx, ry, rz
LINEAR_SOLVER_REFINEMENT_ENABLED = True
LINEAR_SOLVER_REFINEMENT_MAX_ITERATIONS = 10
LINEAR_SOLVER_REFINEMENT_STRATEGY = "best_residual_iterative_refinement"
LINEAR_SOLVER_RESIDUAL_METRIC = "regularized_free_dof_linear_subproblem_inf_norm"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


@dataclass(frozen=True)
class FrameElement:
    elem_id: int
    node_i: int
    node_j: int
    section_id: int
    material_id: int
    length_m: float
    local_axis_angle_deg: float = 0.0
    offset_i_global_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_j_global_m: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class FrameProps:
    area_m2: float
    e_n_per_m2: float
    g_n_per_m2: float
    iy_m4: float
    iz_m4: float
    j_m4: float


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _linear_solver_refinement_policy() -> dict[str, Any]:
    return {
        "enabled": LINEAR_SOLVER_REFINEMENT_ENABLED,
        "max_iterations": LINEAR_SOLVER_REFINEMENT_MAX_ITERATIONS,
        "strategy": LINEAR_SOLVER_REFINEMENT_STRATEGY,
        "residual_metric": LINEAR_SOLVER_RESIDUAL_METRIC,
        "claim_boundary": (
            "Refines the regularized free-DOF linear subproblem solve and keeps the lowest residual iterate. "
            "It is not a substitute for a consistent nonlinear Newton/Jacobian."
        ),
    }


def _beam_end_offset_lookup(rows: object) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    lookup: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    if not isinstance(rows, list):
        return lookup
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("coordinate_system") or "").upper() != "GLOBAL":
            continue
        i_offset = row.get("i_offset_m")
        j_offset = row.get("j_offset_m")
        if not isinstance(i_offset, dict) or not isinstance(j_offset, dict):
            continue
        i_vec = np.asarray(
            [
                float(i_offset.get("x") or 0.0),
                float(i_offset.get("y") or 0.0),
                float(i_offset.get("z") or 0.0),
            ],
            dtype=np.float64,
        )
        j_vec = np.asarray(
            [
                float(j_offset.get("x") or 0.0),
                float(j_offset.get("y") or 0.0),
                float(j_offset.get("z") or 0.0),
            ],
            dtype=np.float64,
        )
        for elem_id in row.get("element_ids") or []:
            try:
                lookup[int(elem_id)] = (i_vec, j_vec)
            except (TypeError, ValueError):
                continue
    return lookup


def _element_angle_array_from_props(props: dict[str, Any], elem_id: np.ndarray) -> np.ndarray:
    rows = props.get("element_local_axes") if isinstance(props, dict) else []
    angle_lookup: dict[int, float] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or row.get("family") != "line":
                continue
            try:
                angle_lookup[int(row.get("element_id"))] = float(row.get("angle_deg") or 0.0)
            except (TypeError, ValueError):
                continue
    return np.asarray([angle_lookup.get(int(eid), 0.0) for eid in elem_id], dtype=np.float64)


def _node_dofs(node: int) -> tuple[int, int, int, int, int, int]:
    base = int(node) * DOF_PER_NODE
    return base, base + 1, base + 2, base + 3, base + 4, base + 5


def _select_full_line_mesh(
    *,
    node_xyz: np.ndarray,
    edge_index: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    elem_angle_deg: np.ndarray | None = None,
    beam_end_offsets: dict[int, tuple[np.ndarray, np.ndarray]] | None = None,
) -> tuple[list[FrameElement], np.ndarray, dict[str, Any]]:
    n_elem = int(elem_id.shape[0])
    edge = np.asarray(edge_index[:, :n_elem], dtype=np.int64)
    line_mask = np.asarray(elem_type_code, dtype=np.int32) == 1
    angle_array = (
        np.asarray(elem_angle_deg, dtype=np.float64)
        if elem_angle_deg is not None
        else np.zeros(n_elem, dtype=np.float64)
    )
    used_nodes = sorted(
        set(edge[0, line_mask].astype(int).tolist())
        | set(edge[1, line_mask].astype(int).tolist())
    )
    remap = {old: new for new, old in enumerate(used_nodes)}
    node_xyz_sub = np.asarray([node_xyz[old] for old in used_nodes], dtype=np.float64)
    elements: list[FrameElement] = []
    skipped_short = 0
    offset_applied_count = 0
    max_abs_offset = 0.0
    angle_element_count = 0
    nonzero_angle_count = 0
    max_abs_angle_deg = 0.0
    beam_end_offsets = beam_end_offsets or {}
    for idx in np.where(line_mask)[0]:
        old_i = int(edge[0, idx])
        old_j = int(edge[1, idx])
        if old_i not in remap or old_j not in remap:
            continue
        i = remap[old_i]
        j = remap[old_j]
        elem_id_int = int(elem_id[idx])
        offset_i, offset_j = beam_end_offsets.get(
            elem_id_int,
            (
                np.zeros(3, dtype=np.float64),
                np.zeros(3, dtype=np.float64),
            ),
        )
        offset_i = np.asarray(offset_i, dtype=np.float64)
        offset_j = np.asarray(offset_j, dtype=np.float64)
        if np.any(np.abs(offset_i) > 1.0e-12) or np.any(np.abs(offset_j) > 1.0e-12):
            offset_applied_count += 1
            max_abs_offset = max(max_abs_offset, float(np.max(np.abs([*offset_i, *offset_j]))))
        length_m = float(np.linalg.norm((node_xyz_sub[j] + offset_j) - (node_xyz_sub[i] + offset_i)))
        if length_m < 0.25:
            skipped_short += 1
            continue
        angle_deg = float(angle_array[idx]) if idx < int(angle_array.shape[0]) else 0.0
        angle_element_count += int(elem_angle_deg is not None)
        if abs(angle_deg) > 1.0e-12:
            nonzero_angle_count += 1
            max_abs_angle_deg = max(max_abs_angle_deg, abs(angle_deg))
        elements.append(
            FrameElement(
                elem_id=elem_id_int,
                node_i=i,
                node_j=j,
                section_id=int(elem_section_id[idx]),
                material_id=int(elem_material_id[idx]),
                length_m=length_m,
                local_axis_angle_deg=angle_deg,
                offset_i_global_m=(float(offset_i[0]), float(offset_i[1]), float(offset_i[2])),
                offset_j_global_m=(float(offset_j[0]), float(offset_j[1]), float(offset_j[2])),
            )
        )
    return elements, node_xyz_sub, {
        "raw_line_element_count": int(np.count_nonzero(line_mask)),
        "skipped_short_or_degenerate_count": skipped_short,
        "line_node_count": len(used_nodes),
        "beam_end_offset_applied_element_count": int(offset_applied_count),
        "beam_end_offset_max_abs_m": float(max_abs_offset),
        "frame_local_axis_angle_array_present": bool(elem_angle_deg is not None),
        "frame_local_axis_angle_element_count": int(angle_element_count),
        "frame_local_axis_nonzero_angle_count": int(nonzero_angle_count),
        "frame_local_axis_max_abs_angle_deg": float(max_abs_angle_deg),
    }


def _component_restraints(elements: list[FrameElement], node_xyz: np.ndarray) -> tuple[set[int], int, int]:
    adjacency: dict[int, list[int]] = {idx: [] for idx in range(int(node_xyz.shape[0]))}
    for elem in elements:
        adjacency[elem.node_i].append(elem.node_j)
        adjacency[elem.node_j].append(elem.node_i)
    visited: set[int] = set()
    restrained: set[int] = set()
    component_count = 0
    base_node_count = 0
    for start in range(int(node_xyz.shape[0])):
        if start in visited or not adjacency.get(start):
            continue
        queue = [start]
        visited.add(start)
        component_nodes: list[int] = []
        while queue:
            current = queue.pop()
            component_nodes.append(current)
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        z_min = float(np.min(node_xyz[component_nodes, 2]))
        base_nodes = [
            node for node in component_nodes if abs(float(node_xyz[node, 2]) - z_min) <= 0.05
        ]
        if not base_nodes:
            base_nodes = [component_nodes[0]]
        for node in base_nodes:
            restrained.update(_node_dofs(node))
        component_count += 1
        base_node_count += len(base_nodes)
    return restrained, component_count, base_node_count


def _fallback_props(length_m: float, section_id: int) -> FrameProps:
    scale = 1.0 + float(int(section_id) % 19) * 0.018
    e = 210.0e9
    nu = 0.3
    area = 0.022 * scale
    iy = 7.5e-5 * scale**2
    iz = 5.5e-5 * scale**2
    return FrameProps(
        area_m2=area,
        e_n_per_m2=e,
        g_n_per_m2=e / (2.0 * (1.0 + nu)),
        iy_m4=iy,
        iz_m4=iz,
        j_m4=max(iy + iz, area * max(length_m, 0.5) ** 2 * 1.0e-4, 1.0e-9),
    )


def _frame_props(
    elem: FrameElement,
    *,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> tuple[FrameProps, bool]:
    sec = section_props.get(int(elem.section_id))
    mat = material_props.get(int(elem.material_id))
    if sec is None or mat is None:
        return _fallback_props(elem.length_m, elem.section_id), False
    e = float(mat["E_kN_per_m2"]) * 1000.0
    nu = float(mat.get("poisson", 0.3) or 0.3)
    area = max(float(sec["A_m2"]), 1.0e-9)
    iy = max(float(sec["Iy_m4"]), 1.0e-12)
    iz = max(float(sec["Iz_m4"]), 1.0e-12)
    return (
        FrameProps(
            area_m2=area,
            e_n_per_m2=e,
            g_n_per_m2=e / (2.0 * (1.0 + nu)),
            iy_m4=iy,
            iz_m4=iz,
            j_m4=max(iy + iz, 1.0e-12),
        ),
        True,
    )


def _local_frame_stiffness(props: FrameProps, length_m: float) -> np.ndarray:
    length = max(float(length_m), 1.0e-6)
    k = np.zeros((12, 12), dtype=np.float64)
    ea_l = props.e_n_per_m2 * props.area_m2 / length
    gj_l = props.g_n_per_m2 * props.j_m4 / length
    eiy = props.e_n_per_m2 * props.iy_m4
    eiz = props.e_n_per_m2 * props.iz_m4

    for a, b, val in ((0, 0, ea_l), (0, 6, -ea_l), (6, 0, -ea_l), (6, 6, ea_l)):
        k[a, b] += val
    for a, b, val in ((3, 3, gj_l), (3, 9, -gj_l), (9, 3, -gj_l), (9, 9, gj_l)):
        k[a, b] += val

    l2 = length * length
    l3 = l2 * length
    sub_z = np.array(
        [
            [12.0 * eiz / l3, 6.0 * eiz / l2, -12.0 * eiz / l3, 6.0 * eiz / l2],
            [6.0 * eiz / l2, 4.0 * eiz / length, -6.0 * eiz / l2, 2.0 * eiz / length],
            [-12.0 * eiz / l3, -6.0 * eiz / l2, 12.0 * eiz / l3, -6.0 * eiz / l2],
            [6.0 * eiz / l2, 2.0 * eiz / length, -6.0 * eiz / l2, 4.0 * eiz / length],
        ],
        dtype=np.float64,
    )
    for a, ia in enumerate((1, 5, 7, 11)):
        for b, ib in enumerate((1, 5, 7, 11)):
            k[ia, ib] += sub_z[a, b]

    sub_y = np.array(
        [
            [12.0 * eiy / l3, -6.0 * eiy / l2, -12.0 * eiy / l3, -6.0 * eiy / l2],
            [-6.0 * eiy / l2, 4.0 * eiy / length, 6.0 * eiy / l2, 2.0 * eiy / length],
            [-12.0 * eiy / l3, 6.0 * eiy / l2, 12.0 * eiy / l3, 6.0 * eiy / l2],
            [-6.0 * eiy / l2, 2.0 * eiy / length, 6.0 * eiy / l2, 4.0 * eiy / length],
        ],
        dtype=np.float64,
    )
    for a, ia in enumerate((2, 4, 8, 10)):
        for b, ib in enumerate((2, 4, 8, 10)):
            k[ia, ib] += sub_y[a, b]
    return 0.5 * (k + k.T)


def _local_frame_geometric_stiffness(axial_force_n: float, length_m: float) -> np.ndarray:
    p = max(float(axial_force_n), 0.0)
    if p <= 0.0:
        return np.zeros((12, 12), dtype=np.float64)
    length = max(float(length_m), 1.0e-6)
    coeff = p / (30.0 * length)
    sub = coeff * np.array(
        [
            [36.0, 3.0 * length, -36.0, 3.0 * length],
            [3.0 * length, 4.0 * length**2, -3.0 * length, -1.0 * length**2],
            [-36.0, -3.0 * length, 36.0, -3.0 * length],
            [3.0 * length, -1.0 * length**2, -3.0 * length, 4.0 * length**2],
        ],
        dtype=np.float64,
    )
    kg = np.zeros((12, 12), dtype=np.float64)
    for dofs in ((1, 5, 7, 11), (2, 4, 8, 10)):
        for a, ia in enumerate(dofs):
            for b, ib in enumerate(dofs):
                kg[ia, ib] += sub[a, b]
    return 0.5 * (kg + kg.T)


def _rotation_matrix(pi: np.ndarray, pj: np.ndarray, roll_deg: float = 0.0) -> np.ndarray:
    x_axis = np.asarray(pj - pi, dtype=np.float64)
    x_axis /= max(float(np.linalg.norm(x_axis)), 1.0e-12)
    reference = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(float(np.dot(x_axis, reference))) > 0.95:
        reference = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    y_axis = np.cross(reference, x_axis)
    y_axis /= max(float(np.linalg.norm(y_axis)), 1.0e-12)
    z_axis = np.cross(x_axis, y_axis)
    z_axis /= max(float(np.linalg.norm(z_axis)), 1.0e-12)
    if abs(float(roll_deg)) > 1.0e-12:
        angle = np.deg2rad(float(roll_deg))
        c = float(np.cos(angle))
        s = float(np.sin(angle))
        y_base = y_axis.copy()
        z_base = z_axis.copy()
        y_axis = c * y_base + s * z_base
        z_axis = -s * y_base + c * z_base
        y_axis /= max(float(np.linalg.norm(y_axis)), 1.0e-12)
        z_axis /= max(float(np.linalg.norm(z_axis)), 1.0e-12)
    return np.vstack([x_axis, y_axis, z_axis])


def _transform_stiffness(k_local: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    transform = np.zeros((12, 12), dtype=np.float64)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = rotation
    return transform.T @ k_local @ transform


def _skew(vec: np.ndarray) -> np.ndarray:
    x, y, z = [float(value) for value in np.asarray(vec, dtype=np.float64)]
    return np.array(
        [
            [0.0, -z, y],
            [z, 0.0, -x],
            [-y, x, 0.0],
        ],
        dtype=np.float64,
    )


def _rigid_end_offset_transform(offset_i: np.ndarray, offset_j: np.ndarray) -> np.ndarray:
    transform = np.eye(12, dtype=np.float64)
    transform[0:3, 3:6] = -_skew(offset_i)
    transform[6:9, 9:12] = -_skew(offset_j)
    return transform


def _element_end_points(elem: FrameElement, node_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    offset_i = np.asarray(elem.offset_i_global_m, dtype=np.float64)
    offset_j = np.asarray(elem.offset_j_global_m, dtype=np.float64)
    return node_xyz[elem.node_i] + offset_i, node_xyz[elem.node_j] + offset_j


def _assemble_sparse_frame(
    *,
    elements: list[FrameElement],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    element_axial_forces: dict[int, float] | None = None,
    include_geometric: bool = False,
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(n_dof, dtype=np.float64)
    real_count = 0
    total_gravity_n = 0.0
    section_usage: Counter[int] = Counter()
    material_usage: Counter[int] = Counter()
    local_axis_roll_count = 0
    local_axis_max_abs_angle_deg = 0.0
    for elem in elements:
        props, used_real = _frame_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        real_count += int(bool(used_real))
        section_usage[int(elem.section_id)] += 1
        material_usage[int(elem.material_id)] += 1
        weight_n = props.area_m2 * float(elem.length_m) * 7850.0 * 9.80665
        total_gravity_n += weight_n
        offset_i = np.asarray(elem.offset_i_global_m, dtype=np.float64)
        offset_j = np.asarray(elem.offset_j_global_m, dtype=np.float64)
        rigid_transform = _rigid_end_offset_transform(offset_i, offset_j)
        f_end = np.zeros(12, dtype=np.float64)
        f_end[2] -= 0.5 * weight_n
        f_end[8] -= 0.5 * weight_n
        f_node = rigid_transform.T @ f_end
        pi, pj = _element_end_points(elem, node_xyz)
        if abs(float(elem.local_axis_angle_deg)) > 1.0e-12:
            local_axis_roll_count += 1
            local_axis_max_abs_angle_deg = max(local_axis_max_abs_angle_deg, abs(float(elem.local_axis_angle_deg)))
        rotation = _rotation_matrix(pi, pj, roll_deg=elem.local_axis_angle_deg)
        local = _local_frame_stiffness(props, elem.length_m)
        if include_geometric:
            local -= _local_frame_geometric_stiffness(
                axial_force_n=float((element_axial_forces or {}).get(elem.elem_id, 0.0)),
                length_m=elem.length_m,
            )
        ke_end = _transform_stiffness(local, rotation)
        ke = rigid_transform.T @ ke_end @ rigid_transform
        dofs = _node_dofs(elem.node_i) + _node_dofs(elem.node_j)
        for a, gi in enumerate(dofs):
            f_ext[gi] += float(f_node[a])
        for a, gi in enumerate(dofs):
            for b, gj in enumerate(dofs):
                rows.append(gi)
                cols.append(gj)
                vals.append(float(ke[a, b]))
    stiffness = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()
    meta = {
        "real_section_material_element_count": real_count,
        "real_section_material_coverage_pct": 100.0 * float(real_count) / max(float(len(elements)), 1.0),
        "total_gravity_n": total_gravity_n,
        "unique_section_count": len(section_usage),
        "unique_material_count": len(material_usage),
        "local_axis_roll_transform_applied_count": int(local_axis_roll_count),
        "local_axis_max_abs_angle_deg": float(local_axis_max_abs_angle_deg),
        "section_usage_head": dict(section_usage.most_common(10)),
        "material_usage_head": dict(material_usage.most_common(10)),
    }
    return stiffness, f_ext, meta


def _component_gravity_axial_forces(
    *,
    elements: list[FrameElement],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> dict[int, float]:
    by_node: dict[int, list[FrameElement]] = {idx: [] for idx in range(int(node_xyz.shape[0]))}
    weights: dict[int, float] = {}
    pcr_cap: dict[int, float] = {}
    for elem in elements:
        by_node[elem.node_i].append(elem)
        by_node[elem.node_j].append(elem)
        props, _used_real = _frame_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        weights[elem.elem_id] = props.area_m2 * float(elem.length_m) * 7850.0 * 9.80665
        ei_min = props.e_n_per_m2 * min(props.iy_m4, props.iz_m4)
        pcr = float(np.pi**2 * ei_min / max(float(elem.length_m) ** 2, 1.0e-9))
        pcr_cap[elem.elem_id] = 0.25 * max(pcr, 0.0)

    visited_nodes: set[int] = set()
    axial: dict[int, float] = {}
    for start in range(int(node_xyz.shape[0])):
        if start in visited_nodes or not by_node.get(start):
            continue
        queue = [start]
        visited_nodes.add(start)
        component_elements: dict[int, FrameElement] = {}
        while queue:
            current = queue.pop()
            for elem in by_node.get(current, []):
                component_elements[elem.elem_id] = elem
                other = elem.node_j if elem.node_i == current else elem.node_i
                if other not in visited_nodes:
                    visited_nodes.add(other)
                    queue.append(other)
        ordered = sorted(
            component_elements.values(),
            key=lambda elem: 0.5 * (float(node_xyz[elem.node_i, 2]) + float(node_xyz[elem.node_j, 2])),
            reverse=True,
        )
        weight_above = 0.0
        for elem in ordered:
            pi, pj = _element_end_points(elem, node_xyz)
            dz = abs(float(pj[2]) - float(pi[2]))
            verticality = dz / max(float(elem.length_m), 1.0e-9)
            raw_axial = max(weight_above, 0.0) * min(max(verticality, 0.0), 1.0)
            axial[elem.elem_id] = min(raw_axial, pcr_cap.get(elem.elem_id, raw_axial))
            weight_above += weights.get(elem.elem_id, 0.0)
    return axial


def _solve_sparse_system(*, stiffness: Any, f_ext: np.ndarray, free: np.ndarray) -> tuple[np.ndarray, float, float]:
    k_ff = stiffness[free, :][:, free].tocsc()
    diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
    regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
    k_ff = k_ff + eye(k_ff.shape[0], format="csc") * regularization
    u_free = spsolve(k_ff, f_ext[free])
    residual = k_ff @ u_free - f_ext[free]
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    best_u = np.asarray(u_free, dtype=np.float64)
    best_residual_inf = residual_inf
    # SuperLU can leave an absolute residual floor around the G1 tolerance for
    # the ill-conditioned geometric frame tangent. Keep the best refinement
    # iterate instead of assuming the last correction is monotone.
    for _refine_idx in range(LINEAR_SOLVER_REFINEMENT_MAX_ITERATIONS):
        if residual_inf <= 1.0e-6:
            break
        try:
            correction = np.asarray(spsolve(k_ff, -residual), dtype=np.float64)
        except Exception:
            break
        candidate = np.asarray(u_free, dtype=np.float64) + correction
        candidate_residual = k_ff @ candidate - f_ext[free]
        candidate_residual_inf = (
            float(np.max(np.abs(candidate_residual))) if candidate_residual.size else 0.0
        )
        if np.isfinite(candidate_residual_inf) and candidate_residual_inf < best_residual_inf:
            best_u = candidate
            best_residual_inf = candidate_residual_inf
        u_free = candidate
        residual = candidate_residual
        residual_inf = candidate_residual_inf
    return best_u, best_residual_inf, regularization


def _translation_metrics(u: np.ndarray, node_xyz: np.ndarray) -> dict[str, float]:
    if u.size == 0:
        return {
            "max_abs_displacement_m": 0.0,
            "max_translation_m": 0.0,
            "max_drift_ratio_pct": 0.0,
        }
    translations = u.reshape((-1, DOF_PER_NODE))[:, :3]
    z_vals = node_xyz[:, 2] if node_xyz.size else np.asarray([0.0])
    story_h = np.maximum(z_vals - float(np.min(z_vals)), 0.5)
    horizontal = np.linalg.norm(translations[:, :2], axis=1) if translations.size else np.asarray([0.0])
    return {
        "max_abs_displacement_m": float(np.max(np.abs(u))),
        "max_translation_m": float(np.max(np.linalg.norm(translations, axis=1))) if translations.size else 0.0,
        "max_drift_ratio_pct": float(np.max(horizontal / story_h * 100.0)) if horizontal.size else 0.0,
    }


def _solve_deformed_state_pdelta_fixed_point(
    *,
    elements: list[FrameElement],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float = 0.5,
    max_iterations: int = 12,
    relative_increment_tolerance: float = 1.0e-4,
    residual_tolerance_n: float = 1.0e-3,
    displacement_cap_m: float = 20.0,
    initial_displacement: np.ndarray | None = None,
    relaxation_factor: float = 1.0,
) -> tuple[dict[str, Any], np.ndarray]:
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    free = np.asarray([idx for idx in range(n_dof) if idx not in restrained], dtype=np.int64)
    axial_forces = {int(elem_id): float(force) * float(target_load_scale) for elem_id, force in base_axial_forces.items()}
    if initial_displacement is None:
        u = np.zeros(n_dof, dtype=np.float64)
    else:
        u = np.asarray(initial_displacement, dtype=np.float64).copy()
        if u.shape != (n_dof,):
            u = np.zeros(n_dof, dtype=np.float64)
    history: list[dict[str, float]] = []
    converged = False
    last_residual = float("inf")
    last_increment = float("inf")
    last_fixed_point_increment = float("inf")
    last_relative_increment = float("inf")
    last_regularization = 0.0
    relaxation = min(max(float(relaxation_factor), 1.0e-3), 1.0)
    for iteration in range(1, max_iterations + 1):
        translations = u.reshape((-1, DOF_PER_NODE))[:, :3] if u.size else np.zeros((0, 3), dtype=np.float64)
        deformed_xyz = node_xyz + translations
        tangent, f_step, _asm_meta = _assemble_sparse_frame(
            elements=elements,
            node_xyz=deformed_xyz,
            section_props=section_props,
            material_props=material_props,
            element_axial_forces=axial_forces,
            include_geometric=True,
        )
        u_free, residual_inf, regularization = _solve_sparse_system(
            stiffness=tangent,
            f_ext=f_step * float(target_load_scale),
            free=free,
        )
        fixed_point_candidate = np.zeros(n_dof, dtype=np.float64)
        fixed_point_candidate[free] = np.asarray(u_free, dtype=np.float64)
        fixed_point_increment = (
            float(np.max(np.abs(fixed_point_candidate - u))) if fixed_point_candidate.size else 0.0
        )
        fixed_point_max_abs = max(
            float(np.max(np.abs(fixed_point_candidate))) if fixed_point_candidate.size else 0.0,
            1.0e-9,
        )
        fixed_point_relative_increment = fixed_point_increment / fixed_point_max_abs
        candidate = fixed_point_candidate
        if relaxation < 1.0:
            candidate = (1.0 - relaxation) * u + relaxation * fixed_point_candidate
        increment = float(np.max(np.abs(candidate - u))) if candidate.size else 0.0
        max_abs = max(float(np.max(np.abs(candidate))) if candidate.size else 0.0, 1.0e-9)
        relative_increment = increment / max_abs
        metrics = _translation_metrics(candidate, node_xyz)
        history.append(
            {
                "iteration": float(iteration),
                "residual_inf_n": float(residual_inf),
                "max_increment_m": increment,
                "relative_increment": relative_increment,
                "fixed_point_increment_m": fixed_point_increment,
                "fixed_point_relative_increment": fixed_point_relative_increment,
                "max_translation_m": metrics["max_translation_m"],
                "relaxation_factor": relaxation,
            }
        )
        u = candidate
        last_residual = float(residual_inf)
        last_increment = increment
        last_fixed_point_increment = fixed_point_increment
        last_relative_increment = fixed_point_relative_increment
        last_regularization = float(regularization)
        if (
            residual_inf <= residual_tolerance_n
            and fixed_point_relative_increment <= relative_increment_tolerance
            and metrics["max_translation_m"] <= displacement_cap_m
        ):
            converged = True
            break

    final_metrics = _translation_metrics(u, node_xyz)
    ready = bool(converged and final_metrics["max_translation_m"] <= displacement_cap_m)
    return {
        "ready": ready,
        "converged": converged,
        "target_load_scale": float(target_load_scale),
        "load_scale_reached": float(target_load_scale) if ready else 0.0,
        "initial_displacement_was_seeded": bool(initial_displacement is not None),
        "relaxation_factor": relaxation,
        "iteration_count": len(history),
        "residual_inf_n": last_residual,
        "max_increment_m": last_increment,
        "fixed_point_increment_m": last_fixed_point_increment,
        "relative_increment": last_relative_increment,
        "convergence_increment_metric": "unrelaxed_fixed_point_relative_increment",
        "regularization": last_regularization,
        "linear_solver_refinement": _linear_solver_refinement_policy(),
        "max_abs_displacement_m": final_metrics["max_abs_displacement_m"],
        "max_translation_m": final_metrics["max_translation_m"],
        "max_drift_ratio_pct": final_metrics["max_drift_ratio_pct"],
        "history_tail": history[-5:],
        "claim_boundary": (
            "Deformed-coordinate 6-DOF frame P-Delta fixed-point path under scaled gravity. "
            "It is geometric nonlinear frame evidence, not full material nonlinear or shell/plate closure."
        ),
        "blockers": [] if ready else ["deformed_state_pdelta_path_not_converged"],
    }, u


def _run_deformed_state_pdelta_path(
    *,
    elements: list[FrameElement],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float = 0.5,
    max_iterations: int = 12,
    relative_increment_tolerance: float = 1.0e-4,
    residual_tolerance_n: float = 1.0e-3,
    displacement_cap_m: float = 20.0,
) -> dict[str, Any]:
    payload, _u = _solve_deformed_state_pdelta_fixed_point(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        base_axial_forces=base_axial_forces,
        restrained=restrained,
        target_load_scale=target_load_scale,
        max_iterations=max_iterations,
        relative_increment_tolerance=relative_increment_tolerance,
        residual_tolerance_n=residual_tolerance_n,
        displacement_cap_m=displacement_cap_m,
    )
    return payload


def run_mgt_full_frame_6dof_sparse_equilibrium(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    if not roundtrip_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["roundtrip_npz_missing"],
        }
    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = load_mgt_section_material_properties(mgt_path) if mgt_path.is_file() else {"sections": {}, "materials": {}}
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
    roundtrip = _load_json(roundtrip_json)

    started = time.perf_counter()
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        elem_id_array = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_angle_deg = (
            np.asarray(archive["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in archive.files
            else _element_angle_array_from_props(props, elem_id_array)
        )
        elem_lcaxis_code = (
            np.asarray(archive["elem_lcaxis_code"], dtype=np.int32)
            if "elem_lcaxis_code" in archive.files
            else None
        )
        local_axis_npz_meta = {
            "elem_angle_array_present": bool("elem_angle_deg" in archive.files),
            "elem_angle_source": "roundtrip_npz" if "elem_angle_deg" in archive.files else "mgt_direct_parser_fallback",
            "elem_angle_nonzero_count": int(np.count_nonzero(np.abs(elem_angle_deg) > 1.0e-12))
            if elem_angle_deg.size
            else 0,
            "elem_angle_max_abs_deg": float(np.max(np.abs(elem_angle_deg))) if elem_angle_deg.size else 0.0,
            "elem_lcaxis_array_present": bool(elem_lcaxis_code is not None),
            "elem_lcaxis_nonzero_count": int(np.count_nonzero(elem_lcaxis_code != 0))
            if elem_lcaxis_code is not None
            else 0,
        }
        elements, node_xyz_sub, select_meta = _select_full_line_mesh(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=elem_id_array,
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )
    select_s = time.perf_counter() - started
    restrained, component_count, base_node_count = _component_restraints(elements, node_xyz_sub)
    n_dof = int(node_xyz_sub.shape[0]) * DOF_PER_NODE
    free = np.asarray([idx for idx in range(n_dof) if idx not in restrained], dtype=np.int64)

    assemble_start = time.perf_counter()
    stiffness, f_ext, asm_meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
    )
    assemble_s = time.perf_counter() - assemble_start
    solve_start = time.perf_counter()
    u_free, residual_inf, regularization = _solve_sparse_system(stiffness=stiffness, f_ext=f_ext, free=free)
    solve_s = time.perf_counter() - solve_start

    u = np.zeros(n_dof, dtype=np.float64)
    u[free] = np.asarray(u_free, dtype=np.float64)
    axial_forces = _component_gravity_axial_forces(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
    )
    geometric_assemble_start = time.perf_counter()
    geometric_stiffness, _geo_f_ext, geo_asm_meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    geometric_assembly_s = time.perf_counter() - geometric_assemble_start
    geometric_solve_start = time.perf_counter()
    geo_u_free, geo_residual_inf, geo_regularization = _solve_sparse_system(
        stiffness=geometric_stiffness,
        f_ext=f_ext,
        free=free,
    )
    geometric_solve_s = time.perf_counter() - geometric_solve_start
    geo_u = np.zeros(n_dof, dtype=np.float64)
    geo_u[free] = np.asarray(geo_u_free, dtype=np.float64)
    offset_applied_count = int(select_meta.get("beam_end_offset_applied_element_count") or 0)
    deformed_path_start = time.perf_counter()
    deformed_path = _run_deformed_state_pdelta_path(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
        base_axial_forces=axial_forces,
        restrained=restrained,
        max_iterations=24 if offset_applied_count > 0 else 12,
    )
    deformed_path_s = time.perf_counter() - deformed_path_start
    translations = u.reshape((-1, DOF_PER_NODE))[:, :3] if n_dof else np.zeros((0, 3), dtype=np.float64)
    geo_translations = (
        geo_u.reshape((-1, DOF_PER_NODE))[:, :3] if n_dof else np.zeros((0, 3), dtype=np.float64)
    )
    z_vals = node_xyz_sub[:, 2] if node_xyz_sub.size else np.asarray([0.0])
    story_h = np.maximum(z_vals - float(np.min(z_vals)), 0.5)
    horizontal = np.linalg.norm(translations[:, :2], axis=1) if translations.size else np.asarray([0.0])
    geo_horizontal = np.linalg.norm(geo_translations[:, :2], axis=1) if geo_translations.size else np.asarray([0.0])
    max_drift_ratio_pct = float(np.max(horizontal / story_h * 100.0)) if horizontal.size else 0.0
    geo_max_drift_ratio_pct = float(np.max(geo_horizontal / story_h * 100.0)) if geo_horizontal.size else 0.0
    max_translation_m = float(np.max(np.linalg.norm(translations, axis=1))) if translations.size else 0.0
    geo_max_translation_m = (
        float(np.max(np.linalg.norm(geo_translations, axis=1))) if geo_translations.size else 0.0
    )
    solved_all_line = int(select_meta["raw_line_element_count"]) == len(elements) + int(select_meta["skipped_short_or_degenerate_count"])
    elastic_ready = bool(
        solved_all_line
        and len(elements) > 0
        and free.size > 0
        and np.all(np.isfinite(u_free))
        and residual_inf <= 1.0e-3
    )
    axial_positive = [force for force in axial_forces.values() if float(force) > 0.0]
    geometric_ready = bool(
        elastic_ready
        and np.all(np.isfinite(geo_u_free))
        and geo_residual_inf <= 1.0e-3
        and len(axial_positive) > 0
    )
    rigid_end_offset_tangent_ready = bool(offset_applied_count > 0 and elastic_ready and geometric_ready)
    local_axis_support = {
        **local_axis_npz_meta,
        "frame_angle_rows_consumed": bool(select_meta.get("frame_local_axis_angle_array_present")),
        "frame_angle_element_count": int(select_meta.get("frame_local_axis_angle_element_count") or 0),
        "frame_nonzero_angle_element_count": int(select_meta.get("frame_local_axis_nonzero_angle_count") or 0),
        "frame_max_abs_angle_deg": float(select_meta.get("frame_local_axis_max_abs_angle_deg") or 0.0),
        "solver_local_axis_roll_transform_ready": bool(
            int(asm_meta.get("local_axis_roll_transform_applied_count") or 0) > 0
            and int(geo_asm_meta.get("local_axis_roll_transform_applied_count") or 0) > 0
        ),
        "elastic_assembly_roll_transform_applied_count": int(
            asm_meta.get("local_axis_roll_transform_applied_count") or 0
        ),
        "geometric_assembly_roll_transform_applied_count": int(
            geo_asm_meta.get("local_axis_roll_transform_applied_count") or 0
        ),
        "source_surface_lcaxis_nonzero_count": int(local_axis_npz_meta["elem_lcaxis_nonzero_count"]),
    }
    linear_solver_refinement = _linear_solver_refinement_policy()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if elastic_ready and geometric_ready and deformed_path["ready"] else "partial",
        "full_frame_6dof_sparse_elastic_equilibrium_ready": elastic_ready,
        "full_frame_6dof_linearized_geometric_equilibrium_ready": geometric_ready,
        "full_frame_6dof_deformed_state_pdelta_equilibrium_ready": deformed_path["ready"],
        "full_frame_6dof_nonlinear_equilibrium": False,
        "frame_local_axis_support": local_axis_support,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "solve_scope": "full_line_element_mesh_sparse_6dof_frame_elastic_linearized_geometric_and_deformed_state_pdelta",
        "linear_solver_refinement": linear_solver_refinement,
        "claim_boundary": (
            "Solves the full line/beam element graph with 6 DOF per node and 3D frame stiffness under "
            "gravity loads, including linearized geometric and scaled deformed-state P-Delta passes. "
            "MGT GLOBAL beam end offsets are applied through a rigid-end transformation when present. "
            "MGT frame ANGLE rows are consumed as local y/z roll transforms when present. "
            "This removes the prior collapsed-horizontal-DOF line solve limitation, but does not close "
            "full material nonlinear Newton, shell/plate, diaphragm, or design-code claims."
        ),
        "mesh_fingerprint": {
            **select_meta,
            "line_elements_solved": len(elements),
            "line_nodes_solved": int(node_xyz_sub.shape[0]),
            "component_count": component_count,
            "base_node_count": base_node_count,
            "dof_count": n_dof,
            "free_dof_count": int(free.size),
            "restrained_dof_count": len(restrained),
            "stiffness_nnz": int(stiffness.nnz),
            "geometric_stiffness_nnz": int(geometric_stiffness.nnz),
        },
        "section_material_coverage": asm_meta,
        "linearized_geometric_tangent": {
            "positive_axial_element_count": len(axial_positive),
            "max_axial_force_n": float(max(axial_positive)) if axial_positive else 0.0,
            "mean_positive_axial_force_n": float(np.mean(axial_positive)) if axial_positive else 0.0,
            "real_section_material_coverage_pct": geo_asm_meta.get("real_section_material_coverage_pct"),
        },
        "beam_end_offset_support": {
            "typed_mgt_offset_parser_ready": bool(beam_end_offsets),
            "global_beam_end_offset_elements_available": int(len(beam_end_offsets)),
            "rigid_end_offset_transform_applied": bool(offset_applied_count > 0),
            "rigid_end_offset_tangent_ready": rigid_end_offset_tangent_ready,
            "applied_element_count": offset_applied_count,
            "max_abs_offset_m": float(select_meta.get("beam_end_offset_max_abs_m") or 0.0),
            "load_eccentricity_moments_applied": bool(offset_applied_count > 0),
            "geometric_tangent_uses_offset_length": bool(offset_applied_count > 0 and geometric_ready),
            "not_closed": [
                "ELEMENT local-yz offset rows are still unsupported in this solver path",
                "roundtrip export and non-frame shell/surface eccentricity semantics have not consumed beam offsets yet",
            ],
        },
        "equilibrium_metrics": {
            "residual_inf_n": residual_inf,
            "max_abs_displacement_m": float(np.max(np.abs(u_free))) if u_free.size else 0.0,
            "max_translation_m": max_translation_m,
            "max_drift_ratio_pct": max_drift_ratio_pct,
            "total_gravity_kn": float(asm_meta["total_gravity_n"]) / 1000.0,
            "regularization": regularization,
            "linear_solver_refinement_enabled": bool(linear_solver_refinement["enabled"]),
            "linear_solver_refinement_strategy": str(linear_solver_refinement["strategy"]),
        },
        "geometric_equilibrium_metrics": {
            "residual_inf_n": geo_residual_inf,
            "max_abs_displacement_m": float(np.max(np.abs(geo_u_free))) if geo_u_free.size else 0.0,
            "max_translation_m": geo_max_translation_m,
            "max_drift_ratio_pct": geo_max_drift_ratio_pct,
            "regularization": geo_regularization,
            "linear_solver_refinement_enabled": bool(linear_solver_refinement["enabled"]),
            "linear_solver_refinement_strategy": str(linear_solver_refinement["strategy"]),
        },
        "deformed_state_pdelta_path": deformed_path,
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_6dof_frame",
            "linear_solver_refinement_enabled": bool(linear_solver_refinement["enabled"]),
            "linear_solver_refinement_max_iterations": int(linear_solver_refinement["max_iterations"]),
            "selection_seconds": select_s,
            "assembly_seconds": assemble_s,
            "solve_seconds": solve_s,
            "geometric_assembly_seconds": geometric_assembly_s,
            "geometric_solve_seconds": geometric_solve_s,
            "deformed_state_pdelta_seconds": deformed_path_s,
            "total_seconds": select_s
            + assemble_s
            + solve_s
            + geometric_assembly_s
            + geometric_solve_s
            + deformed_path_s,
        },
        "limitations": [
            "Scaled deformed-state P-Delta path is fixed-point geometric nonlinear evidence, not full Newton/material closure.",
            "Frame line elements only; shell/plate/solid surfaces remain unsupported by this artifact.",
            "Component base-node auto-restraints are an evidence harness boundary condition, not a full user-authored support model.",
            "Only MGT GLOBAL beam end offsets are applied; local ELEMENT offset rows remain queued.",
        ],
        "blockers": []
        if elastic_ready and geometric_ready and deformed_path["ready"]
        else [
            *([] if elastic_ready and geometric_ready else ["full_frame_6dof_sparse_geometric_equilibrium_not_ready"]),
            *([] if deformed_path["ready"] else ["full_frame_6dof_deformed_state_pdelta_not_ready"]),
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_full_frame_6dof_sparse_equilibrium.json")
    args = parser.parse_args()
    payload = run_mgt_full_frame_6dof_sparse_equilibrium(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
    )
    mesh = payload.get("mesh_fingerprint") or {}
    print(
        "mgt-full-frame-6dof-sparse: "
        f"status={payload['status']} line={mesh.get('line_elements_solved')}/{mesh.get('raw_line_element_count')} "
        f"elastic_residual={(payload.get('equilibrium_metrics') or {}).get('residual_inf_n')} "
        f"geometric_residual={(payload.get('geometric_equilibrium_metrics') or {}).get('residual_inf_n')} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
