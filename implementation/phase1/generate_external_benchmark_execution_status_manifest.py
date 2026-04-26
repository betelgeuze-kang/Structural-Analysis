from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_EXECUTION_MANIFEST = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json"
)
DEFAULT_UPDATES_JSON = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_updates.json"
)
DEFAULT_OUT_JSON = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json"
)

ALLOWED_READY_STATUSES = {"planned", "in_progress", "completed", "failed"}


def _release_surface_status_mode(
    *,
    executable_task_count: int,
    planned_task_count: int,
    in_progress_task_count: int,
    completed_task_count: int,
    failed_task_count: int,
) -> str:
    if failed_task_count > 0:
        return "failed_this_snapshot"
    if executable_task_count > 0 and completed_task_count >= executable_task_count:
        return "execution_complete_no_fail"
    if in_progress_task_count > 0 or completed_task_count > 0:
        return "execution_in_progress"
    if planned_task_count > 0:
        return "not_run_this_snapshot"
    return "blocked_only"


def _release_surface_status_label(status_mode: str) -> str:
    return status_mode.replace("_", " ")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_updates_by_task(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("updates") if isinstance(payload.get("updates"), list) else []
    updates: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        task_id = str(row.get("task_id", "") or "").strip()
        if not task_id:
            continue
        updates[task_id] = row
    return updates


def _status_mode(
    *,
    executable_task_count: int,
    planned_task_count: int,
    in_progress_task_count: int,
    completed_task_count: int,
    failed_task_count: int,
) -> str:
    if failed_task_count > 0:
        return "execution_failure_present"
    if executable_task_count > 0 and completed_task_count >= executable_task_count:
        return "execution_complete_no_fail"
    if in_progress_task_count > 0 or completed_task_count > 0:
        return "execution_in_progress"
    if planned_task_count > 0:
        return "planned_only"
    return "blocked_only"


def build_execution_status_manifest(
    execution_manifest: dict[str, Any],
    *,
    execution_manifest_path: str,
    updates_path: str,
    updates_by_task: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summary = execution_manifest.get("summary") if isinstance(execution_manifest.get("summary"), dict) else {}
    ready_tasks = execution_manifest.get("ready_tasks") if isinstance(execution_manifest.get("ready_tasks"), list) else []
    blocked_tasks = execution_manifest.get("blocked_tasks") if isinstance(execution_manifest.get("blocked_tasks"), list) else []

    tasks: list[dict[str, Any]] = []
    planned = in_progress = completed = failed = 0
    receipt_count = bundle_count = bundle_zip_count = 0

    for row in ready_tasks:
        if not isinstance(row, dict):
            continue
        task_id = str(row.get("task_id", "") or "")
        update = updates_by_task.get(task_id, {})
        lifecycle_status = str(update.get("lifecycle_status", "planned") or "planned")
        if lifecycle_status not in ALLOWED_READY_STATUSES:
            lifecycle_status = "planned"
        if lifecycle_status == "planned":
            planned += 1
        elif lifecycle_status == "in_progress":
            in_progress += 1
        elif lifecycle_status == "completed":
            completed += 1
        elif lifecycle_status == "failed":
            failed += 1
        kpi_receipt_path = str(update.get("kpi_receipt_path", "") or "")
        case_bundle_dir = str(update.get("case_bundle_dir", "") or "")
        case_bundle_zip_path = str(update.get("case_bundle_zip_path", "") or "")
        if kpi_receipt_path:
            receipt_count += 1
        if case_bundle_dir:
            bundle_count += 1
        if case_bundle_zip_path:
            bundle_zip_count += 1
        tasks.append(
            {
                **row,
                "lifecycle_status": lifecycle_status,
                "last_updated_at": str(update.get("updated_at", "") or ""),
                "execution_note": str(update.get("note", "") or ""),
                "artifact_path": str(update.get("artifact_path", "") or ""),
                "kpi_receipt_path": kpi_receipt_path,
                "case_bundle_dir": case_bundle_dir,
                "case_bundle_zip_path": case_bundle_zip_path,
                "bundle_id": str(update.get("bundle_id", "") or ""),
            }
        )

    blocked = 0
    for row in blocked_tasks:
        if not isinstance(row, dict):
            continue
        blocked += 1
        tasks.append(
            {
                **row,
                "lifecycle_status": "blocked_review_boundary",
                "last_updated_at": "",
                "execution_note": "",
                "artifact_path": "",
            }
        )

    executable_task_count = int(len([row for row in ready_tasks if isinstance(row, dict)]))
    finished_task_count = int(completed + failed)
    completion_ratio = float(completed / executable_task_count) if executable_task_count else 0.0
    release_surface_status_mode = _release_surface_status_mode(
        executable_task_count=executable_task_count,
        planned_task_count=planned,
        in_progress_task_count=in_progress,
        completed_task_count=completed,
        failed_task_count=failed,
    )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS_EXECUTION_STATUS_READY",
        "summary": {
            "execution_mode": str(summary.get("execution_mode", "") or ""),
            "status_mode": _status_mode(
                executable_task_count=executable_task_count,
                planned_task_count=planned,
                in_progress_task_count=in_progress,
                completed_task_count=completed,
                failed_task_count=failed,
            ),
            "executable_task_count": executable_task_count,
            "planned_task_count": int(planned),
            "in_progress_task_count": int(in_progress),
            "completed_task_count": int(completed),
            "failed_task_count": int(failed),
            "blocked_task_count": int(blocked),
            "finished_task_count": finished_task_count,
            "completion_ratio": completion_ratio,
            "release_surface_status_mode": release_surface_status_mode,
            "release_surface_status_label": _release_surface_status_label(
                release_surface_status_mode
            ),
            "release_surface_not_run_task_count": int(planned),
            "release_surface_failed_task_count": int(failed),
            "kpi_receipt_task_count": int(receipt_count),
            "case_bundle_dir_task_count": int(bundle_count),
            "case_bundle_zip_task_count": int(bundle_zip_count),
            "review_boundary_pending_count": int(summary.get("review_boundary_pending_count", 0) or 0),
            "review_boundary_resolution_label": str(
                summary.get("review_boundary_resolution_label", "") or ""
            ),
            "review_boundary_owner_label": str(summary.get("review_boundary_owner_label", "") or ""),
            "review_boundary_assignee_label": str(
                summary.get("review_boundary_assignee_label", "") or ""
            ),
            "review_boundary_assignment_status_label": str(
                summary.get("review_boundary_assignment_status_label", "") or ""
            ),
            "review_boundary_priority_label": str(
                summary.get("review_boundary_priority_label", "") or ""
            ),
            "review_boundary_family_label": str(summary.get("review_boundary_family_label", "") or ""),
            "review_boundary_change_count_total": int(
                summary.get("review_boundary_change_count_total", 0) or 0
            ),
            "review_boundary_followup_action_label": str(
                summary.get("review_boundary_followup_action_label", "") or ""
            ),
            "review_boundary_sla_state_label": str(
                summary.get("review_boundary_sla_state_label", "") or ""
            ),
            "review_boundary_age_bucket_label": str(
                summary.get("review_boundary_age_bucket_label", "") or ""
            ),
            "review_boundary_overdue_count": int(
                summary.get("review_boundary_overdue_count", 0) or 0
            ),
            "review_boundary_oldest_open_age_hours": float(
                summary.get("review_boundary_oldest_open_age_hours", 0.0) or 0.0
            ),
            "review_boundary_oldest_open_packet_id": str(
                summary.get("review_boundary_oldest_open_packet_id", "") or ""
            ),
        },
        "tasks": tasks,
        "artifacts": {
            "execution_manifest_json": execution_manifest_path,
            "updates_json": updates_path,
        },
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# External Benchmark Execution Status Manifest",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `execution_mode`: `{summary.get('execution_mode', '')}`",
        f"- `status_mode`: `{summary.get('status_mode', '')}`",
        f"- `release_surface_status_mode`: `{summary.get('release_surface_status_mode', '')}`",
        f"- `release_surface_status_label`: `{summary.get('release_surface_status_label', '')}`",
        (
            f"- `release_surface_status_counts`: "
            f"`not_run={int(summary.get('release_surface_not_run_task_count', 0))} | "
            f"failed={int(summary.get('release_surface_failed_task_count', 0))}`"
        ),
        f"- `executable_task_count`: `{int(summary.get('executable_task_count', 0))}`",
        f"- `planned_task_count`: `{int(summary.get('planned_task_count', 0))}`",
        f"- `in_progress_task_count`: `{int(summary.get('in_progress_task_count', 0))}`",
        f"- `completed_task_count`: `{int(summary.get('completed_task_count', 0))}`",
        f"- `failed_task_count`: `{int(summary.get('failed_task_count', 0))}`",
        f"- `blocked_task_count`: `{int(summary.get('blocked_task_count', 0))}`",
        f"- `kpi_receipt_task_count`: `{int(summary.get('kpi_receipt_task_count', 0))}`",
        f"- `case_bundle_dir_task_count`: `{int(summary.get('case_bundle_dir_task_count', 0))}`",
        f"- `case_bundle_zip_task_count`: `{int(summary.get('case_bundle_zip_task_count', 0))}`",
        f"- `review_boundary_pending_count`: `{int(summary.get('review_boundary_pending_count', 0))}`",
        f"- `completion_ratio`: `{float(summary.get('completion_ratio', 0.0)):.4f}`",
        "",
        "## Tasks",
        "",
    ]
    for row in payload.get("tasks", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row.get('task_id', '')}` | lifecycle=`{row.get('lifecycle_status', '')}` | "
            f"phase=`{row.get('phase', '')}` | note=`{row.get('execution_note', '')}` | "
            f"artifact=`{row.get('artifact_path', '')}` | "
            f"receipt=`{row.get('kpi_receipt_path', '')}` | bundle=`{row.get('case_bundle_zip_path', '')}`"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-manifest", default=str(DEFAULT_EXECUTION_MANIFEST))
    parser.add_argument("--updates-json", default=str(DEFAULT_UPDATES_JSON))
    parser.add_argument("--out", default=str(DEFAULT_OUT_JSON))
    args = parser.parse_args()

    execution_manifest_path = Path(args.execution_manifest)
    execution_manifest = _load_json(execution_manifest_path)
    if not execution_manifest:
        raise SystemExit(f"invalid execution manifest: {execution_manifest_path}")

    updates_path = Path(args.updates_json)
    updates_by_task = _load_updates_by_task(updates_path)
    payload = build_execution_status_manifest(
        execution_manifest,
        execution_manifest_path=str(execution_manifest_path),
        updates_path=str(updates_path),
        updates_by_task=updates_by_task,
    )

    out_path = Path(args.out)
    md_path = out_path.with_suffix(".md")
    _write_json(out_path, payload)
    md_path.write_text(_build_markdown(payload), encoding="utf-8")
    print(f"Wrote external benchmark execution status manifest: {out_path}")


if __name__ == "__main__":
    main()
