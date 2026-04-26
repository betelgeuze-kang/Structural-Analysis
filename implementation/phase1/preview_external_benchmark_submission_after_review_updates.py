#!/usr/bin/env python3
"""Preview external benchmark submission readiness after hypothetical review updates."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from implementation.phase1.generate_audit_review_followup_manifest import build_followup_manifest
from implementation.phase1.generate_audit_review_resolution_manifest import build_resolution_manifest
from implementation.phase1.generate_external_benchmark_submission_readiness import (
    DEFAULT_COMMERCIAL_READINESS_REPORT,
    DEFAULT_PEER_SPD_HINGE_ALIGNMENT_REPORT,
    DEFAULT_PEER_SPD_HINGE_BENCHMARK_REPORT,
    DEFAULT_PEER_SPD_HINGE_FIXTURE_REGRESSION_REPORT,
    DEFAULT_RELEASE_GAP_REPORT,
    DEFAULT_TPU_HFFB_BENCHMARK_REPORT,
    build_submission_readiness,
)

DEFAULT_QUEUE_MANIFEST = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")
DEFAULT_OUT = DEFAULT_OUT_DIR / "external_benchmark_submission_readiness_preview.json"

VALID_STATUSES = {"pending_review", "acknowledged", "approved", "rejected"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _default_resolution(target_status: str, current_resolution: str) -> str:
    if current_resolution.strip():
        return current_resolution
    if target_status == "approved":
        return "approved"
    if target_status == "rejected":
        return "rejected"
    return ""


def _build_queue_manifest_payload(queue_items: list[dict[str, Any]], queue_status_dir: str) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    action_family_counts: Counter[str] = Counter()
    pending_count = 0
    acknowledged_count = 0
    approved_count = 0
    rejected_count = 0

    normalized_items: list[dict[str, Any]] = []
    for row in queue_items:
        queue_status = str(row.get("queue_status", "") or "")
        action_family = str(row.get("action_family", "") or "")
        acknowledged = bool(row.get("acknowledged", False))
        normalized = {
            "packet_id": str(row.get("packet_id", "") or ""),
            "action_family": action_family,
            "followup_type": str(row.get("followup_type", "") or ""),
            "review_priority": str(row.get("review_priority", "") or ""),
            "review_owner": str(row.get("review_owner", "") or ""),
            "queue_status": queue_status,
            "acknowledged": acknowledged,
            "resolution": str(row.get("resolution", "") or ""),
            "created_at_utc": str(row.get("created_at_utc", "") or ""),
            "last_transition_at_utc": str(row.get("last_transition_at_utc", "") or ""),
            "path": str(row.get("path", "") or ""),
            "packet_file_path": str(row.get("packet_file_path", "") or ""),
            "change_count": int(row.get("change_count", 0) or 0),
            "row_count": int(row.get("row_count", 0) or 0),
        }
        normalized_items.append(normalized)
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
        "audit_review_queue_items": normalized_items,
        "audit_review_queue_status_directory": queue_status_dir,
        "summary": {
            "audit_review_queue_item_count": int(len(normalized_items)),
            "audit_review_queue_pending_count": int(pending_count),
            "audit_review_queue_acknowledged_count": int(acknowledged_count),
            "audit_review_queue_approved_count": int(approved_count),
            "audit_review_queue_rejected_count": int(rejected_count),
            "audit_review_queue_status_counts": {key: int(value) for key, value in sorted(status_counts.items())},
            "audit_review_queue_action_family_counts": {key: int(value) for key, value in sorted(action_family_counts.items())},
            "audit_review_queue_status_mode": "preview_from_batch_updates" if normalized_items else "empty_without_history",
        },
    }


def _parse_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("updates") if isinstance(payload, dict) else None
    if rows is None and isinstance(payload, list):
        rows = payload
    if not isinstance(rows, list) or not rows:
        raise SystemExit("Batch preview JSON must contain a non-empty list or {'updates': [...]} payload.")
    updates: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise SystemExit(f"Batch preview row {idx} is not an object.")
        set_status = str(row.get("set_status", "") or "").strip()
        if set_status not in VALID_STATUSES:
            raise SystemExit(f"Batch preview row {idx} has invalid set_status: {set_status!r}")
        packet_id = str(row.get("packet_id", "") or "").strip()
        status_file = str(row.get("status_file", "") or "").strip()
        if not packet_id and not status_file:
            raise SystemExit(f"Batch preview row {idx} needs packet_id or status_file.")
        updates.append(
            {
                "packet_id": packet_id,
                "status_file": status_file,
                "set_status": set_status,
                "resolution": str(row.get("resolution", "") or "").strip(),
                "review_owner": str(row.get("review_owner", "") or "").strip(),
                "note": str(row.get("note", "") or "").strip(),
            }
        )
    return updates


def _apply_preview_updates(queue_manifest_payload: dict[str, Any], update_requests: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    queue_items = queue_manifest_payload.get("audit_review_queue_items")
    if not isinstance(queue_items, list):
        raise SystemExit("Queue manifest has no audit_review_queue_items list.")
    preview_items = [dict(row) for row in queue_items if isinstance(row, dict)]
    index_by_packet = {
        str(row.get("packet_id", "") or ""): idx
        for idx, row in enumerate(preview_items)
        if str(row.get("packet_id", "") or "").strip()
    }
    index_by_status_file = {
        str(row.get("path", "") or ""): idx
        for idx, row in enumerate(preview_items)
        if str(row.get("path", "") or "").strip()
    }
    applied: list[dict[str, Any]] = []
    transition_at = datetime.now(timezone.utc).isoformat()

    for update in update_requests:
        packet_id = str(update.get("packet_id", "") or "")
        status_file = str(update.get("status_file", "") or "")
        index = None
        if packet_id and packet_id in index_by_packet:
            index = index_by_packet[packet_id]
        elif status_file and status_file in index_by_status_file:
            index = index_by_status_file[status_file]
        if index is None:
            raise SystemExit(f"Preview target not found: packet_id={packet_id!r}, status_file={status_file!r}")
        row = dict(preview_items[index])
        previous_status = str(row.get("queue_status", "") or "")
        target_status = str(update.get("set_status", "") or "")
        review_owner = str(update.get("review_owner", "") or row.get("review_owner", "") or "licensed_engineer")
        resolution = _default_resolution(target_status, str(update.get("resolution", "") or ""))
        history = row.get("status_history") if isinstance(row.get("status_history"), list) else []
        history = list(history)
        history.append(
            {
                "transitioned_at_utc": transition_at,
                "from_status": previous_status,
                "to_status": target_status,
                "note": str(update.get("note", "") or "preview_only"),
                "preview_only": True,
            }
        )
        row.update(
            {
                "queue_status": target_status,
                "acknowledged": target_status in {"acknowledged", "approved", "rejected"},
                "resolution": resolution,
                "review_owner": review_owner,
                "last_transition_at_utc": transition_at,
                "status_history": history,
            }
        )
        preview_items[index] = row
        applied.append(
            {
                "packet_id": str(row.get("packet_id", "") or ""),
                "previous_status": previous_status,
                "current_status": target_status,
                "review_owner": review_owner,
                "resolution": resolution,
                "status_file": str(row.get("path", "") or ""),
            }
        )

    queue_status_dir = str(queue_manifest_payload.get("audit_review_queue_status_directory", "") or "")
    return _build_queue_manifest_payload(preview_items, queue_status_dir), applied


def _patch_gap_payload(
    release_gap_payload: dict[str, Any],
    queue_manifest_preview: dict[str, Any],
    followup_preview: dict[str, Any],
    resolution_preview: dict[str, Any],
) -> dict[str, Any]:
    preview = deepcopy(release_gap_payload)
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    queue_summary = queue_manifest_preview.get("summary") if isinstance(queue_manifest_preview.get("summary"), dict) else {}
    followup_summary = followup_preview.get("summary") if isinstance(followup_preview.get("summary"), dict) else {}
    resolution_summary = resolution_preview.get("summary") if isinstance(resolution_preview.get("summary"), dict) else {}

    summary["mgt_export_audit_review_queue_item_count"] = int(queue_summary.get("audit_review_queue_item_count", 0) or 0)
    summary["mgt_export_audit_review_queue_pending_count"] = int(queue_summary.get("audit_review_queue_pending_count", 0) or 0)
    summary["mgt_export_audit_review_queue_acknowledged_count"] = int(queue_summary.get("audit_review_queue_acknowledged_count", 0) or 0)
    summary["mgt_export_audit_review_queue_approved_count"] = int(queue_summary.get("audit_review_queue_approved_count", 0) or 0)
    summary["mgt_export_audit_review_queue_rejected_count"] = int(queue_summary.get("audit_review_queue_rejected_count", 0) or 0)
    summary["mgt_export_audit_review_queue_status_counts"] = dict(queue_summary.get("audit_review_queue_status_counts", {}) or {})
    summary["mgt_export_audit_review_queue_action_family_counts"] = dict(queue_summary.get("audit_review_queue_action_family_counts", {}) or {})
    summary["mgt_export_audit_review_queue_status_mode"] = str(queue_summary.get("audit_review_queue_status_mode", "") or "")
    summary["mgt_export_audit_review_followup_overdue_item_count"] = int(
        followup_summary.get("audit_review_followup_overdue_item_count", 0) or 0
    )
    summary["mgt_export_audit_review_followup_action_label"] = str(
        followup_summary.get("audit_review_followup_action_label", "") or ""
    )
    summary["mgt_export_audit_review_followup_status_label"] = str(
        followup_summary.get("audit_review_followup_status_label", "") or ""
    )
    summary["mgt_export_audit_review_followup_review_owner_label"] = str(
        followup_summary.get("audit_review_followup_review_owner_label", "") or ""
    )
    summary["mgt_export_audit_review_resolution_open_revision_count"] = int(
        resolution_summary.get("audit_review_resolution_open_revision_count", 0) or 0
    )
    summary["mgt_export_audit_review_resolution_action_label"] = str(
        resolution_summary.get("audit_review_resolution_action_label", "") or ""
    )
    summary["mgt_export_audit_review_resolution_status_label"] = str(
        resolution_summary.get("audit_review_resolution_status_label", "") or ""
    )
    preview["summary"] = summary
    return preview


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    readiness = payload.get("readiness_preview") if isinstance(payload.get("readiness_preview"), dict) else {}
    readiness_summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    lines = [
        "# External Benchmark Submission Readiness Preview",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `preview_update_count`: `{int(summary.get('preview_update_count', 0))}`",
        f"- `predicted_reason_code`: `{readiness.get('reason_code', '')}`",
        f"- `recommended_start_mode`: `{readiness_summary.get('recommended_start_mode', '')}`",
        f"- `recommended_submission_scope`: `{readiness_summary.get('recommended_submission_scope', '')}`",
        f"- `pending_review_count`: `{int(readiness_summary.get('audit_review_queue_pending_count', 0))}`",
        f"- `open_revision_count`: `{int(readiness_summary.get('audit_review_resolution_open_revision_count', 0))}`",
        f"- `blockers`: `{readiness_summary.get('blocker_label', 'none')}`",
        f"- `cautions`: `{readiness_summary.get('caution_label', 'none')}`",
        "",
        "## Applied Updates",
        "",
    ]
    for row in payload.get("applied_updates", []):
        lines.append(
            f"- `{row.get('packet_id', '')}` | `{row.get('previous_status', '')}` -> `{row.get('current_status', '')}` | "
            f"resolution=`{row.get('resolution', '')}`"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    parser.add_argument("--batch-updates-json", required=True)
    parser.add_argument("--release-gap-report", default=str(DEFAULT_RELEASE_GAP_REPORT))
    parser.add_argument("--commercial-readiness-report", default=str(DEFAULT_COMMERCIAL_READINESS_REPORT))
    parser.add_argument("--tpu-hffb-benchmark-report", default=str(DEFAULT_TPU_HFFB_BENCHMARK_REPORT))
    parser.add_argument("--peer-spd-hinge-benchmark-report", default=str(DEFAULT_PEER_SPD_HINGE_BENCHMARK_REPORT))
    parser.add_argument("--peer-spd-hinge-fixture-regression-report", default=str(DEFAULT_PEER_SPD_HINGE_FIXTURE_REGRESSION_REPORT))
    parser.add_argument("--peer-spd-hinge-alignment-report", default=str(DEFAULT_PEER_SPD_HINGE_ALIGNMENT_REPORT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    queue_manifest = Path(args.queue_manifest)
    if not queue_manifest.exists():
        raise SystemExit(f"Queue manifest not found: {queue_manifest}")

    updates_payload = _load_json(Path(args.batch_updates_json))
    update_requests = _parse_updates(updates_payload)
    queue_manifest_preview, applied_updates = _apply_preview_updates(_load_json(queue_manifest), update_requests)
    reference_time = datetime.now(timezone.utc).isoformat()
    followup_preview = build_followup_manifest(queue_manifest_preview, reference_time_utc=reference_time)
    resolution_preview = build_resolution_manifest(queue_manifest_preview, followup_preview)
    release_gap_preview = _patch_gap_payload(
        _load_json(Path(args.release_gap_report)),
        queue_manifest_preview,
        followup_preview,
        resolution_preview,
    )
    readiness_preview = build_submission_readiness(
        release_gap_preview,
        _load_json(Path(args.commercial_readiness_report)),
        _load_json(Path(args.tpu_hffb_benchmark_report)),
        _load_json(Path(args.peer_spd_hinge_benchmark_report)),
        _load_json(Path(args.peer_spd_hinge_fixture_regression_report)),
        _load_json(Path(args.peer_spd_hinge_alignment_report)),
    )

    payload = {
        "schema_version": "1.0",
        "generated_at": reference_time,
        "contract_pass": bool(readiness_preview.get("contract_pass", False)),
        "reason_code": str(readiness_preview.get("reason_code", "") or ""),
        "reason": str(readiness_preview.get("reason", "") or ""),
        "summary": {
            "preview_update_count": int(len(applied_updates)),
            "preview_queue_pending_count": int(queue_manifest_preview.get("summary", {}).get("audit_review_queue_pending_count", 0) or 0),
            "preview_resolution_open_revision_count": int(
                resolution_preview.get("summary", {}).get("audit_review_resolution_open_revision_count", 0) or 0
            ),
            "predicted_ready_to_start_now": bool(readiness_preview.get("summary", {}).get("ready_to_start_now", False)),
            "predicted_ready_to_start_full_submission_now": bool(
                readiness_preview.get("summary", {}).get("ready_to_start_full_submission_now", False)
            ),
        },
        "applied_updates": applied_updates,
        "queue_preview": queue_manifest_preview,
        "followup_preview": followup_preview,
        "resolution_preview": resolution_preview,
        "readiness_preview": readiness_preview,
    }
    out_path = Path(args.out)
    _write_json(out_path, payload)
    _write_md(out_path.with_suffix(".md"), _markdown(payload))
    print(f"Wrote external benchmark submission readiness preview: {out_path}")


if __name__ == "__main__":
    main()
