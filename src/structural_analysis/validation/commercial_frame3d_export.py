"""Fail-closed MIDAS GEN and SAP2000 full-result export normalization.

The adapter turns operator-attached CSV tables into the existing bounded external
``ReferenceIR`` contract.  It deliberately does not execute a commercial solver,
establish same-model truth, or grant external-validation authority.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, NoReturn, Sequence

import jsonschema


MANIFEST_SCHEMA = "commercial-frame3d-full-result-export-adapter.v1"
REFERENCE_SCHEMA = "structural-external-linear-frame3d-reference.v1"
RECEIPT_SCHEMA = "commercial-frame3d-full-result-normalization-receipt.v1"
REFERENCE_CLAIM_BOUNDARY = (
    "operator_declared_mapping_and_units_not_independent_validation_or_release_authority"
)
SUPPORTED_TOOLS = {"midas_gen", "sap2000"}
SUPPORTED_ENCODINGS = {"utf-8", "utf-8-sig", "cp949", "utf-16"}
SUPPORTED_DELIMITERS = {",", "\t", ";"}
STABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_SCHEMA_PATH = (
    REPO_ROOT
    / "native/crates/structural-contracts/schemas/external_linear_frame3d_reference_v1.schema.json"
)
VECTOR_COMPONENTS = ("x", "y", "z")
SIX_COMPONENTS = ("fx", "fy", "fz", "mx", "my", "mz")
DISPLACEMENT_COMPONENTS = ("ux", "uy", "uz", "rx", "ry", "rz")


class CommercialExportError(ValueError):
    """Stable fail-closed adapter error."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        super().__init__(f"{code} at {path}: {detail}")
        self.code = code
        self.path = path
        self.detail = detail


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise CommercialExportError(code, path, detail)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_existing_reference_contract(reference: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        _fail("reference_schema_unavailable", str(REFERENCE_SCHEMA_PATH), exc.__class__.__name__)
    errors = sorted(validator.iter_errors(reference), key=lambda item: tuple(str(part) for part in item.path))
    if errors:
        first = errors[0]
        location = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("reference_ir_schema_invalid", location, first.message)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", "/", f"duplicate key {key!r}")
        result[key] = value
    return result


def load_json_strict(path: Path) -> dict[str, Any]:
    """Load a JSON object while rejecting duplicate keys and non-finite values."""

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: _fail(
                "non_finite_json_number", "/", f"non-finite token {token!r}"
            ),
        )
    except CommercialExportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("json_unreadable", str(path), exc.__class__.__name__)
    if not isinstance(payload, dict):
        _fail("json_root_invalid", "/", "expected an object")
    return payload


