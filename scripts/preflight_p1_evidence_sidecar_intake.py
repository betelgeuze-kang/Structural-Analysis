#!/usr/bin/env python3
"""Preflight real EB receipt and RH closure evidence sidecars before promotion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p1_benchmark_breadth_status import (  # noqa: E402
    DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
)


SCHEMA_VERSION = "p1-evidence-sidecar-intake-preflight.v1"
EXTERNAL_EXPECTED_QUEUE_IDS = (
    "hardest_external_10case",
    "tpu_hffb",
    "peer_spd_hinge",
    "korean_public_structures",
)
EXTERNAL_WORK_ITEM_IDS = {
    "hardest_external_10case": "EB-001",
    "tpu_hffb": "EB-002",
    "peer_spd_hinge": "EB-003",
    "korean_public_structures": "EB-004",
}
RESIDUAL_EXPECTED_WORK_ITEM_IDS = ("RH-001", "RH-002", "RH-003")
ATTACHED_STATUSES = {"attached", "verified", "closed", "signed_attached"}
CLOSED_STATUSES = {"closed", "complete", "completed"}
PLACEHOLDER_VALUES = {"", "pending", "none", "null", "n/a", "na", "tbd", "todo"}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _updates(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_updates: Any = payload.get("updates", payload.get("residual_holdout_updates", payload))
    if isinstance(raw_updates, dict) and "residual_holdout_work_items" in raw_updates:
        raw_updates = raw_updates.get("residual_holdout_work_items", [])
    elif raw_updates is payload and isinstance(payload.get("queues"), dict):
        raw_updates = payload["queues"].get("residual_holdout_work_items", [])

    updates: dict[str, dict[str, Any]] = {}
    if isinstance(raw_updates, dict):
        for row_id, row in raw_updates.items():
            if isinstance(row, dict):
                updates[str(row_id)] = row
    elif isinstance(raw_updates, list):
        for row in raw_updates:
            if not isinstance(row, dict):
                continue
            for key in ("queue_id", "work_item_id", "category_id", "id"):
                row_id = str(row.get(key, "") or "").strip()
                if row_id:
                    updates[row_id] = row
                    break
    return updates


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_placeholder(value: Any) -> bool:
    return _text(value).lower() in PLACEHOLDER_VALUES


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _reference_exists(reference: str, *, repo_root: Path) -> bool:
    if _is_placeholder(reference):
        return False
    if _is_url(reference):
        return True
    path = Path(reference)
    if not path.is_absolute():
        path = repo_root / path
    return path.exists()


def _external_receipt_reference(row: dict[str, Any]) -> str:
    for key in ("receipt_url", "submission_receipt_url", "submission_receipt", "closure_evidence_path"):
        value = _text(row.get(key, ""))
        if not _is_placeholder(value):
            return value
    return ""


def _external_row(queue_id: str, row: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    receipt_status = _text(row.get("receipt_status", row.get("submission_receipt_status", ""))).lower()
    closure_status = _text(row.get("closure_evidence_status", "")).lower()
    receipt_reference = _external_receipt_reference(row)
    receipt_reference_exists = _reference_exists(receipt_reference, repo_root=repo_root)
    receipt_attached = bool(receipt_status in ATTACHED_STATUSES and receipt_reference_exists)
    closure_reference = _text(row.get("closure_evidence_path", "")) or receipt_reference
    closure_reference_exists = _reference_exists(closure_reference, repo_root=repo_root)
    closure_attached = bool(closure_status in ATTACHED_STATUSES and closure_reference_exists)
    missing: list[str] = []
    if receipt_status not in ATTACHED_STATUSES:
        missing.append("receipt_status_attached")
    if not receipt_reference_exists:
        missing.append("receipt_url_or_evidence_path")
    if closure_status not in ATTACHED_STATUSES:
        missing.append("closure_evidence_status_attached")
    return {
        "queue_id": queue_id,
        "work_item_id": _text(row.get("work_item_id", "")) or EXTERNAL_WORK_ITEM_IDS.get(queue_id, ""),
        "submission_id": _text(row.get("submission_id", "")),
        "receipt_status": receipt_status,
        "receipt_reference": receipt_reference,
        "receipt_reference_exists": receipt_reference_exists,
        "receipt_attached": receipt_attached,
        "closure_evidence_status": closure_status,
        "closure_evidence_reference": closure_reference,
        "closure_evidence_reference_exists": closure_reference_exists,
        "closure_evidence_attached": closure_attached,
        "last_checked_at_utc": _text(row.get("last_checked_at_utc", "")),
        "submitted_at_utc": _text(row.get("submitted_at_utc", "")),
        "missing_requirements": missing,
    }


def _residual_row(work_item_id: str, row: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    status = _text(row.get("status", "")).lower()
    closure_status = _text(row.get("closure_evidence_status", "")).lower()
    closure_reference = _text(row.get("closure_evidence_path", ""))
    closure_reference_exists = _reference_exists(closure_reference, repo_root=repo_root)
    closure_attached = bool(closure_status in ATTACHED_STATUSES and closure_reference_exists)
    closed = bool(status in CLOSED_STATUSES and closure_attached)
    missing: list[str] = []
    if status not in CLOSED_STATUSES:
        missing.append("status_closed")
    if closure_status not in ATTACHED_STATUSES:
        missing.append("closure_evidence_status_attached")
    if not closure_reference_exists:
        missing.append("closure_evidence_path_exists")
    return {
        "work_item_id": work_item_id,
        "owner": _text(row.get("owner", "")),
        "queue_status": _text(row.get("queue_status", "")),
        "status": status,
        "closure_evidence_required": _text(row.get("closure_evidence_required", "")),
        "closure_evidence_status": closure_status,
        "closure_evidence_reference": closure_reference,
        "closure_evidence_reference_exists": closure_reference_exists,
        "closure_evidence_attached": closure_attached,
        "closed": closed,
        "last_checked_at_utc": _text(row.get("last_checked_at_utc", "")),
        "closed_at_utc": _text(row.get("closed_at_utc", "")),
        "missing_requirements": missing,
    }


def build_preflight(
    *,
    external_benchmark_submission_updates: Path,
    residual_holdout_closure_updates: Path,
    repo_root: Path,
    structure_only: bool = False,
) -> dict[str, Any]:
    external_updates = _updates(_load_json(external_benchmark_submission_updates))
    residual_updates = _updates(_load_json(residual_holdout_closure_updates))

    external_rows = [
        _external_row(queue_id, external_updates.get(queue_id, {}), repo_root=repo_root)
        for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS
    ]
    residual_rows = [
        _residual_row(work_item_id, residual_updates.get(work_item_id, {}), repo_root=repo_root)
        for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS
    ]
    external_missing = [row["queue_id"] for row in external_rows if row["missing_requirements"]]
    residual_missing = [row["work_item_id"] for row in residual_rows if row["missing_requirements"]]
    external_structure_missing = [
        queue_id for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS if queue_id not in external_updates
    ]
    residual_structure_missing = [
        work_item_id for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS if work_item_id not in residual_updates
    ]
    summary = {
        "external_expected_queue_count": len(EXTERNAL_EXPECTED_QUEUE_IDS),
        "external_update_row_count": len(external_updates),
        "external_expected_rows_present": all(queue_id in external_updates for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS),
        "external_receipt_attached_count": sum(1 for row in external_rows if row["receipt_attached"]),
        "external_closure_evidence_attached_count": sum(1 for row in external_rows if row["closure_evidence_attached"]),
        "external_receipt_pending_count": sum(1 for row in external_rows if not row["receipt_attached"]),
        "residual_expected_work_item_count": len(RESIDUAL_EXPECTED_WORK_ITEM_IDS),
        "residual_update_row_count": len(residual_updates),
        "residual_expected_rows_present": all(
            work_item_id in residual_updates for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS
        ),
        "residual_closure_evidence_attached_count": sum(
            1 for row in residual_rows if row["closure_evidence_attached"]
        ),
        "residual_closed_count": sum(1 for row in residual_rows if row["closed"]),
        "residual_closure_pending_count": sum(1 for row in residual_rows if not row["closed"]),
    }
    evidence_contract_pass = bool(
        summary["external_expected_rows_present"]
        and summary["residual_expected_rows_present"]
        and summary["external_receipt_attached_count"] == summary["external_expected_queue_count"]
        and summary["external_closure_evidence_attached_count"] == summary["external_expected_queue_count"]
        and summary["residual_closed_count"] == summary["residual_expected_work_item_count"]
    )
    structure_contract_pass = bool(
        external_benchmark_submission_updates.exists()
        and residual_holdout_closure_updates.exists()
        and summary["external_expected_rows_present"]
        and summary["residual_expected_rows_present"]
    )
    summary["evidence_contract_pass"] = evidence_contract_pass
    summary["structure_only_contract_pass"] = structure_contract_pass
    evidence_blockers = [
        *(f"external_receipt_or_closure_pending:{queue_id}" for queue_id in external_missing),
        *(f"residual_closure_pending:{work_item_id}" for work_item_id in residual_missing),
    ]
    structure_blockers = [
        *(["external_sidecar_missing"] if not external_benchmark_submission_updates.exists() else []),
        *(["residual_sidecar_missing"] if not residual_holdout_closure_updates.exists() else []),
        *(f"external_expected_row_missing:{queue_id}" for queue_id in external_structure_missing),
        *(f"residual_expected_row_missing:{work_item_id}" for work_item_id in residual_structure_missing),
    ]
    contract_pass = structure_contract_pass if structure_only else evidence_contract_pass
    if evidence_contract_pass:
        reason_code = "PASS"
    elif structure_only and structure_contract_pass:
        reason_code = "PASS_STRUCTURE_ONLY_PENDING_EVIDENCE"
    elif structure_only:
        reason_code = "ERR_P1_EVIDENCE_SIDECAR_STRUCTURE_PENDING"
    else:
        reason_code = "ERR_P1_EVIDENCE_SIDECAR_INTAKE_PENDING"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_mode": "structure_only" if structure_only else "strict_evidence",
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "summary": summary,
        "blockers": structure_blockers if structure_only else evidence_blockers,
        "pending_evidence_blockers": evidence_blockers,
        "structure_blockers": structure_blockers,
        "external_benchmark_submission": external_rows,
        "residual_holdout": residual_rows,
        "artifacts": {
            "external_benchmark_submission_updates": str(external_benchmark_submission_updates),
            "external_benchmark_submission_updates_present": external_benchmark_submission_updates.exists(),
            "residual_holdout_closure_updates": str(residual_holdout_closure_updates),
            "residual_holdout_closure_updates_present": residual_holdout_closure_updates.exists(),
            "repo_root": str(repo_root),
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# P1 Evidence Sidecar Intake Preflight",
        "",
        f"- `contract_mode`: `{payload.get('contract_mode', 'strict_evidence')}`",
        f"- `contract_pass`: `{bool(payload['contract_pass'])}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `evidence_contract_pass`: `{bool(summary.get('evidence_contract_pass', payload['contract_pass']))}`",
        f"- `structure_only_contract_pass`: `{bool(summary.get('structure_only_contract_pass', payload['contract_pass']))}`",
        f"- `external_receipt_attached_count`: `{summary['external_receipt_attached_count']}/{summary['external_expected_queue_count']}`",
        f"- `external_closure_evidence_attached_count`: `{summary['external_closure_evidence_attached_count']}/{summary['external_expected_queue_count']}`",
        f"- `residual_closed_count`: `{summary['residual_closed_count']}/{summary['residual_expected_work_item_count']}`",
        f"- `residual_closure_evidence_attached_count`: `{summary['residual_closure_evidence_attached_count']}/{summary['residual_expected_work_item_count']}`",
        f"- `blockers`: `{', '.join(payload['blockers']) or 'none'}`",
        f"- `pending_evidence_blockers`: `{', '.join(payload.get('pending_evidence_blockers', [])) or 'none'}`",
        "",
        "## External Benchmark Submission",
        "",
        "| Queue | Receipt Status | Receipt Evidence | Closure Status | Missing |",
        "|---|---|---|---|---|",
    ]
    for row in payload["external_benchmark_submission"]:
        lines.append(
            f"| {row['queue_id']} | {row['receipt_status']} | {row['receipt_reference'] or 'pending'} | "
            f"{row['closure_evidence_status']} | {', '.join(row['missing_requirements']) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Residual Holdout",
            "",
            "| Work Item | Status | Closure Evidence | Missing |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["residual_holdout"]:
        lines.append(
            f"| {row['work_item_id']} | {row['status']} | {row['closure_evidence_reference'] or 'pending'} "
            f"({row['closure_evidence_status']}) | {', '.join(row['missing_requirements']) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-benchmark-submission-updates",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    )
    parser.add_argument(
        "--residual-holdout-closure-updates",
        type=Path,
        default=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-open", action="store_true")
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="Pass when the expected EB/RH sidecar rows exist, while still reporting pending evidence blockers.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_preflight(
        external_benchmark_submission_updates=args.external_benchmark_submission_updates,
        residual_holdout_closure_updates=args.residual_holdout_closure_updates,
        repo_root=args.repo_root,
        structure_only=args.structure_only,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        _write_json(args.out, payload)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(text if args.json else _markdown(payload))
    return 1 if args.fail_open and not bool(payload["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
