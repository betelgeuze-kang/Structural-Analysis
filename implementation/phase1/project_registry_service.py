#!/usr/bin/env python3
"""Project registry service scaffold for signed packages, audit logs, and approvals."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import zipfile

try:
    from implementation.phase1.project_registry_portfolio_scanner import (
        DEFAULT_REGISTRY_FILENAMES,
        discover_project_registry_paths,
    )
except ImportError:  # pragma: no cover
    from project_registry_portfolio_scanner import DEFAULT_REGISTRY_FILENAMES, discover_project_registry_paths  # type: ignore


REASONS = {
    "PASS": "signed project registry package generated",
    "ERR_INPUT": "invalid project registry inputs",
    "ERR_PACKAGE": "project package creation failed",
    "ERR_AUDIT": "audit log or approval workflow was incomplete",
    "ERR_SIGNATURE": "project registry signing or verification failed",
}


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _openssl(args: list[str]) -> None:
    proc = subprocess.run(args, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "openssl failed").strip())


def _ensure_keypair(private_key: Path, public_key: Path) -> bool:
    generated = False
    if not private_key.exists():
        private_key.parent.mkdir(parents=True, exist_ok=True)
        _openssl(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)])
        generated = True
    if generated or not public_key.exists():
        public_key.parent.mkdir(parents=True, exist_ok=True)
        _openssl(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)])
    return generated


def _sign_payload(payload: dict[str, Any], *, private_key: Path) -> str:
    with tempfile.NamedTemporaryFile(delete=False) as payload_file:
        payload_file.write(_canonical_bytes(payload))
        payload_path = Path(payload_file.name)
    signature_path = payload_path.with_suffix(".sig")
    try:
        _openssl(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ]
        )
        return base64.b64encode(signature_path.read_bytes()).decode("ascii")
    finally:
        payload_path.unlink(missing_ok=True)
        signature_path.unlink(missing_ok=True)


def _verify_signature(payload: dict[str, Any], *, signature_b64: str, public_key: Path) -> bool:
    with tempfile.NamedTemporaryFile(delete=False) as payload_file:
        payload_file.write(_canonical_bytes(payload))
        payload_path = Path(payload_file.name)
    signature_path = payload_path.with_suffix(".sig")
    try:
        signature_path.write_bytes(base64.b64decode(signature_b64.encode("ascii")))
        proc = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_key),
                "-sigfile",
                str(signature_path),
                "-rawin",
                "-in",
                str(payload_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    finally:
        payload_path.unlink(missing_ok=True)
        signature_path.unlink(missing_ok=True)


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _stringify_scalar(value: Any) -> str:
    return str(value or "").strip()


def _sort_registry_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (str(row["project_id"]), str(row["path"])))


def _build_project_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["project_id"]), []).append(row)

    project_rows: list[dict[str, Any]] = []
    for project_id in sorted(grouped):
        project_group = list(grouped[project_id])
        latest_row = max(
            project_group,
            key=lambda row: (
                str(row.get("generated_at", "")),
                str(row.get("path", "")),
            ),
        )
        project_rows.append(
            {
                "project_id": project_id,
                "project_name": str(latest_row["project_name"]),
                "registry_count": len(project_group),
                "all_contract_pass": all(bool(row["contract_pass"]) for row in project_group),
                "any_contract_pass": any(bool(row["contract_pass"]) for row in project_group),
                "latest_generated_at": str(latest_row["generated_at"]),
                "latest_path": str(latest_row["path"]),
                "latest_reason_code": str(latest_row["reason_code"]),
                "latest_signature_verified": bool(latest_row["signature_verified"]),
                "latest_package_reproducible": bool(latest_row["package_reproducible"]),
                "latest_approval_count": _coerce_int(latest_row["approval_count"]),
                "latest_approved_count": _coerce_int(latest_row["approved_count"]),
                "latest_pending_count": _coerce_int(latest_row["pending_count"]),
                "latest_audit_event_count": _coerce_int(latest_row["audit_event_count"]),
                "latest_artifact_count": _coerce_int(latest_row["artifact_count"]),
                "latest_package_sha256": str(latest_row["package_sha256"]),
                "latest_family_id": str(latest_row.get("family_id", "")),
                "latest_portfolio_name": str(latest_row.get("portfolio_name", "")),
                "latest_draft_label": str(latest_row.get("draft_label", "")),
                "registry_paths": [str(row["path"]) for row in _sort_registry_rows(project_group)],
            }
        )
    return project_rows


def _build_family_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        family_id = _stringify_scalar(row.get("family_id", ""))
        if not family_id:
            continue
        portfolio_name = _stringify_scalar(row.get("portfolio_name", ""))
        grouped.setdefault((portfolio_name, family_id), []).append(row)

    family_rows: list[dict[str, Any]] = []
    for portfolio_name, family_id in sorted(grouped):
        family_group = list(grouped[(portfolio_name, family_id)])
        latest_row = max(
            family_group,
            key=lambda row: (
                str(row.get("generated_at", "")),
                str(row.get("path", "")),
            ),
        )
        family_rows.append(
            {
                "portfolio_name": portfolio_name,
                "family_id": family_id,
                "draft_labels": sorted(
                    {
                        _stringify_scalar(row.get("draft_label", ""))
                        for row in family_group
                        if _stringify_scalar(row.get("draft_label", ""))
                    }
                ),
                "project_ids": sorted({_stringify_scalar(row.get("project_id", "")) for row in family_group}),
                "registry_count": len(family_group),
                "complete_registry_count": sum(1 for row in family_group if bool(row.get("contract_pass", False))),
                "signature_verified_count": sum(1 for row in family_group if bool(row.get("signature_verified", False))),
                "package_reproducible_count": sum(1 for row in family_group if bool(row.get("package_reproducible", False))),
                "latest_generated_at": str(latest_row.get("generated_at", "")),
                "latest_path": str(latest_row.get("path", "")),
                "latest_project_id": str(latest_row.get("project_id", "")),
                "latest_project_name": str(latest_row.get("project_name", "")),
            }
        )
    return family_rows


def _normalize_artifact_labels(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    used_labels: set[str] = set()
    for index, path in enumerate(paths, start=1):
        label = path.name or f"artifact_{index}"
        if label in used_labels:
            stem = path.stem or f"artifact_{index}"
            label = f"{stem}_{index}{path.suffix}"
        used_labels.add(label)
        rows.append(
            {
                "label": label,
                "path": str(path),
                "sha256": _sha256_file(path),
                "bytes": int(path.stat().st_size),
            }
        )
    return rows


def _extract_rows(payload: dict[str, Any] | list[Any] | None, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_audit_rows(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    rows = _extract_rows(payload, ("audit_log", "events", "audit_review_queue_items", "audit_review_followup_rows"))
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        normalized.append(
            {
                "event_id": str(row.get("event_id", f"audit-{index:04d}")),
                "actor": str(row.get("actor", row.get("owner", row.get("assignee", "")))),
                "action": str(row.get("action", row.get("current_status", row.get("status", "")))),
                "status": str(row.get("status", row.get("current_status", ""))),
                "artifact_label": str(row.get("artifact_label", row.get("artifact", row.get("file", "")))),
                "timestamp": str(row.get("timestamp", row.get("updated_at", row.get("created_at", "")))),
                "note": str(row.get("note", row.get("comment", ""))),
            }
        )
    return normalized


def _normalize_approval_rows(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    rows = _extract_rows(payload, ("approvals", "approval_rows", "rows"))
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        normalized.append(
            {
                "gate_id": str(row.get("gate_id", row.get("packet_id", f"approval-{index:04d}"))),
                "approver": str(row.get("approver", row.get("review_owner", row.get("owner", "")))),
                "status": str(row.get("status", row.get("decision", ""))),
                "decided_at": str(row.get("decided_at", row.get("updated_at", row.get("timestamp", "")))),
                "comment": str(row.get("comment", row.get("note", ""))),
            }
        )
    return normalized


def _build_package_manifest(
    *,
    project_id: str,
    project_name: str,
    artifact_rows: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "project_name": project_name,
        "generated_at": generated_at,
        "artifact_rows": [
            {
                "label": str(row["label"]),
                "sha256": str(row["sha256"]),
                "bytes": int(row["bytes"]),
            }
            for row in artifact_rows
        ],
    }


def _build_package_bytes(package_manifest: dict[str, Any], artifact_rows: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as zf:
        entries: list[tuple[str, bytes]] = [("package_manifest.json", _canonical_bytes(package_manifest))]
        for row in artifact_rows:
            artifact_path = Path(str(row["path"]))
            entries.append((f"artifacts/{row['label']}", artifact_path.read_bytes()))
        for name, payload in sorted(entries, key=lambda item: item[0]):
            info = zipfile.ZipInfo(filename=name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            zf.writestr(info, payload)
    return buffer.getvalue()


def build_project_registry(
    *,
    project_id: str,
    project_name: str,
    artifact_paths: list[Path],
    audit_payload: dict[str, Any] | list[Any] | None,
    approval_payload: dict[str, Any] | list[Any] | None,
    project_metadata: dict[str, Any] | None = None,
    private_key_out: Path,
    public_key_out: Path,
    signature_out: Path,
    package_out: Path,
    out: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    artifact_rows = _normalize_artifact_labels(artifact_paths)
    audit_rows = _normalize_audit_rows(audit_payload)
    approval_rows = _normalize_approval_rows(approval_payload)
    package_manifest = _build_package_manifest(
        project_id=project_id,
        project_name=project_name,
        artifact_rows=artifact_rows,
        generated_at=timestamp,
    )
    package_bytes = _build_package_bytes(package_manifest, artifact_rows)
    package_rebuilt_bytes = _build_package_bytes(package_manifest, artifact_rows)
    package_out.parent.mkdir(parents=True, exist_ok=True)
    package_out.write_bytes(package_bytes)
    package_sha256 = _sha256_bytes(package_bytes)
    artifact_labels = {str(row["label"]) for row in artifact_rows}
    audit_labels = {str(row["artifact_label"]) for row in audit_rows if str(row.get("artifact_label", "")).strip()}
    referenced_artifact_count = len(artifact_labels & audit_labels)
    approved_count = sum(1 for row in approval_rows if str(row.get("status", "")).lower() == "approved")
    pending_count = sum(1 for row in approval_rows if str(row.get("status", "")).lower() != "approved")
    metadata = dict(project_metadata or {})

    registry_body = {
        "project_id": project_id,
        "project_name": project_name,
        "project_metadata": metadata,
        "package_manifest": package_manifest,
        "package_artifact": {
            "path": str(package_out),
            "sha256": package_sha256,
            "bytes": int(len(package_bytes)),
        },
        "artifact_rows": artifact_rows,
        "audit_log": audit_rows,
        "approvals": approval_rows,
    }
    canonical_body_sha256 = _sha256_bytes(_canonical_bytes(registry_body))

    key_generated_this_run = _ensure_keypair(private_key_out, public_key_out)
    signature_b64 = _sign_payload(registry_body, private_key=private_key_out)
    signature_out.parent.mkdir(parents=True, exist_ok=True)
    signature_out.write_text(signature_b64 + "\n", encoding="utf-8")
    signature_verified = _verify_signature(registry_body, signature_b64=signature_b64, public_key=public_key_out)

    checks = {
        "artifact_hashes_present_pass": all(bool(str(row.get("sha256", "")).strip()) for row in artifact_rows),
        "package_written_pass": package_out.exists(),
        "package_reproducible_pass": package_bytes == package_rebuilt_bytes,
        "audit_log_present_pass": len(audit_rows) > 0,
        "audit_trail_complete_pass": len(audit_rows) > 0 and referenced_artifact_count == len(artifact_rows),
        "approval_workflow_present_pass": len(approval_rows) > 0,
        "approval_complete_pass": len(approval_rows) > 0 and pending_count == 0,
        "signature_generated_pass": bool(signature_b64),
        "signature_verified_pass": bool(signature_verified),
    }
    reason_code = "PASS"
    if not artifact_rows:
        reason_code = "ERR_INPUT"
    elif not checks["package_written_pass"] or not checks["package_reproducible_pass"]:
        reason_code = "ERR_PACKAGE"
    elif not checks["audit_trail_complete_pass"] or not checks["approval_complete_pass"]:
        reason_code = "ERR_AUDIT"
    elif not checks["signature_generated_pass"] or not checks["signature_verified_pass"]:
        reason_code = "ERR_SIGNATURE"
    contract_pass = bool(reason_code == "PASS" and all(checks.values()))

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-project-registry-service",
        "generated_at": timestamp,
        "inputs": {
            "project_id": project_id,
            "project_name": project_name,
            "artifact_paths": [str(path) for path in artifact_paths],
            "project_metadata": metadata,
            "private_key_out": str(private_key_out),
            "public_key_out": str(public_key_out),
            "signature_out": str(signature_out),
            "package_out": str(package_out),
            "out": str(out),
        },
        "checks": checks,
        "summary": {
            "project_id": project_id,
            "project_name": project_name,
            "project_family_id": str(metadata.get("family_id", "")),
            "portfolio_name": str(metadata.get("portfolio_name", "")),
            "draft_label": str(metadata.get("draft_label", "")),
            "artifact_count": len(artifact_rows),
            "audit_event_count": len(audit_rows),
            "approval_count": len(approval_rows),
            "approved_count": approved_count,
            "pending_count": pending_count,
            "referenced_artifact_count": referenced_artifact_count,
            "package_sha256": package_sha256,
            "package_bytes": int(len(package_bytes)),
            "registry_body_sha256": canonical_body_sha256,
            "signing_algorithm": "ed25519",
            "key_generated_this_run": bool(key_generated_this_run),
        },
        "metadata": metadata,
        "registry_body": registry_body,
        "signature": {
            "algorithm": "ed25519",
            "public_key_path": str(public_key_out),
            "signature_out": str(signature_out),
            "signature_b64": signature_b64,
            "canonical_body_sha256": canonical_body_sha256,
        },
        "artifacts": {
            "project_package_zip": str(package_out),
            "project_registry_json": str(out),
            "project_signature_b64": str(signature_out),
        },
        "summary_line": (
            "Project registry service: "
            f"{reason_code} | artifacts={len(artifact_rows)} | "
            f"audit={len(audit_rows)} | approvals={approved_count}/{len(approval_rows)} | "
            f"package_repro={checks['package_reproducible_pass']} | "
            f"signature_verified={checks['signature_verified_pass']}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_project_registry_index(
    *,
    registry_paths: list[Path | str] | None = None,
    registry_dirs: list[Path | str] | None = None,
    registry_globs: list[str] | None = None,
    workspace_out: Path | None = None,
    out: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    discovery = discover_project_registry_paths(
        registry_paths=registry_paths,
        registry_dirs=registry_dirs,
        registry_globs=registry_globs,
        filename_patterns=DEFAULT_REGISTRY_FILENAMES,
    )
    resolved_registry_paths = discovery["registry_paths"]
    source_details_by_key = discovery["source_details_by_key"]
    rows: list[dict[str, Any]] = []
    invalid_registry_count = 0
    for path in resolved_registry_paths:
        source_detail = source_details_by_key.get(str(path.resolve(strict=False)), {})
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            invalid_registry_count += 1
            rows.append(
                {
                    "project_id": path.stem,
                    "project_name": path.stem,
                    "path": str(path),
                    "generated_at": "",
                    "contract_pass": False,
                    "reason_code": "ERR_INPUT",
                    "reason": f"registry payload could not be read: {exc}",
                    "signature_verified": False,
                    "package_reproducible": False,
                    "approval_count": 0,
                    "approved_count": 0,
                    "pending_count": 0,
                    "approval_complete": False,
                    "audit_event_count": 0,
                    "artifact_count": 0,
                    "package_sha256": "",
                    "registry_body_sha256": "",
                    "failed_checks": ["registry_payload_readable_pass"],
                    "source_kinds": list(source_detail.get("source_kinds", [])),
                    "source_specs": list(source_detail.get("source_specs", [])),
                }
            )
            continue
        if not isinstance(payload, dict):
            invalid_registry_count += 1
            rows.append(
                {
                    "project_id": path.stem,
                    "project_name": path.stem,
                    "path": str(path),
                    "generated_at": "",
                    "contract_pass": False,
                    "reason_code": "ERR_INPUT",
                    "reason": "registry payload must be a JSON object",
                    "signature_verified": False,
                    "package_reproducible": False,
                    "approval_count": 0,
                    "approved_count": 0,
                    "pending_count": 0,
                    "approval_complete": False,
                    "audit_event_count": 0,
                    "artifact_count": 0,
                    "package_sha256": "",
                    "registry_body_sha256": "",
                    "failed_checks": ["registry_payload_object_pass"],
                    "source_kinds": list(source_detail.get("source_kinds", [])),
                    "source_specs": list(source_detail.get("source_specs", [])),
                }
            )
            continue
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        approval_count = _coerce_int(summary.get("approval_count", 0))
        approved_count = _coerce_int(summary.get("approved_count", 0))
        pending_count = _coerce_int(summary.get("pending_count", max(approval_count - approved_count, 0)))
        project_id = _stringify_scalar(summary.get("project_id", payload.get("project_id", ""))) or path.stem
        project_name = _stringify_scalar(summary.get("project_name", payload.get("project_name", ""))) or project_id
        family_id = _stringify_scalar(summary.get("project_family_id", metadata.get("family_id", "")))
        portfolio_name = _stringify_scalar(summary.get("portfolio_name", metadata.get("portfolio_name", "")))
        draft_label = _stringify_scalar(summary.get("draft_label", metadata.get("draft_label", "")))
        rows.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "path": str(path),
                "generated_at": _stringify_scalar(payload.get("generated_at", "")),
                "contract_pass": bool(payload.get("contract_pass", False)),
                "reason_code": _stringify_scalar(payload.get("reason_code", "")),
                "reason": _stringify_scalar(payload.get("reason", "")),
                "signature_verified": bool(checks.get("signature_verified_pass", False)),
                "package_reproducible": bool(checks.get("package_reproducible_pass", False)),
                "approval_count": approval_count,
                "approved_count": approved_count,
                "pending_count": pending_count,
                "approval_complete": approval_count > 0 and pending_count == 0,
                "audit_event_count": _coerce_int(summary.get("audit_event_count", 0)),
                "artifact_count": _coerce_int(summary.get("artifact_count", 0)),
                "package_sha256": _stringify_scalar(summary.get("package_sha256", "")),
                "registry_body_sha256": _stringify_scalar(summary.get("registry_body_sha256", "")),
                "family_id": family_id,
                "portfolio_name": portfolio_name,
                "draft_label": draft_label,
                "failed_checks": [
                    str(name)
                    for name, passed in sorted(checks.items())
                    if not bool(passed)
                ],
                "source_kinds": list(source_detail.get("source_kinds", [])),
                "source_specs": list(source_detail.get("source_specs", [])),
            }
        )
    rows = _sort_registry_rows(rows)
    project_rows = _build_project_rollups(rows)
    family_rows = _build_family_rollups(rows)
    complete_count = sum(1 for row in rows if row["contract_pass"])
    signature_verified_count = sum(1 for row in rows if row["signature_verified"])
    reproducible_count = sum(1 for row in rows if row["package_reproducible"])
    approval_complete_count = sum(1 for row in rows if row["approval_complete"])
    unique_project_count = len(project_rows)
    family_count = len(family_rows)
    portfolio_count = len({str(row.get("portfolio_name", "")) for row in family_rows if str(row.get("portfolio_name", "")).strip()})
    multi_registry_project_count = sum(1 for row in project_rows if row["registry_count"] > 1)
    total_approval_count = sum(_coerce_int(row["approval_count"]) for row in rows)
    total_approved_count = sum(_coerce_int(row["approved_count"]) for row in rows)
    total_audit_event_count = sum(_coerce_int(row["audit_event_count"]) for row in rows)
    latest_generated_at = max((str(row["generated_at"]) for row in rows if str(row["generated_at"]).strip()), default="")
    contract_pass = bool(len(rows) > 0 and complete_count == len(rows))
    reason_code = "PASS" if contract_pass else ("CHECK" if rows else "ERR_INPUT")
    workspace_path = str(workspace_out) if workspace_out is not None else ""
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-project-registry-index",
        "generated_at": timestamp,
        "inputs": {
            "registry_paths": [str(path) for path in (registry_paths or [])],
            "registry_dirs": [str(path) for path in (registry_dirs or [])],
            "registry_globs": list(registry_globs or []),
        },
        "scan": discovery["scan"],
        "summary": {
            "project_count": int(len(rows)),
            "complete_project_count": int(complete_count),
            "signature_verified_count": int(signature_verified_count),
            "package_reproducible_count": int(reproducible_count),
            "approval_complete_count": int(approval_complete_count),
            "unique_project_count": int(unique_project_count),
            "family_count": int(family_count),
            "portfolio_count": int(portfolio_count),
            "multi_registry_project_count": int(multi_registry_project_count),
            "invalid_registry_count": int(invalid_registry_count),
            "total_approval_count": int(total_approval_count),
            "total_approved_count": int(total_approved_count),
            "total_audit_event_count": int(total_audit_event_count),
            "latest_registry_generated_at": latest_generated_at,
        },
        "rows": rows,
        "project_rows": project_rows,
        "family_rows": family_rows,
        "artifacts": {
            "project_registry_index_json": str(out) if out is not None else "",
            "project_registry_portfolio_workspace_json": workspace_path,
        },
        "summary_line": (
            "Project registry index: "
            f"{reason_code} | projects={len(rows)} | unique={unique_project_count} | families={family_count} | "
            f"complete={complete_count} | signature={signature_verified_count} | repro={reproducible_count}"
        ),
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": "project registry portfolio index generated" if rows else REASONS["ERR_INPUT"],
    }
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if workspace_out is not None:
        workspace_payload = {
            "schema_version": "1.0",
            "run_id": "phase1-project-registry-portfolio-workspace",
            "generated_at": timestamp,
            "summary": payload["summary"],
            "scan": payload["scan"],
            "project_rows": project_rows,
            "family_rows": family_rows,
            "registry_rows": rows,
            "artifacts": payload["artifacts"],
            "summary_line": payload["summary_line"].replace(
                "Project registry index",
                "Project registry portfolio workspace",
            ),
            "contract_pass": payload["contract_pass"],
            "reason_code": payload["reason_code"],
            "reason": payload["reason"],
        }
        workspace_out.parent.mkdir(parents=True, exist_ok=True)
        workspace_out.write_text(json.dumps(workspace_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--artifact-paths", required=True, help="Comma-separated artifact files")
    parser.add_argument("--audit-log-json", required=True)
    parser.add_argument("--approval-json", required=True)
    parser.add_argument("--private-key-out", required=True)
    parser.add_argument("--public-key-out", required=True)
    parser.add_argument("--signature-out", required=True)
    parser.add_argument("--package-out", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    artifact_paths = [Path(item) for item in _parse_csv(args.artifact_paths)]
    if not artifact_paths or any(not path.exists() for path in artifact_paths):
        raise SystemExit("artifact paths were missing or invalid")
    audit_payload = _load_json(Path(args.audit_log_json))
    approval_payload = _load_json(Path(args.approval_json))
    payload = build_project_registry(
        project_id=str(args.project_id),
        project_name=str(args.project_name),
        artifact_paths=artifact_paths,
        audit_payload=audit_payload,
        approval_payload=approval_payload,
        private_key_out=Path(args.private_key_out),
        public_key_out=Path(args.public_key_out),
        signature_out=Path(args.signature_out),
        package_out=Path(args.package_out),
        out=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
