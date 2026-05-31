#!/usr/bin/env python3
"""Report medium/large Korean public-structure catalog sources."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.korean_building_scale import (  # noqa: E402
    building_scale_band,
    is_medium_or_large,
)

KOREA_DIR = REPO_ROOT / "implementation/phase1/open_data/korea"
DEFAULT_CATALOG = KOREA_DIR / "korean_source_catalog.json"
DEFAULT_COLLECTION_REPORT = KOREA_DIR / "korean_public_structure_collection_report.json"
ARTIFACT_ROOT = KOREA_DIR / "collected" / "artifacts"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _collection_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("records")
    if not isinstance(rows, list):
        return {}
    return {str(row.get("source_id") or ""): row for row in rows if isinstance(row, dict) and row.get("source_id")}


def _attach_hint(record: dict[str, Any], collection_row: dict[str, Any]) -> str:
    local_path = str(collection_row.get("local_path") or record.get("local_path") or "").strip()
    if local_path:
        return local_path
    curated_ifc = str(record.get("curated_local_ifc_reference") or "").strip()
    if curated_ifc:
        return curated_ifc
    source_id = str(record.get("source_id") or "")
    if source_id:
        return f"{ARTIFACT_ROOT.relative_to(REPO_ROOT)}/{source_id}/"
    return ""


def build_medium_large_report(
    *,
    catalog_path: Path,
    collection_report_path: Path,
) -> dict[str, Any]:
    catalog = _load_json(catalog_path)
    rows = catalog.get("source_records")
    if not isinstance(rows, list):
        raise ValueError("catalog missing source_records")

    collection_by_id = _collection_index(_load_json(collection_report_path))
    table_rows: list[dict[str, Any]] = []
    scale_counts: dict[str, int] = {"medium": 0, "large": 0}

    for record in rows:
        if not isinstance(record, dict) or not is_medium_or_large(record):
            continue
        scale = building_scale_band(str(record.get("storey_band") or ""))
        scale_counts[scale] = scale_counts.get(scale, 0) + 1
        source_id = str(record.get("source_id") or "")
        collection_row = collection_by_id.get(source_id, {})
        status = str(collection_row.get("status") or collection_row.get("ingest_status") or record.get("ingest_status") or "")
        table_rows.append(
            {
                "source_id": source_id,
                "title": record.get("title", ""),
                "storey_band": record.get("storey_band", ""),
                "scale": scale,
                "format": record.get("format", ""),
                "collection_policy": record.get("collection_policy", ""),
                "ingest_status": status,
                "attach_hint": _attach_hint(record, collection_row),
            }
        )

    table_rows.sort(key=lambda row: (row["scale"], row["source_id"]))
    return {
        "schema_version": "korean_medium_large_report.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_path": str(catalog_path),
        "collection_report_path": str(collection_report_path),
        "summary": {
            "medium_large_source_count": len(table_rows),
            "medium_count": scale_counts.get("medium", 0),
            "large_count": scale_counts.get("large", 0),
        },
        "rows": table_rows,
    }


def _print_table(report: dict[str, Any]) -> None:
    headers = ("source_id", "title", "storey_band", "scale", "format", "collection_policy", "ingest_status", "attach_hint")
    widths = (42, 36, 10, 6, 5, 28, 22, 48)
    print(" | ".join(h.ljust(w)[:w] for h, w in zip(headers, widths, strict=True)))
    print("-+-".join("-" * w for w in widths))
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        values = [str(row.get(key, "")) for key in headers]
        print(" | ".join(v.ljust(w)[:w] for v, w in zip(values, widths, strict=True)))
    summary = report.get("summary", {})
    print()
    print(
        "Summary: "
        f"medium_large={summary.get('medium_large_source_count', 0)} "
        f"(medium={summary.get('medium_count', 0)}, large={summary.get('large_count', 0)})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--collection-report", type=Path, default=DEFAULT_COLLECTION_REPORT)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    report = build_medium_large_report(
        catalog_path=args.catalog,
        collection_report_path=args.collection_report,
    )
    _print_table(report)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote report JSON: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
