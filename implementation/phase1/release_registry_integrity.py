#!/usr/bin/env python3
"""Strict technical-integrity verification for signed release registries.

This verifier authenticates bytes and package bindings only.  It deliberately
does not grant license, commercial-use, redistribution, third-party, or release
authority.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from typing import Any
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


def _canonical_bytes(payload: dict[str, Any], *, ensure_ascii: bool) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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
        or any(ord(character) < 32 for character in label)
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


def _read_regular_file(raw: Any, *, registry_path: Path | None) -> tuple[Path, bytes] | None:
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
            return candidate, bytes(payload)
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
    left_path, left_bytes = left_file
    right_path, right_bytes = right_file
    try:
        return os.path.samefile(left_path, right_path) and left_bytes == right_bytes
    except OSError:
        return False


def _verify_ed25519(
    body_bytes: bytes,
    *,
    signature_b64: Any,
    public_key_path: Any,
    registry_path: Path | None,
) -> bool:
    if not _CRYPTOGRAPHY_AVAILABLE:
        return False
    public_key_file = _read_regular_file(public_key_path, registry_path=registry_path)
    if public_key_file is None:
        return False
    try:
        signature = base64.b64decode(str(signature_b64 or ""), validate=True)
        public_key = serialization.load_pem_public_key(public_key_file[1])
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        public_key.verify(signature, body_bytes)
        return True
    except (ValueError, TypeError, binascii.Error, InvalidSignature, UnsupportedAlgorithm):
        return False


def _signature_file_matches(file_snapshot: tuple[Path, bytes] | None, expected: Any) -> bool:
    if file_snapshot is None:
        return False
    try:
        return file_snapshot[1] == (str(expected or "") + "\n").encode("ascii")
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
        payload = file_snapshot[1]
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
        "project_registry_signature_file_binding_pass": False,
        "project_registry_artifact_files_pass": False,
        "project_registry_workflow_recomputed_pass": False,
        "release_public_key_packaged_pass": False,
        "release_signature_packaged_pass": False,
        "project_package_binding_pass": False,
        "project_package_exact_entries_pass": False,
        "project_package_artifact_hashes_pass": False,
        "project_package_authority_fail_closed_pass": False,
    }
    if not isinstance(project_registry, dict):
        return checks

    outer_artifacts = release_registry.get("artifacts")
    outer_artifacts = outer_artifacts if isinstance(outer_artifacts, dict) else {}
    registry_file = _read_regular_file(outer_artifacts.get("project_registry_report"), registry_path=registry_path)
    if registry_file is not None:
        try:
            checks["project_registry_document_binding_pass"] = json.loads(
                registry_file[1].decode("utf-8")
            ) == project_registry
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    body = project_registry.get("registry_body")
    signature = project_registry.get("signature")
    summary = project_registry.get("summary")
    if not isinstance(body, dict) or not isinstance(signature, dict) or not isinstance(summary, dict):
        return checks
    canonical_body = _canonical_bytes(body, ensure_ascii=False)
    body_sha256 = _sha256(canonical_body)
    checks["project_registry_body_hash_pass"] = bool(
        body_sha256 == str(signature.get("canonical_body_sha256", ""))
        and body_sha256 == str(summary.get("registry_body_sha256", ""))
    )
    checks["project_registry_signature_pass"] = bool(
        str(signature.get("algorithm", "")).lower() == "ed25519"
        and _verify_ed25519(
            canonical_body,
            signature_b64=signature.get("signature_b64"),
            public_key_path=signature.get("public_key_path"),
            registry_path=registry_path,
        )
    )
    release_signature = release_registry.get("signature")
    release_signature = release_signature if isinstance(release_signature, dict) else {}
    checks["project_registry_signing_key_binding_pass"] = _same_file_reference(
        signature.get("public_key_path"),
        release_signature.get("public_key_path"),
        registry_path=registry_path,
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
    rows = artifact_rows if isinstance(artifact_rows, list) else []
    audit_log = body.get("audit_log")
    approvals = body.get("approvals")
    artifact_labels = {
        _safe_artifact_label(row.get("label"))
        for row in rows
        if isinstance(row, dict) and _safe_artifact_label(row.get("label"))
    }
    audit_labels = {
        str(row.get("artifact_label", ""))
        for row in audit_log
        if isinstance(row, dict) and str(row.get("artifact_label", ""))
    } if isinstance(audit_log, list) else set()
    checks["project_registry_workflow_recomputed_pass"] = bool(
        rows
        and isinstance(audit_log, list)
        and audit_log
        and artifact_labels == audit_labels.intersection(artifact_labels)
        and isinstance(approvals, list)
        and approvals
        and all(
            isinstance(row, dict) and str(row.get("status", "")).lower() == "approved"
            for row in approvals
        )
        and body.get("approval_semantics") == "technical_project_workflow_only"
    )
    checks["release_public_key_packaged_pass"] = _artifact_rows_include_file(
        artifact_rows,
        release_signature.get("public_key_path"),
        registry_path=registry_path,
    )
    checks["release_signature_packaged_pass"] = _artifact_rows_include_file(
        artifact_rows,
        release_signature.get("signature_out"),
        registry_path=registry_path,
    )

    package_artifact = body.get("package_artifact")
    package_manifest = body.get("package_manifest")
    rights_status = body.get("rights_status")
    if not isinstance(package_artifact, dict) or not isinstance(package_manifest, dict) or not isinstance(rights_status, dict):
        return checks
    package_file = _read_regular_file(package_artifact.get("path"), registry_path=registry_path)
    if package_file is None:
        return checks
    package_bytes = package_file[1]
    package_sha256 = _sha256(package_bytes)
    release_summary = release_registry.get("summary")
    release_summary = release_summary if isinstance(release_summary, dict) else {}
    package_artifact_bytes = _as_int(package_artifact.get("bytes"))
    summary_package_bytes = _as_int(summary.get("package_bytes"))
    release_summary_package_bytes = _as_int(release_summary.get("project_registry_package_bytes"))
    checks["project_package_binding_pass"] = bool(
        _same_file_reference(
            package_artifact.get("path"),
            outer_artifacts.get("project_package_zip"),
            registry_path=registry_path,
        )
        and package_sha256 == str(package_artifact.get("sha256", ""))
        and package_artifact_bytes is not None
        and len(package_bytes) == package_artifact_bytes
        and package_sha256 == str(summary.get("package_sha256", ""))
        and summary_package_bytes is not None
        and len(package_bytes) == summary_package_bytes
        and package_sha256 == str(release_summary.get("project_registry_package_sha256", ""))
        and release_summary_package_bytes is not None
        and len(package_bytes) == release_summary_package_bytes
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
            packaged_rights_status = json.loads(rights_status_bytes.decode("utf-8"))
    except Exception:  # Fail closed for malformed/encrypted/compression-bomb ZIP inputs.
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
        and rights_status.get("authority") == NO_LEGAL_AUTHORITY
        and packaged_rights_status == rights_status
        and packaged_rights_status.get("authority") == NO_LEGAL_AUTHORITY
        and packaged_decision.get("verified") is False
        and packaged_third_party.get("status") == "not_established"
        and project_registry.get("technical_contract_pass") is True
        and project_registry.get("contract_pass") is True
        and project_registry.get("reason_code") == "PASS"
    )
    return checks


def verify_release_registry_integrity(
    payload: dict[str, Any],
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Return fail-closed technical verification details for one release registry."""

    body = payload.get("registry_body") if isinstance(payload, dict) else None
    signature = payload.get("signature") if isinstance(payload, dict) else None
    summary = payload.get("summary") if isinstance(payload, dict) else None
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
        "registry_signature_file_binding_pass": False,
        "registry_artifact_hashes_and_sizes_pass": False,
        "registry_authority_fail_closed_pass": False,
    }
    if not isinstance(body, dict) or not isinstance(signature, dict) or not isinstance(summary, dict):
        checks.update(
            _verify_project_package(None, release_registry=payload if isinstance(payload, dict) else {}, registry_path=registry_path)
        )
    else:
        canonical_body = _canonical_bytes(body, ensure_ascii=True)
        body_sha256 = _sha256(canonical_body)
        checks["registry_body_hash_pass"] = bool(
            body_sha256 == str(signature.get("canonical_body_sha256", ""))
            and body_sha256 == str(summary.get("registry_body_sha256", ""))
        )
        checks["registry_ed25519_signature_pass"] = bool(
            str(signature.get("algorithm", "")).lower() == "ed25519"
            and str(summary.get("signing_algorithm", "")).lower() == "ed25519"
            and _verify_ed25519(
                canonical_body,
                signature_b64=signature.get("signature_b64"),
                public_key_path=signature.get("public_key_path"),
                registry_path=registry_path,
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
    }
