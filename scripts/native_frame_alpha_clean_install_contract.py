#!/usr/bin/env python3
"""Dependency-free contracts used by the Frame Alpha clean-install lane."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


class CleanInstallContractError(ValueError):
    """Raised when an input violates a tracked clean-install contract."""


_SCHEMA_ANNOTATIONS = {"$schema", "$id", "title", "description", "default"}
_SCHEMA_ASSERTIONS = {
    "$defs",
    "$ref",
    "additionalProperties",
    "const",
    "enum",
    "items",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "oneOf",
    "pattern",
    "properties",
    "required",
    "type",
}
_SEMANTIC_KEYS = (
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
_SOURCE_FAMILIES = (
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


def load_object_bytes(value: bytes, label: str) -> dict[str, Any]:
    """Decode one finite JSON object while rejecting duplicate keys."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise CleanInstallContractError(f"{label}_duplicate_key:{key}")
            result[key] = item
        return result

    try:
        payload = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CleanInstallContractError(f"{label}_nonfinite:{token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CleanInstallContractError(f"{label}_invalid_json") from error
    if not isinstance(payload, dict):
        raise CleanInstallContractError(f"{label}_must_be_object")
    return payload


def canonical_bytes(value: Any) -> bytes:
    """Render the Python/Rust ModelIR-compatible canonical JSON profile."""

    return json.dumps(
        _normalize(value, "/"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_schema(
    instance: Any, schema: dict[str, Any], *, label: str
) -> None:
    """Validate the complete supported vocabulary of a tracked local schema.

    The clean-install jobs intentionally have no package-install step.  These schemas use a
    small Draft 2020-12 subset, so this validator rejects an unsupported schema keyword rather
    than silently issuing evidence from a partially evaluated contract.
    """

    _check_supported_schema(schema, path="#")
    _validate(instance, schema, root=schema, path="/", label=label)


def derive_model_ir_identity(
    payload: dict[str, Any], *, expected_load_pattern_id: str
) -> dict[str, str]:
    """Derive all native ModelIR identities without consulting the packaged CLI."""

    try:
        model_id = payload["model_id"]
        semantic = _without_source_metadata(
            {key: payload[key] for key in _SEMANTIC_KEYS}
        )
        provenance = {
            "schema_version": payload["schema_version"],
            "capability_profile": payload["capability_profile"],
            "model_id": model_id,
            "provenance": payload["provenance"],
            "entity_source_metadata": {
                family: [_source_metadata(row) for row in payload[family]]
                for family in _SOURCE_FAMILIES
            },
            "roundtrip_map": payload["roundtrip_map"],
            "unsupported_features": payload["unsupported_features"],
            "extensions": payload["extensions"],
        }
        load_patterns = payload["load_patterns"]
    except (KeyError, TypeError) as error:
        raise CleanInstallContractError("packaged_example_identity_shape_invalid") from error
    if not isinstance(model_id, str) or not model_id:
        raise CleanInstallContractError("packaged_example_model_id_invalid")
    if not isinstance(load_patterns, list):
        raise CleanInstallContractError("packaged_example_load_patterns_invalid")
    matches = [
        row
        for row in load_patterns
        if isinstance(row, dict) and row.get("id") == expected_load_pattern_id
    ]
    if len(matches) != 1:
        raise CleanInstallContractError("packaged_example_load_pattern_identity_invalid")
    return {
        "model_id": model_id,
        "model_content_hash": sha256_bytes(canonical_bytes(payload)),
        "model_semantic_hash": sha256_bytes(canonical_bytes(semantic)),
        "model_provenance_hash": sha256_bytes(canonical_bytes(provenance)),
    }


def _normalize(value: Any, path: str) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CleanInstallContractError(f"nonfinite_number:{path}")
        if value == 0.0:
            return 0
        return int(value) if value.is_integer() else value
    if isinstance(value, list):
        return [_normalize(item, f"{path}{index}/") for index, item in enumerate(value)]
    if isinstance(value, dict):
        return {
            str(key): _normalize(item, f"{path}{key}/")
            for key, item in value.items()
        }
    raise CleanInstallContractError(f"unsupported_json_type:{path}:{type(value).__name__}")


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


def _source_metadata(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise CleanInstallContractError("packaged_example_source_metadata_invalid")
    try:
        metadata = {
            "id": row["id"],
            "index": row["index"],
            "extensions": row["extensions"],
        }
        if "source_id" in row:
            metadata["source_id"] = row["source_id"]
        for family in ("nodal_loads", "uniform_member_loads"):
            if family in row:
                if not isinstance(row[family], list):
                    raise CleanInstallContractError(
                        "packaged_example_source_metadata_invalid"
                    )
                metadata[family] = [_source_metadata(item) for item in row[family]]
        return metadata
    except KeyError as error:
        raise CleanInstallContractError(
            "packaged_example_source_metadata_invalid"
        ) from error


def _check_supported_schema(schema: Any, *, path: str) -> None:
    if not isinstance(schema, dict):
        raise CleanInstallContractError(f"schema_node_invalid:{path}")
    unsupported = set(schema) - _SCHEMA_ANNOTATIONS - _SCHEMA_ASSERTIONS
    if unsupported:
        raise CleanInstallContractError(
            f"schema_keyword_unsupported:{path}:{','.join(sorted(unsupported))}"
        )
    for container in ("$defs", "properties"):
        value = schema.get(container, {})
        if not isinstance(value, dict):
            raise CleanInstallContractError(f"schema_{container}_invalid:{path}")
        for key, child in value.items():
            _check_supported_schema(child, path=f"{path}/{container}/{key}")
    items = schema.get("items")
    if isinstance(items, dict):
        _check_supported_schema(items, path=f"{path}/items")
    elif items is not None and not isinstance(items, bool):
        raise CleanInstallContractError(f"schema_items_invalid:{path}")
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _check_supported_schema(additional, path=f"{path}/additionalProperties")
    elif additional is not None and not isinstance(additional, bool):
        raise CleanInstallContractError(f"schema_additional_properties_invalid:{path}")
    one_of = schema.get("oneOf", [])
    if not isinstance(one_of, list):
        raise CleanInstallContractError(f"schema_one_of_invalid:{path}")
    for index, child in enumerate(one_of):
        _check_supported_schema(child, path=f"{path}/oneOf/{index}")


def _validate(
    instance: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
    path: str,
    label: str,
) -> None:
    reference = schema.get("$ref")
    if reference is not None:
        target = _resolve_reference(root, reference)
        _validate(instance, target, root=root, path=path, label=label)

    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                _validate(instance, candidate, root=root, path=path, label=label)
            except CleanInstallContractError:
                continue
            matches += 1
        if matches != 1:
            raise CleanInstallContractError(f"{label}_schema_one_of:{path}")

    expected_type = schema.get("type")
    if expected_type is not None:
        types = [expected_type] if isinstance(expected_type, str) else expected_type
        if not isinstance(types, list) or not any(
            _matches_type(instance, item) for item in types
        ):
            raise CleanInstallContractError(f"{label}_schema_type:{path}")

    if "const" in schema and not _json_equal(instance, schema["const"]):
        raise CleanInstallContractError(f"{label}_schema_const:{path}")
    if "enum" in schema and not any(
        _json_equal(instance, candidate) for candidate in schema["enum"]
    ):
        raise CleanInstallContractError(f"{label}_schema_enum:{path}")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
            raise CleanInstallContractError("schema_required_invalid")
        missing = [key for key in required if key not in instance]
        if missing:
            raise CleanInstallContractError(
                f"{label}_schema_required:{path}:{','.join(sorted(missing))}"
            )
        properties = schema.get("properties", {})
        for key, child in properties.items():
            if key in instance:
                _validate(
                    instance[key],
                    child,
                    root=root,
                    path=_child_path(path, key),
                    label=label,
                )
        extra = set(instance) - set(properties)
        additional = schema.get("additionalProperties", True)
        if extra and additional is False:
            raise CleanInstallContractError(
                f"{label}_schema_additional_properties:{path}:{','.join(sorted(extra))}"
            )
        if isinstance(additional, dict):
            for key in extra:
                _validate(
                    instance[key],
                    additional,
                    root=root,
                    path=_child_path(path, key),
                    label=label,
                )

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise CleanInstallContractError(f"{label}_schema_min_items:{path}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise CleanInstallContractError(f"{label}_schema_max_items:{path}")
        items = schema.get("items")
        if items is False and instance:
            raise CleanInstallContractError(f"{label}_schema_items_forbidden:{path}")
        if isinstance(items, dict):
            for index, item in enumerate(instance):
                _validate(
                    item,
                    items,
                    root=root,
                    path=_child_path(path, str(index)),
                    label=label,
                )

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise CleanInstallContractError(f"{label}_schema_min_length:{path}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise CleanInstallContractError(f"{label}_schema_max_length:{path}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise CleanInstallContractError(f"{label}_schema_pattern:{path}")

    if _matches_type(instance, "number"):
        if "minimum" in schema and instance < schema["minimum"]:
            raise CleanInstallContractError(f"{label}_schema_minimum:{path}")
        if "maximum" in schema and instance > schema["maximum"]:
            raise CleanInstallContractError(f"{label}_schema_maximum:{path}")


def _resolve_reference(root: dict[str, Any], reference: Any) -> dict[str, Any]:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise CleanInstallContractError(f"schema_reference_unsupported:{reference}")
    current: Any = root
    for raw in reference[2:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current:
            raise CleanInstallContractError(f"schema_reference_missing:{reference}")
        current = current[key]
    if not isinstance(current, dict):
        raise CleanInstallContractError(f"schema_reference_invalid:{reference}")
    return current


def _matches_type(value: Any, expected: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "number":
        return not isinstance(value, bool) and isinstance(value, (int, float))
    if expected == "integer":
        return not isinstance(value, bool) and (
            isinstance(value, int)
            or (isinstance(value, float) and math.isfinite(value) and value.is_integer())
        )
    raise CleanInstallContractError(f"schema_type_unsupported:{expected}")


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return not isinstance(left, bool) and not isinstance(right, bool) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return type(left) is type(right) and left == right


def _child_path(path: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"/{escaped}" if path == "/" else f"{path}/{escaped}"
