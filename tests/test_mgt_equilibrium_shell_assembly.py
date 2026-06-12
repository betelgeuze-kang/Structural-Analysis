"""Tests for equilibrium shell assembly with membrane stabilization."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_coupled_frame_shell_sparse_equilibrium import _assemble_surface_shell_6dof  # noqa: E402
from run_mgt_surface_membrane_tangent import _triangle_membrane_stiffness  # noqa: E402
from run_mgt_surface_shell_bending_tangent import _triangle_shell_bending_stiffness  # noqa: E402


def test_equilibrium_shell_includes_membrane_stiffness_on_triangle() -> None:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    e = 210.0e9
    nu = 0.3
    t = 0.2
    bend, _ = _triangle_shell_bending_stiffness(
        points=points,
        e_n_per_m2=e,
        poisson=nu,
        thickness_m=t,
    )
    mem, _ = _triangle_membrane_stiffness(
        points=points,
        e_n_per_m2=e,
        poisson=nu,
        thickness_m=t,
    )
    assert bend is not None and mem is not None
    node_xyz = points
    elem_type_code = np.asarray([2], dtype=np.int32)
    elem_section_id = np.asarray([1], dtype=np.int32)
    elem_material_id = np.asarray([1], dtype=np.int32)
    conn_ptr = np.asarray([0, 3], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 2], dtype=np.int64)
    material_props = {1: {"E_kN_per_m2": e / 1000.0, "poisson": nu}}
    plate_thickness_props = {1: {"effective_thickness_m": t}}
    k_bend, _, meta_bend, _ = _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=False,
    )
    k_full, _, meta_full, _ = _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
    )
    assert meta_bend["shell_tangent_model"] == "mindlin_cst_bending_drilling_only"
    assert meta_full["shell_tangent_model"] == "mindlin_cst_bending_drilling_plus_cst_membrane"
    u = np.zeros(18, dtype=np.float64)
    u[0] = 0.01
    f_bend = np.asarray(k_bend @ u, dtype=np.float64)
    f_full = np.asarray(k_full @ u, dtype=np.float64)
    assert abs(float(f_full[0])) > abs(float(f_bend[0]))
    assert not np.allclose(np.asarray(k_bend.todense()), np.asarray(k_full.todense()))
