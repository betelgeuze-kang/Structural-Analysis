#!/usr/bin/env python3
"""Shared shell material tangent helpers for MGT residual assembly."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from run_mgt_frame_material_nonlinear_tangent import (
    MaterialTangentState,
    _material_e_mpa,
    _material_tangent_state,
    _probe_strain,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE
from run_mgt_surface_membrane_tangent import _local_basis, _triangulate


def surface_strain_proxy(
    *,
    elem_index: int,
    node_xyz: np.ndarray,
    u: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
) -> float:
    """Return a deterministic membrane-like edge strain proxy for a surface row."""
    conn = [int(node) for node in conn_idx[conn_ptr[elem_index] : conn_ptr[elem_index + 1]].tolist()]
    if len(conn) not in {3, 4}:
        return 0.0
    disp = np.asarray(u, dtype=np.float64).reshape((-1, DOF_PER_NODE))[:, :3]
    best = 0.0
    for tri in _triangulate(conn):
        points = np.asarray([node_xyz[node] for node in tri], dtype=np.float64)
        if _local_basis(points[0], points[1], points[2]) is None:
            continue
        for local_i, local_j in ((0, 1), (1, 2), (2, 0)):
            ni = int(tri[local_i])
            nj = int(tri[local_j])
            edge = np.asarray(node_xyz[nj] - node_xyz[ni], dtype=np.float64)
            length = max(float(np.linalg.norm(edge)), 1.0e-12)
            direction = edge / length
            strain = float(np.dot(disp[nj] - disp[ni], direction) / length)
            if abs(strain) > abs(best):
                best = strain
    return float(best)


def _state_summary(states: list[MaterialTangentState]) -> dict[str, Any]:
    ratios = [float(state.tangent_ratio) for state in states]
    strains = [abs(float(state.strain)) for state in states]
    nonlinear = [
        state
        for state in states
        if state.material_family != "USER" and float(state.tangent_ratio) < 0.98
    ]
    return {
        "surface_element_count": int(len(states)),
        "material_family_counts": dict(Counter(state.material_family for state in states)),
        "state_tag_counts": dict(Counter(state.state_tag for state in states)),
        "nonlinear_tangent_surface_element_count": int(len(nonlinear)),
        "min_tangent_ratio": float(min(ratios)) if ratios else 1.0,
        "mean_tangent_ratio": float(np.mean(ratios)) if ratios else 1.0,
        "max_abs_strain": float(max(strains)) if strains else 0.0,
    }


def shell_material_tangent_by_surface_index(
    *,
    node_xyz: np.ndarray,
    u: np.ndarray,
    elem_type_code: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    controlled_probe: bool = False,
) -> tuple[dict[int, float], dict[str, Any]]:
    """Map MGT surface element indices to bounded solver material tangent MPa."""
    tangent_by_surface: dict[int, float] = {}
    states: list[MaterialTangentState] = []
    surface_indices = np.where(np.asarray(elem_type_code, dtype=np.int32) == 2)[0]
    for surface_index in surface_indices.tolist():
        material_id = int(elem_material_id[int(surface_index)])
        mat = material_props.get(material_id, {})
        fallback_e_mpa = _material_e_mpa(mat, fallback_mpa=210000.0)
        strain = surface_strain_proxy(
            elem_index=int(surface_index),
            node_xyz=node_xyz,
            u=u,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
        )
        if controlled_probe:
            strain = _probe_strain(mat, strain, fallback_e_mpa=fallback_e_mpa)
        state = _material_tangent_state(mat, strain, fallback_e_mpa=fallback_e_mpa)
        tangent_by_surface[int(surface_index)] = float(state.solver_tangent_mpa)
        states.append(state)
    summary = _state_summary(states)
    return tangent_by_surface, {
        "shell_material_tangent_mode": (
            "controlled_probe" if controlled_probe else "state_edge_strain_proxy"
        ),
        "shell_material_tangent_surface_element_count": int(len(tangent_by_surface)),
        **summary,
    }
