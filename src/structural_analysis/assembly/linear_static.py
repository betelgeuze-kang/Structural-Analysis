"""Strict 6-DOF global assembly for the authoritative CPU linear solver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from structural_analysis.elements.axial import (
    AxialElementProperties,
    axial_element_properties,
    axial_global_stiffness,
)
from structural_analysis.elements.frame3d import (
    FRAME_DOF_LABELS,
    FRAME_END_FORCE_LABELS,
    Frame3DProperties,
    frame3d_global_stiffness,
    frame3d_local_end_forces,
    frame3d_properties_from_canonical,
)
from structural_analysis.model.schema import CanonicalModel

DOF_LABELS = FRAME_DOF_LABELS
DOF_PER_NODE = len(DOF_LABELS)
LOAD_COMPONENT_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
STIFFNESS_STORAGE = "dense_numpy"
SPARSE_STIFFNESS_STORAGE = "scipy_sparse_csr"
SUPPORTED_ELEMENT_TYPES = {"truss", "axial", "frame", "beam", "column"}


@dataclass(frozen=True)
class ElementAssemblyRecord:
    element_id: str
    element_type: str
    node_ids: tuple[str, str]
    dofs: tuple[int, ...]
    properties: AxialElementProperties | Frame3DProperties


@dataclass(frozen=True)
class LinearStaticAssembly:
    stiffness: np.ndarray | csr_matrix
    loads: np.ndarray
    constrained_dofs: tuple[int, ...]
    active_dofs: tuple[int, ...]
    node_ids: tuple[str, ...]
    node_coordinates: tuple[tuple[float, float, float], ...]
    element_records: tuple[ElementAssemblyRecord, ...]
    warnings: tuple[str, ...]
    stiffness_storage: str = STIFFNESS_STORAGE


def assemble_linear_static(
    model: CanonicalModel,
    *,
    load_case: str | None = None,
) -> tuple[LinearStaticAssembly | None, list[dict[str, Any]]]:
    return _assemble_linear_static(model, sparse=False, load_case=load_case)


def assemble_linear_static_sparse(
    model: CanonicalModel,
    *,
    load_case: str | None = None,
) -> tuple[LinearStaticAssembly | None, list[dict[str, Any]]]:
    return _assemble_linear_static(model, sparse=True, load_case=load_case)


def _assemble_linear_static(
    model: CanonicalModel,
    *,
    sparse: bool,
    load_case: str | None,
) -> tuple[LinearStaticAssembly | None, list[dict[str, Any]]]:
    unsupported: list[dict[str, Any]] = []
    if model.units.length != "m" or model.units.force != "kN":
        unsupported.append(
            {
                "kind": "linear_static_units_not_supported",
                "detail": "Authoritative CPU v1 requires explicit m/kN canonical units.",
            }
        )
    node_ids = tuple(str(node.get("id", "")) for node in model.nodes)
    if not node_ids:
        unsupported.append({"kind": "linear_static_nodes_missing"})
        return None, unsupported
    if len(set(node_ids)) != len(node_ids):
        unsupported.append({"kind": "linear_static_duplicate_nodes"})
        return None, unsupported

    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    coordinates = _node_coordinates(model.nodes, unsupported)
    materials = {str(row.get("id", "")): row for row in model.materials}
    sections = {str(row.get("id", "")): row for row in model.sections}
    dof_count = len(node_ids) * DOF_PER_NODE
    dense_stiffness = np.zeros((dof_count, dof_count), dtype=float) if not sparse else None
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    active_dofs: set[int] = set()
    records: list[ElementAssemblyRecord] = []

    for element in model.elements:
        assembled = _element_matrix(
            element=element,
            node_index=node_index,
            coordinates=coordinates,
            materials=materials,
            sections=sections,
            unsupported=unsupported,
        )
        if assembled is None:
            continue
        element_stiffness, record = assembled
        records.append(record)
        row_scale = max(float(np.max(np.abs(element_stiffness))), 1.0)
        for local_row, global_row in enumerate(record.dofs):
            if float(np.max(np.abs(element_stiffness[local_row, :]))) > 1.0e-14 * row_scale:
                active_dofs.add(global_row)
            for local_column, global_column in enumerate(record.dofs):
                value = float(element_stiffness[local_row, local_column])
                if value == 0.0:
                    continue
                if sparse:
                    rows.append(global_row)
                    cols.append(global_column)
                    data.append(value)
                else:
                    assert dense_stiffness is not None
                    dense_stiffness[global_row, global_column] += value

    selected_loads = _select_load_case(model.loads, load_case, unsupported)
    loads = _load_vector(selected_loads, node_index, unsupported)
    constrained_dofs = _constrained_dofs(model.supports, node_index, unsupported)
    if not selected_loads:
        unsupported.append(
            {"kind": "linear_static_loads_missing", "load_case": load_case}
        )
    if not model.supports:
        unsupported.append({"kind": "linear_static_supports_missing"})
    if not model.elements:
        unsupported.append({"kind": "linear_static_elements_missing"})
    if model.elements and not records:
        unsupported.append({"kind": "linear_static_no_supported_elements"})

    for dof in np.flatnonzero(np.abs(loads) > 0.0).tolist():
        if int(dof) not in active_dofs:
            node_id = node_ids[int(dof) // DOF_PER_NODE]
            label = DOF_LABELS[int(dof) % DOF_PER_NODE]
            unsupported.append(
                {
                    "kind": "linear_static_load_on_inactive_dof",
                    "node": node_id,
                    "dof": label,
                    "detail": "No assembled element stiffness supports this loaded DOF.",
                }
            )

    if unsupported:
        return None, unsupported
    stiffness: np.ndarray | csr_matrix
    storage: str
    if sparse:
        stiffness = coo_matrix((data, (rows, cols)), shape=(dof_count, dof_count)).tocsr()
        storage = SPARSE_STIFFNESS_STORAGE
    else:
        assert dense_stiffness is not None
        stiffness = dense_stiffness
        storage = STIFFNESS_STORAGE
    coordinate_rows = tuple(coordinates[node_id] for node_id in node_ids)
    return (
        LinearStaticAssembly(
            stiffness=stiffness,
            loads=loads,
            constrained_dofs=tuple(sorted(set(constrained_dofs))),
            active_dofs=tuple(sorted(active_dofs)),
            node_ids=node_ids,
            node_coordinates=coordinate_rows,
            element_records=tuple(records),
            warnings=(),
            stiffness_storage=storage,
        ),
        [],
    )


def recover_element_results(
    assembly: LinearStaticAssembly,
    displacements: np.ndarray,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for record in assembly.element_records:
        element_displacement = np.asarray(displacements[list(record.dofs)], dtype=float)
        if isinstance(record.properties, Frame3DProperties):
            local_forces = frame3d_local_end_forces(record.properties, element_displacement)
            results.append(
                {
                    "id": record.element_id,
                    "type": record.element_type,
                    "nodes": list(record.node_ids),
                    "local_end_forces": {
                        label: float(local_forces[index])
                        for index, label in enumerate(FRAME_END_FORCE_LABELS)
                    },
                }
            )
            continue
        properties = record.properties
        direction = np.asarray(properties.direction_cosines, dtype=float)
        translation_indices = (0, 1, 2, 6, 7, 8)
        translation = element_displacement[list(translation_indices)]
        elongation = float(np.dot(direction, translation[3:6] - translation[0:3]))
        axial_force = (
            properties.elastic_modulus * properties.area / properties.length * elongation
        )
        results.append(
            {
                "id": record.element_id,
                "type": record.element_type,
                "nodes": list(record.node_ids),
                "axial_force": float(axial_force),
                "elongation": elongation,
                "local_end_forces": {"FX_I": -float(axial_force), "FX_J": float(axial_force)},
            }
        )
    return results


def _element_matrix(
    *,
    element: dict[str, Any],
    node_index: dict[str, int],
    coordinates: dict[str, tuple[float, float, float]],
    materials: dict[str, dict[str, Any]],
    sections: dict[str, dict[str, Any]],
    unsupported: list[dict[str, Any]],
) -> tuple[np.ndarray, ElementAssemblyRecord] | None:
    element_id = str(element.get("id", ""))
    element_type = str(element.get("type", "")).lower()
    if element_type not in SUPPORTED_ELEMENT_TYPES:
        unsupported.append(
            {
                "kind": "linear_static_element_not_supported",
                "element": element_id,
                "element_type": element.get("type", ""),
            }
        )
        return None
    raw_nodes = element.get("nodes")
    if not isinstance(raw_nodes, list) or len(raw_nodes) != 2:
        unsupported.append(
            {"kind": "linear_static_element_connectivity_invalid", "element": element_id}
        )
        return None
    node_pair = (str(raw_nodes[0]), str(raw_nodes[1]))
    if any(node_id not in node_index or node_id not in coordinates for node_id in node_pair):
        unsupported.append({"kind": "linear_static_element_node_missing", "element": element_id})
        return None
    material = materials.get(str(element.get("material", "")))
    section = sections.get(str(element.get("section", "")))
    if material is None:
        unsupported.append(
            {
                "kind": "linear_static_material_missing",
                "element": element_id,
                "detail": "Production fallback material is disabled.",
            }
        )
        return None
    if section is None:
        unsupported.append(
            {
                "kind": "linear_static_section_missing",
                "element": element_id,
                "detail": "Production fallback section is disabled.",
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
            elastic_modulus = _positive_float(material, ("elastic_modulus", "E_kN_per_m2"))
            area = _positive_float(section, ("area", "A_m2"))
            if elastic_modulus is None:
                raise ValueError("explicit positive elastic_modulus is required")
            if area is None:
                raise ValueError("explicit positive section area is required")
            properties: AxialElementProperties | Frame3DProperties = axial_element_properties(
                element_id=element_id,
                node_ids=node_pair,
                start_coordinates=coordinates[node_pair[0]],
                end_coordinates=coordinates[node_pair[1]],
                elastic_modulus=elastic_modulus,
                area=area,
            )
            translational = axial_global_stiffness(properties)
            element_stiffness = np.zeros((12, 12), dtype=float)
            translation_dofs = (0, 1, 2, 6, 7, 8)
            for row, target_row in enumerate(translation_dofs):
                for column, target_column in enumerate(translation_dofs):
                    element_stiffness[target_row, target_column] = translational[row, column]
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
    except ValueError as exc:
        unsupported.append(
            {
                "kind": "linear_static_element_properties_invalid",
                "element": element_id,
                "detail": str(exc),
            }
        )
        return None
    return (
        element_stiffness,
        ElementAssemblyRecord(
            element_id=element_id,
            element_type=element_type,
            node_ids=node_pair,
            dofs=dofs,
            properties=properties,
        ),
    )


def _node_coordinates(
    nodes: list[dict[str, Any]],
    unsupported: list[dict[str, Any]],
) -> dict[str, tuple[float, float, float]]:
    coordinates: dict[str, tuple[float, float, float]] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        raw = node.get("coordinates")
        if not isinstance(raw, list) or len(raw) != 3:
            unsupported.append(
                {"kind": "linear_static_node_coordinates_invalid", "node": node_id}
            )
            continue
        try:
            coordinate = tuple(float(value) for value in raw)
        except (TypeError, ValueError):
            unsupported.append(
                {"kind": "linear_static_node_coordinates_invalid", "node": node_id}
            )
            continue
        if not all(np.isfinite(value) for value in coordinate):
            unsupported.append(
                {"kind": "linear_static_node_coordinates_invalid", "node": node_id}
            )
            continue
        coordinates[node_id] = coordinate  # type: ignore[assignment]
    return coordinates


def _select_load_case(
    loads: list[dict[str, Any]],
    load_case: str | None,
    unsupported: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if load_case is None:
        return loads
    selected = [
        load
        for load in loads
        if str(load.get("load_case", load.get("case", ""))) == load_case
    ]
    if not selected:
        unsupported.append({"kind": "linear_static_load_case_not_found", "load_case": load_case})
    return selected


def _load_vector(
    loads: list[dict[str, Any]],
    node_index: dict[str, int],
    unsupported: list[dict[str, Any]],
) -> np.ndarray:
    vector = np.zeros(len(node_index) * DOF_PER_NODE, dtype=float)
    for load in loads:
        node_id = str(load.get("node", load.get("node_id", "")))
        if node_id not in node_index:
            unsupported.append({"kind": "linear_static_load_node_missing", "node": node_id})
            continue
        components = _six_components(load, unsupported)
        base = DOF_PER_NODE * node_index[node_id]
        for offset, value in enumerate(components):
            vector[base + offset] += value
    return vector


def _six_components(
    load: dict[str, Any],
    unsupported: list[dict[str, Any]],
) -> tuple[float, float, float, float, float, float]:
    raw = load.get("components")
    try:
        if isinstance(raw, list) and len(raw) in {3, 6}:
            values = [float(value) for value in raw]
            if len(values) == 3:
                values.extend([0.0, 0.0, 0.0])
            return tuple(values)  # type: ignore[return-value]
        if isinstance(raw, dict):
            return tuple(
                float(raw.get(label, raw.get(label.lower(), 0.0)))
                for label in LOAD_COMPONENT_LABELS
            )  # type: ignore[return-value]
        return tuple(
            float(load.get(label, load.get(label.lower(), 0.0)))
            for label in LOAD_COMPONENT_LABELS
        )  # type: ignore[return-value]
    except (TypeError, ValueError):
        unsupported.append({"kind": "linear_static_load_components_invalid"})
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _constrained_dofs(
    supports: list[dict[str, Any]],
    node_index: dict[str, int],
    unsupported: list[dict[str, Any]],
) -> list[int]:
    constrained: list[int] = []
    for support in supports:
        node_id = str(support.get("node", support.get("node_id", "")))
        if node_id not in node_index:
            unsupported.append({"kind": "linear_static_support_node_missing", "node": node_id})
            continue
        raw_dofs = support.get("dofs", support.get("restrained_dofs", []))
        if raw_dofs == "all":
            raw_dofs = list(DOF_LABELS)
        if not isinstance(raw_dofs, list):
            unsupported.append(
                {"kind": "linear_static_support_dofs_invalid", "node": node_id}
            )
            continue
        for raw_dof in raw_dofs:
            label = str(raw_dof).upper()
            if label not in DOF_LABELS:
                unsupported.append(
                    {
                        "kind": "linear_static_support_dof_not_supported",
                        "node": node_id,
                        "dof": raw_dof,
                    }
                )
                continue
            constrained.append(DOF_PER_NODE * node_index[node_id] + DOF_LABELS.index(label))
    return constrained


def _positive_float(source: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in source or source.get(key) is None:
            continue
        try:
            value = float(source[key])
        except (TypeError, ValueError):
            return None
        return value if np.isfinite(value) and value > 0.0 else None
    return None
