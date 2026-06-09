#!/usr/bin/env python3
"""Physical equilibrium internal-force assembly for MGT coupled residual gates."""

from __future__ import annotations

from typing import Any

import numpy as np

from run_mgt_coupled_frame_shell_sparse_equilibrium import _assemble_surface_shell_6dof
from run_mgt_frame_material_nonlinear_tangent import (
    _axial_strain,
    _material_tangent_state,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    FrameElement,
    _assemble_sparse_frame,
    _element_end_points,
    _frame_props,
    _node_dofs,
    _rigid_end_offset_transform,
)
from run_mgt_frame_material_nonlinear_tangent import _assemble_material_tangent_frame


def _stress_axial_correction_global(
    *,
    elem: FrameElement,
    node_xyz: np.ndarray,
    u: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> np.ndarray:
    props, _ = _frame_props(
        elem,
        section_props=section_props,
        material_props=material_props,
    )
    sec = section_props.get(int(elem.section_id))
    if not isinstance(sec, dict):
        return np.zeros(12, dtype=np.float64)
    area = max(float(sec.get("A_m2") or 0.0), 1.0e-12)
    strain = _axial_strain(elem, node_xyz, u)
    mat = material_props.get(int(elem.material_id), {})
    state = _material_tangent_state(mat, strain)
    n_linear = float(props.e_n_per_m2) * area * strain
    n_stress = float(state.stress_mpa) * 1.0e6 * area
    delta_n = n_stress - n_linear
    if abs(delta_n) <= 1.0e-12:
        return np.zeros(12, dtype=np.float64)
    pi, pj = _element_end_points(elem, node_xyz)
    axis = np.asarray(pj - pi, dtype=np.float64)
    axis /= max(float(np.linalg.norm(axis)), 1.0e-12)
    correction_end = np.zeros(12, dtype=np.float64)
    correction_end[0:3] = delta_n * axis
    correction_end[6:9] = -delta_n * axis
    offset_i = np.asarray(elem.offset_i_global_m, dtype=np.float64)
    offset_j = np.asarray(elem.offset_j_global_m, dtype=np.float64)
    rigid_transform = _rigid_end_offset_transform(offset_i, offset_j)
    return np.asarray(rigid_transform.T @ correction_end, dtype=np.float64)


def assemble_physical_internal_forces(
    *,
    u: np.ndarray,
    node_xyz: np.ndarray,
    frame_elements: list[FrameElement],
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
    apply_material_stress_axial_correction: bool = False,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Assemble F_int(u) from equilibrium operators, not Newton tangent operators."""
    translations = np.asarray(u, dtype=np.float64).reshape((-1, DOF_PER_NODE))[:, :3]
    deformed_xyz = node_xyz + translations
    axial_forces = {
        int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_equilibrium_stiffness, _frame_f, frame_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=deformed_xyz,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    shell_stiffness, _shell_f, shell_meta, _surface_conns = _assemble_surface_shell_6dof(
        node_xyz=deformed_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    equilibrium_stiffness = frame_equilibrium_stiffness + shell_stiffness + spring_stiffness
    f_int = np.asarray(equilibrium_stiffness @ u, dtype=np.float64)
    stress_corrected_element_count = 0
    if apply_material_stress_axial_correction:
        for elem in frame_elements:
            correction = _stress_axial_correction_global(
                elem=elem,
                node_xyz=deformed_xyz,
                u=u,
                section_props=section_props,
                material_props=material_props,
            )
            if float(np.max(np.abs(correction))) <= 1.0e-12:
                continue
            stress_corrected_element_count += 1
            dofs = _node_dofs(elem.node_i) + _node_dofs(elem.node_j)
            for a, gi in enumerate(dofs):
                f_int[gi] += float(correction[a])
    return f_int, {
        "physical_internal_force_model": (
            "elastic_frame_geometric_plus_linear_shell_plus_springs"
            + (
                "_with_stress_based_axial_correction"
                if apply_material_stress_axial_correction
                else ""
            )
        ),
        "frame_equilibrium_stiffness_nnz": int(frame_equilibrium_stiffness.nnz),
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "spring_stiffness_nnz": int(spring_stiffness.nnz),
        "equilibrium_stiffness_nnz": int(equilibrium_stiffness.nnz),
        "frame_equilibrium_meta": frame_meta,
        "shell_meta": shell_meta,
        "stress_corrected_element_count": int(stress_corrected_element_count),
    }


def assemble_newton_tangent_stiffness(
    *,
    u: np.ndarray,
    node_xyz: np.ndarray,
    frame_elements: list[FrameElement],
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
    service_tangent_by_element: dict[int, float],
    service_material_meta: dict[str, Any],
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    """Assemble the regularized Newton tangent used only for correction directions."""
    translations = np.asarray(u, dtype=np.float64).reshape((-1, DOF_PER_NODE))[:, :3]
    deformed_xyz = node_xyz + translations
    axial_forces = {
        int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_material_stiffness, frame_f, frame_material_meta = _assemble_material_tangent_frame(
        elements=frame_elements,
        node_xyz=deformed_xyz,
        section_props=section_props,
        material_props=material_props,
        tangent_by_element_mpa=service_tangent_by_element,
    )
    frame_elastic_stiffness, _elastic_f, _elastic_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=deformed_xyz,
        section_props=section_props,
        material_props=material_props,
    )
    frame_geometric_total, _geo_f, frame_geometric_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=deformed_xyz,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    frame_stiffness = frame_material_stiffness + (frame_geometric_total - frame_elastic_stiffness)
    shell_stiffness, shell_f, shell_meta, _surface_conns = _assemble_surface_shell_6dof(
        node_xyz=deformed_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    stiffness = frame_stiffness + shell_stiffness + spring_stiffness
    assembled_f_ext = (frame_f * float(frame_gravity_load_scale) + shell_f) * float(load_scale)
    return stiffness, assembled_f_ext, {
        "frame_material_stiffness_nnz": int(frame_material_stiffness.nnz),
        "frame_geometric_delta_stiffness_nnz": int((frame_geometric_total - frame_elastic_stiffness).nnz),
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "spring_stiffness_nnz": int(spring_stiffness.nnz),
        "coupled_stiffness_nnz": int(stiffness.nnz),
        "frame_material_meta": frame_material_meta,
        "frame_geometric_meta": frame_geometric_meta,
        "service_material_meta": service_material_meta,
        "shell_meta": shell_meta,
    }


def assemble_physical_residual(
    *,
    u: np.ndarray,
    f_ext: np.ndarray,
    free: np.ndarray,
    f_int: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    residual = np.asarray(f_int[free] - f_ext[free], dtype=np.float64)
    rhs = np.asarray(f_ext[free], dtype=np.float64)
    return residual, rhs
