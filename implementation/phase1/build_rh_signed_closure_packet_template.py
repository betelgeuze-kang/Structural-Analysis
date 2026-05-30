#!/usr/bin/env python3
"""RH signed-closure packet template (does not close holdout rows)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rh-signed-closure-packet-template.v1"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_rh_signed_closure_packet_template(
    *,
    rh_payload: dict[str, Any],
    checklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updates = rh_payload.get("updates") if isinstance(rh_payload.get("updates"), dict) else {}
    checklist_rows = {
        str(row.get("work_id")): row
        for row in (checklist or {}).get("rows") or []
        if isinstance(row, dict) and row.get("work_id")
    }

    packets: dict[str, Any] = {}
    for work_id, row in sorted(updates.items()):
        if not isinstance(row, dict):
            continue
        checklist_row = checklist_rows.get(work_id, {})
        packets[work_id] = {
            "work_id": work_id,
            "status": row.get("status"),
            "closure_evidence_required": row.get("closure_evidence_required"),
            "supplementary_evidence_path": row.get("supplementary_evidence_path"),
            "supplementary_metric_note": row.get("supplementary_metric_note"),
            "template_fields": {
                "reviewer_name": "",
                "reviewer_organization": "",
                "license_or_authority_id": "",
                "reviewed_at_utc": "",
                "signature_method": "",
                "signed_artifact_path": "",
                "signed_artifact_sha256": "",
                "scope_statement": "",
            },
            "engineer_checklist": checklist_row.get("checklist") or [],
            "closure_note": "Populate template_fields and set signed_artifact_path before marking RH closed.",
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "template_only",
        "claim": "Not a signed closure packet; attach completed packet to RH closure_evidence_path.",
        "open_count": sum(1 for row in packets.values() if str(row.get("status") or "") == "open"),
        "packets": packets,
    }
