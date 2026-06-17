#!/usr/bin/env python3
"""Collect GitHub Actions CI pass-streak evidence for PM release gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA_VERSION = "github-actions-ci-streak-evidence.v1"
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json")
DEFAULT_REPO = "betelgeuze-kang/Structural-Analysis"
DEFAULT_LOCAL_WORKFLOW_DIR = Path(".github/workflows")
GH_FIELDS = "databaseId,event,conclusion,status,headSha,headBranch,createdAt,updatedAt,url,name"
GH_DEBUG_LINE = re.compile(r"^\* Request(?:\s|$)")
KNOWN_GITHUB_TRIGGER_EVENTS = frozenset(
    (
        "branch_protection_rule",
        "check_run",
        "check_suite",
        "create",
        "delete",
        "deployment",
        "deployment_status",
        "discussion",
        "discussion_comment",
        "fork",
        "gollum",
        "issue_comment",
        "issues",
        "label",
        "merge_group",
        "milestone",
        "page_build",
        "project",
        "project_card",
        "project_column",
        "public",
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "pull_request_target",
        "push",
        "registry_package",
        "release",
        "repository_dispatch",
        "schedule",
        "status",
        "watch",
        "workflow_call",
        "workflow_dispatch",
        "workflow_run",
    )
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GH_DEBUG", None)
    return env


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_gh_message(message: str) -> str:
    lines = [
        line.strip()
        for line in message.splitlines()
        if line.strip() and not GH_DEBUG_LINE.match(line.strip())
    ]
    return "\n".join(lines) or "gh command failed"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _run_gh_list(*, repo: str, workflow: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    cmd = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow,
        "--limit",
        str(limit),
        "--json",
        GH_FIELDS,
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True, env=_gh_env())
    if completed.returncode != 0:
        message = _clean_gh_message(completed.stderr or completed.stdout or "gh run list failed")
        return [], message
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return [], f"gh run list returned invalid JSON: {exc}"
    rows = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    return rows, ""


def _run_gh_workflows(*, repo: str) -> tuple[list[dict[str, Any]], str]:
    completed = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/workflows?per_page=100"],
        check=False,
        capture_output=True,
        text=True,
        env=_gh_env(),
    )
    if completed.returncode != 0:
        return [], _clean_gh_message(completed.stderr or completed.stdout or "gh workflow discovery failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return [], f"gh workflow discovery returned invalid JSON: {exc}"
    rows = payload.get("workflows") if isinstance(payload, dict) else []
    return [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "path": row.get("path"),
            "state": row.get("state"),
        }
        for row in rows
        if isinstance(row, dict)
    ], ""


def _strip_yaml_key(value: str) -> str:
    return value.strip().strip("\"'")


def _parse_inline_yaml_events(value: str) -> set[str]:
    value = value.strip()
    if not value:
        return set()
    if value.startswith("[") and value.endswith("]"):
        tokens = [_strip_yaml_key(token) for token in value[1:-1].split(",")]
    else:
        tokens = [_strip_yaml_key(value)]
    return {token for token in tokens if token in KNOWN_GITHUB_TRIGGER_EVENTS}


def _workflow_trigger_events(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    events: set[str] = set()
    in_on_block = False
    on_indent = 0
    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if "#" in stripped:
            stripped = stripped.split("#", 1)[0].rstrip()
        if not in_on_block:
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            if _strip_yaml_key(key) != "on":
                continue
            on_indent = indent
            inline_events = _parse_inline_yaml_events(value)
            if inline_events:
                events.update(inline_events)
                in_on_block = False
            else:
                in_on_block = True
            continue
        if indent <= on_indent:
            in_on_block = False
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            if _strip_yaml_key(key) == "on":
                inline_events = _parse_inline_yaml_events(value)
                if inline_events:
                    events.update(inline_events)
                else:
                    in_on_block = True
                    on_indent = indent
            continue
        if stripped.startswith("-"):
            event = _strip_yaml_key(stripped[1:].strip())
            if event in KNOWN_GITHUB_TRIGGER_EVENTS:
                events.add(event)
            continue
        if ":" in stripped:
            key = _strip_yaml_key(stripped.split(":", 1)[0])
            if key in KNOWN_GITHUB_TRIGGER_EVENTS:
                events.add(key)
    return sorted(events)


def _local_workflows(workflow_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not workflow_dir.exists():
        return rows
    for path in sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]):
        name = ""
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("name:"):
                    name = stripped.split(":", 1)[1].strip().strip("\"'")
                    break
        except Exception:
            name = ""
        trigger_events = _workflow_trigger_events(path)
        rows.append(
            {
                "name": name,
                "path": path.as_posix(),
                "exists": path.exists(),
                "trigger_events": trigger_events,
                "pull_request_trigger_present": "pull_request" in trigger_events,
                "schedule_trigger_present": "schedule" in trigger_events,
                "workflow_dispatch_trigger_present": "workflow_dispatch" in trigger_events,
            }
        )
    return rows


def _workflow_match(workflows: list[dict[str, Any]], workflow: str) -> dict[str, Any]:
    workflow_text = workflow.strip().lower()
    for row in workflows:
        name = str(row.get("name", "") or "").strip().lower()
        path = str(row.get("path", "") or "").strip().lower()
        if name == workflow_text or path.endswith(workflow_text):
            return row
    return {}


def _local_trigger_status(lane: str, local_workflow: dict[str, Any]) -> dict[str, Any]:
    local_trigger_events = [
        str(item)
        for item in local_workflow.get("trigger_events", [])
        if isinstance(item, str)
    ]
    local_pull_request_trigger_present = "pull_request" in local_trigger_events
    local_schedule_trigger_present = "schedule" in local_trigger_events
    local_workflow_dispatch_trigger_present = "workflow_dispatch" in local_trigger_events
    if lane == "pr":
        local_required_trigger_present = local_pull_request_trigger_present
    else:
        local_required_trigger_present = bool(
            local_schedule_trigger_present or local_workflow_dispatch_trigger_present
        )
    return {
        "local_workflow_trigger_events": sorted(local_trigger_events),
        "local_required_trigger_present": local_required_trigger_present,
        "local_pull_request_trigger_present": local_pull_request_trigger_present,
        "local_schedule_trigger_present": local_schedule_trigger_present,
        "local_workflow_dispatch_trigger_present": local_workflow_dispatch_trigger_present,
    }


def _is_pass(row: dict[str, Any]) -> bool:
    return str(row.get("status", "")).lower() == "completed" and str(row.get("conclusion", "")).lower() == "success"


def _lane_from_rows(
    *,
    lane: str,
    workflow: str,
    rows: list[dict[str, Any]],
    allowed_events: set[str],
    threshold: int,
    registered_workflows: list[dict[str, Any]],
    local_workflows: list[dict[str, Any]],
    error: str = "",
) -> dict[str, Any]:
    error = _clean_gh_message(error) if error else ""
    registered_workflow = _workflow_match(registered_workflows, workflow)
    local_workflow = _workflow_match(local_workflows, workflow)
    local_trigger_status = _local_trigger_status(lane, local_workflow)
    relevant = [
        {
            "run_id": row.get("databaseId"),
            "event": row.get("event"),
            "workflow": row.get("name", workflow),
            "head_branch": row.get("headBranch"),
            "head_sha": row.get("headSha"),
            "status": row.get("status"),
            "conclusion": row.get("conclusion"),
            "created_at": row.get("createdAt"),
            "updated_at": row.get("updatedAt"),
            "url": row.get("url"),
            "pass": _is_pass(row),
        }
        for row in sorted(rows, key=lambda item: str(item.get("createdAt", "")), reverse=True)
        if str(row.get("event", "")).lower() in allowed_events
    ]
    ignored_event_names = sorted(
        {
            str(row.get("event", "") or "")
            for row in rows
            if str(row.get("event", "")).lower() not in allowed_events
        }
    )
    pull_request_run_source_present = True
    if lane == "pr":
        pull_request_run_source_present = bool(relevant)
    consecutive = 0
    for row in relevant:
        if not row["pass"]:
            break
        consecutive += 1
    blockers = []
    if error:
        blockers.append("github_actions_query_failed")
    if registered_workflows and not registered_workflow:
        blockers.append("github_actions_workflow_not_registered")
    if lane == "pr" and registered_workflow and rows and not pull_request_run_source_present:
        blockers.append("pr_pull_request_run_source_absent")
    if consecutive < threshold:
        blockers.append(f"{lane}_github_actions_{threshold}_consecutive_pass_evidence_missing")
    return {
        "lane": lane,
        "workflow": workflow,
        "workflow_registered": bool(registered_workflow),
        "registered_workflow": registered_workflow,
        "local_workflow_present": bool(local_workflow),
        "local_workflow": local_workflow,
        **local_trigger_status,
        "allowed_events": sorted(allowed_events),
        "threshold": threshold,
        "query_error": error,
        "queried_run_count": len(rows),
        "run_count": len(relevant),
        "ignored_event_count": max(0, len(rows) - len(relevant)),
        "ignored_event_names": ignored_event_names,
        "pull_request_run_source_present": pull_request_run_source_present,
        "pass_count": sum(1 for row in relevant if row["pass"]),
        "consecutive_pass_count": consecutive,
        "threshold_pass": consecutive >= threshold,
        "blockers": blockers,
        "rows": relevant,
    }


def build_evidence(
    *,
    repo: str,
    threshold: int,
    limit: int,
    pr_workflow: str,
    nightly_workflow: str,
    pr_rows: list[dict[str, Any]] | None = None,
    nightly_rows: list[dict[str, Any]] | None = None,
    pr_error: str = "",
    nightly_error: str = "",
    registered_workflows: list[dict[str, Any]] | None = None,
    workflow_discovery_error: str = "",
    local_workflows: list[dict[str, Any]] | None = None,
    local_workflow_dir: Path = DEFAULT_LOCAL_WORKFLOW_DIR,
) -> dict[str, Any]:
    if registered_workflows is None:
        registered_workflows, workflow_discovery_error = _run_gh_workflows(repo=repo)
    if local_workflows is None:
        local_workflows = _local_workflows(local_workflow_dir)
    if pr_rows is None:
        pr_rows, pr_error = _run_gh_list(repo=repo, workflow=pr_workflow, limit=limit)
    if nightly_rows is None:
        nightly_rows, nightly_error = _run_gh_list(repo=repo, workflow=nightly_workflow, limit=limit)
    lanes = {
        "pr": _lane_from_rows(
            lane="pr",
            workflow=pr_workflow,
            rows=pr_rows,
            allowed_events={"pull_request"},
            threshold=threshold,
            registered_workflows=registered_workflows,
            local_workflows=local_workflows,
            error=pr_error,
        ),
        "nightly": _lane_from_rows(
            lane="nightly",
            workflow=nightly_workflow,
            rows=nightly_rows,
            allowed_events={"schedule", "workflow_dispatch"},
            threshold=threshold,
            registered_workflows=registered_workflows,
            local_workflows=local_workflows,
            error=nightly_error,
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "repo": repo,
        "threshold": threshold,
        "limit": limit,
        "workflow_discovery": {
            "query_error": workflow_discovery_error,
            "registered_workflow_count": len(registered_workflows),
            "registered_workflows": registered_workflows,
            "local_workflow_count": len(local_workflows),
            "local_workflows": local_workflows,
        },
        "contract_pass": all(lane["threshold_pass"] for lane in lanes.values()),
        "reason_code": "PASS" if all(lane["threshold_pass"] for lane in lanes.values()) else "ERR_CI_STREAK_INCOMPLETE",
        "lanes": lanes,
        "summary": {
            "pr_consecutive_pass_count": lanes["pr"]["consecutive_pass_count"],
            "pr_pull_request_run_source_present": lanes["pr"]["pull_request_run_source_present"],
            "nightly_consecutive_pass_count": lanes["nightly"]["consecutive_pass_count"],
            "pr_threshold_pass": lanes["pr"]["threshold_pass"],
            "nightly_threshold_pass": lanes["nightly"]["threshold_pass"],
            "pr_workflow_registered": lanes["pr"]["workflow_registered"],
            "nightly_workflow_registered": lanes["nightly"]["workflow_registered"],
            "nightly_local_workflow_present": lanes["nightly"]["local_workflow_present"],
            "pr_local_required_trigger_present": lanes["pr"]["local_required_trigger_present"],
            "nightly_local_required_trigger_present": lanes["nightly"]["local_required_trigger_present"],
        },
        "claim_boundary": (
            "GitHub Actions evidence is read-only run history from gh run list; PR lane only counts "
            "pull_request events and nightly lane only counts schedule/workflow_dispatch events."
        ),
    }


def refresh_local_workflow_metadata(
    *,
    existing_evidence_path: Path = DEFAULT_OUT,
    local_workflow_dir: Path = DEFAULT_LOCAL_WORKFLOW_DIR,
) -> dict[str, Any]:
    payload = _load_json(existing_evidence_path)
    if not payload:
        return build_evidence(
            repo=DEFAULT_REPO,
            threshold=30,
            limit=100,
            pr_workflow="CI",
            nightly_workflow="Nightly Full Quality",
            registered_workflows=[],
            pr_rows=[],
            nightly_rows=[],
            local_workflow_dir=local_workflow_dir,
        )
    local_workflows = _local_workflows(local_workflow_dir)
    workflow_discovery = payload.get("workflow_discovery")
    if not isinstance(workflow_discovery, dict):
        workflow_discovery = {}
    workflow_discovery["local_workflow_count"] = len(local_workflows)
    workflow_discovery["local_workflows"] = local_workflows
    workflow_discovery["local_workflow_metadata_generated_at"] = _now_utc_iso()
    payload["workflow_discovery"] = workflow_discovery
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        lanes = {}
    for lane, default_workflow in (("pr", "CI"), ("nightly", "Nightly Full Quality")):
        lane_payload = lanes.get(lane)
        if not isinstance(lane_payload, dict):
            continue
        workflow = str(lane_payload.get("workflow", "") or default_workflow)
        local_workflow = _workflow_match(local_workflows, workflow)
        lane_payload["local_workflow_present"] = bool(local_workflow)
        lane_payload["local_workflow"] = local_workflow
        lane_payload.update(_local_trigger_status(lane, local_workflow))
        lanes[lane] = lane_payload
    payload["lanes"] = lanes
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    summary["pr_local_required_trigger_present"] = bool(
        _as_dict(lanes.get("pr")).get("local_required_trigger_present")
    )
    summary["nightly_local_required_trigger_present"] = bool(
        _as_dict(lanes.get("nightly")).get("local_required_trigger_present")
    )
    payload["summary"] = summary
    payload["claim_boundary"] = (
        str(payload.get("claim_boundary", "")).rstrip()
        + " Local workflow trigger metadata is parsed from the current checkout and does not refresh "
        "or replace GitHub Actions run-history evidence."
    ).strip()
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--threshold", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pr-workflow", default="CI")
    parser.add_argument("--nightly-workflow", default="Nightly Full Quality")
    parser.add_argument("--local-workflow-dir", type=Path, default=DEFAULT_LOCAL_WORKFLOW_DIR)
    parser.add_argument(
        "--local-metadata-only",
        action="store_true",
        help="Refresh only local workflow trigger metadata in an existing evidence file.",
    )
    parser.add_argument("--existing-evidence", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.local_metadata_only:
        payload = refresh_local_workflow_metadata(
            existing_evidence_path=args.existing_evidence,
            local_workflow_dir=args.local_workflow_dir,
        )
    else:
        payload = build_evidence(
            repo=args.repo,
            threshold=args.threshold,
            limit=args.limit,
            pr_workflow=args.pr_workflow,
            nightly_workflow=args.nightly_workflow,
            local_workflow_dir=args.local_workflow_dir,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
