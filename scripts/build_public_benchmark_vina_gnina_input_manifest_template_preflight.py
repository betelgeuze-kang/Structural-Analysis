#!/usr/bin/env python3
"""Preflight the Vina/GNINA input manifest template without promoting it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_public_benchmark_vina_gnina_execution_plan import (  # noqa: E402
    DEFAULT_INPUT_MANIFEST,
    DEFAULT_OUT as DEFAULT_EXECUTION_PLAN,
    INPUT_MANIFEST_CASE_FIELDS,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    PLACEHOLDER_PROVENANCE_PREFIXES,
    PLACEHOLDER_SOURCE_TEXT_MARKERS,
    SOURCE_CHECKSUM_PATTERN,
    SUPPORTED_BENCHMARK_SPLITS,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_TEMPLATE = PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_template.csv"
DEFAULT_OUT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_template_preflight.json"
)
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "public-benchmark-vina-gnina-input-manifest-template-preflight.v1"
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "codex-public-benchmark-vina-gnina-input-preflight/1.0"
CASE_ID_FIELD = "case_id"
MANIFEST_REQUIRED_FIELDS = (CASE_ID_FIELD, *INPUT_MANIFEST_CASE_FIELDS)
LOCAL_FILE_FIELDS = (
    "protein_structure_path",
    "reference_ligand_path",
    "prepared_receptor_path",
    "prepared_ligand_path",
)
SOURCE_LOCAL_FILE_FIELDS = ("protein_structure_path", "reference_ligand_path")
PREPARED_LOCAL_FILE_FIELDS = ("prepared_receptor_path", "prepared_ligand_path")
CHECKSUM_FIELDS = (
    "source_checksum",
    "protein_structure_checksum",
    "reference_ligand_checksum",
    "prepared_receptor_checksum",
    "prepared_ligand_checksum",
)
SOURCE_RECEIPT_FIELDS = ("source_license_or_accession", "provenance_ref")
RECEIPT_REF_FIELDS = (
    "vina_config_ref",
    "gnina_config_ref",
    "vina_run_receipt_ref",
    "gnina_run_receipt_ref",
    "input_preparation_provenance_ref",
)
LOCAL_FILE_LABELS = {
    "protein_structure_path": "source_protein_structure",
    "reference_ligand_path": "source_reference_ligand",
    "prepared_receptor_path": "prepared_receptor",
    "prepared_ligand_path": "prepared_ligand",
}
SOURCE_FAMILY_POLICY = {
    "accepted_markers": ["casf", "pdbbind"],
    "placeholder_markers_rejected": True,
}

ProbeFunc = Callable[[str, int], dict[str, Any]]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_csv_rows(repo_root: Path, path: Path) -> tuple[list[str], list[dict[str, str]]]:
    resolved = _resolve(repo_root, path)
    if not resolved.is_file():
        return [], []
    with resolved.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [
            {
                str(key).strip(): str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in reader
        ]
    return [str(field) for field in reader.fieldnames or []], rows


def _int_header(value: Any) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return 0
    return parsed if parsed > 0 else 0


def _response_metadata(response: Any) -> dict[str, Any]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
        }
    return {
        "content_length_bytes": _int_header(headers.get("Content-Length")),
        "content_type": str(headers.get("Content-Type") or ""),
        "last_modified": str(headers.get("Last-Modified") or ""),
        "etag": str(headers.get("ETag") or ""),
        "accept_ranges": str(headers.get("Accept-Ranges") or ""),
    }


def _head_probe(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", response.getcode()) or 0)
            return {
                "http_status": status,
                "final_url": str(response.geturl() or url),
                "error": "",
                **_response_metadata(response),
            }
    except HTTPError as exc:
        return {
            "http_status": int(exc.code or 0),
            "final_url": str(exc.geturl() or url),
            "error": exc.__class__.__name__,
            **_response_metadata(exc),
        }
    except (TimeoutError, URLError, OSError) as exc:
        return {
            "http_status": 0,
            "final_url": "",
            "error": exc.__class__.__name__,
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _checksum_status(value: str) -> dict[str, Any]:
    if not value:
        return {
            "present": False,
            "valid_sha256": False,
            "blocker": "checksum_missing",
        }
    if not SOURCE_CHECKSUM_PATTERN.fullmatch(value):
        return {
            "present": True,
            "valid_sha256": False,
            "blocker": "checksum_invalid",
        }
    digest = value.split(":", 1)[1].lower()
    if len(set(digest)) == 1:
        return {
            "present": True,
            "valid_sha256": False,
            "blocker": "checksum_placeholder_digest",
        }
    return {"present": True, "valid_sha256": True, "blocker": ""}


def _contains_placeholder_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_SOURCE_TEXT_MARKERS)


def _has_placeholder_provenance_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _source_receipt_status(field: str, value: str) -> dict[str, Any]:
    if not value:
        return {
            "field": field,
            "present": False,
            "status": "missing",
            "blocker": "source_receipt_missing",
        }
    if _contains_placeholder_marker(value):
        return {
            "field": field,
            "present": True,
            "status": "placeholder",
            "blocker": "source_receipt_placeholder",
        }
    if field == "provenance_ref" and _has_placeholder_provenance_prefix(value):
        return {
            "field": field,
            "present": True,
            "status": "placeholder",
            "blocker": "source_receipt_placeholder",
        }
    return {
        "field": field,
        "present": True,
        "status": "ready",
        "blocker": "",
    }


def _benchmark_split_status(value: str) -> dict[str, Any]:
    if not value:
        return {"present": False, "valid": False, "blocker": "benchmark_split_missing"}
    valid = value in SUPPORTED_BENCHMARK_SPLITS
    return {
        "present": True,
        "valid": valid,
        "blocker": "" if valid else "benchmark_split_unsupported",
    }


def _source_family_status(value: str) -> dict[str, Any]:
    if not value:
        return {"present": False, "valid": False, "blocker": "source_family_missing"}
    lowered = value.lower()
    if _contains_placeholder_marker(value):
        return {
            "present": True,
            "valid": False,
            "blocker": "source_family_placeholder",
        }
    accepted_markers = {
        str(marker) for marker in SOURCE_FAMILY_POLICY["accepted_markers"]
    }
    valid = any(marker in lowered for marker in accepted_markers)
    return {
        "present": True,
        "valid": valid,
        "blocker": "" if valid else "source_family_unsupported",
    }


def _local_file_status(repo_root: Path, path_value: str, checksum_value: str) -> dict[str, Any]:
    if not path_value:
        return {
            "path": "",
            "exists": False,
            "is_file": False,
            "actual_checksum": "",
            "checksum_verified": False,
            "blocker": "path_missing",
        }
    path = Path(path_value)
    resolved = path if path.is_absolute() else repo_root / path
    exists = resolved.exists()
    is_file = resolved.is_file()
    actual_checksum = ""
    checksum_verified = False
    blocker = ""
    if not exists:
        blocker = "path_not_found"
    elif not is_file:
        blocker = "path_not_file"
    else:
        try:
            actual_checksum = _sha256_file(resolved)
        except OSError:
            blocker = "checksum_read_error"
        else:
            checksum_status = _checksum_status(checksum_value)
            if checksum_status["blocker"]:
                blocker = str(checksum_status["blocker"])
            elif actual_checksum.lower() != checksum_value.lower():
                blocker = "checksum_mismatch"
            else:
                checksum_verified = True
    return {
        "path": path_value,
        "expected_checksum": checksum_value,
        "exists": exists,
        "is_file": is_file,
        "actual_checksum": actual_checksum,
        "checksum_verified": checksum_verified,
        "blocker": blocker,
    }


def _ref_status(repo_root: Path, value: str) -> dict[str, Any]:
    if not value:
        return {
            "ref": "",
            "present": False,
            "local_path_exists": False,
            "status": "missing",
            "blocker": "ref_missing",
        }
    if value.startswith(("http://", "https://")):
        return {
            "ref": value,
            "present": True,
            "local_path_exists": False,
            "status": "external_ref",
            "blocker": "",
        }
    resolved = _resolve(repo_root, Path(value))
    local_path_exists = resolved.exists()
    return {
        "ref": value,
        "present": True,
        "local_path_exists": local_path_exists,
        "status": "ready" if local_path_exists else "local_ref_not_found",
        "blocker": "" if local_path_exists else "local_ref_not_found",
    }


def _source_url_probe(
    *,
    url: str,
    probe_source_urls: bool,
    timeout_seconds: int,
    probe_func: ProbeFunc,
) -> dict[str, Any]:
    if not url:
        return {
            "url": "",
            "attempted": False,
            "status": "url_missing",
            "http_status": 0,
            "final_url": "",
            "error": "url_missing",
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
            "success_criteria_met": False,
        }
    if not probe_source_urls:
        return {
            "url": url,
            "attempted": False,
            "status": "not_run",
            "http_status": 0,
            "final_url": "",
            "error": "",
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
            "success_criteria_met": False,
        }
    raw_probe = probe_func(url, timeout_seconds)
    http_status = int(raw_probe.get("http_status") or 0)
    success = 200 <= http_status < 400
    return {
        "url": url,
        "attempted": True,
        "status": "reachable" if success else "blocked",
        "http_status": http_status,
        "final_url": str(raw_probe.get("final_url") or ""),
        "error": str(raw_probe.get("error") or ""),
        "content_length_bytes": _int_header(raw_probe.get("content_length_bytes")),
        "content_type": str(raw_probe.get("content_type") or ""),
        "last_modified": str(raw_probe.get("last_modified") or ""),
        "etag": str(raw_probe.get("etag") or ""),
        "accept_ranges": str(raw_probe.get("accept_ranges") or ""),
        "success_criteria_met": success,
    }


def _source_url_probe_plan(
    *,
    source_file_acquisition_plan: list[dict[str, Any]],
    probe_source_urls: bool,
    timeout_seconds: int,
    probe_func: ProbeFunc,
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for row in source_file_acquisition_plan:
        url = str(row.get("source_url") or "")
        if not url:
            continue
        entry = by_url.setdefault(
            url,
            {
                "source_url": url,
                "case_ids": [],
                "file_roles": [],
                "head_command": (
                    f"curl --head --location --max-time {timeout_seconds} '{url}'"
                ),
            },
        )
        case_id = str(row.get("case_id") or "")
        file_role = str(row.get("file_role") or "")
        if case_id and case_id not in entry["case_ids"]:
            entry["case_ids"].append(case_id)
        if file_role and file_role not in entry["file_roles"]:
            entry["file_roles"].append(file_role)
    plan: list[dict[str, Any]] = []
    for url, entry in by_url.items():
        probe = _source_url_probe(
            url=url,
            probe_source_urls=probe_source_urls,
            timeout_seconds=timeout_seconds,
            probe_func=probe_func,
        )
        plan.append(
            {
                **entry,
                "status": probe["status"],
                "blockers": [] if probe["success_criteria_met"] else [probe["status"]],
                "probe": probe,
                "claim_boundary": (
                    "This is a HEAD-only source URL probe. It does not download "
                    "or promote benchmark payloads as actual evidence."
                ),
            }
        )
    return plan


def _expected_case_ids(execution_plan: dict[str, Any]) -> list[str]:
    case_plans = execution_plan.get("case_execution_plans")
    if not isinstance(case_plans, list):
        return []
    return [
        str(row.get("case_id") or "")
        for row in case_plans
        if isinstance(row, dict) and str(row.get("case_id") or "")
    ]


def _filled_manifest_status(execution_plan: dict[str, Any]) -> dict[str, Any]:
    status = execution_plan.get("input_manifest_status")
    return status if isinstance(status, dict) else {}


def _row_preflight(repo_root: Path, row: dict[str, str]) -> dict[str, Any]:
    missing_required_fields = [
        field for field in MANIFEST_REQUIRED_FIELDS if not str(row.get(field) or "")
    ]
    benchmark_statuses = {
        "benchmark_split": _benchmark_split_status(
            str(row.get("benchmark_split") or "")
        ),
        "source_family": _source_family_status(str(row.get("source_family") or "")),
    }
    unsupported_benchmark_fields = [
        field
        for field, status in benchmark_statuses.items()
        if status["present"] and str(status["blocker"] or "")
    ]
    source_receipt_statuses = {
        field: _source_receipt_status(field, str(row.get(field) or ""))
        for field in SOURCE_RECEIPT_FIELDS
    }
    invalid_source_receipt_fields = [
        field
        for field, status in source_receipt_statuses.items()
        if status["present"] and str(status["blocker"] or "")
    ]
    checksum_statuses = {
        field: _checksum_status(str(row.get(field) or ""))
        for field in CHECKSUM_FIELDS
    }
    invalid_checksum_fields = [
        field
        for field, status in checksum_statuses.items()
        if status["present"] and not status["valid_sha256"]
    ]
    local_file_statuses = {
        field: _local_file_status(
            repo_root,
            str(row.get(field) or ""),
            str(row.get(field.replace("_path", "_checksum")) or ""),
        )
        for field in LOCAL_FILE_FIELDS
    }
    missing_local_file_fields = [
        field
        for field, status in local_file_statuses.items()
        if str(status.get("blocker") or "")
    ]
    receipt_ref_statuses = {
        field: _ref_status(repo_root, str(row.get(field) or ""))
        for field in RECEIPT_REF_FIELDS
    }
    missing_receipt_ref_fields = [
        field
        for field, status in receipt_ref_statuses.items()
        if str(status.get("blocker") or "")
    ]
    blockers = []
    if missing_required_fields:
        blockers.append("manifest_required_fields_missing")
    if unsupported_benchmark_fields:
        blockers.append("manifest_benchmark_identity_invalid")
    if invalid_source_receipt_fields:
        blockers.append("manifest_source_receipts_invalid")
    if invalid_checksum_fields:
        blockers.append("manifest_checksum_fields_invalid")
    if missing_local_file_fields:
        blockers.append("manifest_local_files_missing_or_unverified")
    if missing_receipt_ref_fields:
        blockers.append("manifest_receipt_refs_missing")
    local_file_requirements = []
    for field in LOCAL_FILE_FIELDS:
        status = local_file_statuses[field]
        checksum_field = field.replace("_path", "_checksum")
        is_source_file = field in SOURCE_LOCAL_FILE_FIELDS
        blocker = str(status.get("blocker") or "")
        local_file_requirements.append(
            {
                "case_id": str(row.get(CASE_ID_FIELD) or ""),
                "complex_id": str(row.get("complex_id") or ""),
                "field": field,
                "file_role": LOCAL_FILE_LABELS[field],
                "file_group": "official_source_file" if is_source_file else "prepared_input_file",
                "path": str(row.get(field) or ""),
                "expected_checksum_field": checksum_field,
                "expected_checksum": str(row.get(checksum_field) or ""),
                "source_url": str(row.get("provenance_ref") or "") if is_source_file else "",
                "source_license_or_accession": (
                    str(row.get("source_license_or_accession") or "")
                    if is_source_file
                    else ""
                ),
                "status": "ready" if not blocker else "operator_completion_required",
                "blocker": blocker,
                "operator_action": (
                    "verify_local_source_file_checksum"
                    if is_source_file and not blocker
                    else "acquire_from_official_casf_archive_and_verify_checksum"
                    if is_source_file
                    else "verify_prepared_input_file_checksum"
                    if not blocker
                    else "prepare_vina_gnina_input_and_record_checksum"
                ),
            }
        )
    receipt_ref_requirements = []
    for field in RECEIPT_REF_FIELDS:
        status = receipt_ref_statuses[field]
        blocker = str(status.get("blocker") or "")
        receipt_ref_requirements.append(
            {
                "case_id": str(row.get(CASE_ID_FIELD) or ""),
                "complex_id": str(row.get("complex_id") or ""),
                "field": field,
                "ref": str(row.get(field) or ""),
                "status": "ready" if not blocker else "operator_completion_required",
                "blocker": blocker,
                "operator_action": (
                    "verify_manifest_receipt_ref"
                    if not blocker
                    else f"attach_{field}"
                ),
            }
        )
    return {
        "case_id": str(row.get(CASE_ID_FIELD) or ""),
        "complex_id": str(row.get("complex_id") or ""),
        "status": "operator_completion_required" if blockers else "ready",
        "missing_required_fields": missing_required_fields,
        "unsupported_benchmark_fields": unsupported_benchmark_fields,
        "invalid_source_receipt_fields": invalid_source_receipt_fields,
        "benchmark_statuses": benchmark_statuses,
        "source_receipt_statuses": source_receipt_statuses,
        "invalid_checksum_fields": invalid_checksum_fields,
        "missing_local_file_fields": missing_local_file_fields,
        "missing_receipt_ref_fields": missing_receipt_ref_fields,
        "checksum_statuses": checksum_statuses,
        "local_file_statuses": local_file_statuses,
        "receipt_ref_statuses": receipt_ref_statuses,
        "local_file_requirements": local_file_requirements,
        "receipt_ref_requirements": receipt_ref_requirements,
        "blockers": blockers,
    }


def build_public_benchmark_vina_gnina_input_manifest_template_preflight(
    *,
    repo_root: Path = ROOT,
    execution_plan: Path = DEFAULT_EXECUTION_PLAN,
    template: Path = DEFAULT_TEMPLATE,
    expected_manifest: Path = DEFAULT_INPUT_MANIFEST,
    probe_source_urls: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    probe_func: ProbeFunc = _head_probe,
) -> dict[str, Any]:
    execution_plan_payload = _load_json(repo_root, execution_plan)
    header_fields, rows = _read_csv_rows(repo_root, template)
    row_preflights = [_row_preflight(repo_root, row) for row in rows]
    local_file_requirements = [
        requirement
        for row in row_preflights
        for requirement in row["local_file_requirements"]
    ]
    source_file_acquisition_plan = [
        row
        for row in local_file_requirements
        if row["field"] in SOURCE_LOCAL_FILE_FIELDS
    ]
    prepared_input_plan = [
        row
        for row in local_file_requirements
        if row["field"] in PREPARED_LOCAL_FILE_FIELDS
    ]
    receipt_ref_plan = [
        requirement
        for row in row_preflights
        for requirement in row["receipt_ref_requirements"]
    ]
    source_url_probe_plan = _source_url_probe_plan(
        source_file_acquisition_plan=source_file_acquisition_plan,
        probe_source_urls=probe_source_urls,
        timeout_seconds=timeout_seconds,
        probe_func=probe_func,
    )
    expected_case_ids = _expected_case_ids(execution_plan_payload)
    template_case_ids = [row["case_id"] for row in row_preflights if row["case_id"]]
    missing_expected_case_ids = [
        case_id for case_id in expected_case_ids if case_id not in template_case_ids
    ]
    unexpected_template_case_ids = [
        case_id for case_id in template_case_ids if expected_case_ids and case_id not in expected_case_ids
    ]
    duplicate_case_ids = sorted(
        {
            case_id
            for case_id in template_case_ids
            if case_id and template_case_ids.count(case_id) > 1
        }
    )
    missing_required_value_count = sum(
        len(row["missing_required_fields"]) for row in row_preflights
    )
    invalid_checksum_count = sum(
        len(row["invalid_checksum_fields"]) for row in row_preflights
    )
    invalid_source_receipt_count = sum(
        len(row["invalid_source_receipt_fields"]) for row in row_preflights
    )
    unsupported_benchmark_field_count = sum(
        len(row["unsupported_benchmark_fields"]) for row in row_preflights
    )
    missing_local_file_count = sum(
        len(row["missing_local_file_fields"]) for row in row_preflights
    )
    missing_receipt_ref_count = sum(
        len(row["missing_receipt_ref_fields"]) for row in row_preflights
    )
    missing_source_file_count = sum(
        1 for row in source_file_acquisition_plan if row["blocker"]
    )
    missing_prepared_input_count = sum(
        1 for row in prepared_input_plan if row["blocker"]
    )
    missing_receipt_requirement_count = sum(
        1 for row in receipt_ref_plan if row["blocker"]
    )
    source_url_reachable_count = sum(
        1 for row in source_url_probe_plan if row["status"] == "reachable"
    )
    source_url_blocked_count = sum(
        1 for row in source_url_probe_plan if row["status"] == "blocked"
    )
    source_url_not_run_count = sum(
        1 for row in source_url_probe_plan if row["status"] == "not_run"
    )
    known_source_url_content_length_bytes = sum(
        int(_as_dict(row.get("probe")).get("content_length_bytes") or 0)
        for row in source_url_probe_plan
    )
    template_case_coverage_complete = bool(rows) and not (
        missing_expected_case_ids or unexpected_template_case_ids or duplicate_case_ids
    )
    manifest_ready = bool(rows) and template_case_coverage_complete and not (
        missing_required_value_count
        or unsupported_benchmark_field_count
        or invalid_source_receipt_count
        or invalid_checksum_count
        or missing_local_file_count
        or missing_receipt_ref_count
    )
    if not rows:
        status = "template_missing_or_empty"
    elif not template_case_coverage_complete:
        status = "template_case_coverage_blocked"
    elif manifest_ready:
        status = "operator_manifest_complete"
    else:
        status = "operator_manifest_completion_required"
    filled_manifest = _filled_manifest_status(execution_plan_payload)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py"),
                Path("scripts/build_public_benchmark_vina_gnina_execution_plan.py"),
                execution_plan,
                template,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_input_manifest_template_preflight",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bool(rows) and template_case_coverage_complete,
        "manifest_ready": manifest_ready,
        "template_artifact": str(template),
        "expected_manifest_artifact": str(expected_manifest),
        "filled_manifest_detected": bool(
            filled_manifest.get("selected_manifest_path")
            or int(filled_manifest.get("detected_manifest_artifact_count") or 0) > 0
        ),
        "filled_manifest_status": filled_manifest,
        "required_fields": list(MANIFEST_REQUIRED_FIELDS),
        "local_file_fields": list(LOCAL_FILE_FIELDS),
        "checksum_fields": list(CHECKSUM_FIELDS),
        "source_receipt_fields": list(SOURCE_RECEIPT_FIELDS),
        "source_family_policy": SOURCE_FAMILY_POLICY,
        "supported_benchmark_splits": list(SUPPORTED_BENCHMARK_SPLITS),
        "receipt_ref_fields": list(RECEIPT_REF_FIELDS),
        "header_fields": header_fields,
        "expected_case_ids": expected_case_ids,
        "template_case_ids": template_case_ids,
        "missing_expected_case_ids": missing_expected_case_ids,
        "unexpected_template_case_ids": unexpected_template_case_ids,
        "duplicate_case_ids": duplicate_case_ids,
        "case_preflight_rows": row_preflights,
        "case_preflight_row_count": len(row_preflights),
        "source_file_acquisition_plan": source_file_acquisition_plan,
        "prepared_input_plan": prepared_input_plan,
        "receipt_ref_plan": receipt_ref_plan,
        "source_url_probe_plan": source_url_probe_plan,
        "source_url_probe_policy": {
            "probe_source_urls": bool(probe_source_urls),
            "timeout_seconds": int(timeout_seconds),
            "network_probe_only": True,
            "raw_payload_downloaded_by_plan": False,
            "raw_payload_committed_by_plan": False,
        },
        "operator_actions": [
            "do_not_commit_template_as_actual_manifest_evidence",
            "review_source_file_acquisition_plan",
            "review_prepared_input_plan",
            "review_receipt_ref_plan",
            "review_source_url_probe_plan",
            "copy_template_to_expected_manifest_only_after_operator_completion",
            "attach_local_source_and_prepared_input_files",
            "fill_missing_prepared_input_checksums_and_preparation_receipts",
            "rerun_vina_gnina_execution_plan_after_manifest_completion",
        ],
        "commands": {
            "write_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
                f"--out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}"
            ),
            "probe_source_urls": (
                "python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py "
                f"--out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} --probe-source-urls"
            ),
            "rerun_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--out {DEFAULT_EXECUTION_PLAN}"
            ),
            "rerun_runtime_readiness": (
                "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
                f"--out {PRODUCTIZATION / 'public_benchmark_vina_gnina_runtime_readiness.json'}"
            ),
        },
        "summary": {
            "expected_case_count": len(expected_case_ids),
            "template_row_count": len(rows),
            "template_case_count": len(template_case_ids),
            "template_case_coverage_complete": template_case_coverage_complete,
            "missing_expected_case_count": len(missing_expected_case_ids),
            "unexpected_template_case_count": len(unexpected_template_case_ids),
            "duplicate_case_id_count": len(duplicate_case_ids),
            "missing_required_value_count": missing_required_value_count,
            "unsupported_benchmark_field_count": unsupported_benchmark_field_count,
            "invalid_source_receipt_count": invalid_source_receipt_count,
            "invalid_checksum_count": invalid_checksum_count,
            "missing_local_file_count": missing_local_file_count,
            "missing_receipt_ref_count": missing_receipt_ref_count,
            "source_file_requirement_count": len(source_file_acquisition_plan),
            "source_file_missing_count": missing_source_file_count,
            "source_url_probe_count": len(source_url_probe_plan),
            "source_url_probe_network_performed": bool(probe_source_urls),
            "source_url_reachable_count": source_url_reachable_count,
            "source_url_blocked_count": source_url_blocked_count,
            "source_url_not_run_count": source_url_not_run_count,
            "known_source_url_content_length_bytes": (
                known_source_url_content_length_bytes
            ),
            "known_source_url_content_length_gib": round(
                known_source_url_content_length_bytes / (1024**3),
                3,
            ),
            "prepared_input_requirement_count": len(prepared_input_plan),
            "prepared_input_missing_count": missing_prepared_input_count,
            "receipt_ref_requirement_count": len(receipt_ref_plan),
            "receipt_ref_missing_count": missing_receipt_requirement_count,
            "manifest_ready": manifest_ready,
        },
        "claim_boundary": (
            "This preflight audits the operator input-manifest template only. It "
            "does not promote the template to an actual manifest, verify license "
            "rights, run Vina/GNINA, create adapter rows, or close Public Benchmark "
            "Phase 2."
        ),
    }


def render_public_benchmark_vina_gnina_input_manifest_template_preflight_markdown(
    payload: dict[str, Any],
) -> str:
    summary = payload["summary"]
    lines = [
        "# Public Benchmark Vina/GNINA Input Manifest Template Preflight",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `manifest_ready`: `{payload['manifest_ready']}`",
        f"- `template_row_count`: `{summary['template_row_count']}`",
        f"- `missing_required_value_count`: `{summary['missing_required_value_count']}`",
        f"- `unsupported_benchmark_field_count`: `{summary['unsupported_benchmark_field_count']}`",
        f"- `invalid_source_receipt_count`: `{summary['invalid_source_receipt_count']}`",
        f"- `missing_local_file_count`: `{summary['missing_local_file_count']}`",
        f"- `missing_receipt_ref_count`: `{summary['missing_receipt_ref_count']}`",
        f"- `source_file_missing_count`: `{summary['source_file_missing_count']}`",
        f"- `source_url_probe_count`: `{summary['source_url_probe_count']}`",
        "- `known_source_url_content_length_gib`: "
        f"`{summary['known_source_url_content_length_gib']}`",
        f"- `prepared_input_missing_count`: `{summary['prepared_input_missing_count']}`",
        f"- `receipt_ref_missing_count`: `{summary['receipt_ref_missing_count']}`",
        "",
        "## Case Rows",
        "",
        "| Case | Status | Missing Fields | Missing Files | Missing Refs |",
        "|---|---|---|---|---|",
    ]
    for row in payload["case_preflight_rows"]:
        lines.append(
            f"| `{row['case_id']}` | `{row['status']}` | "
            f"`{len(row['missing_required_fields'])}` | "
            f"`{len(row['missing_local_file_fields'])}` | "
            f"`{len(row['missing_receipt_ref_fields'])}` |"
        )
    source_plan = [
        row
        for row in payload.get("source_file_acquisition_plan", [])
        if isinstance(row, dict)
    ]
    if source_plan:
        lines.extend(
            [
                "",
                "## Source File Acquisition Plan",
                "",
                "| Case | Role | Path | Expected Checksum | Status | Action |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in source_plan:
            lines.append(
                f"| `{row.get('case_id', '')}` | `{row.get('file_role', '')}` | "
                f"`{row.get('path', '')}` | `{row.get('expected_checksum', '')}` | "
                f"`{row.get('status', '')}` | `{row.get('operator_action', '')}` |"
            )
    source_url_plan = [
        row for row in payload.get("source_url_probe_plan", []) if isinstance(row, dict)
    ]
    if source_url_plan:
        lines.extend(
            [
                "",
                "## Source URL Probe Plan",
                "",
                "| URL | Status | Size Bytes | Cases |",
                "|---|---|---:|---:|",
            ]
        )
        for row in source_url_plan:
            probe = _as_dict(row.get("probe"))
            lines.append(
                f"| `{row.get('source_url', '')}` | `{row.get('status', '')}` | "
                f"`{probe.get('content_length_bytes', 0)}` | "
                f"`{len(row.get('case_ids', []))}` |"
            )
    prepared_plan = [
        row
        for row in payload.get("prepared_input_plan", [])
        if isinstance(row, dict)
    ]
    if prepared_plan:
        lines.extend(
            [
                "",
                "## Prepared Input Plan",
                "",
                "| Case | Role | Path | Expected Checksum | Status | Action |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in prepared_plan:
            lines.append(
                f"| `{row.get('case_id', '')}` | `{row.get('file_role', '')}` | "
                f"`{row.get('path', '')}` | `{row.get('expected_checksum', '')}` | "
                f"`{row.get('status', '')}` | `{row.get('operator_action', '')}` |"
            )
    receipt_plan = [
        row for row in payload.get("receipt_ref_plan", []) if isinstance(row, dict)
    ]
    if receipt_plan:
        lines.extend(
            [
                "",
                "## Receipt Ref Plan",
                "",
                "| Case | Field | Ref | Status | Action |",
                "|---|---|---|---|---|",
            ]
        )
        for row in receipt_plan:
            lines.append(
                f"| `{row.get('case_id', '')}` | `{row.get('field', '')}` | "
                f"`{row.get('ref', '')}` | `{row.get('status', '')}` | "
                f"`{row.get('operator_action', '')}` |"
            )
    lines.extend(["", "## Commands", ""])
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_public_benchmark_vina_gnina_input_manifest_template_preflight(
    *,
    repo_root: Path = ROOT,
    execution_plan: Path = DEFAULT_EXECUTION_PLAN,
    template: Path = DEFAULT_TEMPLATE,
    expected_manifest: Path = DEFAULT_INPUT_MANIFEST,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    probe_source_urls: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    payload = build_public_benchmark_vina_gnina_input_manifest_template_preflight(
        repo_root=repo_root,
        execution_plan=execution_plan,
        template=template,
        expected_manifest=expected_manifest,
        probe_source_urls=probe_source_urls,
        timeout_seconds=timeout_seconds,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = _resolve(repo_root, out_md)
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_public_benchmark_vina_gnina_input_manifest_template_preflight_markdown(
            payload
        ),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--execution-plan", type=Path, default=DEFAULT_EXECUTION_PLAN)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--expected-manifest", type=Path, default=DEFAULT_INPUT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--probe-source-urls", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_public_benchmark_vina_gnina_input_manifest_template_preflight(
        repo_root=args.repo_root,
        execution_plan=args.execution_plan,
        template=args.template,
        expected_manifest=args.expected_manifest,
        out=args.out,
        out_md=args.out_md,
        probe_source_urls=args.probe_source_urls,
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-input-manifest-template-preflight: "
            f"{payload['status']} | rows={payload['case_preflight_row_count']} | "
            f"manifest_ready={payload['manifest_ready']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
