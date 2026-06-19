#!/usr/bin/env python3
"""Check customer completed-project shadow evidence readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_customer_shadow_evidence import (  # noqa: E402
    DEFAULT_SCHEMA,
    validate_payload,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "customer-shadow-evidence-status.v1"
DEFAULT_EVIDENCE_DIR = Path("implementation/phase1/customer_shadow_evidence")
DEFAULT_VALIDATOR = Path("implementation/phase1/validate_customer_shadow_evidence.py")
DEFAULT_OUT = Path("implementation/phase1/customer_shadow_evidence_status.json")
DEFAULT_MIN_COMPLETED_CASES = 3
DEFAULT_TARGET_COMPLETED_CASES = 5


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _evidence_paths(evidence_dir: Path) -> list[Path]:
    if not evidence_dir.exists():
        return []
    return sorted(path for path in evidence_dir.glob("*.json") if path.is_file())


def _row(path: Path, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    validation = validate_payload(payload, schema)
    return {
        "path": str(path),
        "case_id": str(payload.get("case_id", "") or ""),
        "project_status": str(payload.get("project_status", "") or ""),
        "structure_family": str(payload.get("structure_family", "") or ""),
        "reference_solver": str(payload.get("reference_solver", "") or ""),
        "reference_solver_version": str(payload.get("reference_solver_version", "") or ""),
        "reviewer_decision": str(payload.get("reviewer_decision", "") or ""),
        "raw_data_retained_by_customer": payload.get("raw_data_retained_by_customer"),
        "redistribution_allowed": payload.get("redistribution_allowed"),
        "contract_pass": bool(validation.get("contract_pass", False)),
        "reason_code": str(validation.get("reason_code", "") or ""),
        "blockers": validation.get("blockers", []),
    }


def _completed_case_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["contract_pass"]
        and row["project_status"] == "completed"
        and row["raw_data_retained_by_customer"] is True
        and row["redistribution_allowed"] is False
    ]


def build_status(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    schema_path: Path = DEFAULT_SCHEMA,
    min_completed_cases: int = DEFAULT_MIN_COMPLETED_CASES,
    target_completed_cases: int = DEFAULT_TARGET_COMPLETED_CASES,
) -> dict[str, Any]:
    schema = _load_json(schema_path)
    paths = _evidence_paths(evidence_dir)
    rows = [_row(path, _load_json(path), schema) for path in paths]
    completed_rows = _completed_case_rows(rows)
    completed_case_ids = [row["case_id"] for row in completed_rows if row["case_id"]]
    duplicate_completed_case_ids = sorted(
        {case_id for case_id in completed_case_ids if completed_case_ids.count(case_id) > 1}
    )
    invalid_rows = [row for row in rows if not row["contract_pass"]]
    raw_policy_violations = [
        row["path"]
        for row in rows
        if row["raw_data_retained_by_customer"] is not True or row["redistribution_allowed"] is not False
    ]
    checks = {
        "schema_present": schema_path.exists(),
        "evidence_directory_present": evidence_dir.exists(),
        "min_completed_shadow_cases_pass": len(completed_rows) >= min_completed_cases,
        "target_completed_shadow_cases_pass": len(completed_rows) >= target_completed_cases,
        "all_evidence_files_valid_pass": not invalid_rows,
        "completed_case_ids_unique_pass": not duplicate_completed_case_ids,
        "raw_data_policy_pass": not raw_policy_violations,
    }
    blockers: list[str] = []
    if not checks["schema_present"]:
        blockers.append("schema_missing")
    if not checks["evidence_directory_present"]:
        blockers.append("evidence_directory_missing")
    if not checks["min_completed_shadow_cases_pass"]:
        blockers.append("completed_shadow_case_count_below_minimum")
    if invalid_rows:
        blockers.append("invalid_customer_shadow_evidence_files_present")
    if duplicate_completed_case_ids:
        blockers.append("duplicate_completed_shadow_case_ids")
    if raw_policy_violations:
        blockers.append("raw_data_policy_violation")

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[schema_path, DEFAULT_VALIDATOR, evidence_dir],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_existing_shadow_evidence_schema_and_directory_metadata",
            repo_root=REPO_ROOT,
        ),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_CUSTOMER_SHADOW_EVIDENCE_INCOMPLETE",
        "evidence_dir": str(evidence_dir),
        "schema": str(schema_path),
        "summary": {
            "evidence_file_count": len(rows),
            "valid_evidence_file_count": len(rows) - len(invalid_rows),
            "invalid_evidence_file_count": len(invalid_rows),
            "completed_shadow_case_count": len(completed_rows),
            "min_completed_shadow_cases": min_completed_cases,
            "target_completed_shadow_cases": target_completed_cases,
            "completed_shadow_case_ids": completed_case_ids,
            "duplicate_completed_shadow_case_ids": duplicate_completed_case_ids,
            "raw_policy_violation_count": len(raw_policy_violations),
        },
        "checks": checks,
        "blockers": blockers,
        "evidence_rows": rows,
        "claim_boundary": (
            "Customer shadow evidence status counts validated completed-project evidence metadata only. "
            "It must not create synthetic customer cases, ingest customer raw data, or treat missing "
            "customer-retained evidence as closed. PASS requires at least the configured minimum of "
            "completed-project shadow cases with raw_data_retained_by_customer=true and redistribution_allowed=false."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--min-completed-cases", type=int, default=DEFAULT_MIN_COMPLETED_CASES)
    parser.add_argument("--target-completed-cases", type=int, default=DEFAULT_TARGET_COMPLETED_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-write", action="store_true", help="Print the status without writing --out.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = build_status(
        evidence_dir=args.evidence_dir,
        schema_path=args.schema,
        min_completed_cases=args.min_completed_cases,
        target_completed_cases=args.target_completed_cases,
    )
    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = payload["summary"]
        print(
            "customer-shadow-evidence-status: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"cases={summary['completed_shadow_case_count']}/{summary['min_completed_shadow_cases']} | "
            f"files={summary['valid_evidence_file_count']}/{summary['evidence_file_count']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
