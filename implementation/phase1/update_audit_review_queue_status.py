#!/usr/bin/env python3
"""Update audit review queue item status and rebuild queue summary artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

from implementation.phase1.generate_audit_review_followup_manifest import build_followup_manifest
from implementation.phase1.generate_audit_review_resolution_manifest import (
    build_resolution_manifest,
    write_resolution_files,
)


ROOT = Path("implementation/phase1")
RELEASE_DIR = ROOT / "release"
DEFAULT_QUEUE_MANIFEST = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json")
DEFAULT_EXPORT_REPORT = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.export_report.json")
DEFAULT_OUT_REPORT = Path("implementation/phase1/audit_review_queue_update_report.json")
DEFAULT_FOLLOWUP_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_followup_manifest.json"
)
DEFAULT_RESOLUTION_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_resolution_manifest.json"
)
DEFAULT_RESOLUTION_DIR = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_resolution_files"
)
DEFAULT_RELEASE_GAP_JSON = RELEASE_DIR / "release_gap_report.json"
DEFAULT_RELEASE_GAP_MD = RELEASE_DIR / "release_gap_report.md"
DEFAULT_RELEASE_REGISTRY = RELEASE_DIR / "release_registry.json"
DEFAULT_RELEASE_PRIVATE_KEY = RELEASE_DIR / "signing" / "release_registry_ed25519.pem"
DEFAULT_RELEASE_PUBLIC_KEY = RELEASE_DIR / "signing" / "release_registry_ed25519.pub.pem"
DEFAULT_RELEASE_SIGNATURE = RELEASE_DIR / "signing" / "release_registry.signature.b64"
DEFAULT_COMMITTEE_OUT_DIR = RELEASE_DIR / "committee_review"
DEFAULT_EXTERNAL_LATEST = RELEASE_DIR / "external_validation_latest.json"
DEFAULT_EXTERNAL_LIGHT_LATEST = RELEASE_DIR / "external_validation_light_latest.json"
REQUIRED_BATCH_ATTESTATION_FIELDS = (
    "reviewer_name",
    "reviewer_license_id",
    "decision_basis",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_step(step: str, cmd: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "step": step,
            "command": shlex.join(cmd),
            "return_code": 0,
            "ok": True,
            "status": "dry_run",
            "stdout_tail": "",
            "stderr_tail": "",
        }
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return {
        "step": step,
        "command": shlex.join(cmd),
        "return_code": int(proc.returncode),
        "ok": bool(proc.returncode == 0),
        "status": "ok" if proc.returncode == 0 else "failed",
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _append_step(rows: list[dict[str, Any]], step: str, cmd: list[str], *, dry_run: bool = False) -> bool:
    row = _run_step(step, cmd, dry_run=dry_run)
    rows.append(row)
    return bool(row["ok"])


def _normalize_attestation(payload: Any) -> dict[str, Any]:
    attestation = payload if isinstance(payload, dict) else {}
    return {
        "reviewer_name": str(attestation.get("reviewer_name", "") or "").strip(),
        "reviewer_license_id": str(attestation.get("reviewer_license_id", "") or "").strip(),
        "decision_basis": str(attestation.get("decision_basis", "") or "").strip(),
        "review_session_id": str(attestation.get("review_session_id", "") or "").strip(),
        "attested_at_utc": str(attestation.get("attested_at_utc", "") or "").strip(),
        "apply_live_acknowledged": bool(attestation.get("apply_live_acknowledged", False)),
    }


def _missing_attestation_fields(attestation: dict[str, Any]) -> list[str]:
    missing = [field for field in REQUIRED_BATCH_ATTESTATION_FIELDS if not str(attestation.get(field, "") or "").strip()]
    if not bool(attestation.get("apply_live_acknowledged", False)):
        missing.append("apply_live_acknowledged")
    return missing


def _status_acknowledged(queue_status: str) -> bool:
    return queue_status in {"acknowledged", "approved", "rejected"}


def _default_resolution(queue_status: str) -> str:
    if queue_status == "approved":
        return "approved"
    if queue_status == "rejected":
        return "rejected"
    return ""


def _resolve_queue_status_dir(manifest_path: Path, manifest_payload: dict[str, Any], explicit: str) -> Path:
    if explicit.strip():
        return Path(explicit)
    queue_dir = str(manifest_payload.get("audit_review_queue_status_directory", "")).strip()
    if queue_dir:
        return Path(queue_dir)
    return manifest_path.with_suffix(".audit_review_queue_status_files")


def _resolve_target_status_file(manifest_payload: dict[str, Any], packet_id: str, explicit: str) -> Path:
    if explicit.strip():
        return Path(explicit)
    if not packet_id.strip():
        raise SystemExit("Provide --packet-id or --status-file.")
    items = manifest_payload.get("audit_review_queue_items")
    if not isinstance(items, list):
        raise SystemExit("Queue manifest has no audit_review_queue_items list.")
    matches = [row for row in items if str(row.get("packet_id", "")).strip() == packet_id.strip()]
    if not matches:
        raise SystemExit(f"Queue packet_id not found: {packet_id}")
    if len(matches) > 1:
        raise SystemExit(f"Queue packet_id is ambiguous: {packet_id}")
    path = str(matches[0].get("path", "")).strip()
    if not path:
        raise SystemExit(f"Queue packet_id has no status path: {packet_id}")
    return Path(path)


def _refresh_queue_manifest(manifest_path: Path, queue_status_dir: Path) -> dict[str, Any]:
    status_files = sorted(queue_status_dir.glob("*.review_status.json")) if queue_status_dir.exists() else []
    queue_items: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    action_family_counts: Counter[str] = Counter()
    pending_count = 0
    acknowledged_count = 0
    approved_count = 0
    rejected_count = 0

    for status_path in status_files:
        payload = _load_json(status_path)
        queue_status = str(payload.get("queue_status", "") or "")
        action_family = str(payload.get("action_family", "") or "")
        acknowledged = bool(payload.get("acknowledged", False))
        queue_items.append(
            {
                "packet_id": str(payload.get("packet_id", "") or ""),
                "action_family": action_family,
                "followup_type": str(payload.get("followup_type", "") or ""),
                "review_priority": str(payload.get("review_priority", "") or ""),
                "review_owner": str(payload.get("review_owner", "") or ""),
                "queue_status": queue_status,
                "acknowledged": acknowledged,
                "resolution": str(payload.get("resolution", "") or ""),
                "created_at_utc": str(payload.get("created_at_utc", "") or ""),
                "last_transition_at_utc": str(payload.get("last_transition_at_utc", "") or ""),
                "path": str(status_path),
                "packet_file_path": str(payload.get("packet_file_path", "") or ""),
                "change_count": int(payload.get("change_count", 0) or 0),
                "row_count": int(payload.get("row_count", 0) or 0),
            }
        )
        if queue_status:
            status_counts[queue_status] += 1
        if action_family:
            action_family_counts[action_family] += 1
        if queue_status == "pending_review":
            pending_count += 1
        if acknowledged:
            acknowledged_count += 1
        if queue_status == "approved":
            approved_count += 1
        if queue_status == "rejected":
            rejected_count += 1

    summary = {
        "audit_review_queue_item_count": len(queue_items),
        "audit_review_queue_pending_count": int(pending_count),
        "audit_review_queue_acknowledged_count": int(acknowledged_count),
        "audit_review_queue_approved_count": int(approved_count),
        "audit_review_queue_rejected_count": int(rejected_count),
        "audit_review_queue_status_counts": {k: int(v) for k, v in sorted(status_counts.items())},
        "audit_review_queue_action_family_counts": {k: int(v) for k, v in sorted(action_family_counts.items())},
        "audit_review_queue_status_mode": "refreshed_from_status_files" if queue_items else "empty_without_history",
    }
    payload = {
        "schema_version": "1.0",
        "audit_review_queue_items": queue_items,
        "audit_review_queue_status_directory": str(queue_status_dir),
        "summary": summary,
    }
    _write_json(manifest_path, payload)
    return payload


def _patch_export_report(
    export_report_path: Path,
    queue_manifest_payload: dict[str, Any],
    followup_manifest_payload: dict[str, Any],
    resolution_manifest_payload: dict[str, Any],
) -> bool:
    if not export_report_path.exists():
        return False
    export_report = _load_json(export_report_path)
    summary = export_report.get("summary") if isinstance(export_report.get("summary"), dict) else {}
    queue_summary = queue_manifest_payload.get("summary") if isinstance(queue_manifest_payload.get("summary"), dict) else {}
    followup_summary = (
        followup_manifest_payload.get("summary") if isinstance(followup_manifest_payload.get("summary"), dict) else {}
    )
    resolution_summary = (
        resolution_manifest_payload.get("summary")
        if isinstance(resolution_manifest_payload.get("summary"), dict)
        else {}
    )
    summary["audit_review_queue_item_count"] = int(queue_summary.get("audit_review_queue_item_count", 0) or 0)
    summary["audit_review_queue_pending_count"] = int(queue_summary.get("audit_review_queue_pending_count", 0) or 0)
    summary["audit_review_queue_acknowledged_count"] = int(queue_summary.get("audit_review_queue_acknowledged_count", 0) or 0)
    summary["audit_review_queue_approved_count"] = int(queue_summary.get("audit_review_queue_approved_count", 0) or 0)
    summary["audit_review_queue_rejected_count"] = int(queue_summary.get("audit_review_queue_rejected_count", 0) or 0)
    summary["audit_review_queue_status_counts"] = {
        str(k): int(v) for k, v in sorted((queue_summary.get("audit_review_queue_status_counts") or {}).items())
    }
    summary["audit_review_queue_action_family_counts"] = {
        str(k): int(v) for k, v in sorted((queue_summary.get("audit_review_queue_action_family_counts") or {}).items())
    }
    summary["audit_review_queue_status_mode"] = str(queue_summary.get("audit_review_queue_status_mode", "") or "")
    summary["audit_review_followup_item_count"] = int(followup_summary.get("audit_review_followup_item_count", 0) or 0)
    summary["audit_review_followup_open_item_count"] = int(
        followup_summary.get("audit_review_followup_open_item_count", 0) or 0
    )
    summary["audit_review_followup_closed_item_count"] = int(
        followup_summary.get("audit_review_followup_closed_item_count", 0) or 0
    )
    summary["audit_review_followup_action_counts"] = {
        str(k): int(v) for k, v in sorted((followup_summary.get("audit_review_followup_action_counts") or {}).items())
    }
    summary["audit_review_followup_action_label"] = str(
        followup_summary.get("audit_review_followup_action_label", "") or ""
    )
    summary["audit_review_followup_review_owner_counts"] = {
        str(k): int(v) for k, v in sorted((followup_summary.get("audit_review_followup_review_owner_counts") or {}).items())
    }
    summary["audit_review_followup_review_owner_label"] = str(
        followup_summary.get("audit_review_followup_review_owner_label", "") or ""
    )
    summary["audit_review_followup_status_counts"] = {
        str(k): int(v) for k, v in sorted((followup_summary.get("audit_review_followup_status_counts") or {}).items())
    }
    summary["audit_review_followup_status_label"] = str(
        followup_summary.get("audit_review_followup_status_label", "") or ""
    )
    summary["audit_review_followup_owner_counts"] = {
        str(k): int(v) for k, v in sorted((followup_summary.get("audit_review_followup_owner_counts") or {}).items())
    }
    summary["audit_review_followup_owner_label"] = str(
        followup_summary.get("audit_review_followup_owner_label", "") or ""
    )
    summary["audit_review_followup_sla_state_counts"] = {
        str(k): int(v) for k, v in sorted((followup_summary.get("audit_review_followup_sla_state_counts") or {}).items())
    }
    summary["audit_review_followup_sla_state_label"] = str(
        followup_summary.get("audit_review_followup_sla_state_label", "") or ""
    )
    summary["audit_review_followup_age_bucket_counts"] = {
        str(k): int(v) for k, v in sorted((followup_summary.get("audit_review_followup_age_bucket_counts") or {}).items())
    }
    summary["audit_review_followup_age_bucket_label"] = str(
        followup_summary.get("audit_review_followup_age_bucket_label", "") or ""
    )
    summary["audit_review_followup_overdue_item_count"] = int(
        followup_summary.get("audit_review_followup_overdue_item_count", 0) or 0
    )
    summary["audit_review_followup_oldest_open_age_hours"] = float(
        followup_summary.get("audit_review_followup_oldest_open_age_hours", 0.0) or 0.0
    )
    summary["audit_review_followup_oldest_open_packet_id"] = str(
        followup_summary.get("audit_review_followup_oldest_open_packet_id", "") or ""
    )
    summary["audit_review_followup_reference_time_utc"] = str(
        followup_summary.get("audit_review_followup_reference_time_utc", "") or ""
    )
    summary["audit_review_followup_sla_policy_label"] = str(
        followup_summary.get("audit_review_followup_sla_policy_label", "") or ""
    )
    summary["audit_review_followup_mode"] = str(followup_summary.get("audit_review_followup_mode", "") or "")
    summary["audit_review_resolution_item_count"] = int(
        resolution_summary.get("audit_review_resolution_item_count", 0) or 0
    )
    summary["audit_review_resolution_file_count"] = int(
        resolution_summary.get("audit_review_resolution_file_count", 0) or 0
    )
    summary["audit_review_resolution_open_item_count"] = int(
        resolution_summary.get("audit_review_resolution_open_item_count", 0) or 0
    )
    summary["audit_review_resolution_closed_item_count"] = int(
        resolution_summary.get("audit_review_resolution_closed_item_count", 0) or 0
    )
    summary["audit_review_resolution_pending_item_count"] = int(
        resolution_summary.get("audit_review_resolution_pending_item_count", 0) or 0
    )
    summary["audit_review_resolution_open_revision_count"] = int(
        resolution_summary.get("audit_review_resolution_open_revision_count", 0) or 0
    )
    summary["audit_review_resolution_closed_packet_count"] = int(
        resolution_summary.get("audit_review_resolution_closed_packet_count", 0) or 0
    )
    summary["audit_review_resolution_action_counts"] = {
        str(k): int(v) for k, v in sorted((resolution_summary.get("audit_review_resolution_action_counts") or {}).items())
    }
    summary["audit_review_resolution_action_label"] = str(
        resolution_summary.get("audit_review_resolution_action_label", "") or ""
    )
    summary["audit_review_resolution_owner_counts"] = {
        str(k): int(v) for k, v in sorted((resolution_summary.get("audit_review_resolution_owner_counts") or {}).items())
    }
    summary["audit_review_resolution_owner_label"] = str(
        resolution_summary.get("audit_review_resolution_owner_label", "") or ""
    )
    summary["audit_review_resolution_status_counts"] = {
        str(k): int(v) for k, v in sorted((resolution_summary.get("audit_review_resolution_status_counts") or {}).items())
    }
    summary["audit_review_resolution_status_label"] = str(
        resolution_summary.get("audit_review_resolution_status_label", "") or ""
    )
    summary["audit_review_resolution_mode"] = str(
        resolution_summary.get("audit_review_resolution_mode", "") or ""
    )
    summary["audit_review_queue_sync_source"] = "queue_manifest_override"
    export_report["summary"] = summary
    _write_json(export_report_path, export_report)
    return True


def _build_queue_manifest_payload(
    queue_status_dir: Path,
    status_payloads: dict[Path, dict[str, Any]],
) -> dict[str, Any]:
    queue_items: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    action_family_counts: Counter[str] = Counter()
    pending_count = 0
    acknowledged_count = 0
    approved_count = 0
    rejected_count = 0

    for status_path in sorted(status_payloads):
        payload = status_payloads[status_path]
        queue_status = str(payload.get("queue_status", "") or "")
        action_family = str(payload.get("action_family", "") or "")
        acknowledged = bool(payload.get("acknowledged", False))
        queue_items.append(
            {
                "packet_id": str(payload.get("packet_id", "") or ""),
                "action_family": action_family,
                "followup_type": str(payload.get("followup_type", "") or ""),
                "review_priority": str(payload.get("review_priority", "") or ""),
                "review_owner": str(payload.get("review_owner", "") or ""),
                "queue_status": queue_status,
                "acknowledged": acknowledged,
                "resolution": str(payload.get("resolution", "") or ""),
                "created_at_utc": str(payload.get("created_at_utc", "") or ""),
                "last_transition_at_utc": str(payload.get("last_transition_at_utc", "") or ""),
                "path": str(status_path),
                "packet_file_path": str(payload.get("packet_file_path", "") or ""),
                "change_count": int(payload.get("change_count", 0) or 0),
                "row_count": int(payload.get("row_count", 0) or 0),
            }
        )
        if queue_status:
            status_counts[queue_status] += 1
        if action_family:
            action_family_counts[action_family] += 1
        if queue_status == "pending_review":
            pending_count += 1
        if acknowledged:
            acknowledged_count += 1
        if queue_status == "approved":
            approved_count += 1
        if queue_status == "rejected":
            rejected_count += 1

    return {
        "schema_version": "1.0",
        "audit_review_queue_items": queue_items,
        "audit_review_queue_status_directory": str(queue_status_dir),
        "summary": {
            "audit_review_queue_item_count": len(queue_items),
            "audit_review_queue_pending_count": int(pending_count),
            "audit_review_queue_acknowledged_count": int(acknowledged_count),
            "audit_review_queue_approved_count": int(approved_count),
            "audit_review_queue_rejected_count": int(rejected_count),
            "audit_review_queue_status_counts": {k: int(v) for k, v in sorted(status_counts.items())},
            "audit_review_queue_action_family_counts": {k: int(v) for k, v in sorted(action_family_counts.items())},
            "audit_review_queue_status_mode": "refreshed_from_status_files" if queue_items else "empty_without_history",
        },
    }


def _load_status_payloads(queue_status_dir: Path) -> dict[Path, dict[str, Any]]:
    status_payloads: dict[Path, dict[str, Any]] = {}
    if not queue_status_dir.exists():
        return status_payloads
    for status_path in sorted(queue_status_dir.glob("*.review_status.json")):
        status_payloads[status_path] = _load_json(status_path)
    return status_payloads


def _resolve_update_requests(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    batch_path = str(args.batch_updates_json).strip()
    has_single = bool(str(args.set_status).strip())
    if batch_path and has_single:
        raise SystemExit("Use either --batch-updates-json or single-update flags, not both.")
    if batch_path:
        payload = _load_json(Path(batch_path))
        attestation = _normalize_attestation(payload.get("attestation") if isinstance(payload, dict) else {})
        if isinstance(payload, dict):
            rows = payload.get("updates")
        else:
            rows = payload
        if not isinstance(rows, list) or not rows:
            raise SystemExit("Batch update JSON must contain a non-empty list or {'updates': [...]} payload.")
        updates: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise SystemExit(f"Batch update row {idx} is not an object.")
            status = str(row.get("set_status", "") or "").strip()
            if status not in {"pending_review", "acknowledged", "approved", "rejected"}:
                raise SystemExit(f"Batch update row {idx} has invalid set_status: {status!r}")
            packet_id = str(row.get("packet_id", "") or "").strip()
            status_file = str(row.get("status_file", "") or "").strip()
            if not packet_id and not status_file:
                raise SystemExit(f"Batch update row {idx} needs packet_id or status_file.")
            updates.append(
                {
                    "packet_id": packet_id,
                    "status_file": status_file,
                    "set_status": status,
                    "resolution": str(row.get("resolution", "") or ""),
                    "review_owner": str(row.get("review_owner", "") or ""),
                    "note": str(row.get("note", "") or ""),
                }
            )
        return updates, attestation

    if not has_single:
        raise SystemExit("Provide --set-status for a single update or use --batch-updates-json.")
    if not str(args.packet_id).strip() and not str(args.status_file).strip():
        raise SystemExit("Provide --packet-id or --status-file.")
    return (
        [
            {
                "packet_id": str(args.packet_id).strip(),
                "status_file": str(args.status_file).strip(),
                "set_status": str(args.set_status).strip(),
                "resolution": str(args.resolution).strip(),
                "review_owner": str(args.review_owner).strip(),
                "note": str(args.note).strip(),
            }
        ],
        {},
    )


def _apply_update(
    manifest_payload: dict[str, Any],
    update: dict[str, Any],
    *,
    status_payloads: dict[Path, dict[str, Any]],
    batch_attestation: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    target_status_path = _resolve_target_status_file(
        manifest_payload,
        str(update.get("packet_id", "") or ""),
        str(update.get("status_file", "") or ""),
    )
    if target_status_path not in status_payloads and not target_status_path.exists():
        raise SystemExit(f"Queue status file not found: {target_status_path}")
    before_payload = dict(status_payloads.get(target_status_path) or _load_json(target_status_path))
    after_payload = dict(before_payload)
    previous_status = str(before_payload.get("queue_status", "") or "")
    target_status = str(update.get("set_status", "") or "")
    resolution = str(update.get("resolution", "") or "")
    if not resolution.strip():
        resolution = _default_resolution(target_status)
    review_owner = str(update.get("review_owner", "") or before_payload.get("review_owner", "") or "licensed_engineer")
    transition_at = _now_utc()
    history = before_payload.get("status_history") if isinstance(before_payload.get("status_history"), list) else []
    history = list(history)
    history.append(
        {
            "transitioned_at_utc": transition_at,
            "from_status": previous_status,
            "to_status": target_status,
            "note": str(update.get("note", "") or ""),
            "batch_attestation": dict(batch_attestation or {}),
        }
    )
    after_payload.update(
        {
            "review_owner": review_owner,
            "queue_status": target_status,
            "acknowledged": _status_acknowledged(target_status),
            "resolution": resolution,
            "last_transition_at_utc": transition_at,
            "status_history": history,
            "last_decision_attestation": dict(batch_attestation or {}),
        }
    )
    status_payloads[target_status_path] = after_payload
    if not dry_run:
        _write_json(target_status_path, after_payload)
    return {
        "target_status_path": str(target_status_path),
        "target_packet_id": str(after_payload.get("packet_id", "") or ""),
        "previous_status": previous_status,
        "current_status": target_status,
        "acknowledged": bool(after_payload.get("acknowledged", False)),
        "resolution": str(after_payload.get("resolution", "") or ""),
        "review_owner": review_owner,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    p.add_argument("--queue-status-dir", default="")
    p.add_argument("--mgt-export-report", default=str(DEFAULT_EXPORT_REPORT))
    p.add_argument("--audit-review-followup-manifest", default=str(DEFAULT_FOLLOWUP_MANIFEST))
    p.add_argument("--audit-review-resolution-manifest", default=str(DEFAULT_RESOLUTION_MANIFEST))
    p.add_argument("--audit-review-resolution-dir", default=str(DEFAULT_RESOLUTION_DIR))
    p.add_argument("--batch-updates-json", default="")
    p.add_argument("--packet-id", default="")
    p.add_argument("--status-file", default="")
    p.add_argument("--set-status", default="", choices=["", "pending_review", "acknowledged", "approved", "rejected"])
    p.add_argument("--resolution", default="")
    p.add_argument("--review-owner", default="")
    p.add_argument("--note", default="")
    p.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", default=str(DEFAULT_OUT_REPORT))
    args = p.parse_args()

    manifest_path = Path(args.queue_manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Queue manifest not found: {manifest_path}")
    manifest_payload = _load_json(manifest_path)
    queue_status_dir = _resolve_queue_status_dir(manifest_path, manifest_payload, args.queue_status_dir)
    status_payloads = _load_status_payloads(queue_status_dir)
    update_requests, batch_attestation = _resolve_update_requests(args)
    attestation_missing_fields = (
        _missing_attestation_fields(batch_attestation)
        if str(args.batch_updates_json).strip() and not bool(args.dry_run)
        else []
    )
    if attestation_missing_fields:
        raise SystemExit(
            "Batch live updates require attestation fields: " + ", ".join(attestation_missing_fields)
        )
    update_results: list[dict[str, Any]] = []
    for update in update_requests:
        update_results.append(
            _apply_update(
                manifest_payload,
                update,
                status_payloads=status_payloads,
                batch_attestation=batch_attestation,
                dry_run=bool(args.dry_run),
            )
        )
    refreshed_manifest = _build_queue_manifest_payload(queue_status_dir, status_payloads)
    followup_manifest = build_followup_manifest(refreshed_manifest)
    resolution_manifest = build_resolution_manifest(refreshed_manifest, followup_manifest)
    resolution_files = []
    if not bool(args.dry_run):
        resolution_files = write_resolution_files(
            Path(args.audit_review_resolution_dir),
            resolution_manifest.get("audit_review_resolution_rows", []),
        )
    resolution_manifest["audit_review_resolution_files"] = resolution_files
    resolution_manifest["audit_review_resolution_directory"] = str(args.audit_review_resolution_dir)
    resolution_summary = resolution_manifest.get("summary") if isinstance(resolution_manifest.get("summary"), dict) else {}
    resolution_summary["audit_review_resolution_file_count"] = int(len(resolution_files))
    if not bool(args.dry_run):
        _write_json(manifest_path, refreshed_manifest)
        _write_json(Path(args.audit_review_followup_manifest), followup_manifest)
        _write_json(Path(args.audit_review_resolution_manifest), resolution_manifest)
    export_report_patched = False
    if not bool(args.dry_run):
        export_report_patched = _patch_export_report(
            Path(args.mgt_export_report),
            refreshed_manifest,
            followup_manifest,
            resolution_manifest,
        )
    steps: list[dict[str, Any]] = []
    release_surface_refresh_pass = not bool(args.refresh_release_surfaces)

    if bool(args.refresh_release_surfaces):
        release_steps = [
            (
                "release_gap_report",
                [
                    sys.executable,
                    "implementation/phase1/generate_release_gap_report.py",
                    "--mgt-export-report",
                    str(args.mgt_export_report),
                    "--mgt-export-audit-review-queue-manifest",
                    str(manifest_path),
                    "--mgt-export-audit-review-followup-manifest",
                    str(args.audit_review_followup_manifest),
                    "--out-json",
                    str(DEFAULT_RELEASE_GAP_JSON),
                    "--out-md",
                    str(DEFAULT_RELEASE_GAP_MD),
                ],
            ),
            (
                "external_benchmark_submission_readiness",
                [
                    sys.executable,
                    "implementation/phase1/generate_external_benchmark_submission_readiness.py",
                ],
            ),
            (
                "release_registry",
                [
                    sys.executable,
                    "implementation/phase1/generate_signed_release_registry.py",
                    "--gap-report",
                    str(DEFAULT_RELEASE_GAP_JSON),
                    "--committee-package",
                    str(DEFAULT_COMMITTEE_OUT_DIR / "committee_review_package_report.json"),
                    "--committee-summary",
                    str(DEFAULT_COMMITTEE_OUT_DIR / "committee_summary.json"),
                    "--private-key-out",
                    str(DEFAULT_RELEASE_PRIVATE_KEY),
                    "--public-key-out",
                    str(DEFAULT_RELEASE_PUBLIC_KEY),
                    "--signature-out",
                    str(DEFAULT_RELEASE_SIGNATURE),
                    "--out",
                    str(DEFAULT_RELEASE_REGISTRY),
                ],
            ),
            (
                "committee_review_package",
                [
                    sys.executable,
                    "implementation/phase1/generate_committee_review_package.py",
                    "--gap-report",
                    str(DEFAULT_RELEASE_GAP_JSON),
                    "--release-registry",
                    str(DEFAULT_RELEASE_REGISTRY),
                    "--out-dir",
                    str(DEFAULT_COMMITTEE_OUT_DIR),
                ],
            ),
            (
                "external_validation_submission",
                [
                    sys.executable,
                    "implementation/phase1/prepare_external_validation_submission.py",
                    "--release-dir",
                    str(RELEASE_DIR),
                    "--latest-pointer",
                    str(DEFAULT_EXTERNAL_LATEST),
                    "--light-latest-pointer",
                    str(DEFAULT_EXTERNAL_LIGHT_LATEST),
                ],
            ),
            (
                "freeze_release_snapshot",
                [
                    sys.executable,
                    "implementation/phase1/freeze_release_snapshot.py",
                ],
            ),
            (
                "promote_release_candidate",
                [
                    sys.executable,
                    "implementation/phase1/promote_release_candidate.py",
                ],
            ),
        ]
        release_surface_refresh_pass = True
        for step_name, cmd in release_steps:
            if not _append_step(steps, step_name, cmd, dry_run=bool(args.dry_run)):
                release_surface_refresh_pass = False
                break

    reason_code = "PASS" if bool(release_surface_refresh_pass) else "ERR_RELEASE_REFRESH_FAIL"
    reason = (
        "audit review queue status update completed"
        if reason_code == "PASS"
        else "audit review queue status update completed, but release surface refresh failed"
    )

    out_path = Path(args.out)
    _write_json(
        out_path,
        {
            "contract_pass": bool(reason_code == "PASS"),
            "reason_code": reason_code,
            "reason": reason,
            "queue_manifest_path": str(manifest_path),
            "audit_review_followup_manifest_path": str(args.audit_review_followup_manifest),
            "audit_review_resolution_manifest_path": str(args.audit_review_resolution_manifest),
            "audit_review_resolution_dir": str(args.audit_review_resolution_dir),
            "queue_status_dir": str(queue_status_dir),
            "batch_update_count": int(len(update_results)),
            "batch_attestation": batch_attestation,
            "batch_attestation_missing_fields": attestation_missing_fields,
            "updates": update_results,
            "target_status_path": str(update_results[0]["target_status_path"]) if update_results else "",
            "target_packet_id": str(update_results[0]["target_packet_id"]) if update_results else "",
            "previous_status": str(update_results[0]["previous_status"]) if update_results else "",
            "current_status": str(update_results[0]["current_status"]) if update_results else "",
            "acknowledged": bool(update_results[0]["acknowledged"]) if update_results else False,
            "resolution": str(update_results[0]["resolution"]) if update_results else "",
            "review_owner": str(update_results[0]["review_owner"]) if update_results else "",
            "export_report_path": str(args.mgt_export_report),
            "export_report_patched": bool(export_report_patched),
            "refresh_release_surfaces": bool(args.refresh_release_surfaces),
            "release_surface_refresh_pass": bool(release_surface_refresh_pass),
            "dry_run": bool(args.dry_run),
            "state_write_skipped": bool(args.dry_run),
            "queue_summary": refreshed_manifest.get("summary", {}),
            "followup_summary": followup_manifest.get("summary", {}),
            "resolution_summary": resolution_manifest.get("summary", {}),
            "steps": steps,
        },
    )
    print(f"Wrote audit review queue update report: {out_path}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
