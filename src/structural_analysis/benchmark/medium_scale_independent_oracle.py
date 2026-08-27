"""Independent assembly oracle for the generated medium Frame/Truss profile.

This module deliberately does not import the production assembly, element,
solver, or API layers.  It is a second implementation of the narrow linear
Euler--Bernoulli Frame3D and axial-truss equations used by the deterministic
medium profile.  Its output is an internal differential reference only; it is
not an external solver, an independent operator run, or a scientific
validation decision.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.linalg import solve


ORACLE_ID = "repository-independent-medium-frame3d-oracle.v1"
ORACLE_TRUTH_CLASS = "same_repository_independent_implementation"
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
END_FORCE_LABELS = (
    "FX_I",
    "FY_I",
    "FZ_I",
    "MX_I",
    "MY_I",
    "MZ_I",
    "FX_J",
    "FY_J",
    "FZ_J",
    "MX_J",
    "MY_J",
    "MZ_J",
)
NORMALIZATION_POLICY = {
    "policy_id": "medium-frame3d-reference-normalization.v1",
    "units": {"length": "m", "force": "kN", "moment": "kN*m"},
    "global_axes": ["X", "Y", "Z"],
    "node_order": "lexicographic_stable_id",
    "member_order": "lexicographic_stable_id",
    "dof_order": list(DOF_LABELS),
    "member_direction": "canonical_i_to_j",
    "local_axis": "local_x_i_to_j_reference_global_z_fallback_global_y",
    "member_end_force_sign": "element_action_positive_in_positive_local_dof",
    "reaction_sign": "assembled_internal_minus_external_at_constrained_dofs",
}


class MediumScaleOracleError(ValueError):
    """Stable fail-closed error for inputs outside the internal oracle subset."""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def oracle_implementation_sha256() -> str:
    """Bind a receipt to the exact second-implementation source bytes."""

    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _positive_number(source: Mapping[str, Any], key: str, *, owner: str) -> float:
    try:
        value = float(source[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediumScaleOracleError(f"{owner}:{key}:explicit_number_required") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise MediumScaleOracleError(f"{owner}:{key}:positive_finite_required")
    return value


def _scatter(matrix: np.ndarray, indices: Sequence[int], values: np.ndarray) -> None:
    for local_row, global_row in enumerate(indices):
        for local_column, global_column in enumerate(indices):
            matrix[global_row, global_column] += float(values[local_row, local_column])


def _local_frame_stiffness(
    *,
    elastic_modulus: float,
    shear_modulus: float,
    area: float,
    iy: float,
    iz: float,
    torsional_constant: float,
    length: float,
) -> np.ndarray:
    """Return the standard 12-DOF Euler--Bernoulli local stiffness."""

    matrix = np.zeros((12, 12), dtype=np.float64)
    axial = elastic_modulus * area / length
    torsion = shear_modulus * torsional_constant / length
    _scatter(matrix, (0, 6), np.array([[axial, -axial], [-axial, axial]]))
    _scatter(matrix, (3, 9), np.array([[torsion, -torsion], [-torsion, torsion]]))

    length_squared = length * length
    length_cubed = length_squared * length
    eiz = elastic_modulus * iz
    about_z = np.array(
        [
            [
                12.0 * eiz / length_cubed,
                6.0 * eiz / length_squared,
                -12.0 * eiz / length_cubed,
                6.0 * eiz / length_squared,
            ],
            [
                6.0 * eiz / length_squared,
                4.0 * eiz / length,
                -6.0 * eiz / length_squared,
                2.0 * eiz / length,
            ],
            [
                -12.0 * eiz / length_cubed,
                -6.0 * eiz / length_squared,
                12.0 * eiz / length_cubed,
                -6.0 * eiz / length_squared,
            ],
            [
                6.0 * eiz / length_squared,
                2.0 * eiz / length,
                -6.0 * eiz / length_squared,
                4.0 * eiz / length,
            ],
        ],
        dtype=np.float64,
    )
    _scatter(matrix, (1, 5, 7, 11), about_z)

    eiy = elastic_modulus * iy
    about_y = np.array(
        [
            [
                12.0 * eiy / length_cubed,
                -6.0 * eiy / length_squared,
                -12.0 * eiy / length_cubed,
                -6.0 * eiy / length_squared,
            ],
            [
                -6.0 * eiy / length_squared,
                4.0 * eiy / length,
                6.0 * eiy / length_squared,
                2.0 * eiy / length,
            ],
            [
                -12.0 * eiy / length_cubed,
                6.0 * eiy / length_squared,
                12.0 * eiy / length_cubed,
                6.0 * eiy / length_squared,
            ],
            [
                -6.0 * eiy / length_squared,
                2.0 * eiy / length,
                6.0 * eiy / length_squared,
                4.0 * eiy / length,
            ],
        ],
        dtype=np.float64,
    )
    _scatter(matrix, (2, 4, 8, 10), about_y)
    return 0.5 * (matrix + matrix.T)


def _frame_rotation(start: np.ndarray, end: np.ndarray) -> np.ndarray:
    local_x = np.asarray(end - start, dtype=np.float64)
    length = float(np.linalg.norm(local_x))
    if not math.isfinite(length) or length <= 1.0e-12:
        raise MediumScaleOracleError("frame_chord:positive_length_required")
    local_x /= length
    reference = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(float(local_x @ reference)) > 0.95:
        reference = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    local_y = np.cross(reference, local_x)
    local_y /= float(np.linalg.norm(local_y))
    local_z = np.cross(local_x, local_y)
    local_z /= float(np.linalg.norm(local_z))
    return np.vstack((local_x, local_y, local_z))


def _frame_transform(rotation: np.ndarray) -> np.ndarray:
    transform = np.zeros((12, 12), dtype=np.float64)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = rotation
    return transform


def _element_properties(
    element: Mapping[str, Any],
    materials: Mapping[str, Mapping[str, Any]],
    sections: Mapping[str, Mapping[str, Any]],
) -> tuple[float, float, Mapping[str, Any]]:
    element_id = str(element.get("id", ""))
    material_id = str(element.get("material", ""))
    section_id = str(element.get("section", ""))
    if material_id not in materials or section_id not in sections:
        raise MediumScaleOracleError(
            f"element:{element_id}:material_or_section_missing"
        )
    material = materials[material_id]
    section = sections[section_id]
    elastic_modulus = _positive_number(
        material, "elastic_modulus", owner=f"material:{material_id}"
    )
    poisson = _positive_number(
        material, "poisson_ratio", owner=f"material:{material_id}"
    )
    if poisson >= 0.5:
        raise MediumScaleOracleError(
            f"material:{material_id}:poisson_ratio_outside_oracle_range"
        )
    shear_modulus = elastic_modulus / (2.0 * (1.0 + poisson))
    return elastic_modulus, shear_modulus, section


def _element_matrix_and_recovery(
    *,
    element: Mapping[str, Any],
    start: np.ndarray,
    end: np.ndarray,
    materials: Mapping[str, Mapping[str, Any]],
    sections: Mapping[str, Mapping[str, Any]],
) -> tuple[np.ndarray, tuple[str, np.ndarray, np.ndarray | None]]:
    element_id = str(element.get("id", ""))
    element_type = str(element.get("type", "")).lower()
    forbidden = {
        "local_axis_angle_deg",
        "local_axis_angle",
        "offset_i",
        "offset_j",
        "rigid_offset_i",
        "rigid_offset_j",
        "releases",
        "release_i",
        "release_j",
    }
    if any(key in element for key in forbidden):
        raise MediumScaleOracleError(
            f"element:{element_id}:release_offset_or_roll_outside_oracle_subset"
        )
    elastic_modulus, shear_modulus, section = _element_properties(
        element, materials, sections
    )
    chord = np.asarray(end - start, dtype=np.float64)
    length = float(np.linalg.norm(chord))
    if not math.isfinite(length) or length <= 1.0e-12:
        raise MediumScaleOracleError(f"element:{element_id}:positive_length_required")

    if element_type in {"truss", "axial"}:
        area = _positive_number(
            section, "area", owner=f"section:{element.get('section', '')}"
        )
        direction = chord / length
        dyad = np.outer(direction, direction) * (elastic_modulus * area / length)
        translation = np.block([[dyad, -dyad], [-dyad, dyad]])
        matrix = np.zeros((12, 12), dtype=np.float64)
        translation_dofs = (0, 1, 2, 6, 7, 8)
        _scatter(matrix, translation_dofs, translation)
        return matrix, (element_type, direction, None)

    if element_type not in {"frame", "beam", "column"}:
        raise MediumScaleOracleError(
            f"element:{element_id}:unsupported_type:{element_type}"
        )
    area = _positive_number(
        section, "area", owner=f"section:{element.get('section', '')}"
    )
    iy = _positive_number(section, "iy", owner=f"section:{element.get('section', '')}")
    iz = _positive_number(section, "iz", owner=f"section:{element.get('section', '')}")
    torsional_constant = _positive_number(
        section,
        "torsional_constant",
        owner=f"section:{element.get('section', '')}",
    )
    local = _local_frame_stiffness(
        elastic_modulus=elastic_modulus,
        shear_modulus=shear_modulus,
        area=area,
        iy=iy,
        iz=iz,
        torsional_constant=torsional_constant,
        length=length,
    )
    transform = _frame_transform(_frame_rotation(start, end))
    return transform.T @ local @ transform, (element_type, local, transform)


def _model_rows(model: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = model.get(key)
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise MediumScaleOracleError(f"model:{key}:list_of_objects_required")
    return value


def run_independent_medium_oracle(model: Mapping[str, Any]) -> dict[str, Any]:
    """Assemble, solve, recover, and normalize one generated medium model."""

    started = time.perf_counter()
    units = model.get("units")
    coordinate_system = model.get("coordinate_system")
    if units != {"length": "m", "force": "kN"}:
        raise MediumScaleOracleError("model:explicit_m_kn_units_required")
    if coordinate_system != {
        "axis_order": ["X", "Y", "Z"],
        "up_axis": "Z",
    }:
        raise MediumScaleOracleError("model:global_xyz_z_up_required")

    nodes = _model_rows(model, "nodes")
    elements = _model_rows(model, "elements")
    materials_rows = _model_rows(model, "materials")
    sections_rows = _model_rows(model, "sections")
    loads = _model_rows(model, "loads")
    supports = _model_rows(model, "supports")
    node_ids = [str(row.get("id", "")) for row in nodes]
    if not node_ids or len(node_ids) != len(set(node_ids)) or "" in node_ids:
        raise MediumScaleOracleError("model:nodes:unique_nonempty_ids_required")
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    coordinates: dict[str, np.ndarray] = {}
    for row in nodes:
        node_id = str(row["id"])
        raw = row.get("coordinates")
        if not isinstance(raw, list) or len(raw) != 3:
            raise MediumScaleOracleError(f"node:{node_id}:three_coordinates_required")
        values = np.asarray(raw, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise MediumScaleOracleError(f"node:{node_id}:finite_coordinates_required")
        coordinates[node_id] = values

    def unique_rows(
        rows: Sequence[Mapping[str, Any]], owner: str
    ) -> dict[str, Mapping[str, Any]]:
        identities = [str(row.get("id", "")) for row in rows]
        if "" in identities or len(identities) != len(set(identities)):
            raise MediumScaleOracleError(f"model:{owner}:unique_nonempty_ids_required")
        return dict(zip(identities, rows, strict=True))

    materials = unique_rows(materials_rows, "materials")
    sections = unique_rows(sections_rows, "sections")
    equation_count = 6 * len(node_ids)
    stiffness = np.zeros((equation_count, equation_count), dtype=np.float64)
    active: set[int] = set()
    recovery_rows: list[
        tuple[
            str,
            str,
            tuple[str, str],
            tuple[int, ...],
            tuple[str, np.ndarray, np.ndarray | None],
        ]
    ] = []
    element_ids: set[str] = set()
    for element in elements:
        element_id = str(element.get("id", ""))
        if not element_id or element_id in element_ids:
            raise MediumScaleOracleError("model:elements:unique_nonempty_ids_required")
        element_ids.add(element_id)
        raw_nodes = element.get("nodes")
        if not isinstance(raw_nodes, list) or len(raw_nodes) != 2:
            raise MediumScaleOracleError(
                f"element:{element_id}:two_node_connectivity_required"
            )
        pair = (str(raw_nodes[0]), str(raw_nodes[1]))
        if pair[0] not in node_index or pair[1] not in node_index:
            raise MediumScaleOracleError(f"element:{element_id}:unknown_node")
        matrix, recovery = _element_matrix_and_recovery(
            element=element,
            start=coordinates[pair[0]],
            end=coordinates[pair[1]],
            materials=materials,
            sections=sections,
        )
        dofs = tuple(
            6 * node_index[node_id] + local_dof
            for node_id in pair
            for local_dof in range(6)
        )
        row_scale = max(float(np.max(np.abs(matrix))), 1.0)
        for local_row, global_row in enumerate(dofs):
            if float(np.max(np.abs(matrix[local_row, :]))) > 1.0e-14 * row_scale:
                active.add(global_row)
        stiffness[np.ix_(dofs, dofs)] += matrix
        recovery_rows.append(
            (element_id, str(element.get("type", "")).lower(), pair, dofs, recovery)
        )

    external = np.zeros(equation_count, dtype=np.float64)
    load_labels = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    for load in loads:
        node_id = str(load.get("node", load.get("node_id", "")))
        if node_id not in node_index:
            raise MediumScaleOracleError(f"load:unknown_node:{node_id}")
        components = load.get("components")
        if not isinstance(components, Mapping):
            raise MediumScaleOracleError(f"load:{node_id}:component_map_required")
        for local_dof, label in enumerate(load_labels):
            value = float(components.get(label, 0.0))
            if not math.isfinite(value):
                raise MediumScaleOracleError(f"load:{node_id}:{label}:finite_required")
            external[6 * node_index[node_id] + local_dof] += value
    inactive_loaded = sorted(
        int(index)
        for index in np.flatnonzero(np.abs(external) > 0.0)
        if int(index) not in active
    )
    if inactive_loaded:
        raise MediumScaleOracleError(
            "model:load_on_inactive_equation:" + ",".join(map(str, inactive_loaded))
        )

    constrained: set[int] = set()
    for support in supports:
        node_id = str(support.get("node", support.get("node_id", "")))
        if node_id not in node_index:
            raise MediumScaleOracleError(f"support:unknown_node:{node_id}")
        raw_dofs = support.get("dofs", support.get("restrained_dofs"))
        if raw_dofs == "all":
            raw_dofs = list(DOF_LABELS)
        if not isinstance(raw_dofs, list):
            raise MediumScaleOracleError(f"support:{node_id}:dof_list_required")
        for raw in raw_dofs:
            label = str(raw).upper()
            if label not in DOF_LABELS:
                raise MediumScaleOracleError(f"support:{node_id}:unknown_dof:{label}")
            constrained.add(6 * node_index[node_id] + DOF_LABELS.index(label))

    free = sorted(active - constrained)
    if len(free) < 1:
        raise MediumScaleOracleError("model:no_free_active_equations")
    free_matrix = stiffness[np.ix_(free, free)]
    free_load = external[free]
    try:
        free_displacement = solve(
            free_matrix,
            free_load,
            assume_a="sym",
            check_finite=True,
        )
    except Exception as exc:
        raise MediumScaleOracleError("oracle_dense_direct_solve_failed") from exc
    if not np.all(np.isfinite(free_displacement)):
        raise MediumScaleOracleError("oracle_dense_direct_solve_nonfinite")
    displacement = np.zeros(equation_count, dtype=np.float64)
    displacement[free] = free_displacement
    internal = stiffness @ displacement
    residual = internal - external
    free_residual = residual[free]
    relative_residual = float(
        np.linalg.norm(free_residual, ord=np.inf)
        / max(float(np.linalg.norm(free_load, ord=np.inf)), 1.0)
    )
    reaction = np.zeros(equation_count, dtype=np.float64)
    constrained_indices = sorted(constrained)
    reaction[constrained_indices] = residual[constrained_indices]

    member_forces: list[dict[str, Any]] = []
    for element_id, element_type, pair, dofs, recovery in recovery_rows:
        kind, first, second = recovery
        element_displacement = displacement[list(dofs)]
        if kind in {"truss", "axial"}:
            direction = first
            element = next(row for row in elements if str(row["id"]) == element_id)
            elastic_modulus, _, section = _element_properties(
                element, materials, sections
            )
            area = _positive_number(
                section,
                "area",
                owner=f"section:{element.get('section', '')}",
            )
            length = float(np.linalg.norm(coordinates[pair[1]] - coordinates[pair[0]]))
            extension = float(
                direction @ (element_displacement[6:9] - element_displacement[0:3])
            )
            axial = elastic_modulus * area / length * extension
            local_values = {"FX_I": -axial, "FX_J": axial}
        else:
            local = first
            assert second is not None
            transform = second
            local_force = local @ transform @ element_displacement
            local_values = {
                label: float(local_force[index])
                for index, label in enumerate(END_FORCE_LABELS)
            }
        member_forces.append(
            {
                "id": element_id,
                "type": element_type,
                "nodes": list(pair),
                "local_end_forces": local_values,
            }
        )

    displacement_rows = {
        node_id: {
            label: float(displacement[6 * node_index[node_id] + index])
            for index, label in enumerate(DOF_LABELS)
        }
        for node_id in node_ids
    }
    reaction_rows = {
        node_id: {
            label: float(reaction[6 * node_index[node_id] + index])
            for index, label in enumerate(DOF_LABELS)
        }
        for node_id in node_ids
    }
    normalized = {
        "displacements": [
            displacement_rows[node_id][label]
            for node_id in sorted(displacement_rows)
            for label in DOF_LABELS
        ],
        "reactions": [
            reaction_rows[node_id][label]
            for node_id in sorted(reaction_rows)
            for label in DOF_LABELS
        ],
        "member_forces": [
            float(member["local_end_forces"][label])
            for member in sorted(member_forces, key=lambda row: str(row["id"]))
            for label in sorted(member["local_end_forces"])
        ],
        "strain_energy": float(0.5 * displacement @ internal),
        "free_dof_count": len(free),
    }
    raw = {
        "node_ids": node_ids,
        "displacements": displacement_rows,
        "reactions": reaction_rows,
        "member_forces": member_forces,
        "strain_energy": normalized["strain_energy"],
        "relative_residual": relative_residual,
        "free_dof_count": len(free),
    }
    return {
        "oracle_id": ORACLE_ID,
        "truth_class": ORACLE_TRUTH_CLASS,
        "implementation_source_sha256": oracle_implementation_sha256(),
        "normalization_policy": NORMALIZATION_POLICY,
        "raw_result_sha256": _canonical_hash(raw),
        "normalized_result_sha256": _canonical_hash(normalized),
        "normalized_projection": normalized,
        "relative_residual": relative_residual,
        "free_dof_count": len(free),
        "execution_seconds": time.perf_counter() - started,
        "authority_boundary": (
            "Independent repository implementation and normalization only; not an "
            "external solver, independent operator, scientific acceptance, or product authority."
        ),
    }


__all__ = [
    "MediumScaleOracleError",
    "NORMALIZATION_POLICY",
    "ORACLE_ID",
    "ORACLE_TRUTH_CLASS",
    "oracle_implementation_sha256",
    "run_independent_medium_oracle",
]
