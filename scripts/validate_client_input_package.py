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
import shutil
import tempfile
from typing import Any
import zipfile


SCHEMA_VERSION = "client-input-validation-report.v1"
DEFAULT_REPORT_OUT = Path("implementation/phase1/client_input_validation_report.json")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_row(path: Path, root: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    return {
        "path": rel,
        "bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _finite_number(value: Any) -> bool:
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
        keys = {str(key).lower() for key in row}
        if "units" in keys or "unit" in keys or {"length_unit", "force_unit"} & keys:
            return True
    return False


def _has_revision(payload: Any) -> bool:
    for row in _walk_dicts(payload):
        keys = {str(key).lower() for key in row}
        if {"revision", "drawing_revision", "rev", "version"} & keys:
            return True
    return False


def _has_load_case(payload: Any) -> bool:
    for row in _walk_dicts(payload):
        keys = {str(key).lower() for key in row}
        if {"load_case", "load_cases", "loadcomb", "load_combination", "load_combinations", "loads"} & keys:
            return True
    return False


def _proxy_label_explicit(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    if "proxy" not in text and "fallback" not in text:
        return True
    return "proxy_labeled" in text or "fallback_labeled" in text or "explicitly labeled" in text


def _json_file_checks(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"path": str(path), "valid_json": False, "error": str(exc)}

    node_lists = _extract_candidate_lists(payload, {"nodes", "node"})
    element_lists = _extract_candidate_lists(payload, {"elements", "members", "member", "edges"})
    geometry_present = bool(node_lists and element_lists)
    coordinates_valid = False
    member_identity_present = False

    for nodes in node_lists:
        for node in nodes[:1000]:
            if not isinstance(node, dict):
                continue
            keys = {str(key).lower(): value for key, value in node.items()}
            if all(_finite_number(keys.get(axis)) for axis in ("x", "y", "z")):
                coordinates_valid = True
                break
            coords = keys.get("coords") or keys.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 3 and all(_finite_number(item) for item in coords[:3]):
                coordinates_valid = True
                break
        if coordinates_valid:
            break

    for elements in element_lists:
        for element in elements[:1000]:
            if not isinstance(element, dict):
                continue
            keys = {str(key).lower() for key in element}
            if {"id", "member_id", "element_id", "eid"} & keys:
                member_identity_present = True
                break
        if member_identity_present:
            break

    return {
        "path": str(path),
        "valid_json": True,
        "geometry_present": geometry_present,
        "coordinates_valid": coordinates_valid,
        "member_identity_present": member_identity_present,
        "units_present": _has_units(payload),
        "load_case_present": _has_load_case(payload),
        "revision_present": _has_revision(payload),
        "proxy_or_fallback_explicit": _proxy_label_explicit(payload),
    }


def _csv_file_checks(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        headers = {str(item).lower() for item in (reader.fieldnames or [])}
        rows = list(reader)
    except csv.Error as exc:
        return {"path": str(path), "valid_csv": False, "error": str(exc)}

    coord_aliases = [{"x", "y", "z"}, {"node_x", "node_y", "node_z"}]
    has_coords = any(aliases <= headers for aliases in coord_aliases)
    coordinates_valid = False
    if has_coords:
        for row in rows[:1000]:
            lowered = {str(key).lower(): value for key, value in row.items()}
            axis_keys = ("x", "y", "z") if {"x", "y", "z"} <= headers else ("node_x", "node_y", "node_z")
            if all(_finite_number(lowered.get(axis)) for axis in axis_keys):
                coordinates_valid = True
                break
    return {
        "path": str(path),
        "valid_csv": True,
        "row_count": len(rows),
        "geometry_present": bool(has_coords and rows),
        "coordinates_valid": coordinates_valid,
        "member_identity_present": bool({"id", "member_id", "element_id"} & headers),
        "units_present": bool({"units", "unit", "length_unit", "force_unit"} & headers),
        "load_case_present": bool({"load_case", "load_combo", "load_combination"} & headers),
        "revision_present": bool({"revision", "drawing_revision", "rev", "version"} & headers),
        "proxy_or_fallback_explicit": not ({"proxy", "fallback"} & headers) or bool(
            {"proxy_labeled", "fallback_labeled"} & headers
        ),
    }


def _extract_zip(input_path: Path) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="client-input-"))
    with zipfile.ZipFile(input_path) as archive:
        archive.extractall(temp_root)
    return temp_root


def _input_root(input_path: Path) -> tuple[Path, bool]:
    if input_path.is_dir():
        return input_path, False
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        return _extract_zip(input_path), True
    if input_path.is_file():
        temp_root = Path(tempfile.mkdtemp(prefix="client-input-single-"))
        shutil.copy2(input_path, temp_root / input_path.name)
        return temp_root, True
    return input_path, False


def validate_client_input_package(*, input_path: Path) -> dict[str, Any]:
    root, cleanup = _input_root(input_path)
    try:
        files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
        json_checks = [_json_file_checks(path) for path in files if path.suffix.lower() == ".json"]
        csv_checks = [_csv_file_checks(path) for path in files if path.suffix.lower() == ".csv"]
        data_checks = json_checks + csv_checks

        input_available = bool(root.exists() and files)
        has_data_file = bool(data_checks)
        geometry_present = any(bool(row.get("geometry_present")) for row in data_checks)
        coordinates_valid = any(bool(row.get("coordinates_valid")) for row in data_checks)
        member_identity_present = any(bool(row.get("member_identity_present")) for row in data_checks)
        units_present = any(bool(row.get("units_present")) for row in data_checks)
        load_case_present = any(bool(row.get("load_case_present")) for row in data_checks)
        revision_present = any(bool(row.get("revision_present")) for row in data_checks)
        proxy_or_fallback_explicit = all(bool(row.get("proxy_or_fallback_explicit", True)) for row in data_checks)

        blocked = [
            *(["input_package_missing_or_empty"] if not input_available else []),
            *(["json_or_csv_data_file_missing"] if input_available and not has_data_file else []),
            *(["model_geometry_missing"] if has_data_file and not geometry_present else []),
            *(["model_coordinates_invalid_or_missing"] if geometry_present and not coordinates_valid else []),
        ]
        needs_review = [
            *(["member_or_element_id_missing"] if has_data_file and not member_identity_present else []),
            *(["unit_information_missing"] if has_data_file and not units_present else []),
            *(["load_case_or_combination_missing"] if has_data_file and not load_case_present else []),
            *(["revision_information_missing"] if has_data_file and not revision_present else []),
            *(["proxy_or_fallback_label_missing"] if has_data_file and not proxy_or_fallback_explicit else []),
        ]
        status = "blocked" if blocked else "needs_review" if needs_review else "ready"
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now_utc_iso(),
            "contract_pass": status == "ready",
            "status": status,
            "reason_code": "PASS" if status == "ready" else f"ERR_CLIENT_INPUT_{status.upper()}",
            "summary_line": (
                f"Client input validation: {status.upper()} | files={len(files)} | "
                f"data_files={len(data_checks)} | blockers={len(blocked)} | review={len(needs_review)}"
            ),
            "input_path": str(input_path),
            "checks": {
                "input_available": input_available,
                "has_data_file": has_data_file,
                "geometry_present": geometry_present,
                "coordinates_valid": coordinates_valid,
                "member_identity_present": member_identity_present,
                "units_present": units_present,
                "load_case_present": load_case_present,
                "revision_present": revision_present,
                "proxy_or_fallback_explicit": proxy_or_fallback_explicit,
            },
            "missing_data_report": blocked + needs_review,
            "blockers": blocked,
            "needs_review": needs_review,
            "file_rows": [_source_row(path, root) for path in files],
            "data_file_checks": data_checks,
        }
    finally:
        if cleanup and root.exists():
            shutil.rmtree(root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_client_input_package(input_path=args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and payload["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
