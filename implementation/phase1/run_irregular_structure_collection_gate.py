#!/usr/bin/env python3
"""Gate irregular-structure catalog/triage/collection readiness for benchmark intake."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

REASONS = {
    "PASS": "irregular structure catalog, triage, collection, and top5 execution manifest are ready",
    "ERR_INVALID_INPUT": "invalid irregular structure collection gate input",
    "ERR_CATALOG": "irregular structure source catalog is incomplete",
    "ERR_TRIAGE": "irregular structure triage coverage is incomplete",
    "ERR_COLLECTION": "irregular structure collection report is incomplete",
    "ERR_TOP5": "irregular top5 execution manifest is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source_catalog", "triage_report", "collection_report", "top5_manifest", "out"],
    "properties": {
        "source_catalog": {"type": "string", "minLength": 1},
        "triage_report": {"type": "string", "minLength": 1},
        "collection_report": {"type": "string", "minLength": 1},
        "top5_manifest": {"type": "string", "minLength": 1},
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


def run_gate(*, source_catalog: dict[str, Any], triage_report: dict[str, Any], collection_report: dict[str, Any], top5_manifest: dict[str, Any]) -> dict[str, Any]:
    catalog_summary = source_catalog.get("summary") if isinstance(source_catalog.get("summary"), dict) else {}
    triage_summary = triage_report.get("summary") if isinstance(triage_report.get("summary"), dict) else {}
    collection_summary = collection_report.get("summary") if isinstance(collection_report.get("summary"), dict) else {}
    top5_rows = top5_manifest.get("top5_families") if isinstance(top5_manifest.get("top5_families"), list) else []

    local_ready_count = int(catalog_summary.get("local_ready_count", 0) or 0)
    remote_candidate_count = int(catalog_summary.get("remote_candidate_count", 0) or 0)
    collected_count = int(collection_summary.get("collected_count", 0) or 0)
    metadata_only_remote_candidate_count = int(collection_summary.get("metadata_only_remote_candidate_count", 0) or 0)
    rejected_count = int(collection_summary.get("rejected_count", 0) or 0)

    top5_execution_modes = [str(row.get("execution_mode", "") or "").strip() for row in top5_rows if isinstance(row, dict)]
    top5_local_ready_count = sum(1 for mode in top5_execution_modes if mode.startswith("ready_local"))
    top5_proxy_ready_count = sum(1 for mode in top5_execution_modes if mode == "ready_local_proxy_now")
    top5_bridged_ready_count = sum(1 for mode in top5_execution_modes if mode == "ready_local_bridged_now")
    top5_canonical_ready_count = sum(
        1 for mode in top5_execution_modes if mode in {"ready_local_now", "ready_local_canonical_now"}
    )
    top5_reference_collected_count = sum(1 for mode in top5_execution_modes if mode == "reference_collected_only")
    top5_remote_needed_count = sum(1 for mode in top5_execution_modes if mode == "remote_source_hunt_needed")

    checks = {
        "catalog_present_pass": bool(source_catalog),
        "catalog_family_count_pass": int(catalog_summary.get("family_count", 0) or 0) >= 20,
        "catalog_source_record_count_pass": int(catalog_summary.get("source_record_count", 0) or 0) >= 20,
        "catalog_local_ready_pass": local_ready_count >= 5,
        "catalog_remote_candidate_pass": remote_candidate_count >= 10,
        "triage_present_pass": bool(triage_report),
        "triage_native_roundtrip_candidate_pass": int(triage_summary.get("native_roundtrip_candidate_count", 0) or 0) >= 10,
        "triage_solver_benchmark_candidate_pass": int(triage_summary.get("solver_benchmark_candidate_count", 0) or 0) >= 8,
        "triage_ai_learning_candidate_pass": int(triage_summary.get("ai_learning_candidate_count", 0) or 0) >= 20,
        "triage_quick_start_local_pass": int(triage_summary.get("quick_start_local_source_count", 0) or 0) >= 5,
        "collection_report_present_pass": bool(collection_report.get("contract_pass", False)),
        "collection_collected_count_pass": collected_count >= 5,
        "collection_remote_candidate_count_pass": metadata_only_remote_candidate_count >= 10,
        "collection_no_rejections_pass": rejected_count == 0,
        "collection_alignment_pass": (
            collected_count >= local_ready_count
            and (collected_count + metadata_only_remote_candidate_count + rejected_count)
            == int(catalog_summary.get("source_record_count", 0) or 0)
        ),
        "top5_manifest_present_pass": bool(top5_manifest.get("contract_pass", False)),
        "top5_count_pass": len(top5_rows) == 5,
        "top5_execution_mode_pass": len(top5_execution_modes) == 5 and all(
            mode
            in {
                "ready_local_proxy_now",
                "ready_local_bridged_now",
                "ready_local_canonical_now",
                "ready_local_now",
                "reference_collected_only",
                "remote_source_hunt_needed",
            }
            for mode in top5_execution_modes
        ),
        "top5_local_reference_remote_mix_pass": (
            top5_local_ready_count + top5_reference_collected_count + top5_remote_needed_count
        ) == 5,
    }

    contract_pass = bool(all(checks.values()))
    if not checks["catalog_present_pass"] or not checks["catalog_family_count_pass"] or not checks["catalog_source_record_count_pass"]:
        reason_code = "ERR_CATALOG"
    elif not checks["triage_present_pass"] or not checks["triage_native_roundtrip_candidate_pass"] or not checks["triage_solver_benchmark_candidate_pass"]:
        reason_code = "ERR_TRIAGE"
    elif not checks["collection_report_present_pass"] or not checks["collection_collected_count_pass"]:
        reason_code = "ERR_COLLECTION"
    elif not checks["top5_manifest_present_pass"] or not checks["top5_count_pass"]:
        reason_code = "ERR_TOP5"
    else:
        reason_code = "PASS"

    summary = {
        "family_count": int(catalog_summary.get("family_count", 0) or 0),
        "source_record_count": int(catalog_summary.get("source_record_count", 0) or 0),
        "local_ready_count": local_ready_count,
        "remote_candidate_count": remote_candidate_count,
        "authority_high_like_count": int(catalog_summary.get("authority_high_like_count", 0) or 0),
        "ai_high_like_count": int(catalog_summary.get("ai_high_like_count", 0) or 0),
        "native_roundtrip_candidate_count": int(triage_summary.get("native_roundtrip_candidate_count", 0) or 0),
        "solver_benchmark_candidate_count": int(triage_summary.get("solver_benchmark_candidate_count", 0) or 0),
        "ai_learning_candidate_count": int(triage_summary.get("ai_learning_candidate_count", 0) or 0),
        "quick_start_local_source_count": int(triage_summary.get("quick_start_local_source_count", 0) or 0),
        "collected_count": collected_count,
        "metadata_only_remote_candidate_count": metadata_only_remote_candidate_count,
        "rejected_count": rejected_count,
        "format_counts": collection_summary.get("format_counts") if isinstance(collection_summary.get("format_counts"), dict) else {},
        "top5_count": len(top5_rows),
        "top5_local_ready_count": top5_local_ready_count,
        "top5_proxy_ready_count": top5_proxy_ready_count,
        "top5_bridged_ready_count": top5_bridged_ready_count,
        "top5_canonical_ready_count": top5_canonical_ready_count,
        "top5_reference_collected_count": top5_reference_collected_count,
        "top5_remote_needed_count": top5_remote_needed_count,
        "top5_execution_modes": top5_execution_modes,
        "top5_manifest_summary_line": str(top5_manifest.get("summary_line", "") or "").strip(),
    }
    summary_line = (
        "Irregular structure collection gate: "
        f"{'PASS' if contract_pass else 'CHECK'} | families={summary['family_count']} | "
        f"sources={summary['source_record_count']} | local_ready={summary['local_ready_count']} | "
        f"remote_candidates={summary['remote_candidate_count']} | collected={summary['collected_count']} | "
        f"native_roundtrip_candidates={summary['native_roundtrip_candidate_count']} | "
        f"solver_candidates={summary['solver_benchmark_candidate_count']} | ai_candidates={summary['ai_learning_candidate_count']} | "
        f"top5={summary['top5_count']} (local={summary['top5_local_ready_count']},proxy={summary['top5_proxy_ready_count']},"
        f"bridged={summary['top5_bridged_ready_count']},canonical={summary['top5_canonical_ready_count']},"
        f"reference={summary['top5_reference_collected_count']},remote={summary['top5_remote_needed_count']})"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-irregular-structure-collection-gate",
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
    parser.add_argument("--source-catalog", "--catalog", dest="source_catalog", default="implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json")
    parser.add_argument("--triage-report", default="implementation/phase1/open_data/irregular/irregular_structure_triage_report.json")
    parser.add_argument("--collection-report", default="implementation/phase1/open_data/irregular/irregular_structure_collection_report.json")
    parser.add_argument("--top5-manifest", "--top5-execution-manifest", dest="top5_manifest", default="implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json")
    parser.add_argument("--out", default="implementation/phase1/irregular_structure_collection_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "source_catalog": str(args.source_catalog),
        "triage_report": str(args.triage_report),
        "collection_report": str(args.collection_report),
        "top5_manifest": str(args.top5_manifest),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_irregular_structure_collection_gate")
        report = run_gate(
            source_catalog=_load_json(Path(args.source_catalog)),
            triage_report=_load_json(Path(args.triage_report)),
            collection_report=_load_json(Path(args.collection_report)),
            top5_manifest=_load_json(Path(args.top5_manifest)),
        )
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-irregular-structure-collection-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote irregular structure collection gate report: {out}")
    raise SystemExit(0 if bool(report.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
