#!/usr/bin/env python3
"""Attach delivery-bundle supplementary artifacts to RH sidecar (no auto-close)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    REPO_ROOT / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json"
)
DEFAULT_RH = (
    REPO_ROOT / "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def merge_supplementary_evidence(
    rh_payload: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    hints = bundle.get("holdout_evidence_hints") if isinstance(bundle.get("holdout_evidence_hints"), dict) else {}
    updates = rh_payload.get("updates") if isinstance(rh_payload.get("updates"), dict) else {}
    merged_updates: dict[str, Any] = {}
    for work_id, row in updates.items():
        if not isinstance(row, dict):
            continue
        next_row = dict(row)
        hint = hints.get(work_id) if isinstance(hints.get(work_id), dict) else {}
        artifact = str(hint.get("supplementary_artifact") or "").strip()
        if artifact:
            next_row["supplementary_evidence_path"] = artifact
            next_row["supplementary_evidence_status"] = "attached_supplementary"
            next_row["supplementary_evidence_note"] = str(hint.get("note") or "")
            next_row["supplementary_attached_at_utc"] = datetime.now(timezone.utc).isoformat()
        summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
        if work_id == "RH-002" and summary.get("cross_validation_marginal_accepted"):
            next_row["supplementary_metric_note"] = (
                f"crossval={summary.get('cross_validation_status')}; "
                f"marginal_accepted={summary.get('cross_validation_marginal_accepted')}"
            )
        if work_id == "RH-001" and summary.get("mgt_integrity_status"):
            next_row["supplementary_metric_note"] = (
                f"reanalysis={summary.get('reanalysis_status')}; "
                f"mgt_integrity={summary.get('mgt_integrity_status')}"
            )
        if work_id == "RH-003" and summary.get("story_reanalysis_status"):
            next_row["supplementary_metric_note"] = (
                f"story_reanalysis={summary.get('story_reanalysis_status')}; "
                f"mgt_pipeline={summary.get('mgt_pipeline_status')}"
            )
        merged_updates[work_id] = next_row

    out = dict(rh_payload)
    out["updates"] = merged_updates
    artifacts = bundle.get("artifacts") if isinstance(bundle.get("artifacts"), dict) else {}
    template_path = str(artifacts.get("rh_signed_closure_packet_template") or "").strip()
    out["supplementary_evidence_basis"] = {
        "delivery_evidence_bundle": str(bundle.get("generated_at") or ""),
        "bundle_status": bundle.get("status"),
        "bundle_schema": bundle.get("schema_version"),
        "rh_signed_closure_packet_template": template_path,
        "note": "Supplementary paths do not close RH work items; signed closure evidence still required.",
    }
    if template_path:
        for work_id, row in merged_updates.items():
            if isinstance(row, dict):
                row["closure_packet_template_path"] = template_path
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-json", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--residual-holdout-json", type=Path, default=DEFAULT_RH)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()
    bundle = _load(args.bundle_json)
    rh = _load(args.residual_holdout_json)
    if not bundle:
        print(f"sync-rh: missing bundle: {args.bundle_json}", file=sys.stderr)
        return 2
    if not rh:
        print(f"sync-rh: missing RH sidecar: {args.residual_holdout_json}", file=sys.stderr)
        return 2

    merged = merge_supplementary_evidence(rh, bundle)
    out_path = args.output_json or args.residual_holdout_json
    out_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    attached = sum(
        1
        for row in merged.get("updates", {}).values()
        if isinstance(row, dict) and row.get("supplementary_evidence_path")
    )
    print(f"sync-rh: attached supplementary evidence on {attached} RH rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
