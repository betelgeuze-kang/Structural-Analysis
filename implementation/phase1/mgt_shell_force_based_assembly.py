#!/usr/bin/env python3
"""Linear force-consistent shell internal-force recovery at reference geometry."""

from __future__ import annotations

from typing import Any

import numpy as np

from mgt_equilibrium_geometry_contract import EQUILIBRIUM_GEOMETRY_CONTRACT, assembly_node_xyz
from mgt_equilibrium_shell_assembly import assemble_equilibrium_surface_shell_6dof


def _cached_shell_operator(
    *,
    u: np.ndarray,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    include_membrane: bool,
    shell_operator_cache: dict[str, Any] | None,
    material_tangent_by_surface_index_mpa: dict[int, float] | None = None,
) -> tuple[Any, dict[str, Any], bool]:
    cache_key = "shell_full_membrane_bending" if include_membrane else "shell_bending_drilling"
    material_override_enabled = bool(material_tangent_by_surface_index_mpa)
    if (
        not material_override_enabled
        and shell_operator_cache is not None
        and cache_key in shell_operator_cache
    ):
        cached = shell_operator_cache[cache_key]
        return cached["stiffness"], dict(cached["meta"]), True
    assembly_xyz = assembly_node_xyz(node_xyz=node_xyz, u=u)
    shell_stiffness, _shell_f, shell_meta, _surface_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=assembly_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=include_membrane,
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    shell_meta = {
        **dict(shell_meta),
        "shell_material_tangent_override_enabled": material_override_enabled,
        "shell_material_tangent_operator_cache_disabled": material_override_enabled,
    }
    if shell_operator_cache is not None and not material_override_enabled:
        shell_operator_cache[cache_key] = {
            "stiffness": shell_stiffness,
            "meta": dict(shell_meta),
            "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        }
    return shell_stiffness, dict(shell_meta), False


def assemble_shell_internal_force_components(
    *,
    u: np.ndarray,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    shell_operator_cache: dict[str, Any] | None = None,
    material_tangent_by_surface_index_mpa: dict[int, float] | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Recover additive shell resisting-force components for diagnostics."""
    shell_full, full_meta, full_cache_hit = _cached_shell_operator(
        u=u,
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
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    shell_bending, bending_meta, bending_cache_hit = _cached_shell_operator(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=False,
        shell_operator_cache=shell_operator_cache,
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    u_np = np.asarray(u, dtype=np.float64)
    f_full = np.asarray(shell_full @ u_np, dtype=np.float64)
    f_bending = np.asarray(shell_bending @ u_np, dtype=np.float64)
    f_membrane = np.asarray(f_full - f_bending, dtype=np.float64)
    return {
        "shell_bending_drilling": f_bending,
        "shell_membrane": f_membrane,
    }, {
        "shell_internal_force_model": (
            "membrane_bending_drilling_force_consistent_reference_geometry_split"
        ),
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "shell_stiffness_nnz": int(shell_full.nnz),
        "shell_bending_drilling_stiffness_nnz": int(shell_bending.nnz),
        "shell_membrane_stiffness_nnz": int((shell_full - shell_bending).nnz),
        "shell_internal_force_cache_enabled": shell_operator_cache is not None,
        "shell_full_operator_cache_hit": bool(full_cache_hit),
        "shell_bending_operator_cache_hit": bool(bending_cache_hit),
        "shell_material_tangent_override_enabled": bool(
            full_meta.get("shell_material_tangent_override_enabled")
        ),
        "shell_material_tangent_operator_cache_disabled": bool(
            full_meta.get("shell_material_tangent_operator_cache_disabled")
        ),
        "shell_meta": full_meta,
        "shell_bending_drilling_meta": bending_meta,
    }


def assemble_shell_internal_force_components_batch(
    *,
    u_batch: np.ndarray,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    shell_operator_cache: dict[str, Any] | None = None,
    material_tangent_by_surface_index_mpa: dict[int, float] | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Batch recover additive shell resisting-force components."""
    states = np.asarray(u_batch, dtype=np.float64)
    if states.ndim != 2:
        raise ValueError("u_batch must be a 2D array shaped (batch, n_dof)")
    reference_u = states[0] if states.shape[0] else np.zeros(int(node_xyz.shape[0]) * 6)
    shell_full, full_meta, full_cache_hit = _cached_shell_operator(
        u=reference_u,
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
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    shell_bending, bending_meta, bending_cache_hit = _cached_shell_operator(
        u=reference_u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=False,
        shell_operator_cache=shell_operator_cache,
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    f_full = np.asarray(shell_full @ states.T, dtype=np.float64).T
    f_bending = np.asarray(shell_bending @ states.T, dtype=np.float64).T
    f_membrane = np.asarray(f_full - f_bending, dtype=np.float64)
    return {
        "shell_bending_drilling": f_bending,
        "shell_membrane": f_membrane,
    }, {
        "shell_internal_force_model": (
            "membrane_bending_drilling_force_consistent_reference_geometry_split"
        ),
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "shell_stiffness_nnz": int(shell_full.nnz),
        "shell_bending_drilling_stiffness_nnz": int(shell_bending.nnz),
        "shell_membrane_stiffness_nnz": int((shell_full - shell_bending).nnz),
        "shell_internal_force_cache_enabled": shell_operator_cache is not None,
        "shell_full_operator_cache_hit": bool(full_cache_hit),
        "shell_bending_operator_cache_hit": bool(bending_cache_hit),
        "shell_batch_size": int(states.shape[0]),
        "shell_material_tangent_override_enabled": bool(
            full_meta.get("shell_material_tangent_override_enabled")
        ),
        "shell_material_tangent_operator_cache_disabled": bool(
            full_meta.get("shell_material_tangent_operator_cache_disabled")
        ),
        "shell_meta": full_meta,
        "shell_bending_drilling_meta": bending_meta,
    }


def assemble_shell_internal_forces(
    *,
    u: np.ndarray,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    shell_operator_cache: dict[str, Any] | None = None,
    material_tangent_by_surface_index_mpa: dict[int, float] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Recover shell resisting forces as K_shell(reference) @ u."""
    shell_stiffness, shell_meta, cache_hit = _cached_shell_operator(
        u=u,
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
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    f_shell = np.asarray(shell_stiffness @ np.asarray(u, dtype=np.float64), dtype=np.float64)
    return f_shell, {
        "shell_internal_force_model": "membrane_bending_drilling_force_consistent_reference_geometry",
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "shell_internal_force_cache_enabled": shell_operator_cache is not None,
        "shell_internal_force_cache_hit": bool(cache_hit),
        "shell_material_tangent_override_enabled": bool(
            shell_meta.get("shell_material_tangent_override_enabled")
        ),
        "shell_material_tangent_operator_cache_disabled": bool(
            shell_meta.get("shell_material_tangent_operator_cache_disabled")
        ),
        "shell_meta": shell_meta,
    }


def assemble_shell_internal_forces_batch(
    *,
    u_batch: np.ndarray,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    shell_operator_cache: dict[str, Any] | None = None,
    material_tangent_by_surface_index_mpa: dict[int, float] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Batch recover shell resisting forces as K_shell(reference) @ U."""
    states = np.asarray(u_batch, dtype=np.float64)
    if states.ndim != 2:
        raise ValueError("u_batch must be a 2D array shaped (batch, n_dof)")
    reference_u = states[0] if states.shape[0] else np.zeros(int(node_xyz.shape[0]) * 6)
    shell_stiffness, shell_meta, cache_hit = _cached_shell_operator(
        u=reference_u,
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
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
    f_shell = np.asarray(shell_stiffness @ states.T, dtype=np.float64).T
    return f_shell, {
        "shell_internal_force_model": "membrane_bending_drilling_force_consistent_reference_geometry",
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "shell_internal_force_cache_enabled": shell_operator_cache is not None,
        "shell_internal_force_cache_hit": bool(cache_hit),
        "shell_batch_size": int(states.shape[0]),
        "shell_material_tangent_override_enabled": bool(
            shell_meta.get("shell_material_tangent_override_enabled")
        ),
        "shell_material_tangent_operator_cache_disabled": bool(
            shell_meta.get("shell_material_tangent_operator_cache_disabled")
        ),
        "shell_meta": shell_meta,
    }
