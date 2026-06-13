#!/usr/bin/env python3
"""Physical equilibrium internal-force assembly for MGT coupled residual gates."""

from __future__ import annotations

from typing import Any

import numpy as np

from mgt_equilibrium_shell_assembly import assemble_equilibrium_surface_shell_6dof
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
from mgt_equilibrium_geometry_contract import (
    EQUILIBRIUM_GEOMETRY_CONTRACT,
    assembly_node_xyz,
)
from mgt_coupled_stiffness_unit_audit import audit_coupled_stiffness_diagonals
from mgt_frame_force_based_assembly import assemble_frame_force_based_f_int
from mgt_shell_force_based_assembly import (
    assemble_shell_internal_force_components,
    assemble_shell_internal_forces,
)


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


def assemble_physical_internal_force_components(
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
    use_force_based_frame: bool = True,
    split_shell_components: bool = False,
    shell_operator_cache: dict[str, Any] | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Assemble component-wise F_int(u), separated for residual diagnostics."""
    assembly_xyz = assembly_node_xyz(node_xyz=node_xyz, u=u)
    axial_forces = {
        int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    if use_force_based_frame:
        f_frame, frame_meta = assemble_frame_force_based_f_int(
            u=u,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=material_props,
            element_axial_forces=axial_forces,
            include_geometric=True,
        )
        frame_equilibrium_stiffness = None
    else:
        frame_equilibrium_stiffness, _frame_f, frame_meta = _assemble_sparse_frame(
            elements=frame_elements,
            node_xyz=assembly_xyz,
            section_props=section_props,
            material_props=material_props,
            element_axial_forces=axial_forces,
            include_geometric=True,
        )
        f_frame = np.asarray(frame_equilibrium_stiffness @ u, dtype=np.float64)
    if split_shell_components:
        shell_components, shell_meta = assemble_shell_internal_force_components(
            u=u,
            node_xyz=node_xyz,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            shell_operator_cache=shell_operator_cache,
        )
        f_shell = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
        for values in shell_components.values():
            f_shell = f_shell + np.asarray(values, dtype=np.float64)
    else:
        f_shell, shell_meta = assemble_shell_internal_forces(
            u=u,
            node_xyz=node_xyz,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            shell_operator_cache=shell_operator_cache,
        )
        shell_components = {"shell": np.asarray(f_shell, dtype=np.float64)}
    f_spring = np.asarray(spring_stiffness @ u, dtype=np.float64)
    shell_stiffness_nnz = int(shell_meta.get("shell_stiffness_nnz") or 0)
    f_material_stress_correction = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
    stress_corrected_element_count = 0
    if apply_material_stress_axial_correction:
        for elem in frame_elements:
            correction = _stress_axial_correction_global(
                elem=elem,
                node_xyz=assembly_xyz,
                u=u,
                section_props=section_props,
                material_props=material_props,
            )
            if float(np.max(np.abs(correction))) <= 1.0e-12:
                continue
            stress_corrected_element_count += 1
            dofs = _node_dofs(elem.node_i) + _node_dofs(elem.node_j)
            for a, gi in enumerate(dofs):
                f_material_stress_correction[gi] += float(correction[a])
    frame_model = (
        frame_meta.get("frame_internal_force_model", "quasi_tangent_k_eq_at_u")
        if use_force_based_frame
        else "elastic_frame_geometric_plus_linear_shell_plus_springs"
    )
    components = {
        "frame": np.asarray(f_frame, dtype=np.float64),
        "spring": np.asarray(f_spring, dtype=np.float64),
        "material_stress_correction": np.asarray(f_material_stress_correction, dtype=np.float64),
    }
    components.update({name: np.asarray(values, dtype=np.float64) for name, values in shell_components.items()})
    return components, {
        "physical_internal_force_model": (
            frame_model + "_plus_force_consistent_shell_plus_springs"
            + (
                "_with_stress_based_axial_correction"
                if apply_material_stress_axial_correction
                else ""
            )
        ),
        "use_force_based_frame": bool(use_force_based_frame),
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "frame_equilibrium_stiffness_nnz": (
            int(frame_equilibrium_stiffness.nnz) if frame_equilibrium_stiffness is not None else 0
        ),
        "shell_stiffness_nnz": shell_stiffness_nnz,
        "spring_stiffness_nnz": int(spring_stiffness.nnz),
        "shell_internal_force_model": shell_meta.get("shell_internal_force_model"),
        "split_shell_components": bool(split_shell_components),
        "frame_equilibrium_meta": frame_meta,
        "shell_meta": shell_meta,
        "stress_corrected_element_count": int(stress_corrected_element_count),
    }


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
    use_force_based_frame: bool = True,
    include_component_forces: bool = False,
    split_shell_components: bool | None = None,
    shell_operator_cache: dict[str, Any] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Assemble F_int(u) from equilibrium operators, not Newton tangent operators."""
    split_shell = bool(include_component_forces) if split_shell_components is None else bool(split_shell_components)
    components, meta = assemble_physical_internal_force_components(
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
        apply_material_stress_axial_correction=apply_material_stress_axial_correction,
        use_force_based_frame=use_force_based_frame,
        split_shell_components=split_shell,
        shell_operator_cache=shell_operator_cache,
    )
    f_int = np.zeros_like(np.asarray(u, dtype=np.float64))
    component_inf = {}
    for name, values in components.items():
        arr = np.asarray(values, dtype=np.float64)
        f_int = f_int + arr
        component_inf[f"{name}_inf_n"] = float(np.max(np.abs(arr))) if arr.size else 0.0
    meta = {**meta, "component_internal_force_inf_n": component_inf}
    if include_component_forces:
        meta["component_forces"] = components
    return np.asarray(f_int, dtype=np.float64), meta


def assemble_equilibrium_operator_stiffness(
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
    restrained: set[int] | None = None,
    shell_pressure_load_allowed_surface_elements: set[int] | None = None,
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    """Assemble K_eq consistent with force-based F_int at the reference geometry map."""
    assembly_xyz = assembly_node_xyz(node_xyz=node_xyz, u=u)
    axial_forces = {
        int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_stiffness, frame_f, frame_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=assembly_xyz,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    shell_stiffness, shell_f, shell_meta, _surface_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=assembly_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        pressure_load_allowed_surface_elements=shell_pressure_load_allowed_surface_elements,
    )
    stiffness = frame_stiffness + shell_stiffness + spring_stiffness
    assembled_f_ext = (frame_f * float(frame_gravity_load_scale) + shell_f) * float(load_scale)
    meta: dict[str, Any] = {
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "newton_tangent_model": "equilibrium_operator_consistent_with_force_based_f_int",
        "frame_equilibrium_stiffness_nnz": int(frame_stiffness.nnz),
        "shell_stiffness_nnz": int(shell_stiffness.nnz),
        "spring_stiffness_nnz": int(spring_stiffness.nnz),
        "coupled_stiffness_nnz": int(stiffness.nnz),
        "frame_equilibrium_meta": frame_meta,
        "shell_meta": shell_meta,
    }
    if restrained is not None:
        from run_mgt_direct_residual_newton_probe import _active_free

        _active, free = _active_free(stiffness, restrained)
        meta["stiffness_unit_audit"] = audit_coupled_stiffness_diagonals(
            components={
                "frame": frame_stiffness,
                "shell": shell_stiffness,
                "spring": spring_stiffness,
            },
            free_global_dofs=np.asarray(free, dtype=np.int64),
        )
    return stiffness, assembled_f_ext, meta


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
    shell_pressure_load_allowed_surface_elements: set[int] | None = None,
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    """Assemble the regularized Newton tangent used only for correction directions."""
    assembly_xyz = assembly_node_xyz(node_xyz=node_xyz, u=u)
    axial_forces = {
        int(elem_id): float(force) * float(frame_gravity_load_scale) * float(load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    frame_material_stiffness, frame_f, frame_material_meta = _assemble_material_tangent_frame(
        elements=frame_elements,
        node_xyz=assembly_xyz,
        section_props=section_props,
        material_props=material_props,
        tangent_by_element_mpa=service_tangent_by_element,
    )
    frame_elastic_stiffness, _elastic_f, _elastic_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=assembly_xyz,
        section_props=section_props,
        material_props=material_props,
    )
    frame_geometric_total, _geo_f, frame_geometric_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=assembly_xyz,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    frame_stiffness = frame_material_stiffness + (frame_geometric_total - frame_elastic_stiffness)
    shell_stiffness, shell_f, shell_meta, _surface_conns = assemble_equilibrium_surface_shell_6dof(
        node_xyz=assembly_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        pressure_load_allowed_surface_elements=shell_pressure_load_allowed_surface_elements,
    )
    stiffness = frame_stiffness + shell_stiffness + spring_stiffness
    assembled_f_ext = (frame_f * float(frame_gravity_load_scale) + shell_f) * float(load_scale)
    return stiffness, assembled_f_ext, {
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
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
