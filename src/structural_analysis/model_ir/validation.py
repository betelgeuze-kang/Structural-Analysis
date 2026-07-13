"""Strict schema and engineering-invariant validation for ModelIR v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

MODEL_IR_V2_SCHEMA_VERSION = "structural-analysis-model-ir.v2"
_ZERO_LENGTH_TOLERANCE_M = 1.0e-12

_EXPECTED_UNIT_SCALES: dict[str, dict[str, float]] = {
    "length": {"m": 1.0, "mm": 1.0e-3, "cm": 1.0e-2, "ft": 0.3048, "in": 0.0254},
    "force": {"N": 1.0, "kN": 1.0e3, "MN": 1.0e6, "lbf": 4.4482216152605, "kip": 4448.2216152605},
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
    content_hash: str | None

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
            "content_hash": self.content_hash,
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


def validate_model_ir_v2(payload: Any) -> ModelIRValidationReport:
    schema = load_model_ir_v2_schema()
    validator = Draft202012Validator(schema)
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
        str(payload.get("schema_version", ""))
        if isinstance(payload, dict)
        else ""
    )
    if schema_issues or not isinstance(payload, dict):
        return ModelIRValidationReport(
            schema_version=schema_version,
            schema_valid=False,
            semantics_valid=False,
            analysis_ready=False,
            issues=schema_issues,
            blocking_feature_ids=(),
            content_hash=None,
        )

    semantic_issues = tuple(sorted(_semantic_issues(payload)))
    blocking_feature_ids = tuple(
        sorted(
            str(row["feature_id"])
            for row in payload["unsupported_features"]
            if bool(row["blocking"])
        )
    )
    content_hash: str | None
    try:
        content_hash = model_ir_v2_content_hash(payload)
    except ValueError as exc:
        semantic_issues = tuple(
            sorted(
                (*semantic_issues, ModelIRValidationIssue("non_finite_number", "/", str(exc)))
            )
        )
        content_hash = None

    semantics_valid = not semantic_issues
    return ModelIRValidationReport(
        schema_version=schema_version,
        schema_valid=True,
        semantics_valid=semantics_valid,
        analysis_ready=semantics_valid and not blocking_feature_ids,
        issues=semantic_issues,
        blocking_feature_ids=blocking_feature_ids,
        content_hash=content_hash,
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

    node_coordinates = {
        str(row["id"]): tuple(float(value) for value in row["coordinates_m"])
        for row in payload["nodes"]
    }
    for index, element in enumerate(payload["elements"]):
        base = f"/elements/{index}"
        node_pair = tuple(str(value) for value in element["node_ids"])
        if node_pair[0] == node_pair[1]:
            yield ModelIRValidationIssue(
                "element_nodes_not_distinct", f"{base}/node_ids", "Element end nodes must differ."
            )
        for node_id in node_pair:
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
            expected_family = "frame_3d" if element["type"] == "frame_3d" else "truss_3d"
            if section["family_id"] != expected_family:
                yield ModelIRValidationIssue(
                    "element_section_family_mismatch",
                    f"{base}/section_id",
                    f"Element type {element['type']} requires section family {expected_family}.",
                )
        if all(node_id in node_coordinates for node_id in node_pair):
            offsets = element["offsets"]
            start = tuple(
                node_coordinates[node_pair[0]][axis] + float(offsets["i_global_m"][axis])
                for axis in range(3)
            )
            end = tuple(
                node_coordinates[node_pair[1]][axis] + float(offsets["j_global_m"][axis])
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
        yield from _indexed_family_issues(pattern["nodal_loads"], f"load_patterns/{pattern_index}/nodal_loads")
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
                "load_pattern_all_zero", base, "Each load pattern must contain a non-zero load."
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
                yield _missing_reference(f"{base}/active_element_ids", "element", element_id)
        for constraint_id in stage["active_constraint_ids"]:
            if constraint_id not in constraint_ids:
                yield _missing_reference(
                    f"{base}/active_constraint_ids", "constraint", constraint_id
                )
        for pattern_id in stage["load_pattern_ids"]:
            if pattern_id not in load_pattern_ids:
                yield _missing_reference(f"{base}/load_pattern_ids", "load_pattern", pattern_id)

    for index, time_function in enumerate(payload["time_functions"]):
        times = [float(point[0]) for point in time_function["points"]]
        if any(current <= previous for previous, current in zip(times, times[1:])):
            yield ModelIRValidationIssue(
                "time_function_not_strictly_increasing",
                f"/time_functions/{index}/points",
                "Time-function coordinates must be strictly increasing.",
            )

    all_entity_ids = node_ids | material_ids | set(section_by_id) | element_ids | constraint_ids | load_pattern_ids | load_combination_ids
    for index, row in enumerate(payload["roundtrip_map"]):
        entity_id = str(row["model_ir_entity_id"])
        if entity_id not in all_entity_ids:
            yield _missing_reference(
                f"/roundtrip_map/{index}/model_ir_entity_id", "model_ir_entity", entity_id
            )


def _finite_number_issues(value: Any, path: str = "") -> Iterable[ModelIRValidationIssue]:
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
            yield from _finite_number_issues(item, f"{path}/{_escape_pointer(str(key))}")


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


def _indexed_family_issues(rows: list[dict[str, Any]], family: str) -> Iterable[ModelIRValidationIssue]:
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

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> tuple[str, ...] | None:
        if node in visiting:
            start = trail.index(node) if node in trail else 0
            return (*trail[start:], node)
        if node in visited:
            return None
        visiting.add(node)
        for child in graph[node]:
            cycle = visit(child, (*trail, node))
            if cycle is not None:
                return cycle
        visiting.remove(node)
        visited.add(node)
        return None

    for combination_id in sorted(graph):
        cycle = visit(combination_id, ())
        if cycle is not None:
            yield ModelIRValidationIssue(
                "load_combination_cycle",
                "/load_combinations",
                "Load-combination graph contains a cycle: " + " -> ".join(cycle),
            )
            break


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
        return [_normalize_value(item, f"{path}{index}/") for index, item in enumerate(value)]
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
