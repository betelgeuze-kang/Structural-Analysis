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

MODEL_IR_V2_SCHEMA_VERSION = "structural-analysis-model-ir.v2"
_ZERO_LENGTH_TOLERANCE_M = 1.0e-12

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
    yield from _finite_number_issues(payload)
    yield from _unit_scale_issues(payload)

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
    material_ids = {str(row["id"]) for row in payload["materials"]}
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
        element_nodes = tuple(str(value) for value in element["node_ids"])
        if len(set(element_nodes)) != len(element_nodes):
            yield ModelIRValidationIssue(
                "element_nodes_not_distinct",
                f"{base}/node_ids",
                "Element nodes must be distinct.",
            )
        for node_id in element_nodes:
            if node_id not in node_ids:
                yield _missing_reference(f"{base}/node_ids", "node", node_id)
        material_id = str(element["material_id"])
        if material_id not in material_ids:
            yield _missing_reference(f"{base}/material_id", "material", material_id)
        section_id = str(element["section_id"])
        section = section_by_id.get(section_id)
        if section is None:
            yield _missing_reference(f"{base}/section_id", "section", section_id)
        else:
            expected_family = {
                "frame_3d": "frame_3d",
                "truss_3d": "truss_3d",
                "shell_3": "shell_3",
            }[element["type"]]
            if section["family_id"] != expected_family:
                yield ModelIRValidationIssue(
                    "element_section_family_mismatch",
                    f"{base}/section_id",
                    f"Element type {element['type']} requires section family {expected_family}.",
                )
        if element["type"] == "shell_3" and all(node_id in node_coordinates for node_id in element_nodes):
            a, b, c = (node_coordinates[node_id] for node_id in element_nodes)
            ab = tuple(b[axis] - a[axis] for axis in range(3))
            ac = tuple(c[axis] - a[axis] for axis in range(3))
            cross = (
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            )
            twice_area = math.sqrt(sum(value * value for value in cross))
            if twice_area <= _ZERO_LENGTH_TOLERANCE_M**2:
                yield ModelIRValidationIssue(
                    "element_zero_area",
                    base,
                    "Shell element area must be positive.",
                )
        elif all(node_id in node_coordinates for node_id in element_nodes):
            offsets = element["offsets"]
            start = tuple(
                node_coordinates[element_nodes[0]][axis]
                + float(offsets["i_global_m"][axis])
                for axis in range(3)
            )
            end = tuple(
                node_coordinates[element_nodes[1]][axis]
                + float(offsets["j_global_m"][axis])
                for axis in range(3)
            )
            length = math.sqrt(sum((end[axis] - start[axis]) ** 2 for axis in range(3)))
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
        if not nonzero:
            yield ModelIRValidationIssue(
                "load_pattern_all_zero",
                base,
                "Each load pattern must contain a non-zero load.",
            )

    nested_load_ids = [
        str(load["id"])
        for pattern in payload["load_patterns"]
        for load in pattern["nodal_loads"]
    ]
    if len(nested_load_ids) != len(set(nested_load_ids)):
        yield ModelIRValidationIssue(
            "duplicate_id",
            "/load_patterns/*/nodal_loads",
            "Nodal-load IDs must be unique across all load patterns.",
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


def _finite_number_issues(
    value: Any, path: str = ""
) -> Iterable[ModelIRValidationIssue]:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            yield ModelIRValidationIssue(
                "non_finite_number", path or "/", "NaN and Infinity are forbidden."
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
