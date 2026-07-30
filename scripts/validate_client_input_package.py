#!/usr/bin/env python3
"""Validate a client input directory or zip before workstation delivery processing."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from typing import Any
import zipfile

from jsonschema import Draft202012Validator


SCHEMA_VERSION = "client-input-validation-report.v1"
DEFAULT_REPORT_OUT = Path("implementation/phase1/client_input_validation_report.json")
REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).resolve()
SCHEMA_PATH = REPO_ROOT / (
    "src/structural_analysis/schemas/"
    "client_input_validation_report_v1.schema.json"
)
MAX_FILE_COUNT = 10_000
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
SOURCE_KINDS = {
    "operator_or_local_input",
    "repository_reference_fixture",
}
ISSUE_REASON_CODES = {
    "input_package_missing_or_empty": "ERR_CLIENT_INPUT_MISSING_OR_EMPTY",
    "json_or_csv_data_file_missing": "ERR_CLIENT_INPUT_DATA_FILE_MISSING",
    "data_file_parse_failed": "ERR_CLIENT_INPUT_DATA_FILE_PARSE_FAILED",
    "model_geometry_missing": "ERR_CLIENT_INPUT_MODEL_GEOMETRY_MISSING",
    "model_coordinates_invalid_or_missing": "ERR_CLIENT_INPUT_COORDINATES_INVALID",
    "model_topology_invalid": "ERR_CLIENT_INPUT_TOPOLOGY_INVALID",
    "member_or_element_id_missing": "ERR_CLIENT_INPUT_MEMBER_ID_MISSING",
    "unit_information_missing": "ERR_CLIENT_INPUT_UNITS_MISSING",
    "load_case_or_combination_missing": "ERR_CLIENT_INPUT_LOAD_CASE_MISSING",
    "revision_information_missing": "ERR_CLIENT_INPUT_REVISION_MISSING",
    "proxy_or_fallback_label_missing": "ERR_CLIENT_INPUT_PROXY_LABEL_MISSING",
    "unsafe_archive_path": "ERR_CLIENT_INPUT_UNSAFE_ARCHIVE_PATH",
    "archive_symlink_rejected": "ERR_CLIENT_INPUT_ARCHIVE_SYMLINK",
    "encrypted_archive_member_rejected": "ERR_CLIENT_INPUT_ARCHIVE_ENCRYPTED",
    "input_symlink_rejected": "ERR_CLIENT_INPUT_SYMLINK",
    "input_file_count_exceeded": "ERR_CLIENT_INPUT_FILE_COUNT_EXCEEDED",
    "input_file_size_exceeded": "ERR_CLIENT_INPUT_FILE_SIZE_EXCEEDED",
    "input_total_size_exceeded": "ERR_CLIENT_INPUT_TOTAL_SIZE_EXCEEDED",
    "duplicate_archive_member": "ERR_CLIENT_INPUT_ARCHIVE_DUPLICATE",
    "repository_reference_fixture_directory_required": (
        "ERR_CLIENT_INPUT_REFERENCE_FIXTURE_DIRECTORY_REQUIRED"
    ),
}


class ClientInputValidationError(ValueError):
    """Stable fail-closed input-package validation error."""

    def __init__(self, issue: str) -> None:
        super().__init__(issue)
        self.issue = issue


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _source_row(path: Path, root: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    return {
        "path": rel,
        "bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in {float("inf"), float("-inf")}


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        rows.append(value)
        for item in value.values():
            rows.extend(_walk_dicts(item))
    elif isinstance(value, list):
        for item in value:
            rows.extend(_walk_dicts(item))
    return rows


def _has_nonempty_value(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value) and any(
            _has_nonempty_value(item) for item in value.values()
        )
    if isinstance(value, (list, tuple, set)):
        return bool(value) and any(_has_nonempty_value(item) for item in value)
    return True


def _alias_value(row: dict[str, Any], aliases: set[str]) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    return None


def _identifier(value: Any) -> str | None:
    if not _has_nonempty_value(value):
        return None
    normalized = str(value).strip()
    return normalized if normalized else None


def _extract_candidate_lists(payload: Any, names: set[str]) -> list[list[Any]]:
    lists: list[list[Any]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in names and isinstance(value, list):
                lists.append(value)
            lists.extend(_extract_candidate_lists(value, names))
    elif isinstance(payload, list):
        for item in payload:
            lists.extend(_extract_candidate_lists(item, names))
    return lists


def _has_units(payload: Any) -> bool:
    for row in _walk_dicts(payload):
        lowered = {str(key).lower(): value for key, value in row.items()}
        if any(
            key in lowered and _has_nonempty_value(lowered[key])
            for key in ("units", "unit", "length_unit", "force_unit")
        ):
            return True
    return False


def _has_revision(payload: Any) -> bool:
    for row in _walk_dicts(payload):
        lowered = {str(key).lower(): value for key, value in row.items()}
        if any(
            key in lowered and _has_nonempty_value(lowered[key])
            for key in ("revision", "drawing_revision", "rev", "version")
        ):
            return True
    return False


def _has_load_case(payload: Any) -> bool:
    for row in _walk_dicts(payload):
        lowered = {str(key).lower(): value for key, value in row.items()}
        if any(
            key in lowered
            and (
                _has_nonempty_value(lowered[key])
                or (
                    isinstance(lowered[key], dict)
                    and any(_identifier(item) for item in lowered[key])
                )
            )
            for key in (
                "load_case",
                "load_cases",
                "loadcomb",
                "load_combination",
                "load_combinations",
                "loads",
            )
        ):
            return True
    return False


def _proxy_label_explicit(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    if "proxy" not in text and "fallback" not in text:
        return True
    return "proxy_labeled" in text or "fallback_labeled" in text or "explicitly labeled" in text


def _json_file_checks(path: Path, root: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "path": path.relative_to(root).as_posix(),
            "valid_json": False,
            "error": exc.__class__.__name__,
        }

    node_lists = _extract_candidate_lists(payload, {"nodes", "node"})
    element_lists = _extract_candidate_lists(payload, {"elements", "members", "member", "edges"})
    geometry_present = bool(node_lists and element_lists)
    node_rows = [
        node
        for nodes in node_lists
        for node in nodes
        if isinstance(node, dict)
    ]
    element_rows = [
        element
        for elements in element_lists
        for element in elements
        if isinstance(element, dict)
    ]
    node_ids: set[str] = set()
    node_coordinates: dict[str, tuple[float, float, float]] = {}
    coordinates_valid = bool(node_rows)
    for node in node_rows:
        node_id = _identifier(_alias_value(node, {"id", "node_id", "nid"}))
        if node_id is not None:
            node_ids.add(node_id)
        keys = {str(key).lower(): value for key, value in node.items()}
        direct_coordinates = all(
            _finite_number(keys.get(axis)) for axis in ("x", "y", "z")
        )
        coords = keys.get("coords") or keys.get("coordinates")
        vector_coordinates = bool(
            isinstance(coords, list)
            and len(coords) >= 3
            and all(_finite_number(item) for item in coords[:3])
        )
        if node_id and (direct_coordinates or vector_coordinates):
            values = (
                (keys["x"], keys["y"], keys["z"])
                if direct_coordinates
                else (coords[0], coords[1], coords[2])
            )
            node_coordinates[node_id] = tuple(float(value) for value in values)
        if not (node_id and (direct_coordinates or vector_coordinates)):
            coordinates_valid = False

    member_ids: set[str] = set()
    member_endpoints: list[tuple[str, str]] = []
    for element in element_rows:
        member_id = _identifier(
            _alias_value(element, {"id", "member_id", "element_id", "eid"})
        )
        node_i = _identifier(
            _alias_value(
                element,
                {"i", "node_i", "start_node", "node1", "node_1", "source"},
            )
        )
        node_j = _identifier(
            _alias_value(
                element,
                {"j", "node_j", "end_node", "node2", "node_2", "target"},
            )
        )
        if member_id is not None:
            member_ids.add(member_id)
        if node_i is not None and node_j is not None:
            member_endpoints.append((node_i, node_j))
    member_identity_present = bool(element_rows) and len(member_ids) == len(
        element_rows
    )
    coordinates_valid = bool(
        coordinates_valid and len(node_ids) == len(node_rows)
    )
    topology_valid = bool(
        node_ids
        and member_ids
        and len(member_endpoints) == len(element_rows)
        and all(
            node_i in node_ids
            and node_j in node_ids
            and node_i != node_j
            and node_coordinates.get(node_i) != node_coordinates.get(node_j)
            for node_i, node_j in member_endpoints
        )
    )

    return {
        "path": path.relative_to(root).as_posix(),
        "valid_json": True,
        "geometry_present": geometry_present,
        "coordinates_valid": coordinates_valid,
        "member_identity_present": member_identity_present,
        "topology_valid": topology_valid,
        "node_row_count": len(node_rows),
        "member_row_count": len(element_rows),
        "node_ids": sorted(node_ids),
        "node_coordinates": {
            key: list(node_coordinates[key]) for key in sorted(node_coordinates)
        },
        "member_ids": sorted(member_ids),
        "member_endpoints": [list(row) for row in member_endpoints],
        "units_present": _has_units(payload),
        "load_case_present": _has_load_case(payload),
        "revision_present": _has_revision(payload),
        "proxy_or_fallback_explicit": _proxy_label_explicit(payload),
    }


def _csv_file_checks(path: Path, root: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        raw_headers = [str(item).strip() for item in (reader.fieldnames or [])]
        normalized_headers = [item.lower() for item in raw_headers]
        if (
            not raw_headers
            or any(not item for item in raw_headers)
            or len(set(normalized_headers)) != len(normalized_headers)
        ):
            raise csv.Error("CSV headers must be non-empty and unique")
        headers = set(normalized_headers)
        rows = list(reader)
        if any(
            None in row
            or any(value is None for value in row.values())
            for row in rows
        ):
            raise csv.Error("CSV rows must match the header width")
    except (OSError, UnicodeError, csv.Error) as exc:
        return {
            "path": path.relative_to(root).as_posix(),
            "valid_csv": False,
            "error": exc.__class__.__name__,
        }

    lowered_rows = [
        {str(key).strip().lower(): value for key, value in row.items()}
        for row in rows
    ]
    axis_keys = (
        ("x", "y", "z")
        if {"x", "y", "z"} <= headers
        else ("node_x", "node_y", "node_z")
    )
    has_coords = set(axis_keys) <= headers
    node_ids: set[str] = set()
    node_coordinates: dict[str, tuple[float, float, float]] = {}
    coordinates_valid = False
    if has_coords:
        coordinate_rows = []
        for row in lowered_rows:
            node_id = _identifier(
                _alias_value(row, {"node_id", "node", "nid", "id"})
            )
            if node_id is None and not any(
                _has_nonempty_value(row.get(axis)) for axis in axis_keys
            ):
                continue
            coordinate_rows.append(row)
            if node_id is not None:
                node_ids.add(node_id)
                if all(_finite_number(row.get(axis)) for axis in axis_keys):
                    node_coordinates[node_id] = tuple(
                        float(row[axis]) for axis in axis_keys
                    )
        coordinates_valid = bool(
            coordinate_rows
            and len(node_ids) == len(coordinate_rows)
            and all(
                _identifier(
                    _alias_value(row, {"node_id", "node", "nid", "id"})
                )
                is not None
                and all(_finite_number(row.get(axis)) for axis in axis_keys)
                for row in coordinate_rows
            )
        )

    member_ids: set[str] = set()
    member_endpoints: list[tuple[str, str]] = []
    member_row_count = 0
    explicit_member_id_aliases = {"member_id", "element_id", "eid"}
    endpoint_aliases = {
        "i",
        "j",
        "node_i",
        "node_j",
        "start_node",
        "end_node",
        "node1",
        "node2",
        "node_1",
        "node_2",
        "source",
        "target",
    }
    member_id_aliases = set(explicit_member_id_aliases)
    if not (explicit_member_id_aliases & headers) and endpoint_aliases & headers:
        member_id_aliases.add("id")
    for row in lowered_rows:
        node_i = _identifier(
            _alias_value(
                row,
                {"i", "node_i", "start_node", "node1", "node_1", "source"},
            )
        )
        node_j = _identifier(
            _alias_value(
                row,
                {"j", "node_j", "end_node", "node2", "node_2", "target"},
            )
        )
        member_id = _identifier(_alias_value(row, member_id_aliases))
        if member_id is None and node_i is None and node_j is None:
            continue
        member_row_count += 1
        if member_id is not None:
            member_ids.add(member_id)
        if node_i is not None and node_j is not None:
            member_endpoints.append((node_i, node_j))

    def any_nonempty(aliases: set[str]) -> bool:
        return any(
            _identifier(_alias_value(row, aliases)) is not None
            for row in lowered_rows
        )

    topology_valid = bool(
        node_ids
        and member_ids
        and len(member_endpoints) == len(member_ids)
        and all(
            node_i in node_ids
            and node_j in node_ids
            and node_i != node_j
            and node_coordinates.get(node_i) != node_coordinates.get(node_j)
            for node_i, node_j in member_endpoints
        )
    )
    return {
        "path": path.relative_to(root).as_posix(),
        "valid_csv": True,
        "row_count": len(rows),
        "geometry_present": bool(node_ids and member_ids),
        "coordinates_valid": coordinates_valid,
        "member_identity_present": bool(
            member_row_count and len(member_ids) == member_row_count
        ),
        "topology_valid": topology_valid,
        "node_row_count": len(node_ids),
        "member_row_count": member_row_count,
        "node_ids": sorted(node_ids),
        "node_coordinates": {
            key: list(node_coordinates[key]) for key in sorted(node_coordinates)
        },
        "member_ids": sorted(member_ids),
        "member_endpoints": [list(row) for row in member_endpoints],
        "units_present": any_nonempty(
            {"units", "unit", "length_unit", "force_unit"}
        ),
        "load_case_present": any_nonempty(
            {"load_case", "load_combo", "load_combination"}
        ),
        "revision_present": any_nonempty(
            {"revision", "drawing_revision", "rev", "version"}
        ),
        "proxy_or_fallback_explicit": not ({"proxy", "fallback"} & headers) or any_nonempty(
            {"proxy_labeled", "fallback_labeled"}
        ),
    }


def _extract_zip(input_path: Path) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="client-input-"))
    try:
        with zipfile.ZipFile(input_path) as archive:
            infos = archive.infolist()
            file_infos = [info for info in infos if not info.is_dir()]
            if len(infos) > MAX_FILE_COUNT or len(file_infos) > MAX_FILE_COUNT:
                raise ClientInputValidationError("input_file_count_exceeded")
            total_bytes = 0
            destinations: set[str] = set()
            for info in infos:
                raw_name = info.filename
                pure = PurePosixPath(raw_name)
                if (
                    not raw_name
                    or "\\" in raw_name
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or any(
                        not part or part == "." or ":" in part
                        for part in pure.parts
                    )
                ):
                    raise ClientInputValidationError("unsafe_archive_path")
                normalized = pure.as_posix().rstrip("/")
                if not normalized:
                    continue
                if normalized in destinations:
                    raise ClientInputValidationError("duplicate_archive_member")
                destinations.add(normalized)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode):
                    raise ClientInputValidationError("archive_symlink_rejected")
                if info.flag_bits & 0x1:
                    raise ClientInputValidationError(
                        "encrypted_archive_member_rejected"
                    )
                if info.file_size > MAX_FILE_BYTES:
                    raise ClientInputValidationError("input_file_size_exceeded")
                total_bytes += info.file_size
                if total_bytes > MAX_TOTAL_BYTES:
                    raise ClientInputValidationError("input_total_size_exceeded")
                destination = (temp_root / Path(*pure.parts)).resolve()
                try:
                    destination.relative_to(temp_root.resolve())
                except ValueError as exc:
                    raise ClientInputValidationError("unsafe_archive_path") from exc
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if destination.stat().st_size != info.file_size:
                    raise ClientInputValidationError("input_file_size_exceeded")
        return temp_root
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def _safe_file_inventory(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_symlink():
        raise ClientInputValidationError("input_symlink_rejected")
    resolved_root = root.resolve()
    files: list[Path] = []
    total_bytes = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ClientInputValidationError("input_symlink_rejected")
        if not path.is_file():
            continue
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError as exc:
            raise ClientInputValidationError("unsafe_archive_path") from exc
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ClientInputValidationError("input_file_size_exceeded")
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise ClientInputValidationError("input_total_size_exceeded")
        files.append(path)
        if len(files) > MAX_FILE_COUNT:
            raise ClientInputValidationError("input_file_count_exceeded")
    return files


def _input_root(input_path: Path) -> tuple[Path, bool]:
    if input_path.is_symlink():
        raise ClientInputValidationError("input_symlink_rejected")
    if input_path.is_dir():
        return input_path, False
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        return _extract_zip(input_path), True
    if input_path.is_file():
        if input_path.stat().st_size > MAX_FILE_BYTES:
            raise ClientInputValidationError("input_file_size_exceeded")
        temp_root = Path(tempfile.mkdtemp(prefix="client-input-single-"))
        shutil.copy2(input_path, temp_root / input_path.name)
        return temp_root, True
    return input_path, False


def _input_binding(
    *,
    input_path: Path,
    source_kind: str,
    file_rows: list[dict[str, Any]],
    validated: bool,
) -> dict[str, Any]:
    try:
        repository_path: str | None = input_path.resolve().relative_to(
            REPO_ROOT.resolve()
        ).as_posix()
    except ValueError:
        repository_path = None
    source_commit_sha = _git_head()
    current_worktree_bound = bool(
        validated
        and source_kind == "repository_reference_fixture"
        and repository_path is not None
        and input_path.is_dir()
        and not input_path.is_symlink()
        and len(source_commit_sha) == 40
    )
    return {
        "source_kind": source_kind,
        "repository_path": repository_path,
        "current_worktree_bound": current_worktree_bound,
        "commit_tree_bound": False,
        "source_commit_sha": source_commit_sha,
        "file_count": len(file_rows),
        "total_bytes": sum(int(row["bytes"]) for row in file_rows),
        "input_set_hash": _canonical_hash(file_rows),
        "validator_path": "scripts/validate_client_input_package.py",
        "validator_sha256": _sha256_path(VALIDATOR_PATH),
        "schema_path": (
            "src/structural_analysis/schemas/"
            "client_input_validation_report_v1.schema.json"
        ),
        "schema_sha256": _sha256_path(SCHEMA_PATH),
    }


def _finalize_report(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["artifact_hash"] = _canonical_hash(result)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    expected_hash = _canonical_hash(
        {key: value for key, value in result.items() if key != "artifact_hash"}
    )
    binding = result["input_binding"]
    if (
        result["artifact_hash"] != expected_hash
        or result["contract_pass"] is not (result["status"] == "ready")
        or result["missing_data_report"]
        != [*result["blockers"], *result["needs_review"]]
        or binding["file_count"] != len(result["file_rows"])
        or binding["total_bytes"]
        != sum(int(row["bytes"]) for row in result["file_rows"])
        or binding["input_set_hash"] != _canonical_hash(result["file_rows"])
        or binding["source_commit_sha"] != result["source_commit_sha"]
        or (
            binding["current_worktree_bound"]
            and (
                binding["source_kind"] != "repository_reference_fixture"
                or binding["repository_path"] is None
                or binding["commit_tree_bound"] is not False
            )
        )
    ):
        raise ClientInputValidationError("report_contract_invalid")
    return result


def _error_report(
    *,
    input_path: Path,
    source_kind: str,
    issue: str,
) -> dict[str, Any]:
    reason_code = ISSUE_REASON_CODES.get(
        issue, "ERR_CLIENT_INPUT_PACKAGE_VALIDATION_FAILED"
    )
    return _finalize_report(
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now_utc_iso(),
            "source_commit_sha": _git_head(),
            "contract_pass": False,
            "status": "blocked",
            "reason_code": reason_code,
            "reason_codes": [reason_code],
            "summary_line": (
                "Client input validation: BLOCKED | files=0 | data_files=0 | "
                "blockers=1 | review=0"
            ),
            "input_path": str(input_path),
            "input_binding": _input_binding(
                input_path=input_path,
                source_kind=source_kind,
                file_rows=[],
                validated=False,
            ),
            "checks": {
                "input_available": False,
                "has_data_file": False,
                "data_files_parse": False,
                "geometry_present": False,
                "coordinates_valid": False,
                "member_identity_present": False,
                "topology_valid": False,
                "units_present": False,
                "load_case_present": False,
                "revision_present": False,
                "proxy_or_fallback_explicit": False,
            },
            "missing_data_report": [issue],
            "blockers": [issue],
            "needs_review": [],
            "file_rows": [],
            "data_file_checks": [],
            "claim_boundary": {
                "allowed": "bounded input-package shape and metadata validation",
                "forbidden": [
                    "structural adequacy approval",
                    "client-source authenticity",
                    "engineer-of-record approval",
                ],
                "source_authority": source_kind,
            },
        }
    )


def validate_client_input_package(
    *,
    input_path: Path,
    source_kind: str = "operator_or_local_input",
) -> dict[str, Any]:
    if source_kind not in SOURCE_KINDS:
        raise ValueError("source_kind is invalid")
    root = input_path
    cleanup = False
    try:
        if (
            source_kind == "repository_reference_fixture"
            and not input_path.is_symlink()
            and input_path.exists()
            and not input_path.is_dir()
        ):
            return _error_report(
                input_path=input_path,
                source_kind=source_kind,
                issue="repository_reference_fixture_directory_required",
            )
        try:
            root, cleanup = _input_root(input_path)
            files = _safe_file_inventory(root)
        except (ClientInputValidationError, zipfile.BadZipFile, OSError) as exc:
            issue = (
                exc.issue
                if isinstance(exc, ClientInputValidationError)
                else "data_file_parse_failed"
            )
            return _error_report(
                input_path=input_path,
                source_kind=source_kind,
                issue=issue,
            )

        json_checks = [
            _json_file_checks(path, root)
            for path in files
            if path.suffix.lower() == ".json"
        ]
        csv_checks = [
            _csv_file_checks(path, root)
            for path in files
            if path.suffix.lower() == ".csv"
        ]
        data_checks = json_checks + csv_checks
        file_rows = [_source_row(path, root) for path in files]

        input_available = bool(root.exists() and files)
        has_data_file = bool(data_checks)
        data_files_parse = bool(
            has_data_file
            and all(
                row.get("valid_json", row.get("valid_csv", False)) is True
                for row in data_checks
            )
        )
        node_ids = {
            str(node_id)
            for row in data_checks
            for node_id in row.get("node_ids", [])
        }
        member_ids = {
            str(member_id)
            for row in data_checks
            for member_id in row.get("member_ids", [])
        }
        member_endpoints = [
            (str(endpoint[0]), str(endpoint[1]))
            for row in data_checks
            for endpoint in row.get("member_endpoints", [])
            if isinstance(endpoint, list) and len(endpoint) == 2
        ]
        node_coordinates = {
            str(node_id): tuple(float(value) for value in coordinates)
            for row in data_checks
            for node_id, coordinates in row.get("node_coordinates", {}).items()
            if isinstance(coordinates, list) and len(coordinates) == 3
        }
        node_checks = [
            row for row in data_checks if int(row.get("node_row_count", 0)) > 0
        ]
        member_checks = [
            row
            for row in data_checks
            if int(row.get("member_row_count", 0)) > 0
        ]
        member_row_count = sum(
            int(row.get("member_row_count", 0)) for row in member_checks
        )
        node_row_count = sum(
            int(row.get("node_row_count", 0)) for row in node_checks
        )
        geometry_present = bool(node_row_count and member_row_count)
        coordinates_valid = bool(node_checks) and bool(
            len(node_ids) == node_row_count
            and len(node_coordinates) == node_row_count
            and all(bool(row.get("coordinates_valid")) for row in node_checks)
        )
        member_identity_present = bool(member_checks) and bool(
            len(member_ids) == member_row_count
            and all(
                bool(row.get("member_identity_present"))
                for row in member_checks
            )
        )
        topology_valid = bool(
            geometry_present
            and member_identity_present
            and len(member_endpoints) == member_row_count
            and all(
                node_i in node_ids
                and node_j in node_ids
                and node_i != node_j
                and node_coordinates.get(node_i) != node_coordinates.get(node_j)
                for node_i, node_j in member_endpoints
            )
        )
        units_present = any(bool(row.get("units_present")) for row in data_checks)
        load_case_present = any(
            bool(row.get("load_case_present")) for row in data_checks
        )
        revision_present = any(
            bool(row.get("revision_present")) for row in data_checks
        )
        proxy_or_fallback_explicit = bool(
            has_data_file
            and all(
                bool(row.get("proxy_or_fallback_explicit", True))
                for row in data_checks
            )
        )

        blocked = [
            *(["input_package_missing_or_empty"] if not input_available else []),
            *(
                ["json_or_csv_data_file_missing"]
                if input_available and not has_data_file
                else []
            ),
            *(["data_file_parse_failed"] if has_data_file and not data_files_parse else []),
            *(["model_geometry_missing"] if has_data_file and not geometry_present else []),
            *(
                ["model_coordinates_invalid_or_missing"]
                if geometry_present and not coordinates_valid
                else []
            ),
            *(
                ["model_topology_invalid"]
                if (
                    geometry_present
                    and coordinates_valid
                    and member_identity_present
                    and not topology_valid
                )
                else []
            ),
        ]
        needs_review = [
            *(
                ["member_or_element_id_missing"]
                if has_data_file and not member_identity_present
                else []
            ),
            *(["unit_information_missing"] if has_data_file and not units_present else []),
            *(
                ["load_case_or_combination_missing"]
                if has_data_file and not load_case_present
                else []
            ),
            *(
                ["revision_information_missing"]
                if has_data_file and not revision_present
                else []
            ),
            *(
                ["proxy_or_fallback_label_missing"]
                if has_data_file and not proxy_or_fallback_explicit
                else []
            ),
        ]
        status = "blocked" if blocked else "needs_review" if needs_review else "ready"
        issues = [*blocked, *needs_review]
        reason_codes = [ISSUE_REASON_CODES[issue] for issue in issues]
        reason_code = "PASS" if status == "ready" else reason_codes[0]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now_utc_iso(),
            "source_commit_sha": _git_head(),
            "contract_pass": status == "ready",
            "status": status,
            "reason_code": reason_code,
            "reason_codes": ["PASS"] if status == "ready" else reason_codes,
            "summary_line": (
                f"Client input validation: {status.upper()} | files={len(files)} | "
                f"data_files={len(data_checks)} | blockers={len(blocked)} | "
                f"review={len(needs_review)}"
            ),
            "input_path": str(input_path),
            "input_binding": _input_binding(
                input_path=input_path,
                source_kind=source_kind,
                file_rows=file_rows,
                validated=status == "ready",
            ),
            "checks": {
                "input_available": input_available,
                "has_data_file": has_data_file,
                "data_files_parse": data_files_parse,
                "geometry_present": geometry_present,
                "coordinates_valid": coordinates_valid,
                "member_identity_present": member_identity_present,
                "topology_valid": topology_valid,
                "units_present": units_present,
                "load_case_present": load_case_present,
                "revision_present": revision_present,
                "proxy_or_fallback_explicit": proxy_or_fallback_explicit,
            },
            "missing_data_report": issues,
            "blockers": blocked,
            "needs_review": needs_review,
            "file_rows": file_rows,
            "data_file_checks": data_checks,
            "claim_boundary": {
                "allowed": "bounded input-package shape and metadata validation",
                "forbidden": [
                    "structural adequacy approval",
                    "client-source authenticity",
                    "engineer-of-record approval",
                ],
                "source_authority": source_kind,
            },
        }
        return _finalize_report(payload)
    finally:
        if cleanup and root.exists():
            shutil.rmtree(root, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument(
        "--source-kind",
        choices=sorted(SOURCE_KINDS),
        default="operator_or_local_input",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_client_input_package(
        input_path=args.input,
        source_kind=args.source_kind,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and payload["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
