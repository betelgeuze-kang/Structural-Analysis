#!/usr/bin/env python3
"""Build an owner-facing customer shadow evidence intake packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "customer-shadow-evidence-intake-packet.v1"
DEFAULT_SCHEMA = Path("implementation/phase1/customer_shadow_evidence.schema.json")
DEFAULT_TEMPLATE = Path("docs/templates/customer_shadow_evidence.template.json")
DEFAULT_STATUS = Path("implementation/phase1/customer_shadow_evidence_status.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/customer_shadow_evidence_intake_packet.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")


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


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _slot(case_index: int, template_path: Path, evidence_dir: str) -> dict[str, Any]:
    case_id = f"customer-shadow-case-{case_index:03d}"
    evidence_path = f"{evidence_dir}/{case_id}.json"
    return {
        "slot_id": case_id,
        "required": True,
        "status": "owner_input_required",
        "evidence_path": evidence_path,
        "source_template": str(template_path),
        "owner_actions": [
            "copy template without committing customer raw data",
            "replace every OWNER_INPUT_REQUIRED value with derived evidence metadata",
            "keep raw_data_retained_by_customer=true",
            "keep redistribution_allowed=false",
            "attach reviewer_decision PASS, REVIEW, or FAIL",
            "run validator and attach only the metadata JSON when customer permits derived evidence storage",
        ],
        "validation_command": (
            "python3 implementation/phase1/validate_customer_shadow_evidence.py "
            f"--evidence {evidence_path} --json --fail-blocked"
        ),
    }


def build_packet(
    *,
    schema_path: Path = DEFAULT_SCHEMA,
    template_path: Path = DEFAULT_TEMPLATE,
    status_path: Path = DEFAULT_STATUS,
    min_completed_cases: int | None = None,
    target_completed_cases: int | None = None,
) -> dict[str, Any]:
    schema = _load_json(schema_path)
    template = _load_json(template_path)
    status = _load_json(status_path)
    status_summary = _as_dict(status.get("summary"))
    evidence_dir = str(status.get("evidence_dir") or "implementation/phase1/customer_shadow_evidence")
    min_cases = int(min_completed_cases or _as_int(status_summary.get("min_completed_shadow_cases"), 3))
    target_cases = int(target_completed_cases or _as_int(status_summary.get("target_completed_shadow_cases"), 5))
    slot_count = max(min_cases, target_cases)
    required_fields = [str(field) for field in schema.get("required_fields", [])]
    fixed_values = _as_dict(schema.get("fixed_values"))
    allowed_decisions = [str(value) for value in schema.get("allowed_reviewer_decisions", [])]
    slots = [_slot(idx, template_path, evidence_dir) for idx in range(1, slot_count + 1)]
    checks = {
        "schema_present": schema_path.exists(),
        "template_present": template_path.exists(),
        "status_present": status_path.exists(),
        "required_fields_present": bool(required_fields),
        "template_has_required_fields": all(field in template for field in required_fields),
        "raw_data_policy_fixed": fixed_values.get("raw_data_retained_by_customer") is True
        and fixed_values.get("redistribution_allowed") is False,
        "reviewer_decisions_present": bool({"PASS", "REVIEW", "FAIL"} <= set(allowed_decisions)),
        "intake_slot_count_covers_target": slot_count >= target_cases >= min_cases,
        "current_status_blocked_until_evidence_attached": status.get("contract_pass") is not True,
    }
    blockers = [key for key, passed in checks.items() if not passed]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[schema_path, template_path, status_path],
            reused_evidence=True,
            reuse_policy="intake_packet_rebuilt_from_schema_template_and_current_shadow_status",
        ),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_CUSTOMER_SHADOW_INTAKE_PACKET_INCOMPLETE",
        "schema": str(schema_path),
        "template": str(template_path),
        "status": str(status_path),
        "summary": {
            "current_completed_shadow_case_count": _as_int(status_summary.get("completed_shadow_case_count"), 0),
            "min_completed_shadow_cases": min_cases,
            "target_completed_shadow_cases": target_cases,
            "intake_slot_count": slot_count,
            "required_field_count": len(required_fields),
            "allowed_reviewer_decisions": allowed_decisions,
            "current_status_contract_pass": status.get("contract_pass"),
        },
        "checks": checks,
        "blockers": blockers,
        "intake_slots": slots,
        "commands": {
            "validate_one_evidence_file": (
                "python3 implementation/phase1/validate_customer_shadow_evidence.py "
                "--evidence <filled-customer-shadow-evidence.json> --json --fail-blocked"
            ),
            "refresh_status": "python3 implementation/phase1/check_customer_shadow_evidence_status.py --json",
            "refresh_evidence_console_scope": "python3 scripts/build_evidence_console_scope_status.py --json",
        },
        "claim_boundary": (
            "This packet creates owner-input slots and validation commands only. It does not create "
            "customer shadow evidence, ingest customer raw data, or close the 3/5 completed-project target. "
            "Each slot must be filled with real customer-retained derived metadata and pass the validator."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Customer Shadow Evidence Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `current_completed_shadow_case_count`: "
        f"`{payload['summary']['current_completed_shadow_case_count']}`",
        f"- `current_status_contract_pass`: `{payload['summary']['current_status_contract_pass']}`",
        f"- `target_completed_shadow_cases`: `{payload['summary']['target_completed_shadow_cases']}`",
        f"- `claim_boundary`: {payload['claim_boundary']}",
        "",
        "| Slot | Status | Evidence Path |",
        "|---|---|---|",
    ]
    for row in payload["intake_slots"]:
        lines.append(f"| `{row['slot_id']}` | `{row['status']}` | `{row['evidence_path']}` |")
    lines.append("")
    lines.append("## Commands")
    lines.append("")
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--min-completed-cases", type=int)
    parser.add_argument("--target-completed-cases", type=int)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(
        schema_path=args.schema,
        template_path=args.template,
        status_path=args.status,
        min_completed_cases=args.min_completed_cases,
        target_completed_cases=args.target_completed_cases,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else (
            "customer-shadow-evidence-intake-packet: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"slots={payload['summary']['intake_slot_count']} | "
            f"current={payload['summary']['current_completed_shadow_case_count']}/"
            f"{payload['summary']['min_completed_shadow_cases']}"
        )
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
