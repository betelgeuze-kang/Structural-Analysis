#!/usr/bin/env python3
"""Validate a fresh full-validation lane receipt against the JSON Schema contract."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


SCHEMA_VERSION = "fresh-validation-receipt-validation.v1"
DEFAULT_SCHEMA = Path("implementation/phase1/fresh_validation_receipt.schema.json")
PLACEHOLDER_MARKERS = ("OWNER_INPUT_REQUIRED", "TODO", "PLACEHOLDER", "FIXME")
COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
SHA256_REF_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


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


def _has_empty_leaf(value: Any) -> bool:
    if isinstance(value, str):
        return not bool(value.strip())
    if isinstance(value, dict):
        return any(_has_empty_leaf(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_empty_leaf(item) for item in value)
    return False


def _is_iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_payload(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        blockers.append(f"schema_invalid:{exc.message}")
        return {
            "schema_version": SCHEMA_VERSION,
            "contract_pass": False,
            "reason_code": "ERR_FRESH_VALIDATION_RECEIPT_INVALID",
            "blockers": blockers,
            "summary": {},
            "claim_boundary": str(schema.get("claim_boundary", "")),
        }

    validator = Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    for err in schema_errors:
        path = "/".join(str(part) for part in err.absolute_path) or "<root>"
        if err.validator == "required":
            missing_fields = [str(value) for value in err.validator_value] if isinstance(err.validator_value, list) else []
            for missing_field in missing_fields:
                blockers.append(f"missing_field:{missing_field}")
        else:
            blockers.append(f"schema_violation:{path}:{err.message}")

    expected = {
        "schema_version": "fresh-validation-receipt.v1",
        "reason_code": "PASS",
        "reused_evidence": False,
        "contract_pass": True,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            blockers.append(f"fixed_value_mismatch:{field}")

    for field in ("lane_id", "runner", "generated_at", "source_commit_sha", "engine_version", "validation_command", "claim_boundary"):
        if field in payload and (not _value_present(payload.get(field)) or _has_empty_leaf(payload.get(field))):
            blockers.append(f"empty_required_field:{field}")

    generated_at = str(payload.get("generated_at", "") or "")
    if generated_at and not _is_iso_datetime(generated_at):
        blockers.append("generated_at_not_iso_datetime")

    input_checksums = payload.get("input_checksums")
    if not isinstance(input_checksums, dict) or not input_checksums:
        blockers.append("empty_required_field:input_checksums")
    elif _has_empty_leaf(input_checksums):
        blockers.append("empty_required_field:input_checksums")
    else:
        for key, value in input_checksums.items():
            if not isinstance(value, str) or not value.strip():
                blockers.append(f"empty_required_field:input_checksums.{key}")
            elif not SHA256_REF_RE.match(value):
                blockers.append(f"input_checksums.{key}:not_sha256")

    source_commit_sha = str(payload.get("source_commit_sha", "") or "")
    if source_commit_sha and not COMMIT_SHA_RE.match(source_commit_sha):
        blockers.append("source_commit_sha_not_commit_sha")

    receipt_artifacts = payload.get("receipt_artifacts")
    if not isinstance(receipt_artifacts, list) or not receipt_artifacts:
        blockers.append("receipt_artifacts_missing_or_empty")
    else:
        for index, artifact in enumerate(receipt_artifacts):
            if not isinstance(artifact, dict):
                blockers.append(f"receipt_artifacts[{index}]:not_object")
                continue
            path_value = artifact.get("path")
            sha_value = artifact.get("sha256")
            if not isinstance(path_value, str) or not path_value.strip():
                blockers.append(f"receipt_artifacts[{index}].path:empty")
            if not isinstance(sha_value, str) or not SHA256_REF_RE.match(sha_value or ""):
                blockers.append(f"receipt_artifacts[{index}].sha256:not_sha256")

    summary = payload.get("summary")
    if not isinstance(summary, dict) or not summary:
        blockers.append("empty_required_field:summary")
    else:
        case_count = summary.get("case_count")
        passed_count = summary.get("passed_case_count")
        if not isinstance(case_count, int) or case_count < 0:
            blockers.append("summary.case_count:not_non_negative_integer")
        if not isinstance(passed_count, int) or passed_count < 0:
            blockers.append("summary.passed_case_count:not_non_negative_integer")
        if isinstance(case_count, int) and isinstance(passed_count, int) and passed_count > case_count:
            blockers.append("summary.passed_case_count_exceeds_case_count")

    if _has_placeholder(payload):
        blockers.append("placeholder_marker_present")

    blockers = sorted(set(blockers))

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_FRESH_VALIDATION_RECEIPT_INVALID",
        "blockers": blockers,
        "summary": {
            "schema_violation_count": len([b for b in blockers if b.startswith("schema_violation:")]),
            "fixed_mismatch_count": len([b for b in blockers if b.startswith("fixed_value_mismatch:")]),
            "empty_required_field_count": len([b for b in blockers if b.startswith("empty_required_field:")]),
            "placeholder_present": "placeholder_marker_present" in blockers,
            "source_commit_sha_pass": bool(source_commit_sha and COMMIT_SHA_RE.match(source_commit_sha)),
            "reused_evidence": payload.get("reused_evidence"),
            "contract_pass_field": payload.get("contract_pass"),
            "reason_code_field": payload.get("reason_code"),
            "lane_id": payload.get("lane_id"),
        },
        "claim_boundary": str(schema.get("claim_boundary", "")),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_payload(_load_json(args.receipt), _load_json(args.schema))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "fresh-validation-receipt: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
