#!/usr/bin/env python3
"""Conservative finite-chord axial geometry for the MGT 6-DOF frame path.

The existing frame force-recovery path evaluates one reference-geometry elastic
matrix.  This module replaces only that matrix's linear axial contribution with
the gradient of a finite-chord extension energy.  Bending and torsion remain on
the reference-geometry small-rotation formulation, so this is not a complete
large-rotation corotational beam.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    FrameElement,
    _element_end_points,
    _frame_props,
    _node_dofs,
    _rigid_end_offset_transform,
)


STATE_UPDATED_FRAME_AXIAL_GEOMETRY_PROFILE = (
    "finite_chord_conservative_axial_replacement.v1"
)
STATE_UPDATED_FRAME_AXIAL_PROPERTY_COVERAGE_SCHEMA_VERSION = (
    "mgt-state-updated-frame-axial-property-coverage.v1"
)


def audit_state_updated_frame_axial_property_coverage(
    *,
    frame_elements: list[FrameElement],
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    unresolved_element_head_limit: int = 32,
) -> dict[str, Any]:
    """Audit exact per-element source-property binding without fallbacks."""

    if unresolved_element_head_limit < 0:
        raise ValueError("unresolved_element_head_limit must be non-negative")
    missing_section_ids: Counter[int] = Counter()
    missing_material_ids: Counter[int] = Counter()
    unresolved_rows: list[dict[str, Any]] = []
    section_resolved_count = 0
    material_resolved_count = 0
    resolved_count = 0
    for element in frame_elements:
        section_id = int(element.section_id)
        material_id = int(element.material_id)
        section_resolved = section_props.get(section_id) is not None
        material_resolved = material_props.get(material_id) is not None
        section_resolved_count += int(section_resolved)
        material_resolved_count += int(material_resolved)
        resolved_count += int(section_resolved and material_resolved)
        if not section_resolved:
            missing_section_ids[section_id] += 1
        if not material_resolved:
            missing_material_ids[material_id] += 1
        if not (section_resolved and material_resolved):
            unresolved_rows.append(
                {
                    "element_id": int(element.elem_id),
                    "section_id": section_id,
                    "material_id": material_id,
                    "missing_section_property": not section_resolved,
                    "missing_material_property": not material_resolved,
                }
            )
    element_count = int(len(frame_elements))
    unresolved_count = int(element_count - resolved_count)
    exact = unresolved_count == 0
    return {
        "schema_version": (
            STATE_UPDATED_FRAME_AXIAL_PROPERTY_COVERAGE_SCHEMA_VERSION
        ),
        "frame_element_count": element_count,
        "source_section_property_count": int(len(section_props)),
        "source_material_property_count": int(len(material_props)),
        "section_property_resolved_element_count": int(
            section_resolved_count
        ),
        "material_property_resolved_element_count": int(
            material_resolved_count
        ),
        "resolved_source_property_element_count": int(resolved_count),
        "unresolved_source_property_element_count": unresolved_count,
        "source_property_coverage_ratio": (
            float(resolved_count) / float(element_count)
            if element_count
            else 1.0
        ),
        "exact_source_property_coverage": exact,
        "missing_section_element_count": int(
            element_count - section_resolved_count
        ),
        "missing_material_element_count": int(
            element_count - material_resolved_count
        ),
        "missing_section_id_counts": [
            {"section_id": int(identifier), "element_count": int(count)}
            for identifier, count in sorted(missing_section_ids.items())
        ],
        "missing_material_id_counts": [
            {"material_id": int(identifier), "element_count": int(count)}
            for identifier, count in sorted(missing_material_ids.items())
        ],
        "unresolved_element_head": unresolved_rows[
            :unresolved_element_head_limit
        ],
        "unresolved_element_head_limit": int(
            unresolved_element_head_limit
        ),
        "fallback_allowed_for_state_updated_geometry": False,
        "claim_boundary": (
            "This audit checks exact section/material table binding for every "
            "selected frame element. A missing binding blocks the state-updated "
            "geometry path; design-material rows and synthetic fallback values "
            "are not promoted to analysis elastic properties."
        ),
    }


def _finite_state(
    values: Any,
    *,
    name: str,
    dimension: int,
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (dimension,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite vector of length {dimension}")
    return np.array(array, dtype=np.float64, copy=True)


def _finite_state_batch(
    values: Any,
    *,
    name: str,
    dimension: int,
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if (
        array.ndim != 2
        or int(array.shape[1]) != dimension
        or not np.all(np.isfinite(array))
    ):
        raise ValueError(
            f"{name} must be a finite matrix with second dimension {dimension}"
        )
    return np.array(array, dtype=np.float64, copy=True)


@dataclass(frozen=True)
class PrepackedStateUpdatedFrameAxialGeometry:
    """Vectorized conservative axial correction on global nodal 6-DOF rows."""

    dofs: np.ndarray
    relative_translation_operators: np.ndarray
    reference_chords_m: np.ndarray
    reference_lengths_m: np.ndarray
    axial_stiffness_n_per_m: np.ndarray
    n_dof: int
    meta: dict[str, Any]

    @property
    def element_count(self) -> int:
        return int(self.dofs.shape[0])

    def _kinematics(
        self,
        displacement_u: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        state = _finite_state(
            displacement_u,
            name="displacement_u",
            dimension=self.n_dof,
        )
        gathered = state[self.dofs]
        relative_translation = np.einsum(
            "eij,ej->ei",
            self.relative_translation_operators,
            gathered,
            optimize=True,
        )
        current_chords = self.reference_chords_m + relative_translation
        current_lengths = np.linalg.norm(current_chords, axis=1)
        if np.any(current_lengths <= 1.0e-12):
            element_index = int(np.flatnonzero(current_lengths <= 1.0e-12)[0])
            raise ValueError(
                "state-updated frame axial chord collapsed at packed element "
                f"index {element_index}"
            )
        current_directions = current_chords / current_lengths[:, None]
        return (
            relative_translation,
            current_chords,
            current_lengths,
            current_directions,
        )

    def _stable_axial_kinematics(
        self,
        displacement_u: np.ndarray,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
    ]:
        """Evaluate extension and its nonlinear remainder without cancellation."""

        (
            relative_translation,
            current_chords,
            current_lengths,
            current_directions,
        ) = self._kinematics(displacement_u)
        reference_directions = (
            self.reference_chords_m / self.reference_lengths_m[:, None]
        )
        linear_extensions_m = np.einsum(
            "ei,ei->e",
            reference_directions,
            relative_translation,
            optimize=True,
        )
        relative_translation_squared_m2 = np.einsum(
            "ei,ei->e",
            relative_translation,
            relative_translation,
            optimize=True,
        )
        length_sum_m = current_lengths + self.reference_lengths_m
        # Evaluate ||r + d|| - ||r|| by a difference of squares. Directly
        # subtracting the two lengths loses the second-order transverse term
        # when d is small relative to the reference chord.
        extensions_m = (
            2.0
            * self.reference_lengths_m
            * linear_extensions_m
            + relative_translation_squared_m2
        ) / length_sum_m
        # The correction uses extension - n_ref.d. Evaluate that second-order
        # remainder directly instead of subtracting two first-order values.
        extension_minus_linear_m = (
            relative_translation_squared_m2
            - linear_extensions_m * extensions_m
        ) / length_sum_m
        return (
            relative_translation,
            current_chords,
            current_lengths,
            current_directions,
            reference_directions,
            linear_extensions_m,
            extensions_m,
            extension_minus_linear_m,
        )

    def _element_end_forces(
        self,
        displacement_u: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        (
            _relative_translation,
            _current_chords,
            _current_lengths,
            current_directions,
            reference_directions,
            linear_extensions_m,
            extensions_m,
            _extension_minus_linear_m,
        ) = self._stable_axial_kinematics(displacement_u)
        axial_forces_n = self.axial_stiffness_n_per_m * extensions_m
        nonlinear_end_forces = axial_forces_n[:, None] * current_directions
        linear_end_forces = (
            self.axial_stiffness_n_per_m * linear_extensions_m
        )[:, None] * reference_directions
        return (
            nonlinear_end_forces,
            linear_end_forces,
            axial_forces_n,
            extensions_m,
        )

    def _scatter_element_forces(self, end_forces: np.ndarray) -> np.ndarray:
        element_nodal_forces = np.einsum(
            "eij,ei->ej",
            self.relative_translation_operators,
            end_forces,
            optimize=True,
        )
        global_forces = np.zeros(self.n_dof, dtype=np.float64)
        np.add.at(global_forces, self.dofs.ravel(), element_nodal_forces.ravel())
        return global_forces

    def assemble_total_axial_internal_force(
        self,
        displacement_u: np.ndarray,
    ) -> np.ndarray:
        nonlinear, _linear, _axial, _extension = self._element_end_forces(
            displacement_u
        )
        return self._scatter_element_forces(nonlinear)

    def assemble_reference_linear_axial_internal_force(
        self,
        displacement_u: np.ndarray,
    ) -> np.ndarray:
        _nonlinear, linear, _axial, _extension = self._element_end_forces(
            displacement_u
        )
        return self._scatter_element_forces(linear)

    def assemble_correction(
        self,
        displacement_u: np.ndarray,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        (
            _relative_translation,
            _current_chords,
            _current_lengths,
            current_directions,
            reference_directions,
            _linear_extensions_m,
            extensions_m,
            extension_minus_linear_m,
        ) = self._stable_axial_kinematics(displacement_u)
        direction_delta = current_directions - reference_directions
        correction_end_forces = self.axial_stiffness_n_per_m[:, None] * (
            extension_minus_linear_m[:, None] * reference_directions
            + extensions_m[:, None] * direction_delta
        )
        correction = self._scatter_element_forces(correction_end_forces)
        axial_forces_n = self.axial_stiffness_n_per_m * extensions_m
        return correction, {
            **self.meta,
            "state_updated_frame_axial_geometry_applied": True,
            "maximum_extension_abs_m": float(
                np.max(np.abs(extensions_m)) if extensions_m.size else 0.0
            ),
            "maximum_axial_force_abs_n": float(
                np.max(np.abs(axial_forces_n)) if axial_forces_n.size else 0.0
            ),
            "tension_element_count": int(np.count_nonzero(axial_forces_n > 0.0)),
            "compression_element_count": int(
                np.count_nonzero(axial_forces_n < 0.0)
            ),
            "correction_inf_n": float(
                np.linalg.norm(correction, ord=np.inf) if correction.size else 0.0
            ),
        }

    def correction_strain_energy_n_m(self, displacement_u: np.ndarray) -> float:
        (
            _relative_translation,
            _current_chords,
            _current_lengths,
            _current_directions,
            _reference_directions,
            linear_extensions_m,
            extensions_m,
            extension_minus_linear_m,
        ) = self._stable_axial_kinematics(displacement_u)
        correction_energy = 0.5 * self.axial_stiffness_n_per_m * (
            extension_minus_linear_m
            * (extensions_m + linear_extensions_m)
        )
        return float(np.sum(correction_energy))

    def tangent_action(
        self,
        displacement_u: np.ndarray,
        direction_u: np.ndarray,
    ) -> np.ndarray:
        (
            _relative_translation,
            _current_chords,
            current_lengths,
            current_directions,
            reference_directions,
            _linear_extensions_m,
            extensions_m,
            _extension_minus_linear_m,
        ) = self._stable_axial_kinematics(displacement_u)
        direction = _finite_state(
            direction_u,
            name="direction_u",
            dimension=self.n_dof,
        )
        gathered_direction = direction[self.dofs]
        relative_direction = np.einsum(
            "eij,ej->ei",
            self.relative_translation_operators,
            gathered_direction,
            optimize=True,
        )
        direction_delta = current_directions - reference_directions
        current_projection = np.einsum(
            "ei,ei->e",
            current_directions,
            relative_direction,
            optimize=True,
        )
        projection_delta = np.einsum(
            "ei,ei->e",
            direction_delta,
            relative_direction,
            optimize=True,
        )
        material_correction_action = self.axial_stiffness_n_per_m[:, None] * (
            projection_delta[:, None] * reference_directions
            + current_projection[:, None] * direction_delta
        )
        geometric_correction_action = (
            self.axial_stiffness_n_per_m * extensions_m / current_lengths
        )[:, None] * (
            relative_direction
            - current_projection[:, None] * current_directions
        )
        return self._scatter_element_forces(
            material_correction_action + geometric_correction_action
        )

    def assemble_correction_batch(
        self,
        displacement_batch: np.ndarray,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        states = _finite_state_batch(
            displacement_batch,
            name="displacement_batch",
            dimension=self.n_dof,
        )
        rows: list[np.ndarray] = []
        row_meta: list[dict[str, Any]] = []
        for state in states:
            correction, meta = self.assemble_correction(state)
            rows.append(correction)
            row_meta.append(meta)
        result = (
            np.vstack(rows)
            if rows
            else np.zeros((0, self.n_dof), dtype=np.float64)
        )
        return result, {
            **self.meta,
            "state_updated_frame_axial_geometry_applied": True,
            "batch_size": int(states.shape[0]),
            "maximum_batch_correction_inf_n": max(
                (float(row["correction_inf_n"]) for row in row_meta),
                default=0.0,
            ),
            "maximum_batch_axial_force_abs_n": max(
                (float(row["maximum_axial_force_abs_n"]) for row in row_meta),
                default=0.0,
            ),
        }


def prepack_state_updated_frame_axial_geometry(
    *,
    node_xyz: np.ndarray,
    frame_elements: list[FrameElement],
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    require_real_properties: bool = True,
) -> PrepackedStateUpdatedFrameAxialGeometry:
    """Prepack finite-chord axial kinematics without property fallbacks."""

    coordinates = np.asarray(node_xyz, dtype=np.float64)
    if (
        coordinates.ndim != 2
        or coordinates.shape[1] != 3
        or not np.all(np.isfinite(coordinates))
    ):
        raise ValueError("node_xyz must be a finite (n_nodes, 3) array")
    property_coverage = audit_state_updated_frame_axial_property_coverage(
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
    )
    if (
        require_real_properties
        and not property_coverage["exact_source_property_coverage"]
    ):
        missing_material_ids = [
            int(row["material_id"])
            for row in property_coverage["missing_material_id_counts"]
        ]
        missing_section_ids = [
            int(row["section_id"])
            for row in property_coverage["missing_section_id_counts"]
        ]
        first_unresolved = property_coverage["unresolved_element_head"][0]
        raise ValueError(
            "state-updated frame axial geometry requires complete source "
            "property coverage: unresolved_element_count="
            f"{property_coverage['unresolved_source_property_element_count']}, "
            f"missing_material_ids={missing_material_ids}, "
            f"missing_section_ids={missing_section_ids}, "
            f"first_unresolved_element={first_unresolved['element_id']}"
        )
    element_count = len(frame_elements)
    dofs = np.zeros((element_count, 12), dtype=np.int64)
    relative_operators = np.zeros((element_count, 3, 12), dtype=np.float64)
    reference_chords = np.zeros((element_count, 3), dtype=np.float64)
    reference_lengths = np.zeros(element_count, dtype=np.float64)
    axial_stiffness = np.zeros(element_count, dtype=np.float64)
    relative_end_selector = np.zeros((3, 12), dtype=np.float64)
    relative_end_selector[:, 0:3] = -np.eye(3, dtype=np.float64)
    relative_end_selector[:, 6:9] = np.eye(3, dtype=np.float64)
    real_property_count = 0
    offset_element_count = 0

    for element_index, element in enumerate(frame_elements):
        props, used_real = _frame_props(
            element,
            section_props=section_props,
            material_props=material_props,
        )
        real_property_count += int(used_real)
        start, end = _element_end_points(element, coordinates)
        chord = np.asarray(end - start, dtype=np.float64)
        length = float(np.linalg.norm(chord))
        if not np.isfinite(length) or length <= 1.0e-12:
            raise ValueError(
                f"state-updated frame axial element {element.elem_id} has zero length"
            )
        rigid = _rigid_end_offset_transform(
            np.asarray(element.offset_i_global_m, dtype=np.float64),
            np.asarray(element.offset_j_global_m, dtype=np.float64),
        )
        element_dofs = _node_dofs(element.node_i) + _node_dofs(element.node_j)
        dofs[element_index, :] = np.asarray(element_dofs, dtype=np.int64)
        relative_operators[element_index, :, :] = relative_end_selector @ rigid
        reference_chords[element_index, :] = chord
        reference_lengths[element_index] = length
        axial_stiffness[element_index] = (
            float(props.e_n_per_m2) * float(props.area_m2) / length
        )
        offset_element_count += int(
            np.any(np.abs(element.offset_i_global_m) > 1.0e-12)
            or np.any(np.abs(element.offset_j_global_m) > 1.0e-12)
        )

    for array in (
        dofs,
        relative_operators,
        reference_chords,
        reference_lengths,
        axial_stiffness,
    ):
        array.setflags(write=False)
    return PrepackedStateUpdatedFrameAxialGeometry(
        dofs=dofs,
        relative_translation_operators=relative_operators,
        reference_chords_m=reference_chords,
        reference_lengths_m=reference_lengths,
        axial_stiffness_n_per_m=axial_stiffness,
        n_dof=int(coordinates.shape[0]) * DOF_PER_NODE,
        meta={
            "schema_version": "mgt-state-updated-frame-axial-geometry.v1",
            "formulation_profile": STATE_UPDATED_FRAME_AXIAL_GEOMETRY_PROFILE,
            "element_count": int(element_count),
            "real_property_element_count": int(real_property_count),
            "property_fallback_count": int(element_count - real_property_count),
            "source_property_coverage_audit": property_coverage,
            "beam_end_offset_element_count": int(offset_element_count),
            "reference_linear_axial_contribution_replaced": True,
            "conservative_energy_gradient": True,
            "consistent_tangent_action_available": True,
            "finite_chord_translation_geometry": True,
            "finite_chord_extension_evaluation": (
                "difference_of_squares_cancellation_stable"
            ),
            "finite_chord_correction_evaluation": (
                "second_order_decomposition_cancellation_stable"
            ),
            "rigid_end_offset_rotation_map": (
                "small_rotation_linearized_offset_transform"
            ),
            "frame_bending_torsion_state_update_connected": False,
            "finite_nodal_rotation_objectivity_claim": False,
            "full_corotational_frame_claim": False,
            "material_state_update_claim": False,
            "claim_boundary": (
                "Replaces the reference linear axial force with a conservative "
                "finite-chord extension force and exact axial tangent action. "
                "Bending/torsion remain reference-geometry small-rotation terms; "
                "this is not a complete 3D corotational beam or material update."
            ),
        },
    )


__all__ = [
    "PrepackedStateUpdatedFrameAxialGeometry",
    "STATE_UPDATED_FRAME_AXIAL_GEOMETRY_PROFILE",
    "STATE_UPDATED_FRAME_AXIAL_PROPERTY_COVERAGE_SCHEMA_VERSION",
    "audit_state_updated_frame_axial_property_coverage",
    "prepack_state_updated_frame_axial_geometry",
]
