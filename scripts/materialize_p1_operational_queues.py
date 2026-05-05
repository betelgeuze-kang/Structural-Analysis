#!/usr/bin/env python3
"""Materialize P1 external submission and residual holdout operational queues."""

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
    DEFAULT_COMMERCIAL_READINESS,
    DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    _commercial_gate,
    _external_submission_queue_gate,
    _load_json,
)


SCHEMA_VERSION = "p1-operational-queues.v1"
DEFAULT_OUT = Path("implementation/phase1/release/p1_operational_queues/p1_operational_queues.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release/p1_operational_queues/p1_operational_queues.md")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_closed(row: dict[str, Any]) -> bool:
    status = str(row.get("status", "") or "").lower()
    evidence_status = str(row.get("closure_evidence_status", "") or "").lower()
    return status in {"closed", "complete", "completed"} or evidence_status in {"attached", "verified", "closed"}


def _residual_owner_action(row: dict[str, Any]) -> str:
    if _is_closed(row):
        return "verify_closure_evidence_and_archive"
    queue_status = str(row.get("queue_status", "") or "")
    if queue_status == "pending_cross_validation":
        return "run_legacy_tool_cross_validation_and_attach_report"
    if queue_status == "pending_signoff":
        return "collect_authority_signoff_or_formal_hold_receipt"
    return "complete_engineer_review_and_attach_signed_packet"


def _external_owner_action(row: dict[str, Any]) -> str:
    direct = str(row.get("submission_owner_action", "") or "")
    if direct:
        return direct
    lifecycle = row.get("status_lifecycle") if isinstance(row.get("status_lifecycle"), dict) else {}
    nested = str(lifecycle.get("submission_owner_action", "") or "")
    if nested:
        return nested
    status = str(row.get("status", "") or "")
    if status == "ready_for_full_submission":
        return "submit_external_benchmark_package_and_attach_receipt"
    if status == "ready_for_benchmark_start_final_review_pending":
        return "start_benchmark_execution_then_close_review_boundary_before_submission"
    return "clear_blockers_before_submission"


def _normalize_residual(row: dict[str, Any], *, artifact_root: Path) -> dict[str, Any]:
    work_item_id = str(row.get("work_item_id", "") or "")
    packet_path = artifact_root / "residual_holdout_queue" / f"{work_item_id or 'residual_holdout'}.closure_packet_template.json"
    return {
        "work_item_id": work_item_id,
        "category_id": str(row.get("category_id", "") or ""),
        "queue_type": "residual_holdout",
        "queue_name": str(row.get("queue_name", "") or "residual_holdout_queue"),
        "queue_status": str(row.get("queue_status", "") or "pending_review"),
        "status": str(row.get("status", "") or "open"),
        "owner": str(row.get("owner", "") or ""),
        "sla_hours": int(row.get("sla_hours", 0) or 0),
        "sla_label": str(row.get("sla_label", "") or ""),
        "due_date": str(row.get("due_date", "") or ""),
        "closure_evidence_required": str(row.get("closure_evidence_required", "") or ""),
        "closure_evidence_path": str(row.get("closure_evidence_path", "") or ""),
        "closure_evidence_status": str(row.get("closure_evidence_status", "") or "pending"),
        "last_checked_at_utc": str(row.get("last_checked_at_utc", "") or ""),
        "closed_at_utc": str(row.get("closed_at_utc", "") or ""),
        "closure_packet_template_path": str(packet_path),
        "owner_action": _residual_owner_action(row),
    }


