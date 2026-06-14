#!/usr/bin/env python3
"""6-DOF corotational force-based frame internal-force recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from run_mgt_full_frame_6dof_sparse_equilibrium import (
    FrameElement,
    FrameProps,
    _element_end_points,
    _frame_props,
    _local_frame_geometric_stiffness,
    _local_frame_stiffness,
    _node_dofs,
    _rigid_end_offset_transform,
    _rotation_matrix,
)


@dataclass(frozen=True)
class PrepackedFrameForceBasedAssembly:
    """Reference-geometry frame force operator reused across residual replays."""

    dofs: np.ndarray
    element_stiffness: np.ndarray
    n_dof: int
    meta: dict[str, Any]

    def assemble(self, u: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        u_np = np.asarray(u, dtype=np.float64)
        gathered = u_np[self.dofs]
        element_forces = np.einsum(
            "eij,ej->ei",
            self.element_stiffness,
            gathered,
            optimize=True,
        )
        f_int = np.zeros(int(self.n_dof), dtype=np.float64)
        np.add.at(f_int, self.dofs.ravel(), element_forces.ravel())
        return f_int, {
            **self.meta,
            "frame_force_based_fastpath": True,
            "frame_force_based_prepacked_element_count": int(self.dofs.shape[0]),
        }


def _frame_12_transform(rotation: np.ndarray) -> np.ndarray:
    transform = np.zeros((12, 12), dtype=np.float64)
    block = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = block
    return transform


def _element_end_points_reference(
    *,
    elem: FrameElement,
    node_xyz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Reference chord for corotational transforms; deformation is carried only by ``u``."""
    return _element_end_points(elem, node_xyz)


def _element_force_based_end_forces(
    *,
    elem: FrameElement,
    node_xyz: np.ndarray,
    u: np.ndarray,
    props: FrameProps,
    axial_force_n: float,
    include_geometric: bool,
) -> np.ndarray:
    """Recover corotational 12-DOF end forces in the nodal (offset-mapped) frame."""
    offset_i = np.asarray(elem.offset_i_global_m, dtype=np.float64)
    offset_j = np.asarray(elem.offset_j_global_m, dtype=np.float64)
    rigid_transform = _rigid_end_offset_transform(offset_i, offset_j)
    dofs = _node_dofs(elem.node_i) + _node_dofs(elem.node_j)
    displacement_node = np.asarray(u[list(dofs)], dtype=np.float64)
    displacement_end = rigid_transform @ displacement_node

    pi, pj = _element_end_points_reference(elem=elem, node_xyz=node_xyz)
    reference_length = max(float(elem.length_m), 1.0e-6)

    rotation = _rotation_matrix(pi, pj, roll_deg=elem.local_axis_angle_deg)
    transform = _frame_12_transform(rotation)
    displacement_local = transform @ displacement_end

    local_stiffness = _local_frame_stiffness(props, reference_length)
    if include_geometric:
        local_stiffness = local_stiffness - _local_frame_geometric_stiffness(
            axial_force_n=float(axial_force_n),
            length_m=reference_length,
        )
    force_local = local_stiffness @ displacement_local
    force_end = transform.T @ force_local
    return np.asarray(rigid_transform.T @ force_end, dtype=np.float64)


