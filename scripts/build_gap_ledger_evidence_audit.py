#!/usr/bin/env python3
"""Audit commercial/AI gap-ledger rows for evidence-backed closure boundaries."""

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


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_LEDGER_STATUS = PRODUCTIZATION / "commercial_gap_ledger_status.json"
DEFAULT_OUT = PRODUCTIZATION / "gap_ledger_evidence_audit.json"
SCHEMA_VERSION = "gap-ledger-evidence-audit.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _has_evidence(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence")
    return isinstance(evidence, dict) and bool(evidence)


def _has_claim_boundary(row: dict[str, Any]) -> bool:
    return bool(str(row.get("claim_boundary", "")).strip())


def _has_next_gate(row: dict[str, Any]) -> bool:
    return bool(str(row.get("next_gate", "")).strip())


def _row_id(row: dict[str, Any]) -> str:
    return str(row.get("id", ""))


def _closure_requirements(row: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = _as_dict(row.get("evidence"))
    requirements = [
        item
        for item in _as_list(evidence.get("closure_requirements"))
        if isinstance(item, dict)
    ]
    requirements.extend(
        item
        for item in _as_list(evidence.get("external_closure_requirements"))
        if isinstance(item, dict)
    )
    return requirements


def _requirement_passed(requirement: dict[str, Any]) -> bool:
    if "passed" in requirement:
        return requirement.get("passed") is True
    if "receipt_attached" in requirement:
        return requirement.get("receipt_attached") is True
    return False


def _closure_requirement_summary(row: dict[str, Any]) -> dict[str, Any]:
    requirements = _closure_requirements(row)
    failed = [item for item in requirements if not _requirement_passed(item)]
    passed_count = len(requirements) - len(failed)
    return {
        "closure_requirement_count": len(requirements),
        "closure_requirement_pass_count": passed_count,
        "closure_requirement_fail_count": len(failed),
        "closure_requirement_failed_ids": [
            str(item.get("id", "")) for item in failed if str(item.get("id", ""))
        ],
    }


def build_gap_ledger_evidence_audit(
    *,
    repo_root: Path = ROOT,
    ledger_status_path: Path = DEFAULT_LEDGER_STATUS,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    ledger = _load_json(repo_root, ledger_status_path)
    rows = [row for row in _as_list(ledger.get("rows")) if isinstance(row, dict)]
    closed_rows = [row for row in rows if str(row.get("status")) == "closed" or row.get("closed") is True]
    nonclosed_rows = [row for row in rows if row not in closed_rows]

    closed_missing_evidence = [_row_id(row) for row in closed_rows if not _has_evidence(row)]
    closed_with_blockers = [_row_id(row) for row in closed_rows if _as_list(row.get("blockers"))]
    closed_missing_claim_boundary = [_row_id(row) for row in closed_rows if not _has_claim_boundary(row)]
    closed_missing_boundary_or_next_gate = [
        _row_id(row) for row in closed_rows if not _has_claim_boundary(row) and not _has_next_gate(row)
    ]
    nonclosed_missing_blockers = [_row_id(row) for row in nonclosed_rows if not _as_list(row.get("blockers"))]
    nonclosed_missing_claim_boundary = [_row_id(row) for row in nonclosed_rows if not _has_claim_boundary(row)]
    nonclosed_missing_evidence = [_row_id(row) for row in nonclosed_rows if not _has_evidence(row)]

    blockers = [
        *[f"closed_row_missing_evidence:{row_id}" for row_id in closed_missing_evidence],
        *[f"closed_row_has_blockers:{row_id}" for row_id in closed_with_blockers],
        *[
            f"closed_row_missing_boundary_or_next_gate:{row_id}"
            for row_id in closed_missing_boundary_or_next_gate
        ],
        *[f"nonclosed_row_missing_blockers:{row_id}" for row_id in nonclosed_missing_blockers],
        *[f"nonclosed_row_missing_claim_boundary:{row_id}" for row_id in nonclosed_missing_claim_boundary],
        *[f"nonclosed_row_missing_evidence:{row_id}" for row_id in nonclosed_missing_evidence],
    ]
    contract_pass = not blockers

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                ledger_status_path,
                Path("docs/commercial-structural-solver-product-gap-ledger.md"),
                Path("docs/structural-analysis-ai-engine-gap-ledger.md"),
                Path("scripts/build_gap_ledger_evidence_audit.py"),
            ],
            reused_evidence=True,
            reuse_policy="gap_ledger_evidence_audit_reads_existing_gap_ledger_status_without_creating_closure",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "full_gap_ledger_ready": bool(ledger.get("full_gap_ledger_ready") is True),
        "ledger_status": str(ledger.get("status", "missing")),
        "row_count": len(rows),
        "closed_row_count": len(closed_rows),
        "nonclosed_row_count": len(nonclosed_rows),
        "closed_evidence_coverage": {
            "closed_row_count": len(closed_rows),
            "closed_rows_with_evidence_count": len(closed_rows) - len(closed_missing_evidence),
            "closed_rows_without_blockers_count": len(closed_rows) - len(closed_with_blockers),
            "closed_missing_evidence_ids": closed_missing_evidence,
            "closed_with_blockers_ids": closed_with_blockers,
            "closed_missing_claim_boundary_ids": closed_missing_claim_boundary,
            "closed_missing_boundary_or_next_gate_ids": closed_missing_boundary_or_next_gate,
            "claim_boundary_advisory": (
                "Closed rows may rely on next_gate for residual scope guidance today, "
                "but explicit row-level claim boundaries are listed for follow-up."
            ),
        },
        "nonclosed_visibility": {
            "nonclosed_row_count": len(nonclosed_rows),
            "nonclosed_rows_with_blockers_count": len(nonclosed_rows) - len(nonclosed_missing_blockers),
            "nonclosed_rows_with_claim_boundary_count": len(nonclosed_rows) - len(nonclosed_missing_claim_boundary),
            "nonclosed_rows_with_evidence_count": len(nonclosed_rows) - len(nonclosed_missing_evidence),
            "nonclosed_missing_blocker_ids": nonclosed_missing_blockers,
            "nonclosed_missing_claim_boundary_ids": nonclosed_missing_claim_boundary,
            "nonclosed_missing_evidence_ids": nonclosed_missing_evidence,
        },
        "row_outcomes": [
            {
                "id": _row_id(row),
                "ledger": str(row.get("ledger", "")),
                "status": str(row.get("status", "")),
                "closed": bool(row.get("closed") is True or row.get("status") == "closed"),
                "evidence_present": _has_evidence(row),
                "blocker_count": len(_as_list(row.get("blockers"))),
                "claim_boundary_present": _has_claim_boundary(row),
                "next_gate_present": _has_next_gate(row),
                "evidence_key_count": len(_as_dict(row.get("evidence"))),
                **_closure_requirement_summary(row),
            }
            for row in rows
        ],
        "blockers": blockers,
        "summary_line": (
            "Gap ledger evidence audit: "
            f"{'READY' if contract_pass else 'BLOCKED'} | closed_evidence="
            f"{len(closed_rows) - len(closed_missing_evidence)}/{len(closed_rows)} | "
            f"nonclosed_boundaries={len(nonclosed_rows) - len(nonclosed_missing_claim_boundary)}/{len(nonclosed_rows)}"
        ),
        "claim_boundary": (
            "This audit verifies whether the current G1-G10 and AI-G1-AI-G10 ledger rows "
            "are represented with evidence, blockers, and claim-boundary visibility. It "
            "does not create authoritative evidence, close any row, create external "
            "receipts, prove commercial readiness, or override the source ledger status."
        ),
    }


def write_gap_ledger_evidence_audit(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    ledger_status_path: Path = DEFAULT_LEDGER_STATUS,
) -> dict[str, Any]:
    payload = build_gap_ledger_evidence_audit(repo_root=repo_root, ledger_status_path=ledger_status_path)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_gap_ledger_evidence_audit(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    ledger_status_path: Path = DEFAULT_LEDGER_STATUS,
) -> tuple[bool, str]:
    expected = build_gap_ledger_evidence_audit(repo_root=repo_root, ledger_status_path=ledger_status_path)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"gap_ledger_evidence_audit_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"gap_ledger_evidence_audit_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "gap_ledger_evidence_audit_mismatch"
    return True, "gap_ledger_evidence_audit_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ledger-status", type=Path, default=DEFAULT_LEDGER_STATUS)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_gap_ledger_evidence_audit(
            out_path=args.out,
            ledger_status_path=args.ledger_status,
        )
        print(f"Gap ledger evidence audit check: {message}")
        return 0 if ok else 1
    payload = write_gap_ledger_evidence_audit(out_path=args.out, ledger_status_path=args.ledger_status)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
