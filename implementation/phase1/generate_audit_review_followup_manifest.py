#!/usr/bin/env python3
"""Generate follow-up actions from the audit review queue manifest."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

DEFAULT_QUEUE_MANIFEST = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json")
DEFAULT_OUT = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_followup_manifest.json")
DEFAULT_ASSIGNMENT_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_owner_assignments.json"
)
DEFAULT_SLA_HOURS = 96.0
SLA_HOURS_BY_PRIORITY = {
    "critical": 8.0,
    "high": 24.0,
    "medium": 72.0,
    "low": 168.0,
}

FOLLOWUP_ACTION_BY_STATUS = {
    "pending_review": ("wait_for_review", "licensed_engineer"),
    "acknowledged": ("review_in_progress", "licensed_engineer"),
    "approved": ("close_packet", "none"),
    "rejected": ("reopen_revision_cycle", "design_engineer"),
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _label(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={count}" for key, count in sorted(counts.items()))


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _reference_time(reference_time_utc: str | None) -> datetime:
    parsed = _parse_utc(reference_time_utc)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc)


def _age_bucket(age_hours: float | None, *, closed: bool) -> str:
    if closed:
        return "closed"
    if age_hours is None:
        return "unknown_age"
    if age_hours < 24.0:
        return "lt_24h"
    if age_hours < 72.0:
        return "24_to_72h"
    if age_hours < 168.0:
        return "72_to_168h"
    return "gte_168h"


def _sla_hours(priority: str) -> float:
    return float(SLA_HOURS_BY_PRIORITY.get(priority.strip().lower(), DEFAULT_SLA_HOURS))


def _normalized_hours(value: float | None) -> float | None:
    if value is None:
        return None
    normalized = float(value)
    if abs(normalized) < (1.0 / 3600.0):
        return 0.0
    return round(normalized, 6)


def _assignment_row_map(assignments_manifest_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(assignments_manifest_payload, dict):
        return {}
    rows = assignments_manifest_payload.get("assignment_rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("packet_id", "") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("packet_id", "") or "").strip()
    }


def build_followup_manifest(
    queue_manifest_payload: dict[str, Any],
    *,
    assignments_manifest_payload: dict[str, Any] | None = None,
    reference_time_utc: str | None = None,
) -> dict[str, Any]:
    queue_items = queue_manifest_payload.get("audit_review_queue_items")
    if not isinstance(queue_items, list):
        queue_items = []

    reference_time = _reference_time(reference_time_utc)
    rows: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    review_owner_counts: Counter[str] = Counter()
    assignee_counts: Counter[str] = Counter()
    assignment_status_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    sla_state_counts: Counter[str] = Counter()
    age_bucket_counts: Counter[str] = Counter()
    open_count = 0
    closed_count = 0
    overdue_count = 0
    oldest_open_age_hours = 0.0
    oldest_open_packet_id = ""
    assignment_row_map = _assignment_row_map(assignments_manifest_payload)

    for row in queue_items:
        if not isinstance(row, dict):
            continue
        queue_status = str(row.get("queue_status", "") or "")
        followup_action, followup_owner = FOLLOWUP_ACTION_BY_STATUS.get(
            queue_status,
            ("unknown_followup", "review_coordinator"),
        )
        if followup_action == "close_packet":
            closed_count += 1
        else:
            open_count += 1
        review_priority = str(row.get("review_priority", "") or "")
        review_owner = str(row.get("review_owner", "") or "").strip() or followup_owner
        assignment_row = assignment_row_map.get(str(row.get("packet_id", "") or ""), {})
        assigned_reviewer_name = str(assignment_row.get("assignee_name", "") or "").strip()
        assigned_reviewer_license_id = str(
            assignment_row.get("assignee_license_id", "") or ""
        ).strip()
        assignment_status = str(assignment_row.get("assignment_status", "") or "").strip().lower()
        if not assignment_status:
            assignment_status = "assigned" if assigned_reviewer_name else "unassigned"
        assignee_label = assigned_reviewer_name or "unassigned"
        age_started_at = (
            _parse_utc(row.get("last_transition_at_utc"))
            or _parse_utc(row.get("created_at_utc"))
            or _parse_utc(row.get("updated_at_utc"))
        )
        if age_started_at is not None and followup_action != "close_packet":
            age_hours = max((reference_time - age_started_at).total_seconds() / 3600.0, 0.0)
        elif followup_action == "close_packet":
            age_hours = 0.0
        else:
            age_hours = None
        sla_hours = _sla_hours(review_priority)
        due_at = age_started_at + timedelta(hours=sla_hours) if age_started_at is not None else None
        overdue = bool(
            followup_action != "close_packet"
            and due_at is not None
            and reference_time > due_at
        )
        overdue_hours = (
            max((reference_time - due_at).total_seconds() / 3600.0, 0.0)
            if overdue and due_at is not None
            else 0.0
        )
        age_hours = _normalized_hours(age_hours)
        overdue_hours = _normalized_hours(overdue_hours) or 0.0
        if followup_action == "close_packet":
            sla_state = "closed"
        elif age_started_at is None:
            sla_state = "age_unknown"
        elif overdue:
            sla_state = "overdue"
        else:
            sla_state = "within_sla"
        age_bucket = _age_bucket(age_hours, closed=followup_action == "close_packet")
        action_counts[followup_action] += 1
        owner_counts[followup_owner] += 1
        review_owner_counts[review_owner] += 1
        assignee_counts[assignee_label] += 1
        assignment_status_counts[assignment_status] += 1
        if queue_status:
            status_counts[queue_status] += 1
        sla_state_counts[sla_state] += 1
        age_bucket_counts[age_bucket] += 1
        if overdue:
            overdue_count += 1
        if age_hours is not None and followup_action != "close_packet" and age_hours >= oldest_open_age_hours:
            oldest_open_age_hours = float(age_hours)
            oldest_open_packet_id = str(row.get("packet_id", "") or "")
        rows.append(
            {
                "packet_id": str(row.get("packet_id", "") or ""),
                "action_family": str(row.get("action_family", "") or ""),
                "followup_type": str(row.get("followup_type", "") or ""),
                "review_priority": review_priority,
                "queue_status": queue_status,
                "followup_action": followup_action,
                "followup_owner": followup_owner,
                "review_owner": review_owner,
                "assigned_reviewer_name": assigned_reviewer_name,
                "assigned_reviewer_license_id": assigned_reviewer_license_id,
                "assignment_status": assignment_status,
                "assignment_note": str(assignment_row.get("note", "") or ""),
                "assignment_updated_at_utc": str(
                    assignment_row.get("assignment_updated_at_utc", "") or ""
                ),
                "status_file_path": str(row.get("path", "") or ""),
                "packet_file_path": str(row.get("packet_file_path", "") or ""),
                "change_count": int(row.get("change_count", 0) or 0),
                "row_count": int(row.get("row_count", 0) or 0),
                "age_started_at_utc": _iso_utc(age_started_at),
                "reference_time_utc": _iso_utc(reference_time),
                "sla_hours": float(sla_hours),
                "due_at_utc": _iso_utc(due_at),
                "age_hours": age_hours,
                "overdue": overdue,
                "overdue_hours": overdue_hours,
                "sla_state": sla_state,
                "age_bucket": age_bucket,
            }
        )

    action_dict = {k: int(v) for k, v in sorted(action_counts.items())}
    owner_dict = {k: int(v) for k, v in sorted(owner_counts.items())}
    review_owner_dict = {k: int(v) for k, v in sorted(review_owner_counts.items())}
    assignee_dict = {k: int(v) for k, v in sorted(assignee_counts.items())}
    assignment_status_dict = {k: int(v) for k, v in sorted(assignment_status_counts.items())}
    status_dict = {k: int(v) for k, v in sorted(status_counts.items())}
    sla_state_dict = {k: int(v) for k, v in sorted(sla_state_counts.items())}
    age_bucket_dict = {k: int(v) for k, v in sorted(age_bucket_counts.items())}
    return {
        "schema_version": "1.0",
        "audit_review_followup_rows": rows,
        "summary": {
            "audit_review_followup_item_count": int(len(rows)),
            "audit_review_followup_open_item_count": int(open_count),
            "audit_review_followup_closed_item_count": int(closed_count),
            "audit_review_followup_action_counts": action_dict,
            "audit_review_followup_action_label": _label(action_dict),
            "audit_review_followup_owner_counts": owner_dict,
            "audit_review_followup_owner_label": _label(owner_dict),
            "audit_review_followup_review_owner_counts": review_owner_dict,
            "audit_review_followup_review_owner_label": _label(review_owner_dict),
            "audit_review_followup_assignee_counts": assignee_dict,
            "audit_review_followup_assignee_label": _label(assignee_dict),
            "audit_review_followup_assignment_status_counts": assignment_status_dict,
            "audit_review_followup_assignment_status_label": _label(assignment_status_dict),
            "audit_review_followup_status_counts": status_dict,
            "audit_review_followup_status_label": _label(status_dict),
            "audit_review_followup_sla_state_counts": sla_state_dict,
            "audit_review_followup_sla_state_label": _label(sla_state_dict),
            "audit_review_followup_age_bucket_counts": age_bucket_dict,
            "audit_review_followup_age_bucket_label": _label(age_bucket_dict),
            "audit_review_followup_overdue_item_count": int(overdue_count),
            "audit_review_followup_oldest_open_age_hours": float(_normalized_hours(oldest_open_age_hours) or 0.0),
            "audit_review_followup_oldest_open_packet_id": str(oldest_open_packet_id),
            "audit_review_followup_reference_time_utc": _iso_utc(reference_time),
            "audit_review_followup_sla_policy_label": ", ".join(
                f"{priority}={int(hours)}h" for priority, hours in sorted(SLA_HOURS_BY_PRIORITY.items())
            )
            + f", default={int(DEFAULT_SLA_HOURS)}h",
            "audit_review_followup_mode": "queue_status_projected_followup_actions" if rows else "none",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    parser.add_argument("--assignment-manifest", default=str(DEFAULT_ASSIGNMENT_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--reference-time-utc", default="")
    args = parser.parse_args()

    queue_manifest_path = Path(args.queue_manifest)
    if not queue_manifest_path.exists():
        raise SystemExit(f"Queue manifest not found: {queue_manifest_path}")
    queue_manifest_payload = _load_json(queue_manifest_path)
    assignment_manifest_path = Path(args.assignment_manifest)
    assignment_manifest_payload = (
        _load_json(assignment_manifest_path) if assignment_manifest_path.exists() else {}
    )
    payload = build_followup_manifest(
        queue_manifest_payload,
        assignments_manifest_payload=assignment_manifest_payload,
        reference_time_utc=str(args.reference_time_utc or ""),
    )
    out_path = Path(args.out)
    _write_json(out_path, payload)
    print(f"Wrote audit review follow-up manifest: {out_path}")


if __name__ == "__main__":
    main()
