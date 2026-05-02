#!/usr/bin/env python3
"""Generate a normalized Korean public-structure source catalog."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.korean_source_schema import (  # noqa: E402
    SCHEMA_VERSION,
    normalize_korean_source_record,
)


KOREA_OPEN_DATA_DIR = REPO_ROOT / "implementation/phase1/open_data/korea"
DEFAULT_OUT_PATH = KOREA_OPEN_DATA_DIR / "korean_source_catalog.json"
DEFAULT_SEED_PATH = KOREA_OPEN_DATA_DIR / "korean_source_seed.json"

def _default_source_rows_from_repo_seed() -> list[dict[str, Any]]:
    if not DEFAULT_SEED_PATH.exists():
        return []
    payload = json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))
    rows = payload.get("source_records", payload if isinstance(payload, list) else [])
    if not isinstance(rows, list):
        raise ValueError("default korean source seed must be a list or dict with source_records")
    return [dict(row) for row in rows if isinstance(row, dict)]


DEFAULT_SOURCE_ROWS: list[dict[str, Any]] = _default_source_rows_from_repo_seed()


def _load_seed_rows(seed_path: Path | None) -> list[dict[str, Any]]:
    if seed_path is None or not seed_path.exists():
        return list(DEFAULT_SOURCE_ROWS)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("source_records", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("seed payload must be a list or dict with source_records")
    if not isinstance(rows, list):
        raise ValueError("source_records must be a list")
    return [dict(row) for row in rows]


def build_korean_source_catalog(raw_records: list[dict[str, Any]], *, generated_at_utc: str | None = None) -> dict[str, Any]:
    normalized_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in raw_records:
        record = normalize_korean_source_record(raw)
        source_id = record["source_id"]
        if source_id in seen_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen_ids.add(source_id)
        normalized_records.append(record)

    source_class_counts = Counter(row["source_class"] for row in normalized_records)
    format_counts = Counter(row["format"] for row in normalized_records)
    content_kind_counts = Counter(row["content_kind"] for row in normalized_records)
    ingest_status_counts = Counter(row["ingest_status"] for row in normalized_records)
    seed_priority_counts = Counter(row.get("seed_priority", "") for row in normalized_records)
    promotion_hint_counts = Counter(row.get("promotion_hint", "") for row in normalized_records)
    collection_policy_counts = Counter(row.get("collection_policy", "") for row in normalized_records)
    summary = {
        "record_count": len(normalized_records),
        "source_class_counts": dict(sorted(source_class_counts.items())),
        "format_counts": dict(sorted(format_counts.items())),
        "content_kind_counts": dict(sorted(content_kind_counts.items())),
        "ingest_status_counts": dict(sorted(ingest_status_counts.items())),
        "seed_priority_counts": dict(sorted(seed_priority_counts.items())),
        "promotion_hint_counts": dict(sorted(promotion_hint_counts.items())),
        "collection_policy_counts": dict(sorted(collection_policy_counts.items())),
        "seed_metadata_complete_count": sum(
            1
            for row in normalized_records
            if row.get("seed_basis") and row.get("seed_priority") and row.get("promotion_hint") and row.get("collection_policy")
        ),
        "exact_topology_candidate_count": sum(1 for row in normalized_records if row["exact_topology_candidate"]),
        "native_writeback_candidate_count": sum(1 for row in normalized_records if row["native_writeback_candidate"]),
        "curated_local_ifc_required_count": sum(1 for row in normalized_records if row.get("curated_local_ifc_required")),
        "curated_local_ifc_attached_count": sum(
            1 for row in normalized_records if str(row.get("curated_local_ifc_status", "") or "") == "attached"
        ),
        "p0_focus_candidate_count": sum(
            1
            for row in normalized_records
            if row.get("seed_priority") == "P0"
            and (
                row.get("exact_topology_candidate")
                or row.get("native_writeback_candidate")
                or row.get("promotion_hint") == "preview_roundtrip_candidate"
            )
        ),
    }
    summary_line = (
        "Korean source catalog: PASS | "
        f"records={summary['record_count']} | "
        f"seed_complete={summary['seed_metadata_complete_count']} | "
        f"exact_topology={summary['exact_topology_candidate_count']} | "
        f"native_writeback={summary['native_writeback_candidate_count']} | "
        f"p0_focus={summary['p0_focus_candidate_count']}"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "source_records": normalized_records,
        "summary_line": summary_line,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-json", default=str(DEFAULT_SEED_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT_PATH))
    args = parser.parse_args()

    seed_path = Path(args.seed_json)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_korean_source_catalog(_load_seed_rows(seed_path))
    out_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote Korean source catalog: {out_path}")


if __name__ == "__main__":
    main()
