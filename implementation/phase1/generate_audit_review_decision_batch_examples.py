#!/usr/bin/env python3
"""Generate safe attested example batch-decision files for reviewer operations."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATE_JSON = Path(
    "implementation/phase1/release/external_benchmark_kickoff/audit_review_decision_batch_template.json"
)
DEFAULT_OUT_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")

APPROVE_ALL_NAME = "audit_review_decision_batch_approve_all.attested_example.json"
MIXED_NAME = "audit_review_decision_batch_mixed.attested_example.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _label(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items())) or "none"


def _example_attestation(example_mode: str) -> dict[str, Any]:
    return {
        "reviewer_name": "EXAMPLE_REVIEWER_REPLACE_ME",
        "reviewer_license_id": "EXAMPLE_LICENSE_REPLACE_ME",
        "decision_basis": f"example_only_{example_mode}_replace_with_actual_review_basis",
        "review_session_id": f"example-session-{example_mode}",
        "attested_at_utc": datetime.now(timezone.utc).isoformat(),
        "apply_live_acknowledged": False,
    }


def _updates_for_mode(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        packet_id = str(row.get("packet_id", "") or "")
        action_family = str(row.get("action_family", "") or "")
        current_status = str(row.get("current_status", "") or "")
        if mode == "approve_all":
            set_status = "approved"
            resolution = "close_packet"
            note = "Example approve-all batch. Replace attestation fields before live apply."
        else:
            set_status = "approved" if index % 2 == 0 else "rejected"
            resolution = "close_packet" if set_status == "approved" else "open_revision_required"
            note = (
                "Example mixed batch. Approved packets close; rejected packets reopen a revision cycle."
            )
        updates.append(
            {
                "packet_id": packet_id,
                "status_file": str(row.get("status_file", "") or ""),
                "action_family": action_family,
                "followup_type": str(row.get("followup_type", "") or ""),
                "review_priority": str(row.get("review_priority", "") or ""),
                "review_owner": str(row.get("review_owner", "") or ""),
                "current_status": current_status,
                "allowed_statuses": list(row.get("allowed_statuses", []) or []),
                "set_status": set_status,
                "resolution": resolution,
                "note": note,
            }
        )
    return updates


def _summary_for_updates(updates: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    for row in updates:
        status_counts[str(row.get("set_status", "") or "")] += 1
        owner_counts[str(row.get("review_owner", "") or "licensed_engineer")] += 1
        family_counts[str(row.get("action_family", "") or "")] += 1
    rejected_count = int(status_counts.get("rejected", 0))
    return {
        "decision_item_count": int(len(updates)),
        "target_status_counts": {key: int(value) for key, value in sorted(status_counts.items())},
        "target_status_label": _label(status_counts),
        "action_family_counts": {key: int(value) for key, value in sorted(family_counts.items())},
        "action_family_label": _label(family_counts),
        "review_owner_counts": {key: int(value) for key, value in sorted(owner_counts.items())},
        "review_owner_label": _label(owner_counts),
        "expected_preview_reason_code": "PASS_START_NOW_FULL"
        if rejected_count == 0
        else "ERR_ARCHITECTURE_BLOCKERS",
        "expected_ready_full": bool(rejected_count == 0),
        "expected_open_revision_count": rejected_count,
        "safe_for_live_apply": False,
        "operator_note": (
            "Example only. Replace reviewer attestation and set apply_live_acknowledged=true only after real review."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    attestation = payload.get("attestation") if isinstance(payload.get("attestation"), dict) else {}
    lines = [
        f"# {payload.get('example_mode', 'audit_review_decision_batch_example')}",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `decision_item_count`: `{int(summary.get('decision_item_count', 0))}`",
        f"- `target_status`: `{summary.get('target_status_label', 'none')}`",
        f"- `expected_preview_reason_code`: `{summary.get('expected_preview_reason_code', '')}`",
        f"- `expected_ready_full`: `{bool(summary.get('expected_ready_full', False))}`",
        f"- `expected_open_revision_count`: `{int(summary.get('expected_open_revision_count', 0))}`",
        f"- `safe_for_live_apply`: `{bool(summary.get('safe_for_live_apply', False))}`",
        "",
        "## Attestation Placeholder",
        "",
        f"- `reviewer_name`: `{attestation.get('reviewer_name', '')}`",
        f"- `reviewer_license_id`: `{attestation.get('reviewer_license_id', '')}`",
        f"- `decision_basis`: `{attestation.get('decision_basis', '')}`",
        f"- `apply_live_acknowledged`: `{bool(attestation.get('apply_live_acknowledged', False))}`",
        "",
        "## Updates",
        "",
    ]
    for row in payload.get("updates", []):
        lines.append(
            f"- `{row.get('packet_id', '')}` | family=`{row.get('action_family', '')}` | "
            f"set_status=`{row.get('set_status', '')}` | resolution=`{row.get('resolution', '')}`"
        )
    return "\n".join(lines) + "\n"


def build_example_payload(template_payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    rows = template_payload.get("updates")
    if not isinstance(rows, list):
        rows = []
    updates = _updates_for_mode([row for row in rows if isinstance(row, dict)], mode)
    summary = _summary_for_updates(updates)
    example_mode = "approve_all_attested_example" if mode == "approve_all" else "mixed_attested_example"
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(updates),
        "reason_code": "PASS" if updates else "ERR_NO_TEMPLATE_ITEMS",
        "reason": "safe attested example batch generated" if updates else "decision template contains no open packets",
        "example_mode": example_mode,
        "example_only": True,
        "summary": summary,
        "attestation": _example_attestation(example_mode),
        "updates": updates,
    }


def _write_example(out_dir: Path, file_name: str, payload: dict[str, Any]) -> Path:
    out_path = out_dir / file_name
    _write_json(out_path, payload)
    out_path.with_suffix(".md").write_text(_markdown(payload), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-json", default=str(DEFAULT_TEMPLATE_JSON))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    template_json = Path(args.template_json)
    if not template_json.exists():
        raise SystemExit(f"Batch template not found: {template_json}")

    template_payload = _load_json(template_json)
    out_dir = Path(args.out_dir)
    approve_out = _write_example(
        out_dir,
        APPROVE_ALL_NAME,
        build_example_payload(template_payload, mode="approve_all"),
    )
    mixed_out = _write_example(
        out_dir,
        MIXED_NAME,
        build_example_payload(template_payload, mode="mixed"),
    )
    print(f"Wrote audit review decision batch examples: {approve_out}, {mixed_out}")


if __name__ == "__main__":
    main()
