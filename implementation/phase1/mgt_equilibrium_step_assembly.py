#!/usr/bin/env python3
"""Per load-step equilibrium residual assembler with frozen external load."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from mgt_equilibrium_geometry_contract import EQUILIBRIUM_GEOMETRY_CONTRACT
from mgt_physical_residual_assembly import (
    assemble_equilibrium_operator_stiffness,
    assemble_physical_internal_forces,
    assemble_physical_residual,
)
from run_mgt_direct_residual_newton_probe import _active_free
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE, FrameElement


def _surface_pressure_load_path_filter(
    *,
    frame_elements: list[FrameElement],
    elem_type_code: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    restrained: set[int],
    policy: str,
) -> tuple[set[int] | None, dict[str, Any]]:
    normalized = str(policy or "all_components").strip().lower()
    if normalized in {"all", "all_components", "unfiltered"}:
        return None, {
            "shell_pressure_load_path_policy": "all_components",
            "pressure_load_filter_enabled": False,
        }
    if normalized not in {"attached_components_only", "attached_only"}:
        raise ValueError(
            "shell_pressure_load_path_policy must be all_components or attached_components_only"
        )
    type_code = np.asarray(elem_type_code, dtype=np.int32)
    ptr = np.asarray(conn_ptr, dtype=np.int64)
    idx = np.asarray(conn_idx, dtype=np.int64)
    surface_indices = np.where(type_code == 2)[0]
    conn_by_elem: dict[int, list[int]] = {}
    incident_by_node: dict[int, list[int]] = {}
    for elem_index in surface_indices.tolist():
        start = int(ptr[int(elem_index)])
        end = int(ptr[int(elem_index) + 1])
        if start < 0 or end < start or end > int(idx.size):
            continue
        conn = [int(node) for node in idx[start:end].tolist()]
        if len(conn) not in {3, 4}:
            continue
        conn_by_elem[int(elem_index)] = conn
        for node in conn:
            incident_by_node.setdefault(int(node), []).append(int(elem_index))
    frame_nodes = {int(element.node_i) for element in frame_elements}
    frame_nodes.update(int(element.node_j) for element in frame_elements)
    restrained_translation_nodes = {
        int(dof) // DOF_PER_NODE
        for dof in restrained
        if int(dof) % DOF_PER_NODE in {0, 1, 2}
    }
    eligible: set[int] = set()
    visited: set[int] = set()
    component_count = 0
    attached_component_count = 0
    free_pressure_component_count = 0
    free_pressure_element_count = 0
    for seed_elem in sorted(conn_by_elem):
        if seed_elem in visited:
            continue
        component_count += 1
        pending = [int(seed_elem)]
        component_elems: set[int] = set()
        component_nodes: set[int] = set()
        while pending:
            elem_index = int(pending.pop())
            if elem_index in visited:
                continue
            conn = conn_by_elem.get(elem_index)
            if not conn:
                continue
            visited.add(elem_index)
            component_elems.add(elem_index)
            for node in conn:
                component_nodes.add(int(node))
                for neighbor in incident_by_node.get(int(node), []):
                    if int(neighbor) not in visited:
                        pending.append(int(neighbor))
        attached = bool(
            component_nodes.intersection(frame_nodes)
            or component_nodes.intersection(restrained_translation_nodes)
        )
        if attached:
            attached_component_count += 1
            eligible.update(component_elems)
        else:
            free_pressure_component_count += 1
            free_pressure_element_count += len(component_elems)
    return eligible, {
        "shell_pressure_load_path_policy": "attached_components_only",
        "pressure_load_filter_enabled": True,
        "surface_component_count": int(component_count),
        "attached_surface_component_count": int(attached_component_count),
        "free_pressure_surface_component_count": int(free_pressure_component_count),
        "pressure_load_allowed_surface_element_count": int(len(eligible)),
        "pressure_load_suppressed_surface_element_count": int(free_pressure_element_count),
        "claim_boundary": (
            "Diagnostic load-path policy: shell pressure is applied only to surface components "
            "with a frame-connected node or an authored translational restraint."
        ),
    }


def build_equilibrium_step_assembler(
    *,
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
    restrained: set[int],
    shell_pressure_load_path_policy: str = "all_components",
) -> tuple[
    Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    dict[str, Any],
]:
    """Build R(u)=F_int(u)-F_ext with F_ext frozen at u=0 for the load step."""
    reference_holder: dict[str, np.ndarray] = {}
    shell_operator_cache: dict[str, Any] = {}
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    pressure_allowed_surface_elements, pressure_load_path_meta = _surface_pressure_load_path_filter(
        frame_elements=frame_elements,
        elem_type_code=elem_type_code,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        restrained=restrained,
        policy=shell_pressure_load_path_policy,
    )

    def assemble_residual(
        u: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
        include_component_forces: bool = False,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        if residual_only:
            if external_load_override is not None:
                f_ext = np.asarray(external_load_override, dtype=np.float64)
            elif "reference_f_ext" in reference_holder:
                f_ext = reference_holder["reference_f_ext"]
            else:
                residual_only = False
        if residual_only:
            if free_override is not None:
                free = np.asarray(free_override, dtype=np.int64)
            elif "reference_free" in reference_holder:
                free = np.asarray(reference_holder["reference_free"], dtype=np.int64)
            else:
                residual_only = False
        if residual_only:
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
                include_component_forces=include_component_forces,
                shell_operator_cache=shell_operator_cache,
            )
            residual, rhs = assemble_physical_residual(
                u=u,
                f_ext=f_ext,
                free=free,
                f_int=f_int,
            )
            return None, f_ext, free, residual, rhs, {
                **physical_meta,
                "residual_only_assembly": True,
                "residual_only_free_override": bool(free_override is not None),
                "free_dof_count": int(free.size),
                "frozen_external_load": bool("reference_f_ext" in reference_holder),
                "shell_pressure_load_path_meta": pressure_load_path_meta,
                "shell_operator_cache_size": int(len(shell_operator_cache)),
            }
        stiffness, assembled_f_ext, tangent_meta = assemble_equilibrium_operator_stiffness(
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
            restrained=restrained,
            shell_pressure_load_allowed_surface_elements=pressure_allowed_surface_elements,
        )
        _active, free = _active_free(stiffness, restrained)
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
            include_component_forces=include_component_forces,
            shell_operator_cache=shell_operator_cache,
        )
        if external_load_override is not None:
            f_ext = np.asarray(external_load_override, dtype=np.float64)
        elif "reference_f_ext" in reference_holder:
            f_ext = reference_holder["reference_f_ext"]
        else:
            f_ext = assembled_f_ext
        residual, rhs = assemble_physical_residual(
            u=u,
            f_ext=f_ext,
            free=free,
            f_int=f_int,
        )
        return stiffness, f_ext, free, residual, rhs, {
            **tangent_meta,
            **physical_meta,
            "shell_pressure_load_path_meta": pressure_load_path_meta,
            "active_dof_count": int(_active.size),
            "free_dof_count": int(free.size),
            "frozen_external_load": bool("reference_f_ext" in reference_holder),
            "shell_operator_cache_size": int(len(shell_operator_cache)),
        }

    _reference_stiffness, reference_f_ext, _reference_free, _reference_residual, _reference_rhs, _ = (
        assemble_residual(np.zeros(n_dof, dtype=np.float64))
    )
    reference_holder["reference_f_ext"] = reference_f_ext
    reference_holder["reference_free"] = _reference_free

    def assemble_with_frozen_external_load(
        u: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
        include_component_forces: bool = False,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        override = reference_f_ext if external_load_override is None else external_load_override
        return assemble_residual(
            u,
            external_load_override=override,
            include_component_forces=include_component_forces,
            residual_only=residual_only,
            free_override=free_override,
        )
    assemble_with_frozen_external_load.supports_residual_only = True  # type: ignore[attr-defined]

    setup_meta = {
        "equilibrium_geometry_contract": EQUILIBRIUM_GEOMETRY_CONTRACT,
        "frozen_load_scale": float(load_scale),
        "reference_f_ext_inf_n": float(np.max(np.abs(reference_f_ext))) if reference_f_ext.size else 0.0,
        "free_dof_count": int(_reference_free.size),
        "shell_pressure_load_path_meta": pressure_load_path_meta,
    }
    return assemble_with_frozen_external_load, setup_meta
