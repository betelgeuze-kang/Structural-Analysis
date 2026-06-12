#!/usr/bin/env python3
"""Linear force-consistent shell internal-force recovery at reference geometry."""

from __future__ import annotations

from typing import Any

import numpy as np

from mgt_equilibrium_geometry_contract import EQUILIBRIUM_GEOMETRY_CONTRACT, assembly_node_xyz
from mgt_equilibrium_shell_assembly import assemble_equilibrium_surface_shell_6dof


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
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Recover additive shell resisting-force components for diagnostics."""
    assembly_xyz = assembly_node_xyz(node_xyz=node_xyz, u=u)
    shell_full, _shell_f, full_meta, _surface_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=assembly_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
    )
    shell_bending, _bend_f, bending_meta, _bend_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=assembly_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=False,
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
) -> tuple[np.ndarray, dict[str, Any]]:
    """Recover shell resisting forces as K_shell(reference) @ u."""
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
        include_membrane=True,
    )
    f_shell = np.asarray(shell_stiffness @ np.asarray(u, dtype=np.float64), dtype=np.float64)
    return f_shell, {
        "shell_internal_force_model": "membrane_bending_drilling_force_consistent_reference_geometry",
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "shell_meta": shell_meta,
    }
