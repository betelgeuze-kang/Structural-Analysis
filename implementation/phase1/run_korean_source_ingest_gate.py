#!/usr/bin/env python3
"""Gate Korean public-structure source ingest evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

REASONS = {
    "PASS": "korean source catalog, collection report, and ingest report are present",
    "ERR_INVALID_INPUT": "invalid korean source ingest gate input",
    "ERR_CATALOG": "korean source catalog evidence is incomplete",
    "ERR_COLLECTION": "korean source collection evidence is incomplete",
    "ERR_INGEST": "korean source ingest evidence is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["catalog", "collection_report", "ingest_report", "out"],
    "properties": {
        "catalog": {"type": "string", "minLength": 1},
        "collection_report": {"type": "string", "minLength": 1},
        "ingest_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def run_gate(*, catalog: dict[str, Any], collection_report: dict[str, Any], ingest_report: dict[str, Any]) -> dict[str, Any]:
    catalog_rows = catalog.get("source_records") if isinstance(catalog.get("source_records"), list) else []
    catalog_summary = catalog.get("summary") if isinstance(catalog.get("summary"), dict) else {}
    collection_summary = collection_report.get("summary") if isinstance(collection_report.get("summary"), dict) else {}
    ingest_summary = ingest_report.get("summary") if isinstance(ingest_report.get("summary"), dict) else {}
    ingest_records = ingest_report.get("records") if isinstance(ingest_report.get("records"), list) else []

    source_count = int(catalog_summary.get("record_count", len(catalog_rows)) or 0)
    source_class_counts = (
        dict(catalog_summary.get("source_class_counts", {}) or {})
        if isinstance(catalog_summary.get("source_class_counts"), dict)
        else {}
    )
    source_class_count = int(sum(1 for value in source_class_counts.values() if int(value or 0) > 0))
    collected_count = int(collection_summary.get("collected_count", 0) or 0)
    metadata_only_count = int(collection_summary.get("metadata_only_remote_candidate_count", 0) or 0)
    rejected_count = int(collection_summary.get("rejected_count", 0) or 0)
    fingerprinted_count = int(ingest_summary.get("fingerprinted_count", 0) or 0)
    ingest_metadata_only_count = int(ingest_summary.get("metadata_only_count", 0) or 0)
    ingest_rejected_count = int(ingest_summary.get("rejected_count", 0) or 0)
    duplicate_sha_group_count = int(ingest_summary.get("duplicate_sha_group_count", 0) or 0)

    checks = {
        "catalog_present_pass": bool(catalog_rows) and str(catalog.get("schema_version", "") or "").strip() == "korean_source_catalog.v1",
        "source_class_coverage_pass": source_class_count >= 4,
        "collection_report_present_pass": bool(collection_report.get("contract_pass", False)),
        "collection_count_match_pass": int(collection_summary.get("source_count", 0) or 0) == source_count,
        "collection_accounting_pass": collected_count + metadata_only_count + rejected_count == source_count,
        "ingest_report_present_pass": bool(ingest_report.get("contract_pass", False)),
        "ingest_count_match_pass": int(ingest_summary.get("source_count", 0) or 0) == source_count and len(ingest_records) == source_count,
        "ingest_accounting_pass": fingerprinted_count + ingest_metadata_only_count + ingest_rejected_count == source_count,
        "duplicate_sha_group_consistency_pass": duplicate_sha_group_count <= max(fingerprinted_count, 1) if source_count else False,
    }
    contract_pass = bool(
        checks["catalog_present_pass"]
        and checks["source_class_coverage_pass"]
        and checks["collection_report_present_pass"]
        and checks["collection_count_match_pass"]
        and checks["collection_accounting_pass"]
        and checks["ingest_report_present_pass"]
        and checks["ingest_count_match_pass"]
        and checks["ingest_accounting_pass"]
        and checks["duplicate_sha_group_consistency_pass"]
    )
    if not checks["catalog_present_pass"] or not checks["source_class_coverage_pass"]:
        reason_code = "ERR_CATALOG"
    elif not (
        checks["collection_report_present_pass"]
        and checks["collection_count_match_pass"]
        and checks["collection_accounting_pass"]
    ):
        reason_code = "ERR_COLLECTION"
    elif not contract_pass:
        reason_code = "ERR_INGEST"
    else:
        reason_code = "PASS"

    summary = {
        "source_count": source_count,
        "source_class_count": source_class_count,
        "source_class_counts": dict(sorted(source_class_counts.items())),
        "collected_count": collected_count,
        "metadata_only_remote_candidate_count": metadata_only_count,
        "rejected_count": rejected_count,
        "fingerprinted_count": fingerprinted_count,
        "duplicate_sha_group_count": duplicate_sha_group_count,
        "seed_metadata_complete_count": int(ingest_summary.get("seed_metadata_complete_count", 0) or 0),
        "exact_topology_candidate_count": int(ingest_summary.get("exact_topology_candidate_count", 0) or 0),
        "native_writeback_candidate_count": int(ingest_summary.get("native_writeback_candidate_count", 0) or 0),
        "p0_focus_candidate_count": int(ingest_summary.get("p0_focus_candidate_count", 0) or 0),
        "collection_summary_line": str(collection_report.get("summary_line", "") or ""),
        "ingest_summary_line": str(ingest_report.get("summary_line", "") or ""),
    }
    summary_line = (
        "Korean source ingest gate: "
        f"{'PASS' if contract_pass else 'CHECK'} | sources={summary['source_count']} | "
        f"classes={summary['source_class_count']} | collected={summary['collected_count']} | "
        f"fingerprinted={summary['fingerprinted_count']} | metadata_only={summary['metadata_only_remote_candidate_count']} | "
        f"rejected={summary['rejected_count']} | duplicate_sha_groups={summary['duplicate_sha_group_count']} | "
        f"seed_complete={summary['seed_metadata_complete_count']} | "
        f"exact_topology={summary['exact_topology_candidate_count']} | "
        f"native_writeback={summary['native_writeback_candidate_count']} | "
        f"p0_focus={summary['p0_focus_candidate_count']}"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-korean-source-ingest-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
        "summary_line": summary_line,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="implementation/phase1/open_data/korea/korean_source_catalog.json")
    parser.add_argument(
        "--collection-report",
        default="implementation/phase1/open_data/korea/korean_public_structure_collection_report.json",
    )
    parser.add_argument("--ingest-report", default="implementation/phase1/open_data/korea/korean_source_ingest_report.json")
    parser.add_argument("--out", default="implementation/phase1/korean_source_ingest_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "catalog": str(args.catalog),
        "collection_report": str(args.collection_report),
        "ingest_report": str(args.ingest_report),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_korean_source_ingest_gate")
        report = run_gate(
            catalog=_load_json(Path(args.catalog)),
            collection_report=_load_json(Path(args.collection_report)),
            ingest_report=_load_json(Path(args.ingest_report)),
        )
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-korean-source-ingest-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote Korean source ingest gate report: {out}")
    raise SystemExit(0 if bool(report.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