def _normalize_external(row: dict[str, Any], *, artifact_root: Path) -> dict[str, Any]:
    work_item_id = str(row.get("work_item_id", "") or "")
    receipt_template_path = (
        artifact_root / "external_benchmark_submission_queue" / f"{work_item_id or 'external_submission'}.receipt_template.json"
    )
    receipt_status = str(row.get("receipt_status", "") or row.get("submission_receipt_status", "") or "pending")
    submission_receipt = str(row.get("submission_receipt", "") or "").strip()
    if submission_receipt == "pending":
        submission_receipt = ""
    lifecycle = str(
        row.get("submission_lifecycle_status", "")
        or row.get("submission_lifecycle", "")
        or row.get("lifecycle", "")
        or row.get("lifecycle_status", "")
        or ""
    )
    return {
        "work_item_id": work_item_id,
        "queue_id": str(row.get("queue_id", "") or ""),
        "queue_type": "external_benchmark_submission",
        "submission_id": str(row.get("submission_id", "") or ""),
        "submission_scope": str(row.get("submission_scope", "") or ""),
        "owner": str(row.get("owner", "") or ""),
        "status": str(row.get("status", "") or ""),
        "queue_status": str(row.get("queue_status", "") or row.get("status", "") or ""),
        "submission_status": str(row.get("submission_status", "") or lifecycle),
        "submission_lifecycle_status": lifecycle,
        "receipt_url": str(row.get("receipt_url", "") or row.get("submission_receipt_url", "") or submission_receipt),
        "receipt_status": receipt_status,
        "submitted_at_utc": str(row.get("submitted_at_utc", "") or ""),
        "last_checked_at_utc": str(row.get("last_checked_at_utc", "") or ""),
        "onepage_attestation": str(row.get("onepage_attestation", "") or ""),
        "onepage_attestation_status": str(row.get("onepage_attestation_status", "") or ""),
        "dry_run_evidence": str(row.get("dry_run_evidence", "") or ""),
        "closure_evidence_required": str(row.get("closure_evidence_required", "") or ""),
        "closure_evidence_path": str(row.get("closure_evidence_path", "") or ""),
        "closure_evidence_status": str(row.get("closure_evidence_status", "") or "pending"),
        "receipt_template_path": str(receipt_template_path),
        "owner_action": _external_owner_action(row),
    }


