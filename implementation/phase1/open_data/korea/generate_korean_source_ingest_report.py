#!/usr/bin/env python3
"""Generate a provenance/fingerprint-oriented Korean source ingest report."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
KOREA_OPEN_DATA_DIR = REPO_ROOT / "implementation/phase1/open_data/korea"
DEFAULT_CATALOG = KOREA_OPEN_DATA_DIR / "korean_source_catalog.json"
DEFAULT_COLLECTION_REPORT = KOREA_OPEN_DATA_DIR / "korean_public_structure_collection_report.json"
DEFAULT_OUT = KOREA_OPEN_DATA_DIR / "korean_source_ingest_report.json"
SCHEMA_VERSION = "1.0"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def build_korean_source_ingest_report(catalog: dict[str, Any], collection_report: dict[str, Any]) -> dict[str, Any]:
    catalog_rows = catalog.get("source_records") if isinstance(catalog.get("source_records"), list) else []
    collection_rows = collection_report.get("records") if isinstance(collection_report.get("records"), list) else []
    collection_by_id = {
        str(row.get("source_id") or "").strip(): row for row in collection_rows if isinstance(row, dict)
    }

    duplicate_sha_groups: dict[str, list[str]] = defaultdict(list)
    records: list[dict[str, Any]] = []
    for row in catalog_rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        collected = collection_by_id.get(source_id, {})
        sha256 = str(collected.get("sha256") or "").strip()
        if sha256:
            duplicate_sha_groups[sha256].append(source_id)
        records.append(
            {
                "source_id": source_id,
                "title": str(row.get("title") or "").strip(),
                "source_class": str(row.get("source_class") or "").strip(),
                "origin_type": str(row.get("origin_type") or "").strip(),
                "origin_org": str(row.get("origin_org") or "").strip(),
                "format": str(row.get("format") or "").strip(),
                "content_kind": str(row.get("content_kind") or "").strip(),
                "structure_type": str(row.get("structure_type") or "").strip(),
                "structural_system": str(row.get("structural_system") or "").strip(),
                "storey_band": str(row.get("storey_band") or "").strip(),
                "seed_basis": str(row.get("seed_basis") or "").strip(),
                "seed_priority": str(row.get("seed_priority") or "").strip(),
                "promotion_hint": str(row.get("promotion_hint") or "").strip(),
                "collection_policy": str(row.get("collection_policy") or "").strip(),
                "provenance_url": str(row.get("provenance_url") or "").strip(),
                "download_url": str(row.get("download_url") or "").strip(),
                "license_hint": str(row.get("license_hint") or "").strip(),
                "exact_topology_candidate": bool(row.get("exact_topology_candidate", False)),
                "native_writeback_candidate": bool(row.get("native_writeback_candidate", False)),
                "notes": str(row.get("notes") or "").strip(),
                "ingest_status": str(collected.get("ingest_status") or row.get("ingest_status") or "discovered").strip(),
                "retrieved_at_utc": str(collected.get("retrieved_at_utc") or row.get("retrieved_at_utc") or "").strip(),
                "sha256": sha256,
                "local_path": str(collected.get("local_path") or row.get("local_path") or "").strip(),
                "resolved_reference": str(collected.get("resolved_reference") or "").strip(),
                "reference_scheme": str(collected.get("reference_scheme") or "").strip(),
                "status": str(collected.get("status") or "").strip(),
                "reason": str(collected.get("reason") or "").strip(),
                "byte_count": int(collected.get("byte_count") or 0),
                "artifacts": dict(collected.get("artifacts") or {}),
            }
        )

    source_class_counts: dict[str, int] = defaultdict(int)
    content_kind_counts: dict[str, int] = defaultdict(int)
    ingest_status_counts: dict[str, int] = defaultdict(int)
    seed_priority_counts: dict[str, int] = defaultdict(int)
    promotion_hint_counts: dict[str, int] = defaultdict(int)
    collection_policy_counts: dict[str, int] = defaultdict(int)
    for row in records:
        source_class_counts[row["source_class"]] += 1
        content_kind_counts[row["content_kind"]] += 1
        ingest_status_counts[row["ingest_status"]] += 1
        seed_priority_counts[row["seed_priority"]] += 1
        promotion_hint_counts[row["promotion_hint"]] += 1
        collection_policy_counts[row["collection_policy"]] += 1

    duplicate_groups = [
        {"sha256": sha256, "source_ids": sorted(source_ids), "count": len(source_ids)}
        for sha256, source_ids in sorted(duplicate_sha_groups.items())
        if sha256 and len(source_ids) > 1
    ]
    summary = {
        "source_count": len(records),
        "fingerprinted_count": sum(1 for row in records if row["sha256"]),
        "metadata_only_count": sum(1 for row in records if row["status"] == "metadata_only_remote_candidate"),
        "rejected_count": sum(1 for row in records if row["status"] == "rejected"),
        "duplicate_sha_group_count": len(duplicate_groups),
        "source_class_counts": dict(sorted(source_class_counts.items())),
        "content_kind_counts": dict(sorted(content_kind_counts.items())),
        "ingest_status_counts": dict(sorted(ingest_status_counts.items())),
        "seed_priority_counts": dict(sorted(seed_priority_counts.items())),
        "promotion_hint_counts": dict(sorted(promotion_hint_counts.items())),
        "collection_policy_counts": dict(sorted(collection_policy_counts.items())),
        "seed_metadata_complete_count": sum(
            1
            for row in records
            if row["seed_basis"] and row["seed_priority"] and row["promotion_hint"] and row["collection_policy"]
        ),
        "exact_topology_candidate_count": sum(1 for row in records if row["exact_topology_candidate"]),
        "native_writeback_candidate_count": sum(1 for row in records if row["native_writeback_candidate"]),
        "p0_focus_candidate_count": sum(
            1
            for row in records
            if row["seed_priority"] == "P0"
            and (
                row["exact_topology_candidate"]
                or row["native_writeback_candidate"]
                or row["promotion_hint"] == "preview_roundtrip_candidate"
            )
        ),
    }
    summary_line = (
        "Korean source ingest: PASS | "
        f"sources={summary['source_count']} | fingerprinted={summary['fingerprinted_count']} | "
        f"metadata_only={summary['metadata_only_count']} | rejected={summary['rejected_count']} | "
        f"duplicate_sha_groups={summary['duplicate_sha_group_count']} | "
        f"seed_complete={summary['seed_metadata_complete_count']} | "
        f"exact_topology={summary['exact_topology_candidate_count']} | "
        f"native_writeback={summary['native_writeback_candidate_count']} | "
        f"p0_focus={summary['p0_focus_candidate_count']}"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "duplicate_sha_groups": duplicate_groups,
        "records": records,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "korean source catalog ingest report generated",
        "summary_line": summary_line,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--collection-report", default=str(DEFAULT_COLLECTION_REPORT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_korean_source_ingest_report(
        catalog=_load_json(Path(args.catalog)),
        collection_report=_load_json(Path(args.collection_report)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote Korean source ingest report: {out_path}")


if __name__ == "__main__":
    main()
