#!/usr/bin/env python3
"""Build a source-bound technical receipt for the 10-case IFC import-health lane."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from acquire_buildingsmart_ifc_current_source import (  # noqa: E402
    ManifestError,
    build_acquisition_receipt,
    validate_manifest,
)
from build_phase3_ifc_import_health_execution_receipt import (  # noqa: E402
    _candidate_rows,
)
from structural_analysis.io.ifc.loader import (  # noqa: E402
    LOAD_GROUP_ENTITY_TYPES,
    LOAD_RELATIONSHIP_ENTITY_TYPES,
    MATERIAL_ENTITY_PREFIXES,
    SECTION_ENTITY_SUFFIXES,
    STRUCTURAL_ENTITY_TYPES,
)
from structural_analysis.results.schema import AnalysisResult  # noqa: E402
from structural_analysis.results.validation import validate  # noqa: E402

PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MANIFEST = Path(
    "benchmarks/import_health/buildingsmart_ifc_current_source.v1.json"
)
DEFAULT_SCHEMA = Path(
    "canonical/ifc-import-health-current-source-technical-receipt.v1.schema.json"
)
DEFAULT_ACQUISITION = Path(
    ".ci/ifc-import-health-current-source/acquisition-receipt.json"
)
DEFAULT_OUTPUT = Path(".ci/ifc-import-health-current-source/technical-receipt.json")
DEFAULT_SUPPORT_DIR = Path(".ci/ifc-import-health-current-source/support")
RESULT_SCHEMA = Path("src/structural_analysis/schemas/result.schema.json")
CLEAN_ACQUISITION = PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"
DIRTY_ACQUISITION = (
    PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
)
IMPORT_HEALTH = PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
SOURCE_LICENSE = PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
SILENT_IMPORT_LOSS = PRODUCTIZATION / "phase6_silent_import_loss_status.json"
RECEIPT_SCHEMA_VERSION = "ifc-import-health-current-source-technical-receipt.v1"
EXPECTED_CASE_COUNT = 10
EXPECTED_CLEAN_COUNT = 2
EXPECTED_DIRTY_COUNT = 8
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RAW_ASSIGNMENT_RE = re.compile(r"#(?P<id>[0-9]+)\s*=")
SUPPORT_ARTIFACT_PREFIX = Path("support/repository")


class ReceiptError(ValueError):
    """Raised when current-source evidence cannot be interpreted safely."""


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        raise ReceiptError(f"supporting_receipt_missing:{path.as_posix()}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReceiptError(
            f"supporting_receipt_unreadable:{path.as_posix()}:{exc.__class__.__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReceiptError(f"supporting_receipt_not_object:{path.as_posix()}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _repo_relative_path(repo_root: Path, path: Path) -> Path:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        return resolved.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ReceiptError(f"support_path_outside_repository:{path.as_posix()}") from exc


def _support_artifact_path(repo_root: Path, path: Path) -> str:
    relative = _repo_relative_path(repo_root, path)
    return (SUPPORT_ARTIFACT_PREFIX / relative).as_posix()


def _raw_step_assignment_ids(path: Path) -> list[str]:
    """Count STEP entity assignments independently of the product IFC parser."""

    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise ReceiptError(f"raw_ifc_file_unavailable:{path.as_posix()}") from exc
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReceiptError(f"raw_ifc_utf8_decode_failed:{path.as_posix()}") from exc
    masked: list[str] = []
    index = 0
    in_string = False
    in_comment = False
    while index < len(text):
        if in_comment:
            if text.startswith("*/", index):
                masked.extend((" ", " "))
                index += 2
                in_comment = False
            else:
                masked.append("\n" if text[index] == "\n" else " ")
                index += 1
            continue
        if in_string:
            char = text[index]
            masked.append("\n" if char == "\n" else " ")
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    masked.append(" ")
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if text.startswith("/*", index):
            masked.extend((" ", " "))
            index += 2
            in_comment = True
            continue
        if text[index] == "'":
            masked.append(" ")
            index += 1
            in_string = True
            continue
        masked.append(text[index])
        index += 1
    if in_comment:
        raise ReceiptError(f"raw_ifc_unterminated_comment:{path.as_posix()}")
    if in_string:
        raise ReceiptError(f"raw_ifc_unterminated_string:{path.as_posix()}")
    return [match.group("id") for match in RAW_ASSIGNMENT_RE.finditer("".join(masked))]


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ReceiptError(f"git_source_identity_failed:{args[0]}")
    return [line for line in completed.stdout.splitlines() if line]


def _git_source_binding(
    repo_root: Path,
    source_commit_sha: str,
    *,
    allowed_generated_paths: list[Path],
) -> dict[str, Any]:
    head_lines = _git_lines(repo_root, "rev-parse", "HEAD")
    tree_lines = _git_lines(repo_root, "rev-parse", "HEAD^{tree}")
    top_lines = _git_lines(repo_root, "rev-parse", "--show-toplevel")
    if len(head_lines) != 1 or len(tree_lines) != 1 or len(top_lines) != 1:
        raise ReceiptError("git_source_identity_shape_invalid")
    if Path(top_lines[0]).resolve() != repo_root.resolve():
        raise ReceiptError("git_source_repository_root_mismatch")
    allowed = {
        _repo_relative_path(repo_root, path).as_posix()
        for path in allowed_generated_paths
    }
    changed = set(_git_lines(repo_root, "diff", "--name-only", "HEAD", "--"))
    changed.update(_git_lines(repo_root, "diff", "--cached", "--name-only", "--"))
    changed.update(
        _git_lines(repo_root, "ls-files", "--others", "--exclude-standard")
    )
    dirty_source_paths = sorted(path for path in changed if path not in allowed)
    changed_generated_paths = sorted(path for path in changed if path in allowed)
    head_sha = head_lines[0]
    return {
        "verification_mode": "git_exact_source_with_generated_evidence_allowlist",
        "declared_source_commit_sha": source_commit_sha,
        "git_head_commit_sha": head_sha,
        "git_head_tree_sha": tree_lines[0],
        "source_commit_matches": head_sha == source_commit_sha,
        "source_tree_clean": not dirty_source_paths,
        "changed_generated_paths": changed_generated_paths,
        "dirty_source_paths": dirty_source_paths,
    }


def _is_load_related_entity(entity_type: str) -> bool:
    return (
        entity_type in LOAD_GROUP_ENTITY_TYPES
        or entity_type in LOAD_RELATIONSHIP_ENTITY_TYPES
        or (
            entity_type.startswith("IFCSTRUCTURALLOAD")
            and entity_type not in LOAD_GROUP_ENTITY_TYPES
        )
        or (entity_type.startswith("IFCSTRUCTURAL") and "ACTION" in entity_type)
    )


def _validate_result_and_report(
    *,
    repo_root: Path,
    case_id: str,
    manifest_row: dict[str, Any],
    import_row: dict[str, Any],
    contract_row: dict[str, Any],
    raw_record_count: int,
) -> tuple[list[str], Path | None, Path | None, dict[str, Any]]:
    blockers: list[str] = []
    execution = import_row.get("execution")
    if not isinstance(execution, dict):
        return ["case_execution_receipt_missing"], None, None, {}
    result_path = _relative_evidence_path(
        repo_root,
        execution.get("result_path"),
        case_id,
    )
    report_path = _relative_evidence_path(
        repo_root,
        execution.get("report_path"),
        case_id,
    )
    result = _load_json(repo_root, result_path)
    report = _load_json(repo_root, report_path)
    result_schema = _load_json(repo_root, RESULT_SCHEMA)
    schema_errors = sorted(
        Draft202012Validator(result_schema).iter_errors(result),
        key=lambda error: list(error.path),
    )
    if schema_errors:
        blockers.append("result_schema_invalid")
        result_object = None
    else:
        try:
            result_object = AnalysisResult(**result)
        except (TypeError, ValueError):
            blockers.append("result_envelope_invalid")
            result_object = None
    if result_object is not None:
        expected_report = validate(result_object).to_dict()
        if report != expected_report:
            blockers.append("report_authoritative_replay_mismatch")
    if execution.get("result") != result:
        blockers.append("execution_embedded_result_mismatch")
    if execution.get("report") != report:
        blockers.append("execution_embedded_report_mismatch")
    if execution.get("result_exists") is not True:
        blockers.append("execution_result_exists_not_true")
    if execution.get("report_exists") is not True:
        blockers.append("execution_report_exists_not_true")
    if execution.get("return_code") != 2:
        blockers.append("execution_return_code_invalid")
    expected_sha = manifest_row.get("sha256")
    for name, payload in (("result", result), ("report", report)):
        if payload.get("input_checksum") != expected_sha:
            blockers.append(f"{name}_input_checksum_mismatch")
        if payload.get("status") != "blocked":
            blockers.append(f"{name}_status_not_blocked")
    if result.get("analysis_type") != "model_health":
        blockers.append("result_analysis_type_invalid")
    if result.get("solver") != "developer_preview_model_health":
        blockers.append("result_solver_invalid")
    if report.get("contract_pass") is not False:
        blockers.append("report_contract_pass_not_false")
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        blockers.append("result_metrics_invalid")
        metrics = {}
    entity_counts = metrics.get("entity_counts")
    if not isinstance(entity_counts, dict) or not all(
        isinstance(key, str)
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        for key, value in entity_counts.items()
    ):
        blockers.append("entity_counts_invalid")
        entity_counts = {}
    parsed_record_count = metrics.get("parsed_record_count")
    parser_record_count = metrics.get("record_count")
    entity_count_sum = sum(entity_counts.values())
    if not (
        isinstance(parsed_record_count, int)
        and not isinstance(parsed_record_count, bool)
        and isinstance(parser_record_count, int)
        and not isinstance(parser_record_count, bool)
        and raw_record_count
        == parser_record_count
        == parsed_record_count
        == entity_count_sum
    ):
        blockers.append("raw_parser_entity_accounting_mismatch")
    raw_ids = _raw_step_assignment_ids(repo_root / str(manifest_row["local_path"]))
    if len(raw_ids) != len(set(raw_ids)):
        blockers.append("raw_duplicate_entity_ids")
    expected_structural = sum(
        count for entity, count in entity_counts.items() if entity in STRUCTURAL_ENTITY_TYPES
    )
    expected_material = sum(
        count
        for entity, count in entity_counts.items()
        if any(entity.startswith(prefix) for prefix in MATERIAL_ENTITY_PREFIXES)
    )
    expected_section = sum(
        count
        for entity, count in entity_counts.items()
        if not any(entity.startswith(prefix) for prefix in MATERIAL_ENTITY_PREFIXES)
        and any(entity.endswith(suffix) for suffix in SECTION_ENTITY_SUFFIXES)
    )
    expected_load = sum(
        count for entity, count in entity_counts.items() if _is_load_related_entity(entity)
    )
    expected_class_counts = {
        "structural_entity_count": expected_structural,
        "material_entity_count": expected_material,
        "section_entity_count": expected_section,
        "load_related_entity_count": expected_load,
    }
    for key, expected in expected_class_counts.items():
        if metrics.get(key) != expected:
            blockers.append(f"entity_class_accounting_mismatch:{key}")
    if metrics.get("element_count") != expected_structural:
        blockers.append("element_structural_count_mismatch")
    if metrics.get("load_count") != expected_load:
        blockers.append("load_entity_count_mismatch")
    if metrics.get("text_scan_only") is not True:
        blockers.append("result_text_scan_boundary_missing")
    contract = contract_row.get("contract")
    if not isinstance(contract, dict):
        blockers.append("case_contract_missing")
        contract = {}
    warnings = result.get("warnings")
    unsupported = result.get("unsupported_features")
    if not isinstance(warnings, list):
        warnings = []
    if not isinstance(unsupported, list):
        unsupported = []
    unsupported_kinds = {
        row.get("kind") for row in unsupported if isinstance(row, dict)
    }
    for fragment in contract.get("required_warning_fragments", []):
        if not any(isinstance(warning, str) and fragment in warning for warning in warnings):
            blockers.append("required_warning_missing")
    for kind in contract.get("required_blocked_fields", []):
        if kind not in unsupported_kinds:
            blockers.append(f"required_unsupported_kind_missing:{kind}")
    for entity_type in contract.get("expected_structural_classes_present", []):
        if int(entity_counts.get(entity_type, 0)) <= 0:
            blockers.append(f"expected_structural_class_missing:{entity_type}")
    silent_gate = import_row.get("silent_import_loss_gate")
    if not isinstance(silent_gate, dict):
        blockers.append("case_silent_import_loss_gate_missing")
    else:
        expected_gate_values = {
            "record_count": parser_record_count,
            "parsed_record_count": parsed_record_count,
            **expected_class_counts,
            "visible_entity_accounting": not any(
                blocker.startswith("entity_")
                or blocker == "raw_parser_entity_accounting_mismatch"
                for blocker in blockers
            ),
        }
        for key, expected in expected_gate_values.items():
            if silent_gate.get(key) != expected:
                blockers.append(f"silent_gate_metric_mismatch:{key}")
        if blockers:
            if silent_gate.get("contract_pass") is True:
                blockers.append("silent_gate_false_positive")
        elif silent_gate.get("contract_pass") is not True:
            blockers.append("silent_gate_not_passed")
    return sorted(set(blockers)), result_path, report_path, metrics


def _relative_evidence_path(repo_root: Path, value: Any, case_id: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReceiptError(f"case_evidence_path_missing:{case_id}")
    declared = Path(value)
    if declared.is_absolute() or ".." in declared.parts:
        raise ReceiptError(f"case_evidence_path_invalid:{case_id}:{value}")
    resolved = (repo_root / declared).resolve()
    evidence_root = (repo_root / PRODUCTIZATION).resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError as exc:
        raise ReceiptError(
            f"case_evidence_path_outside_productization:{case_id}"
        ) from exc
    if not resolved.exists() or not resolved.is_file():
        raise ReceiptError(f"case_evidence_file_missing:{case_id}:{value}")
    return declared


def _receipt_binding(
    repo_root: Path,
    path: Path,
    payload: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    observed_source_sha = payload.get("source_commit_sha")
    return {
        "path": path.as_posix(),
        "artifact_path": _support_artifact_path(repo_root, path),
        "sha256": _sha256(repo_root / path),
        "source_commit_sha": observed_source_sha,
        "source_commit_matches": observed_source_sha == source_commit_sha,
        "schema_version": payload.get("schema_version", ""),
    }


def _support_manifest_entries(
    *,
    repo_root: Path,
    paths: list[Path],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_source_paths: set[str] = set()
    seen_artifact_paths: set[str] = set()
    for path in paths:
        relative = _repo_relative_path(repo_root, path)
        source_path = relative.as_posix()
        artifact_path = _support_artifact_path(repo_root, path)
        if source_path in seen_source_paths:
            continue
        if artifact_path in seen_artifact_paths:
            raise ReceiptError(f"support_artifact_path_collision:{artifact_path}")
        source = repo_root / relative
        if not source.is_file() or source.suffix != ".json":
            raise ReceiptError(f"support_json_file_required:{source_path}")
        seen_source_paths.add(source_path)
        seen_artifact_paths.add(artifact_path)
        entries.append(
            {
                "source_path": source_path,
                "artifact_path": artifact_path,
                "sha256": _sha256(source),
            }
        )
    return sorted(entries, key=lambda row: row["artifact_path"])


def _copy_support_files(
    *,
    repo_root: Path,
    support_dir: Path,
    entries: list[dict[str, Any]],
) -> None:
    resolved_support = (
        support_dir if support_dir.is_absolute() else repo_root / support_dir
    )
    resolved_support.mkdir(parents=True, exist_ok=True)
    expected_paths = {
        Path(str(row["artifact_path"])).relative_to(SUPPORT_ARTIFACT_PREFIX.parent)
        for row in entries
    }
    unexpected = sorted(
        path.relative_to(resolved_support).as_posix()
        for path in resolved_support.rglob("*")
        if path.is_symlink()
        or (path.is_file() and path.relative_to(resolved_support) not in expected_paths)
    )
    if unexpected:
        raise ReceiptError(f"support_bundle_unexpected_entries:{','.join(unexpected)}")
    for row in entries:
        source = repo_root / str(row["source_path"])
        relative_target = Path(str(row["artifact_path"])).relative_to(
            SUPPORT_ARTIFACT_PREFIX.parent
        )
        target = resolved_support / relative_target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def verify_support_bundle(
    payload: dict[str, Any],
    *,
    bundle_root: Path,
) -> tuple[bool, str]:
    support_manifest = payload.get("support_manifest")
    if not isinstance(support_manifest, dict):
        return False, "support_manifest_missing"
    entries = support_manifest.get("entries")
    if not isinstance(entries, list):
        return False, "support_manifest_entries_invalid"
    if support_manifest.get("file_count") != len(entries):
        return False, "support_manifest_file_count_mismatch"
    if support_manifest.get("sha256") != _canonical_sha256(entries):
        return False, "support_manifest_digest_mismatch"
    expected_paths: set[str] = set()
    for row in entries:
        if not isinstance(row, dict):
            return False, "support_manifest_entry_invalid"
        artifact_path = row.get("artifact_path")
        expected_sha = row.get("sha256")
        if not isinstance(artifact_path, str) or not artifact_path:
            return False, "support_manifest_artifact_path_invalid"
        declared = Path(artifact_path)
        if declared.is_absolute() or ".." in declared.parts:
            return False, "support_manifest_artifact_path_unsafe"
        resolved = (bundle_root / declared).resolve()
        try:
            resolved.relative_to(bundle_root.resolve())
        except ValueError:
            return False, "support_manifest_artifact_path_outside_bundle"
        if not resolved.is_file() or resolved.is_symlink():
            return False, f"support_manifest_file_missing:{artifact_path}"
        if not isinstance(expected_sha, str) or SHA256_RE.fullmatch(expected_sha) is None:
            return False, "support_manifest_sha256_invalid"
        if _sha256(resolved) != expected_sha:
            return False, f"support_manifest_file_hash_mismatch:{artifact_path}"
        expected_paths.add(declared.as_posix())
    support_root = bundle_root / SUPPORT_ARTIFACT_PREFIX.parent
    observed_paths = {
        path.relative_to(bundle_root).as_posix()
        for path in support_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if observed_paths != expected_paths:
        return False, "support_manifest_file_set_mismatch"
    return True, "support_bundle_integrity_consistent_nonfresh"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def validate_receipt_schema(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    schema_path: Path = DEFAULT_SCHEMA,
) -> None:
    schema = _load_json(repo_root, schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "$"
        raise ReceiptError(
            f"technical_receipt_schema_invalid:{location}:{first.message}"
        )


def build_current_source_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    acquisition_path: Path = DEFAULT_ACQUISITION,
    schema_path: Path = DEFAULT_SCHEMA,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo_root = repo_root.resolve()
    if COMMIT_RE.fullmatch(source_commit_sha) is None:
        raise ReceiptError("source_commit_sha_invalid")
    manifest = _load_json(repo_root, manifest_path)
    try:
        validate_manifest(manifest, require_canonical_identity=True)
    except ManifestError as exc:
        raise ReceiptError(f"manifest_validation_failed:{exc}") from exc
    acquisition = _load_json(repo_root, acquisition_path)
    support_payloads = {
        CLEAN_ACQUISITION: _load_json(repo_root, CLEAN_ACQUISITION),
        DIRTY_ACQUISITION: _load_json(repo_root, DIRTY_ACQUISITION),
        IMPORT_HEALTH: _load_json(repo_root, IMPORT_HEALTH),
        SOURCE_LICENSE: _load_json(repo_root, SOURCE_LICENSE),
        SILENT_IMPORT_LOSS: _load_json(repo_root, SILENT_IMPORT_LOSS),
    }
    technical_blockers: list[str] = []
    manifest_cases = manifest.get("cases")
    if not isinstance(manifest_cases, list):
        raise ReceiptError("manifest_cases_invalid")
    manifest_case_map = {
        str(row.get("case_id")): row
        for row in manifest_cases
        if isinstance(row, dict) and row.get("case_id")
    }
    if len(manifest_case_map) != EXPECTED_CASE_COUNT:
        technical_blockers.append("manifest_case_set_invalid")

    replayed_acquisition = build_acquisition_receipt(
        repo_root=repo_root,
        manifest_path=manifest_path,
        source_commit_sha=source_commit_sha,
        download_missing=False,
        require_canonical_identity=True,
    )
    if replayed_acquisition.get("technical_contract_pass") is not True:
        technical_blockers.append("current_raw_source_or_license_replay_blocked")
        technical_blockers.extend(
            f"current_raw_replay:{blocker}"
            for blocker in replayed_acquisition.get("blockers", [])
        )
    if _strip_volatile(acquisition) != _strip_volatile(replayed_acquisition):
        technical_blockers.append("acquisition_receipt_current_raw_replay_mismatch")

    if acquisition.get("source_commit_sha") != source_commit_sha:
        technical_blockers.append("acquisition_source_commit_mismatch")
    if acquisition.get("manifest_sha256") != _sha256(repo_root / manifest_path):
        technical_blockers.append("acquisition_manifest_hash_mismatch")
    if acquisition.get("technical_contract_pass") is not True:
        technical_blockers.append("acquisition_technical_contract_not_passed")
    acquisition_artifacts = acquisition.get("artifacts")
    if not isinstance(acquisition_artifacts, list):
        raise ReceiptError("acquisition_artifacts_invalid")
    acquired_cases = {
        str(row.get("case_id")): row
        for row in acquisition_artifacts
        if isinstance(row, dict) and row.get("artifact_kind") == "case"
    }
    acquired_licenses = [
        row
        for row in acquisition_artifacts
        if isinstance(row, dict) and row.get("artifact_kind") == "license"
    ]
    if len(acquired_cases) != len(
        [
            row
            for row in acquisition_artifacts
            if isinstance(row, dict) and row.get("artifact_kind") == "case"
        ]
    ):
        technical_blockers.append("acquisition_duplicate_case_rows")
    if set(acquired_cases) != set(manifest_case_map):
        technical_blockers.append("acquisition_case_set_mismatch")
    if len(acquired_licenses) != 2 or not all(
        row.get("verified") is True for row in acquired_licenses
    ):
        technical_blockers.append("upstream_license_material_not_exact")

    contract_rows = _candidate_rows(repo_root, source_commit_sha)
    contract_case_map = {
        str(row.get("case_id")): row
        for row in contract_rows
        if isinstance(row, dict) and row.get("case_id")
    }
    if set(contract_case_map) != set(manifest_case_map):
        technical_blockers.append("execution_contract_case_set_mismatch")

    import_health = support_payloads[IMPORT_HEALTH]
    import_cases_raw = import_health.get("case_receipts")
    if not isinstance(import_cases_raw, list):
        raise ReceiptError("import_health_case_receipts_invalid")
    import_case_map = {
        str(row.get("case_id")): row
        for row in import_cases_raw
        if isinstance(row, dict) and row.get("case_id")
    }
    if len(import_case_map) != len(import_cases_raw):
        technical_blockers.append("import_health_duplicate_case_rows")
    if set(import_case_map) != set(manifest_case_map):
        technical_blockers.append("import_health_case_set_mismatch")

    case_receipts: list[dict[str, Any]] = []
    support_files: list[Path] = [
        acquisition_path,
        *support_payloads.keys(),
    ]
    for case_id in sorted(manifest_case_map):
        manifest_row = manifest_case_map[case_id]
        acquired_row = acquired_cases.get(case_id, {})
        import_row = import_case_map.get(case_id, {})
        contract_row = contract_case_map.get(case_id, {})
        case_blockers: list[str] = []
        if acquired_row.get("verified") is not True:
            case_blockers.append("source_bytes_not_verified")
        if acquired_row.get("expected_sha256") != manifest_row.get("sha256"):
            case_blockers.append("acquisition_expected_hash_manifest_mismatch")
        if acquired_row.get("observed_sha256") != manifest_row.get("sha256"):
            case_blockers.append("acquisition_observed_hash_manifest_mismatch")
        if import_row.get("source_sha256") != manifest_row.get("sha256"):
            case_blockers.append("import_source_hash_manifest_mismatch")
        if import_row.get("lane_kind") != manifest_row.get("lane_kind"):
            case_blockers.append("import_lane_kind_manifest_mismatch")
        if import_row.get("local_path") != manifest_row.get("local_path"):
            case_blockers.append("import_local_path_manifest_mismatch")
        if import_row.get("source_url") != manifest_row.get("download_url"):
            case_blockers.append("import_source_url_manifest_mismatch")
        if contract_row.get("lane_kind") != manifest_row.get("lane_kind"):
            case_blockers.append("contract_lane_kind_manifest_mismatch")
        if contract_row.get("local_path") != manifest_row.get("local_path"):
            case_blockers.append("contract_local_path_manifest_mismatch")
        if contract_row.get("source_url") != manifest_row.get("download_url"):
            case_blockers.append("contract_source_url_manifest_mismatch")
        if import_row.get("source_file_acquired") is not True:
            case_blockers.append("import_source_not_acquired")
        if import_row.get("import_health_executed") is not True:
            case_blockers.append("import_health_not_executed")
        if import_row.get("import_health_contract_pass") is not True:
            case_blockers.append("import_health_contract_not_passed")
        silent_gate = import_row.get("silent_import_loss_gate")
        if (
            not isinstance(silent_gate, dict)
            or silent_gate.get("contract_pass") is not True
        ):
            case_blockers.append("case_silent_import_loss_gate_not_passed")
        elif silent_gate.get("visible_entity_accounting") is not True:
            case_blockers.append("case_visible_entity_accounting_missing")
        raw_path = repo_root / str(manifest_row["local_path"])
        raw_assignment_ids = _raw_step_assignment_ids(raw_path)
        raw_record_count = len(raw_assignment_ids)
        semantic_blockers, result_path, report_path, result_metrics = (
            _validate_result_and_report(
                repo_root=repo_root,
                case_id=case_id,
                manifest_row=manifest_row,
                import_row=import_row,
                contract_row=contract_row,
                raw_record_count=raw_record_count,
            )
        )
        case_blockers.extend(semantic_blockers)
        if result_path is not None and report_path is not None:
            support_files.extend([result_path, report_path])
        if case_blockers:
            technical_blockers.extend(f"{case_id}:{item}" for item in case_blockers)
        entity_counts = result_metrics.get("entity_counts", {})
        entity_count_sum = (
            sum(entity_counts.values())
            if isinstance(entity_counts, dict)
            and all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
                for value in entity_counts.values()
            )
            else None
        )
        case_receipts.append(
            {
                "case_id": case_id,
                "lane_kind": manifest_row.get("lane_kind"),
                "upstream_repository": manifest_row.get("upstream_repository"),
                "upstream_commit_sha": manifest_row.get("upstream_commit_sha"),
                "upstream_path": manifest_row.get("upstream_path"),
                "source_sha256": manifest_row.get("sha256"),
                "source_byte_length": manifest_row.get("byte_length"),
                "license_id": manifest_row.get("license_id"),
                "import_health_executed": import_row.get("import_health_executed")
                is True,
                "import_health_contract_pass": import_row.get(
                    "import_health_contract_pass"
                )
                is True,
                "silent_import_loss_gate_pass": isinstance(silent_gate, dict)
                and silent_gate.get("contract_pass") is True,
                "visible_entity_accounting": isinstance(silent_gate, dict)
                and silent_gate.get("visible_entity_accounting") is True,
                "raw_record_count": raw_record_count,
                "record_count": silent_gate.get("record_count")
                if isinstance(silent_gate, dict)
                else None,
                "parsed_record_count": silent_gate.get("parsed_record_count")
                if isinstance(silent_gate, dict)
                else None,
                "entity_count_sum": entity_count_sum,
                "result_path": result_path.as_posix() if result_path else "",
                "result_artifact_path": _support_artifact_path(repo_root, result_path)
                if result_path
                else "",
                "result_sha256": _sha256(repo_root / result_path)
                if result_path
                else "",
                "report_path": report_path.as_posix() if report_path else "",
                "report_artifact_path": _support_artifact_path(repo_root, report_path)
                if report_path
                else "",
                "report_sha256": _sha256(repo_root / report_path)
                if report_path
                else "",
                "technical_contract_pass": not case_blockers,
                "blockers": case_blockers,
            }
        )

    all_support_payloads = {acquisition_path: acquisition, **support_payloads}
    support_bindings = {
        path.name: _receipt_binding(repo_root, path, payload, source_commit_sha)
        for path, payload in all_support_payloads.items()
    }
    for name, binding in support_bindings.items():
        if binding["source_commit_matches"] is not True:
            technical_blockers.append(
                f"supporting_receipt_source_commit_mismatch:{name}"
            )
    silent_status = support_payloads[SILENT_IMPORT_LOSS]
    if silent_status.get("technical_silent_import_loss_zero") is not True:
        technical_blockers.append("phase6_technical_silent_import_loss_zero_not_proven")
    if silent_status.get("technical_direct_blockers") not in ([], None):
        technical_blockers.append("phase6_technical_direct_blockers_present")
    expected_counts = {
        "source_file_acquired_count": EXPECTED_CASE_COUNT,
        "source_checksum_attached_count": EXPECTED_CASE_COUNT,
        "import_health_execution_count": EXPECTED_CASE_COUNT,
        "import_health_contract_pass_count": EXPECTED_CASE_COUNT,
        "visible_entity_accounting_case_count": EXPECTED_CASE_COUNT,
        "silent_import_loss_gate_pass_count": EXPECTED_CASE_COUNT,
    }
    for key, expected in expected_counts.items():
        if import_health.get(key) != expected:
            technical_blockers.append(f"import_health_count_invalid:{key}")
    lane_counts = {
        "clean": sum(row["lane_kind"] == "clean" for row in case_receipts),
        "dirty": sum(row["lane_kind"] == "dirty" for row in case_receipts),
    }
    if lane_counts != {"clean": EXPECTED_CLEAN_COUNT, "dirty": EXPECTED_DIRTY_COUNT}:
        technical_blockers.append("import_health_lane_counts_invalid")
    source_identity = _git_source_binding(
        repo_root,
        source_commit_sha,
        allowed_generated_paths=support_files,
    )
    if source_identity["source_commit_matches"] is not True:
        technical_blockers.append("git_head_source_commit_mismatch")
    if source_identity["source_tree_clean"] is not True:
        technical_blockers.append("git_source_tree_dirty")
    support_entries = _support_manifest_entries(
        repo_root=repo_root,
        paths=support_files,
    )
    if len(support_entries) != 26:
        technical_blockers.append("support_manifest_file_count_invalid")
    technical_blockers = sorted(set(technical_blockers))
    technical_contract_pass = not technical_blockers

    source_license = support_payloads[SOURCE_LICENSE]
    nontechnical_blockers = sorted(
        {
            str(blocker)
            for blocker in [
                *source_license.get("blockers", []),
                *silent_status.get("product_release_credit_blockers", []),
                "current_source_technical_workflow_not_product_legal_authority",
            ]
            if str(blocker)
        }
    )
    legal_and_product_blockers = [
        blocker
        for blocker in nontechnical_blockers
        if any(
            token in blocker
            for token in (
                "license",
                "legal",
                "quantity_credit",
                "product_legal_authority",
            )
        )
    ]
    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "source_identity": source_identity,
        "status": "technical_ready_product_authority_blocked"
        if technical_contract_pass
        else "technical_blocked",
        "technical_contract_pass": technical_contract_pass,
        "receipt_schema": {
            "path": schema_path.as_posix(),
            "sha256": _sha256(repo_root / schema_path),
        },
        "manifest": {
            "path": manifest_path.as_posix(),
            "sha256": _sha256(repo_root / manifest_path),
            "schema_version": manifest.get("schema_version"),
            "case_count": len(manifest_case_map),
            "storage_boundary": manifest.get("storage_boundary"),
        },
        "counts": {
            "required_case_count": EXPECTED_CASE_COUNT,
            "case_count": len(case_receipts),
            "clean_case_count": lane_counts["clean"],
            "dirty_case_count": lane_counts["dirty"],
            "source_file_acquired_count": import_health.get(
                "source_file_acquired_count", 0
            ),
            "source_checksum_attached_count": import_health.get(
                "source_checksum_attached_count", 0
            ),
            "import_health_execution_count": import_health.get(
                "import_health_execution_count", 0
            ),
            "import_health_contract_pass_count": import_health.get(
                "import_health_contract_pass_count", 0
            ),
            "visible_entity_accounting_case_count": import_health.get(
                "visible_entity_accounting_case_count", 0
            ),
            "silent_import_loss_gate_pass_count": import_health.get(
                "silent_import_loss_gate_pass_count", 0
            ),
        },
        "claims": {
            "same_operator_current_source_execution": technical_contract_pass,
            "immutable_source_and_license_byte_identity": technical_contract_pass,
            "technical_silent_import_loss_zero": technical_contract_pass,
            "text_scan_import_health_only": True,
            "solver_ready_geometry_or_topology": False,
            "independent_reproduction": False,
            "product_legal_approval": False,
            "redistribution_authority": False,
            "commercial_use_authority": False,
            "phase3_quantity_credit": False,
            "release_authority": False,
        },
        "case_receipts": case_receipts,
        "supporting_receipts": support_bindings,
        "support_manifest": {
            "file_count": len(support_entries),
            "sha256": _canonical_sha256(support_entries),
            "entries": support_entries,
        },
        "technical_blockers": technical_blockers,
        "legal_and_product_blockers": legal_and_product_blockers,
        "nontechnical_blockers": nontechnical_blockers,
        "spillover_blockers": silent_status.get("spillover_blockers", []),
        "raw_ifc_files_uploaded": False,
        "claim_boundary": (
            "This source-bound artifact proves exact-byte acquisition and same-operator "
            "model-health execution for ten clean/dirty IFC files, including visible entity "
            "accounting and the scoped technical silent-import-loss-zero gate. The adapter is "
            "still a STEP text scan. Raw IFC files remain in ignored private_corpus storage. "
            "The artifact does not prove canonical geometry/topology, independent reproduction, "
            "product/legal approval, redistribution or commercial-use permission, Phase 3 "
            "quantity credit, or release authority."
        ),
    }
    return payload, support_entries


def write_current_source_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    acquisition_path: Path = DEFAULT_ACQUISITION,
    schema_path: Path = DEFAULT_SCHEMA,
    out_path: Path = DEFAULT_OUTPUT,
    support_dir: Path = DEFAULT_SUPPORT_DIR,
    copy_support: bool = True,
) -> dict[str, Any]:
    payload, support_entries = build_current_source_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        schema_path=schema_path,
    )
    validate_receipt_schema(payload, repo_root=repo_root, schema_path=schema_path)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    if copy_support:
        _copy_support_files(
            repo_root=repo_root,
            support_dir=support_dir,
            entries=support_entries,
        )
        ok, message = verify_support_bundle(payload, bundle_root=resolved.parent)
        if not ok:
            raise ReceiptError(message)
    return payload


def check_current_source_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    acquisition_path: Path = DEFAULT_ACQUISITION,
    schema_path: Path = DEFAULT_SCHEMA,
    out_path: Path = DEFAULT_OUTPUT,
) -> tuple[bool, str]:
    expected, _ = build_current_source_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        schema_path=schema_path,
    )
    validate_receipt_schema(expected, repo_root=repo_root, schema_path=schema_path)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"current_source_receipt_missing:{out_path.as_posix()}"
    existing = _load_json(repo_root, out_path)
    validate_receipt_schema(existing, repo_root=repo_root, schema_path=schema_path)
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "current_source_receipt_mismatch"
    if expected["technical_contract_pass"] is not True:
        return False, "current_source_technical_contract_blocked"
    bundle_ok, bundle_message = verify_support_bundle(
        existing,
        bundle_root=resolved.parent,
    )
    if not bundle_ok:
        return False, bundle_message
    return True, "current_source_receipt_consistent_and_technical_ready"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit-sha")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--acquisition", type=Path, default=DEFAULT_ACQUISITION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--support-dir", type=Path, default=DEFAULT_SUPPORT_DIR)
    parser.add_argument("--no-copy-support", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-support-bundle", action="store_true")
    parser.add_argument("--fail-technical-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check_support_bundle:
            existing = _load_json(ROOT, args.out)
            validate_receipt_schema(
                existing,
                repo_root=ROOT,
                schema_path=args.schema,
            )
            if (
                args.source_commit_sha is not None
                and existing.get("source_commit_sha") != args.source_commit_sha
            ):
                raise ReceiptError("support_bundle_source_commit_mismatch")
            resolved = args.out if args.out.is_absolute() else ROOT / args.out
            ok, message = verify_support_bundle(
                existing,
                bundle_root=resolved.parent,
            )
            print(f"IFC current-source support bundle check: {message}")
            return 0 if ok else 1
        if args.source_commit_sha is None:
            raise ReceiptError("source_commit_sha_required_for_fresh_execution")
        if args.check:
            ok, message = check_current_source_receipt(
                source_commit_sha=args.source_commit_sha,
                manifest_path=args.manifest,
                acquisition_path=args.acquisition,
                schema_path=args.schema,
                out_path=args.out,
            )
            print(f"IFC current-source receipt check: {message}")
            return 0 if ok else 1
        payload = write_current_source_receipt(
            source_commit_sha=args.source_commit_sha,
            manifest_path=args.manifest,
            acquisition_path=args.acquisition,
            schema_path=args.schema,
            out_path=args.out,
            support_dir=args.support_dir,
            copy_support=not args.no_copy_support,
        )
    except (ReceiptError, json.JSONDecodeError) as exc:
        print(f"IFC current-source receipt: technical_blocked | {exc}")
        return 1
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "IFC current-source receipt: "
            f"{payload['status']} | technical="
            f"{payload['counts']['import_health_contract_pass_count']}/"
            f"{payload['counts']['required_case_count']} | product_authority=false"
        )
    if args.fail_technical_blocked and payload["technical_contract_pass"] is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
