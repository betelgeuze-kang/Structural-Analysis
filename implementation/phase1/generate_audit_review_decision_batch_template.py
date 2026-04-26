#!/usr/bin/env python3
"""Generate a reviewer batch-decision template for open audit review packets."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

DEFAULT_QUEUE_MANIFEST = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")
DEFAULT_OUT = DEFAULT_OUT_DIR / "audit_review_decision_batch_template.json"

DECISION_OPEN_STATUSES = {"pending_review", "acknowledged"}
ALLOWED_STATUS_BY_CURRENT = {
    "pending_review": ["acknowledged", "approved", "rejected"],
    "acknowledged": ["approved", "rejected"],
}
ATTESTATION_TEMPLATE = {
    "reviewer_name": "",
    "reviewer_license_id": "",
    "decision_basis": "",
    "review_session_id": "",
    "attested_at_utc": "",
    "apply_live_acknowledged": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _label(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items())) or "none"


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# Audit Review Decision Batch Template",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `decision_item_count`: `{int(summary.get('decision_item_count', 0))}`",
        f"- `current_status`: `{summary.get('current_status_label', 'none')}`",
        f"- `review_owner`: `{summary.get('review_owner_label', 'none')}`",
        f"- `review_priority`: `{summary.get('review_priority_label', 'none')}`",
        "",
        "## Reviewer Attestation",
        "",
        "- Fill `attestation.reviewer_name`, `attestation.reviewer_license_id`, and `attestation.decision_basis` before `--apply-live`.",
        "- Set `attestation.apply_live_acknowledged=true` only when the decision is ready to be written to live queue state.",
        "",
        "## Decision Items",
        "",
    ]
    for row in payload.get("updates", []):
        lines.append(
            f"- `{row.get('packet_id', '')}` | family=`{row.get('action_family', '')}` | "
            f"priority=`{row.get('review_priority', '')}` | current=`{row.get('current_status', '')}` | "
            f"allowed=`{', '.join(row.get('allowed_statuses', []))}`"
        )
    return "\n".join(lines) + "\n"


def build_decision_batch_template(queue_manifest_payload: dict[str, Any]) -> dict[str, Any]:
    rows = queue_manifest_payload.get("audit_review_queue_items")
    if not isinstance(rows, list):
        rows = []

    current_status_counts: Counter[str] = Counter()
    review_owner_counts: Counter[str] = Counter()
    review_priority_counts: Counter[str] = Counter()
    updates: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        current_status = str(row.get("queue_status", "") or "")
        if current_status not in DECISION_OPEN_STATUSES:
            continue
        review_owner = str(row.get("review_owner", "") or "licensed_engineer")
        review_priority = str(row.get("review_priority", "") or "")
        current_status_counts[current_status] += 1
        review_owner_counts[review_owner] += 1
        if review_priority:
            review_priority_counts[review_priority] += 1
        updates.append(
            {
                "packet_id": str(row.get("packet_id", "") or ""),
                "status_file": str(row.get("path", "") or ""),
                "action_family": str(row.get("action_family", "") or ""),
                "followup_type": str(row.get("followup_type", "") or ""),
                "review_priority": review_priority,
                "review_owner": review_owner,
                "current_status": current_status,
                "allowed_statuses": list(ALLOWED_STATUS_BY_CURRENT.get(current_status, ["approved", "rejected"])),
                "set_status": "",
                "resolution": "",
                "note": "",
            }
        )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(updates),
        "reason_code": "PASS" if updates else "ERR_NO_OPEN_DECISION_ITEMS",
        "reason": "open review packets available for decision batching" if updates else "no open review packets need reviewer decisions",
        "summary": {
            "decision_item_count": int(len(updates)),
            "current_status_counts": {key: int(value) for key, value in sorted(current_status_counts.items())},
            "current_status_label": _label(current_status_counts),
            "review_owner_counts": {key: int(value) for key, value in sorted(review_owner_counts.items())},
            "review_owner_label": _label(review_owner_counts),
            "review_priority_counts": {key: int(value) for key, value in sorted(review_priority_counts.items())},
            "review_priority_label": _label(review_priority_counts),
        },
        "attestation": dict(ATTESTATION_TEMPLATE),
        "updates": updates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    queue_manifest = Path(args.queue_manifest)
    if not queue_manifest.exists():
        raise SystemExit(f"Queue manifest not found: {queue_manifest}")

    payload = build_decision_batch_template(_load_json(queue_manifest))
    out_path = Path(args.out)
    md_path = out_path.with_suffix(".md")
    _write_json(out_path, payload)
    md_path.write_text(_markdown(payload), encoding="utf-8")
    print(f"Wrote audit review decision batch template: {out_path}")


if __name__ == "__main__":
    main()
