#!/usr/bin/env python3
"""Build a reviewer handoff package for open PM release gate blockers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-release-gate-reviewer-handoff.v1"
DEFAULT_PM_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_CLOSURE_BOARD = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json"
)
DEFAULT_COMPLETION_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

BLOCKER_CHECK_KEYS = {
    "basic_ci::pr_ci_30_consecutive_pass_evidence_missing": ["pr_ci_30_run_streak_pass"],
    "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing": ["nightly_ci_30_run_streak_pass"],
    "ux::human_new_user_observation_missing_or_failed": ["human_new_user_observation_pass"],
    "ux::human_new_user_30min_sample_evidence_missing": [
        "human_new_user_sample_30min_evidence_present",
        "human_new_user_sample_30min_pass",
    ],
    "security::license_status_not_configured": [
        "license_status_configured_pass",
        "license_status_closure_report_present",
    ],
}


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


def _indexed(rows: list[Any], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get(key, "") or "")
        if row_key:
            indexed[row_key] = row
    return indexed


def _split_blocker(blocker_id: str) -> tuple[str, str]:
    if "::" not in blocker_id:
        return "", blocker_id
    return tuple(blocker_id.split("::", 1))  # type: ignore[return-value]


def _required_fields_present(row: dict[str, Any]) -> bool:
    return bool(
        row.get("blocker_id")
        and row.get("owner")
        and row.get("closure_state")
        and row.get("next_action")
        and row.get("reproduction_commands")
        and row.get("verification_commands")
        and row.get("verdict_change_conditions")
    )


def _verdict_change_conditions(*, blocker_id: str, audit_row: dict[str, Any]) -> list[str]:
    namespace, _ = _split_blocker(blocker_id)
    check_keys = BLOCKER_CHECK_KEYS.get(blocker_id, [])
    conditions = [
        f"`release_area.{namespace}` status is `pass` in `pm_release_gate_completion_audit.json`",
        f"`{blocker_id}` is absent from `pm_release_gate_report.json.release_area_blockers`",
    ]
    for key in check_keys:
        conditions.append(f"`release_area.{namespace}::{key}` is `true` in `pm_release_gate_report.json`")
    if not check_keys:
        conditions.append("The owning release-area row has no blocker-specific false check in the PM report.")
    checks = _as_dict(audit_row.get("checks"))
    false_checks = [key for key, value in checks.items() if value is False]
    if false_checks:
        conditions.append("Current false audit check(s): " + ", ".join(f"`{key}`" for key in false_checks))
    return conditions


def _audit_row_for_blocker(blocker_id: str, audit_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    namespace, _ = _split_blocker(blocker_id)
    return _as_dict(audit_rows.get(f"release_area.{namespace}"))


def _handoff_row(
    *,
    blocker: dict[str, Any],
    audit_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    blocker_id = str(blocker.get("blocker_id", ""))
    audit_row = _audit_row_for_blocker(blocker_id, audit_rows)
    return {
        "blocker_id": blocker_id,
        "release_area_requirement_id": str(audit_row.get("requirement_id", "")),
        "release_area_status": str(audit_row.get("status", "")),
        "owner": str(blocker.get("owner", "")),
        "closure_state": str(blocker.get("closure_state", "")),
        "handoff_state": str(blocker.get("handoff_state", "")),
        "evidence_state": str(blocker.get("evidence_state", "")),
        "next_action": str(blocker.get("next_action", "")),
        "claim_boundary": str(blocker.get("claim_boundary", audit_row.get("claim_boundary", ""))),
        "acceptance_criteria": [str(item) for item in _as_list(blocker.get("acceptance_criteria"))],
        "verdict_change_conditions": _verdict_change_conditions(blocker_id=blocker_id, audit_row=audit_row),
        "reproduction_commands": [str(item) for item in _as_list(blocker.get("reproduction_commands"))],
        "verification_commands": [str(item) for item in _as_list(blocker.get("verification_commands"))],
        "evidence_artifact_paths": {
            str(key): str(value)
            for key, value in _as_dict(blocker.get("primary_evidence_artifacts")).items()
            if str(value)
        },
        "external_input_required": bool(blocker.get("external_input_required", False)),
        "owner_input_required": bool(blocker.get("owner_input_required", False)),
    }


def build_handoff(
    *,
    pm_report: Path = DEFAULT_PM_REPORT,
    closure_board: Path = DEFAULT_CLOSURE_BOARD,
    completion_audit: Path = DEFAULT_COMPLETION_AUDIT,
) -> dict[str, Any]:
    pm_payload = _load_json(pm_report)
    closure_payload = _load_json(closure_board)
    audit_payload = _load_json(completion_audit)
    audit_rows = _indexed(_as_list(audit_payload.get("rows")), "requirement_id")
    rows = [
        _handoff_row(blocker=row, audit_rows=audit_rows)
        for row in _as_list(closure_payload.get("rows"))
        if isinstance(row, dict)
    ]
    incomplete_rows = [row["blocker_id"] for row in rows if not _required_fields_present(row)]
    contract_pass = bool(not incomplete_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_REVIEWER_HANDOFF_INCOMPLETE",
        "pm_release_gate_report": str(pm_report),
        "pm_release_blocker_closure_board": str(closure_board),
        "pm_release_gate_completion_audit": str(completion_audit),
        "pm_summary_line": str(pm_payload.get("summary_line", "")),
        "summary_line": (
            "PM release gate reviewer handoff: "
            f"{'PASS' if contract_pass else 'BLOCKED'} | "
            f"open_blockers={len(rows)} | incomplete={len(incomplete_rows)}"
        ),
        "summary": {
            "open_blocker_count": len(rows),
            "handoff_complete_count": len(rows) - len(incomplete_rows),
            "handoff_incomplete_count": len(incomplete_rows),
            "external_input_required_count": sum(1 for row in rows if row["external_input_required"]),
            "owner_input_required_count": sum(1 for row in rows if row["owner_input_required"]),
            "release_area_gate_ready": bool(pm_payload.get("release_area_gate_ready", False)),
            "full_release_gate_ready": bool(pm_payload.get("full_release_gate_ready", False)),
            "limited_commercial_ready": bool(pm_payload.get("limited_commercial_ready", False)),
            "paid_pilot_candidate": bool(pm_payload.get("paid_pilot_candidate", False)),
        },
        "incomplete_blockers": incomplete_rows,
        "rows": rows,
        "claim_boundary": (
            "This reviewer handoff packages PM blocker review actions and verdict-change conditions. It does not "
            "convert missing tracked CI streak, human UX observation, license approval, or other external evidence "
            "into a release pass."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Gate Reviewer Handoff",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        "",
        "| Blocker | Owner | Closure | Verdict Change Conditions |",
        "|---|---|---|---|",
    ]
    for row in payload["rows"]:
        conditions = "<br>".join(str(item) for item in row.get("verdict_change_conditions", []))
        lines.append(
            f"| `{row['blocker_id']}` | `{row['owner']}` | `{row['closure_state']}` | {conditions} |"
        )
    if not payload["rows"]:
        lines.append("| none | `release_owner` | `closed` | No open PM release blockers. |")
    lines.append("")
    if payload["rows"]:
        lines.extend(["## Blocker Details", ""])
    for row in payload["rows"]:
        lines.extend(
            [
                f"### `{row['blocker_id']}`",
                "",
                f"- Owner: `{row['owner']}`",
                f"- Release area status: `{row['release_area_status']}`",
                f"- Closure state: `{row['closure_state']}`",
                f"- Evidence state: `{row['evidence_state']}`",
                f"- External input required: `{row['external_input_required']}`",
                f"- Owner input required: `{row['owner_input_required']}`",
                f"- Next action: {row['next_action']}",
                "",
                "Acceptance criteria:",
            ]
        )
        for item in row.get("acceptance_criteria", []):
            lines.append(f"- {item}")
        if not row.get("acceptance_criteria"):
            lines.append("- none")
        lines.extend(["", "Evidence artifact paths:"])
        artifact_paths = row.get("evidence_artifact_paths", {})
        if artifact_paths:
            for key, value in artifact_paths.items():
                lines.append(f"- `{key}`: `{value}`")
        else:
            lines.append("- none")
        lines.extend(["", "Reproduction commands:"])
        reproduction_commands = row.get("reproduction_commands", [])
        if reproduction_commands:
            for command in reproduction_commands:
                lines.append(f"- `{command}`")
        else:
            lines.append("- none")
        lines.extend(["", "Verification commands:"])
        verification_commands = row.get("verification_commands", [])
        if verification_commands:
            for command in verification_commands:
                lines.append(f"- `{command}`")
        else:
            lines.append("- none")
        lines.extend(["", "Verdict change conditions:"])
        for item in row.get("verdict_change_conditions", []):
            lines.append(f"- {item}")
        lines.append("")
    lines.append(payload["claim_boundary"])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument("--closure-board", type=Path, default=DEFAULT_CLOSURE_BOARD)
    parser.add_argument("--completion-audit", type=Path, default=DEFAULT_COMPLETION_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_handoff(
        pm_report=args.pm_report,
        closure_board=args.closure_board,
        completion_audit=args.completion_audit,
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
