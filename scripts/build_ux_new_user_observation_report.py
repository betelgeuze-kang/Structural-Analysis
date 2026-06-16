#!/usr/bin/env python3
"""Validate human new-user sample workflow observation evidence for the PM UX gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ux-new-user-observation-report.v1"
DEFAULT_OBSERVATION = Path("implementation/phase1/release_evidence/productization/ux_new_user_observation.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
ACCEPTED_DECISIONS = {"accepted", "approved", "pass", "signed", "approved_for_release"}
PLACEHOLDER_MARKERS = ("TODO", "TBD", "PLACEHOLDER", "TEMPLATE", "REPLACE_ME", "OWNER_INPUT_REQUIRED")
REQUIRED_FIELDS = (
    "contract_pass",
    "participant_role",
    "new_to_product",
    "sample_project_id",
    "workflow_scope",
    "observer",
    "started_at_utc",
    "completed_at_utc",
    "completion_minutes",
    "blocker_count",
    "evidence_ref",
    "approval_decision",
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


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _field_present(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _looks_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    upper = value.strip().upper()
    return bool(not upper or any(marker in upper for marker in PLACEHOLDER_MARKERS))


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def build_report(
    *,
    observation_path: Path = DEFAULT_OBSERVATION,
    max_completion_minutes: float = 30.0,
) -> dict[str, Any]:
    observation = _load_json(observation_path)
    missing_fields = [field for field in REQUIRED_FIELDS if not _field_present(observation, field)]
    placeholder_fields = [field for field in REQUIRED_FIELDS if _looks_placeholder(observation.get(field))]
    completion_minutes = _as_float(observation.get("completion_minutes"))
    decision = str(observation.get("approval_decision", "")).strip().lower()
    participant_role = str(observation.get("participant_role", "")).strip().lower()
    new_to_product = observation.get("new_to_product") is True
    blocker_count = _as_int(observation.get("blocker_count"), 1)

    checks = {
        "observation_file_present": observation_path.exists(),
        "contract_signal_pass": _reason_pass(observation),
        "required_fields_present": not missing_fields,
        "placeholder_values_absent": not placeholder_fields,
        "participant_role_new_user_pass": participant_role in {"new_user", "first_time_user", "pilot_user"},
        "new_to_product_pass": new_to_product,
        "completion_minutes_present": completion_minutes is not None,
        "completion_30min_pass": bool(completion_minutes is not None and completion_minutes <= max_completion_minutes),
        "blocker_count_zero_pass": blocker_count == 0,
        "approval_decision_pass": decision in ACCEPTED_DECISIONS,
    }
    blockers = [
        *(["observation_file_missing"] if not checks["observation_file_present"] else []),
        *(["contract_signal_not_pass"] if not checks["contract_signal_pass"] else []),
        *(["required_fields_missing"] if not checks["required_fields_present"] else []),
        *(["placeholder_values_present"] if not checks["placeholder_values_absent"] else []),
        *(["participant_not_new_user"] if not checks["participant_role_new_user_pass"] else []),
        *(["new_to_product_not_confirmed"] if not checks["new_to_product_pass"] else []),
        *(["completion_minutes_missing"] if not checks["completion_minutes_present"] else []),
        *(["completion_gt_30min"] if completion_minutes is not None and not checks["completion_30min_pass"] else []),
        *(["blocking_usability_issue_present"] if not checks["blocker_count_zero_pass"] else []),
        *(["approval_decision_not_accepted"] if not checks["approval_decision_pass"] else []),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_UX_NEW_USER_OBSERVATION_REQUIRED",
        "observation_path": str(observation_path),
        "checks": checks,
        "blockers": blockers,
        "summary_line": (
            f"UX new-user observation: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"completion={completion_minutes if completion_minutes is not None else 'missing'}/{max_completion_minutes} min | "
            f"blockers={blocker_count}"
        ),
        "summary": {
            "completion_minutes": completion_minutes,
            "max_completion_minutes": max_completion_minutes,
            "participant_role": participant_role,
            "new_to_product": new_to_product,
            "blocker_count": blocker_count,
            "approval_decision": decision,
            "missing_fields": missing_fields,
            "placeholder_fields": placeholder_fields,
            "owner_action": (
                "Attach a human new-user observation record for the sample project workflow, including "
                "participant status, observer, timestamps, completion minutes, blocker count, evidence "
                "reference, and accepted release decision."
            ),
        },
        "required_fields": list(REQUIRED_FIELDS),
        "validation_commands": [
            f"python3 scripts/build_ux_new_user_observation_report.py --out {DEFAULT_OUT}",
            "python3 scripts/build_ux_new_user_observation_intake_packet.py "
            "--out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json",
            "python3 scripts/report_pm_release_gate.py "
            "--out implementation/phase1/release_evidence/productization/pm_release_gate_report.json "
            "--out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        ],
        "claim_boundary": (
            "This report validates a human new-user observation record. Automated browser rehearsal evidence "
            "does not satisfy the PM UX release-area gate by itself."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# UX New-User Observation Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `observation_path`: `{payload['observation_path']}`",
        "",
        "## Required Fields",
        "",
    ]
    for field in payload["required_fields"]:
        lines.append(f"- `{field}`")
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, default=DEFAULT_OBSERVATION)
    parser.add_argument("--max-completion-minutes", type=float, default=30.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        observation_path=args.observation,
        max_completion_minutes=float(args.max_completion_minutes),
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
