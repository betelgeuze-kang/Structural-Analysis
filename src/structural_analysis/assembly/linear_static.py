"""Global assembly for the narrow axial linear-static solver slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from structural_analysis.elements.axial import axial_element_properties, axial_global_stiffness
from structural_analysis.model.schema import CanonicalModel

DOF_LABELS = ("UX", "UY", "UZ")
STIFFNESS_STORAGE = "dense_numpy"
SPARSE_STIFFNESS_STORAGE = "scipy_sparse_csr"


@dataclass(frozen=True)
class LinearStaticAssembly:
    stiffness: np.ndarray | csr_matrix
    loads: np.ndarray
    constrained_dofs: tuple[int, ...]
    node_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    stiffness_storage: str = STIFFNESS_STORAGE


def assemble_linear_static(model: CanonicalModel) -> tuple[LinearStaticAssembly | None, list[dict[str, Any]]]:
    unsupported: list[dict[str, Any]] = []
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
    dof_count = len(node_ids) * len(DOF_LABELS)
    stiffness = np.zeros((dof_count, dof_count), dtype=float)

    for element in model.elements:
        _assemble_element(
            element=element,
            node_index=node_index,
            coordinates=coordinates,
            materials=materials,
            sections=sections,
            stiffness=stiffness,
            unsupported=unsupported,
        )

    loads = _load_vector(model.loads, node_index, unsupported)
    constrained_dofs = _constrained_dofs(model.supports, node_index, unsupported)
    if not model.loads:
        unsupported.append({"kind": "linear_static_loads_missing"})
    if not model.supports:
        unsupported.append({"kind": "linear_static_supports_missing"})
    if not model.elements:
        unsupported.append({"kind": "linear_static_elements_missing"})

    if unsupported:
        return None, unsupported
    return (
        LinearStaticAssembly(
            stiffness=stiffness,
            loads=loads,
            constrained_dofs=tuple(sorted(set(constrained_dofs))),
            node_ids=node_ids,
            warnings=(),
        ),
        [],
    )


def assemble_linear_static_sparse(
    model: CanonicalModel,
) -> tuple[LinearStaticAssembly | None, list[dict[str, Any]]]:
    """Assemble global stiffness in deterministic scipy CSR storage for the axial preview."""
    unsupported: list[dict[str, Any]] = []
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
    dof_count = len(node_ids) * len(DOF_LABELS)
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []

    for element in model.elements:
        _assemble_element_sparse(
            element=element,
            node_index=node_index,
            coordinates=coordinates,
            materials=materials,
            sections=sections,
            rows=rows,
            cols=cols,
            data=data,
            unsupported=unsupported,
        )

    loads = _load_vector(model.loads, node_index, unsupported)
    constrained_dofs = _constrained_dofs(model.supports, node_index, unsupported)
    if not model.loads:
        unsupported.append({"kind": "linear_static_loads_missing"})
    if not model.supports:
        unsupported.append({"kind": "linear_static_supports_missing"})
    if not model.elements:
        unsupported.append({"kind": "linear_static_elements_missing"})

    if unsupported:
        return None, unsupported

    stiffness = coo_matrix((data, (rows, cols)), shape=(dof_count, dof_count)).tocsr()
    return (
        LinearStaticAssembly(
            stiffness=stiffness,
            loads=loads,
            constrained_dofs=tuple(sorted(set(constrained_dofs))),
            node_ids=node_ids,
            warnings=(),
            stiffness_storage=SPARSE_STIFFNESS_STORAGE,
        ),
        [],
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
            unsupported.append({"kind": "linear_static_node_coordinates_invalid", "node": node_id})
            continue
        try:
            coordinates[node_id] = (float(raw[0]), float(raw[1]), float(raw[2]))
        except (TypeError, ValueError):
            unsupported.append({"kind": "linear_static_node_coordinates_invalid", "node": node_id})
    return coordinates


def _assemble_element(
    *,
    element: dict[str, Any],
    node_index: dict[str, int],
    coordinates: dict[str, tuple[float, float, float]],
    materials: dict[str, dict[str, Any]],
    sections: dict[str, dict[str, Any]],
    stiffness: np.ndarray,
    unsupported: list[dict[str, Any]],
) -> None:
    element_id = str(element.get("id", ""))
    element_type = str(element.get("type", "")).lower()
    if element_type not in {"truss", "axial"}:
        unsupported.append(
            {
                "kind": "linear_static_element_not_supported",
                "element": element_id,
                "element_type": element.get("type", ""),
            }
        )
        return
    raw_nodes = element.get("nodes")
    if not isinstance(raw_nodes, list) or len(raw_nodes) != 2:
        unsupported.append({"kind": "linear_static_element_connectivity_invalid", "element": element_id})
        return
    node_pair = (str(raw_nodes[0]), str(raw_nodes[1]))
    if any(node_id not in node_index or node_id not in coordinates for node_id in node_pair):
        unsupported.append({"kind": "linear_static_element_node_missing", "element": element_id})
        return

    material = materials.get(str(element.get("material", "")))
    section = sections.get(str(element.get("section", "")))
    elastic_modulus = _positive_float(material, "elastic_modulus")
    area = _positive_float(section, "area")
    if elastic_modulus is None:
        unsupported.append({"kind": "linear_static_material_elastic_modulus_missing", "element": element_id})
        return
    if area is None:
        unsupported.append({"kind": "linear_static_section_area_missing", "element": element_id})
        return

    try:
        properties = axial_element_properties(
            element_id=element_id,
            node_ids=node_pair,
            start_coordinates=coordinates[node_pair[0]],
            end_coordinates=coordinates[node_pair[1]],
            elastic_modulus=elastic_modulus,
            area=area,
        )
    except ValueError as exc:
        unsupported.append({"kind": "linear_static_element_invalid", "element": element_id, "detail": str(exc)})
        return

    element_stiffness = axial_global_stiffness(properties)
    dofs = [3 * node_index[node_id] + offset for node_id in node_pair for offset in range(3)]
    for row_index, global_row in enumerate(dofs):
        for col_index, global_col in enumerate(dofs):
            stiffness[global_row, global_col] += element_stiffness[row_index, col_index]


def _assemble_element_sparse(
    *,
    element: dict[str, Any],
    node_index: dict[str, int],
    coordinates: dict[str, tuple[float, float, float]],
    materials: dict[str, dict[str, Any]],
    sections: dict[str, dict[str, Any]],
    rows: list[int],
    cols: list[int],
    data: list[float],
    unsupported: list[dict[str, Any]],
) -> None:
    element_id = str(element.get("id", ""))
    element_type = str(element.get("type", "")).lower()
    if element_type not in {"truss", "axial"}:
        unsupported.append(
            {
                "kind": "linear_static_element_not_supported",
                "element": element_id,
                "element_type": element.get("type", ""),
            }
        )
        return
    raw_nodes = element.get("nodes")
    if not isinstance(raw_nodes, list) or len(raw_nodes) != 2:
        unsupported.append({"kind": "linear_static_element_connectivity_invalid", "element": element_id})
        return
    node_pair = (str(raw_nodes[0]), str(raw_nodes[1]))
    if any(node_id not in node_index or node_id not in coordinates for node_id in node_pair):
        unsupported.append({"kind": "linear_static_element_node_missing", "element": element_id})
        return

    material = materials.get(str(element.get("material", "")))
    section = sections.get(str(element.get("section", "")))
    elastic_modulus = _positive_float(material, "elastic_modulus")
    area = _positive_float(section, "area")
    if elastic_modulus is None:
        unsupported.append({"kind": "linear_static_material_elastic_modulus_missing", "element": element_id})
        return
    if area is None:
        unsupported.append({"kind": "linear_static_section_area_missing", "element": element_id})
        return

    try:
        properties = axial_element_properties(
            element_id=element_id,
            node_ids=node_pair,
            start_coordinates=coordinates[node_pair[0]],
            end_coordinates=coordinates[node_pair[1]],
            elastic_modulus=elastic_modulus,
            area=area,
        )
    except ValueError as exc:
        unsupported.append({"kind": "linear_static_element_invalid", "element": element_id, "detail": str(exc)})
        return

    element_stiffness = axial_global_stiffness(properties)
    dofs = [3 * node_index[node_id] + offset for node_id in node_pair for offset in range(3)]
    for row_index, global_row in enumerate(dofs):
        for col_index, global_col in enumerate(dofs):
            value = float(element_stiffness[row_index, col_index])
            if value != 0.0:
                rows.append(global_row)
                cols.append(global_col)
                data.append(value)


def _positive_float(source: dict[str, Any] | None, key: str) -> float | None:
    if not source:
        return None
    try:
        value = float(source.get(key))
    except (TypeError, ValueError):
        return None
    return value if value > 0.0 else None


def _load_vector(
    loads: list[dict[str, Any]],
    node_index: dict[str, int],
    unsupported: list[dict[str, Any]],
) -> np.ndarray:
    vector = np.zeros(len(node_index) * len(DOF_LABELS), dtype=float)
    for load in loads:
        node_id = str(load.get("node", load.get("node_id", "")))
        if node_id not in node_index:
            unsupported.append({"kind": "linear_static_load_node_missing", "node": node_id})
            continue
        components = _force_components(load, unsupported)
        base = 3 * node_index[node_id]
        for offset, value in enumerate(components):
            vector[base + offset] += value
    return vector


def _force_components(
    load: dict[str, Any],
    unsupported: list[dict[str, Any]],
) -> tuple[float, float, float]:
    raw = load.get("components")
    if isinstance(raw, list) and len(raw) == 3:
        try:
            return (float(raw[0]), float(raw[1]), float(raw[2]))
        except (TypeError, ValueError):
            pass
    if isinstance(raw, dict):
        try:
            return (
                float(raw.get("FX", raw.get("fx", 0.0))),
                float(raw.get("FY", raw.get("fy", 0.0))),
                float(raw.get("FZ", raw.get("fz", 0.0))),
            )
        except (TypeError, ValueError):
            pass
    try:
        return (
            float(load.get("fx", load.get("FX", 0.0))),
            float(load.get("fy", load.get("FY", 0.0))),
            float(load.get("fz", load.get("FZ", 0.0))),
        )
    except (TypeError, ValueError):
        unsupported.append({"kind": "linear_static_load_components_invalid"})
        return (0.0, 0.0, 0.0)


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
            unsupported.append({"kind": "linear_static_support_dofs_invalid", "node": node_id})
            continue
        for raw_dof in raw_dofs:
            label = str(raw_dof).upper()
            if label not in DOF_LABELS:
                unsupported.append({"kind": "linear_static_support_dof_not_supported", "node": node_id, "dof": raw_dof})
                continue
            constrained.append(3 * node_index[node_id] + DOF_LABELS.index(label))
    return constrained
