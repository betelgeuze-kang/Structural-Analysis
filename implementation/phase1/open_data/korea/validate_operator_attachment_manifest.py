#!/usr/bin/env python3
"""Validate G7 operator-attached source-native artifact manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1 import run_korean_medium_large_ingest_pipeline as ingest  # noqa: E402


DEFAULT_REPORT = (
    ingest.KOREA_DIR / "operator_attachment_manifest_validation_report.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def validate_operator_attachment_manifest(
    *,
    manifest_path: Path = ingest.DEFAULT_OPERATOR_ATTACHMENT_MANIFEST,
    catalog_path: Path = ingest.DEFAULT_CATALOG,
) -> dict[str, Any]:
    catalog = _load_json(catalog_path)
    source_records = catalog.get("source_records")
    if not isinstance(source_records, list):
        raise ValueError(f"catalog missing source_records: {catalog_path}")
    catalog_source_ids = {
        str(row.get("source_id") or "")
        for row in source_records
        if isinstance(row, dict) and row.get("source_id")
    }
    validation = ingest._operator_attachment_manifest_rows(
        manifest_path=manifest_path,
        catalog_source_ids=catalog_source_ids,
    )
    summary = dict(validation["summary"])
    accepted = int(summary.get("operator_attachment_manifest_accepted_count") or 0)
    rejected = int(summary.get("operator_attachment_manifest_rejected_count") or 0)
    ready_for_overlay = bool(summary.get("operator_attachment_manifest_present")) and rejected == 0
    return {
        "schema_version": "korean-medium-large-operator-attachment-manifest-validation.v1",
        "manifest_path": str(manifest_path),
        "catalog_path": str(catalog_path),
        "ready_for_collection_overlay": ready_for_overlay,
        "accepted_source_count": accepted,
        "rejected_source_count": rejected,
        "summary": summary,
        "rows": validation["rows"],
        "claim_boundary": (
            "Accepted rows are eligible for ingest overlay. They still count as G7 "
            "evidence only after run_korean_medium_large_ingest_pipeline replays the "
            "artifact checks and updates the ingest receipt."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ingest.DEFAULT_OPERATOR_ATTACHMENT_MANIFEST,
    )
    parser.add_argument("--catalog", type=Path, default=ingest.DEFAULT_CATALOG)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--show-summary", action="store_true")
    args = parser.parse_args()

    report = validate_operator_attachment_manifest(
        manifest_path=args.manifest,
        catalog_path=args.catalog,
    )
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.show_summary:
        summary = report["summary"]
        print(
            "operator-attachment-manifest: "
            f"present={summary['operator_attachment_manifest_present']} "
            f"accepted={summary['operator_attachment_manifest_accepted_count']} "
            f"rejected={summary['operator_attachment_manifest_rejected_count']} "
            f"ready_for_overlay={report['ready_for_collection_overlay']}"
        )
    return 0 if report["ready_for_collection_overlay"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