def build_operational_queues(
    *,
    commercial_readiness: Path,
    external_benchmark_submission_readiness: Path,
    residual_holdout_closure_updates: Path | None = DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    p1_benchmark_breadth_status: Path | None,
    artifact_root: Path,
) -> dict[str, Any]:
    commercial_gate = _commercial_gate(
        commercial_readiness,
        residual_holdout_closure_updates=residual_holdout_closure_updates,
    )
    external_gate = _external_submission_queue_gate(external_benchmark_submission_readiness)
    residual_items = [
        _normalize_residual(row, artifact_root=artifact_root)
        for row in commercial_gate.get("residual_holdout_work_items", [])
        if isinstance(row, dict)
    ]
    external_items = [
        _normalize_external(row, artifact_root=artifact_root)
        for row in external_gate.get("submission_queue", [])
        if isinstance(row, dict)
    ]
    p1_benchmark_payload = _load_json(p1_benchmark_breadth_status) if p1_benchmark_breadth_status else {}
    residual_operational = bool(
        residual_items
        and all(
            row["work_item_id"]
            and row["owner"]
            and row["queue_status"]
            and row["closure_evidence_required"]
            and row["closure_evidence_status"]
            for row in residual_items
        )
    )
    external_operational = bool(
        external_items
        and bool(external_gate.get("ok", False))
        and all(
            row["work_item_id"]
            and row["submission_id"]
            and row["receipt_status"]
            and row["closure_evidence_required"]
            and row["owner_action"]
            for row in external_items
        )
    )
    contract_pass = bool(residual_operational and external_operational)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_P1_OPERATIONAL_QUEUES_INCOMPLETE",
        "summary": {
            "external_submission_queue_count": len(external_items),
            "external_submission_ready_count": int(external_gate.get("submission_queue_ready_count", 0) or 0),
            "external_submission_review_pending_count": int(
                external_gate.get("submission_queue_review_pending_count", 0) or 0
            ),
            "external_submission_blocked_count": int(external_gate.get("submission_queue_blocked_count", 0) or 0),
            "external_submission_receipt_pending_count": sum(
                1 for row in external_items if str(row.get("receipt_status", "") or "").startswith("pending")
            ),
            "external_submission_receipt_attached_count": sum(
                1 for row in external_items if str(row.get("receipt_url", "") or "").strip()
            ),
            "external_submission_last_checked_count": sum(
                1 for row in external_items if str(row.get("last_checked_at_utc", "") or "").strip()
            ),
            "external_submission_closure_evidence_attached_count": sum(
                1
                for row in external_items
                if str(row.get("closure_evidence_status", "") or "").lower() in {"attached", "verified", "closed"}
            ),
            "external_submission_operational": external_operational,
            "residual_holdout_work_item_count": len(residual_items),
            "residual_holdout_open_count": sum(1 for row in residual_items if not _is_closed(row)),
            "residual_holdout_closure_evidence_pending_count": sum(
                1
                for row in residual_items
                if not _is_closed(row) and str(row.get("closure_evidence_status", "") or "") == "pending"
            ),
            "residual_holdout_closure_evidence_attached_count": sum(
                1
                for row in residual_items
                if str(row.get("closure_evidence_status", "") or "").lower() in {"attached", "verified", "closed"}
            ),
            "residual_holdout_last_checked_count": sum(
                1 for row in residual_items if str(row.get("last_checked_at_utc", "") or "").strip()
            ),
            "residual_holdout_operational": residual_operational,
            "commercial_scope_ready": bool(commercial_gate.get("commercial_scope_ready", False)),
            "full_commercial_replacement_ready": bool(commercial_gate.get("full_commercial_replacement_ready", False)),
            "p1_benchmark_execution_unblocked": bool(
                p1_benchmark_payload.get("p1_benchmark_execution_unblocked", False)
            ),
        },
        "queues": {
            "external_benchmark_submission_work_items": external_items,
            "residual_holdout_work_items": residual_items,
        },
        "artifacts": {
            "commercial_readiness": str(commercial_readiness),
            "external_benchmark_submission_readiness": str(external_benchmark_submission_readiness),
            "residual_holdout_closure_updates": str(residual_holdout_closure_updates or ""),
            "residual_holdout_closure_updates_present": bool(
                residual_holdout_closure_updates and residual_holdout_closure_updates.exists()
            ),
            "p1_benchmark_breadth_status": str(p1_benchmark_breadth_status) if p1_benchmark_breadth_status else "",
            "artifact_root": str(artifact_root),
            "external_benchmark_submission_work_items": str(
                artifact_root / "external_benchmark_submission_queue" / "external_benchmark_submission_work_items.json"
            ),
            "residual_holdout_work_items": str(
                artifact_root / "residual_holdout_queue" / "residual_holdout_work_items.json"
            ),
        },
    }


def _packet_template(row: dict[str, Any], *, schema_version: str) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "work_item_id": row.get("work_item_id", ""),
        "owner": row.get("owner", ""),
        "status": row.get("status", ""),
        "queue_status": row.get("queue_status", ""),
        "closure_evidence_required": row.get("closure_evidence_required", ""),
        "closure_evidence_path": row.get("closure_evidence_path", ""),
        "closure_evidence_status": row.get("closure_evidence_status", ""),
        "last_checked_at_utc": row.get("last_checked_at_utc", ""),
        "closed_at_utc": row.get("closed_at_utc", ""),
        "owner_action": row.get("owner_action", ""),
    }


