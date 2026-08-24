"""Strict schema and engineering-invariant validation for ModelIR v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, validators
import numpy as np

MODEL_IR_V2_SCHEMA_VERSION = "structural-analysis-model-ir.v2"
_ZERO_LENGTH_TOLERANCE_M = 1.0e-12
_BOUNDED_FRAME3D_MAX_ABS_COORDINATE_M = 1.0e9
_BOUNDED_FRAME3D_MODULUS_PA_RANGE = (1.0e-3, 1.0e18)
_BOUNDED_FRAME3D_YIELD_STRESS_PA_RANGE = (1.0e-6, 1.0e18)
_BOUNDED_FRAME3D_POSITIVE_HARDENING_PA_RANGE = (1.0e-12, 1.0e18)
_BOUNDED_FRAME3D_AREA_M2_RANGE = (1.0e-18, 1.0e12)
_BOUNDED_FRAME3D_INERTIA_M4_RANGE = (1.0e-36, 1.0e36)
_BOUNDED_FRAME3D_MAX_ABS_LOAD_SI = 1.0e18
_BOUNDED_FRAME3D_MAX_ABS_ROLL_RAD = 1.0e6

_EXPECTED_UNIT_SCALES: dict[str, dict[str, float]] = {
    "length": {"m": 1.0, "mm": 1.0e-3, "cm": 1.0e-2, "ft": 0.3048, "in": 0.0254},
    "force": {
        "N": 1.0,
        "kN": 1.0e3,
        "MN": 1.0e6,
        "lbf": 4.4482216152605,
        "kip": 4448.2216152605,
    },
    "mass": {"kg": 1.0, "tonne": 1.0e3, "slug": 14.593902937206},
    "time": {"s": 1.0},
    "rotation": {"rad": 1.0, "deg": math.pi / 180.0},
}
_SCALE_KEYS = {
    "length": "length_to_m",
    "force": "force_to_n",
    "mass": "mass_to_kg",
    "time": "time_to_s",
    "rotation": "rotation_to_rad",
}
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)


@dataclass(frozen=True, order=True)
class ModelIRValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ModelIRValidationReport:
    schema_version: str
    schema_valid: bool
    semantics_valid: bool
    analysis_ready: bool
    issues: tuple[ModelIRValidationIssue, ...]
    blocking_feature_ids: tuple[str, ...]
    derived_blocking_feature_ids: tuple[str, ...]
    content_hash: str | None
    semantic_hash: str | None
    provenance_hash: str | None

    @property
    def contract_valid(self) -> bool:
        return self.schema_valid and self.semantics_valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "schema_valid": self.schema_valid,
            "semantics_valid": self.semantics_valid,
            "contract_valid": self.contract_valid,
            "analysis_ready": self.analysis_ready,
            "issues": [asdict(issue) for issue in self.issues],
            "blocking_feature_ids": list(self.blocking_feature_ids),
            "derived_blocking_feature_ids": list(self.derived_blocking_feature_ids),
            "content_hash": self.content_hash,
            "semantic_hash": self.semantic_hash,
            "provenance_hash": self.provenance_hash,
            "claim_boundary": "model_ir_contract_validation_not_solver_readiness",
        }


class ModelIRValidationError(ValueError):
    """Raised when a ModelIR document fails contract or readiness validation."""

    def __init__(self, report: ModelIRValidationReport) -> None:
        self.report = report
        summary = "; ".join(
            f"{issue.code}@{issue.path}: {issue.message}" for issue in report.issues[:5]
        )
        if len(report.issues) > 5:
            summary += f"; ... {len(report.issues) - 5} more issue(s)"
        if not summary and report.blocking_feature_ids:
            summary = "blocking unsupported features: " + ", ".join(
                report.blocking_feature_ids
            )
        super().__init__(summary or "ModelIR v2 validation failed.")


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object repeats a key that would otherwise be overwritten."""


def load_json_object_strict(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle, object_pairs_hook=_object_without_duplicate_keys)
    if not isinstance(payload, dict):
        raise ValueError("ModelIR v2 root must be a JSON object.")
    return payload


def load_model_ir_v2_schema() -> dict[str, Any]:
    schema_resource = resources.files("structural_analysis.schemas").joinpath(
        "model_ir_v2.schema.json"
    )
    with schema_resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):  # pragma: no cover - packaged schema invariant
        raise TypeError("Packaged ModelIR v2 schema must be a JSON object.")
    Draft202012Validator.check_schema(schema)
    return schema


