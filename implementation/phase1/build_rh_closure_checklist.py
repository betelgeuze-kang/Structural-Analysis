#!/usr/bin/env python3
"""Engineer-facing RH closure checklist (supplementary evidence ≠ signed closure)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rh-closure-checklist.v1"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_rh_closure_checklist(
    *,
    rh_payload: dict[str, Any],
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bundle = bundle or {}
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    hints = bundle.get("holdout_evidence_hints") if isinstance(bundle.get("holdout_evidence_hints"), dict) else {}
    updates = rh_payload.get("updates") if isinstance(rh_payload.get("updates"), dict) else {}

    rows: list[dict[str, Any]] = []
    for work_id, row in sorted(updates.items()):
        if not isinstance(row, dict):
            continue
        hint = hints.get(work_id) if isinstance(hints.get(work_id), dict) else {}
        required = str(row.get("closure_evidence_required") or "")
        rows.append(
            {
                "work_id": work_id,
                "status": row.get("status"),
                "owner": row.get("owner"),
                "closure_evidence_required": required,
                "closure_evidence_status": row.get("closure_evidence_status"),
                "supplementary_evidence_path": row.get("supplementary_evidence_path")
                or hint.get("supplementary_artifact"),
                "supplementary_metric_note": row.get("supplementary_metric_note"),
                "checklist": [
                    f"Attach signed artifact: {required}" if required else "Define closure evidence type",
                    "Verify supplementary JSON paths match delivery bundle artifacts",
                    "Do not mark RH closed until closure_evidence_path is populated",
                ],
            }
        )

    open_count = sum(1 for row in rows if str(row.get("status") or "") == "open")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_authority" if open_count else "complete",
        "open_count": open_count,
        "delivery_bundle_status": bundle.get("status"),
        "delivery_summary": summary,
        "rows": rows,
        "note": "Checklist supports engineer-in-loop closure; auto supplementary attach does not close RH items.",
    }
