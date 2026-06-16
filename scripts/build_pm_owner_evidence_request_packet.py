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


def _owner_sort_key(owner: str) -> tuple[int, str]:
    try:
        return (OWNER_ORDER.index(owner), owner)
    except ValueError:
        return (len(OWNER_ORDER), owner)


def _request_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence_artifacts = _as_dict(row.get("evidence_artifacts"))
    handoff = _as_dict(row.get("handoff"))
    expected_intake_artifact = str(handoff.get("expected_intake_artifact", "") or "")
    expected_intake_path = str(evidence_artifacts.get(expected_intake_artifact, "") or "")
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
        "external_input_required": any(row["external_input_required"] for row in rows),
        "owner_input_required": any(row["owner_input_required"] for row in rows),
        "incomplete_blockers": incomplete,
        "request_rows": rows,
    }


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


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Owner Evidence Request Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        "",
        "| Owner | State | Blockers | Next Actions | Expected Intake |",
        "|---|---|---|---|---|",
    ]
    for packet in payload["owner_packets"]:
        blockers = "<br>".join(f"`{item}`" for item in packet["blocker_ids"]) or "none"
        actions = "<br>".join(str(item) for item in packet["next_actions"]) or "No open owner evidence requests."
        intake = "<br>".join(f"`{item}`" for item in packet["expected_intake_paths"]) or "none"
        lines.append(
            f"| `{packet['owner']}` | `{packet['request_state']}` | {blockers} | {actions} | {intake} |"
        )
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