def write_operational_artifacts(payload: dict[str, Any], *, out: Path, out_md: Path | None) -> None:
    artifact_root = Path(str(payload.get("artifacts", {}).get("artifact_root", out.parent)))
    external_items = payload["queues"]["external_benchmark_submission_work_items"]
    residual_items = payload["queues"]["residual_holdout_work_items"]
    _write_json(out, payload)
    _write_json(
        artifact_root / "external_benchmark_submission_queue" / "external_benchmark_submission_work_items.json",
        external_items,
    )
    _write_json(artifact_root / "residual_holdout_queue" / "residual_holdout_work_items.json", residual_items)
    for row in external_items:
        _write_json(
            Path(str(row["receipt_template_path"])),
            {
                **_packet_template(row, schema_version="external_benchmark_submission_receipt_template.v1"),
                "queue_id": row.get("queue_id", ""),
                "submission_id": row.get("submission_id", ""),
                "receipt_url": row.get("receipt_url", ""),
                "receipt_status": row.get("receipt_status", ""),
                "submitted_at_utc": row.get("submitted_at_utc", ""),
                "last_checked_at_utc": row.get("last_checked_at_utc", ""),
            },
        )
    for row in residual_items:
        _write_json(
            Path(str(row["closure_packet_template_path"])),
            {
                **_packet_template(row, schema_version="residual_holdout_closure_packet_template.v1"),
                "category_id": row.get("category_id", ""),
                "sla_hours": row.get("sla_hours", 0),
                "sla_label": row.get("sla_label", ""),
                "due_date": row.get("due_date", ""),
            },
        )
    if out_md:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(payload), encoding="utf-8")


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# P1 Operational Queues",
        "",
        f"- `contract_pass`: `{bool(payload.get('contract_pass', False))}`",
        f"- `reason_code`: `{payload.get('reason_code', '')}`",
        f"- `external_submission_queue_count`: `{summary.get('external_submission_queue_count', 0)}`",
        f"- `residual_holdout_work_item_count`: `{summary.get('residual_holdout_work_item_count', 0)}`",
        f"- `residual_holdout_open_count`: `{summary.get('residual_holdout_open_count', 0)}`",
        f"- `residual_holdout_closure_evidence_pending_count`: `{summary.get('residual_holdout_closure_evidence_pending_count', 0)}`",
        f"- `full_commercial_replacement_ready`: `{bool(summary.get('full_commercial_replacement_ready', False))}`",
        "",
        "## External Benchmark Submission",
        "",
        "| Work Item | Queue | Submission ID | Owner | Status | Lifecycle | Receipt Status | Receipt URL | Receipt Template | Owner Action |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["queues"]["external_benchmark_submission_work_items"]:
        lines.append(
            f"| {row.get('work_item_id', '')} | {row.get('queue_id', '')} | {row.get('submission_id', '')} | "
            f"{row.get('owner', '')} | {row.get('status', '')} | {row.get('submission_lifecycle_status', '')} | "
            f"{row.get('receipt_status', '')} | {row.get('receipt_url', '') or 'pending'} | "
            f"{row.get('receipt_template_path', '')} | "
            f"{row.get('owner_action', '')} |"
        )
    lines.extend(
        [
            "",
            "## Residual Holdout",
            "",
            "| Work Item | Category | Owner | Queue Status | SLA | Due | Closure Evidence | Last Checked | Packet Template | Owner Action |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in payload["queues"]["residual_holdout_work_items"]:
        lines.append(
            f"| {row.get('work_item_id', '')} | {row.get('category_id', '')} | {row.get('owner', '')} | "
            f"{row.get('queue_status', '')} | {row.get('sla_label', '')} | {row.get('due_date', '')} | "
            f"{row.get('closure_evidence_required', '')} ({row.get('closure_evidence_status', '')}: "
            f"{row.get('closure_evidence_path', '') or 'pending'}) | {row.get('last_checked_at_utc', '')} | "
            f"{row.get('closure_packet_template_path', '')} | {row.get('owner_action', '')} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument(
        "--external-benchmark-submission-readiness",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    )
    parser.add_argument(
        "--residual-holdout-closure-updates",
        type=Path,
        default=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    )
    parser.add_argument("--p1-benchmark-breadth-status", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact_root = args.artifact_root or args.out.parent
    out_md = args.out_md
    if out_md is None and args.out == DEFAULT_OUT:
        out_md = DEFAULT_OUT_MD
    payload = build_operational_queues(
        commercial_readiness=args.commercial_readiness,
        external_benchmark_submission_readiness=args.external_benchmark_submission_readiness,
        residual_holdout_closure_updates=args.residual_holdout_closure_updates,
        p1_benchmark_breadth_status=args.p1_benchmark_breadth_status,
        artifact_root=artifact_root,
    )
    write_operational_artifacts(payload, out=args.out, out_md=out_md)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_markdown(payload))
    return 1 if args.fail_open and not bool(payload["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
