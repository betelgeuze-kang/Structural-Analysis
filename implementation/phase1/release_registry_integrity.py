#!/usr/bin/env python3
"""Strict technical-integrity verification for signed release registries.

This verifier authenticates bytes and package bindings only.  It deliberately
does not grant license, commercial-use, redistribution, third-party, or release
authority.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from typing import Any
import unicodedata
import zipfile

try:
    from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in dependency-minimal runtime
    InvalidSignature = Exception  # type: ignore[misc,assignment]
    UnsupportedAlgorithm = Exception  # type: ignore[misc,assignment]
    serialization = None  # type: ignore[assignment]
    Ed25519PublicKey = None  # type: ignore[assignment,misc]
    _CRYPTOGRAPHY_AVAILABLE = False


TECHNICAL_CONTRACT_SEMANTICS = "technical_package_integrity_and_workflow_completion_only"
PACKAGE_RIGHTS_STATUS_NAME = "LEGAL_AND_THIRD_PARTY_STATUS.json"
NO_LEGAL_AUTHORITY: dict[str, Any] = {
    "product_license_approval": False,
    "commercial_use_authority": False,
    "redistribution_authority": False,
    "third_party_redistribution_clearance": "not_established",
    "release_authority": False,
}
MAX_TECHNICAL_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_PROJECT_PACKAGE_ENTRIES = 2048
MAX_PROJECT_PACKAGE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_PROJECT_PACKAGE_COMPRESSION_RATIO = 100
TECHNICAL_PRODUCER_KEY_ENV = "STRUCTURAL_TECHNICAL_PRODUCER_PUBLIC_KEY_SHA256"
TECHNICAL_PRODUCER_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "canonical"
    / "technical-release-producer-key-policy.v1.json"
)
REPOSITORY_LICENSE_PATH = Path(__file__).resolve().parents[2] / "LICENSE"
REQUIRED_RELEASE_ARTIFACT_LABELS = frozenset(
    {
        "repro_report",
        "lock_manifest",
        "kds_summary",
        "midas_conversion",
        "solver_hip_e2e",
        "parser_script",
    }
)
PROJECT_TECHNICAL_ARTIFACT_LABELS = frozenset(
    {"release_registry_public_key", "release_registry_signature"}
)
VERIFIED_WORKFLOW_STRING_KEYS = frozenset(
    {
        "deployment_model",
        "external_benchmark_submission_preview_approve_all_reason_code",
        "external_benchmark_submission_preview_reject_one_reason_code",
        "audit_review_decision_batch_runner_reason_code",
        "mgt_export_audit_review_followup_status_label",
        "mgt_export_audit_review_queue_status_label",
        "mgt_export_audit_review_resolution_status_label",
        "mgt_export_connection_detailing_delivery_mode",
        "mgt_export_detailing_delivery_mode",
        "mgt_export_evidence_model",
        "mgt_export_support_mode",
    }
)
VERIFIED_WORKFLOW_BOOLEAN_KEYS = frozenset(
    {
        "audit_review_decision_batch_runner_preview_ready_full",
        "external_benchmark_submission_preview_approve_all_ready_full",
    }
)
VERIFIED_WORKFLOW_COUNT_KEYS = frozenset(
    {
        "audit_review_decision_batch_template_item_count",
        "external_benchmark_submission_preview_approve_all_open_revision_count",
        "external_benchmark_submission_preview_approve_all_pending_count",
        "mgt_export_audit_review_followup_item_count",
        "mgt_export_audit_review_packet_count",
        "mgt_export_audit_review_queue_item_count",
        "mgt_export_audit_review_queue_pending_count",
        "mgt_export_audit_review_resolution_item_count",
        "mgt_export_connection_detailing_structured_payload_mapped_change_count",
        "mgt_export_detailing_structured_payload_mapped_change_count",
        "mgt_export_direct_patch_change_count",
        "mgt_export_group_local_connection_detailing_payload_available_count",
        "mgt_export_group_local_detailing_payload_available_count",
        "mgt_export_group_local_rebar_payload_available_count",
        "mgt_export_instruction_sidecar_audit_only_change_count",
        "mgt_export_instruction_sidecar_manual_input_change_count",
    }
)


@dataclass(frozen=True)
class _FileSnapshot:
    path: Path
    payload: bytes
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int


def _canonical_bytes(payload: dict[str, Any], *, ensure_ascii: bool) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_json_object(payload: bytes) -> dict[str, Any] | None:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_json_key")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise ValueError("non_finite_json_number")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _rights_status_shape_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    repository_license = payload.get("repository_license")
    decision = payload.get("rights_holder_decision")
    third_party = payload.get("third_party_review")
    authority = payload.get("authority")
    return bool(
        set(payload)
        == {
            "schema_version",
            "generated_at",
            "repository_license",
            "rights_holder_decision",
            "third_party_review",
            "technical_contract_semantics",
            "signature_claim_boundary",
            "legal_claim_boundary",
            "authority",
        }
        and payload.get("schema_version") == "project-package-rights-status.v1"
        and isinstance(payload.get("generated_at"), str)
        and bool(payload.get("generated_at"))
        and isinstance(repository_license, dict)
        and set(repository_license) == {"source_path", "archive_path", "sha256", "bytes"}
        and repository_license.get("source_path") == "LICENSE"
        and repository_license.get("archive_path") == "LICENSE"
        and _is_sha256(repository_license.get("sha256"))
        and isinstance(repository_license.get("bytes"), int)
        and not isinstance(repository_license.get("bytes"), bool)
        and repository_license.get("bytes", 0) > 0
        and isinstance(decision, dict)
        and set(decision)
        == {
            "canonical_status_path",
            "closure_report_path",
            "verified",
            "signature_verified",
            "exact_source_binding_verified",
            "decision_id",
            "status",
        }
        and decision.get("verified") is False
        and decision.get("signature_verified") is False
        and decision.get("exact_source_binding_verified") is False
        and decision.get("decision_id") == ""
        and decision.get("status") == "not_provided"
        and isinstance(decision.get("canonical_status_path"), str)
        and bool(decision.get("canonical_status_path"))
        and isinstance(decision.get("closure_report_path"), str)
        and bool(decision.get("closure_report_path"))
        and isinstance(third_party, dict)
        and set(third_party)
        == {
            "notice_inventory_complete",
            "redistribution_conditions_verified",
            "status",
        }
        and third_party.get("notice_inventory_complete") is False
        and third_party.get("redistribution_conditions_verified") is False
        and third_party.get("status") == "not_established"
        and payload.get("technical_contract_semantics") == TECHNICAL_CONTRACT_SEMANTICS
        and isinstance(payload.get("signature_claim_boundary"), str)
        and bool(payload.get("signature_claim_boundary"))
        and isinstance(payload.get("legal_claim_boundary"), str)
        and bool(payload.get("legal_claim_boundary"))
        and authority == NO_LEGAL_AUTHORITY
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _safe_artifact_label(value: Any) -> str:
    label = value if isinstance(value, str) else ""
    try:
        encoded_label = label.encode("utf-8")
    except UnicodeError:
        return ""
    if (
        not label
        or label in {".", ".."}
        or len(encoded_label) > 255
        or any(character in label for character in ("/", "\\", "\0"))
        or unicodedata.normalize("NFKC", label) != label
        or any(
            ord(character) == 127
            or unicodedata.category(character) in {"Cc", "Cf"}
            for character in label
        )
    ):
        return ""
    return label


def _candidate_paths(raw: Any, *, registry_path: Path | None) -> list[Path]:
    text = str(raw or "").strip()
    if not text:
        return []
    path = Path(text)
    if path.is_absolute():
        return [path]
    candidates = [Path.cwd() / path]
    if registry_path is not None:
        registry_relative = registry_path.parent / path
        if registry_relative != candidates[0]:
            candidates.append(registry_relative)
    return candidates


def _read_regular_file(raw: Any, *, registry_path: Path | None) -> _FileSnapshot | None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    for candidate in _candidate_paths(raw, registry_path=registry_path):
        fd = -1
        try:
            fd = os.open(candidate, flags)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_TECHNICAL_ARTIFACT_BYTES:
                continue
            payload = bytearray()
            while len(payload) <= MAX_TECHNICAL_ARTIFACT_BYTES:
                chunk = os.read(fd, min(1024 * 1024, MAX_TECHNICAL_ARTIFACT_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            after = os.fstat(fd)
            stable = all(
                getattr(before, field) == getattr(after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            )
            if (
                not stable
                or len(payload) != before.st_size
                or len(payload) > MAX_TECHNICAL_ARTIFACT_BYTES
            ):
                continue
            return _FileSnapshot(
                path=candidate,
                payload=bytes(payload),
                device=int(before.st_dev),
                inode=int(before.st_ino),
                size=int(before.st_size),
                mtime_ns=int(before.st_mtime_ns),
                ctime_ns=int(before.st_ctime_ns),
            )
        except (OSError, ValueError):
            continue
        finally:
            if fd >= 0:
                os.close(fd)
    return None


def _same_file_reference(
    left: Any,
    right: Any,
    *,
    registry_path: Path | None,
) -> bool:
    left_file = _read_regular_file(left, registry_path=registry_path)
    right_file = _read_regular_file(right, registry_path=registry_path)
    if left_file is None or right_file is None:
        return False
    return _snapshots_same(left_file, right_file)


def _snapshots_same(left_file: _FileSnapshot, right_file: _FileSnapshot) -> bool:
    return bool(
        left_file.device == right_file.device
        and left_file.inode == right_file.inode
        and left_file.size == right_file.size
        and left_file.mtime_ns == right_file.mtime_ns
        and left_file.ctime_ns == right_file.ctime_ns
        and left_file.payload == right_file.payload
    )


def _producer_policy_valid() -> bool:
    policy = _read_regular_file(TECHNICAL_PRODUCER_POLICY_PATH, registry_path=None)
    if policy is None:
        return False
    try:
        payload = json.loads(policy.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload == {
        "schema_version": "technical-release-producer-key-policy.v1",
        "fingerprint_environment_variable": TECHNICAL_PRODUCER_KEY_ENV,
        "fingerprint_algorithm": "sha256",
        "approved_key_fingerprints": [],
        "technical_integrity_only": True,
        "legal_authority": False,
        "commercial_use_authority": False,
        "redistribution_authority": False,
        "release_authority": False,
    }


def _technical_producer_key_fingerprint_pass(snapshot: _FileSnapshot | None) -> bool:
    expected = str(os.environ.get(TECHNICAL_PRODUCER_KEY_ENV, "") or "").strip().lower()
    if expected.startswith("sha256:"):
        expected = expected.removeprefix("sha256:")
    return bool(
        snapshot is not None
        and _producer_policy_valid()
        and _is_sha256(expected)
        and _sha256(snapshot.payload) == expected
    )


def _verify_ed25519(
    body_bytes: bytes,
    *,
    signature_b64: Any,
    public_key_path: Any,
    registry_path: Path | None,
    public_key_snapshot: _FileSnapshot | None = None,
) -> bool:
    if not _CRYPTOGRAPHY_AVAILABLE:
        return False
    public_key_file = public_key_snapshot or _read_regular_file(
        public_key_path, registry_path=registry_path
    )
    if public_key_file is None:
        return False
    try:
        signature = base64.b64decode(str(signature_b64 or ""), validate=True)
        public_key = serialization.load_pem_public_key(public_key_file.payload)
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        public_key.verify(signature, body_bytes)
        return True
    except (ValueError, TypeError, binascii.Error, InvalidSignature, UnsupportedAlgorithm):
        return False


def _signature_file_matches(file_snapshot: _FileSnapshot | None, expected: Any) -> bool:
    if file_snapshot is None:
        return False
    try:
        return file_snapshot.payload == (str(expected or "") + "\n").encode("ascii")
    except UnicodeError:
        return False


def _artifact_rows_match_files(
    rows: Any,
    *,
    registry_path: Path | None,
) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    labels: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        label = _safe_artifact_label(row.get("label"))
        if not label or label in labels or not _is_sha256(row.get("sha256")):
            return False
        labels.add(label)
        file_snapshot = _read_regular_file(row.get("path"), registry_path=registry_path)
        if file_snapshot is None:
            return False
        payload = file_snapshot.payload
        expected_size = _as_int(row.get("bytes"))
        if expected_size is None:
            return False
        if expected_size != len(payload) or str(row.get("sha256")) != _sha256(payload):
            return False
    return True


def _artifact_rows_include_file(
    rows: Any,
    target: Any,
    *,
    registry_path: Path | None,
) -> bool:
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict)
        and _same_file_reference(row.get("path"), target, registry_path=registry_path)
        for row in rows
    )


def _normalized_artifact_rows(rows: Any, *, include_path: bool) -> list[dict[str, Any]] | None:
    if not isinstance(rows, list) or not rows:
        return None
    normalized: list[dict[str, Any]] = []
    labels: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        label = _safe_artifact_label(row.get("label"))
        digest = str(row.get("sha256", ""))
        size = _as_int(row.get("bytes"))
        path = row.get("path")
        if (
            not label
            or label in labels
            or not _is_sha256(digest)
            or size is None
            or (include_path and (not isinstance(path, str) or not path))
        ):
            return None
        labels.add(label)
        item: dict[str, Any] = {"label": label}
        if include_path:
            item["path"] = str(path)
        item.update({"sha256": digest, "bytes": size})
        normalized.append(item)
    return normalized


def _zip_metadata_safe(archive: zipfile.ZipFile) -> bool:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_PROJECT_PACKAGE_ENTRIES:
        return False
    total_uncompressed = 0
    for info in infos:
        if info.flag_bits & 0x1:
            return False
        if info.is_dir() or info.file_size < 0 or info.compress_size < 0:
            return False
        if info.file_size > MAX_TECHNICAL_ARTIFACT_BYTES:
            return False
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_PROJECT_PACKAGE_UNCOMPRESSED_BYTES:
            return False
        if info.file_size:
            if info.compress_size == 0:
                return False
            if info.file_size / info.compress_size > MAX_PROJECT_PACKAGE_COMPRESSION_RATIO:
                return False
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            return False
    return True


def _project_workflow_pass(body: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    audit_log = body.get("audit_log")
    approvals = body.get("approvals")
    if not isinstance(audit_log, list) or not audit_log or not isinstance(approvals, list) or not approvals:
        return False
    artifact_labels = {row["label"] for row in rows}
    passing_statuses = {"completed", "passed", "approved", "success"}
    audit_keys = {
        "event_id",
        "actor",
        "action",
        "status",
        "artifact_label",
        "timestamp",
        "note",
    }
    approval_keys = {"gate_id", "approver", "status", "decided_at", "comment"}
    audit_labels: list[str] = []
    for row in audit_log:
        if (
            not isinstance(row, dict)
            or set(row) != audit_keys
            or any(not isinstance(row[key], str) for key in audit_keys)
            or not row["event_id"].strip()
            or not row["action"].strip()
        ):
            return False
        label = _safe_artifact_label(row.get("artifact_label"))
        status = str(row.get("status", "")).strip().casefold()
        if not label or label not in artifact_labels or status not in passing_statuses:
            return False
        audit_labels.append(label)
    return bool(
        set(audit_labels) == artifact_labels
        and all(
            isinstance(row, dict)
            and set(row) == approval_keys
            and all(isinstance(row[key], str) for key in approval_keys)
            and row["gate_id"].strip()
            and str(row.get("status", "")).strip().casefold() == "approved"
            for row in approvals
        )
        and body.get("approval_semantics") == "technical_project_workflow_only"
    )


def _verified_release_projection(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    source = body.get("accelerated_coverage_provenance")
    if not isinstance(source, dict):
        return {}
    projection: dict[str, Any] = {}
    for key in VERIFIED_WORKFLOW_STRING_KEYS:
        value = source.get(key)
        if isinstance(value, str):
            projection[key] = value
    for key in VERIFIED_WORKFLOW_BOOLEAN_KEYS:
        value = source.get(key)
        if isinstance(value, bool):
            projection[key] = value
    for key in VERIFIED_WORKFLOW_COUNT_KEYS:
        value = source.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            projection[key] = value
    return projection


def _verify_project_package(
    project_registry: Any,
    *,
    release_registry: dict[str, Any],
    registry_path: Path | None,
) -> dict[str, bool]:
    checks = {
        "project_registry_document_binding_pass": False,
        "project_registry_body_hash_pass": False,
        "project_registry_signature_pass": False,
        "project_registry_signing_key_binding_pass": False,
        "technical_producer_key_policy_pass": False,
        "project_registry_signature_file_binding_pass": False,
        "project_registry_artifact_files_pass": False,
        "release_project_artifact_bijection_pass": False,
        "release_required_artifact_labels_pass": False,
        "project_registry_workflow_recomputed_pass": False,
        "release_public_key_packaged_pass": False,
        "release_signature_packaged_pass": False,
        "project_package_binding_pass": False,
        "project_package_exact_entries_pass": False,
        "project_package_artifact_hashes_pass": False,
        "repository_license_packaged_pass": False,
        "project_package_rights_status_canonical_pass": False,
        "project_package_authority_fail_closed_pass": False,
    }
    if not isinstance(project_registry, dict):
        return checks

    outer_artifacts = release_registry.get("artifacts")
    outer_artifacts = outer_artifacts if isinstance(outer_artifacts, dict) else {}
    registry_file = _read_regular_file(outer_artifacts.get("project_registry_report"), registry_path=registry_path)
    if registry_file is not None:
        try:
            checks["project_registry_document_binding_pass"] = (
                _strict_json_object(registry_file.payload) == project_registry
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass

    body = project_registry.get("registry_body")
    signature = project_registry.get("signature")
    if not isinstance(body, dict) or not isinstance(signature, dict):
        return checks
    try:
        canonical_body = _canonical_bytes(body, ensure_ascii=False)
    except (TypeError, UnicodeError, ValueError):
        canonical_body = b""
    body_sha256 = _sha256(canonical_body) if canonical_body else ""
    checks["project_registry_body_hash_pass"] = bool(
        body_sha256 and body_sha256 == str(signature.get("canonical_body_sha256", ""))
    )
    project_key_file = _read_regular_file(
        signature.get("public_key_path"), registry_path=registry_path
    )
    checks["project_registry_signature_pass"] = bool(
        canonical_body
        and str(signature.get("algorithm", "")).lower() == "ed25519"
        and _verify_ed25519(
            canonical_body,
            signature_b64=signature.get("signature_b64"),
            public_key_path=signature.get("public_key_path"),
            registry_path=registry_path,
            public_key_snapshot=project_key_file,
        )
    )
    release_signature = release_registry.get("signature")
    release_signature = release_signature if isinstance(release_signature, dict) else {}
    release_key_file = _read_regular_file(
        release_signature.get("public_key_path"), registry_path=registry_path
    )
    checks["technical_producer_key_policy_pass"] = _technical_producer_key_fingerprint_pass(
        release_key_file
    )
    checks["project_registry_signing_key_binding_pass"] = bool(
        project_key_file is not None
        and release_key_file is not None
        and _snapshots_same(project_key_file, release_key_file)
    )
    signature_file = _read_regular_file(signature.get("signature_out"), registry_path=registry_path)
    checks["project_registry_signature_file_binding_pass"] = bool(
        _signature_file_matches(signature_file, signature.get("signature_b64"))
        and _same_file_reference(
            signature.get("signature_out"),
            outer_artifacts.get("project_registry_signature"),
            registry_path=registry_path,
        )
    )
    artifact_rows = body.get("artifact_rows")
    checks["project_registry_artifact_files_pass"] = _artifact_rows_match_files(
        artifact_rows,
        registry_path=registry_path,
    )
    rows = _normalized_artifact_rows(artifact_rows, include_path=True) or []
    release_body = release_registry.get("registry_body")
    release_body = release_body if isinstance(release_body, dict) else {}
    release_rows = _normalized_artifact_rows(release_body.get("artifacts"), include_path=True) or []
    release_labels = {row["label"] for row in release_rows}
    project_rows_by_label = {row["label"]: row for row in rows}
    checks["release_required_artifact_labels_pass"] = bool(
        REQUIRED_RELEASE_ARTIFACT_LABELS.issubset(release_labels)
    )
    expected_project_labels = release_labels | PROJECT_TECHNICAL_ARTIFACT_LABELS
    release_rows_match = bool(
        release_rows
        and set(project_rows_by_label) == expected_project_labels
        and all(project_rows_by_label.get(row["label"]) == row for row in release_rows)
    )
    checks["release_project_artifact_bijection_pass"] = release_rows_match
    checks["project_registry_workflow_recomputed_pass"] = _project_workflow_pass(body, rows)
    release_public_key_row = project_rows_by_label.get("release_registry_public_key", {})
    release_signature_row = project_rows_by_label.get("release_registry_signature", {})
    checks["release_public_key_packaged_pass"] = bool(
        isinstance(release_public_key_row, dict)
        and _same_file_reference(
            release_public_key_row.get("path"),
            release_signature.get("public_key_path"),
            registry_path=registry_path,
        )
    )
    checks["release_signature_packaged_pass"] = bool(
        isinstance(release_signature_row, dict)
        and _same_file_reference(
            release_signature_row.get("path"),
            release_signature.get("signature_out"),
            registry_path=registry_path,
        )
    )

    package_artifact = body.get("package_artifact")
    package_manifest = body.get("package_manifest")
    rights_status = body.get("rights_status")
    if not isinstance(package_artifact, dict) or not isinstance(package_manifest, dict) or not isinstance(rights_status, dict):
        return checks
    package_file = _read_regular_file(package_artifact.get("path"), registry_path=registry_path)
    if package_file is None:
        return checks
    package_bytes = package_file.payload
    package_sha256 = _sha256(package_bytes)
    package_artifact_bytes = _as_int(package_artifact.get("bytes"))
    checks["project_package_binding_pass"] = bool(
        _same_file_reference(
            package_artifact.get("path"),
            outer_artifacts.get("project_package_zip"),
            registry_path=registry_path,
        )
        and package_sha256 == str(package_artifact.get("sha256", ""))
        and package_artifact_bytes is not None
        and len(package_bytes) == package_artifact_bytes
    )

    try:
        expected_names = sorted(
            [
                "LICENSE",
                PACKAGE_RIGHTS_STATUS_NAME,
                "package_manifest.json",
                *[f"artifacts/{row['label']}" for row in rows if isinstance(row, dict)],
            ]
        )
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
            if not _zip_metadata_safe(archive):
                return checks
            names = archive.namelist()
            checks["project_package_exact_entries_pass"] = bool(
                names == expected_names
                and len(names) == len(set(names))
                and archive.read("package_manifest.json") == _canonical_bytes(package_manifest, ensure_ascii=False)
            )
            manifest_rows = package_manifest.get("artifact_rows")
            expected_rows = [
                {
                    "label": str(row["label"]),
                    "path": str(row["path"]),
                    "sha256": str(row["sha256"]),
                    "bytes": int(row["bytes"]),
                }
                for row in rows
            ]
            artifact_hashes_pass = manifest_rows == expected_rows
            for row in expected_rows:
                payload = archive.read(f"artifacts/{row['label']}")
                artifact_hashes_pass = bool(
                    artifact_hashes_pass
                    and len(payload) == row["bytes"]
                    and _sha256(payload) == row["sha256"]
                )
            license_bytes = archive.read("LICENSE")
            rights_status_bytes = archive.read(PACKAGE_RIGHTS_STATUS_NAME)
            legal_rows = package_manifest.get("legal_and_third_party_artifacts")
            expected_legal_rows = [
                {"path": "LICENSE", "sha256": _sha256(license_bytes), "bytes": len(license_bytes)},
                {
                    "path": PACKAGE_RIGHTS_STATUS_NAME,
                    "sha256": _sha256(rights_status_bytes),
                    "bytes": len(rights_status_bytes),
                },
            ]
            artifact_hashes_pass = bool(artifact_hashes_pass and legal_rows == expected_legal_rows)
            checks["project_package_artifact_hashes_pass"] = artifact_hashes_pass
            repository_license = _read_regular_file(
                REPOSITORY_LICENSE_PATH,
                registry_path=None,
            )
            checks["repository_license_packaged_pass"] = bool(
                repository_license is not None
                and license_bytes == repository_license.payload
            )
            packaged_rights_status = _strict_json_object(rights_status_bytes)
            checks["project_package_rights_status_canonical_pass"] = bool(
                _rights_status_shape_valid(rights_status)
                and packaged_rights_status == rights_status
                and rights_status_bytes
                == _canonical_bytes(rights_status, ensure_ascii=False)
            )
    except Exception:  # Fail closed for malformed/encrypted/compression-bomb ZIP inputs.
        return checks

    if not isinstance(packaged_rights_status, dict):
        return checks
    packaged_decision = packaged_rights_status.get("rights_holder_decision")
    packaged_decision = packaged_decision if isinstance(packaged_decision, dict) else {}
    packaged_third_party = packaged_rights_status.get("third_party_review")
    packaged_third_party = packaged_third_party if isinstance(packaged_third_party, dict) else {}
    checks["project_package_authority_fail_closed_pass"] = bool(
        project_registry.get("technical_contract_semantics") == TECHNICAL_CONTRACT_SEMANTICS
        and body.get("technical_contract_semantics") == TECHNICAL_CONTRACT_SEMANTICS
        and project_registry.get("authority") == NO_LEGAL_AUTHORITY
        and body.get("authority") == NO_LEGAL_AUTHORITY
        and package_manifest.get("authority") == NO_LEGAL_AUTHORITY
        and checks["project_package_rights_status_canonical_pass"]
        and packaged_rights_status == rights_status
        and packaged_rights_status.get("authority") == NO_LEGAL_AUTHORITY
        and packaged_decision.get("verified") is False
        and packaged_third_party.get("status") == "not_established"
        and project_registry.get("technical_contract_pass") is True
        and project_registry.get("contract_pass") is True
        and project_registry.get("reason_code") == "PASS"
    )
    return checks


def verify_project_registry_integrity(
    payload: dict[str, Any],
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Verify one project registry from signed bytes and recomputed package state."""

    checks: dict[str, bool] = {
        "project_registry_body_hash_pass": False,
        "project_registry_signature_pass": False,
        "technical_producer_key_policy_pass": False,
        "project_registry_signature_file_binding_pass": False,
        "project_registry_artifact_files_pass": False,
        "project_registry_workflow_recomputed_pass": False,
        "project_package_binding_pass": False,
        "project_package_exact_entries_pass": False,
        "project_package_artifact_hashes_pass": False,
        "repository_license_packaged_pass": False,
        "project_package_rights_status_canonical_pass": False,
        "project_package_authority_fail_closed_pass": False,
    }
    body = payload.get("registry_body") if isinstance(payload, dict) else None
    signature = payload.get("signature") if isinstance(payload, dict) else None
    if not isinstance(body, dict) or not isinstance(signature, dict):
        return {
            "technical_project_registry_integrity_pass": False,
            "checks": checks,
            "blockers": list(checks),
            "verified_projection": {},
            "authority": dict(NO_LEGAL_AUTHORITY),
        }
    try:
        canonical_body = _canonical_bytes(body, ensure_ascii=False)
    except (TypeError, UnicodeError, ValueError):
        canonical_body = b""
    body_sha256 = _sha256(canonical_body) if canonical_body else ""
    checks["project_registry_body_hash_pass"] = bool(
        body_sha256 and body_sha256 == str(signature.get("canonical_body_sha256", ""))
    )
    public_key_file = _read_regular_file(
        signature.get("public_key_path"), registry_path=registry_path
    )
    checks["technical_producer_key_policy_pass"] = _technical_producer_key_fingerprint_pass(
        public_key_file
    )
    checks["project_registry_signature_pass"] = bool(
        canonical_body
        and str(signature.get("algorithm", "")).casefold() == "ed25519"
        and _verify_ed25519(
            canonical_body,
            signature_b64=signature.get("signature_b64"),
            public_key_path=signature.get("public_key_path"),
            registry_path=registry_path,
            public_key_snapshot=public_key_file,
        )
    )
    signature_file = _read_regular_file(
        signature.get("signature_out"), registry_path=registry_path
    )
    checks["project_registry_signature_file_binding_pass"] = _signature_file_matches(
        signature_file, signature.get("signature_b64")
    )

    artifact_rows = body.get("artifact_rows")
    rows = _normalized_artifact_rows(artifact_rows, include_path=True) or []
    checks["project_registry_artifact_files_pass"] = _artifact_rows_match_files(
        artifact_rows, registry_path=registry_path
    )
    checks["project_registry_workflow_recomputed_pass"] = _project_workflow_pass(body, rows)

    package_artifact = body.get("package_artifact")
    package_manifest = body.get("package_manifest")
    rights_status = body.get("rights_status")
    if (
        not isinstance(package_artifact, dict)
        or not isinstance(package_manifest, dict)
        or not isinstance(rights_status, dict)
    ):
        package_file = None
    else:
        package_file = _read_regular_file(
            package_artifact.get("path"), registry_path=registry_path
        )
    if package_file is not None:
        package_bytes = package_file.payload
        package_size = _as_int(package_artifact.get("bytes"))
        checks["project_package_binding_pass"] = bool(
            _sha256(package_bytes) == str(package_artifact.get("sha256", ""))
            and package_size is not None
            and len(package_bytes) == package_size
        )
        try:
            with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
                if not _zip_metadata_safe(archive):
                    raise ValueError("unsafe ZIP metadata")
                names = archive.namelist()
                expected_names = sorted(
                    [
                        "LICENSE",
                        PACKAGE_RIGHTS_STATUS_NAME,
                        "package_manifest.json",
                        *[f"artifacts/{row['label']}" for row in rows],
                    ]
                )
                checks["project_package_exact_entries_pass"] = bool(
                    names == expected_names
                    and len(names) == len(set(names))
                    and archive.read("package_manifest.json")
                    == _canonical_bytes(package_manifest, ensure_ascii=False)
                )
                expected_rows = [
                    {
                        "label": row["label"],
                        "path": row["path"],
                        "sha256": row["sha256"],
                        "bytes": row["bytes"],
                    }
                    for row in rows
                ]
                hashes_pass = package_manifest.get("artifact_rows") == expected_rows
                for row in expected_rows:
                    artifact_bytes = archive.read(f"artifacts/{row['label']}")
                    hashes_pass = bool(
                        hashes_pass
                        and len(artifact_bytes) == row["bytes"]
                        and _sha256(artifact_bytes) == row["sha256"]
                    )
                license_bytes = archive.read("LICENSE")
                rights_status_bytes = archive.read(PACKAGE_RIGHTS_STATUS_NAME)
                expected_legal_rows = [
                    {
                        "path": "LICENSE",
                        "sha256": _sha256(license_bytes),
                        "bytes": len(license_bytes),
                    },
                    {
                        "path": PACKAGE_RIGHTS_STATUS_NAME,
                        "sha256": _sha256(rights_status_bytes),
                        "bytes": len(rights_status_bytes),
                    },
                ]
                hashes_pass = bool(
                    hashes_pass
                    and package_manifest.get("legal_and_third_party_artifacts")
                    == expected_legal_rows
                )
                packaged_rights_status = _strict_json_object(rights_status_bytes)
                checks["project_package_artifact_hashes_pass"] = hashes_pass
                repository_license = _read_regular_file(
                    REPOSITORY_LICENSE_PATH,
                    registry_path=None,
                )
                checks["repository_license_packaged_pass"] = bool(
                    repository_license is not None
                    and license_bytes == repository_license.payload
                )
                checks["project_package_rights_status_canonical_pass"] = bool(
                    _rights_status_shape_valid(rights_status)
                    and packaged_rights_status == rights_status
                    and rights_status_bytes
                    == _canonical_bytes(rights_status, ensure_ascii=False)
                )
                checks["project_package_authority_fail_closed_pass"] = bool(
                    isinstance(packaged_rights_status, dict)
                    and payload.get("technical_contract_semantics")
                    == TECHNICAL_CONTRACT_SEMANTICS
                    and body.get("technical_contract_semantics")
                    == TECHNICAL_CONTRACT_SEMANTICS
                    and payload.get("authority") == NO_LEGAL_AUTHORITY
                    and body.get("authority") == NO_LEGAL_AUTHORITY
                    and package_manifest.get("authority") == NO_LEGAL_AUTHORITY
                    and checks["project_package_rights_status_canonical_pass"]
                    and packaged_rights_status == rights_status
                    and packaged_rights_status.get("authority") == NO_LEGAL_AUTHORITY
                    and isinstance(packaged_rights_status.get("rights_holder_decision"), dict)
                    and packaged_rights_status["rights_holder_decision"].get("verified") is False
                    and isinstance(packaged_rights_status.get("third_party_review"), dict)
                    and packaged_rights_status["third_party_review"].get("status")
                    == "not_established"
                )
        except Exception:  # Fail closed for every malformed ZIP/JSON implementation error.
            pass

    technical_pass = bool(checks and all(checks.values()))
    approvals = body.get("approvals") if isinstance(body.get("approvals"), list) else []
    metadata = body.get("project_metadata") if isinstance(body.get("project_metadata"), dict) else {}
    verified_projection = {
        "project_id": str(body.get("project_id", "")),
        "project_name": str(body.get("project_name", "")),
        "generated_at": str(body.get("generated_at", "")),
        "family_id": str(metadata.get("family_id", "")),
        "portfolio_name": str(metadata.get("portfolio_name", "")),
        "draft_label": str(metadata.get("draft_label", "")),
        "artifact_count": len(rows),
        "audit_event_count": len(body.get("audit_log", []))
        if isinstance(body.get("audit_log"), list)
        else 0,
        "approval_count": len(approvals),
        "approved_count": sum(
            1
            for row in approvals
            if isinstance(row, dict)
            and str(row.get("status", "")).strip().casefold() == "approved"
        ),
        "pending_count": sum(
            1
            for row in approvals
            if not isinstance(row, dict)
            or str(row.get("status", "")).strip().casefold() != "approved"
        ),
        "package_sha256": str(package_artifact.get("sha256", ""))
        if isinstance(package_artifact, dict)
        else "",
        "registry_body_sha256": body_sha256,
    }
    return {
        "schema_version": "technical-project-registry-integrity.v1",
        "technical_project_registry_integrity_pass": technical_pass,
        "checks": checks,
        "blockers": [name for name, passed in checks.items() if not passed],
        "verified_projection": verified_projection if technical_pass else {},
        "authority": dict(NO_LEGAL_AUTHORITY),
    }


