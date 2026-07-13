"""Deterministic, backend-neutral numerical buffers compiled from ModelIR v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping
import re

import numpy as np

from structural_analysis.model_ir import (
    ModelIRDocument,
    canonicalize_model_ir_v2,
    validate_model_ir_v2,
)

SOLVER_MODEL_BUFFERS_SCHEMA_VERSION = "structural-analysis-solver-model-buffers.v1"
DOF_ORDER = ("UX", "UY", "UZ", "RX", "RY", "RZ")
LOAD_COMPONENT_ORDER = ("FX", "FY", "FZ", "MX", "MY", "MZ")
END_ORDER = ("i", "j")
AXIS_ORDER = ("X", "Y", "Z")
_INT32_MAX = np.iinfo(np.int32).max
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

ELEMENT_TYPE_CODES = {"truss_3d": 1, "frame_3d": 2}
ELEMENT_FORMULATION_CODES = {"linear_truss_3d": 1, "euler_bernoulli_3d": 2}
MATERIAL_LAW_CODES = {"linear_elastic_isotropic": 1}
SECTION_FAMILY_CODES = {"truss_3d": 1, "frame_3d": 2}

_BUFFER_DTYPES = {
    "node_coordinates_m": "<f8",
    "element_connectivity": "<i4",
    "element_type": "|u1",
    "element_formulation_code": "|u1",
    "element_material_index": "<i4",
    "element_section_index": "<i4",
    "material_law_code": "|u1",
    "material_properties_si": "<f8",
    "section_family_code": "|u1",
    "section_properties_si": "<f8",
    "element_local_axis_rotation_rad": "<f8",
    "element_offsets_m": "<f8",
    "element_release_mask": "|u1",
    "support_mask": "|u1",
    "prescribed_values_si": "<f8",
    "load_vector_si": "<f8",
}


@dataclass(frozen=True)
class _BufferContract:
    semantic: str
    units: str
    axis_labels: tuple[str, ...]
    component_labels: tuple[str, ...]
    component_units: tuple[str, ...]
    index_base: int | None = None


_BUFFER_CONTRACTS: dict[str, _BufferContract] = {
    "node_coordinates_m": _BufferContract(
        "canonical global node coordinates", "m", ("node", "axis"), AXIS_ORDER, ("m",) * 3
    ),
    "element_connectivity": _BufferContract(
        "zero-based node indices per element", "index", ("element", "end"), END_ORDER, ("index",) * 2, 0
    ),
    "element_type": _BufferContract(
        "element family code", "enum", ("element",), ("element_type_code",), ("enum",)
    ),
    "element_formulation_code": _BufferContract(
        "element formulation code", "enum", ("element",), ("formulation_code",), ("enum",)
    ),
    "element_material_index": _BufferContract(
        "zero-based material index per element", "index", ("element",), ("material_index",), ("index",), 0
    ),
    "element_section_index": _BufferContract(
        "zero-based section index per element", "index", ("element",), ("section_index",), ("index",), 0
    ),
    "material_law_code": _BufferContract(
        "material constitutive-law code", "enum", ("material",), ("law_code",), ("enum",)
    ),
    "material_properties_si": _BufferContract(
        "material parameter columns", "mixed", ("material", "property"), ("elastic_modulus", "poisson_ratio", "density"), ("Pa", "1", "kg/m3")
    ),
    "section_family_code": _BufferContract(
        "section family code", "enum", ("section",), ("family_code",), ("enum",)
    ),
    "section_properties_si": _BufferContract(
        "section parameter columns", "mixed", ("section", "property"), ("area", "iy", "iz", "torsional_constant", "shear_area_y", "shear_area_z"), ("m2", "m4", "m4", "m4", "m2", "m2")
    ),
    "element_local_axis_rotation_rad": _BufferContract(
        "element roll about local x", "rad", ("element",), ("local_x_roll",), ("rad",)
    ),
    "element_offsets_m": _BufferContract(
        "global rigid-end offsets", "m", ("element", "end", "axis"), tuple(f"{end}.{axis}" for end in END_ORDER for axis in AXIS_ORDER), ("m",) * 6
    ),
    "element_release_mask": _BufferContract(
        "released element-end DOF mask", "bool", ("element", "end", "dof"), tuple(f"{end}.{dof}" for end in END_ORDER for dof in DOF_ORDER), ("bool",) * 12
    ),
    "support_mask": _BufferContract(
        "restrained nodal DOF mask", "bool", ("node", "dof"), DOF_ORDER, ("bool",) * 6
    ),
    "prescribed_values_si": _BufferContract(
        "prescribed nodal translation/rotation", "mixed", ("node", "dof"), DOF_ORDER, ("m", "m", "m", "rad", "rad", "rad")
    ),
    "load_vector_si": _BufferContract(
        "nodal force/moment for selected pattern", "mixed", ("node", "component"), LOAD_COMPONENT_ORDER, ("N", "N", "N", "N*m", "N*m", "N*m")
    ),
}


@dataclass(frozen=True)
class BufferDescriptor:
    name: str
    semantic: str
    units: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    axis_labels: tuple[str, ...]
    component_labels: tuple[str, ...]
    component_units: tuple[str, ...]
    index_base: int | None
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("shape", "axis_labels", "component_labels", "component_units"):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class SolverModelBuffers:
    schema_version: str
    model_ir_content_hash: str
    load_pattern_id: str
    dof_order: tuple[str, ...]
    numeric_buffer_hash: str
    entity_mapping_hash: str
    artifact_hash: str
    descriptors: tuple[BufferDescriptor, ...]
    entity_ids: Mapping[str, tuple[str, ...]]
    code_tables: Mapping[str, Mapping[str, int]]
    _arrays: Mapping[str, np.ndarray]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown SolverModelBuffers array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_ir_content_hash": self.model_ir_content_hash,
            "load_pattern_id": self.load_pattern_id,
            "dof_order": list(self.dof_order),
            "numeric_buffer_hash": self.numeric_buffer_hash,
            "entity_mapping_hash": self.entity_mapping_hash,
            "artifact_hash": self.artifact_hash,
            "index_policy": {"base": 0, "dtype": "<i4", "max_value": int(_INT32_MAX)},
            "axis_orders": {
                "global": list(AXIS_ORDER),
                "element_end": list(END_ORDER),
                "dof": list(DOF_ORDER),
                "load_component": list(LOAD_COMPONENT_ORDER),
            },
            "entity_ids": {key: list(value) for key, value in self.entity_ids.items()},
            "code_tables": {
                key: dict(value) for key, value in self.code_tables.items()
            },
            "buffers": [descriptor.to_dict() for descriptor in self.descriptors],
            "claim_boundary": "backend_neutral_buffer_contract_not_solver_parity",
        }


class SolverModelBufferError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


def pack_solver_model_buffers(
    model: ModelIRDocument | dict[str, Any],
    *,
    load_pattern_id: str,
) -> SolverModelBuffers:
    """Compile one Phase 0 load-pattern view into immutable little-endian buffers."""

    claimed_document_hash = model.content_hash if isinstance(model, ModelIRDocument) else None
    source_payload = model.to_dict() if isinstance(model, ModelIRDocument) else model
    if not isinstance(source_payload, dict):
        raise SolverModelBufferError(
            "model_ir_contract_invalid", "/", "ModelIR root must be an object."
        )

    # Reparse canonical JSON so semantically equal signed zero/integral floats pack identically.
    payload = json.loads(canonicalize_model_ir_v2(source_payload))
    report = validate_model_ir_v2(payload)
    if not report.contract_valid:
        raise SolverModelBufferError(
            "model_ir_contract_invalid",
            "/",
            "; ".join(f"{row.code}@{row.path}" for row in report.issues[:5]),
        )
    if not report.analysis_ready:
        raise SolverModelBufferError(
            "model_ir_not_analysis_ready",
            "/unsupported_features",
            "Blocking ModelIR features prevent solver-buffer compilation.",
        )
    if report.content_hash is None:  # pragma: no cover - validation invariant
        raise SolverModelBufferError(
            "model_ir_content_hash_missing", "/", "Validated ModelIR has no content hash."
        )
    if claimed_document_hash is not None and claimed_document_hash != report.content_hash:
        raise SolverModelBufferError(
            "model_ir_document_hash_mismatch",
            "/",
            "ModelIRDocument content hash does not match its canonical payload.",
        )
    model_hash = report.content_hash

    selected_pattern = _validate_phase0_profile(payload, load_pattern_id)
    _guard_int32_dimensions(payload)

    nodes = payload["nodes"]
    materials = payload["materials"]
    sections = payload["sections"]
    elements = payload["elements"]
    node_index = {str(row["id"]): int(row["index"]) for row in nodes}
    material_index = {str(row["id"]): int(row["index"]) for row in materials}
    section_index = {str(row["id"]): int(row["index"]) for row in sections}

    raw_arrays: dict[str, np.ndarray] = {
        "node_coordinates_m": np.asarray(
            [row["coordinates_m"] for row in nodes], dtype="<f8"
        ),
        "element_connectivity": np.asarray(
            [[node_index[str(node_id)] for node_id in row["node_ids"]] for row in elements],
            dtype="<i4",
        ),
        "element_type": np.asarray(
            [ELEMENT_TYPE_CODES[str(row["type"])] for row in elements], dtype="u1"
        ),
        "element_formulation_code": np.asarray(
            [ELEMENT_FORMULATION_CODES[str(row["formulation"])] for row in elements],
            dtype="u1",
        ),
        "element_material_index": np.asarray(
            [material_index[str(row["material_id"])] for row in elements], dtype="<i4"
        ),
        "element_section_index": np.asarray(
            [section_index[str(row["section_id"])] for row in elements], dtype="<i4"
        ),
        "material_law_code": np.asarray(
            [MATERIAL_LAW_CODES[str(row["law_id"])] for row in materials], dtype="u1"
        ),
        "material_properties_si": np.asarray(
            [
                [
                    row["parameters"]["elastic_modulus_pa"],
                    row["parameters"]["poisson_ratio"],
                    row["parameters"]["density_kg_m3"],
                ]
                for row in materials
            ],
            dtype="<f8",
        ),
        "section_family_code": np.asarray(
            [SECTION_FAMILY_CODES[str(row["family_id"])] for row in sections], dtype="u1"
        ),
        "section_properties_si": np.asarray(
            [_section_properties(row) for row in sections], dtype="<f8"
        ),
        "element_local_axis_rotation_rad": np.asarray(
            [float(row.get("local_axis_rotation_rad", 0.0)) for row in elements],
            dtype="<f8",
        ),
        "element_offsets_m": np.asarray(
            [[row["offsets"]["i_global_m"], row["offsets"]["j_global_m"]] for row in elements],
            dtype="<f8",
        ),
        "element_release_mask": _element_release_mask(elements),
    }
    support_mask, prescribed_values = _constraint_buffers(payload["constraints"], node_index)
    raw_arrays["support_mask"] = support_mask
    raw_arrays["prescribed_values_si"] = prescribed_values
    raw_arrays["load_vector_si"] = _load_buffer(selected_pattern, node_index, len(nodes))

    arrays: dict[str, np.ndarray] = {}
    descriptors: list[BufferDescriptor] = []
    for name in sorted(raw_arrays):
        array = _immutable_c_array(raw_arrays[name])
        arrays[name] = array
        descriptors.append(_descriptor(name, array))

    descriptor_tuple = tuple(descriptors)
    entity_ids = {
        "nodes": tuple(str(row["id"]) for row in nodes),
        "materials": tuple(str(row["id"]) for row in materials),
        "sections": tuple(str(row["id"]) for row in sections),
        "elements": tuple(str(row["id"]) for row in elements),
        "constraints": tuple(str(row["id"]) for row in payload["constraints"]),
        "load_patterns": tuple(str(row["id"]) for row in payload["load_patterns"]),
    }
    code_tables = {
        "element_type": ELEMENT_TYPE_CODES,
        "element_formulation": ELEMENT_FORMULATION_CODES,
        "material_law": MATERIAL_LAW_CODES,
        "section_family": SECTION_FAMILY_CODES,
    }
    numeric_buffer_hash = _numeric_buffer_hash(descriptor_tuple, code_tables)
    entity_mapping_hash = _mapping_hash(entity_ids)
    artifact_hash = _artifact_hash(
        model_ir_content_hash=model_hash,
        load_pattern_id=load_pattern_id,
        numeric_buffer_hash=numeric_buffer_hash,
        entity_mapping_hash=entity_mapping_hash,
    )
    return SolverModelBuffers(
        schema_version=SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
        model_ir_content_hash=model_hash,
        load_pattern_id=load_pattern_id,
        dof_order=DOF_ORDER,
        numeric_buffer_hash=numeric_buffer_hash,
        entity_mapping_hash=entity_mapping_hash,
        artifact_hash=artifact_hash,
        descriptors=descriptor_tuple,
        entity_ids=MappingProxyType(entity_ids),
        code_tables=MappingProxyType(
            {key: MappingProxyType(dict(value)) for key, value in code_tables.items()}
        ),
        _arrays=MappingProxyType(arrays),
    )


def validate_solver_model_buffers(buffers: SolverModelBuffers) -> SolverModelBuffers:
    """Revalidate the backend-neutral v1 ABI without assembling an operator."""

    if not isinstance(buffers, SolverModelBuffers):
        raise SolverModelBufferError(
            "solver_buffer_type_invalid", "/", "Expected SolverModelBuffers."
        )
    if buffers.schema_version != SOLVER_MODEL_BUFFERS_SCHEMA_VERSION:
        raise SolverModelBufferError(
            "solver_buffer_schema_mismatch",
            "/schema_version",
            f"Expected {SOLVER_MODEL_BUFFERS_SCHEMA_VERSION}.",
        )
    if buffers.dof_order != DOF_ORDER:
        raise SolverModelBufferError(
            "solver_buffer_dof_order_mismatch",
            "/dof_order",
            f"Expected {DOF_ORDER}.",
        )
    expected_names = tuple(sorted(_BUFFER_CONTRACTS))
    if (
        not isinstance(buffers.descriptors, tuple)
        or tuple(row.name for row in buffers.descriptors) != expected_names
        or len({row.name for row in buffers.descriptors}) != len(expected_names)
    ):
        raise SolverModelBufferError(
            "solver_buffer_descriptor_set_invalid",
            "/buffers",
            "Buffer descriptors must contain the canonical name-ordered ABI set.",
        )
    try:
        array_names = set(buffers._arrays)
    except (AttributeError, TypeError) as exc:
        raise SolverModelBufferError(
            "solver_buffer_array_set_invalid", "/buffers", "Backing arrays are invalid."
        ) from exc
    if array_names != set(expected_names):
        raise SolverModelBufferError(
            "solver_buffer_array_set_invalid",
            "/buffers",
            "Backing arrays do not match descriptors.",
        )
    arrays: dict[str, np.ndarray] = {}
    for descriptor in buffers.descriptors:
        try:
            array = buffers.array(descriptor.name)
        except KeyError as exc:
            raise SolverModelBufferError(
                "solver_buffer_array_missing",
                f"/buffers/{descriptor.name}",
                "Descriptor has no backing array.",
            ) from exc
        if (
            not isinstance(array, np.ndarray)
            or array.dtype.str != _BUFFER_DTYPES[descriptor.name]
            or not array.flags.c_contiguous
            or array.flags.writeable
        ):
            raise SolverModelBufferError(
                "solver_buffer_storage_invalid",
                f"/buffers/{descriptor.name}",
                "Buffer dtype or immutable C-order storage is invalid.",
            )
        try:
            array.setflags(write=True)
        except ValueError:
            pass
        else:  # pragma: no cover - defensive; restore without mutating bytes
            array.setflags(write=False)
            raise SolverModelBufferError(
                "solver_buffer_storage_invalid",
                f"/buffers/{descriptor.name}",
                "Buffer is not backed by immutable storage.",
            )
        if _descriptor(descriptor.name, array) != descriptor:
            raise SolverModelBufferError(
                "solver_buffer_descriptor_mismatch",
                f"/buffers/{descriptor.name}",
                "Descriptor/hash does not match backing bytes.",
            )
        arrays[descriptor.name] = array

    node_count = arrays["node_coordinates_m"].shape[0]
    element_count = arrays["element_connectivity"].shape[0]
    material_count = arrays["material_properties_si"].shape[0]
    section_count = arrays["section_properties_si"].shape[0]
    if min(node_count, element_count, material_count, section_count) <= 0:
        raise SolverModelBufferError(
            "solver_buffer_shape_invalid",
            "/buffers",
            "Node, element, material, and section counts must be positive.",
        )
    expected_shapes = {
        "node_coordinates_m": (node_count, 3),
        "element_connectivity": (element_count, 2),
        "element_type": (element_count,),
        "element_formulation_code": (element_count,),
        "element_material_index": (element_count,),
        "element_section_index": (element_count,),
        "material_law_code": (material_count,),
        "material_properties_si": (material_count, 3),
        "section_family_code": (section_count,),
        "section_properties_si": (section_count, 6),
        "element_local_axis_rotation_rad": (element_count,),
        "element_offsets_m": (element_count, 2, 3),
        "element_release_mask": (element_count, 2, len(DOF_ORDER)),
        "support_mask": (node_count, len(DOF_ORDER)),
        "prescribed_values_si": (node_count, len(DOF_ORDER)),
        "load_vector_si": (node_count, len(DOF_ORDER)),
    }
    for name, shape in expected_shapes.items():
        if arrays[name].shape != shape:
            raise SolverModelBufferError(
                "solver_buffer_shape_invalid",
                f"/buffers/{name}",
                f"Expected shape {shape}, got {arrays[name].shape}.",
            )
    for name, array in arrays.items():
        if array.dtype.kind == "f" and not np.all(np.isfinite(array)):
            raise SolverModelBufferError(
                "solver_buffer_non_finite",
                f"/buffers/{name}",
                "Floating-point buffer contains NaN or Infinity.",
            )
    for name in ("element_release_mask", "support_mask"):
        if np.any((arrays[name] != 0) & (arrays[name] != 1)):
            raise SolverModelBufferError(
                "solver_buffer_mask_invalid",
                f"/buffers/{name}",
                "Mask buffer must contain only 0 or 1.",
            )
    index_bounds = (
        ("element_connectivity", node_count),
        ("element_material_index", material_count),
        ("element_section_index", section_count),
    )
    for name, upper_bound in index_bounds:
        if np.any(arrays[name] < 0) or np.any(arrays[name] >= upper_bound):
            raise SolverModelBufferError(
                "solver_buffer_index_out_of_range",
                f"/buffers/{name}",
                f"Indices must be within [0, {upper_bound}).",
            )
    if np.any(arrays["element_connectivity"][:, 0] == arrays["element_connectivity"][:, 1]):
        raise SolverModelBufferError(
            "solver_buffer_connectivity_invalid",
            "/buffers/element_connectivity",
            "Every element must connect two distinct nodes.",
        )

    expected_tables = {
        "element_type": ELEMENT_TYPE_CODES,
        "element_formulation": ELEMENT_FORMULATION_CODES,
        "material_law": MATERIAL_LAW_CODES,
        "section_family": SECTION_FAMILY_CODES,
    }
    try:
        actual_tables = {key: dict(value) for key, value in buffers.code_tables.items()}
    except (AttributeError, TypeError, ValueError) as exc:
        raise SolverModelBufferError(
            "solver_buffer_code_tables_invalid",
            "/code_tables",
            "Code tables must be mappings.",
        ) from exc
    if actual_tables != expected_tables:
        raise SolverModelBufferError(
            "solver_buffer_code_tables_invalid",
            "/code_tables",
            "Code tables do not match the v1 ABI.",
        )
    code_arrays = {
        "element_type": ELEMENT_TYPE_CODES,
        "element_formulation_code": ELEMENT_FORMULATION_CODES,
        "material_law_code": MATERIAL_LAW_CODES,
        "section_family_code": SECTION_FAMILY_CODES,
    }
    for name, table in code_arrays.items():
        if not set(int(value) for value in np.unique(arrays[name])).issubset(
            set(table.values())
        ):
            raise SolverModelBufferError(
                "solver_buffer_code_invalid",
                f"/buffers/{name}",
                "Buffer contains a code outside the v1 table.",
            )
    if buffers.numeric_buffer_hash != _numeric_buffer_hash(
        buffers.descriptors, buffers.code_tables
    ):
        raise SolverModelBufferError(
            "solver_buffer_numeric_hash_mismatch",
            "/numeric_buffer_hash",
            "Numeric buffer hash is stale.",
        )

    required_families = {
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
    }
    if set(buffers.entity_ids) != required_families:
        raise SolverModelBufferError(
            "solver_buffer_entity_mapping_invalid",
            "/entity_ids",
            "Entity mapping families are incomplete.",
        )
    for family, ids in buffers.entity_ids.items():
        if (
            not isinstance(ids, tuple)
            or any(not isinstance(value, str) or not value for value in ids)
            or len(ids) != len(set(ids))
        ):
            raise SolverModelBufferError(
                "solver_buffer_entity_mapping_invalid",
                f"/entity_ids/{family}",
                "Entity IDs must be a unique tuple of non-empty strings.",
            )
    expected_counts = {
        "nodes": node_count,
        "materials": material_count,
        "sections": section_count,
        "elements": element_count,
    }
    if any(len(buffers.entity_ids[name]) != count for name, count in expected_counts.items()):
        raise SolverModelBufferError(
            "solver_buffer_entity_mapping_invalid",
            "/entity_ids",
            "Entity mapping counts do not match numerical buffers.",
        )
    if buffers.load_pattern_id not in buffers.entity_ids["load_patterns"]:
        raise SolverModelBufferError(
            "solver_buffer_load_pattern_invalid",
            "/load_pattern_id",
            "Selected load pattern is absent from the entity mapping.",
        )
    if (
        not isinstance(buffers.model_ir_content_hash, str)
        or _SHA256_PATTERN.fullmatch(buffers.model_ir_content_hash) is None
    ):
        raise SolverModelBufferError(
            "solver_buffer_model_hash_invalid",
            "/model_ir_content_hash",
            "ModelIR binding must use sha256:<64 lowercase hex>.",
        )
    if buffers.entity_mapping_hash != _mapping_hash(buffers.entity_ids):
        raise SolverModelBufferError(
            "solver_buffer_entity_hash_mismatch",
            "/entity_mapping_hash",
            "Entity mapping hash is stale.",
        )
    if buffers.artifact_hash != _artifact_hash(
        model_ir_content_hash=buffers.model_ir_content_hash,
        load_pattern_id=buffers.load_pattern_id,
        numeric_buffer_hash=buffers.numeric_buffer_hash,
        entity_mapping_hash=buffers.entity_mapping_hash,
    ):
        raise SolverModelBufferError(
            "solver_buffer_artifact_hash_mismatch",
            "/artifact_hash",
            "Aggregate solver-buffer hash is stale.",
        )
    return buffers


def _validate_phase0_profile(
    payload: dict[str, Any], load_pattern_id: str
) -> dict[str, Any]:
    load_patterns = {str(row["id"]): row for row in payload["load_patterns"]}
    if load_pattern_id not in load_patterns:
        raise SolverModelBufferError(
            "load_pattern_not_found", "/load_patterns", f"Unknown load pattern: {load_pattern_id}"
        )
    for field in ("load_combinations", "time_functions", "construction_stages"):
        if payload[field]:
            raise SolverModelBufferError(
                "phase0_profile_feature_not_supported",
                f"/{field}",
                f"Phase 0 buffer profile requires {field} to be empty.",
            )
    selected = load_patterns[load_pattern_id]
    if any(float(value) != 0.0 for value in selected["self_weight"]):
        raise SolverModelBufferError(
            "phase0_profile_feature_not_supported",
            f"/load_patterns/{selected['index']}/self_weight",
            "Phase 0 buffer profile requires explicit nodal loads and zero self-weight.",
        )
    for index, element in enumerate(payload["elements"]):
        if element.get("releases") and any(element["releases"][end] for end in END_ORDER):
            raise SolverModelBufferError(
                "phase0_profile_feature_not_supported",
                f"/elements/{index}/releases",
                "Phase 0 CPU-compatible profile requires empty element releases.",
            )
        if any(
            float(value) != 0.0
            for end in END_ORDER
            for value in element["offsets"][f"{end}_global_m"]
        ):
            raise SolverModelBufferError(
                "phase0_profile_feature_not_supported",
                f"/elements/{index}/offsets",
                "Phase 0 CPU-compatible profile requires zero element offsets.",
            )
    for index, constraint in enumerate(payload["constraints"]):
        if any(float(value) != 0.0 for value in constraint["prescribed_values_si"].values()):
            raise SolverModelBufferError(
                "phase0_profile_feature_not_supported",
                f"/constraints/{index}/prescribed_values_si",
                "Phase 0 CPU-compatible profile requires zero prescribed values.",
            )
    return selected


def _guard_int32_dimensions(payload: dict[str, Any]) -> None:
    counts = {
        "nodes": len(payload["nodes"]),
        "elements": len(payload["elements"]),
        "materials": len(payload["materials"]),
        "sections": len(payload["sections"]),
        "global_dofs": len(payload["nodes"]) * len(DOF_ORDER),
    }
    for name, count in counts.items():
        if count > _INT32_MAX:
            raise SolverModelBufferError(
                "int32_index_capacity_exceeded",
                f"/{name}",
                f"{name} count {count} exceeds int32 capacity {_INT32_MAX}.",
            )


def _section_properties(section: dict[str, Any]) -> list[float]:
    parameters = section["parameters"]
    if section["family_id"] == "truss_3d":
        return [float(parameters["area_m2"]), 0.0, 0.0, 0.0, 0.0, 0.0]
    return [
        float(parameters["area_m2"]),
        float(parameters["iy_m4"]),
        float(parameters["iz_m4"]),
        float(parameters["torsional_constant_m4"]),
        float(parameters["shear_area_y_m2"]),
        float(parameters["shear_area_z_m2"]),
    ]


def _element_release_mask(elements: list[dict[str, Any]]) -> np.ndarray:
    mask = np.zeros((len(elements), len(END_ORDER), len(DOF_ORDER)), dtype="u1")
    for element_index, element in enumerate(elements):
        releases = element.get("releases", {"i": [], "j": []})
        for end_index, end in enumerate(END_ORDER):
            for dof in releases.get(end, []):
                mask[element_index, end_index, DOF_ORDER.index(str(dof))] = 1
    return mask


def _constraint_buffers(
    constraints: list[dict[str, Any]], node_index: dict[str, int]
) -> tuple[np.ndarray, np.ndarray]:
    support_mask = np.zeros((len(node_index), len(DOF_ORDER)), dtype="u1")
    prescribed_values = np.zeros((len(node_index), len(DOF_ORDER)), dtype="<f8")
    for constraint in constraints:
        node = node_index[str(constraint["node_id"])]
        for dof in constraint["dofs"]:
            component = DOF_ORDER.index(str(dof))
            support_mask[node, component] = 1
            prescribed_values[node, component] = float(
                constraint["prescribed_values_si"].get(dof, 0.0)
            )
    return support_mask, prescribed_values


def _load_buffer(
    load_pattern: dict[str, Any], node_index: dict[str, int], node_count: int
) -> np.ndarray:
    vector = np.zeros((node_count, len(DOF_ORDER)), dtype="<f8")
    for load in load_pattern["nodal_loads"]:
        node = node_index[str(load["node_id"])]
        for component, key in enumerate(LOAD_COMPONENT_ORDER):
            vector[node, component] += float(load["components_si"][key])
    return vector


def _immutable_c_array(value: np.ndarray) -> np.ndarray:
    contiguous = np.ascontiguousarray(value)
    immutable_bytes = contiguous.tobytes(order="C")
    return np.frombuffer(immutable_bytes, dtype=contiguous.dtype).reshape(contiguous.shape)


def _descriptor(name: str, array: np.ndarray) -> BufferDescriptor:
    contract = _BUFFER_CONTRACTS[name]
    metadata = {
        "name": name,
        "semantic": contract.semantic,
        "units": contract.units,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "axis_labels": list(contract.axis_labels),
        "component_labels": list(contract.component_labels),
        "component_units": list(contract.component_units),
        "index_base": contract.index_base,
        "byte_length": int(array.nbytes),
    }
    raw = memoryview(array).cast("B")
    data_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    canonical_metadata = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    digest = hashlib.sha256()
    digest.update(canonical_metadata)
    digest.update(b"\0")
    digest.update(raw)
    return BufferDescriptor(
        name=name,
        semantic=contract.semantic,
        units=contract.units,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        axis_labels=contract.axis_labels,
        component_labels=contract.component_labels,
        component_units=contract.component_units,
        index_base=contract.index_base,
        byte_length=int(array.nbytes),
        data_hash=data_hash,
        content_hash=f"sha256:{digest.hexdigest()}",
    )


def _numeric_buffer_hash(
    descriptors: tuple[BufferDescriptor, ...], code_tables: Mapping[str, Mapping[str, int]]
) -> str:
    payload = {
        "schema_version": SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
        "dof_order": list(DOF_ORDER),
        "axis_order": list(AXIS_ORDER),
        "end_order": list(END_ORDER),
        "load_component_order": list(LOAD_COMPONENT_ORDER),
        "code_tables": {key: dict(value) for key, value in sorted(code_tables.items())},
        "buffers": [descriptor.to_dict() for descriptor in descriptors],
    }
    return _json_hash(payload)


def _mapping_hash(entity_ids: Mapping[str, tuple[str, ...]]) -> str:
    return _json_hash({key: list(value) for key, value in sorted(entity_ids.items())})


def _artifact_hash(
    *,
    model_ir_content_hash: str,
    load_pattern_id: str,
    numeric_buffer_hash: str,
    entity_mapping_hash: str,
) -> str:
    return _json_hash(
        {
            "schema_version": SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
            "model_ir_content_hash": model_ir_content_hash,
            "load_pattern_id": load_pattern_id,
            "numeric_buffer_hash": numeric_buffer_hash,
            "entity_mapping_hash": entity_mapping_hash,
        }
    )


def _json_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