def canonicalize_model_ir_v2(payload: dict[str, Any]) -> str:
    """Return deterministic UTF-8 JSON after finite-number and signed-zero normalization."""

    normalized = _normalize_value(payload, path="/")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def model_ir_v2_content_hash(payload: dict[str, Any]) -> str:
    canonical = canonicalize_model_ir_v2(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def model_ir_v2_semantic_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Project normalized physical meaning without source/provenance metadata."""

    keys = (
        "schema_version",
        "capability_profile",
        "units",
        "coordinate_system",
        "dof_components",
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
    )
    return _without_source_metadata({key: payload[key] for key in keys})


def model_ir_v2_semantic_hash(payload: dict[str, Any]) -> str:
    return model_ir_v2_content_hash(model_ir_v2_semantic_projection(payload))


def model_ir_v2_provenance_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Project document/source identity without normalized physical values."""

    source_families = (
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
    )
    return {
        "schema_version": payload["schema_version"],
        "capability_profile": payload["capability_profile"],
        "model_id": payload["model_id"],
        "provenance": payload["provenance"],
        "entity_source_metadata": {
            family: [_source_metadata(row) for row in payload[family]]
            for family in source_families
        },
        "roundtrip_map": payload["roundtrip_map"],
        "unsupported_features": payload["unsupported_features"],
        "extensions": payload["extensions"],
    }


def model_ir_v2_provenance_hash(payload: dict[str, Any]) -> str:
    return model_ir_v2_content_hash(model_ir_v2_provenance_projection(payload))


def derive_model_ir_v2_blocking_feature_ids(
    payload: dict[str, Any],
) -> tuple[str, ...]:
    """Derive fail-closed blockers from unsupported roundtrip content."""

    derived: set[str] = set()
    for row in payload["roundtrip_map"]:
        if row["mapping_status"] != "unsupported":
            continue
        identity = {
            "source_entity_id": row["source_entity_id"],
            "entity_kind": row["entity_kind"],
            "model_ir_entity_id": row["model_ir_entity_id"],
            "mapping_status": row["mapping_status"],
        }
        digest = model_ir_v2_content_hash(identity).removeprefix("sha256:")[:16]
        derived.add(f"derived.roundtrip.unsupported.{digest}")
    return tuple(sorted(derived))


def validate_model_ir_v2(payload: Any) -> ModelIRValidationReport:
    schema = load_model_ir_v2_schema()
    validator = _StrictDraft202012Validator(schema)
    schema_issues = tuple(
        sorted(
            (
                ModelIRValidationIssue(
                    code="schema_validation_error",
                    path=_json_pointer(error.absolute_path),
                    message=error.message,
                )
                for error in validator.iter_errors(payload)
            ),
            key=lambda issue: (issue.path, issue.message),
        )
    )

    schema_version = (
        str(payload.get("schema_version", "")) if isinstance(payload, dict) else ""
    )
    if schema_issues or not isinstance(payload, dict):
        return ModelIRValidationReport(
            schema_version=schema_version,
            schema_valid=False,
            semantics_valid=False,
            analysis_ready=False,
            issues=schema_issues,
            blocking_feature_ids=(),
            derived_blocking_feature_ids=(),
            content_hash=None,
            semantic_hash=None,
            provenance_hash=None,
        )

    semantic_issues = tuple(sorted(_semantic_issues(payload)))
    declared_blocking_feature_ids = tuple(
        sorted(
            str(row["feature_id"])
            for row in payload["unsupported_features"]
            if bool(row["blocking"])
        )
    )
    derived_blocking_feature_ids = derive_model_ir_v2_blocking_feature_ids(payload)
    blocking_feature_ids = tuple(
        sorted({*declared_blocking_feature_ids, *derived_blocking_feature_ids})
    )
    content_hash: str | None
    semantic_hash: str | None
    provenance_hash: str | None
    try:
        content_hash = model_ir_v2_content_hash(payload)
        semantic_hash = model_ir_v2_semantic_hash(payload)
        provenance_hash = model_ir_v2_provenance_hash(payload)
    except ValueError as exc:
        semantic_issues = tuple(
            sorted(
                (
                    *semantic_issues,
                    ModelIRValidationIssue("non_finite_number", "/", str(exc)),
                )
            )
        )
        content_hash = None
        semantic_hash = None
        provenance_hash = None

    semantics_valid = not semantic_issues
    return ModelIRValidationReport(
        schema_version=schema_version,
        schema_valid=True,
        semantics_valid=semantics_valid,
        analysis_ready=semantics_valid and not blocking_feature_ids,
        issues=semantic_issues,
        blocking_feature_ids=blocking_feature_ids,
        derived_blocking_feature_ids=derived_blocking_feature_ids,
        content_hash=content_hash,
        semantic_hash=semantic_hash,
        provenance_hash=provenance_hash,
    )


def _semantic_issues(payload: dict[str, Any]) -> Iterable[ModelIRValidationIssue]:
    finite_issues = tuple(_finite_number_issues(payload))
    yield from finite_issues
    if finite_issues:
        return
    yield from _unit_scale_issues(payload)
    bounded_planar = payload["capability_profile"] in {
        "bounded_planar_frame_alpha",
        "planar_frame_verified_alpha.v1",
    }
    bounded_frame3d_direct_control = (
        payload["capability_profile"] == "bounded_frame3d_direct_displacement_control"
    )

    families = (
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
    )
    for family in families:
        yield from _indexed_family_issues(payload[family], family)

    node_ids = {str(row["id"]) for row in payload["nodes"]}
    material_by_id = {str(row["id"]): row for row in payload["materials"]}
    material_ids = set(material_by_id)
    section_by_id = {str(row["id"]): row for row in payload["sections"]}
    element_ids = {str(row["id"]) for row in payload["elements"]}
    constraint_ids = {str(row["id"]) for row in payload["constraints"]}
    load_pattern_ids = {str(row["id"]) for row in payload["load_patterns"]}
    load_combination_ids = {str(row["id"]) for row in payload["load_combinations"]}
    time_function_ids = {str(row["id"]) for row in payload["time_functions"]}
    construction_stage_ids = {str(row["id"]) for row in payload["construction_stages"]}

    node_coordinates = {
        str(row["id"]): tuple(float(value) for value in row["coordinates_m"])
        for row in payload["nodes"]
    }
    for index, element in enumerate(payload["elements"]):
        base = f"/elements/{index}"
        node_pair = tuple(str(value) for value in element["node_ids"])
        if node_pair[0] == node_pair[1]:
            yield ModelIRValidationIssue(
                "element_nodes_not_distinct",
                f"{base}/node_ids",
                "Element end nodes must differ.",
            )
        for node_id in node_pair:
            if node_id not in node_ids:
                yield _missing_reference(f"{base}/node_ids", "node", node_id)
        section_id = str(element["section_id"])
        section = section_by_id.get(section_id)
        if section is None:
            yield _missing_reference(f"{base}/section_id", "section", section_id)
        else:
            expected_family = (
                "rectangular_rc_fiber_2d"
                if bounded_planar
                else ("frame_3d" if element["type"] == "frame_3d" else "truss_3d")
            )
            if section["family_id"] != expected_family:
                yield ModelIRValidationIssue(
                    "element_section_family_mismatch",
                    f"{base}/section_id",
                    f"Element type {element['type']} requires section family {expected_family}.",
                )
        if not bounded_planar:
            material_id = str(element["material_id"])
            if material_id not in material_ids:
                yield _missing_reference(f"{base}/material_id", "material", material_id)
        if all(node_id in node_coordinates for node_id in node_pair):
            offsets = element["offsets"]
            start = tuple(
                node_coordinates[node_pair[0]][axis]
                + float(offsets["i_global_m"][axis])
                for axis in range(3)
            )
            end = tuple(
                node_coordinates[node_pair[1]][axis]
                + float(offsets["j_global_m"][axis])
                for axis in range(3)
            )
            length = math.dist(start, end)
            if not math.isfinite(length):
                yield ModelIRValidationIssue(
                    "element_effective_length_not_finite",
                    base,
                    "Element length after offsets must remain finite.",
                )
            if length <= _ZERO_LENGTH_TOLERANCE_M:
                yield ModelIRValidationIssue(
                    "element_zero_effective_length",
                    base,
                    "Element length after offsets must exceed 1e-12 m.",
                )

    constrained_dofs: dict[tuple[str, str], float] = {}
    for index, constraint in enumerate(payload["constraints"]):
        base = f"/constraints/{index}"
        node_id = str(constraint["node_id"])
        if node_id not in node_ids:
            yield _missing_reference(f"{base}/node_id", "node", node_id)
        prescribed = set(constraint["prescribed_values_si"])
        dofs = set(constraint["dofs"])
        if not prescribed.issubset(dofs):
            yield ModelIRValidationIssue(
                "prescribed_value_dof_not_restrained",
                f"{base}/prescribed_values_si",
                "Prescribed-value DOFs must also appear in the restrained DOF list.",
            )
        for dof in constraint["dofs"]:
            key = (node_id, str(dof))
            value = float(constraint["prescribed_values_si"].get(dof, 0.0))
            if key in constrained_dofs:
                detail = (
                    "Conflicting prescribed values."
                    if constrained_dofs[key] != value
                    else "DOF is restrained more than once."
                )
                yield ModelIRValidationIssue(
                    "duplicate_constrained_dof",
                    f"{base}/dofs",
                    f"Node {node_id} DOF {dof}: {detail}",
                )
            else:
                constrained_dofs[key] = value

    for pattern_index, pattern in enumerate(payload["load_patterns"]):
        base = f"/load_patterns/{pattern_index}"
        yield from _indexed_family_issues(
            pattern["nodal_loads"], f"load_patterns/{pattern_index}/nodal_loads"
        )
        member_loads = pattern.get("uniform_member_loads", [])
        yield from _indexed_family_issues(
            member_loads,
            f"load_patterns/{pattern_index}/uniform_member_loads",
        )
        nonzero = any(float(value) != 0.0 for value in pattern["self_weight"])
        for load_index, load in enumerate(pattern["nodal_loads"]):
            node_id = str(load["node_id"])
            if node_id not in node_ids:
                yield _missing_reference(
                    f"{base}/nodal_loads/{load_index}/node_id", "node", node_id
                )
            nonzero = nonzero or any(
                float(value) != 0.0 for value in load["components_si"].values()
            )
        for load_index, load in enumerate(member_loads):
            member_id = str(load["member_id"])
            if member_id not in element_ids:
                yield _missing_reference(
                    f"{base}/uniform_member_loads/{load_index}/member_id",
                    "element",
                    member_id,
                )
            nonzero = nonzero or any(
                float(value) != 0.0 for value in load["components_si"].values()
            )
        if not nonzero and not bounded_planar:
            yield ModelIRValidationIssue(
                "load_pattern_all_zero",
                base,
                "Each load pattern must contain a non-zero load.",
            )

    nested_load_ids = [
        str(load["id"])
        for pattern in payload["load_patterns"]
        for family in (pattern["nodal_loads"], pattern.get("uniform_member_loads", []))
        for load in family
    ]
    if len(nested_load_ids) != len(set(nested_load_ids)):
        yield ModelIRValidationIssue(
            "duplicate_id",
            "/load_patterns/*",
            "Nested load IDs must be unique across all load patterns.",
        )

    yield from _load_combination_issues(
        payload["load_combinations"], load_pattern_ids, load_combination_ids
    )

    for stage_index, stage in enumerate(payload["construction_stages"]):
        base = f"/construction_stages/{stage_index}"
        for element_id in stage["active_element_ids"]:
            if element_id not in element_ids:
                yield _missing_reference(
                    f"{base}/active_element_ids", "element", element_id
                )
        for constraint_id in stage["active_constraint_ids"]:
            if constraint_id not in constraint_ids:
                yield _missing_reference(
                    f"{base}/active_constraint_ids", "constraint", constraint_id
                )
        for pattern_id in stage["load_pattern_ids"]:
            if pattern_id not in load_pattern_ids:
                yield _missing_reference(
                    f"{base}/load_pattern_ids", "load_pattern", pattern_id
                )

    for index, time_function in enumerate(payload["time_functions"]):
        times = [float(point[0]) for point in time_function["points"]]
        if any(current <= previous for previous, current in zip(times, times[1:])):
            yield ModelIRValidationIssue(
                "time_function_not_strictly_increasing",
                f"/time_functions/{index}/points",
                "Time-function coordinates must be strictly increasing.",
            )

    entity_ids_by_kind = {
        "node": node_ids,
        "material": material_ids,
        "section": set(section_by_id),
        "element": element_ids,
        "constraint": constraint_ids,
        "load_pattern": load_pattern_ids,
        "load_combination": load_combination_ids,
        "time_function": time_function_ids,
        "construction_stage": construction_stage_ids,
    }
    all_entity_ids = set().union(*entity_ids_by_kind.values())
    for index, row in enumerate(payload["roundtrip_map"]):
        entity_id = str(row["model_ir_entity_id"])
        if entity_id not in all_entity_ids:
            yield _missing_reference(
                f"/roundtrip_map/{index}/model_ir_entity_id",
                "model_ir_entity",
                entity_id,
            )
        elif entity_id not in entity_ids_by_kind[str(row["entity_kind"])]:
            yield ModelIRValidationIssue(
                "roundtrip_entity_kind_mismatch",
                f"/roundtrip_map/{index}/entity_kind",
                f"Entity {entity_id} is not a {row['entity_kind']}.",
            )

    if bounded_planar:
        yield from _bounded_planar_issues(
            payload,
            node_ids=node_ids,
            material_by_id=material_by_id,
            section_by_id=section_by_id,
            constrained_dofs=constrained_dofs,
        )
    if bounded_frame3d_direct_control:
        yield from _bounded_frame3d_direct_control_issues(
            payload,
            node_ids=node_ids,
            material_by_id=material_by_id,
            section_by_id=section_by_id,
            constrained_dofs=constrained_dofs,
        )


def _bounded_frame3d_direct_control_issues(
    payload: dict[str, Any],
    *,
    node_ids: set[str],
    material_by_id: dict[str, dict[str, Any]],
    section_by_id: dict[str, dict[str, Any]],
    constrained_dofs: dict[tuple[str, str], float],
) -> Iterable[ModelIRValidationIssue]:
    """Enforce the source contract consumed by bounded Frame3D direct control."""

    numeric_issues = tuple(_bounded_frame3d_numeric_issues(payload))
    yield from numeric_issues
    if numeric_issues:
        return
    known_constrained_dofs = {
        (node_id, component): value
        for (node_id, component), value in constrained_dofs.items()
        if node_id in node_ids
    }
    load_to_dof = {
        "FX": "UX",
        "FY": "UY",
        "FZ": "UZ",
        "MX": "RX",
        "MY": "RY",
        "MZ": "RZ",
    }
    for index, material in enumerate(payload["materials"]):
        base = f"/materials/{index}"
        if material["law_id"] != "bilinear_combined_hardening_steel":
            yield ModelIRValidationIssue(
                "bounded_frame3d_material_law_unsupported",
                f"{base}/law_id",
                "Every bounded Frame3D member requires bilinear combined-hardening steel.",
            )
        if "shear_modulus_pa" not in material["parameters"]:
            yield ModelIRValidationIssue(
                "bounded_frame3d_shear_modulus_missing",
                f"{base}/parameters/shear_modulus_pa",
                "Frame3D requires an explicit positive shear modulus; no Poisson fallback is allowed.",
            )

    coordinates = {
        str(row["id"]): tuple(float(value) for value in row["coordinates_m"])
        for row in payload["nodes"]
    }
    if len(set(coordinates.values())) != len(coordinates):
        yield ModelIRValidationIssue(
            "bounded_frame3d_node_coordinate_duplicate",
            "/nodes",
            "Bounded Frame3D nodes must have unique 3D coordinates.",
        )

    graph: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    undirected_pairs: set[tuple[str, str]] = set()
    referenced_materials: set[str] = set()
    referenced_sections: set[str] = set()
    for index, element in enumerate(payload["elements"]):
        base = f"/elements/{index}"
        node_i, node_j = (str(value) for value in element["node_ids"])
        pair = tuple(sorted((node_i, node_j)))
        if pair in undirected_pairs:
            yield ModelIRValidationIssue(
                "bounded_frame3d_parallel_member_unsupported",
                f"{base}/node_ids",
                "Parallel or duplicate members are outside the bounded v1 profile.",
            )
        undirected_pairs.add(pair)
        if node_i in graph and node_j in graph:
            graph[node_i].add(node_j)
            graph[node_j].add(node_i)
        referenced_materials.add(str(element["material_id"]))
        referenced_sections.add(str(element["section_id"]))
        offsets = element["offsets"]
        if any(
            float(value) != 0.0
            for end in ("i_global_m", "j_global_m")
            for value in offsets[end]
        ):
            yield ModelIRValidationIssue(
                "bounded_frame3d_rigid_offset_unsupported",
                f"{base}/offsets",
                "Rigid offsets are not consumed by the bounded Frame3D direct-control solver.",
            )
        releases = element["releases"]
        if releases["i"] or releases["j"]:
            yield ModelIRValidationIssue(
                "bounded_frame3d_release_unsupported",
                f"{base}/releases",
                "Member end releases are not consumed by the bounded Frame3D direct-control solver.",
            )
    if referenced_materials != set(material_by_id):
        yield ModelIRValidationIssue(
            "bounded_frame3d_material_reference_set_invalid",
            "/materials",
            "Every and only declared bounded Frame3D material must be referenced.",
        )
    if referenced_sections != set(section_by_id):
        yield ModelIRValidationIssue(
            "bounded_frame3d_section_reference_set_invalid",
            "/sections",
            "Every and only declared bounded Frame3D section must be referenced.",
        )
    if node_ids:
        start = min(node_ids)
        visited = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for neighbor in sorted(graph[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if visited != node_ids:
            yield ModelIRValidationIssue(
                "bounded_frame3d_graph_disconnected",
                "/elements",
                "The bounded Frame3D member graph must include every node.",
            )

    for (node_id, component), value in known_constrained_dofs.items():
        if value != 0.0:
            yield ModelIRValidationIssue(
                "bounded_frame3d_prescribed_support_unsupported",
                "/constraints",
                f"Node {node_id} component {component} must be fixed at zero.",
            )
    free_equation_count = len(node_ids) * 6 - len(known_constrained_dofs)
    if not 1 <= free_equation_count <= 768:
        yield ModelIRValidationIssue(
            "bounded_frame3d_free_equation_count_out_of_range",
            "/constraints",
            "Bounded Frame3D requires between 1 and 768 free equations.",
        )

    if coordinates:
        coordinate_values = np.asarray(list(coordinates.values()), dtype=np.float64)
        spans = np.ptp(coordinate_values, axis=0)
        characteristic_length = max(float(np.linalg.norm(spans)), 1.0)
        coordinate_origin = np.mean(coordinate_values, axis=0)
        rigid_rows: list[tuple[float, float, float, float, float, float]] = []
        for (node_id, component), _value in sorted(known_constrained_dofs.items()):
            x, y, z = (
                (coordinate - origin) / characteristic_length
                for coordinate, origin in zip(
                    coordinates[node_id], coordinate_origin, strict=True
                )
            )
            rigid_rows.append(
                {
                    "UX": (1.0, 0.0, 0.0, 0.0, z, -y),
                    "UY": (0.0, 1.0, 0.0, -z, 0.0, x),
                    "UZ": (0.0, 0.0, 1.0, y, -x, 0.0),
                    "RX": (0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                    "RY": (0.0, 0.0, 0.0, 0.0, 1.0, 0.0),
                    "RZ": (0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
                }[component]
            )
        rigid_matrix = np.asarray(rigid_rows, dtype=np.float64).reshape((-1, 6))
        rigid_rank = int(np.linalg.matrix_rank(rigid_matrix)) if rigid_rows else 0
        if rigid_rank < 6:
            yield ModelIRValidationIssue(
                "bounded_frame3d_rigid_body_restraint_rank_insufficient",
                "/constraints",
                f"Support rows restrain only {rigid_rank}/6 rigid-body modes.",
            )

    pattern = payload["load_patterns"][0]
    seen_load_nodes: set[str] = set()
    free_reference_load_present = False
    for load_index, load in enumerate(pattern["nodal_loads"]):
        base = f"/load_patterns/0/nodal_loads/{load_index}"
        node_id = str(load["node_id"])
        if node_id in seen_load_nodes:
            yield ModelIRValidationIssue(
                "bounded_frame3d_duplicate_nodal_load",
                f"{base}/node_id",
                "Use at most one bounded Frame3D nodal-load row per node.",
            )
        seen_load_nodes.add(node_id)
        components = load["components_si"]
        nonzero_components = [
            component for component, value in components.items() if float(value) != 0.0
        ]
        if not nonzero_components:
            yield ModelIRValidationIssue(
                "bounded_frame3d_zero_nodal_load",
                f"{base}/components_si",
                "A declared bounded Frame3D reference-load row must be nonzero.",
            )
        for load_component in nonzero_components:
            dof = load_to_dof[load_component]
            if (node_id, dof) in known_constrained_dofs:
                yield ModelIRValidationIssue(
                    "bounded_frame3d_reference_load_on_restrained_dof",
                    f"{base}/components_si/{load_component}",
                    "Reference loads on restrained equations are outside the bounded profile.",
                )
            else:
                free_reference_load_present = True
    if not free_reference_load_present:
        yield ModelIRValidationIssue(
            "bounded_frame3d_free_reference_load_missing",
            "/load_patterns/0/nodal_loads",
            "Direct displacement control requires a nonzero reference load on a free equation.",
        )


def _bounded_frame3d_numeric_issues(
    payload: dict[str, Any],
) -> Iterable[ModelIRValidationIssue]:
    """Reject values that cannot survive the bounded SI-to-solver projection."""

    for index, node in enumerate(payload["nodes"]):
        for axis, value in enumerate(node["coordinates_m"]):
            if abs(float(value)) > _BOUNDED_FRAME3D_MAX_ABS_COORDINATE_M:
                yield ModelIRValidationIssue(
                    "bounded_frame3d_coordinate_magnitude_out_of_range",
                    f"/nodes/{index}/coordinates_m/{axis}",
                    "Bounded Frame3D coordinates must have magnitude at most 1e9 m.",
                )
    for axis, value in enumerate(payload["coordinate_system"]["origin_m"]):
        if abs(float(value)) > _BOUNDED_FRAME3D_MAX_ABS_COORDINATE_M:
            yield ModelIRValidationIssue(
                "bounded_frame3d_coordinate_magnitude_out_of_range",
                f"/coordinate_system/origin_m/{axis}",
                "Bounded Frame3D origin coordinates must have magnitude at most 1e9 m.",
            )

    for index, material in enumerate(payload["materials"]):
        parameters = material["parameters"]
        for name in ("elastic_modulus_pa", "shear_modulus_pa"):
            if name not in parameters:
                continue
            value = float(parameters[name])
            lower, upper = _BOUNDED_FRAME3D_MODULUS_PA_RANGE
            if not lower <= value <= upper:
                yield ModelIRValidationIssue(
                    "bounded_frame3d_material_conversion_out_of_range",
                    f"/materials/{index}/parameters/{name}",
                    "Elastic/shear modulus must remain positive and finite after SI conversion.",
                )
        yield_value = float(parameters["yield_stress_pa"])
        lower, upper = _BOUNDED_FRAME3D_YIELD_STRESS_PA_RANGE
        if not lower <= yield_value <= upper:
            yield ModelIRValidationIssue(
                "bounded_frame3d_material_conversion_out_of_range",
                f"/materials/{index}/parameters/yield_stress_pa",
                "Yield stress must remain positive and finite after MPa conversion.",
            )
        for name in (
            "isotropic_hardening_modulus_pa",
            "kinematic_hardening_modulus_pa",
            "yield_tolerance_pa",
        ):
            value = float(parameters[name])
            lower, upper = _BOUNDED_FRAME3D_POSITIVE_HARDENING_PA_RANGE
            if value != 0.0 and not lower <= value <= upper:
                yield ModelIRValidationIssue(
                    "bounded_frame3d_material_conversion_out_of_range",
                    f"/materials/{index}/parameters/{name}",
                    "Nonzero hardening/tolerance values must survive MPa conversion.",
                )

    for index, section in enumerate(payload["sections"]):
        parameters = section["parameters"]
        for name in ("area_m2", "shear_area_y_m2", "shear_area_z_m2"):
            value = float(parameters[name])
            lower, upper = _BOUNDED_FRAME3D_AREA_M2_RANGE
            if not lower <= value <= upper:
                yield ModelIRValidationIssue(
                    "bounded_frame3d_section_value_out_of_range",
                    f"/sections/{index}/parameters/{name}",
                    "Frame area terms are outside the bounded arithmetic range.",
                )
        for name in ("iy_m4", "iz_m4", "torsional_constant_m4"):
            value = float(parameters[name])
            lower, upper = _BOUNDED_FRAME3D_INERTIA_M4_RANGE
            if not lower <= value <= upper:
                yield ModelIRValidationIssue(
                    "bounded_frame3d_section_value_out_of_range",
                    f"/sections/{index}/parameters/{name}",
                    "Frame inertia terms are outside the bounded arithmetic range.",
                )

    for index, element in enumerate(payload["elements"]):
        if (
            abs(float(element["local_axis_rotation_rad"]))
            > _BOUNDED_FRAME3D_MAX_ABS_ROLL_RAD
        ):
            yield ModelIRValidationIssue(
                "bounded_frame3d_roll_magnitude_out_of_range",
                f"/elements/{index}/local_axis_rotation_rad",
                "Local-axis roll is outside the bounded arithmetic range.",
            )

    for pattern_index, pattern in enumerate(payload["load_patterns"]):
        for load_index, load in enumerate(pattern["nodal_loads"]):
            for component, value in load["components_si"].items():
                if abs(float(value)) > _BOUNDED_FRAME3D_MAX_ABS_LOAD_SI:
                    yield ModelIRValidationIssue(
                        "bounded_frame3d_load_magnitude_out_of_range",
                        f"/load_patterns/{pattern_index}/nodal_loads/{load_index}/components_si/{component}",
                        "Reference force/moment is outside the bounded arithmetic range.",
                    )
        for load_index, load in enumerate(pattern.get("uniform_member_loads", [])):
            for component, value in load["components_si"].items():
                if abs(float(value)) > _BOUNDED_FRAME3D_MAX_ABS_LOAD_SI:
                    yield ModelIRValidationIssue(
                        "bounded_frame3d_load_magnitude_out_of_range",
                        f"/load_patterns/{pattern_index}/uniform_member_loads/{load_index}/components_si/{component}",
                        "Uniform member force per length is outside the bounded arithmetic range.",
                    )


def _bounded_planar_issues(
    payload: dict[str, Any],
    *,
    node_ids: set[str],
    material_by_id: dict[str, dict[str, Any]],
    section_by_id: dict[str, dict[str, Any]],
    constrained_dofs: dict[tuple[str, str], float],
) -> Iterable[ModelIRValidationIssue]:
    """Enforce the exact bounded connected Frame2D ModelIR profile."""

    active_components = {"UX", "UY", "RZ"}
    inactive_components = {"UZ", "RX", "RY"}
    material_law_by_id = {
        material_id: str(row["law_id"]) for material_id, row in material_by_id.items()
    }
    referenced_materials: set[str] = set()
    for index, section in enumerate(payload["sections"]):
        base = f"/sections/{index}"
        steel_id = str(section["steel_material_id"])
        concrete_id = str(section["concrete_material_id"])
        referenced_materials.update((steel_id, concrete_id))
        if material_law_by_id.get(steel_id) != "bilinear_combined_hardening_steel":
            yield ModelIRValidationIssue(
                "bounded_planar_section_steel_material_invalid",
                f"{base}/steel_material_id",
                "Section steel material must reference the bounded bilinear steel law.",
            )
        if material_law_by_id.get(concrete_id) != "asymmetric_concrete_damage":
            yield ModelIRValidationIssue(
                "bounded_planar_section_concrete_material_invalid",
                f"{base}/concrete_material_id",
                "Section concrete material must reference the bounded asymmetric concrete law.",
            )
        parameters = section["parameters"]
        cover = float(parameters["cover_m"])
        if 2.0 * cover >= min(
            float(parameters["width_m"]), float(parameters["depth_m"])
        ):
            yield ModelIRValidationIssue(
                "bounded_planar_section_cover_invalid",
                f"{base}/parameters/cover_m",
                "Twice the cover must be smaller than both section dimensions.",
            )
    if referenced_materials != set(material_by_id):
        yield ModelIRValidationIssue(
            "bounded_planar_unused_material",
            "/materials",
            "Every bounded planar material must be referenced by a section.",
        )

    coordinates = {
        str(row["id"]): tuple(float(value) for value in row["coordinates_m"])
        for row in payload["nodes"]
    }
    for index, node in enumerate(payload["nodes"]):
        if float(node["coordinates_m"][2]) != 0.0:
            yield ModelIRValidationIssue(
                "bounded_planar_node_out_of_plane",
                f"/nodes/{index}/coordinates_m/2",
                "Bounded planar nodes require Z=0.",
            )
    if len({(row[0], row[1]) for row in coordinates.values()}) != len(coordinates):
        yield ModelIRValidationIssue(
            "bounded_planar_node_coordinate_duplicate",
            "/nodes",
            "Bounded planar node XY coordinates must be unique.",
        )

    graph: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    undirected_pairs: set[tuple[str, str]] = set()
    referenced_sections: set[str] = set()
    member_load_present = False
    for index, element in enumerate(payload["elements"]):
        base = f"/elements/{index}"
        node_i, node_j = (str(value) for value in element["node_ids"])
        pair = tuple(sorted((node_i, node_j)))
        if pair in undirected_pairs:
            yield ModelIRValidationIssue(
                "bounded_planar_parallel_member_unsupported",
                f"{base}/node_ids",
                "The bounded profile does not support parallel members.",
            )
        undirected_pairs.add(pair)
        if node_i in graph and node_j in graph:
            graph[node_i].add(node_j)
            graph[node_j].add(node_i)
        referenced_sections.add(str(element["section_id"]))
        offsets = element["offsets"]
        if any(float(offsets[end][2]) != 0.0 for end in ("i_global_m", "j_global_m")):
            yield ModelIRValidationIssue(
                "bounded_planar_offset_out_of_plane",
                f"{base}/offsets",
                "Bounded planar rigid offsets require zero global Z components.",
            )
        releases = element["releases"]
        if any(set(releases[end]) - {"RZ"} for end in ("i", "j")):
            yield ModelIRValidationIssue(
                "bounded_planar_release_unsupported",
                f"{base}/releases",
                "Only an optional RZ release at either member end is supported.",
            )
        member_load = element["uniform_distributed_load_local"]
        member_load_present = member_load_present or any(
            float(member_load[key]) != 0.0 for key in ("qx_n_per_m", "qy_n_per_m")
        )
    if referenced_sections != set(section_by_id):
        yield ModelIRValidationIssue(
            "bounded_planar_unused_section",
            "/sections",
            "Every bounded planar section must be referenced by a member.",
        )
    if node_ids:
        start = min(node_ids)
        visited = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for neighbor in sorted(graph[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if visited != node_ids:
            yield ModelIRValidationIssue(
                "bounded_planar_graph_disconnected",
                "/elements",
                "The bounded planar member graph must be connected.",
            )

    inactive_missing = sorted(
        (node_id, component)
        for node_id in node_ids
        for component in inactive_components
        if (node_id, component) not in constrained_dofs
    )
    if inactive_missing:
        node_id, component = inactive_missing[0]
        yield ModelIRValidationIssue(
            "bounded_planar_inactive_dof_unrestrained",
            "/constraints",
            f"Node {node_id} inactive component {component} must be restrained.",
        )
    for (node_id, component), value in constrained_dofs.items():
        if component in inactive_components and value != 0.0:
            yield ModelIRValidationIssue(
                "bounded_planar_inactive_dof_prescribed_nonzero",
                "/constraints",
                f"Node {node_id} inactive component {component} must be fixed at zero.",
            )
    if not any(component in active_components for _node, component in constrained_dofs):
        yield ModelIRValidationIssue(
            "bounded_planar_active_support_missing",
            "/constraints",
            "At least one active UX, UY, or RZ support is required.",
        )

    pattern = payload["load_patterns"][0]
    seen_load_nodes: set[str] = set()
    nodal_load_present = False
    for load_index, load in enumerate(pattern["nodal_loads"]):
        base = f"/load_patterns/0/nodal_loads/{load_index}"
        node_id = str(load["node_id"])
        if node_id in seen_load_nodes:
            yield ModelIRValidationIssue(
                "bounded_planar_duplicate_nodal_load",
                f"{base}/node_id",
                "Use at most one bounded planar nodal-load row per node.",
            )
        seen_load_nodes.add(node_id)
        components = load["components_si"]
        if any(float(components[key]) != 0.0 for key in ("FZ", "MX", "MY")):
            yield ModelIRValidationIssue(
                "bounded_planar_load_out_of_plane",
                f"{base}/components_si",
                "Only in-plane FX, FY, and MZ nodal loads are supported.",
            )
        in_plane_nonzero = any(
            float(components[key]) != 0.0 for key in ("FX", "FY", "MZ")
        )
        if not in_plane_nonzero:
            yield ModelIRValidationIssue(
                "bounded_planar_zero_nodal_load",
                f"{base}/components_si",
                "A declared bounded planar nodal-load row must be nonzero.",
            )
        nodal_load_present = nodal_load_present or in_plane_nonzero
    prescribed_present = any(
        component in active_components and value != 0.0
        for (_node_id, component), value in constrained_dofs.items()
    )
    if not (nodal_load_present or member_load_present or prescribed_present):
        yield ModelIRValidationIssue(
            "bounded_planar_load_missing",
            "/load_patterns/0",
            "At least one nodal, member, or prescribed-displacement load is required.",
        )


def _finite_number_issues(
    value: Any, path: str = ""
) -> Iterable[ModelIRValidationIssue]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        try:
            normalized = float(value)
        except OverflowError:
            normalized = math.inf
        if not math.isfinite(normalized):
            yield ModelIRValidationIssue(
                "non_finite_number",
                path or "/",
                "Numbers must be finite and representable as binary64 values.",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _finite_number_issues(item, f"{path}/{index}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _finite_number_issues(
                item, f"{path}/{_escape_pointer(str(key))}"
            )


def _unit_scale_issues(payload: dict[str, Any]) -> Iterable[ModelIRValidationIssue]:
    source_units = payload["provenance"]["source_units"]
    scales = payload["provenance"]["unit_scales_to_si"]
    for dimension, unit in source_units.items():
        expected = _EXPECTED_UNIT_SCALES[dimension][unit]
        scale_key = _SCALE_KEYS[dimension]
        actual = float(scales[scale_key])
        if not math.isclose(actual, expected, rel_tol=1.0e-12, abs_tol=1.0e-15):
            yield ModelIRValidationIssue(
                "unit_scale_mismatch",
                f"/provenance/unit_scales_to_si/{scale_key}",
                f"Source unit {unit} requires scale {expected:.17g}, got {actual:.17g}.",
            )


def _indexed_family_issues(
    rows: list[dict[str, Any]], family: str
) -> Iterable[ModelIRValidationIssue]:
    yield from _id_family_issues(rows, family, "id")
    indices = [int(row["index"]) for row in rows]
    if len(indices) != len(set(indices)):
        yield ModelIRValidationIssue(
            "duplicate_index", f"/{family}", f"{family} indices must be unique."
        )
    expected = list(range(len(rows)))
    if indices != expected:
        yield ModelIRValidationIssue(
            "noncanonical_index_order",
            f"/{family}",
            f"{family} indices must be contiguous and match array order: {expected}.",
        )


def _id_family_issues(
    rows: list[dict[str, Any]], family: str, id_key: str
) -> Iterable[ModelIRValidationIssue]:
    ids = [str(row[id_key]) for row in rows]
    if len(ids) != len(set(ids)):
        yield ModelIRValidationIssue(
            "duplicate_id", f"/{family}", f"{family} {id_key} values must be unique."
        )


def _load_combination_issues(
    combinations: list[dict[str, Any]],
    load_pattern_ids: set[str],
    combination_ids: set[str],
) -> Iterable[ModelIRValidationIssue]:
    graph: dict[str, list[str]] = {str(row["id"]): [] for row in combinations}
    for index, combination in enumerate(combinations):
        for term_index, term in enumerate(combination["terms"]):
            ref_id = str(term["ref_id"])
            path = f"/load_combinations/{index}/terms/{term_index}/ref_id"
            if term["ref_kind"] == "load_pattern":
                if ref_id not in load_pattern_ids:
                    yield _missing_reference(path, "load_pattern", ref_id)
            else:
                if ref_id not in combination_ids:
                    yield _missing_reference(path, "load_combination", ref_id)
                else:
                    graph[str(combination["id"])].append(ref_id)

    # Iterative depth-first traversal avoids recursion failure for imported
    # combination graphs whose valid dependency depth exceeds Python's stack.
    state = {combination_id: 0 for combination_id in graph}
    for root in sorted(graph):
        if state[root] != 0:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        trail: list[str] = []
        trail_positions: dict[str, int] = {}
        while stack:
            node, child_index = stack[-1]
            if state[node] == 0:
                state[node] = 1
                trail_positions[node] = len(trail)
                trail.append(node)
            children = graph[node]
            if child_index < len(children):
                child = children[child_index]
                stack[-1] = (node, child_index + 1)
                if state[child] == 0:
                    stack.append((child, 0))
                elif state[child] == 1:
                    cycle = (*trail[trail_positions[child] :], child)
                    yield ModelIRValidationIssue(
                        "load_combination_cycle",
                        "/load_combinations",
                        "Load-combination graph contains a cycle: "
                        + " -> ".join(cycle),
                    )
                    return
                continue
            stack.pop()
            state[node] = 2
            trail_positions.pop(node)
            assert trail.pop() == node


def _without_source_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_source_metadata(item)
            for key, item in value.items()
            if key not in {"source_id", "extensions"}
        }
    if isinstance(value, list):
        return [_without_source_metadata(item) for item in value]
    return value


def _source_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "id": row["id"],
        "index": row["index"],
        "extensions": row["extensions"],
    }
    if "source_id" in row:
        metadata["source_id"] = row["source_id"]
    if "nodal_loads" in row:
        metadata["nodal_loads"] = [
            _source_metadata(load) for load in row["nodal_loads"]
        ]
    if "uniform_member_loads" in row:
        metadata["uniform_member_loads"] = [
            _source_metadata(load) for load in row["uniform_member_loads"]
        ]
    return metadata


def _normalize_value(value: Any, path: str) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite number at {path}")
        if value == 0.0:
            return 0
        return int(value) if value.is_integer() else value
    if isinstance(value, list):
        return [
            _normalize_value(item, f"{path}{index}/")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(item, f"{path}{key}/")
            for key, item in value.items()
        }
    raise TypeError(f"Unsupported ModelIR value at {path}: {type(value).__name__}")


def _missing_reference(path: str, kind: str, reference: str) -> ModelIRValidationIssue:
    return ModelIRValidationIssue(
        "dangling_reference", path, f"Unknown {kind} reference: {reference}"
    )


def _json_pointer(path: Iterable[Any]) -> str:
    parts = [_escape_pointer(str(part)) for part in path]
    return "/" + "/".join(parts) if parts else "/"


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result
