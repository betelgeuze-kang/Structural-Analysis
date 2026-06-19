#!/usr/bin/env python3
"""Validate customer shadow evidence without ingesting raw customer data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA = Path("implementation/phase1/customer_shadow_evidence.schema.json")
PLACEHOLDER_MARKERS = ("TODO", "OWNER_INPUT_REQUIRED", "PLACEHOLDER", "<", ">")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        upper = value.upper()
        return any(marker in upper for marker in PLACEHOLDER_MARKERS)
    if isinstance(value, dict):
        return any(_has_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    return False


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return True


def validate_payload(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    required = [str(field) for field in schema.get("required_fields", [])]
    missing = [field for field in required if field not in payload]
    empty_required = [field for field in required if field in payload and not _value_present(payload.get(field))]
    fixed_values = schema.get("fixed_values") if isinstance(schema.get("fixed_values"), dict) else {}
    fixed_mismatches = [
        field
        for field, expected in fixed_values.items()
        if field in payload and payload.get(field) != expected
    ]
    allowed_decisions = {str(value) for value in schema.get("allowed_reviewer_decisions", [])}
    reviewer_decision = str(payload.get("reviewer_decision", ""))
    blockers: list[str] = []
    blockers.extend([f"missing_field:{field}" for field in missing])
    blockers.extend([f"empty_required_field:{field}" for field in empty_required])
    blockers.extend([f"fixed_value_mismatch:{field}" for field in fixed_mismatches])
    if reviewer_decision not in allowed_decisions:
        blockers.append("reviewer_decision_not_allowed")
    if not isinstance(payload.get("delta_metrics"), dict) or not payload.get("delta_metrics"):
        blockers.append("delta_metrics_missing_or_empty")
    if not isinstance(payload.get("residual_metrics"), dict) or not payload.get("residual_metrics"):
        blockers.append("residual_metrics_missing_or_empty")
    if _has_placeholder(payload):
        blockers.append("placeholder_marker_present")
    checksum = str(payload.get("reference_output_checksum", "") or "")
    if checksum and not checksum.startswith("sha256:"):
        blockers.append("reference_output_checksum_not_sha256")

    return {
        "schema_version": "customer-shadow-evidence-validation.v1",
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_CUSTOMER_SHADOW_EVIDENCE_INVALID",
        "blockers": blockers,
        "summary": {
            "required_field_count": len(required),
            "missing_field_count": len(missing),
            "empty_required_field_count": len(empty_required),
            "fixed_mismatch_count": len(fixed_mismatches),
            "reviewer_decision": reviewer_decision,
            "raw_data_retained_by_customer": payload.get("raw_data_retained_by_customer"),
            "redistribution_allowed": payload.get("redistribution_allowed"),
        },
        "claim_boundary": str(schema.get("claim_boundary", "")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = validate_payload(_load_json(args.evidence), _load_json(args.schema))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "customer-shadow-evidence: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
