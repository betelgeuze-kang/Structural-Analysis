#!/usr/bin/env python3
"""Generate resolution artifacts from audit review queue and follow-up manifests."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


DEFAULT_QUEUE_MANIFEST = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json")
DEFAULT_FOLLOWUP_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_followup_manifest.json"
)
DEFAULT_OUT = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_resolution_manifest.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_resolution_files")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _label(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={count}" for key, count in sorted(counts.items()))


def _slug(token: Any) -> str:
    text = str(token or "").strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    normalized = "".join(chars).strip("_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized or "unknown"


def _resolution_projection(followup_action: str, followup_owner: str, review_owner: str) -> tuple[str, str, str, bool]:
    if followup_action == "close_packet":
        return ("close_packet", "release_coordinator", "closed_packet", False)
    if followup_action == "reopen_revision_cycle":
        return ("reopen_revision_cycle", review_owner or "design_engineer", "revision_package_open", True)
    if followup_action == "review_in_progress":
        return ("continue_review", review_owner or followup_owner or "licensed_engineer", "in_review", True)
    return ("await_review_decision", review_owner or followup_owner or "licensed_engineer", "pending_review", True)


def build_resolution_manifest(
    queue_manifest_payload: dict[str, Any],
    followup_manifest_payload: dict[str, Any],
) -> dict[str, Any]:
    queue_rows = queue_manifest_payload.get("audit_review_queue_items")
    if not isinstance(queue_rows, list):
        queue_rows = []
    followup_rows = followup_manifest_payload.get("audit_review_followup_rows")
    if not isinstance(followup_rows, list):
        followup_rows = []

    queue_row_by_packet = {
        str(row.get("packet_id", "") or ""): row
        for row in queue_rows
        if isinstance(row, dict) and str(row.get("packet_id", "") or "").strip()
    }

    resolution_rows: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    open_count = 0
    closed_count = 0
    open_revision_count = 0
    closed_packet_count = 0
    pending_count = 0

    for row in followup_rows:
        if not isinstance(row, dict):
            continue
        packet_id = str(row.get("packet_id", "") or "")
        queue_row = queue_row_by_packet.get(packet_id, {})
        followup_action = str(row.get("followup_action", "") or "")
        review_owner = str(row.get("review_owner", "") or queue_row.get("review_owner", "") or "")
        followup_owner = str(row.get("followup_owner", "") or "")
        resolution_action, resolution_owner, resolution_status, resolution_required = _resolution_projection(
            followup_action,
            followup_owner,
            review_owner,
        )
        action_counts[resolution_action] += 1
        owner_counts[resolution_owner] += 1
        status_counts[resolution_status] += 1
        if resolution_status == "closed_packet":
            closed_count += 1
            closed_packet_count += 1
        else:
            open_count += 1
            if resolution_status == "revision_package_open":
                open_revision_count += 1
            if resolution_status == "pending_review":
                pending_count += 1
        resolution_rows.append(
            {
                "packet_id": packet_id,
                "action_family": str(row.get("action_family", "") or ""),
                "followup_type": str(row.get("followup_type", "") or ""),
                "review_priority": str(row.get("review_priority", "") or ""),
                "queue_status": str(row.get("queue_status", "") or ""),
                "review_owner": review_owner,
                "followup_action": followup_action,
                "resolution_action": resolution_action,
                "resolution_owner": resolution_owner,
                "resolution_status": resolution_status,
                "resolution_required": bool(resolution_required),
                "resolution_note": str(queue_row.get("resolution", "") or ""),
                "status_file_path": str(row.get("status_file_path", "") or queue_row.get("path", "") or ""),
                "packet_file_path": str(row.get("packet_file_path", "") or queue_row.get("packet_file_path", "") or ""),
                "change_count": int(row.get("change_count", 0) or 0),
                "row_count": int(row.get("row_count", 0) or 0),
            }
        )

    action_dict = {k: int(v) for k, v in sorted(action_counts.items())}
    owner_dict = {k: int(v) for k, v in sorted(owner_counts.items())}
    status_dict = {k: int(v) for k, v in sorted(status_counts.items())}
    return {
        "schema_version": "1.0",
        "audit_review_resolution_rows": resolution_rows,
        "summary": {
            "audit_review_resolution_item_count": int(len(resolution_rows)),
            "audit_review_resolution_open_item_count": int(open_count),
            "audit_review_resolution_closed_item_count": int(closed_count),
            "audit_review_resolution_pending_item_count": int(pending_count),
            "audit_review_resolution_open_revision_count": int(open_revision_count),
            "audit_review_resolution_closed_packet_count": int(closed_packet_count),
            "audit_review_resolution_action_counts": action_dict,
            "audit_review_resolution_action_label": _label(action_dict),
            "audit_review_resolution_owner_counts": owner_dict,
            "audit_review_resolution_owner_label": _label(owner_dict),
            "audit_review_resolution_status_counts": status_dict,
            "audit_review_resolution_status_label": _label(status_dict),
            "audit_review_resolution_mode": "queue_followup_projected_resolution_actions" if resolution_rows else "none",
        },
    }


def write_resolution_files(out_dir: Path, resolution_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if out_dir.exists():
        for existing in out_dir.glob("*.resolution.json"):
            existing.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for index, row in enumerate(resolution_rows, start=1):
        action_family = str(row.get("action_family", "") or "")
        resolution_action = str(row.get("resolution_action", "") or "")
        review_priority = str(row.get("review_priority", "") or "")
        file_name = (
            f"{index:02d}."
            f"{_slug(action_family)}."
            f"{_slug(resolution_action)}."
            f"{_slug(review_priority)}.resolution.json"
        )
        path = out_dir / file_name
        payload = {
            "schema_version": "1.0",
            "resolution": dict(row),
            "summary": {
                "packet_id": str(row.get("packet_id", "") or ""),
                "resolution_action": resolution_action,
                "resolution_status": str(row.get("resolution_status", "") or ""),
                "resolution_owner": str(row.get("resolution_owner", "") or ""),
                "change_count": int(row.get("change_count", 0) or 0),
                "row_count": int(row.get("row_count", 0) or 0),
            },
        }
        _write_json(path, payload)
        written.append(
            {
                "packet_id": str(row.get("packet_id", "") or ""),
                "resolution_action": resolution_action,
                "resolution_status": str(row.get("resolution_status", "") or ""),
                "resolution_owner": str(row.get("resolution_owner", "") or ""),
                "path": str(path),
            }
        )
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    parser.add_argument("--followup-manifest", default=str(DEFAULT_FOLLOWUP_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    queue_manifest_path = Path(args.queue_manifest)
    followup_manifest_path = Path(args.followup_manifest)
    if not queue_manifest_path.exists():
        raise SystemExit(f"Queue manifest not found: {queue_manifest_path}")
    if not followup_manifest_path.exists():
        raise SystemExit(f"Follow-up manifest not found: {followup_manifest_path}")

    queue_manifest_payload = _load_json(queue_manifest_path)
    followup_manifest_payload = _load_json(followup_manifest_path)
    payload = build_resolution_manifest(queue_manifest_payload, followup_manifest_payload)
    files = write_resolution_files(Path(args.out_dir), payload.get("audit_review_resolution_rows", []))
    payload["audit_review_resolution_files"] = files
    payload["audit_review_resolution_directory"] = str(Path(args.out_dir))
    payload["summary"]["audit_review_resolution_file_count"] = int(len(files))
    _write_json(Path(args.out), payload)
    print(f"Wrote audit review resolution manifest: {args.out}")


if __name__ == "__main__":
    main()
