#!/usr/bin/env python3
"""Build a PM-facing closure board for open release blockers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-release-blocker-closure-board.v1"
DEFAULT_ACTION_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_PM_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _row_handoff_ready(row: dict[str, Any]) -> bool:
    handoff = _as_dict(row.get("handoff"))
    return bool(row.get("handoff_ready", handoff.get("handoff_ready", False)))


def _row_handoff_state(row: dict[str, Any]) -> str:
    handoff = _as_dict(row.get("handoff"))
    return str(row.get("handoff_state", handoff.get("handoff_state", "")) or "")


def _row_closure_state(row: dict[str, Any]) -> str:
    if str(row.get("status", "open")) == "closed":
        return "closed"
    if not _row_handoff_ready(row):
        return "handoff_incomplete"
    handoff_state = _row_handoff_state(row)
    if handoff_state:
        return handoff_state
    if _as_bool(row.get("external_input_required")):
        return "external_owner_input_ready"
    return "local_remediation_ready"


def _board_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence_status = _as_dict(row.get("evidence_status"))
    evidence_artifacts = {
        str(key): str(value)
        for key, value in _as_dict(row.get("evidence_artifacts")).items()
        if str(value)
    }
    return {
        "blocker_id": str(row.get("blocker_id", "")),
        "scope": str(row.get("scope", "")),
        "owner": str(row.get("owner", "")),
        "handoff_ready": _row_handoff_ready(row),
        "handoff_state": _row_handoff_state(row),
        "closure_state": _row_closure_state(row),
        "evidence_state": str(evidence_status.get("state", "open_release_evidence_blocker")),
        "resolution_type": str(row.get("resolution_type", "")),
        "external_input_required": _as_bool(row.get("external_input_required")),
        "owner_input_required": _as_bool(row.get("owner_input_required")),
        "next_action": str(row.get("next_action", row.get("owner_action", "")) or ""),
        "acceptance_criteria": [str(item) for item in _as_list(row.get("acceptance_criteria"))],
        "primary_evidence_artifacts": evidence_artifacts,
        "reproduction_commands": [str(item) for item in _as_list(row.get("reproduction_commands"))],
        "verification_commands": [str(item) for item in _as_list(row.get("verification_commands"))],
        "claim_boundary": str(row.get("claim_boundary", "")),
    }


def _state_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        state = str(row.get("closure_state", "unknown"))
        counts[state] = counts.get(state, 0) + 1
    return counts


def _pm_blocker_ids(pm_payload: dict[str, Any]) -> list[str]:
    full_blockers = [str(item) for item in _as_list(pm_payload.get("full_release_blockers"))]
    if not full_blockers:
        full_blockers = [
            *[str(item) for item in _as_list(pm_payload.get("blockers"))],
            *[str(item) for item in _as_list(pm_payload.get("release_area_blockers"))],
        ]
    release_tiers = _as_dict(pm_payload.get("release_tiers"))
    ga_blockers = [str(item) for item in _as_list(release_tiers.get("ga_enterprise_blockers"))]
    return list(dict.fromkeys([*full_blockers, *ga_blockers]))


def _reason_code(
    *,
    action_register_loaded: bool,
    pm_report_loaded: bool,
    action_register_matches_pm_report: bool,
    rows: list[dict[str, Any]],
    full_release_gate_ready: bool,
) -> str:
    if not action_register_loaded:
        return "ERR_PM_BLOCKER_ACTION_REGISTER_MISSING"
    if not pm_report_loaded:
        return "ERR_PM_RELEASE_GATE_REPORT_MISSING"
    if not action_register_matches_pm_report:
        return "ERR_PM_BLOCKER_ACTION_REGISTER_STALE"
    if rows:
        return "ERR_PM_RELEASE_BLOCKERS_OPEN"
    if not full_release_gate_ready:
        return "ERR_PM_RELEASE_GATE_NOT_READY"
    return "PASS"


def build_board(
    *,
    action_register: Path = DEFAULT_ACTION_REGISTER,
    pm_report: Path = DEFAULT_PM_REPORT,
) -> dict[str, Any]:
    register_payload = _load_json(action_register)
    pm_payload = _load_json(pm_report)
    register_summary = _as_dict(register_payload.get("summary"))
    rows = [_board_row(row) for row in _as_list(register_payload.get("rows")) if isinstance(row, dict)]
    full_release_gate_ready = bool(
        pm_payload.get("full_release_gate_ready", register_summary.get("full_release_gate_ready", False))
    )
    release_area_gate_ready = bool(
        pm_payload.get("release_area_gate_ready", register_summary.get("release_area_gate_ready", False))
    )
    limited_commercial_ready = bool(
        pm_payload.get("limited_commercial_ready", register_summary.get("limited_commercial_ready", False))
    )
    limited_commercial_milestone_ready = bool(
        pm_payload.get(
            "limited_commercial_milestone_ready",
            register_summary.get("limited_commercial_milestone_ready", limited_commercial_ready),
        )
    )
    limited_commercial_release_ready = bool(
        pm_payload.get(
            "limited_commercial_release_ready",
            register_summary.get("limited_commercial_release_ready", limited_commercial_ready),
        )
    )
    paid_pilot_candidate = bool(
        pm_payload.get("paid_pilot_candidate", register_summary.get("paid_pilot_candidate", False))
    )
    action_register_loaded = bool(register_payload)
    pm_report_loaded = bool(pm_payload)
    pm_blocker_ids = _pm_blocker_ids(pm_payload)
    register_blocker_ids = [str(row.get("blocker_id", "")) for row in rows if str(row.get("blocker_id", ""))]
    pm_blocker_set = set(pm_blocker_ids)
    register_blocker_set = set(register_blocker_ids)
    missing_from_action_register = sorted(pm_blocker_set - register_blocker_set)
    stale_action_register_blockers = sorted(register_blocker_set - pm_blocker_set)
    action_register_matches_pm_report = (
        action_register_loaded
        and pm_report_loaded
        and not missing_from_action_register
        and not stale_action_register_blockers
    )
    reason_code = _reason_code(
        action_register_loaded=action_register_loaded,
        pm_report_loaded=pm_report_loaded,
        action_register_matches_pm_report=action_register_matches_pm_report,
        rows=rows,
        full_release_gate_ready=full_release_gate_ready,
    )
    contract_pass = reason_code == "PASS"
    closure_state_counts = _state_counts(rows)
    handoff_not_ready_count = sum(1 for row in rows if not row["handoff_ready"])
    external_owner_input_ready_count = closure_state_counts.get("external_owner_input_ready", 0)
    local_remediation_ready_count = closure_state_counts.get("local_remediation_ready", 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "pm_release_gate_report": str(pm_report),
        "pm_release_blocker_action_register": str(action_register),
        "pm_summary_line": str(
            pm_payload.get("summary_line", register_payload.get("pm_summary_line", ""))
        ),
        "summary_line": (
            "PM release blocker closure board: "
            f"{'PASS' if contract_pass else 'BLOCKED'} | "
            f"open={len(rows)} | "
            f"external_owner_ready={external_owner_input_ready_count} | "
            f"handoff_not_ready={handoff_not_ready_count}"
        ),
        "summary": {
            "open_blocker_count": len(rows),
            "closure_state_counts": closure_state_counts,
            "external_owner_input_ready_count": external_owner_input_ready_count,
            "local_remediation_ready_count": local_remediation_ready_count,
            "handoff_ready_count": sum(1 for row in rows if row["handoff_ready"]),
            "handoff_not_ready_count": handoff_not_ready_count,
            "all_open_blockers_have_handoff": all(row["handoff_ready"] for row in rows),
            "external_input_required_count": sum(1 for row in rows if row["external_input_required"]),
            "owner_input_required_count": sum(1 for row in rows if row["owner_input_required"]),
            "release_area_gate_ready": release_area_gate_ready,
            "full_release_gate_ready": full_release_gate_ready,
            "limited_commercial_milestone_ready": limited_commercial_milestone_ready,
            "limited_commercial_release_ready": limited_commercial_release_ready,
            "limited_commercial_ready": limited_commercial_ready,
            "paid_pilot_candidate": paid_pilot_candidate,
            "register_open_blocker_count": _as_int(register_summary.get("open_blocker_count"), len(rows)),
            "pm_report_blocker_count": len(pm_blocker_ids),
            "register_blocker_count": len(register_blocker_ids),
            "action_register_matches_pm_report": action_register_matches_pm_report,
            "missing_from_action_register_count": len(missing_from_action_register),
            "stale_action_register_blocker_count": len(stale_action_register_blockers),
            "missing_from_action_register": missing_from_action_register,
            "stale_action_register_blockers": stale_action_register_blockers,
            "action_register_loaded": action_register_loaded,
            "pm_report_loaded": pm_report_loaded,
        },
        "rows": rows,
        "claim_boundary": (
            "This closure board is an owner-handoff and daily closure artifact. It does not convert missing "
            "CI streak, human UX observation, license, or other external evidence into a release pass."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Blocker Closure Board",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `open_blocker_count`: `{payload['summary']['open_blocker_count']}`",
        f"- `all_open_blockers_have_handoff`: `{payload['summary']['all_open_blockers_have_handoff']}`",
        f"- `action_register_matches_pm_report`: `{payload['summary']['action_register_matches_pm_report']}`",
        "",
        "| Blocker | Owner | Closure State | Evidence State | Next Action |",
        "|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| `{row['blocker_id']}` | `{row['owner']}` | `{row['closure_state']}` | "
            f"`{row['evidence_state']}` | {row['next_action']} |"
        )
    if not payload["rows"]:
        lines.append("| none | `release_owner` | `closed` | `PASS` | No open PM release blockers. |")
    lines.extend(["", payload["claim_boundary"]])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-register", type=Path, default=DEFAULT_ACTION_REGISTER)
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_board(action_register=args.action_register, pm_report=args.pm_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
