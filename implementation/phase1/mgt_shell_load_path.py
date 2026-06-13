#!/usr/bin/env python3
"""Shell surface load-path classification helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE, FrameElement


def surface_pressure_load_path_components(
    *,
    frame_elements: list[FrameElement],
    elem_type_code: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    restrained: set[int],
) -> list[dict[str, Any]]:
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

    components: list[dict[str, Any]] = []
    visited: set[int] = set()
    for seed_elem in sorted(conn_by_elem):
        if seed_elem in visited:
            continue
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

        frame_connected_nodes = sorted(int(node) for node in component_nodes if node in frame_nodes)
        restrained_translation_dofs = [
            int(node) * DOF_PER_NODE + comp
            for node in sorted(component_nodes)
            for comp in range(3)
            if int(node) in restrained_translation_nodes
        ]
        attached = bool(frame_connected_nodes or restrained_translation_dofs)
        components.append(
            {
                "surface_element_indices": sorted(int(elem) for elem in component_elems),
                "surface_node_indices": sorted(int(node) for node in component_nodes),
                "attached": bool(attached),
                "frame_connected_node_count": int(len(frame_connected_nodes)),
                "restrained_translation_dof_count": int(len(restrained_translation_dofs)),
            }
        )
    return components


def surface_pressure_load_path_filter(
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
    components = surface_pressure_load_path_components(
        frame_elements=frame_elements,
        elem_type_code=elem_type_code,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        restrained=restrained,
    )
    eligible: set[int] = set()
    attached_component_count = 0
    free_pressure_component_count = 0
    free_pressure_element_count = 0
    for component in components:
        component_elems = {int(elem) for elem in component["surface_element_indices"]}
        if bool(component["attached"]):
            attached_component_count += 1
            eligible.update(component_elems)
        else:
            free_pressure_component_count += 1
            free_pressure_element_count += len(component_elems)
    return eligible, {
        "shell_pressure_load_path_policy": "attached_components_only",
        "pressure_load_filter_enabled": True,
        "surface_component_count": int(len(components)),
        "attached_surface_component_count": int(attached_component_count),
        "free_pressure_surface_component_count": int(free_pressure_component_count),
        "pressure_load_allowed_surface_element_count": int(len(eligible)),
        "pressure_load_suppressed_surface_element_count": int(free_pressure_element_count),
        "claim_boundary": (
            "Diagnostic load-path policy: shell pressure is applied only to surface components "
            "with a frame-connected node or an authored translational restraint."
        ),
    }
