#!/usr/bin/env python3
"""Generate or refresh the audit review owner assignment manifest."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_QUEUE_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_owner_assignments.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _label(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def _existing_assignment_map(existing_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = existing_payload.get("assignment_rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("packet_id", "") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("packet_id", "") or "").strip()
    }


def build_assignment_manifest(
    queue_manifest_payload: dict[str, Any],
    *,
    existing_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    queue_rows = queue_manifest_payload.get("audit_review_queue_items")
    if not isinstance(queue_rows, list):
        queue_rows = []
    existing_map = _existing_assignment_map(existing_payload or {})
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    owner_role_counts: Counter[str] = Counter()
    assignee_counts: Counter[str] = Counter()

    for row in queue_rows:
        if not isinstance(row, dict):
            continue
        packet_id = str(row.get("packet_id", "") or "").strip()
        if not packet_id:
            continue
        existing = existing_map.get(packet_id, {})
        review_owner_role = str(row.get("review_owner", "") or "").strip() or "licensed_engineer"
        assignee_name = str(existing.get("assignee_name", "") or "").strip()
        assignment_status = str(existing.get("assignment_status", "") or "").strip().lower()
        if not assignment_status:
            assignment_status = "assigned" if assignee_name else "unassigned"
        rows.append(
            {
                "packet_id": packet_id,
                "action_family": str(row.get("action_family", "") or ""),
                "followup_type": str(row.get("followup_type", "") or ""),
                "review_priority": str(row.get("review_priority", "") or ""),
                "review_owner_role": review_owner_role,
                "assignee_name": assignee_name,
                "assignee_license_id": str(existing.get("assignee_license_id", "") or "").strip(),
                "assignee_email": str(existing.get("assignee_email", "") or "").strip(),
                "assignment_status": assignment_status,
                "assignment_updated_at_utc": str(
                    existing.get("assignment_updated_at_utc", "") or ""
                ),
                "note": str(existing.get("note", "") or ""),
            }
        )
        status_counts[assignment_status] += 1
        owner_role_counts[review_owner_role] += 1
        assignee_counts[assignee_name or "unassigned"] += 1

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assignment_rows": rows,
        "summary": {
            "audit_review_assignment_item_count": int(len(rows)),
            "audit_review_assignment_status_counts": {k: int(v) for k, v in sorted(status_counts.items())},
            "audit_review_assignment_status_label": _label(status_counts),
            "audit_review_assignment_owner_role_counts": {k: int(v) for k, v in sorted(owner_role_counts.items())},
            "audit_review_assignment_owner_role_label": _label(owner_role_counts),
            "audit_review_assignment_assignee_counts": {k: int(v) for k, v in sorted(assignee_counts.items())},
            "audit_review_assignment_assignee_label": _label(assignee_counts),
            "audit_review_assignment_mode": "merged_existing_assignments" if rows else "none",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    queue_manifest_path = Path(args.queue_manifest)
    if not queue_manifest_path.exists():
        raise SystemExit(f"Queue manifest not found: {queue_manifest_path}")
    out_path = Path(args.out)
    existing_payload = _load_json(out_path) if out_path.exists() else {}
    payload = build_assignment_manifest(_load_json(queue_manifest_path), existing_payload=existing_payload)
    _write_json(out_path, payload)
    print(f"Wrote audit review owner assignment manifest: {out_path}")


if __name__ == "__main__":
    main()