def prepack_frame_force_based_assembly(
    *,
    node_xyz: np.ndarray,
    frame_elements: list[FrameElement],
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    element_axial_forces: dict[int, float] | None = None,
    include_geometric: bool = True,
) -> PrepackedFrameForceBasedAssembly:
    """Precompute per-element force matrices for repeated residual-only replay."""
    n_dof = int(node_xyz.shape[0]) * 6
    element_axial_forces = element_axial_forces or {}
    dof_rows = np.zeros((int(len(frame_elements)), 12), dtype=np.int64)
    element_stiffness = np.zeros((int(len(frame_elements)), 12, 12), dtype=np.float64)
    real_count = 0
    geometric_element_count = 0
    min_chord_length_m = float("inf")
    max_chord_length_ratio = 0.0

    for elem_index, elem in enumerate(frame_elements):
        props, used_real = _frame_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        real_count += int(bool(used_real))
        pi_ref, pj_ref = _element_end_points(elem, node_xyz)
        reference_chord_length = max(float(np.linalg.norm(pj_ref - pi_ref)), 1.0e-12)
        min_chord_length_m = min(min_chord_length_m, reference_chord_length)
        max_chord_length_ratio = max(max_chord_length_ratio, 1.0)

        axial_force_n = float(element_axial_forces.get(elem.elem_id, 0.0))
        if include_geometric and axial_force_n > 0.0:
            geometric_element_count += 1

        offset_i = np.asarray(elem.offset_i_global_m, dtype=np.float64)
        offset_j = np.asarray(elem.offset_j_global_m, dtype=np.float64)
        rigid_transform = _rigid_end_offset_transform(offset_i, offset_j)
        pi, pj = _element_end_points_reference(elem=elem, node_xyz=node_xyz)
        reference_length = max(float(elem.length_m), 1.0e-6)
        rotation = _rotation_matrix(pi, pj, roll_deg=elem.local_axis_angle_deg)
        transform = _frame_12_transform(rotation)
        local_stiffness = _local_frame_stiffness(props, reference_length)
        if include_geometric:
            local_stiffness = local_stiffness - _local_frame_geometric_stiffness(
                axial_force_n=axial_force_n,
                length_m=reference_length,
            )
        element_stiffness[elem_index, :, :] = (
            rigid_transform.T @ transform.T @ local_stiffness @ transform @ rigid_transform
        )
        dof_rows[elem_index, :] = np.asarray(
            _node_dofs(elem.node_i) + _node_dofs(elem.node_j),
            dtype=np.int64,
        )

    return PrepackedFrameForceBasedAssembly(
        dofs=dof_rows,
        element_stiffness=element_stiffness,
        n_dof=n_dof,
        meta={
            "frame_internal_force_model": "corotational_force_based_6dof",
            "real_section_material_element_count": int(real_count),
            "geometric_element_count": int(geometric_element_count),
            "min_chord_length_m": float(min_chord_length_m if frame_elements else 0.0),
            "max_chord_length_ratio": float(max_chord_length_ratio),
            "element_count": int(len(frame_elements)),
            "frame_force_based_fastpath_available": True,
        },
    )


def assemble_frame_force_based_f_int(
    *,
    u: np.ndarray,
    node_xyz: np.ndarray,
    frame_elements: list[FrameElement],
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    element_axial_forces: dict[int, float] | None = None,
    include_geometric: bool = True,
    prepacked: PrepackedFrameForceBasedAssembly | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Assemble global F_int from element-wise corotational force recovery."""
    if prepacked is not None:
        return prepacked.assemble(u)

    n_dof = int(node_xyz.shape[0]) * 6
    f_int = np.zeros(n_dof, dtype=np.float64)
    real_count = 0
    geometric_element_count = 0
    min_chord_length_m = float("inf")
    max_chord_length_ratio = 0.0
    element_axial_forces = element_axial_forces or {}

    for elem in frame_elements:
        props, used_real = _frame_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        real_count += int(bool(used_real))
        pi_ref, pj_ref = _element_end_points(elem, node_xyz)
        reference_chord_length = max(float(np.linalg.norm(pj_ref - pi_ref)), 1.0e-12)
        min_chord_length_m = min(min_chord_length_m, reference_chord_length)
        max_chord_length_ratio = max(max_chord_length_ratio, 1.0)

        axial_force_n = float(element_axial_forces.get(elem.elem_id, 0.0))
        if include_geometric and axial_force_n > 0.0:
            geometric_element_count += 1

        force_node = _element_force_based_end_forces(
            elem=elem,
            node_xyz=node_xyz,
            u=u,
            props=props,
            axial_force_n=axial_force_n,
            include_geometric=include_geometric,
        )
        dofs = _node_dofs(elem.node_i) + _node_dofs(elem.node_j)
        for index, global_dof in enumerate(dofs):
            f_int[global_dof] += float(force_node[index])

    return f_int, {
        "frame_internal_force_model": "corotational_force_based_6dof",
        "real_section_material_element_count": int(real_count),
        "geometric_element_count": int(geometric_element_count),
        "min_chord_length_m": float(min_chord_length_m if frame_elements else 0.0),
        "max_chord_length_ratio": float(max_chord_length_ratio),
        "element_count": int(len(frame_elements)),
    }
