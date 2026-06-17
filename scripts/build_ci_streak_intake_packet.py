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
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.md")
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
    local_required_trigger_present = github_lane.get("local_required_trigger_present") is True
    local_pull_request_trigger_present = github_lane.get("local_pull_request_trigger_present") is True
    local_schedule_trigger_present = github_lane.get("local_schedule_trigger_present") is True
    local_workflow_dispatch_trigger_present = github_lane.get("local_workflow_dispatch_trigger_present") is True
    pull_request_run_source_present = (
        github_lane.get("pull_request_run_source_present") is True if lane == "pr" else None
    )
    run_count = _as_int(github_lane.get("run_count"))
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
        "workflow_registered": workflow_registered,
        "workflow_state": workflow_state,
        "workflow_active": workflow_active,
        "local_workflow_present": local_workflow_present,
        "local_workflow_trigger_events": local_workflow_trigger_events,
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
        "lanes": lanes,
        "contract_pass": not blockers,
        "blockers": _dedupe(blockers),
    }


def _lane_row(lane: str, manifest: dict[str, Any], source_evidence: dict[str, Any]) -> dict[str, Any]:
    manifest_lane = _manifest_lane(manifest, lane)
    source_lane = _as_dict(_as_dict(source_evidence.get("lanes")).get(lane))
    threshold = _as_int(manifest_lane.get("threshold"), _as_int(manifest.get("threshold"), 30))
    manifest_consecutive = _as_int(manifest_lane.get("consecutive_pass_count"))
    source_consecutive = _as_int(source_lane.get("source_consecutive_pass_count"))
    source_credit_pass = source_lane.get("source_release_credit_pass") is True
    consecutive = source_consecutive if source_credit_pass else 0
    missing = max(0, threshold - consecutive)
    manifest_threshold_pass = manifest_lane.get("threshold_pass") is True
    threshold_pass = bool(manifest_threshold_pass and source_credit_pass and consecutive >= threshold)
    blockers = [str(item) for item in manifest_lane.get("blockers", []) if isinstance(item, str)]
    blockers.extend(str(item) for item in source_lane.get("blockers", []) if isinstance(item, str))
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
        "streak_source": str(manifest_lane.get("streak_source", "")),
        "owner_action": str(manifest_lane.get("owner_action", "")),
        "claim_boundary": str(manifest_lane.get("claim_boundary", "")),
        "blockers": _dedupe(blockers),
    }


def build_packet(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    github_actions_evidence_path: Path = DEFAULT_GITHUB_ACTIONS_EVIDENCE,
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
    lane_rows = [
        _lane_row("pr", manifest, source_evidence),
        _lane_row("nightly", manifest, source_evidence),
    ]
    blockers = [
        f"{row['lane']}:{blocker}"
        for row in lane_rows
        for blocker in row["blockers"]
        if not row["threshold_pass"]
    ]
    contract_pass = bool(manifest.get("contract_pass") is True and source_evidence["contract_pass"] and not blockers)
    source_blockers = [str(item) for item in source_evidence["blockers"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": (
            "PASS"
            if contract_pass
            else "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE"
            if source_blockers
            else "ERR_CI_STREAK_EVIDENCE_INCOMPLETE"
        ),
        "ci_consecutive_pass_manifest": str(manifest_path),
        "github_actions_ci_streak_evidence": str(github_actions_evidence_path),
        "source_evidence": source_evidence,
        "summary": {
            "threshold": threshold,
            "lane_count": len(lane_rows),
            "lane_pass_count": sum(1 for row in lane_rows if row["threshold_pass"]),
            "open_blocker_count": len(blockers),
            "source_evidence_pass": source_evidence["contract_pass"],
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
        "current_blockers": blockers,
        "validation_commands": [
            f"python3 scripts/build_github_actions_ci_streak_evidence.py --out {DEFAULT_GITHUB_ACTIONS_EVIDENCE}",
            f"python3 scripts/build_ci_consecutive_pass_manifest.py --out {DEFAULT_MANIFEST}",
            f"python3 scripts/build_ci_streak_intake_packet.py --out {DEFAULT_OUT}",
            "python3 scripts/report_pm_release_gate.py "
            " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
            " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
            "python3 scripts/build_pm_release_blocker_action_register.py "
            " --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
            " --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
        ],
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
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `ci_consecutive_pass_manifest`: `{payload['ci_consecutive_pass_manifest']}`",
        f"- `github_actions_ci_streak_evidence`: `{payload['github_actions_ci_streak_evidence']}`",
        "",
        "| Lane | Streak | Missing | Source | Workflow Registered | Pass | Owner Action |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for row in payload["lane_rows"]:
        lines.append(
            f"| `{row['lane']}` | `{row['consecutive_pass_count']}/{row['threshold']}` | "
            f"`{row['missing_consecutive_pass_count']}` | `{row['streak_source']}` | "
            f"`{row['github_actions_workflow_registered']}` | `{row['threshold_pass']}` | "
            f"{row['owner_action']} |"
        )
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
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
