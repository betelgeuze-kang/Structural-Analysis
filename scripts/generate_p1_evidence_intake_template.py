#!/usr/bin/env python3
"""Generate a fill-in P1 EB/RH evidence intake manifest template."""

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

from build_p1_evidence_sidecar_updates import (  # noqa: E402
    EXTERNAL_CLOSURE_REQUIRED,
    EXTERNAL_EXPECTED_QUEUE_IDS,
    EXTERNAL_SUBMISSION_IDS,
    EXTERNAL_WORK_ITEM_IDS,
    RESIDUAL_DEFAULTS,
    RESIDUAL_EXPECTED_WORK_ITEM_IDS,
    SCHEMA_VERSION,
)


DEFAULT_P1_OPERATIONAL_QUEUES = Path(
    "implementation/phase1/release/p1_operational_queues/p1_operational_queues.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _queue_maps(operational_queues: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = _load_json(operational_queues)
    queues = payload.get("queues") if isinstance(payload.get("queues"), dict) else {}
    external_rows = queues.get("external_benchmark_submission_work_items", [])
    residual_rows = queues.get("residual_holdout_work_items", [])
    external = {
        _text(row.get("queue_id", "")): row
        for row in external_rows
        if isinstance(row, dict) and _text(row.get("queue_id", ""))
    }
    residual = {
        _text(row.get("work_item_id", "")): row
        for row in residual_rows
        if isinstance(row, dict) and _text(row.get("work_item_id", ""))
    }
    return external, residual


def _external_template_row(queue_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "work_item_id": _text(row.get("work_item_id", "")) or EXTERNAL_WORK_ITEM_IDS.get(queue_id, ""),
        "queue_id": queue_id,
        "submission_id": _text(row.get("submission_id", "")) or EXTERNAL_SUBMISSION_IDS.get(queue_id, ""),
        "owner": _text(row.get("owner", "")),
        "required_evidence": _text(row.get("closure_evidence_required", ""))
        or EXTERNAL_CLOSURE_REQUIRED.get(queue_id, "external_submission_receipt"),
        "receipt_url": "",
        "receipt_path": "",
        "closure_evidence_path": "",
        "submitted_at_utc": "",
        "last_checked_at_utc": "",
        "source_receipt_template_path": _text(row.get("receipt_template_path", "")),
        "source_owner_action": _text(row.get("owner_action", "")),
        "source_status": _text(row.get("status", "")),
        "source_receipt_status": _text(row.get("receipt_status", "")),
    }


def _residual_template_row(work_item_id: str, row: dict[str, Any]) -> dict[str, Any]:
    defaults = RESIDUAL_DEFAULTS.get(work_item_id, {})
    return {
        "work_item_id": work_item_id,
        "category_id": _text(row.get("category_id", "")),
        "owner": _text(row.get("owner", "")) or _text(defaults.get("owner", "")),
        "required_evidence": _text(row.get("closure_evidence_required", ""))
        or _text(defaults.get("closure_evidence_required", "")),
        "closure_evidence_path": "",
        "last_checked_at_utc": "",
        "closed_at_utc": "",
        "source_closure_packet_template_path": _text(row.get("closure_packet_template_path", "")),
        "source_owner_action": _text(row.get("owner_action", "")),
        "source_queue_status": _text(row.get("queue_status", "")) or _text(defaults.get("queue_status", "")),
        "source_status": _text(row.get("status", "")),
        "sla_label": _text(row.get("sla_label", "")) or _text(defaults.get("sla_label", "")),
        "due_date": _text(row.get("due_date", "")) or _text(defaults.get("due_date", "")),
    }


def build_template(*, p1_operational_queues: Path) -> dict[str, Any]:
    external_rows, residual_rows = _queue_maps(p1_operational_queues)
    external = {
        queue_id: _external_template_row(queue_id, external_rows.get(queue_id, {}))
        for queue_id in EXTERNAL_EXPECTED_QUEUE_IDS
    }
    residual = {
        work_item_id: _residual_template_row(work_item_id, residual_rows.get(work_item_id, {}))
        for work_item_id in RESIDUAL_EXPECTED_WORK_ITEM_IDS
    }
    empty_required_field_count = sum(
        1
        for row in external.values()
        for key in ("receipt_url", "receipt_path", "closure_evidence_path")
        if not _text(row.get(key, ""))
    ) + sum(1 for row in residual.values() if not _text(row.get("closure_evidence_path", "")))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "template_kind": "p1_evidence_intake_fill_in",
        "source_p1_operational_queues": str(p1_operational_queues),
        "instructions": {
            "external_benchmark_receipts": (
                "Fill receipt_url or receipt_path for every EB row. Use closure_evidence_path when the closure "
                "artifact differs from the receipt reference."
            ),
            "residual_holdout_closures": (
                "Fill closure_evidence_path for RH-001..RH-003. Local paths must exist before sidecar build."
            ),
            "promotion_gate": (
                "Run build_p1_evidence_sidecar_updates.py --require-complete, then "
                "preflight_p1_evidence_sidecar_intake.py --fail-open."
            ),
        },
        "external_benchmark_receipts": external,
        "residual_holdout_closures": residual,
        "summary": {
            "external_expected_queue_count": len(EXTERNAL_EXPECTED_QUEUE_IDS),
            "residual_expected_work_item_count": len(RESIDUAL_EXPECTED_WORK_ITEM_IDS),
            "empty_required_field_count": empty_required_field_count,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# P1 Evidence Intake Template",
        "",
        f"- `schema_version`: `{payload['schema_version']}`",
        f"- `source_p1_operational_queues`: `{payload['source_p1_operational_queues']}`",
        f"- `empty_required_field_count`: `{payload['summary']['empty_required_field_count']}`",
        "",
        "## External Benchmark Receipts",
        "",
        "| Queue | Work Item | Owner | Required Evidence | Receipt URL | Receipt Path | Closure Evidence Path |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in payload["external_benchmark_receipts"].values():
        lines.append(
            f"| {row['queue_id']} | {row['work_item_id']} | {row['owner']} | {row['required_evidence']} | "
            f"{row['receipt_url'] or 'TODO'} | {row['receipt_path'] or 'TODO'} | "
            f"{row['closure_evidence_path'] or 'TODO'} |"
        )
    lines.extend(
        [
            "",
            "## Residual Holdout Closures",
            "",
            "| Work Item | Category | Owner | Required Evidence | Closure Evidence Path | Due |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in payload["residual_holdout_closures"].values():
        lines.append(
            f"| {row['work_item_id']} | {row['category_id']} | {row['owner']} | {row['required_evidence']} | "
            f"{row['closure_evidence_path'] or 'TODO'} | {row['due_date']} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-operational-queues", type=Path, default=DEFAULT_P1_OPERATIONAL_QUEUES)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_template(p1_operational_queues=args.p1_operational_queues)
    _write_json(args.out, payload)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