def _expect_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("type_mismatch", path, "expected object")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("type_mismatch", path, "expected array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Iterable[str], path: str) -> None:
    expected_set = set(expected)
    actual_set = set(value)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing or extra:
        _fail(
            "object_shape_invalid",
            path,
            f"missing={missing!r}, extra={extra!r}",
        )


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("string_invalid", path, "expected non-empty string")
    return value.strip()


def _stable_id(value: Any, path: str) -> str:
    candidate = _string(value, path)
    if not STABLE_ID.fullmatch(candidate):
        _fail("stable_id_invalid", path, candidate)
    return candidate


def _hash(value: Any, path: str) -> str:
    candidate = _string(value, path)
    if not SHA256.fullmatch(candidate):
        _fail("sha256_invalid", path, candidate)
    return candidate


def _normalized_solver_name(value: Any, path: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "_", _string(value, path).lower()).strip("_")
    aliases = {
        "midas": "midas_gen",
        "midas_gen": "midas_gen",
        "midas_gen_nx": "midas_gen",
        "sap2000": "sap2000",
        "sap_2000": "sap2000",
    }
    return aliases.get(candidate, candidate)


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail("type_mismatch", path, "expected boolean")
    return value


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool):
        _fail("number_invalid", path, "boolean is not a number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        _fail("number_invalid", path, repr(value))
    if not math.isfinite(result):
        _fail("number_invalid", path, "non-finite number")
    return result


def _six_bools(value: Any, path: str) -> tuple[bool, ...]:
    rows = _expect_list(value, path)
    if len(rows) != 6 or any(not isinstance(item, bool) for item in rows):
        _fail("release_vector_invalid", path, "expected six booleans")
    return tuple(rows)


def _vector3(value: Any, path: str) -> tuple[float, float, float]:
    rows = _expect_list(value, path)
    if len(rows) != 3:
        _fail("vector_invalid", path, "expected three finite numbers")
    return tuple(_finite(item, f"{path}/{index}") for index, item in enumerate(rows))  # type: ignore[return-value]


def _proper_signed_permutation(value: Any, path: str) -> tuple[tuple[float, ...], ...]:
    rows = _expect_list(value, path)
    if len(rows) != 3:
        _fail("axis_transform_invalid", path, "expected 3x3 matrix")
    matrix: list[tuple[float, ...]] = []
    for row_index, row in enumerate(rows):
        values = _expect_list(row, f"{path}/{row_index}")
        if len(values) != 3:
            _fail("axis_transform_invalid", path, "expected 3x3 matrix")
        parsed = tuple(_finite(item, f"{path}/{row_index}") for item in values)
        if any(item not in {-1.0, 0.0, 1.0} for item in parsed):
            _fail("axis_transform_invalid", path, "only signed permutations are supported")
        matrix.append(parsed)
    if any(sum(abs(item) for item in row) != 1.0 for row in matrix):
        _fail("axis_transform_invalid", path, "each row must select exactly one axis")
    if any(sum(abs(matrix[row][column]) for row in range(3)) != 1.0 for column in range(3)):
        _fail("axis_transform_invalid", path, "each column must map exactly once")
    determinant = (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    if determinant != 1.0:
        _fail("axis_transform_invalid", path, "reflection transforms are not supported")
    return tuple(matrix)


def _transform3(matrix: Sequence[Sequence[float]], values: Sequence[float]) -> list[float]:
    return [sum(matrix[row][column] * values[column] for column in range(3)) for row in range(3)]


def _transform6(matrix: Sequence[Sequence[float]], values: Sequence[float]) -> list[float]:
    return _transform3(matrix, values[:3]) + _transform3(matrix, values[3:])


def _resolve_contained_file(package_root: Path, raw_path: Any, path: str) -> tuple[str, Path]:
    relative = _string(raw_path, path)
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail("operator_file_outside_package", path, relative)
    root = package_root.resolve()
    try:
        resolved = (root / candidate).resolve(strict=True)
    except OSError:
        _fail("operator_file_missing", path, relative)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _fail("operator_file_outside_package", path, relative)
    return candidate.as_posix(), resolved


def _verify_raw_file(
    role: str,
    descriptor: Any,
    *,
    package: Mapping[str, Any],
    package_root: Path,
) -> tuple[str, Path, str]:
    row = _expect_object(descriptor, f"/raw_files/{role}")
    _exact_keys(row, {"path", "sha256"}, f"/raw_files/{role}")
    relative, resolved = _resolve_contained_file(package_root, row["path"], f"/raw_files/{role}/path")
    expected = _hash(row["sha256"], f"/raw_files/{role}/sha256")
    actual = _sha256_file(resolved)
    if actual != expected:
        _fail("raw_file_checksum_mismatch", f"/raw_files/{role}", relative)
    package_checksums = _expect_object(package.get("file_checksums"), "/operator_package/file_checksums")
    if package_checksums.get(relative) != expected:
        _fail("operator_package_checksum_mismatch", f"/raw_files/{role}", relative)
    package_key = "raw_input_files" if role == "model_input" else "raw_result_files"
    package_paths = _expect_list(package.get(package_key), f"/operator_package/{package_key}")
    if relative not in package_paths:
        _fail("raw_file_not_declared_by_operator_package", f"/raw_files/{role}", relative)
    return relative, resolved, actual


def _validate_table(
    name: str,
    table: Any,
    *,
    raw_path: str,
    expected_columns: set[str],
    external_case: str,
) -> dict[str, Any]:
    path = f"/tables/{name}"
    row = _expect_object(table, path)
    _exact_keys(
        row,
        {
            "path",
            "encoding",
            "delimiter",
            "header_row",
            "filters",
            "load_filter_column",
            "columns",
        },
        path,
    )
    if _string(row["path"], f"{path}/path") != raw_path:
        _fail("table_raw_file_mismatch", f"{path}/path", raw_path)
    encoding = _string(row["encoding"], f"{path}/encoding").lower()
    if encoding not in SUPPORTED_ENCODINGS:
        _fail("table_encoding_unsupported", f"{path}/encoding", encoding)
    delimiter = row["delimiter"]
    if delimiter not in SUPPORTED_DELIMITERS:
        _fail("table_delimiter_unsupported", f"{path}/delimiter", repr(delimiter))
    header_row = row["header_row"]
    if isinstance(header_row, bool) or not isinstance(header_row, int) or not 1 <= header_row <= 100:
        _fail("table_header_row_invalid", f"{path}/header_row", repr(header_row))
    filters = _expect_object(row["filters"], f"{path}/filters")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in filters.items()):
        _fail("table_filter_invalid", f"{path}/filters", "filters must map strings to strings")
    load_filter_column = _string(row["load_filter_column"], f"{path}/load_filter_column")
    if filters.get(load_filter_column) != external_case:
        _fail(
            "load_filter_mismatch",
            f"{path}/filters/{load_filter_column}",
            f"expected {external_case!r}",
        )
    columns = _expect_object(row["columns"], f"{path}/columns")
    _exact_keys(columns, expected_columns, f"{path}/columns")
    normalized_columns = {
        key: _string(value, f"{path}/columns/{key}") for key, value in columns.items()
    }
    if len(set(normalized_columns.values())) != len(normalized_columns):
        _fail("table_column_mapping_ambiguous", f"{path}/columns", "raw headers must be unique")
    return {
        "encoding": encoding,
        "delimiter": delimiter,
        "header_row": header_row,
        "filters": dict(filters),
        "load_filter_column": load_filter_column,
        "columns": normalized_columns,
    }


def _read_filtered_rows(path: Path, table: Mapping[str, Any], table_path: str) -> list[dict[str, str]]:
    try:
        handle = path.open(encoding=str(table["encoding"]), newline="")
    except (OSError, UnicodeError) as exc:
        _fail("table_unreadable", table_path, exc.__class__.__name__)
    with handle:
        for _ in range(int(table["header_row"]) - 1):
            if handle.readline() == "":
                _fail("table_header_missing", table_path, "header_row exceeds file length")
        reader = csv.DictReader(handle, delimiter=str(table["delimiter"]))
        raw_headers = reader.fieldnames
        if not raw_headers:
            _fail("table_header_missing", table_path, "CSV header is missing")
        headers = [header.strip() for header in raw_headers]
        if any(not header for header in headers) or len(set(headers)) != len(headers):
            _fail("table_header_invalid", table_path, "headers must be non-empty and unique")
        required = set(table["columns"].values()) | set(table["filters"])
        missing = sorted(required - set(headers))
        if missing:
            _fail("table_column_missing", table_path, repr(missing))
        selected: list[dict[str, str]] = []
        for row_index, raw_row in enumerate(reader, start=int(table["header_row"]) + 1):
            if None in raw_row:
                _fail("table_row_width_invalid", f"{table_path}/row/{row_index}", "extra columns")
            row = {
                str(key).strip(): "" if value is None else str(value).strip()
                for key, value in raw_row.items()
            }
            if all(row.get(key) == value for key, value in table["filters"].items()):
                selected.append(row)
        if not selected:
            _fail("table_filter_selected_no_rows", table_path, "no rows matched filters")
        return selected


def _parse_six(row: Mapping[str, str], columns: Mapping[str, str], components: Sequence[str], path: str) -> list[float]:
    return [_finite(row.get(columns[name]), f"{path}/{name}") for name in components]


def _validate_release_and_offset_semantics(
    semantics: Mapping[str, Any],
    member_rows: Mapping[str, Mapping[str, Any]],
    global_transform: Sequence[Sequence[float]],
) -> None:
    releases = _expect_list(semantics["releases"], "/semantic_mapping/releases")
    offsets = _expect_list(semantics["rigid_offsets"], "/semantic_mapping/rigid_offsets")
    release_map: dict[str, Mapping[str, Any]] = {}
    for index, value in enumerate(releases):
        path = f"/semantic_mapping/releases/{index}"
        row = _expect_object(value, path)
        _exact_keys(
            row,
            {"external_member_id", "raw_i", "raw_j", "canonical_i", "canonical_j"},
            path,
        )
        external_id = _string(row["external_member_id"], f"{path}/external_member_id")
        if external_id in release_map:
            _fail("duplicate_release_mapping", path, external_id)
        release_map[external_id] = row
    offset_map: dict[str, Mapping[str, Any]] = {}
    for index, value in enumerate(offsets):
        path = f"/semantic_mapping/rigid_offsets/{index}"
        row = _expect_object(value, path)
        _exact_keys(
            row,
            {
                "external_member_id",
                "coordinate_system",
                "raw_unit",
                "raw_i",
                "raw_j",
                "canonical_i_m",
                "canonical_j_m",
            },
            path,
        )
        external_id = _string(row["external_member_id"], f"{path}/external_member_id")
        if external_id in offset_map:
            _fail("duplicate_offset_mapping", path, external_id)
        offset_map[external_id] = row
    expected_ids = set(member_rows)
    if set(release_map) != expected_ids:
        _fail("release_mapping_coverage_mismatch", "/semantic_mapping/releases", repr(sorted(expected_ids)))
    if set(offset_map) != expected_ids:
        _fail("offset_mapping_coverage_mismatch", "/semantic_mapping/rigid_offsets", repr(sorted(expected_ids)))

    for external_id, member in member_rows.items():
        reversed_ends = member["raw_i_maps_to"] == "j"
        release = release_map[external_id]
        raw_i = _six_bools(release["raw_i"], f"/semantic_mapping/releases/{external_id}/raw_i")
        raw_j = _six_bools(release["raw_j"], f"/semantic_mapping/releases/{external_id}/raw_j")
        canonical_i = _six_bools(
            release["canonical_i"], f"/semantic_mapping/releases/{external_id}/canonical_i"
        )
        canonical_j = _six_bools(
            release["canonical_j"], f"/semantic_mapping/releases/{external_id}/canonical_j"
        )
        if any((*raw_i[:3], *raw_j[:3], *canonical_i[:3], *canonical_j[:3])):
            _fail(
                "translational_release_unsupported",
                "/semantic_mapping/releases",
                external_id,
            )
        expected_i, expected_j = (raw_j, raw_i) if reversed_ends else (raw_i, raw_j)
        if expected_i != canonical_i or expected_j != canonical_j:
            _fail("release_mapping_not_equivalent", "/semantic_mapping/releases", external_id)

        offset = offset_map[external_id]
        if offset["coordinate_system"] != "global":
            _fail("offset_coordinate_system_unsupported", "/semantic_mapping/rigid_offsets", external_id)
        raw_unit = offset["raw_unit"]
        if raw_unit not in {"m", "mm"}:
            _fail("offset_unit_unsupported", "/semantic_mapping/rigid_offsets", repr(raw_unit))
        scale = 1.0 if raw_unit == "m" else 0.001
        raw_i_vector = _transform3(
            global_transform,
            _vector3(offset["raw_i"], f"/semantic_mapping/rigid_offsets/{external_id}/raw_i"),
        )
        raw_j_vector = _transform3(
            global_transform,
            _vector3(offset["raw_j"], f"/semantic_mapping/rigid_offsets/{external_id}/raw_j"),
        )
        raw_i_m = [value * scale for value in raw_i_vector]
        raw_j_m = [value * scale for value in raw_j_vector]
        canonical_i_m = _vector3(
            offset["canonical_i_m"], f"/semantic_mapping/rigid_offsets/{external_id}/canonical_i_m"
        )
        canonical_j_m = _vector3(
            offset["canonical_j_m"], f"/semantic_mapping/rigid_offsets/{external_id}/canonical_j_m"
        )
        expected_offset_i, expected_offset_j = (
            (raw_j_m, raw_i_m) if reversed_ends else (raw_i_m, raw_j_m)
        )
        if any(abs(a - b) > 1.0e-12 for a, b in zip(expected_offset_i, canonical_i_m)) or any(
            abs(a - b) > 1.0e-12 for a, b in zip(expected_offset_j, canonical_j_m)
        ):
            _fail("offset_mapping_not_equivalent", "/semantic_mapping/rigid_offsets", external_id)


def _validate_semantics(
    value: Any,
    *,
    bindings: Mapping[str, Any],
    member_rows: Mapping[str, Mapping[str, Any]],
    global_transform: Sequence[Sequence[float]],
) -> dict[str, Any]:
    semantics = _expect_object(value, "/semantic_mapping")
    _exact_keys(
        semantics,
        {
            "releases",
            "rigid_offsets",
            "load",
            "mass_source",
            "solver_settings",
            "unmapped_records",
        },
        "/semantic_mapping",
    )
    unmapped = _expect_list(semantics["unmapped_records"], "/semantic_mapping/unmapped_records")
    if unmapped:
        _fail("unmapped_semantic_records", "/semantic_mapping/unmapped_records", repr(unmapped))

    load = _expect_object(semantics["load"], "/semantic_mapping/load")
    _exact_keys(
        load,
        {"external_case", "canonical_load_pattern_id", "canonical_load_combination_id", "equivalent"},
        "/semantic_mapping/load",
    )
    external_case = _string(load["external_case"], "/semantic_mapping/load/external_case")
    if load["canonical_load_pattern_id"] != bindings["load_pattern_id"]:
        _fail("load_mapping_mismatch", "/semantic_mapping/load/canonical_load_pattern_id", "binding mismatch")
    if load["canonical_load_combination_id"] != bindings["load_combination_id"]:
        _fail(
            "load_mapping_mismatch",
            "/semantic_mapping/load/canonical_load_combination_id",
            "binding mismatch",
        )
    if _bool(load["equivalent"], "/semantic_mapping/load/equivalent") is not True:
        _fail("load_mapping_not_equivalent", "/semantic_mapping/load/equivalent", "must be true")

    mass = _expect_object(semantics["mass_source"], "/semantic_mapping/mass_source")
    _exact_keys(
        mass,
        {"participates_in_static_solution", "external_definition", "canonical_definition", "equivalent"},
        "/semantic_mapping/mass_source",
    )
    if _bool(mass["participates_in_static_solution"], "/semantic_mapping/mass_source/participates_in_static_solution"):
        _fail("mass_source_affects_static_solution", "/semantic_mapping/mass_source", "unsupported")
    _string(mass["external_definition"], "/semantic_mapping/mass_source/external_definition")
    _string(mass["canonical_definition"], "/semantic_mapping/mass_source/canonical_definition")
    if _bool(mass["equivalent"], "/semantic_mapping/mass_source/equivalent") is not True:
        _fail("mass_source_mapping_not_equivalent", "/semantic_mapping/mass_source/equivalent", "must be true")

    solver = _expect_object(semantics["solver_settings"], "/semantic_mapping/solver_settings")
    _exact_keys(
        solver,
        {
            "analysis_type",
            "geometric_nonlinearity",
            "material_nonlinearity",
            "p_delta",
            "shear_deformation",
            "equation_solver",
            "equivalent",
        },
        "/semantic_mapping/solver_settings",
    )
    if solver["analysis_type"] != "linear_static":
        _fail("solver_analysis_type_unsupported", "/semantic_mapping/solver_settings/analysis_type", repr(solver["analysis_type"]))
    for field in ("geometric_nonlinearity", "material_nonlinearity", "p_delta"):
        if _bool(solver[field], f"/semantic_mapping/solver_settings/{field}"):
            _fail("solver_setting_unsupported", f"/semantic_mapping/solver_settings/{field}", "must be false")
    if solver["shear_deformation"] != "timoshenko_enabled":
        _fail("solver_setting_unsupported", "/semantic_mapping/solver_settings/shear_deformation", repr(solver["shear_deformation"]))
    _string(solver["equation_solver"], "/semantic_mapping/solver_settings/equation_solver")
    if _bool(solver["equivalent"], "/semantic_mapping/solver_settings/equivalent") is not True:
        _fail("solver_settings_not_equivalent", "/semantic_mapping/solver_settings/equivalent", "must be true")

    _validate_release_and_offset_semantics(semantics, member_rows, global_transform)
    return {"external_case": external_case}


def _parse_manifest(
    manifest: Mapping[str, Any],
    *,
    package: Mapping[str, Any],
    package_root: Path,
) -> dict[str, Any]:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "adapter_id",
            "case_id",
            "modeling_convention_id",
            "reference_id",
            "solver",
            "bindings",
            "raw_files",
            "units",
            "axes",
            "entity_mapping",
            "semantic_mapping",
            "tables",
            "unsupported_features",
            "warnings",
        },
        "/",
    )
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        _fail("manifest_schema_invalid", "/schema_version", repr(manifest["schema_version"]))
    adapter_id = _stable_id(manifest["adapter_id"], "/adapter_id")
    case_id = _stable_id(manifest["case_id"], "/case_id")
    if package.get("case_id") != case_id:
        _fail("operator_package_case_mismatch", "/case_id", repr(package.get("case_id")))
    convention_id = _stable_id(manifest["modeling_convention_id"], "/modeling_convention_id")
    if package.get("modeling_convention_id") != convention_id:
        _fail(
            "operator_package_convention_mismatch",
            "/modeling_convention_id",
            repr(package.get("modeling_convention_id")),
        )
    reference_id = _stable_id(manifest["reference_id"], "/reference_id")

    solver = _expect_object(manifest["solver"], "/solver")
    _exact_keys(solver, {"tool", "version", "run_id", "origin"}, "/solver")
    tool = _string(solver["tool"], "/solver/tool")
    if tool not in SUPPORTED_TOOLS:
        _fail("commercial_tool_unsupported", "/solver/tool", tool)
    version = _string(solver["version"], "/solver/version")
    run_id = _string(solver["run_id"], "/solver/run_id")
    if solver["origin"] != "operator_attached_external":
        _fail("solver_origin_invalid", "/solver/origin", repr(solver["origin"]))
    package_solvers = _expect_list(package.get("reference_solvers"), "/operator_package/reference_solvers")
    matched_solver = [
        row
        for row in package_solvers
        if isinstance(row, dict)
        and _normalized_solver_name(row.get("engine_name"), "/operator_package/reference_solvers/engine_name")
        == tool
        and str(row.get("engine_version", "")).strip() == version
    ]
    if len(matched_solver) != 1:
        _fail("solver_not_uniquely_declared_by_operator_package", "/solver", f"{tool}@{version}")

    bindings = _expect_object(manifest["bindings"], "/bindings")
    _exact_keys(bindings, {"model_content_hash", "load_pattern_id", "load_combination_id"}, "/bindings")
    model_content_hash = _hash(bindings["model_content_hash"], "/bindings/model_content_hash")
    load_pattern = bindings["load_pattern_id"]
    load_combination = bindings["load_combination_id"]
    if (load_pattern is None) == (load_combination is None):
        _fail("load_binding_invalid", "/bindings", "exactly one load identity is required")
    if load_pattern is not None:
        load_pattern = _stable_id(load_pattern, "/bindings/load_pattern_id")
    if load_combination is not None:
        load_combination = _stable_id(load_combination, "/bindings/load_combination_id")
    normalized_bindings = {
        "model_content_hash": model_content_hash,
        "load_pattern_id": load_pattern,
        "load_combination_id": load_combination,
    }

    raw_files = _expect_object(manifest["raw_files"], "/raw_files")
    roles = {"model_input", "node_displacements", "node_reactions", "member_end_forces"}
    _exact_keys(raw_files, roles, "/raw_files")
    verified_files = {
        role: _verify_raw_file(role, raw_files[role], package=package, package_root=package_root)
        for role in sorted(roles)
    }

    units = _expect_object(manifest["units"], "/units")
    _exact_keys(units, {"translation", "rotation", "force", "moment"}, "/units")
    if units["translation"] not in {"m", "mm"}:
        _fail("translation_unit_unsupported", "/units/translation", repr(units["translation"]))
    if units["rotation"] != "rad":
        _fail("rotation_unit_unsupported", "/units/rotation", repr(units["rotation"]))
    if units["force"] not in {"N", "kN"}:
        _fail("force_unit_unsupported", "/units/force", repr(units["force"]))
    if units["moment"] not in {"N*m", "kN*m"}:
        _fail("moment_unit_unsupported", "/units/moment", repr(units["moment"]))

    axes = _expect_object(manifest["axes"], "/axes")
    _exact_keys(
        axes,
        {
            "node_displacement_coordinate_system",
            "node_reaction_coordinate_system",
            "member_end_force_coordinate_system",
            "member_end_force_action",
            "raw_global_to_canonical_transform",
        },
        "/axes",
    )
    expected_axes = {
        "node_displacement_coordinate_system": "global",
        "node_reaction_coordinate_system": "global",
        "member_end_force_coordinate_system": "member_local",
        "member_end_force_action": "native_result_ir_compatible",
    }
    for field, expected in expected_axes.items():
        if axes[field] != expected:
            _fail("axis_contract_unsupported", f"/axes/{field}", repr(axes[field]))
    global_transform = _proper_signed_permutation(
        axes["raw_global_to_canonical_transform"], "/axes/raw_global_to_canonical_transform"
    )

    mappings = _expect_object(manifest["entity_mapping"], "/entity_mapping")
    _exact_keys(mappings, {"nodes", "members"}, "/entity_mapping")
    node_items = _expect_list(mappings["nodes"], "/entity_mapping/nodes")
    if not 2 <= len(node_items) <= 16:
        _fail("node_mapping_count_out_of_bounds", "/entity_mapping/nodes", str(len(node_items)))
    node_rows: dict[str, dict[str, Any]] = {}
    canonical_nodes: set[str] = set()
    for index, value in enumerate(node_items):
        path = f"/entity_mapping/nodes/{index}"
        row = _expect_object(value, path)
        _exact_keys(row, {"external_id", "canonical_id"}, path)
        external_id = _string(row["external_id"], f"{path}/external_id")
        canonical_id = _stable_id(row["canonical_id"], f"{path}/canonical_id")
        if external_id in node_rows or canonical_id in canonical_nodes:
            _fail("node_mapping_not_bijective", path, f"{external_id!r}->{canonical_id!r}")
        node_rows[external_id] = {"canonical_id": canonical_id}
        canonical_nodes.add(canonical_id)

    member_items = _expect_list(mappings["members"], "/entity_mapping/members")
    if not 1 <= len(member_items) <= 32:
        _fail("member_mapping_count_out_of_bounds", "/entity_mapping/members", str(len(member_items)))
    member_rows: dict[str, dict[str, Any]] = {}
    canonical_members: set[str] = set()
    for index, value in enumerate(member_items):
        path = f"/entity_mapping/members/{index}"
        row = _expect_object(value, path)
        _exact_keys(
            row,
            {
                "external_id",
                "canonical_id",
                "raw_i_end",
                "raw_j_end",
                "raw_i_maps_to",
                "raw_local_to_canonical_transform",
            },
            path,
        )
        external_id = _string(row["external_id"], f"{path}/external_id")
        canonical_id = _stable_id(row["canonical_id"], f"{path}/canonical_id")
        raw_i_end = _string(row["raw_i_end"], f"{path}/raw_i_end")
        raw_j_end = _string(row["raw_j_end"], f"{path}/raw_j_end")
        if raw_i_end == raw_j_end:
            _fail("member_end_mapping_ambiguous", path, raw_i_end)
        raw_i_maps_to = row["raw_i_maps_to"]
        if raw_i_maps_to not in {"i", "j"}:
            _fail("member_direction_mapping_invalid", f"{path}/raw_i_maps_to", repr(raw_i_maps_to))
        local_transform = _proper_signed_permutation(
            row["raw_local_to_canonical_transform"], f"{path}/raw_local_to_canonical_transform"
        )
        if external_id in member_rows or canonical_id in canonical_members:
            _fail("member_mapping_not_bijective", path, f"{external_id!r}->{canonical_id!r}")
        member_rows[external_id] = {
            "canonical_id": canonical_id,
            "raw_i_end": raw_i_end,
            "raw_j_end": raw_j_end,
            "raw_i_maps_to": raw_i_maps_to,
            "local_transform": local_transform,
        }
        canonical_members.add(canonical_id)

    semantic_result = _validate_semantics(
        manifest["semantic_mapping"],
        bindings=normalized_bindings,
        member_rows=member_rows,
        global_transform=global_transform,
    )

    unsupported = _expect_list(manifest["unsupported_features"], "/unsupported_features")
    if unsupported:
        _fail("unsupported_features_present", "/unsupported_features", repr(unsupported))
    warnings = _expect_list(manifest["warnings"], "/warnings")
    if any(not isinstance(item, str) or not item.strip() for item in warnings):
        _fail("warnings_invalid", "/warnings", "warnings must be non-empty strings")

    tables = _expect_object(manifest["tables"], "/tables")
    _exact_keys(tables, {"node_displacements", "node_reactions", "member_end_forces"}, "/tables")
    external_case = semantic_result["external_case"]
    parsed_tables = {
        "node_displacements": _validate_table(
            "node_displacements",
            tables["node_displacements"],
            raw_path=verified_files["node_displacements"][0],
            expected_columns={"node_id", *DISPLACEMENT_COMPONENTS},
            external_case=external_case,
        ),
        "node_reactions": _validate_table(
            "node_reactions",
            tables["node_reactions"],
            raw_path=verified_files["node_reactions"][0],
            expected_columns={"node_id", *SIX_COMPONENTS},
            external_case=external_case,
        ),
        "member_end_forces": _validate_table(
            "member_end_forces",
            tables["member_end_forces"],
            raw_path=verified_files["member_end_forces"][0],
            expected_columns={"member_id", "end", *SIX_COMPONENTS},
            external_case=external_case,
        ),
    }
    return {
        "adapter_id": adapter_id,
        "case_id": case_id,
        "modeling_convention_id": convention_id,
        "reference_id": reference_id,
        "tool": tool,
        "version": version,
        "run_id": run_id,
        "bindings": normalized_bindings,
        "units": dict(units),
        "global_transform": global_transform,
        "node_rows": node_rows,
        "member_rows": member_rows,
        "verified_files": verified_files,
        "tables": parsed_tables,
        "warnings": list(warnings),
    }


