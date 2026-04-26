from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from implementation.phase1.generate_audit_review_followup_manifest import build_followup_manifest
from implementation.phase1.hardest_external_10case_catalog import catalog_rows


DEFAULT_KICKOFF_PACKAGE = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_kickoff_package.json"
)
DEFAULT_HARDEST_EXTERNAL_10CASE_KICKOFF_REPORT = Path(
    "implementation/phase1/hardest_external_10case_kickoff_gate_report.json"
)
DEFAULT_OUT_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")
DEFAULT_AUDIT_REVIEW_QUEUE_MANIFEST = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json"
)
DEFAULT_AUDIT_REVIEW_ASSIGNMENT_MANIFEST = Path(
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


def _summary_dict(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def _bool_label(value: bool) -> str:
    return "yes" if value else "no"


def _count_label(rows: list[dict[str, Any]], key: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "") or "").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return "none"
    return ", ".join(f"{name}={counts[name]}" for name in sorted(counts))


def _build_review_boundary_preview_summary(
    approve_all_preview: dict[str, Any],
    reject_one_preview: dict[str, Any],
    decision_runner_report: dict[str, Any],
) -> dict[str, Any]:
    approve_summary = _summary_dict(approve_all_preview)
    reject_summary = _summary_dict(reject_one_preview)
    return {
        "approve_all_reason_code": str(approve_all_preview.get("reason_code", "") or ""),
        "approve_all_ready_full": bool(
            approve_summary.get("predicted_ready_to_start_full_submission_now", False)
        ),
        "approve_all_pending_count": int(
            approve_summary.get("preview_queue_pending_count", 0) or 0
        ),
        "approve_all_open_revision_count": int(
            approve_summary.get("preview_resolution_open_revision_count", 0) or 0
        ),
        "reject_one_reason_code": str(reject_one_preview.get("reason_code", "") or ""),
        "reject_one_ready_full": bool(
            reject_summary.get("predicted_ready_to_start_full_submission_now", False)
        ),
        "reject_one_pending_count": int(
            reject_summary.get("preview_queue_pending_count", 0) or 0
        ),
        "reject_one_open_revision_count": int(
            reject_summary.get("preview_resolution_open_revision_count", 0) or 0
        ),
        "decision_runner_reason_code": str(decision_runner_report.get("reason_code", "") or ""),
        "decision_runner_preview_reason_code": str(
            decision_runner_report.get("preview_reason_code", "") or ""
        ),
        "decision_runner_live_applied": bool(decision_runner_report.get("live_applied", False)),
        "decision_runner_apply_live": bool(decision_runner_report.get("apply_live", False)),
    }


def _build_review_boundary_resolution_label(preview_summary: dict[str, Any]) -> str:
    approve_reason = str(preview_summary.get("approve_all_reason_code", "") or "")
    reject_reason = str(preview_summary.get("reject_one_reason_code", "") or "")
    approve_full = _bool_label(bool(preview_summary.get("approve_all_ready_full", False)))
    reject_open = int(preview_summary.get("reject_one_open_revision_count", 0) or 0)
    return (
        f"approve_all={approve_reason}/ready_full={approve_full}; "
        f"reject_one={reject_reason}/open_revision={reject_open}"
    )


def _followup_row_map(
    queue_manifest: dict[str, Any],
    assignments_manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    followup_manifest = build_followup_manifest(
        queue_manifest,
        assignments_manifest_payload=assignments_manifest,
    )
    rows = followup_manifest.get("audit_review_followup_rows")
    if not isinstance(rows, list):
        rows = []
    row_map = {
        str(row.get("packet_id", "") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("packet_id", "") or "").strip()
    }
    summary = followup_manifest.get("summary")
    return row_map, summary if isinstance(summary, dict) else {}


def _build_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    review_preview = (
        payload.get("review_boundary_preview")
        if isinstance(payload.get("review_boundary_preview"), dict)
        else {}
    )
    lines = [
        "# External Benchmark Execution Manifest",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `execution_mode`: `{summary.get('execution_mode', '')}`",
        f"- `submission_scope`: `{summary.get('submission_scope', '')}`",
        f"- `ready_task_count`: `{int(summary.get('ready_task_count', 0))}`",
        f"- `blocked_task_count`: `{int(summary.get('blocked_task_count', 0))}`",
        f"- `review_boundary_pending_count`: `{int(summary.get('review_boundary_pending_count', 0))}`",
        f"- `review_boundary_resolution_label`: `{summary.get('review_boundary_resolution_label', '')}`",
        f"- `review_boundary_assignee_label`: `{summary.get('review_boundary_assignee_label', '') or 'none'}`",
        f"- `review_boundary_assignment_status_label`: `{summary.get('review_boundary_assignment_status_label', '') or 'none'}`",
        f"- `review_boundary_followup_action_label`: `{summary.get('review_boundary_followup_action_label', '') or 'none'}`",
        f"- `review_boundary_sla_state_label`: `{summary.get('review_boundary_sla_state_label', '') or 'none'}`",
        f"- `review_boundary_age_bucket_label`: `{summary.get('review_boundary_age_bucket_label', '') or 'none'}`",
        f"- `review_boundary_overdue_count`: `{int(summary.get('review_boundary_overdue_count', 0))}`",
        f"- `review_boundary_oldest_open_age_hours`: `{float(summary.get('review_boundary_oldest_open_age_hours', 0.0)):.3f}`",
        f"- `review_boundary_preview_approve_all`: `{str(review_preview.get('approve_all_reason_code', '') or '')}` | ready_full=`{bool(review_preview.get('approve_all_ready_full', False))}`",
        f"- `review_boundary_preview_reject_one`: `{str(review_preview.get('reject_one_reason_code', '') or '')}` | open_revision=`{int(review_preview.get('reject_one_open_revision_count', 0))}`",
        "",
        "## Ready Tasks",
        "",
    ]
    for row in payload.get("ready_tasks", []):
        lines.append(
            f"- `{row.get('task_id', '')}` | phase=`{row.get('phase', '')}` | "
            f"scope=`{row.get('submission_scope', '')}` | input=`{row.get('input_path', '')}`"
        )
    lines.extend(["", "## Blocked Tasks", ""])
    for row in payload.get("blocked_tasks", []):
        lines.append(
            f"- `{row.get('task_id', '')}` | blocker=`{row.get('blocker_reason', '')}` | "
            f"owner=`{row.get('owner', '')}` | action=`{row.get('required_action', '')}` | "
            f"assignee=`{row.get('assignee_name', '') or 'unassigned'}`/assignment=`{row.get('assignment_status', '') or 'unknown'}` | "
            f"followup=`{row.get('followup_action', '')}`/sla=`{row.get('sla_state', '')}`/age=`{row.get('age_bucket', '')}`/overdue=`{bool(row.get('overdue', False))}` | "
            f"approve_all=`{row.get('preview_if_all_closed_reason_code', '')}`/ready_full=`{bool(row.get('preview_if_all_closed_ready_full', False))}` | "
            f"reject_one=`{row.get('preview_if_rejected_reason_code', '')}`/open_revision=`{int(row.get('preview_if_rejected_open_revision_count', 0))}`"
        )
    return "\n".join(lines) + "\n"


def build_execution_manifest(
    kickoff: dict[str, Any],
    *,
    kickoff_path: str,
    audit_review_queue_manifest: dict[str, Any],
    audit_review_queue_manifest_path: str,
    audit_review_assignment_manifest: dict[str, Any] | None,
    audit_review_assignment_manifest_path: str,
    approve_all_preview: dict[str, Any],
    reject_one_preview: dict[str, Any],
    decision_runner_report: dict[str, Any],
    approve_all_preview_path: str,
    reject_one_preview_path: str,
    decision_runner_report_path: str,
) -> dict[str, Any]:
    summary = kickoff.get("summary") if isinstance(kickoff.get("summary"), dict) else {}
    review_boundary = (
        kickoff.get("review_boundary") if isinstance(kickoff.get("review_boundary"), dict) else {}
    )
    ready_to_start_now = bool(summary.get("ready_to_start_now", False))
    ready_to_start_full = bool(summary.get("ready_to_start_full_submission_now", False))
    recommended_start_mode = str(summary.get("recommended_start_mode", "") or "")
    submission_scope = str(summary.get("recommended_submission_scope", "") or "")

    review_boundary_preview = _build_review_boundary_preview_summary(
        approve_all_preview,
        reject_one_preview,
        decision_runner_report,
    )
    followup_row_map, followup_summary = _followup_row_map(
        audit_review_queue_manifest,
        audit_review_assignment_manifest,
    )

    if ready_to_start_full:
        execution_mode = "full"
    elif ready_to_start_now:
        execution_mode = "limited"
    else:
        execution_mode = "blocked"

    tasks: list[dict[str, Any]] = []
    for row in kickoff.get("wind_component_assets", []):
        if not isinstance(row, dict):
            continue
        tasks.append(
            {
                "task_id": f"wind::{str(row.get('benchmark_seed_id', '') or '')}",
                "phase": "component_wind",
                "benchmark_family": "tpu_raw_hffb_mapping",
                "submission_scope": "limited_external_benchmark",
                "execution_status": "ready" if ready_to_start_now else "blocked",
                "input_path": str(row.get("source_manifest_path", "") or ""),
                "source_origin_class": str(row.get("source_origin_class", "") or ""),
                "expected_signal_column_count": int(row.get("signal_column_count", 0) or 0),
                "holdout_split": str(row.get("holdout_split", "") or ""),
            }
        )
    for row in kickoff.get("hinge_component_assets", []):
        if not isinstance(row, dict):
            continue
        tasks.append(
            {
                "task_id": f"hinge::{str(row.get('seed_id', '') or '')}",
                "phase": "component_hinge",
                "benchmark_family": "peer_spd_column_hinge",
                "submission_scope": "limited_external_benchmark",
                "execution_status": "ready" if ready_to_start_now else "blocked",
                "input_path": str(row.get("fixture_path", "") or ""),
                "specimen_id": str(row.get("specimen_id", "") or ""),
                "point_count": int(row.get("point_count", 0) or 0),
                "holdout_split": str(row.get("holdout_split", "") or ""),
            }
        )
    for row in kickoff.get("system_benchmarks", []):
        if not isinstance(row, dict):
            continue
        tasks.append(
            {
                "task_id": f"system::{str(row.get('track_id', '') or '')}",
                "phase": "system_anchor",
                "benchmark_family": str(row.get("track_id", "") or ""),
                "submission_scope": "component_and_system_performance_benchmark",
                "execution_status": "ready_reference_anchor" if ready_to_start_now else "blocked",
                "input_path": str(row.get("report_path", "") or ""),
                "contract_pass": bool(row.get("contract_pass", False)),
                "case_count": int(row.get("case_count", 0) or 0),
            }
        )
    for row in review_boundary.get("pending_packets", []):
        if not isinstance(row, dict):
            continue
        packet_id = str(row.get("packet_id", "") or "")
        followup_row = followup_row_map.get(packet_id, {})
        tasks.append(
            {
                "task_id": f"review::{packet_id}",
                "phase": "review_boundary",
                "benchmark_family": str(row.get("action_family", "") or ""),
                "submission_scope": "final_external_submission_only",
                "execution_status": "blocked",
                "input_path": packet_id,
                "blocker_reason": "pending_review_boundary",
                "required_action": "close_review_packet",
                "owner": str(row.get("review_owner", "licensed_engineer") or "licensed_engineer"),
                "priority": str(row.get("review_priority", "") or ""),
                "change_count": int(row.get("change_count", 0) or 0),
                "followup_action": str(followup_row.get("followup_action", "") or ""),
                "followup_owner": str(followup_row.get("followup_owner", "") or ""),
                "assignee_name": str(
                    followup_row.get("assigned_reviewer_name", "") or "unassigned"
                ),
                "assignee_license_id": str(
                    followup_row.get("assigned_reviewer_license_id", "") or ""
                ),
                "assignment_status": str(
                    followup_row.get("assignment_status", "") or "unassigned"
                ),
                "sla_state": str(followup_row.get("sla_state", "") or ""),
                "age_bucket": str(followup_row.get("age_bucket", "") or ""),
                "overdue": bool(followup_row.get("overdue", False)),
                "age_hours": float(followup_row.get("age_hours", 0.0) or 0.0),
                "due_at_utc": str(followup_row.get("due_at_utc", "") or ""),
                "preview_if_all_closed_reason_code": str(
                    review_boundary_preview.get("approve_all_reason_code", "") or ""
                ),
                "preview_if_all_closed_ready_full": bool(
                    review_boundary_preview.get("approve_all_ready_full", False)
                ),
                "preview_if_all_closed_pending_count": int(
                    review_boundary_preview.get("approve_all_pending_count", 0) or 0
                ),
                "preview_if_rejected_reason_code": str(
                    review_boundary_preview.get("reject_one_reason_code", "") or ""
                ),
                "preview_if_rejected_open_revision_count": int(
                    review_boundary_preview.get("reject_one_open_revision_count", 0) or 0
                ),
                "resolution_path_if_rejected": "reopen_revision_cycle",
            }
        )

    review_boundary_rows = [
        row
        for row in tasks
        if str(row.get("phase", "") or "") == "review_boundary"
    ]
    review_boundary_change_count_total = int(
        sum(int(row.get("change_count", 0) or 0) for row in review_boundary_rows)
    )

    ready_tasks = [
        row for row in tasks if str(row.get("execution_status", "")).startswith("ready")
    ]
    blocked_tasks = [
        row for row in tasks if not str(row.get("execution_status", "")).startswith("ready")
    ]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(ready_to_start_now),
        "reason_code": "PASS_EXECUTION_MANIFEST_READY" if ready_to_start_now else "ERR_EXECUTION_START_BLOCKED",
        "summary": {
            "recommended_start_mode": recommended_start_mode,
            "submission_scope": submission_scope,
            "execution_mode": execution_mode,
            "ready_task_count": int(len(ready_tasks)),
            "blocked_task_count": int(len(blocked_tasks)),
            "review_boundary_pending_count": int(review_boundary.get("pending_packet_count", 0) or 0),
            "review_boundary_resolution_label": _build_review_boundary_resolution_label(
                review_boundary_preview
            ),
            "review_boundary_owner_label": _count_label(review_boundary_rows, "owner"),
            "review_boundary_assignee_label": _count_label(review_boundary_rows, "assignee_name"),
            "review_boundary_assignment_status_label": _count_label(
                review_boundary_rows, "assignment_status"
            ),
            "review_boundary_priority_label": _count_label(review_boundary_rows, "priority"),
            "review_boundary_family_label": _count_label(review_boundary_rows, "benchmark_family"),
            "review_boundary_change_count_total": review_boundary_change_count_total,
            "review_boundary_followup_action_label": str(
                followup_summary.get("audit_review_followup_action_label", "") or ""
            ),
            "review_boundary_sla_state_label": str(
                followup_summary.get("audit_review_followup_sla_state_label", "") or ""
            ),
            "review_boundary_age_bucket_label": str(
                followup_summary.get("audit_review_followup_age_bucket_label", "") or ""
            ),
            "review_boundary_overdue_count": int(
                followup_summary.get("audit_review_followup_overdue_item_count", 0) or 0
            ),
            "review_boundary_oldest_open_age_hours": float(
                followup_summary.get("audit_review_followup_oldest_open_age_hours", 0.0) or 0.0
            ),
            "review_boundary_oldest_open_packet_id": str(
                followup_summary.get("audit_review_followup_oldest_open_packet_id", "") or ""
            ),
        },
        "review_boundary_preview": review_boundary_preview,
        "ready_tasks": ready_tasks,
        "blocked_tasks": blocked_tasks,
        "artifacts": {
            "kickoff_package_json": kickoff_path,
            "audit_review_queue_manifest_json": audit_review_queue_manifest_path,
            "audit_review_assignment_manifest_json": audit_review_assignment_manifest_path,
            "approve_all_preview_json": approve_all_preview_path,
            "reject_one_preview_json": reject_one_preview_path,
            "decision_runner_report_json": decision_runner_report_path,
        },
    }


def build_hardest_external_execution_manifest(
    kickoff_report: dict[str, Any],
    *,
    kickoff_report_path: str,
    audit_review_queue_manifest: dict[str, Any],
    audit_review_queue_manifest_path: str,
    audit_review_assignment_manifest: dict[str, Any] | None,
    audit_review_assignment_manifest_path: str,
    approve_all_preview: dict[str, Any],
    reject_one_preview: dict[str, Any],
    decision_runner_report: dict[str, Any],
    approve_all_preview_path: str,
    reject_one_preview_path: str,
    decision_runner_report_path: str,
) -> dict[str, Any]:
    summary = _summary_dict(kickoff_report)
    review_boundary_preview = _build_review_boundary_preview_summary(
        approve_all_preview,
        reject_one_preview,
        decision_runner_report,
    )
    followup_row_map, followup_summary = _followup_row_map(
        audit_review_queue_manifest,
        audit_review_assignment_manifest,
    )

    ready_to_start_now = bool(summary.get("ready_to_start_now", kickoff_report.get("contract_pass", False)))
    ready_to_start_full = bool(summary.get("ready_to_start_full_submission_now", False))
    recommended_start_mode = str(summary.get("recommended_start_mode", "") or "")
    submission_scope = (
        "full_external_submission_package"
        if ready_to_start_full
        else "hardest_external_benchmark_program"
    )
    execution_mode = "full" if ready_to_start_full else "limited" if ready_to_start_now else "blocked"

    tasks: list[dict[str, Any]] = []
    for row in catalog_rows():
        tasks.append(
            {
                "task_id": f"hardest::{row['case_id']}",
                "case_id": str(row["case_id"]),
                "case_label": str(row["label"]),
                "phase": "hardest_case",
                "benchmark_family": str(row["benchmark_family"]),
                "hazard_family": str(row["hazard_family"]),
                "topology_family": str(row["topology_family"]),
                "load_path_family": str(row["load_path_family"]),
                "submission_scope": submission_scope,
                "execution_status": "ready" if ready_to_start_now else "blocked",
                "input_path": str(row["primary_report_path"]),
                "source_origin_class": "official_external_benchmark_fullcase",
                "primary_report_path": str(row["primary_report_path"]),
                "supporting_report_paths": dict(row.get("supporting_reports", {})),
                "kpi_specs": list(row.get("kpi_specs", [])),
            }
        )

    for row in audit_review_queue_manifest.get("audit_review_queue_items", []):
        if not isinstance(row, dict):
            continue
        packet_id = str(row.get("packet_id", "") or "")
        followup_row = followup_row_map.get(packet_id, {})
        tasks.append(
            {
                "task_id": f"review::{packet_id}",
                "phase": "review_boundary",
                "benchmark_family": str(row.get("action_family", "") or ""),
                "submission_scope": "final_external_submission_only",
                "execution_status": "blocked",
                "input_path": packet_id,
                "blocker_reason": "pending_review_boundary",
                "required_action": "close_review_packet",
                "owner": str(row.get("review_owner", "licensed_engineer") or "licensed_engineer"),
                "priority": str(row.get("review_priority", "") or ""),
                "change_count": int(row.get("change_count", 0) or 0),
                "followup_action": str(followup_row.get("followup_action", "") or ""),
                "followup_owner": str(followup_row.get("followup_owner", "") or ""),
                "assignee_name": str(followup_row.get("assigned_reviewer_name", "") or "unassigned"),
                "assignee_license_id": str(
                    followup_row.get("assigned_reviewer_license_id", "") or ""
                ),
                "assignment_status": str(followup_row.get("assignment_status", "") or "unassigned"),
                "sla_state": str(followup_row.get("sla_state", "") or ""),
                "age_bucket": str(followup_row.get("age_bucket", "") or ""),
                "overdue": bool(followup_row.get("overdue", False)),
                "age_hours": float(followup_row.get("age_hours", 0.0) or 0.0),
                "due_at_utc": str(followup_row.get("due_at_utc", "") or ""),
                "preview_if_all_closed_reason_code": str(
                    review_boundary_preview.get("approve_all_reason_code", "") or ""
                ),
                "preview_if_all_closed_ready_full": bool(
                    review_boundary_preview.get("approve_all_ready_full", False)
                ),
                "preview_if_all_closed_pending_count": int(
                    review_boundary_preview.get("approve_all_pending_count", 0) or 0
                ),
                "preview_if_rejected_reason_code": str(
                    review_boundary_preview.get("reject_one_reason_code", "") or ""
                ),
                "preview_if_rejected_open_revision_count": int(
                    review_boundary_preview.get("reject_one_open_revision_count", 0) or 0
                ),
                "resolution_path_if_rejected": "reopen_revision_cycle",
            }
        )

    review_boundary_rows = [
        row for row in tasks if str(row.get("phase", "") or "") == "review_boundary"
    ]
    ready_tasks = [
        row for row in tasks if str(row.get("execution_status", "")).startswith("ready")
    ]
    blocked_tasks = [
        row for row in tasks if not str(row.get("execution_status", "")).startswith("ready")
    ]
    review_boundary_change_count_total = int(
        sum(int(row.get("change_count", 0) or 0) for row in review_boundary_rows)
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(ready_to_start_now),
        "reason_code": "PASS_EXECUTION_MANIFEST_READY" if ready_to_start_now else "ERR_EXECUTION_START_BLOCKED",
        "summary": {
            "recommended_start_mode": recommended_start_mode,
            "submission_scope": submission_scope,
            "execution_mode": execution_mode,
            "case_task_count": 10,
            "ready_task_count": int(len(ready_tasks)),
            "blocked_task_count": int(len(blocked_tasks)),
            "review_boundary_pending_count": int(
                summary.get("review_pending_count", summary.get("audit_review_queue_pending_count", 0)) or 0
            ),
            "review_boundary_resolution_label": _build_review_boundary_resolution_label(
                review_boundary_preview
            ),
            "review_boundary_owner_label": _count_label(review_boundary_rows, "owner"),
            "review_boundary_assignee_label": _count_label(review_boundary_rows, "assignee_name"),
            "review_boundary_assignment_status_label": _count_label(
                review_boundary_rows, "assignment_status"
            ),
            "review_boundary_priority_label": _count_label(review_boundary_rows, "priority"),
            "review_boundary_family_label": _count_label(review_boundary_rows, "benchmark_family"),
            "review_boundary_change_count_total": review_boundary_change_count_total,
            "review_boundary_followup_action_label": str(
                followup_summary.get("audit_review_followup_action_label", "") or ""
            ),
            "review_boundary_sla_state_label": str(
                followup_summary.get("audit_review_followup_sla_state_label", "") or ""
            ),
            "review_boundary_age_bucket_label": str(
                followup_summary.get("audit_review_followup_age_bucket_label", "") or ""
            ),
            "review_boundary_overdue_count": int(
                followup_summary.get("audit_review_followup_overdue_item_count", 0) or 0
            ),
            "review_boundary_oldest_open_age_hours": float(
                followup_summary.get("audit_review_followup_oldest_open_age_hours", 0.0) or 0.0
            ),
            "review_boundary_oldest_open_packet_id": str(
                followup_summary.get("audit_review_followup_oldest_open_packet_id", "") or ""
            ),
            "full_submission_ready": ready_to_start_full,
        },
        "review_boundary_preview": review_boundary_preview,
        "ready_tasks": ready_tasks,
        "blocked_tasks": blocked_tasks,
        "artifacts": {
            "hardest_external_10case_kickoff_json": kickoff_report_path,
            "audit_review_queue_manifest_json": audit_review_queue_manifest_path,
            "audit_review_assignment_manifest_json": audit_review_assignment_manifest_path,
            "approve_all_preview_json": approve_all_preview_path,
            "reject_one_preview_json": reject_one_preview_path,
            "decision_runner_report_json": decision_runner_report_path,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kickoff-package", default=str(DEFAULT_KICKOFF_PACKAGE))
    parser.add_argument(
        "--hardest-external-10case-kickoff-report",
        default=str(DEFAULT_HARDEST_EXTERNAL_10CASE_KICKOFF_REPORT),
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--audit-review-queue-manifest", default=str(DEFAULT_AUDIT_REVIEW_QUEUE_MANIFEST))
    parser.add_argument(
        "--audit-review-assignment-manifest",
        default=str(DEFAULT_AUDIT_REVIEW_ASSIGNMENT_MANIFEST),
    )
    parser.add_argument("--approve-all-preview")
    parser.add_argument("--reject-one-preview")
    parser.add_argument("--decision-runner-report")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    audit_review_queue_manifest_path = Path(args.audit_review_queue_manifest)
    audit_review_assignment_manifest_path = Path(args.audit_review_assignment_manifest)
    approve_all_preview_path = Path(args.approve_all_preview) if args.approve_all_preview else out_dir / "external_benchmark_submission_readiness_preview.approve_all.json"
    reject_one_preview_path = Path(args.reject_one_preview) if args.reject_one_preview else out_dir / "external_benchmark_submission_readiness_preview.reject_one.json"
    decision_runner_report_path = Path(args.decision_runner_report) if args.decision_runner_report else out_dir / "audit_review_decision_batch_run_report.json"
    audit_review_queue_manifest = _load_json(audit_review_queue_manifest_path)
    audit_review_assignment_manifest = (
        _load_json(audit_review_assignment_manifest_path)
        if audit_review_assignment_manifest_path.exists()
        else {}
    )
    approve_all_preview = _load_json(approve_all_preview_path)
    reject_one_preview = _load_json(reject_one_preview_path)
    decision_runner_report = _load_json(decision_runner_report_path)
    hardest_kickoff_path = Path(args.hardest_external_10case_kickoff_report)
    hardest_kickoff_report = _load_json(hardest_kickoff_path)
    if isinstance(hardest_kickoff_report.get("cases"), list) or isinstance(hardest_kickoff_report.get("case_rows"), list):
        payload = build_hardest_external_execution_manifest(
            hardest_kickoff_report,
            kickoff_report_path=str(hardest_kickoff_path),
            audit_review_queue_manifest=audit_review_queue_manifest,
            audit_review_queue_manifest_path=str(audit_review_queue_manifest_path),
            audit_review_assignment_manifest=audit_review_assignment_manifest,
            audit_review_assignment_manifest_path=str(audit_review_assignment_manifest_path),
            approve_all_preview=approve_all_preview,
            reject_one_preview=reject_one_preview,
            decision_runner_report=decision_runner_report,
            approve_all_preview_path=str(approve_all_preview_path),
            reject_one_preview_path=str(reject_one_preview_path),
            decision_runner_report_path=str(decision_runner_report_path),
        )
    else:
        kickoff_path = Path(args.kickoff_package)
        kickoff = _load_json(kickoff_path)
        if not kickoff:
            raise SystemExit(f"invalid kickoff package: {kickoff_path}")
        payload = build_execution_manifest(
            kickoff,
            kickoff_path=str(kickoff_path),
            audit_review_queue_manifest=audit_review_queue_manifest,
            audit_review_queue_manifest_path=str(audit_review_queue_manifest_path),
            audit_review_assignment_manifest=audit_review_assignment_manifest,
            audit_review_assignment_manifest_path=str(audit_review_assignment_manifest_path),
            approve_all_preview=approve_all_preview,
            reject_one_preview=reject_one_preview,
            decision_runner_report=decision_runner_report,
            approve_all_preview_path=str(approve_all_preview_path),
            reject_one_preview_path=str(reject_one_preview_path),
            decision_runner_report_path=str(decision_runner_report_path),
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "external_benchmark_execution_manifest.json"
    md_path = out_dir / "external_benchmark_execution_manifest.md"
    _write_json(json_path, payload)
    md_path.write_text(_build_markdown(payload), encoding="utf-8")
    print(f"Wrote external benchmark execution manifest: {json_path}")


if __name__ == "__main__":
    main()
