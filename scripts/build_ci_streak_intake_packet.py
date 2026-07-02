#!/usr/bin/env python3
"""Build an owner handoff packet for CI consecutive-pass release evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ci-streak-intake-packet.v1"
GITHUB_ACTIONS_SCHEMA_VERSION = "github-actions-ci-streak-evidence.v1"
DEFAULT_MANIFEST = Path("implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json")
DEFAULT_GITHUB_ACTIONS_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)
DEFAULT_SELF_HOSTED_RUNNER_STATUS = Path(
    "implementation/phase1/release_evidence/productization/github_actions_self_hosted_runner_status.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.md")
DEFAULT_PM_RELEASE_GATE_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_PRODUCT_READINESS_SNAPSHOT = Path("implementation/phase1/release_evidence/productization/product_readiness_snapshot.json")
DEFAULT_MAX_SOURCE_EVIDENCE_AGE_HOURS = 24 * 7


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _release_area_blocker_ids(lane_rows: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for row in lane_rows:
        lane = str(row.get("lane", ""))
        if lane == "pr" and row.get("threshold_pass") is not True:
            ids.append("pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing")
        if lane == "nightly" and row.get("threshold_pass") is not True:
            ids.append("pm_release::basic_ci::nightly_ci_30_consecutive_pass_evidence_missing")
    return _dedupe(ids)


def _manifest_lane(manifest: dict[str, Any], lane: str) -> dict[str, Any]:
    manifest_lanes = _as_dict(manifest.get("lanes"))
    return _as_dict(manifest_lanes.get(lane))


def _source_lane(
    *,
    lane: str,
    threshold: int,
    github_actions: dict[str, Any],
    source_file_present: bool,
    source_schema_pass: bool,
    source_freshness_pass: bool,
    source_threshold_match: bool,
    workflow_discovery_query_error: str,
) -> dict[str, Any]:
    github_lanes = _as_dict(github_actions.get("lanes"))
    github_lane = _as_dict(github_lanes.get(lane))
    source_lane_present = bool(github_lane)
    source_lane_threshold = _as_int(github_lane.get("threshold"), threshold)
    source_consecutive = _as_int(github_lane.get("consecutive_pass_count"))
    source_threshold_pass = github_lane.get("threshold_pass") is True
    query_error = str(github_lane.get("query_error", "") or "")
    workflow_registered = github_lane.get("workflow_registered") is True
    workflow_state = str(_as_dict(github_lane.get("registered_workflow")).get("state", "") or "")
    workflow_active = workflow_state == "active"
    local_workflow_present = github_lane.get("local_workflow_present") is True
    local_workflow_trigger_events = [
        str(item)
        for item in github_lane.get("local_workflow_trigger_events", [])
        if isinstance(item, str)
    ]
    local_workflow_runs_on = [
        str(item)
        for item in github_lane.get("local_workflow_runs_on", [])
        if isinstance(item, str)
    ]
    local_required_trigger_present = github_lane.get("local_required_trigger_present") is True
    local_pull_request_trigger_present = github_lane.get("local_pull_request_trigger_present") is True
    local_schedule_trigger_present = github_lane.get("local_schedule_trigger_present") is True
    local_workflow_dispatch_trigger_present = github_lane.get("local_workflow_dispatch_trigger_present") is True
    local_self_hosted_runner_default = github_lane.get("local_self_hosted_runner_default") is True
    local_github_hosted_runner_default = github_lane.get("local_github_hosted_runner_default") is True
    pull_request_run_source_present = (
        github_lane.get("pull_request_run_source_present") is True if lane == "pr" else None
    )
    run_count = _as_int(github_lane.get("run_count"))
    job_start_blockers = [
        row
        for row in github_lane.get("job_start_blockers", [])
        if isinstance(row, dict)
    ]
    blockers = [
        *(["github_actions_ci_streak_evidence_missing"] if not source_file_present else []),
        *(["github_actions_ci_streak_evidence_schema_invalid"] if source_file_present and not source_schema_pass else []),
        *(["github_actions_ci_streak_evidence_stale"] if source_file_present and not source_freshness_pass else []),
        *(["github_actions_ci_streak_evidence_threshold_mismatch"] if source_file_present and not source_threshold_match else []),
        *(["workflow_discovery_query_error"] if workflow_discovery_query_error else []),
        *(["github_actions_lane_missing"] if source_file_present and source_schema_pass and not source_lane_present else []),
        *(["github_actions_lane_threshold_mismatch"] if source_lane_present and source_lane_threshold != threshold else []),
        *(["github_actions_lane_threshold_not_pass"] if source_lane_present and not source_threshold_pass else []),
        *(["github_actions_lane_streak_below_threshold"] if source_lane_present and source_consecutive < threshold else []),
        *(["github_actions_workflow_not_registered"] if source_lane_present and not workflow_registered else []),
        *(
            ["github_actions_workflow_not_active"]
            if source_lane_present and workflow_registered and not workflow_active
            else []
        ),
        *(["github_actions_query_error"] if query_error else []),
        *(["pr_pull_request_run_source_absent"] if lane == "pr" and source_lane_present and not pull_request_run_source_present else []),
        *(["github_actions_filtered_run_count_below_threshold"] if source_lane_present and run_count < threshold else []),
        *(["local_workflow_uses_github_hosted_runner"] if source_lane_present and local_github_hosted_runner_default else []),
        *(
            ["local_self_hosted_runner_default_missing"]
            if source_lane_present and local_workflow_present and not local_self_hosted_runner_default
            else []
        ),
    ]
    source_release_credit_pass = not blockers
    return {
        "lane": lane,
        "threshold": threshold,
        "source_lane_present": source_lane_present,
        "source_threshold": source_lane_threshold if source_lane_present else None,
        "source_threshold_pass": source_threshold_pass,
        "source_consecutive_pass_count": source_consecutive,
        "source_run_count": run_count,
        "source_release_credit_pass": source_release_credit_pass,
        "job_start_blocker_count": len(job_start_blockers),
        "job_start_blockers": job_start_blockers,
        "workflow_registered": workflow_registered,
        "workflow_state": workflow_state,
        "workflow_active": workflow_active,
        "local_workflow_present": local_workflow_present,
        "local_workflow_trigger_events": local_workflow_trigger_events,
        "local_workflow_runs_on": local_workflow_runs_on,
        "local_self_hosted_runner_default": local_self_hosted_runner_default,
        "local_github_hosted_runner_default": local_github_hosted_runner_default,
        "local_required_trigger_present": local_required_trigger_present,
        "local_pull_request_trigger_present": local_pull_request_trigger_present,
        "local_schedule_trigger_present": local_schedule_trigger_present,
        "local_workflow_dispatch_trigger_present": local_workflow_dispatch_trigger_present,
        "query_error": query_error,
        "pull_request_run_source_present": pull_request_run_source_present,
        "blockers": blockers,
    }


def _source_evidence(
    *,
    path: Path,
    github_actions: dict[str, Any],
    threshold: int,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    source_file_present = path.exists()
    schema_version = str(github_actions.get("schema_version", ""))
    source_schema_pass = schema_version == GITHUB_ACTIONS_SCHEMA_VERSION
    source_threshold = _as_int(github_actions.get("threshold"), threshold)
    source_threshold_match = source_threshold == threshold
    generated_at = _parse_datetime(github_actions.get("generated_at"))
    age_hours = ((now - generated_at).total_seconds() / 3600) if generated_at else None
    freshness_pass = bool(age_hours is not None and 0 <= age_hours <= max_age_hours)
    workflow_discovery = _as_dict(github_actions.get("workflow_discovery"))
    workflow_discovery_query_error = str(workflow_discovery.get("query_error", "") or "")
    workflow_queue_backlog = [
        row
        for row in github_actions.get("workflow_queue_backlog", [])
        if isinstance(row, dict)
    ]
    lanes = {
        lane: _source_lane(
            lane=lane,
            threshold=threshold,
            github_actions=github_actions,
            source_file_present=source_file_present,
            source_schema_pass=source_schema_pass,
            source_freshness_pass=freshness_pass,
            source_threshold_match=source_threshold_match,
            workflow_discovery_query_error=workflow_discovery_query_error,
        )
        for lane in ("pr", "nightly")
    }
    blockers = [
        *(["github_actions_ci_streak_evidence_missing"] if not source_file_present else []),
        *(["github_actions_ci_streak_evidence_schema_invalid"] if source_file_present and not source_schema_pass else []),
        *(["github_actions_ci_streak_evidence_generated_at_missing_or_invalid"] if source_file_present and generated_at is None else []),
        *(["github_actions_ci_streak_evidence_stale"] if source_file_present and generated_at and not freshness_pass else []),
        *(["github_actions_ci_streak_evidence_threshold_mismatch"] if source_file_present and not source_threshold_match else []),
        *(["workflow_discovery_query_error"] if workflow_discovery_query_error else []),
        *(f"{lane}:{blocker}" for lane, row in lanes.items() for blocker in row["blockers"]),
    ]
    return {
        "path": str(path),
        "present": source_file_present,
        "schema_version": schema_version,
        "schema_version_expected": GITHUB_ACTIONS_SCHEMA_VERSION,
        "schema_pass": source_schema_pass,
        "threshold": threshold,
        "source_threshold": source_threshold,
        "threshold_match": source_threshold_match,
        "generated_at": generated_at.isoformat() if generated_at else "",
        "age_hours": round(age_hours, 3) if age_hours is not None else None,
        "max_age_hours": max_age_hours,
        "freshness_pass": freshness_pass,
        "workflow_discovery_query_error": workflow_discovery_query_error,
        "workflow_queue_backlog": workflow_queue_backlog,
        "lanes": lanes,
        "contract_pass": not blockers,
        "blockers": _dedupe(blockers),
    }


def _runner_precondition(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "evaluated": False,
            "path": "",
            "present": False,
            "contract_pass": True,
            "status": "not_evaluated",
            "blockers": [],
            "required_labels": [],
            "matching_runner_count": 0,
            "online_matching_runner_count": 0,
            "ready_runner_count": 0,
            "owner_action": "",
        }
    payload = _load_json(path)
    present = bool(payload)
    blockers = [str(item) for item in payload.get("blockers", []) if str(item)]
    required_labels = [
        str(item) for item in payload.get("required_labels", []) if str(item)
    ]
    contract_pass = bool(present and payload.get("contract_pass") is True)
    online_count = _as_int(payload.get("online_matching_runner_count"))
    matching_count = _as_int(payload.get("matching_runner_count"))
    ready_count = _as_int(payload.get("ready_runner_count"))
    if contract_pass:
        owner_action = "No runner recovery action required; at least one required self-hosted runner is online."
    else:
        labels = ", ".join(required_labels) or "required self-hosted runner labels"
        owner_action = (
            "Bring at least one GitHub Actions self-hosted runner online with labels "
            f"{labels}, then refresh github_actions_self_hosted_runner_status.json and "
            "github_actions_ci_streak_evidence.json before collecting the 30-run streak."
        )
    return {
        "evaluated": True,
        "path": str(path),
        "present": present,
        "schema_version": str(payload.get("schema_version", "")),
        "contract_pass": contract_pass,
        "status": str(payload.get("status", "missing") or "missing"),
        "blockers": blockers if present else ["self_hosted_runner_status_missing"],
        "required_labels": required_labels,
        "matching_runner_count": matching_count,
        "online_matching_runner_count": online_count,
        "ready_runner_count": ready_count,
        "owner_action": owner_action,
        "claim_boundary": str(payload.get("claim_boundary", "")),
    }


def _lane_row(lane: str, manifest: dict[str, Any], source_evidence: dict[str, Any]) -> dict[str, Any]:
    manifest_lane = _manifest_lane(manifest, lane)
    source_lane = _as_dict(_as_dict(source_evidence.get("lanes")).get(lane))
    threshold = _as_int(manifest_lane.get("threshold"), _as_int(manifest.get("threshold"), 30))
    manifest_consecutive = _as_int(manifest_lane.get("consecutive_pass_count"))
    source_consecutive = _as_int(source_lane.get("source_consecutive_pass_count"))
    source_credit_pass = source_lane.get("source_release_credit_pass") is True
    source_observation_usable = bool(
        source_evidence.get("present") is True
        and source_evidence.get("schema_pass") is True
        and source_evidence.get("freshness_pass") is True
        and source_evidence.get("threshold_match") is True
        and source_lane.get("source_lane_present") is True
    )
    consecutive = source_consecutive if source_observation_usable else 0
    missing = max(0, threshold - consecutive)
    manifest_threshold_pass = manifest_lane.get("threshold_pass") is True
    threshold_pass = bool(manifest_threshold_pass and source_credit_pass and consecutive >= threshold)
    blockers = [str(item) for item in manifest_lane.get("blockers", []) if isinstance(item, str)]
    blockers.extend(str(item) for item in source_lane.get("blockers", []) if isinstance(item, str))
    job_start_blockers = [
        row
        for row in source_lane.get("job_start_blockers", [])
        if isinstance(row, dict)
    ]
    if not threshold_pass and not blockers:
        blockers = [f"{lane}_ci_{threshold}_consecutive_pass_evidence_missing"]
    return {
        "lane": lane,
        "threshold": threshold,
        "manifest_threshold_pass": manifest_threshold_pass,
        "manifest_consecutive_pass_count": manifest_consecutive,
        "threshold_pass": threshold_pass,
        "consecutive_pass_count": consecutive,
        "missing_consecutive_pass_count": missing,
        "local_consecutive_pass_count": _as_int(manifest_lane.get("local_consecutive_pass_count")),
        "github_actions_consecutive_pass_count": source_consecutive,
        "source_observation_usable": source_observation_usable,
        "github_actions_threshold_pass": source_lane.get("source_threshold_pass") is True,
        "github_actions_workflow_registered": source_lane.get(
            "workflow_registered",
            manifest_lane.get("github_actions_workflow_registered"),
        ),
        "github_actions_workflow_state": str(source_lane.get("workflow_state", "")),
        "github_actions_workflow_active": source_lane.get("workflow_active") is True,
        "local_workflow_present": bool(source_lane.get("local_workflow_present", False)),
        "local_workflow_trigger_events": [
            str(item)
            for item in source_lane.get("local_workflow_trigger_events", [])
            if isinstance(item, str)
        ],
        "local_required_trigger_present": source_lane.get("local_required_trigger_present") is True,
        "local_pull_request_trigger_present": source_lane.get("local_pull_request_trigger_present") is True,
        "local_schedule_trigger_present": source_lane.get("local_schedule_trigger_present") is True,
        "local_workflow_dispatch_trigger_present": source_lane.get("local_workflow_dispatch_trigger_present") is True,
        "github_actions_query_error": str(source_lane.get("query_error", "") or manifest_lane.get("github_actions_query_error", "")),
        "github_actions_queried_run_count": _as_int(manifest_lane.get("github_actions_queried_run_count")),
        "github_actions_filtered_run_count": _as_int(
            source_lane.get("source_run_count", manifest_lane.get("github_actions_filtered_run_count"))
        ),
        "pull_request_run_source_present": source_lane.get(
            "pull_request_run_source_present",
            manifest_lane.get("pull_request_run_source_present"),
        ),
        "github_actions_ignored_event_names": [
            str(item)
            for item in manifest_lane.get("github_actions_ignored_event_names", [])
            if isinstance(item, str)
        ],
        "source_evidence_release_credit_pass": source_credit_pass,
        "source_evidence_blockers": [str(item) for item in source_lane.get("blockers", []) if isinstance(item, str)],
        "job_start_blocker_count": len(job_start_blockers),
        "job_start_blockers": job_start_blockers,
        "streak_source": str(manifest_lane.get("streak_source", "")),
        "owner_action": str(manifest_lane.get("owner_action", "")),
        "claim_boundary": str(manifest_lane.get("claim_boundary", "")),
        "blockers": _dedupe(blockers),
    }


def _job_start_blocker_queue(lane_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in lane_rows:
        blockers = [
            blocker
            for blocker in row.get("job_start_blockers", [])
            if isinstance(blocker, dict)
        ]
        if not blockers:
            continue
        reason_codes = sorted(
            {
                str(blocker.get("reason_code", "") or "")
                for blocker in blockers
                if str(blocker.get("reason_code", "") or "")
            }
        )
        first = blockers[0]
        queue.append(
            {
                "lane": row["lane"],
                "status": "external_runner_recovery_required",
                "job_start_blocker_count": len(blockers),
                "reason_codes": reason_codes,
                "first_run_id": first.get("run_id"),
                "first_run_url": str(first.get("url", "") or ""),
                "first_head_sha": str(first.get("head_sha", "") or ""),
                "first_head_branch": str(first.get("head_branch", "") or ""),
                "first_queued_minutes": first.get("queued_minutes"),
                "first_message": str(first.get("message", "") or ""),
                "sample_blockers": blockers[:5],
                "owner_action": (
                    f"Resolve the {row['lane']} GitHub Actions job-start blocker, "
                    "bring the required self-hosted runner online, rerun the workflow, "
                    f"then collect {row['threshold']} consecutive successful run(s)."
                ),
            }
        )
    return queue


def _workflow_queue_backlog(source_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in source_evidence.get("workflow_queue_backlog", []):
        if not isinstance(row, dict):
            continue
        queue.append(
            {
                "lane": str(row.get("lane", "") or ""),
                "workflow": str(row.get("workflow", "") or ""),
                "status": "external_runner_recovery_required",
                "reason_code": str(row.get("reason_code", "") or ""),
                "run_id": row.get("run_id"),
                "run_url": str(row.get("url", "") or ""),
                "event": str(row.get("event", "") or ""),
                "head_sha": str(row.get("head_sha", "") or ""),
                "head_branch": str(row.get("head_branch", "") or ""),
                "queued_minutes": row.get("queued_minutes"),
                "message": str(row.get("message", "") or ""),
                "owner_action": (
                    "Bring the required self-hosted runner online, let queued "
                    f"{row.get('workflow', 'workflow')} runs start, then refresh "
                    "github_actions_ci_streak_evidence.json before collecting release streak credit."
                ),
            }
        )
    return queue


def _first_lane(lane_rows: list[dict[str, Any]], lane: str) -> dict[str, Any]:
    for row in lane_rows:
        if row.get("lane") == lane:
            return row
    return {}


def _check_row(
    *,
    field: str,
    current_value: Any,
    required_value: str,
    closure_check: str,
    closure_check_pass: bool,
    owner_note: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "current_value": current_value,
        "required_value": required_value,
        "closure_check": closure_check,
        "closure_check_pass": bool(closure_check_pass),
        "owner_note": owner_note,
    }


def _required_fields(
    *,
    lane_rows: list[dict[str, Any]],
    source_evidence: dict[str, Any],
    threshold: int,
    max_source_evidence_age_hours: float,
) -> list[dict[str, Any]]:
    pr = _first_lane(lane_rows, "pr")
    nightly = _first_lane(lane_rows, "nightly")
    source_lanes = _as_dict(source_evidence.get("lanes"))
    pr_source = _as_dict(source_lanes.get("pr"))
    nightly_source = _as_dict(source_lanes.get("nightly"))
    return [
        _check_row(
            field="github_actions_ci_streak_evidence.schema_version",
            current_value=source_evidence.get("schema_version", ""),
            required_value=GITHUB_ACTIONS_SCHEMA_VERSION,
            closure_check="source_schema_pass",
            closure_check_pass=source_evidence.get("schema_pass") is True,
            owner_note=(
                "CI streak release credit must come from the GitHub Actions streak evidence schema."
            ),
        ),
        _check_row(
            field="github_actions_ci_streak_evidence.generated_at",
            current_value=source_evidence.get("generated_at", ""),
            required_value=f"timezone-aware timestamp no older than {max_source_evidence_age_hours:g} hours",
            closure_check="source_freshness_pass",
            closure_check_pass=source_evidence.get("freshness_pass") is True,
            owner_note=(
                "Stale CI evidence cannot close release freshness or PM release-area gates."
            ),
        ),
        _check_row(
            field="github_actions_ci_streak_evidence.threshold",
            current_value=source_evidence.get("source_threshold"),
            required_value=str(threshold),
            closure_check="source_threshold_match",
            closure_check_pass=source_evidence.get("threshold_match") is True,
            owner_note="Source evidence threshold must match the release contract.",
        ),
        _check_row(
            field="lanes.pr.consecutive_pass_count",
            current_value=pr.get("consecutive_pass_count", 0),
            required_value=f">= {threshold}",
            closure_check="pr_consecutive_pass_count_pass",
            closure_check_pass=_as_int(pr.get("consecutive_pass_count")) >= threshold,
            owner_note="PR release streak credit requires tracked pull_request run evidence.",
        ),
        _check_row(
            field="lanes.pr.threshold_pass",
            current_value=pr.get("threshold_pass", False),
            required_value="true",
            closure_check="pr_threshold_pass",
            closure_check_pass=pr.get("threshold_pass") is True,
            owner_note="Manifest and source evidence must both accept the PR streak.",
        ),
        _check_row(
            field="lanes.pr.pull_request_run_source_present",
            current_value=pr.get("pull_request_run_source_present"),
            required_value="true",
            closure_check="pr_pull_request_run_source_pass",
            closure_check_pass=pr.get("pull_request_run_source_present") is True,
            owner_note="Push-only workflow runs cannot satisfy the PR release-area gate.",
        ),
        _check_row(
            field="lanes.pr.workflow_registered_active",
            current_value=(
                f"registered={pr.get('github_actions_workflow_registered')}; "
                f"state={pr.get('github_actions_workflow_state', '')}"
            ),
            required_value="registered=true and state=active",
            closure_check="pr_workflow_active_pass",
            closure_check_pass=(
                pr.get("github_actions_workflow_registered") is True
                and pr.get("github_actions_workflow_active") is True
            ),
            owner_note="The counted PR workflow must be registered and active in GitHub Actions.",
        ),
        _check_row(
            field="lanes.nightly.consecutive_pass_count",
            current_value=nightly.get("consecutive_pass_count", 0),
            required_value=f">= {threshold}",
            closure_check="nightly_consecutive_pass_count_pass",
            closure_check_pass=_as_int(nightly.get("consecutive_pass_count")) >= threshold,
            owner_note="Nightly release streak credit requires tracked scheduled/nightly evidence.",
        ),
        _check_row(
            field="lanes.nightly.threshold_pass",
            current_value=nightly.get("threshold_pass", False),
            required_value="true",
            closure_check="nightly_threshold_pass",
            closure_check_pass=nightly.get("threshold_pass") is True,
            owner_note="Manifest and source evidence must both accept the nightly streak.",
        ),
        _check_row(
            field="lanes.nightly.workflow_registered_active",
            current_value=(
                f"registered={nightly.get('github_actions_workflow_registered')}; "
                f"state={nightly.get('github_actions_workflow_state', '')}"
            ),
            required_value="registered=true and state=active",
            closure_check="nightly_workflow_active_pass",
            closure_check_pass=(
                nightly.get("github_actions_workflow_registered") is True
                and nightly.get("github_actions_workflow_active") is True
            ),
            owner_note=(
                "The counted nightly workflow must be registered and active in GitHub Actions."
            ),
        ),
        _check_row(
            field="lanes.nightly.schedule_or_dispatch_trigger_present",
            current_value=nightly.get("local_workflow_trigger_events", []),
            required_value="schedule or workflow_dispatch trigger present",
            closure_check="nightly_required_trigger_pass",
            closure_check_pass=(
                nightly.get("local_schedule_trigger_present") is True
                or nightly.get("local_workflow_dispatch_trigger_present") is True
            ),
            owner_note="Nightly evidence must come from the nightly/scheduled lane, not ad hoc local artifacts.",
        ),
        _check_row(
            field="lanes.pr.local_self_hosted_runner_default",
            current_value=pr_source.get("local_self_hosted_runner_default"),
            required_value="true",
            closure_check="pr_self_hosted_runner_default_pass",
            closure_check_pass=pr_source.get("local_self_hosted_runner_default") is True,
            owner_note="The PR workflow must keep the required self-hosted runner default.",
        ),
        _check_row(
            field="lanes.nightly.local_self_hosted_runner_default",
            current_value=nightly_source.get("local_self_hosted_runner_default"),
            required_value="true",
            closure_check="nightly_self_hosted_runner_default_pass",
            closure_check_pass=nightly_source.get("local_self_hosted_runner_default") is True,
            owner_note="The nightly workflow must keep the required self-hosted runner default.",
        ),
    ]


def _derived_checks(
    *,
    lane_rows: list[dict[str, Any]],
    source_evidence: dict[str, Any],
    runner_precondition: dict[str, Any],
    release_area_blocker_ids: list[str],
    job_start_queue: list[dict[str, Any]],
    threshold: int,
) -> list[dict[str, Any]]:
    pr = _first_lane(lane_rows, "pr")
    nightly = _first_lane(lane_rows, "nightly")
    source_lanes = _as_dict(source_evidence.get("lanes"))
    pr_source = _as_dict(source_lanes.get("pr"))
    nightly_source = _as_dict(source_lanes.get("nightly"))
    github_hosted_runner_defaults = bool(
        pr_source.get("local_github_hosted_runner_default")
        or nightly_source.get("local_github_hosted_runner_default")
    )
    runner_pass = (
        runner_precondition.get("contract_pass") is True
        if runner_precondition.get("evaluated") is True
        else True
    )
    return [
        _check_row(
            field="source_manifest_threshold_consistency",
            current_value=(
                f"source={source_evidence.get('source_threshold')}; "
                f"required={threshold}"
            ),
            required_value="source threshold equals release threshold",
            closure_check="source_threshold_match",
            closure_check_pass=source_evidence.get("threshold_match") is True,
            owner_note="The source evidence and release manifest must agree on the 30-run threshold.",
        ),
        _check_row(
            field="source_evidence_freshness",
            current_value=f"age_hours={source_evidence.get('age_hours')}",
            required_value="freshness_pass=true",
            closure_check="source_freshness_pass",
            closure_check_pass=source_evidence.get("freshness_pass") is True,
            owner_note="Refresh GitHub Actions streak evidence immediately before release signoff.",
        ),
        _check_row(
            field="pr_trigger_and_source",
            current_value=(
                f"triggers={pr.get('local_workflow_trigger_events', [])}; "
                f"pull_request_source={pr.get('pull_request_run_source_present')}"
            ),
            required_value="pull_request trigger and pull_request source runs present",
            closure_check="pr_trigger_source_pass",
            closure_check_pass=(
                pr.get("local_pull_request_trigger_present") is True
                and pr.get("pull_request_run_source_present") is True
            ),
            owner_note="The PR lane must prove PR-triggered runs, not only pushes to a branch.",
        ),
        _check_row(
            field="nightly_trigger_source",
            current_value=f"triggers={nightly.get('local_workflow_trigger_events', [])}",
            required_value="schedule or workflow_dispatch trigger present",
            closure_check="nightly_trigger_pass",
            closure_check_pass=(
                nightly.get("local_schedule_trigger_present") is True
                or nightly.get("local_workflow_dispatch_trigger_present") is True
            ),
            owner_note="The nightly lane must remain a real nightly/scheduled release lane.",
        ),
        _check_row(
            field="self_hosted_runner_precondition",
            current_value=(
                f"evaluated={runner_precondition.get('evaluated')}; "
                f"online={runner_precondition.get('online_matching_runner_count')}; "
                f"ready={runner_precondition.get('ready_runner_count')}"
            ),
            required_value="at least one required self-hosted runner online when evaluated",
            closure_check="self_hosted_runner_precondition_pass",
            closure_check_pass=runner_pass,
            owner_note="Queued self-hosted runs cannot accumulate a 30-run release streak.",
        ),
        _check_row(
            field="github_hosted_runner_defaults_absent",
            current_value=github_hosted_runner_defaults,
            required_value="false",
            closure_check="github_hosted_runner_default_absent_pass",
            closure_check_pass=not github_hosted_runner_defaults,
            owner_note="Do not close this gate by moving the release streak to a different runner class.",
        ),
        _check_row(
            field="job_start_blockers_absent",
            current_value=sum(
                _as_int(row.get("job_start_blocker_count")) for row in lane_rows
            ),
            required_value="0",
            closure_check="job_start_blockers_absent_pass",
            closure_check_pass=not job_start_queue,
            owner_note="Queued/job-start-blocked runs must be resolved before the streak can start.",
        ),
        _check_row(
            field="release_area_blockers_absent",
            current_value=release_area_blocker_ids,
            required_value="[]",
            closure_check="release_area_blockers_absent_pass",
            closure_check_pass=not release_area_blocker_ids,
            owner_note="The PM basic_ci release area closes only after both PR and nightly lane blockers disappear.",
        ),
    ]


def _gate_unblock_plan(
    *,
    lane_rows: list[dict[str, Any]],
    runner_precondition: dict[str, Any],
    job_start_queue: list[dict[str, Any]],
    validation_commands: list[str],
    contract_pass: bool,
) -> list[dict[str, Any]]:
    if contract_pass:
        return []
    pr = _first_lane(lane_rows, "pr")
    nightly = _first_lane(lane_rows, "nightly")
    plan: list[dict[str, Any]] = []
    if runner_precondition.get("evaluated") is True and runner_precondition.get("contract_pass") is not True:
        plan.append(
            {
                "slot_id": "restore_self_hosted_runner_precondition",
                "owner": "release_infrastructure_owner",
                "required_artifact": str(DEFAULT_SELF_HOSTED_RUNNER_STATUS),
                "minimum_evidence": [
                    "at least one GitHub Actions runner has the required labels",
                    "matching runner is online",
                    "github_actions_self_hosted_runner_status.json contract_pass=true",
                ],
                "required_labels": runner_precondition.get("required_labels", []),
            }
        )
    if job_start_queue:
        plan.append(
            {
                "slot_id": "resolve_github_actions_job_start_blockers",
                "owner": "release_infrastructure_owner",
                "minimum_evidence": [
                    "queued PR and nightly workflow runs start instead of remaining queued",
                    "job_start_blocker_count is zero for both release lanes",
                    "workflow_queue_backlog is empty or unrelated to counted release lanes",
                ],
                "blocked_lanes": [row["lane"] for row in job_start_queue],
            }
        )
    for row in (pr, nightly):
        if row.get("threshold_pass") is True:
            continue
        lane = str(row.get("lane", ""))
        plan.append(
            {
                "slot_id": f"collect_{lane}_30_consecutive_passes",
                "owner": "release_engineering",
                "lane": lane,
                "required_artifact": str(DEFAULT_GITHUB_ACTIONS_EVIDENCE),
                "current_consecutive_pass_count": row.get("consecutive_pass_count", 0),
                "required_consecutive_pass_count": row.get("threshold", 30),
                "remaining_consecutive_pass_count": row.get(
                    "missing_consecutive_pass_count",
                    30,
                ),
                "minimum_evidence": [
                    f"{lane} GitHub Actions lane threshold_pass=true",
                    f"{lane} consecutive_pass_count >= {row.get('threshold', 30)}",
                    f"{lane} lane has no query, job-start, runner, or source blockers",
                ],
            }
        )
    plan.append(
        {
            "slot_id": "refresh_ci_streak_source_evidence",
            "owner": "release_engineering",
            "required_artifacts": [
                str(DEFAULT_GITHUB_ACTIONS_EVIDENCE),
                str(DEFAULT_MANIFEST),
                str(DEFAULT_OUT),
            ],
            "minimum_evidence": [
                "github_actions_ci_streak_evidence.json schema and freshness pass",
                "ci_consecutive_pass_manifest.json agrees with source threshold",
                "ci_streak_intake_packet.json contract_pass=true",
            ],
            "validation_commands": validation_commands[:4],
        }
    )
    plan.append(
        {
            "slot_id": "regenerate_release_gate_evidence",
            "owner": "release_engineering",
            "minimum_evidence": [
                "PM release basic_ci area no longer blocks PR CI streak evidence",
                "PM release basic_ci area no longer blocks nightly CI streak evidence",
                "product_readiness_snapshot remains source-state consistent",
            ],
            "validation_commands": validation_commands[4:],
        }
    )
    return plan


def build_packet(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    github_actions_evidence_path: Path = DEFAULT_GITHUB_ACTIONS_EVIDENCE,
    runner_status_path: Path | None = None,
    now: datetime | None = None,
    max_source_evidence_age_hours: float = DEFAULT_MAX_SOURCE_EVIDENCE_AGE_HOURS,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    manifest = _load_json(manifest_path)
    github_actions = _load_json(github_actions_evidence_path)
    threshold = _as_int(manifest.get("threshold"), 30)
    source_evidence = _source_evidence(
        path=github_actions_evidence_path,
        github_actions=github_actions,
        threshold=threshold,
        now=now,
        max_age_hours=max_source_evidence_age_hours,
    )
    runner_precondition = _runner_precondition(runner_status_path)
    lane_rows = [
        _lane_row("pr", manifest, source_evidence),
        _lane_row("nightly", manifest, source_evidence),
    ]
    job_start_queue = _job_start_blocker_queue(lane_rows)
    workflow_backlog_queue = _workflow_queue_backlog(source_evidence)
    blockers = [
        f"{row['lane']}:{blocker}"
        for row in lane_rows
        for blocker in row["blockers"]
        if not row["threshold_pass"]
    ]
    runner_blockers = [
        f"runner:{blocker}"
        for blocker in runner_precondition["blockers"]
        if runner_precondition["evaluated"] and not runner_precondition["contract_pass"]
    ]
    blockers.extend(runner_blockers)
    contract_pass = bool(manifest.get("contract_pass") is True and source_evidence["contract_pass"] and not blockers)
    source_blockers = [str(item) for item in source_evidence["blockers"]]
    lane_pass_count = sum(1 for row in lane_rows if row["threshold_pass"])
    pr_missing = next(row["missing_consecutive_pass_count"] for row in lane_rows if row["lane"] == "pr")
    nightly_missing = next(
        row["missing_consecutive_pass_count"] for row in lane_rows if row["lane"] == "nightly"
    )
    runner_status = str(runner_precondition["status"])
    release_area_blocker_ids = _release_area_blocker_ids(lane_rows)
    blocker_ids = _dedupe(
        [
            *release_area_blocker_ids,
            *[f"ci_streak::{blocker}" for blocker in blockers],
        ]
    )
    evidence_intake_artifacts = _dedupe(
        [
            str(manifest_path),
            str(github_actions_evidence_path),
            *(
                [str(runner_status_path)]
                if runner_status_path is not None
                else []
            ),
            str(DEFAULT_OUT),
            str(DEFAULT_PM_RELEASE_GATE_REPORT),
            str(DEFAULT_PRODUCT_READINESS_SNAPSHOT),
        ]
    )
    validation_commands = [
        f"python3 scripts/check_github_actions_self_hosted_runner_status.py --out {DEFAULT_SELF_HOSTED_RUNNER_STATUS}",
        f"python3 scripts/build_github_actions_ci_streak_evidence.py --out {DEFAULT_GITHUB_ACTIONS_EVIDENCE}",
        f"python3 scripts/build_ci_consecutive_pass_manifest.py --out {DEFAULT_MANIFEST}",
        f"python3 scripts/build_ci_streak_intake_packet.py --out {DEFAULT_OUT}",
        "python3 scripts/report_pm_release_gate.py "
        " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
        " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        "python3 scripts/build_pm_release_blocker_action_register.py "
        " --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
        " --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
    ]
    ci_evidence_policy = {
        "required_lanes": ["pr", "nightly"],
        "required_consecutive_pass_count": threshold,
        "accepted_source": (
            "tracked GitHub Actions PR and nightly consecutive-pass evidence"
        ),
        "rejected_substitutes": [
            "local PR or nightly gate artifacts counted as release streak credit",
            "manifest-only consecutive-pass claims without source evidence",
            "queued/job-start-blocked workflow runs",
            "github-hosted runner defaults when self-hosted labels are required",
        ],
        "closure_rule": (
            "The PM basic_ci release area closes only when both PR and nightly "
            "GitHub Actions lanes have fresh, tracked 30-consecutive-pass evidence "
            "from the required runner class."
        ),
    }
    required_fields = _required_fields(
        lane_rows=lane_rows,
        source_evidence=source_evidence,
        threshold=threshold,
        max_source_evidence_age_hours=max_source_evidence_age_hours,
    )
    derived_checks = _derived_checks(
        lane_rows=lane_rows,
        source_evidence=source_evidence,
        runner_precondition=runner_precondition,
        release_area_blocker_ids=release_area_blocker_ids,
        job_start_queue=job_start_queue,
        threshold=threshold,
    )
    gate_unblock_plan = _gate_unblock_plan(
        lane_rows=lane_rows,
        runner_precondition=runner_precondition,
        job_start_queue=job_start_queue,
        validation_commands=validation_commands,
        contract_pass=contract_pass,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "release_area": "basic_ci",
        "release_area_blocker_ids": release_area_blocker_ids,
        "blocker_ids": blocker_ids,
        "blocker_id_count": len(blocker_ids),
        "evidence_intake_artifacts": evidence_intake_artifacts,
        "evidence_intake_artifact_count": len(evidence_intake_artifacts),
        "ci_release_credit_policy": ci_evidence_policy,
        "ci_evidence_policy": ci_evidence_policy,
        "streak_requirements": {
            "required_lanes": ["pr", "nightly"],
            "required_consecutive_pass_count": threshold,
            "required_lane_count": 2,
            "release_area": "basic_ci",
            "source_schema_version": GITHUB_ACTIONS_SCHEMA_VERSION,
            "max_source_evidence_age_hours": max_source_evidence_age_hours,
            "runner_class": "self-hosted linux x64",
        },
        "required_fields": required_fields,
        "required_field_count": len(required_fields),
        "required_field_pass_count": sum(
            1 for row in required_fields if row["closure_check_pass"] is True
        ),
        "derived_checks": derived_checks,
        "derived_check_count": len(derived_checks),
        "derived_check_pass_count": sum(
            1 for row in derived_checks if row["closure_check_pass"] is True
        ),
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "reason_code": (
            "PASS"
            if contract_pass
            else "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE"
            if source_blockers
            else "ERR_CI_STREAK_EVIDENCE_INCOMPLETE"
        ),
        "summary_line": (
            f"CI streak intake: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"lanes={lane_pass_count}/{len(lane_rows)} | "
            f"pr_missing={pr_missing} | nightly_missing={nightly_missing} | "
            f"blockers={len(blockers)} | runner={runner_status}"
        ),
        "ci_consecutive_pass_manifest": str(manifest_path),
        "github_actions_ci_streak_evidence": str(github_actions_evidence_path),
        "source_evidence": source_evidence,
        "runner_precondition": runner_precondition,
        "summary": {
            "threshold": threshold,
            "lane_count": len(lane_rows),
            "lane_pass_count": lane_pass_count,
            "open_blocker_count": len(blockers),
            "source_evidence_pass": source_evidence["contract_pass"],
            "runner_precondition_evaluated": runner_precondition["evaluated"],
            "runner_precondition_pass": runner_precondition["contract_pass"],
            "runner_status": runner_precondition["status"],
            "runner_required_labels": runner_precondition["required_labels"],
            "runner_matching_runner_count": runner_precondition["matching_runner_count"],
            "runner_online_matching_runner_count": runner_precondition["online_matching_runner_count"],
            "runner_ready_runner_count": runner_precondition["ready_runner_count"],
            "runner_owner_action": runner_precondition["owner_action"],
            "job_start_blocker_lane_count": len(job_start_queue),
            "job_start_blocker_count": sum(
                row["job_start_blocker_count"] for row in job_start_queue
            ),
            "workflow_queue_backlog_count": len(workflow_backlog_queue),
            "workflow_queue_backlog_lane_count": len(
                {row["lane"] for row in workflow_backlog_queue if row["lane"]}
            ),
            "release_area_blocker_count": len(release_area_blocker_ids),
            "blocker_id_count": len(blocker_ids),
            "evidence_intake_artifact_count": len(evidence_intake_artifacts),
            "source_evidence_generated_at": source_evidence["generated_at"],
            "source_evidence_age_hours": source_evidence["age_hours"],
            "source_evidence_freshness_pass": source_evidence["freshness_pass"],
            "source_evidence_schema_pass": source_evidence["schema_pass"],
            "pr_missing_consecutive_pass_count": next(
                row["missing_consecutive_pass_count"] for row in lane_rows if row["lane"] == "pr"
            ),
            "nightly_missing_consecutive_pass_count": next(
                row["missing_consecutive_pass_count"] for row in lane_rows if row["lane"] == "nightly"
            ),
            "pr_github_actions_workflow_registered": next(
                row["github_actions_workflow_registered"] for row in lane_rows if row["lane"] == "pr"
            ),
            "pr_github_actions_workflow_state": next(
                row["github_actions_workflow_state"] for row in lane_rows if row["lane"] == "pr"
            ),
            "pr_source_threshold_pass": next(
                row["source_evidence_release_credit_pass"] for row in lane_rows if row["lane"] == "pr"
            ),
            "pr_pull_request_run_source_present": next(
                row["pull_request_run_source_present"] for row in lane_rows if row["lane"] == "pr"
            ),
            "nightly_github_actions_workflow_registered": next(
                row["github_actions_workflow_registered"] for row in lane_rows if row["lane"] == "nightly"
            ),
            "nightly_github_actions_workflow_state": next(
                row["github_actions_workflow_state"] for row in lane_rows if row["lane"] == "nightly"
            ),
            "nightly_source_threshold_pass": next(
                row["source_evidence_release_credit_pass"] for row in lane_rows if row["lane"] == "nightly"
            ),
            "nightly_local_workflow_present": next(
                row["local_workflow_present"] for row in lane_rows if row["lane"] == "nightly"
            ),
            "pr_local_required_trigger_present": next(
                row["local_required_trigger_present"] for row in lane_rows if row["lane"] == "pr"
            ),
            "nightly_local_required_trigger_present": next(
                row["local_required_trigger_present"] for row in lane_rows if row["lane"] == "nightly"
            ),
        },
        "lane_rows": lane_rows,
        "job_start_blocker_queue": job_start_queue,
        "first_job_start_blocker": job_start_queue[0] if job_start_queue else {},
        "workflow_queue_backlog": workflow_backlog_queue,
        "first_workflow_queue_backlog": workflow_backlog_queue[0] if workflow_backlog_queue else {},
        "current_blockers": blockers,
        "current_blocker_count": len(blockers),
        "validation_commands": validation_commands,
        "claim_boundary": (
            "This packet is an owner handoff checklist for CI streak evidence. It independently re-verifies "
            "github_actions_ci_streak_evidence.json and does not convert local gate artifacts or manifest-only "
            "claims into release streak credit; PR and nightly release credit still require tracked "
            "consecutive-pass GitHub Actions evidence for the configured release window."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CI Streak Intake Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `release_area`: `{payload['release_area']}`",
        f"- `current_blocker_count`: `{payload['current_blocker_count']}`",
        f"- `blocker_id_count`: `{payload['blocker_id_count']}`",
        f"- `evidence_intake_artifact_count`: `{payload['evidence_intake_artifact_count']}`",
        f"- `ci_consecutive_pass_manifest`: `{payload['ci_consecutive_pass_manifest']}`",
        f"- `github_actions_ci_streak_evidence`: `{payload['github_actions_ci_streak_evidence']}`",
        "",
        "| Lane | Observed Streak | Missing | Source | Workflow Registered | Pass | Owner Action |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for row in payload["lane_rows"]:
        lines.append(
            f"| `{row['lane']}` | `{row['consecutive_pass_count']}/{row['threshold']}` | "
            f"`{row['missing_consecutive_pass_count']}` | `{row['streak_source']}` | "
            f"`{row['github_actions_workflow_registered']}` | `{row['threshold_pass']}` | "
            f"{row['owner_action']} |"
        )
    runner = payload["runner_precondition"]
    if runner["evaluated"]:
        lines.extend(
            [
                "",
                "## Runner Precondition",
                "",
                "| Path | Status | Online Matching | Ready | Pass | Owner Action |",
                "|---|---|---:|---:|---:|---|",
                (
                    f"| `{runner['path']}` | `{runner['status']}` | "
                    f"`{runner['online_matching_runner_count']}/{runner['matching_runner_count']}` | "
                    f"`{runner['ready_runner_count']}` | `{runner['contract_pass']}` | "
                    f"{runner['owner_action']} |"
                ),
            ]
        )
    if payload.get("job_start_blocker_queue"):
        lines.extend(
            [
                "",
                "## Job Start Blocker Queue",
                "",
                "| Lane | Count | Reason Codes | First Run | Owner Action |",
                "|---|---:|---|---|---|",
            ]
        )
        for row in payload["job_start_blocker_queue"]:
            lines.append(
                f"| `{row['lane']}` | `{row['job_start_blocker_count']}` | "
                f"`{', '.join(row['reason_codes'])}` | "
                f"`{row['first_run_id']}` | {row['owner_action']} |"
            )
    if payload.get("workflow_queue_backlog"):
        lines.extend(
            [
                "",
                "## Workflow Queue Backlog",
                "",
                "| Workflow | Event | Counted Lane | Queued Minutes | Run | Owner Action |",
                "|---|---|---|---:|---|---|",
            ]
        )
        for row in payload["workflow_queue_backlog"]:
            lines.append(
                f"| `{row['workflow']}` | `{row['event']}` | `{row['lane']}` | "
                f"`{row['queued_minutes']}` | `{row['run_id']}` | {row['owner_action']} |"
            )
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Blocker IDs", ""])
    if payload["blocker_ids"]:
        lines.extend(f"- `{item}`" for item in payload["blocker_ids"])
    else:
        lines.append("- none")
    lines.extend(["", "## Evidence Intake Artifacts", ""])
    for artifact in payload["evidence_intake_artifacts"]:
        lines.append(f"- `{artifact}`")
    requirements = payload.get("streak_requirements")
    requirements = requirements if isinstance(requirements, dict) else {}
    lines.extend(["", "## Streak Requirements", ""])
    for key in (
        "required_lanes",
        "required_consecutive_pass_count",
        "source_schema_version",
        "max_source_evidence_age_hours",
        "runner_class",
    ):
        lines.append(f"- `{key}`: `{requirements.get(key, '')}`")
    lines.extend(["", "## Required Fields", ""])
    lines.append("| Field | Current | Required | Pass |")
    lines.append("|---|---|---|---:|")
    for row in payload.get("required_fields", []):
        lines.append(
            f"| `{row.get('field', '')}` | `{row.get('current_value', '')}` | "
            f"`{row.get('required_value', '')}` | `{row.get('closure_check_pass')}` |"
        )
    lines.extend(["", "## Derived Checks", ""])
    lines.append("| Check | Current | Required | Pass |")
    lines.append("|---|---|---|---:|")
    for row in payload.get("derived_checks", []):
        lines.append(
            f"| `{row.get('field', '')}` | `{row.get('current_value', '')}` | "
            f"`{row.get('required_value', '')}` | `{row.get('closure_check_pass')}` |"
        )
    lines.extend(["", "## Gate Unblock Plan", ""])
    if payload.get("gate_unblock_plan"):
        for row in payload["gate_unblock_plan"]:
            lines.append(f"- `{row.get('slot_id', '')}`")
    else:
        lines.append("- none")
    policy = payload.get("ci_release_credit_policy")
    policy = policy if isinstance(policy, dict) else {}
    lines.extend(["", "## CI Release Credit Policy", ""])
    lines.append(f"- `accepted_source`: `{policy.get('accepted_source', '')}`")
    lines.append(
        "- `required_consecutive_pass_count`: "
        f"`{policy.get('required_consecutive_pass_count', '')}`"
    )
    lines.append("- rejected substitutes:")
    for item in policy.get("rejected_substitutes", []):
        lines.append(f"  - {item}")
    lines.extend(
        [
            "",
            "## Source Evidence",
            "",
            "| Path | Schema | Fresh | Age Hours | Pass |",
            "|---|---|---:|---:|---:|",
            (
                f"| `{payload['source_evidence']['path']}` | `{payload['source_evidence']['schema_version']}` | "
                f"`{payload['source_evidence']['freshness_pass']}` | "
                f"`{payload['source_evidence']['age_hours']}` | `{payload['source_evidence']['contract_pass']}` |"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--github-actions-evidence", type=Path, default=DEFAULT_GITHUB_ACTIONS_EVIDENCE)
    parser.add_argument("--runner-status", type=Path, default=DEFAULT_SELF_HOSTED_RUNNER_STATUS)
    parser.add_argument("--max-source-evidence-age-hours", type=float, default=DEFAULT_MAX_SOURCE_EVIDENCE_AGE_HOURS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(
        manifest_path=args.manifest,
        github_actions_evidence_path=args.github_actions_evidence,
        runner_status_path=args.runner_status,
        max_source_evidence_age_hours=args.max_source_evidence_age_hours,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