def build_reference_ir(
    *,
    operator_package_path: Path,
    adapter_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build strict ReferenceIR and a non-promoting normalization receipt."""

    package_path = operator_package_path.resolve(strict=True)
    manifest_path = adapter_manifest_path.resolve(strict=True)
    package = load_json_strict(package_path)
    manifest = load_json_strict(manifest_path)

    # Reuse the existing commercial operator/package policy.  Raw normalization is
    # allowed before the normalized output checksum exists; every raw byte remains
    # permission- and checksum-gated.
    from scripts.build_phase4_commercial_operator_reference_ingest_validator import (  # type: ignore[import-not-found]
        validate_operator_reference_package,
    )
    from scripts.release_evidence_metadata import git_head  # type: ignore[import-not-found]

    raw_preflight = validate_operator_reference_package(
        package,
        package_root=package_path.parent,
        verify_file_hashes=True,
        require_normalized_results=False,
        require_two_reference_solvers=False,
    )
    if raw_preflight["blockers"] or raw_preflight.get("raw_preflight_pass") is not True:
        _fail(
            "operator_package_raw_preflight_failed",
            "/operator_package",
            repr(raw_preflight["blockers"]),
        )

    parsed = _parse_manifest(manifest, package=package, package_root=package_path.parent)
    displacement_table = parsed["tables"]["node_displacements"]
    reaction_table = parsed["tables"]["node_reactions"]
    force_table = parsed["tables"]["member_end_forces"]
    displacement_rows = _read_filtered_rows(
        parsed["verified_files"]["node_displacements"][1],
        displacement_table,
        "/tables/node_displacements",
    )
    reaction_rows = _read_filtered_rows(
        parsed["verified_files"]["node_reactions"][1],
        reaction_table,
        "/tables/node_reactions",
    )
    force_rows = _read_filtered_rows(
        parsed["verified_files"]["member_end_forces"][1],
        force_table,
        "/tables/member_end_forces",
    )

    node_values: dict[str, dict[str, Any]] = {
        external_id: {"node_id": row["canonical_id"]}
        for external_id, row in parsed["node_rows"].items()
    }
    for table_name, rows, table, result_key, components in (
        (
            "node_displacements",
            displacement_rows,
            displacement_table,
            "displacement",
            DISPLACEMENT_COMPONENTS,
        ),
        ("node_reactions", reaction_rows, reaction_table, "reaction", SIX_COMPONENTS),
    ):
        id_column = table["columns"]["node_id"]
        for row_index, row in enumerate(rows):
            external_id = row.get(id_column, "")
            if external_id not in node_values:
                _fail("unknown_external_node", f"/tables/{table_name}/row/{row_index}", external_id)
            if result_key in node_values[external_id]:
                _fail("duplicate_node_result", f"/tables/{table_name}/row/{row_index}", external_id)
            raw_values = _parse_six(
                row,
                table["columns"],
                components,
                f"/tables/{table_name}/row/{row_index}",
            )
            node_values[external_id][result_key] = _transform6(parsed["global_transform"], raw_values)
    for external_id, row in node_values.items():
        if set(row) != {"node_id", "displacement", "reaction"}:
            _fail("node_result_coverage_mismatch", "/entity_mapping/nodes", external_id)

    member_values: dict[str, dict[str, Any]] = {
        external_id: {"member_id": row["canonical_id"]}
        for external_id, row in parsed["member_rows"].items()
    }
    member_id_column = force_table["columns"]["member_id"]
    end_column = force_table["columns"]["end"]
    for row_index, row in enumerate(force_rows):
        external_id = row.get(member_id_column, "")
        mapping = parsed["member_rows"].get(external_id)
        if mapping is None:
            _fail("unknown_external_member", f"/tables/member_end_forces/row/{row_index}", external_id)
        raw_end = row.get(end_column, "")
        if raw_end == mapping["raw_i_end"]:
            raw_slot = "i"
        elif raw_end == mapping["raw_j_end"]:
            raw_slot = "j"
        else:
            _fail("unknown_member_end", f"/tables/member_end_forces/row/{row_index}", raw_end)
        canonical_slot = raw_slot if mapping["raw_i_maps_to"] == "i" else ("j" if raw_slot == "i" else "i")
        result_key = f"end_{canonical_slot}_force"
        if result_key in member_values[external_id]:
            _fail("duplicate_member_end_result", f"/tables/member_end_forces/row/{row_index}", external_id)
        raw_values = _parse_six(
            row,
            force_table["columns"],
            SIX_COMPONENTS,
            f"/tables/member_end_forces/row/{row_index}",
        )
        member_values[external_id][result_key] = _transform6(mapping["local_transform"], raw_values)
    for external_id, row in member_values.items():
        if set(row) != {"member_id", "end_i_force", "end_j_force"}:
            _fail("member_result_coverage_mismatch", "/entity_mapping/members", external_id)

    export_rows = [
        {"role": role, "path": values[0], "sha256": values[2]}
        for role, values in sorted(parsed["verified_files"].items())
    ]
    export_set_hash = _sha256_bytes(_canonical_json_bytes(export_rows))
    reference = {
        "schema_version": REFERENCE_SCHEMA,
        "reference_id": parsed["reference_id"],
        "source": {
            "tool": parsed["tool"],
            "version": parsed["version"],
            "origin": "operator_attached_external",
            "export_sha256": export_set_hash,
        },
        "bindings": parsed["bindings"],
        "axes": {
            "node_displacement": "global_ux_uy_uz_rx_ry_rz",
            "node_reaction": "global_fx_fy_fz_mx_my_mz",
            "member_end_force": "member_local_fx_fy_fz_mx_my_mz_i_then_j",
            "sign_convention": "native_result_ir_compatible",
        },
        "units": parsed["units"],
        "nodes": sorted(node_values.values(), key=lambda row: row["node_id"]),
        "members": sorted(member_values.values(), key=lambda row: row["member_id"]),
        "claim_boundary": REFERENCE_CLAIM_BOUNDARY,
    }
    _validate_existing_reference_contract(reference)
    reference_bytes = _canonical_json_bytes(reference)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "adapter_id": parsed["adapter_id"],
        "case_id": parsed["case_id"],
        "modeling_convention_id": parsed["modeling_convention_id"],
        "source_commit_sha": git_head(REPO_ROOT),
        "adapter_implementation_sha256": _sha256_file(Path(__file__).resolve()),
        "reference_schema_sha256": _sha256_file(REFERENCE_SCHEMA_PATH),
        "operator_package_sha256": _sha256_file(package_path),
        "adapter_manifest_sha256": _sha256_file(manifest_path),
        "reference_ir_canonical_sha256": _sha256_bytes(reference_bytes),
        "source_export_set_sha256": export_set_hash,
        "source_files": export_rows,
        "tool": parsed["tool"],
        "version": parsed["version"],
        "run_id": parsed["run_id"],
        "row_counts": {
            "nodes": len(reference["nodes"]),
            "members": len(reference["members"]),
            "component_rows": len(reference["nodes"]) * 12 + len(reference["members"]) * 12,
        },
        "semantic_gates": {
            "units": "mapped",
            "global_axes": "mapped",
            "member_local_axes": "mapped",
            "end_releases": "matched",
            "rigid_offsets": "matched",
            "load_identity": "matched",
            "mass_source": "declared_not_participating_in_linear_static",
            "solver_settings": "matched_bounded_linear_static",
            "unmapped_records": 0,
        },
        "warnings": parsed["warnings"],
        "authority": {
            "external_solver_execution": "operator_attached_not_independently_observed",
            "same_model_mapping": "operator_declared_manifest_consistent_not_independently_verified",
            "comparison": "not_executed",
            "external_validation": "not_established",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": (
            "Raw-byte, mapping, semantic-equivalence, and ReferenceIR normalization receipt only; "
            "not proof of a commercial solver run, independent reproduction, physical validation, "
            "design authority, or release eligibility."
        ),
    }
    return reference, receipt


def build_comparison_ir_with_native_cli(
    *,
    reference_ir: Mapping[str, Any],
    native_result_path: Path,
    structural_cli_path: Path,
    comparison_id: str,
) -> dict[str, Any]:
    """Delegate ComparisonIR construction to the existing strict Rust CLI."""

    comparison_id = _stable_id(comparison_id, "/comparison_id")
    result_path = native_result_path.resolve(strict=True)
    cli_path = structural_cli_path.resolve(strict=True)
    if not result_path.is_file():
        _fail("native_result_missing", str(native_result_path), "not a file")
    if not cli_path.is_file():
        _fail("structural_cli_missing", str(structural_cli_path), "not a file")
    with tempfile.TemporaryDirectory(prefix="commercial-frame3d-reference-") as temp_dir:
        reference_path = Path(temp_dir) / "reference.json"
        reference_path.write_bytes(_canonical_json_bytes(reference_ir) + b"\n")
        try:
            completed = subprocess.run(
                [
                    str(cli_path),
                    "result",
                    "compare-frame3d",
                    str(result_path),
                    str(reference_path),
                    "--comparison-id",
                    comparison_id,
                    "--output",
                    "comparison-ir",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            _fail("native_comparison_timeout", "/comparison", "120 seconds")
        except OSError as exc:
            _fail("native_comparison_unavailable", "/comparison", exc.__class__.__name__)
    if completed.returncode not in {0, 2}:
        _fail(
            "native_comparison_failed",
            "/comparison",
            f"exit={completed.returncode}; stderr={completed.stderr.strip()[:300]!r}",
        )
    try:
        comparison = json.loads(completed.stdout, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, CommercialExportError):
        _fail("native_comparison_output_invalid", "/comparison", "CLI did not emit strict JSON")
    if not isinstance(comparison, dict) or comparison.get("schema_version") != (
        "structural-native-linear-frame3d-comparison-ir.v1"
    ):
        _fail("native_comparison_output_invalid", "/comparison", "unexpected schema")
    return comparison
