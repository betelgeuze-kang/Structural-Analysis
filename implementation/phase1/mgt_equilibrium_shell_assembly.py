#!/usr/bin/env python3
"""Equilibrium shell operator assembly with membrane+bending+drilling stiffness."""

from __future__ import annotations

from typing import Any

import numpy as np

from run_mgt_coupled_frame_shell_sparse_equilibrium import _assemble_surface_shell_6dof


def assemble_equilibrium_surface_shell_6dof(
    *,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    include_membrane: bool = True,
    pressure_load_allowed_surface_elements: set[int] | None = None,
    material_tangent_by_surface_index_mpa: dict[int, float] | None = None,
) -> tuple[Any, np.ndarray, dict[str, Any], list[list[int]]]:
    """Assemble shell stiffness, optionally with in-plane membrane terms."""
    return _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=bool(include_membrane),
        pressure_load_allowed_surface_elements=pressure_load_allowed_surface_elements,
        material_tangent_by_surface_index_mpa=material_tangent_by_surface_index_mpa,
    )
