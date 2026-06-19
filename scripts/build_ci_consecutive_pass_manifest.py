#!/usr/bin/env python3
"""Build a CI pass-streak manifest from local PR/nightly gate artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json")
DEFAULT_PR_REPORTS = [
    Path("implementation/phase1/ci_gate_report.pr.json"),
    Path("implementation/phase1/ci_gate_report.pr_recheck.json"),
]
DEFAULT_NIGHTLY_REPORTS = [
    Path("implementation/phase1/ci_gate_report.nightly.json"),
]
DEFAULT_NIGHTLY_GLOB_ROOT = Path("implementation/phase1/release")
DEFAULT_GITHUB_ACTIONS_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _github_lane_streak(payload: dict[str, Any], lane: str) -> int:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return 0
    lane_payload = lanes.get(lane)
    if not isinstance(lane_payload, dict):
        return 0
    try:
        return int(lane_payload.get("consecutive_pass_count", 0) or 0)
    except Exception:
        return 0


def _github_lane_payload(payload: dict[str, Any], lane: str) -> dict[str, Any]:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return {}
    lane_payload = lanes.get(lane)
    return lane_payload if isinstance(lane_payload, dict) else {}


def _lane_owner_action(
    label: str,
    threshold: int,
    consecutive: int,
    *,
    github_workflow_registered: bool | None = None,
    github_query_error: str = "",
    github_job_start_blocked: bool = False,
    local_workflow_present: bool = False,
    github_queried_run_count: int = 0,
    github_filtered_run_count: int = 0,
) -> str:
    if consecutive >= threshold:
        return "No release action required; consecutive pass threshold is satisfied."
    missing = max(0, threshold - consecutive)
    if github_job_start_blocked:
        return (
            f"Resolve the {label} GitHub Actions job-start blocker shown in "
            "github_actions_ci_streak_evidence.json, rerun the workflow, and then collect "
            f"{missing} additional consecutive successful CI run(s) before release signoff."
        )
    if github_workflow_registered is False:
        local_hint = " Local workflow file is present, so merge/register it in GitHub Actions first." if local_workflow_present else ""
        return (
            f"Register or enable the {label} GitHub Actions workflow, then collect {missing} additional "
            f"consecutive successful {label} CI run(s) before release signoff.{local_hint}"
        )
    if github_query_error:
        return (
            f"Fix the {label} GitHub Actions evidence query and refresh github_actions_ci_streak_evidence, "
            f"then collect {missing} additional consecutive successful CI run(s) before release signoff."
        )
    if label == "pr" and github_queried_run_count > 0 and github_filtered_run_count == 0:
        return (
            f"No pull_request-triggered CI runs have been observed for the CI workflow "
            f"({github_queried_run_count} run(s) queried, all from non-PR events). "
            "Open a pull request for this branch or add `pull_request` to the CI workflow triggers, "
            f"then collect {missing} additional consecutive successful PR CI run(s) before release signoff."
        )
    if label == "pr":
        return (
            f"Collect {missing} additional consecutive successful PR CI run(s); keep the pull_request CI lane "
            "green and refresh github_actions_ci_streak_evidence before release signoff."
        )
    if label == "nightly":
        return (
            f"Collect {missing} additional consecutive successful nightly CI run(s); keep the scheduled/nightly "
            "lane green and refresh github_actions_ci_streak_evidence before release signoff."
        )
    return f"Collect {missing} additional consecutive successful CI run(s) before release signoff."


def _lane_claim_boundary(label: str) -> str:
    if label == "pr":
        return (
            "Local PR gate reports prove command-level readiness; release streak credit requires tracked PR CI "
            "evidence for the consecutive-pass window."
        )
    if label == "nightly":
        return (
            "Local nightly artifacts prove command-level readiness; release streak credit requires tracked "
            "nightly CI evidence for the consecutive-pass window."
        )
    return "Local CI artifacts prove command-level readiness; release streak credit requires tracked CI evidence."


def _lane(
    label: str,
    reports: list[Path],
    threshold: int,
    github_actions_evidence: dict[str, Any],
    *,
    require_github_actions: bool = True,
) -> dict[str, Any]:
    github_lane = _github_lane_payload(github_actions_evidence, label)
    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for report in reports:
        path = report.resolve()
        if path in seen:
            continue
        seen.add(path)
        payload = _load_json(report)
        ok = _reason_pass(payload)
        rows.append(
            {
                "path": str(report),
                "exists": report.exists(),
                "reason_code": str(payload.get("reason_code", "")),
                "contract_pass": payload.get("contract_pass"),
                "pass": ok,
            }
        )
    local_consecutive = 0
    for row in reversed(rows):
        if not row["pass"]:
            break
        local_consecutive += 1
    github_consecutive = _github_lane_streak(github_actions_evidence, label)
    github_workflow_registered = (
        bool(github_lane.get("workflow_registered")) if "workflow_registered" in github_lane else None
    )
    github_query_error = str(github_lane.get("query_error", "") or "")
    local_workflow_present = bool(github_lane.get("local_workflow_present", False))
    local_workflow_trigger_events = [
        str(item)
        for item in github_lane.get("local_workflow_trigger_events", [])
        if isinstance(item, str)
    ]
    local_required_trigger_present = github_lane.get("local_required_trigger_present") is True
    local_pull_request_trigger_present = github_lane.get("local_pull_request_trigger_present") is True
    local_schedule_trigger_present = github_lane.get("local_schedule_trigger_present") is True
    local_workflow_dispatch_trigger_present = github_lane.get("local_workflow_dispatch_trigger_present") is True
    pull_request_run_source_present = (
        bool(github_lane.get("pull_request_run_source_present"))
        if label == "pr" and "pull_request_run_source_present" in github_lane
        else None
    )
    github_blockers = [str(item) for item in github_lane.get("blockers", []) if isinstance(item, str)]
    github_job_start_blockers = [
        row for row in github_lane.get("job_start_blockers", []) if isinstance(row, dict)
    ]
    github_job_start_blocked = bool(github_job_start_blockers)
    release_consecutive = github_consecutive if require_github_actions else max(local_consecutive, github_consecutive)
    threshold_pass = release_consecutive >= threshold
    blockers = []
    if "github_actions_job_start_blocked" in github_blockers or github_job_start_blocked:
        blockers.append(f"{label}_github_actions_job_start_blocked")
    if "github_actions_query_failed" in github_blockers:
        blockers.append(f"{label}_github_actions_query_failed")
    if "github_actions_workflow_not_registered" in github_blockers:
        blockers.append(f"{label}_github_actions_workflow_not_registered")
    if label == "pr" and "pr_pull_request_run_source_absent" in github_blockers:
        blockers.append("pr_pull_request_run_source_absent")
    if not threshold_pass:
        blockers.append(f"{label}_ci_{threshold}_consecutive_pass_evidence_missing")
    streak_source = "github_actions" if github_consecutive else "missing_tracked_ci_evidence"
    if github_workflow_registered is False:
        streak_source = "github_actions_workflow_not_registered"
    elif github_query_error:
        streak_source = "github_actions_query_failed"
    elif github_job_start_blocked:
        streak_source = "github_actions_job_start_blocked"
    elif label == "pr" and pull_request_run_source_present is False:
        streak_source = "no_pull_request_run_source"
    if not require_github_actions and github_consecutive < local_consecutive:
        streak_source = "local_artifacts"
    return {
        "lane": label,
        "threshold": threshold,
        "release_streak_source_policy": "github_actions_required" if require_github_actions else "local_or_github_actions",
        "report_count": len(rows),
        "pass_count": sum(1 for row in rows if row["pass"]),
        "local_consecutive_pass_count": local_consecutive,
        "github_actions_consecutive_pass_count": github_consecutive,
        "github_actions_workflow_registered": github_workflow_registered,
        "github_actions_query_error": github_query_error,
        "github_actions_queried_run_count": _as_int(github_lane.get("queried_run_count"), 0),
        "github_actions_filtered_run_count": _as_int(github_lane.get("run_count"), 0),
        "pull_request_run_source_present": pull_request_run_source_present,
        "github_actions_ignored_event_names": [
            str(item) for item in github_lane.get("ignored_event_names", []) if isinstance(item, str)
        ],
        "github_actions_job_start_blocker_count": len(github_job_start_blockers),
        "github_actions_job_start_blockers": github_job_start_blockers,
        "local_workflow_present": local_workflow_present,
        "local_workflow_trigger_events": local_workflow_trigger_events,
        "local_required_trigger_present": local_required_trigger_present,
        "local_pull_request_trigger_present": local_pull_request_trigger_present,
        "local_schedule_trigger_present": local_schedule_trigger_present,
        "local_workflow_dispatch_trigger_present": local_workflow_dispatch_trigger_present,
        "release_consecutive_pass_count": release_consecutive,
        "consecutive_pass_count": release_consecutive,
        "missing_consecutive_pass_count": max(0, threshold - release_consecutive),
        "threshold_pass": threshold_pass,
        "blockers": blockers,
        "streak_source": streak_source,
        "owner_action": _lane_owner_action(
            label,
            threshold,
            release_consecutive,
            github_workflow_registered=github_workflow_registered,
            github_query_error=github_query_error,
            github_job_start_blocked=github_job_start_blocked,
            local_workflow_present=local_workflow_present,
            github_queried_run_count=_as_int(github_lane.get("queried_run_count"), 0),
            github_filtered_run_count=_as_int(github_lane.get("run_count"), 0),
        ),
        "claim_boundary": _lane_claim_boundary(label),
        "rows": rows,
    }


def build_manifest(
    *,
    threshold: int,
    pr_reports: list[Path],
    nightly_reports: list[Path],
    github_actions_evidence_path: Path | None = None,
    require_github_actions: bool = True,
) -> dict[str, Any]:
    github_actions_evidence = _load_json(github_actions_evidence_path) if github_actions_evidence_path else {}
    lanes = {
        "pr": _lane(
            "pr",
            pr_reports,
            threshold,
            github_actions_evidence,
            require_github_actions=require_github_actions,
        ),
        "nightly": _lane(
            "nightly",
            nightly_reports,
            threshold,
            github_actions_evidence,
            require_github_actions=require_github_actions,
        ),
    }
    blockers = [
        f"{lane}:{blocker}"
        for lane, lane_payload in lanes.items()
        for blocker in lane_payload["blockers"]
    ]
    return {
        "schema_version": "ci-consecutive-pass-manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_CI_STREAK_INCOMPLETE",
        "blockers": blockers,
        "evidence_sources": {
            "local_pr_report_count": len(pr_reports),
            "local_nightly_report_count": len(nightly_reports),
            "github_actions_evidence_path": str(github_actions_evidence_path or ""),
            "github_actions_evidence_available": bool(github_actions_evidence),
            "github_actions_schema_version": str(github_actions_evidence.get("schema_version", "")),
            "release_streak_source_policy": "github_actions_required"
            if require_github_actions
            else "local_or_github_actions",
        },
        "lanes": lanes,
        "summary": {
            "pr_consecutive_pass_count": lanes["pr"]["consecutive_pass_count"],
            "nightly_consecutive_pass_count": lanes["nightly"]["consecutive_pass_count"],
            "github_actions_pr_consecutive_pass_count": lanes["pr"]["github_actions_consecutive_pass_count"],
            "github_actions_nightly_consecutive_pass_count": lanes["nightly"][
                "github_actions_consecutive_pass_count"
            ],
            "github_actions_pr_workflow_registered": lanes["pr"]["github_actions_workflow_registered"],
            "github_actions_nightly_workflow_registered": lanes["nightly"]["github_actions_workflow_registered"],
            "github_actions_pr_job_start_blocker_count": lanes["pr"][
                "github_actions_job_start_blocker_count"
            ],
            "github_actions_nightly_job_start_blocker_count": lanes["nightly"][
                "github_actions_job_start_blocker_count"
            ],
            "github_actions_nightly_local_workflow_present": lanes["nightly"]["local_workflow_present"],
            "pr_pull_request_run_source_present": lanes["pr"]["pull_request_run_source_present"],
            "pr_threshold_pass": lanes["pr"]["threshold_pass"],
            "nightly_threshold_pass": lanes["nightly"]["threshold_pass"],
            "pr_missing_consecutive_pass_count": lanes["pr"]["missing_consecutive_pass_count"],
            "nightly_missing_consecutive_pass_count": lanes["nightly"]["missing_consecutive_pass_count"],
            "pr_owner_action": lanes["pr"]["owner_action"],
            "nightly_owner_action": lanes["nightly"]["owner_action"],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=30)
    parser.add_argument("--github-actions-evidence", type=Path, default=DEFAULT_GITHUB_ACTIONS_EVIDENCE)
    parser.add_argument(
        "--allow-local-release-streak",
        action="store_true",
        help="Allow local artifacts to satisfy release streak credit. Default requires GitHub Actions evidence.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    nightly_reports = [
        *DEFAULT_NIGHTLY_REPORTS,
        *sorted(DEFAULT_NIGHTLY_GLOB_ROOT.glob("phase3_nightly_hardening_*/ci_gate_report.json")),
    ]
    payload = build_manifest(
        threshold=args.threshold,
        pr_reports=DEFAULT_PR_REPORTS,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=args.github_actions_evidence,
        require_github_actions=not args.allow_local_release_streak,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
