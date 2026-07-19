"""Fail-closed dense stiffness and consistent-mass assembly for modal analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structural_analysis.elements.axial import (
    AxialElementProperties,
    axial_element_properties,
    axial_global_consistent_mass,
    axial_global_stiffness,
)
from structural_analysis.elements.frame3d import (
    FRAME_DOF_LABELS,
    Frame3DProperties,
    frame3d_global_consistent_mass,
    frame3d_global_stiffness,
    frame3d_properties_from_canonical,
)
from structural_analysis.model.schema import CanonicalModel


DOF_LABELS = FRAME_DOF_LABELS
DOF_PER_NODE = len(DOF_LABELS)
SUPPORTED_MODAL_ELEMENT_TYPES = {"truss", "axial", "frame", "beam", "column"}
MASS_MATRIX_UNIT = "kN_s2_per_m"
DENSITY_UNIT = "kg_per_m3"
MASS_FORMULATION = "consistent_euler_bernoulli_with_torsional_rotary_inertia_v1"
NODAL_MASS_FIELDS = {
    "mass",
    "mass_kg",
    "mass_components",
    "lumped_mass",
    "lumped_mass_kg",
    "translational_mass_kg",
    "rotational_mass_kg_m2",
}
ELEMENT_MASS_OVERRIDE_FIELDS = {
    "additional_mass",
    "additional_mass_kg_per_m",
    "mass_scale",
    "nonstructural_mass",
    "nonstructural_mass_kg_per_m",
}


@dataclass(frozen=True)
class ModalElementAssemblyRecord:
    element_id: str
    element_type: str
    node_ids: tuple[str, str]
    dofs: tuple[int, ...]
    density_kg_per_m3: float
    physical_mass_kg: float
    properties: AxialElementProperties | Frame3DProperties


@dataclass(frozen=True)
class ModalAssembly:
    stiffness: np.ndarray
    mass: np.ndarray
    constrained_dofs: tuple[int, ...]
    active_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]
    node_ids: tuple[str, ...]
    node_coordinates: tuple[tuple[float, float, float], ...]
    element_records: tuple[ModalElementAssemblyRecord, ...]
    total_physical_mass_kg: float
    warnings: tuple[str, ...]
    mass_matrix_unit: str = MASS_MATRIX_UNIT
    density_unit: str = DENSITY_UNIT
    mass_formulation: str = MASS_FORMULATION


def assemble_modal_matrices(
    model: CanonicalModel,
) -> tuple[ModalAssembly | None, list[dict[str, Any]]]:
    """Assemble full and reduced-ready matrices without inventing mass inputs."""

    unsupported: list[dict[str, Any]] = []
    if model.units.length != "m" or model.units.force != "kN":
        unsupported.append(
            {
                "kind": "modal_units_not_supported",
                "detail": "Whole-model modal v1 requires explicit m/kN canonical units.",
            }
        )
    unsupported.extend(_unsupported_mass_inputs(model))

    node_ids = tuple(str(node.get("id", "")).strip() for node in model.nodes)
    if not node_ids:
        unsupported.append({"kind": "modal_nodes_missing"})
        return None, unsupported
    if any(not node_id for node_id in node_ids) or len(set(node_ids)) != len(node_ids):
        unsupported.append({"kind": "modal_node_ids_invalid_or_duplicate"})
        return None, unsupported
    coordinates = _node_coordinates(model.nodes, unsupported)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    materials = _unique_rows(model.materials, owner="material", unsupported=unsupported)
    sections = _unique_rows(model.sections, owner="section", unsupported=unsupported)

    dof_count = len(node_ids) * DOF_PER_NODE
    stiffness = np.zeros((dof_count, dof_count), dtype=np.float64)
    mass = np.zeros((dof_count, dof_count), dtype=np.float64)
    active_dofs: set[int] = set()
    records: list[ModalElementAssemblyRecord] = []
    element_ids: set[str] = set()

    for element in model.elements:
        assembled = _modal_element_matrices(
            element=element,
            element_ids=element_ids,
            node_index=node_index,
            coordinates=coordinates,
            materials=materials,
            sections=sections,
            unsupported=unsupported,
        )
        if assembled is None:
            continue
        element_stiffness, element_mass, record = assembled
        records.append(record)
        stiffness[np.ix_(record.dofs, record.dofs)] += element_stiffness
        mass[np.ix_(record.dofs, record.dofs)] += element_mass

        stiffness_scale = max(
            float(np.max(np.abs(element_stiffness))),
            np.finfo(np.float64).tiny,
        )
        mass_scale = max(
            float(np.max(np.abs(element_mass))),
            np.finfo(np.float64).tiny,
        )
        for local_row, global_row in enumerate(record.dofs):
            stiffness_active = (
                float(np.max(np.abs(element_stiffness[local_row, :])))
                > 1.0e-14 * stiffness_scale
            )
            mass_active = (
                float(np.max(np.abs(element_mass[local_row, :])))
                > 1.0e-14 * mass_scale
            )
            if stiffness_active or mass_active:
                active_dofs.add(global_row)

    if not model.elements:
        unsupported.append({"kind": "modal_elements_missing"})
    elif not records and not unsupported:
        unsupported.append({"kind": "modal_no_supported_elements"})

    constrained = _constrained_dofs(model.supports, node_index, unsupported)
    constrained_set = set(constrained)
    free_dofs = tuple(sorted(active_dofs - constrained_set))
    if records and not free_dofs:
        unsupported.append(
            {
                "kind": "modal_free_active_dofs_missing",
                "active_dof_count": len(active_dofs),
                "constrained_dof_count": len(constrained_set),
            }
        )
    if unsupported:
        return None, unsupported

    stiffness = 0.5 * (stiffness + stiffness.T)
    mass = 0.5 * (mass + mass.T)
    warnings = (
        ("Static load rows are ignored by undamped free-vibration modal analysis.",)
        if model.loads
        else ()
    )
    coordinate_rows = tuple(coordinates[node_id] for node_id in node_ids)
    return (
        ModalAssembly(
            stiffness=stiffness,
            mass=mass,
            constrained_dofs=tuple(sorted(constrained_set)),
            active_dofs=tuple(sorted(active_dofs)),
            free_dofs=free_dofs,
            node_ids=node_ids,
            node_coordinates=coordinate_rows,
            element_records=tuple(records),
            total_physical_mass_kg=float(
                sum(record.physical_mass_kg for record in records)
            ),
            warnings=warnings,
        ),
        [],
    )


def _modal_element_matrices(
    *,
    element: dict[str, Any],
    element_ids: set[str],
    node_index: dict[str, int],
    coordinates: dict[str, tuple[float, float, float]],
    materials: dict[str, dict[str, Any]],
    sections: dict[str, dict[str, Any]],
    unsupported: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, ModalElementAssemblyRecord] | None:
    element_id = str(element.get("id", "")).strip()
    if not element_id or element_id in element_ids:
        unsupported.append(
            {"kind": "modal_element_id_invalid_or_duplicate", "element": element_id}
        )
        return None
    element_ids.add(element_id)
    element_type = str(element.get("type", "")).strip().lower()
    if element_type not in SUPPORTED_MODAL_ELEMENT_TYPES:
        unsupported.append(
            {
                "kind": "modal_element_not_supported",
                "element": element_id,
                "element_type": element.get("type", ""),
            }
        )
        return None
    raw_nodes = element.get("nodes")
    if not isinstance(raw_nodes, (list, tuple)) or len(raw_nodes) != 2:
        unsupported.append(
            {"kind": "modal_element_connectivity_invalid", "element": element_id}
        )
        return None
    node_pair = (str(raw_nodes[0]), str(raw_nodes[1]))
    if any(
        node_id not in node_index or node_id not in coordinates
        for node_id in node_pair
    ):
        unsupported.append(
            {"kind": "modal_element_node_missing", "element": element_id}
        )
        return None
    material = materials.get(str(element.get("material", "")))
    section = sections.get(str(element.get("section", "")))
    if material is None:
        unsupported.append(
            {
                "kind": "modal_material_missing",
                "element": element_id,
                "detail": "Implicit material fallback is disabled.",
            }
        )
        return None
    if section is None:
        unsupported.append(
            {
                "kind": "modal_section_missing",
                "element": element_id,
                "detail": "Implicit section fallback is disabled.",
            }
        )
        return None
    density = _positive_number(
        material,
        ("density", "density_kg_per_m3", "density_kg_m3"),
    )
    if density is None:
        unsupported.append(
            {
                "kind": "modal_material_density_missing_or_invalid",
                "element": element_id,
                "material": str(element.get("material", "")),
                "detail": "Explicit finite positive density in kg/m^3 is required.",
            }
        )
        return None

    dofs = tuple(
        DOF_PER_NODE * node_index[node_id] + offset
        for node_id in node_pair
        for offset in range(DOF_PER_NODE)
    )
    try:
        if element_type in {"truss", "axial"}:
            modulus = _positive_number(
                material,
                ("elastic_modulus", "E_kN_per_m2"),
            )
            area = _positive_number(section, ("area", "A_m2"))
            if modulus is None or area is None:
                raise ValueError(
                    "explicit positive elastic_modulus and section area are required"
                )
            properties: AxialElementProperties | Frame3DProperties = (
                axial_element_properties(
                    element_id=element_id,
                    node_ids=node_pair,
                    start_coordinates=coordinates[node_pair[0]],
                    end_coordinates=coordinates[node_pair[1]],
                    elastic_modulus=modulus,
                    area=area,
                )
            )
            translational_stiffness = axial_global_stiffness(properties)
            translational_mass = axial_global_consistent_mass(
                properties,
                density_kg_per_m3=density,
            )
            element_stiffness = np.zeros((12, 12), dtype=np.float64)
            element_mass = np.zeros((12, 12), dtype=np.float64)
            translation_dofs = (0, 1, 2, 6, 7, 8)
            element_stiffness[np.ix_(translation_dofs, translation_dofs)] = (
                translational_stiffness
            )
            element_mass[np.ix_(translation_dofs, translation_dofs)] = (
                translational_mass
            )
            physical_mass = density * properties.area * properties.length
        else:
            properties = frame3d_properties_from_canonical(
                element=element,
                node_ids=node_pair,
                start_coordinates=coordinates[node_pair[0]],
                end_coordinates=coordinates[node_pair[1]],
                material=material,
                section=section,
            )
            element_stiffness = frame3d_global_stiffness(properties)
            element_mass = frame3d_global_consistent_mass(
                properties,
                density_kg_per_m3=density,
            )
            physical_mass = density * properties.props.area_m2 * properties.length_m
    except ValueError as exc:
        unsupported.append(
            {
                "kind": "modal_element_properties_invalid",
                "element": element_id,
                "detail": str(exc),
            }
        )
        return None

    if not np.all(np.isfinite(element_stiffness)) or not np.all(np.isfinite(element_mass)):
        unsupported.append(
            {"kind": "modal_element_matrix_nonfinite", "element": element_id}
        )
        return None
    return (
        element_stiffness,
        element_mass,
        ModalElementAssemblyRecord(
            element_id=element_id,
            element_type=element_type,
            node_ids=node_pair,
            dofs=dofs,
            density_kg_per_m3=density,
            physical_mass_kg=float(physical_mass),
            properties=properties,
        ),
    )


def _unique_rows(
    rows: list[dict[str, Any]],
    *,
    owner: str,
    unsupported: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row.get("id", "")).strip()
        if not row_id or row_id in result:
            unsupported.append(
                {"kind": f"modal_{owner}_id_invalid_or_duplicate", owner: row_id}
            )
            continue
        result[row_id] = row
    return result


def _node_coordinates(
    nodes: list[dict[str, Any]],
    unsupported: list[dict[str, Any]],
) -> dict[str, tuple[float, float, float]]:
    coordinates: dict[str, tuple[float, float, float]] = {}
    for node in nodes:
        node_id = str(node.get("id", "")).strip()
        raw = node.get("coordinates")
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            unsupported.append(
                {"kind": "modal_node_coordinates_invalid", "node": node_id}
            )
            continue
        try:
            coordinate = tuple(float(value) for value in raw)
        except (TypeError, ValueError):
            unsupported.append(
                {"kind": "modal_node_coordinates_invalid", "node": node_id}
            )
            continue
        if not all(np.isfinite(value) for value in coordinate):
            unsupported.append(
                {"kind": "modal_node_coordinates_invalid", "node": node_id}
            )
            continue
        coordinates[node_id] = coordinate  # type: ignore[assignment]
    return coordinates


def _constrained_dofs(
    supports: list[dict[str, Any]],
    node_index: dict[str, int],
    unsupported: list[dict[str, Any]],
) -> list[int]:
    constrained: list[int] = []
    for support in supports:
        node_id = str(support.get("node", support.get("node_id", ""))).strip()
        if node_id not in node_index:
            unsupported.append({"kind": "modal_support_node_missing", "node": node_id})
            continue
        raw_dofs = support.get("dofs", support.get("restrained_dofs", []))
        if raw_dofs == "all":
            raw_dofs = list(DOF_LABELS)
        if not isinstance(raw_dofs, (list, tuple)):
            unsupported.append(
                {"kind": "modal_support_dofs_invalid", "node": node_id}
            )
            continue
        for raw_dof in raw_dofs:
            label = str(raw_dof).strip().upper()
            if label not in DOF_LABELS:
                unsupported.append(
                    {
                        "kind": "modal_support_dof_not_supported",
                        "node": node_id,
                        "dof": raw_dof,
                    }
                )
                continue
            constrained.append(
                DOF_PER_NODE * node_index[node_id] + DOF_LABELS.index(label)
            )
    return constrained


def _positive_number(
    source: dict[str, Any],
    keys: tuple[str, ...],
) -> float | None:
    for key in keys:
        if key not in source or source.get(key) is None:
            continue
        value = source[key]
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) and number > 0.0 else None
    return None


def _unsupported_mass_inputs(model: CanonicalModel) -> list[dict[str, Any]]:
    unsupported: list[dict[str, Any]] = []
    for node in model.nodes:
        present = sorted(NODAL_MASS_FIELDS.intersection(node))
        if present:
            unsupported.append(
                {
                    "kind": "modal_nodal_mass_not_supported",
                    "node": str(node.get("id", "")),
                    "fields": present,
                    "detail": (
                        "Whole-model modal v1 assembles member consistent mass only; "
                        "nodal lumped mass must not be silently ignored."
                    ),
                }
            )
    for element in model.elements:
        present = sorted(ELEMENT_MASS_OVERRIDE_FIELDS.intersection(element))
        if present:
            unsupported.append(
                {
                    "kind": "modal_element_mass_override_not_supported",
                    "element": str(element.get("id", "")),
                    "fields": present,
                }
            )
    for load_index, load in enumerate(model.loads):
        kind = str(load.get("kind", "")).strip().lower()
        if kind in {"mass", "nodal_mass", "lumped_mass"}:
            unsupported.append(
                {
                    "kind": "modal_nodal_mass_not_supported",
                    "load_index": load_index,
                    "load_kind": kind,
                }
            )
    metadata = model.metadata if isinstance(model.metadata, dict) else {}
    nodal_masses = metadata.get("nodal_masses")
    if isinstance(nodal_masses, list) and nodal_masses:
        unsupported.append(
            {
                "kind": "modal_nodal_mass_not_supported",
                "metadata_path": "nodal_masses",
                "row_count": len(nodal_masses),
            }
        )
    for count_owner in ("section_counts", "raw_section_counts"):
        counts = metadata.get(count_owner)
        if not isinstance(counts, dict):
            continue
        try:
            count = int(counts.get("NODALMASS", 0))
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            unsupported.append(
                {
                    "kind": "modal_nodal_mass_not_supported",
                    "metadata_path": f"{count_owner}.NODALMASS",
                    "row_count": count,
                }
            )
    return unsupported