def verify_release_registry_integrity(
    payload: dict[str, Any],
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Return fail-closed technical verification details for one release registry."""

    body = payload.get("registry_body") if isinstance(payload, dict) else None
    signature = payload.get("signature") if isinstance(payload, dict) else None
    checks: dict[str, bool] = {
        "registry_contract_claim_pass": bool(
            isinstance(payload, dict)
            and payload.get("technical_contract_pass") is True
            and payload.get("contract_pass") is True
            and payload.get("reason_code") == "PASS"
        ),
        "registry_body_present_pass": isinstance(body, dict),
        "registry_body_hash_pass": False,
        "registry_ed25519_signature_pass": False,
        "technical_producer_key_policy_pass": False,
        "registry_signature_file_binding_pass": False,
        "registry_artifact_hashes_and_sizes_pass": False,
        "release_required_artifact_labels_pass": False,
        "registry_authority_fail_closed_pass": False,
    }
    if not isinstance(body, dict) or not isinstance(signature, dict):
        checks.update(
            _verify_project_package(None, release_registry=payload if isinstance(payload, dict) else {}, registry_path=registry_path)
        )
    else:
        try:
            canonical_body = _canonical_bytes(body, ensure_ascii=True)
        except (TypeError, UnicodeError, ValueError):
            canonical_body = b""
        body_sha256 = _sha256(canonical_body)
        checks["registry_body_hash_pass"] = bool(
            body_sha256 == str(signature.get("canonical_body_sha256", ""))
        )
        public_key_file = _read_regular_file(
            signature.get("public_key_path"), registry_path=registry_path
        )
        checks["technical_producer_key_policy_pass"] = _technical_producer_key_fingerprint_pass(
            public_key_file
        )
        checks["registry_ed25519_signature_pass"] = bool(
            str(signature.get("algorithm", "")).lower() == "ed25519"
            and _verify_ed25519(
                canonical_body,
                signature_b64=signature.get("signature_b64"),
                public_key_path=signature.get("public_key_path"),
                registry_path=registry_path,
                public_key_snapshot=public_key_file,
            )
        )
        signature_file = _read_regular_file(signature.get("signature_out"), registry_path=registry_path)
        checks["registry_signature_file_binding_pass"] = bool(
            _signature_file_matches(signature_file, signature.get("signature_b64"))
        )
        checks["registry_artifact_hashes_and_sizes_pass"] = _artifact_rows_match_files(
            body.get("artifacts"),
            registry_path=registry_path,
        )
        release_rows = _normalized_artifact_rows(body.get("artifacts"), include_path=True) or []
        checks["release_required_artifact_labels_pass"] = REQUIRED_RELEASE_ARTIFACT_LABELS.issubset(
            {row["label"] for row in release_rows}
        )
        checks["registry_authority_fail_closed_pass"] = bool(
            payload.get("technical_contract_semantics") == TECHNICAL_CONTRACT_SEMANTICS
            and body.get("technical_contract_semantics") == TECHNICAL_CONTRACT_SEMANTICS
            and payload.get("authority") == NO_LEGAL_AUTHORITY
            and body.get("authority") == NO_LEGAL_AUTHORITY
        )
        checks.update(
            _verify_project_package(
                payload.get("project_registry_report"),
                release_registry=payload,
                registry_path=registry_path,
            )
        )

    technical_pass = bool(checks and all(checks.values()))
    return {
        "schema_version": "technical-release-registry-integrity.v1",
        "technical_release_registry_integrity_pass": technical_pass,
        "technical_contract_semantics": TECHNICAL_CONTRACT_SEMANTICS,
        "legal_authority_established": False,
        "authority": dict(NO_LEGAL_AUTHORITY),
        "checks": checks,
        "blockers": [name for name, passed in checks.items() if not passed],
        "verified_release_projection": _verified_release_projection(body)
        if technical_pass
        else {},
    }
