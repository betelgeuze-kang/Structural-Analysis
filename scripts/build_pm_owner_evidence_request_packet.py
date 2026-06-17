#!/usr/bin/env python3
"""Build owner-grouped evidence requests for open PM release blockers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-owner-evidence-request-packet.v1"
DEFAULT_ACTION_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
OWNER_ORDER = (
    "release_ci_owner",
    "ux_research_owner",
    "product_legal_owner",
    "frontend_security_owner",
    "release_owner",
)
INTAKE_ROW_PREVIEW_LIMIT = 12


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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped


def _dedupe_dicts(rows: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get(key, "") or "")
        if not row_key or row_key in seen:
            continue
        seen.add(row_key)
        deduped.append(row)
    return deduped


def _owner_sort_key(owner: str) -> tuple[int, str]:
    try:
        return (OWNER_ORDER.index(owner), owner)
    except ValueError:
        return (len(OWNER_ORDER), owner)


def _public_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    allowed_types = (str, int, float, bool, type(None))
    return {str(key): value for key, value in summary.items() if isinstance(value, allowed_types)}


def _field_request_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _as_list(payload.get("field_rows"))[:INTAKE_ROW_PREVIEW_LIMIT]:
        if not isinstance(row, dict):
            continue
        field = str(row.get("field", "") or "")
        if not field:
            continue
        rows.append(
            {
                "field": field,
                "required_value": str(row.get("required_value", "") or ""),
                "template_value": str(row.get("template_value", "") or ""),
                "owner_note": str(row.get("owner_note", "") or ""),
                "check": str(row.get("closure_check", "") or row.get("report_check", "") or ""),
                "check_pass": row.get("closure_check_pass", row.get("report_check_pass")),
                "missing": row.get("missing"),
                "placeholder": row.get("placeholder"),
            }
        )
    return rows


def _lane_request_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _as_list(payload.get("lane_rows"))[:INTAKE_ROW_PREVIEW_LIMIT]:
        if not isinstance(row, dict):
            continue
        lane = str(row.get("lane", "") or "")
        if not lane:
            continue
        rows.append(
            {
                "lane": lane,
                "threshold": row.get("threshold"),
                "threshold_pass": row.get("threshold_pass"),
                "consecutive_pass_count": row.get("consecutive_pass_count"),
                "missing_consecutive_pass_count": row.get("missing_consecutive_pass_count"),
                "github_actions_consecutive_pass_count": row.get("github_actions_consecutive_pass_count"),
                "github_actions_workflow_registered": row.get("github_actions_workflow_registered"),
                "github_actions_workflow_state": str(row.get("github_actions_workflow_state", "") or ""),
                "local_required_trigger_present": row.get("local_required_trigger_present"),
                "local_workflow_trigger_events": [
                    str(item) for item in _as_list(row.get("local_workflow_trigger_events"))
                ],
                "source_evidence_release_credit_pass": row.get("source_evidence_release_credit_pass"),
                "streak_source": str(row.get("streak_source", "") or ""),
                "blockers": [str(item) for item in _as_list(row.get("blockers"))],
            }
        )
    return rows


def _expected_intake_detail(path_text: str) -> dict[str, Any]:
    if not path_text:
        return {}
    path = Path(path_text)
    payload = _load_json(path)
    present = bool(path.exists() and payload)
    current_blockers = [str(item) for item in _as_list(payload.get("current_blockers"))]
    field_rows = _field_request_rows(payload)
    lane_rows = _lane_request_rows(payload)
    return {
        "path": path_text,
        "present": present,
        "schema_version": str(payload.get("schema_version", "") or ""),
        "contract_pass": payload.get("contract_pass") is True,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": str(payload.get("summary_line", "") or ""),
        "current_blockers": current_blockers,
        "current_blocker_count": len(current_blockers),
        "summary": _public_summary(payload.get("summary")),
        "field_request_rows": field_rows,
        "field_request_count": len(field_rows),
        "lane_request_rows": lane_rows,
        "lane_request_count": len(lane_rows),
        "claim_boundary": str(payload.get("claim_boundary", "") or ""),
    }


def _request_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence_artifacts = _as_dict(row.get("evidence_artifacts"))
    handoff = _as_dict(row.get("handoff"))
    expected_intake_artifact = str(handoff.get("expected_intake_artifact", "") or "")
    expected_intake_path = str(evidence_artifacts.get(expected_intake_artifact, "") or "")
    expected_intake_detail = _expected_intake_detail(expected_intake_path)
    return {
        "blocker_id": str(row.get("blocker_id", "") or ""),
        "scope": str(row.get("scope", "") or ""),
        "title": str(row.get("title", "") or ""),
        "evidence_state": str(_as_dict(row.get("evidence_status")).get("state", "") or ""),
        "handoff_state": str(row.get("handoff_state", "") or ""),
        "next_action": str(row.get("next_action", "") or row.get("owner_action", "") or ""),
        "acceptance_criteria": [str(item) for item in _as_list(row.get("acceptance_criteria"))],
        "reproduction_commands": [str(item) for item in _as_list(row.get("reproduction_commands"))],
        "verification_commands": [str(item) for item in _as_list(row.get("verification_commands"))],
        "expected_intake_artifact": expected_intake_artifact,
        "expected_intake_path": expected_intake_path,
        "expected_intake_detail": expected_intake_detail,
        "evidence_artifacts": {str(key): str(value) for key, value in evidence_artifacts.items() if str(value)},
        "claim_boundary": str(row.get("claim_boundary", "") or ""),
        "external_input_required": bool(row.get("external_input_required", False)),
        "owner_input_required": bool(row.get("owner_input_required", False)),
        "handoff_ready": bool(row.get("handoff_ready", False)),
    }


def _request_complete(row: dict[str, Any]) -> bool:
    return bool(
        row.get("blocker_id")
        and row.get("next_action")
        and row.get("acceptance_criteria")
        and row.get("reproduction_commands")
        and row.get("verification_commands")
        and row.get("handoff_ready")
    )


def _owner_packet(owner: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [row["blocker_id"] for row in rows if not _request_complete(row)]
    intake_details = [
        _as_dict(row.get("expected_intake_detail"))
        for row in rows
        if _as_dict(row.get("expected_intake_detail")).get("path")
    ]
    deduped_intake_details = _dedupe_dicts(intake_details, key="path")
    return {
        "owner": owner,
        "request_state": "ready_for_owner_input" if not incomplete else "request_incomplete",
        "blocker_count": len(rows),
        "blocker_ids": [row["blocker_id"] for row in rows],
        "evidence_states": _dedupe([row["evidence_state"] for row in rows]),
        "next_actions": _dedupe([row["next_action"] for row in rows]),
        "acceptance_criteria": _dedupe(
            [item for row in rows for item in _as_list(row.get("acceptance_criteria"))]
        ),
        "reproduction_commands": _dedupe(
            [item for row in rows for item in _as_list(row.get("reproduction_commands"))]
        ),
        "verification_commands": _dedupe(
            [item for row in rows for item in _as_list(row.get("verification_commands"))]
        ),
        "expected_intake_artifacts": _dedupe([row["expected_intake_artifact"] for row in rows]),
        "expected_intake_paths": _dedupe([row["expected_intake_path"] for row in rows]),
        "expected_intake_details": deduped_intake_details,
        "intake_current_blockers": _dedupe(
            [
                blocker
                for detail in deduped_intake_details
                for blocker in _as_list(detail.get("current_blockers"))
            ]
        ),
        "intake_field_request_rows": _dedupe_dicts(
            [
                field_row
                for detail in deduped_intake_details
                for field_row in _as_list(detail.get("field_request_rows"))
                if isinstance(field_row, dict)
            ],
            key="field",
        ),
        "intake_lane_request_rows": _dedupe_dicts(
            [
                lane_row
                for detail in deduped_intake_details
                for lane_row in _as_list(detail.get("lane_request_rows"))
                if isinstance(lane_row, dict)
            ],
            key="lane",
        ),
        "external_input_required": any(row["external_input_required"] for row in rows),
        "owner_input_required": any(row["owner_input_required"] for row in rows),
        "incomplete_blockers": incomplete,
        "request_rows": rows,
    }


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _markdown_code(value: Any) -> str:
    text = _markdown_cell(value)
    return f"`{text}`" if text else ""


def _markdown_bool(value: Any) -> str:
    if value is True:
        return "`true`"
    if value is False:
        return "`false`"
    return ""


def build_packet(*, action_register: Path = DEFAULT_ACTION_REGISTER) -> dict[str, Any]:
    register = _load_json(action_register)
    rows = [_request_row(row) for row in _as_list(register.get("rows")) if isinstance(row, dict)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    source_rows = _as_list(register.get("rows"))
    for source_row, request_row in zip(source_rows, rows, strict=False):
        owner = str(_as_dict(source_row).get("owner", "") or "release_owner")
        grouped.setdefault(owner, []).append(request_row)
    if not grouped:
        grouped["release_owner"] = []

    packets = [_owner_packet(owner, grouped[owner]) for owner in sorted(grouped, key=_owner_sort_key)]
    incomplete = [blocker for packet in packets for blocker in packet["incomplete_blockers"]]
    contract_pass = not incomplete
    expected_intake_details = _dedupe_dicts(
        [
            detail
            for packet in packets
            for detail in _as_list(packet.get("expected_intake_details"))
            if isinstance(detail, dict)
        ],
        key="path",
    )
    expected_intake_blockers = _dedupe(
        [
            blocker
            for detail in expected_intake_details
            for blocker in _as_list(detail.get("current_blockers"))
        ]
    )
    summary = _as_dict(register.get("summary"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_OWNER_EVIDENCE_REQUEST_INCOMPLETE",
        "pm_release_blocker_action_register": str(action_register),
        "pm_summary_line": str(register.get("pm_summary_line", "")),
        "summary_line": (
            "PM owner evidence request packet: "
            f"{'PASS' if contract_pass else 'BLOCKED'} | owners={len(packets)} | "
            f"open_blockers={len(rows)} | incomplete={len(incomplete)}"
        ),
        "summary": {
            "owner_packet_count": len(packets),
            "open_blocker_count": len(rows),
            "owner_input_required_count": sum(1 for row in rows if row["owner_input_required"]),
            "external_input_required_count": sum(1 for row in rows if row["external_input_required"]),
            "incomplete_request_count": len(incomplete),
            "handoff_contract_pass": contract_pass,
            "evidence_closure_pass": not rows,
            "expected_intake_count": len(expected_intake_details),
            "expected_intake_contract_pass_count": sum(
                1 for detail in expected_intake_details if detail.get("contract_pass") is True
            ),
            "expected_intake_open_blocker_count": len(expected_intake_blockers),
            "expected_intake_field_request_count": sum(
                int(detail.get("field_request_count", 0) or 0) for detail in expected_intake_details
            ),
            "expected_intake_lane_request_count": sum(
                int(detail.get("lane_request_count", 0) or 0) for detail in expected_intake_details
            ),
            "release_area_gate_ready": bool(summary.get("release_area_gate_ready", False)),
            "full_release_gate_ready": bool(summary.get("full_release_gate_ready", False)),
            "limited_commercial_ready": bool(summary.get("limited_commercial_ready", False)),
            "paid_pilot_candidate": bool(summary.get("paid_pilot_candidate", False)),
        },
        "incomplete_blockers": incomplete,
        "owner_packets": packets,
        "claim_boundary": (
            "This packet groups open PM blocker evidence requests by owner. It does not create or replace "
            "tracked CI streaks, human UX observations, product/legal license approval, or any other external "
            "release evidence, and it does not convert missing evidence into a release pass."
        ),
    }


def _markdown_intake_details(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = ["", "## Intake Details", ""]
    any_details = False
    for packet in payload["owner_packets"]:
        lane_rows = [row for row in _as_list(packet.get("intake_lane_request_rows")) if isinstance(row, dict)]
        field_rows = [row for row in _as_list(packet.get("intake_field_request_rows")) if isinstance(row, dict)]
        if not lane_rows and not field_rows:
            continue
        any_details = True
        lines.extend([f"### `{packet['owner']}`", ""])
        if lane_rows:
            lines.extend(
                [
                    "| Lane | Current | Missing | Source | Workflow | Local Trigger | Blockers |",
                    "|---|---:|---:|---|---|---|---|",
                ]
            )
            for row in lane_rows:
                threshold = row.get("threshold")
                current = row.get("consecutive_pass_count")
                events = ", ".join(str(item) for item in _as_list(row.get("local_workflow_trigger_events")))
                blockers = "<br>".join(_markdown_code(item) for item in _as_list(row.get("blockers"))) or "none"
                workflow = (
                    f"registered={row.get('github_actions_workflow_registered')}; "
                    f"state={_markdown_cell(row.get('github_actions_workflow_state'))}"
                )
                local_trigger = (
                    f"required={row.get('local_required_trigger_present')}; "
                    f"events={_markdown_cell(events)}"
                )
                lines.append(
                    "| "
                    f"{_markdown_code(row.get('lane'))} | "
                    f"{_markdown_cell(current)}/{_markdown_cell(threshold)} | "
                    f"{_markdown_cell(row.get('missing_consecutive_pass_count'))} | "
                    f"{_markdown_code(row.get('streak_source'))} | "
                    f"{_markdown_cell(workflow)} | "
                    f"{_markdown_cell(local_trigger)} | "
                    f"{blockers} |"
                )
            lines.append("")
        if field_rows:
            lines.extend(
                [
                    "| Field | Required | Check | Pass | Missing | Placeholder | Owner Note |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for row in field_rows:
                lines.append(
                    "| "
                    f"{_markdown_code(row.get('field'))} | "
                    f"{_markdown_cell(row.get('required_value'))} | "
                    f"{_markdown_code(row.get('check'))} | "
                    f"{_markdown_bool(row.get('check_pass'))} | "
                    f"{_markdown_bool(row.get('missing'))} | "
                    f"{_markdown_bool(row.get('placeholder'))} | "
                    f"{_markdown_cell(row.get('owner_note'))} |"
                )
            lines.append("")
    if not any_details:
        lines.append("No open intake details.")
    return lines


def _markdown_owner_commands(payload: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Owner Commands",
        "",
        "| Owner | Reproduction Commands | Verification Commands |",
        "|---|---|---|",
    ]
    for packet in payload["owner_packets"]:
        reproduction = "<br>".join(_markdown_code(item) for item in packet.get("reproduction_commands", []))
        verification = "<br>".join(_markdown_code(item) for item in packet.get("verification_commands", []))
        lines.append(
            f"| `{packet['owner']}` | {reproduction or 'none'} | {verification or 'none'} |"
        )
    return lines


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Owner Evidence Request Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['summary']['evidence_closure_pass']}`",
        f"- `expected_intake_open_blocker_count`: `{payload['summary']['expected_intake_open_blocker_count']}`",
        "",
        "| Owner | State | Blockers | Next Actions | Expected Intake |",
        "|---|---|---|---|---|",
    ]
    for packet in payload["owner_packets"]:
        blockers = "<br>".join(f"`{item}`" for item in packet["blocker_ids"]) or "none"
        actions = "<br>".join(str(item) for item in packet["next_actions"]) or "No open owner evidence requests."
        intake_paths = "<br>".join(f"`{item}`" for item in packet["expected_intake_paths"]) or "none"
        intake_blockers = "<br>".join(f"`{item}`" for item in packet.get("intake_current_blockers", []))
        intake = intake_paths if not intake_blockers else f"{intake_paths}<br>Current blockers: {intake_blockers}"
        lines.append(
            f"| `{packet['owner']}` | `{packet['request_state']}` | {blockers} | {actions} | {intake} |"
        )
    lines.extend(_markdown_intake_details(payload))
    lines.extend(_markdown_owner_commands(payload))
    lines.extend(["", payload["claim_boundary"]])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-register", type=Path, default=DEFAULT_ACTION_REGISTER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(action_register=args.action_register)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
