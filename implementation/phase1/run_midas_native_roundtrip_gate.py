#!/usr/bin/env python3
"""Gate native MIDAS roundtrip/write-back evidence across the real-source corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

REASONS = {
    "PASS": "native MIDAS roundtrip corpus and per-case write-back diff receipts are present",
    "ERR_INVALID_INPUT": "invalid native MIDAS roundtrip gate input",
    "ERR_CORPUS": "native MIDAS corpus evidence is incomplete",
    "ERR_RECEIPTS": "native MIDAS write-back diff receipt coverage is incomplete",
    "ERR_WRITEBACK": "one or more native MIDAS write-back cases failed topology/load/loadcomb stability checks",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["corpus_manifest", "diff_receipts_report", "out"],
    "properties": {
        "corpus_manifest": {"type": "string", "minLength": 1},
        "diff_receipts_report": {"type": "string", "minLength": 1},
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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _gap(required_total: int, completed_total: int) -> int:
    return max(int(required_total) - int(completed_total), 0)


def _coverage_ratio(completed_total: int, required_total: int) -> float:
    if required_total <= 0:
        return 1.0 if completed_total <= 0 else 0.0
    return round(float(completed_total) / float(required_total), 4)


def run_gate(*, corpus_manifest: dict[str, Any], diff_receipts_report: dict[str, Any]) -> dict[str, Any]:
    corpus_summary = corpus_manifest.get("summary") if isinstance(corpus_manifest.get("summary"), dict) else {}
    receipt_summary = diff_receipts_report.get("summary") if isinstance(diff_receipts_report.get("summary"), dict) else {}
    taxonomy_case_counts = (
        receipt_summary.get("taxonomy_case_counts")
        if isinstance(receipt_summary.get("taxonomy_case_counts"), dict)
        else {}
    )
    taxonomy_card_family_histogram = (
        receipt_summary.get("taxonomy_card_family_histogram")
        if isinstance(receipt_summary.get("taxonomy_card_family_histogram"), dict)
        else {}
    )
    exact_topology_queue_json = str(
        diff_receipts_report.get("exact_topology_structural_preview_promotion_queue_json", "") or ""
    )
    exact_topology_queue_markdown = str(
        diff_receipts_report.get("exact_topology_structural_preview_promotion_queue_markdown", "") or ""
    )
    exact_topology_queue_payload = (
        _load_json(Path(exact_topology_queue_json))
        if exact_topology_queue_json.strip() and Path(exact_topology_queue_json).exists()
        else {}
    )
    exact_topology_queue_summary = (
        exact_topology_queue_payload.get("summary")
        if isinstance(exact_topology_queue_payload.get("summary"), dict)
        else {}
    )
    exact_topology_queue_pending_candidate_rows = [
        dict(row)
        for row in (
            exact_topology_queue_payload.get("pending_candidate_rows")
            or exact_topology_queue_payload.get("rows")
            or []
        )
        if isinstance(row, dict)
    ]
    exact_topology_pending_candidate_rows = [
        dict(row)
        for row in (diff_receipts_report.get("exact_topology_structural_preview_pending_candidate_rows") or [])
        if isinstance(row, dict)
    ]
    korean_promotion_receipt_rows = [
        dict(row)
        for row in (diff_receipts_report.get("korean_structural_preview_promotion_receipt_rows") or [])
        if isinstance(row, dict)
    ]
    native_text_case_count = _safe_int(corpus_summary.get("native_text_case_count", 0))
    ready_case_count = _safe_int(corpus_summary.get("native_writeback_ready_count", 0))
    public_native_writeback_ready_count = _safe_int(corpus_summary.get("public_native_writeback_ready_count", 0))
    public_source_writeback_ready_count = _safe_int(corpus_summary.get("public_source_writeback_ready_count", 0))
    fixture_native_writeback_ready_count = _safe_int(corpus_summary.get("fixture_native_writeback_ready_count", 0))
    korean_exact_topology_candidate_count = _safe_int(
        corpus_summary.get("korean_source_catalog_exact_topology_candidate_count", 0)
    )
    korean_reconstruction_candidate_count = _safe_int(
        corpus_summary.get("korean_solver_ready_reconstruction_candidate_count", 0)
    )
    korean_reconstruction_prepared_count = _safe_int(
        corpus_summary.get("korean_solver_ready_reconstruction_prepared_count", 0)
    )
    receipt_count = _safe_int(receipt_summary.get("receipt_count", 0))
    receipt_pass_count = _safe_int(receipt_summary.get("receipt_pass_count", 0))
    topology_stable_case_count = _safe_int(receipt_summary.get("topology_stable_case_count", 0))
    load_contract_stable_case_count = _safe_int(receipt_summary.get("load_contract_stable_case_count", 0))
    loadcomb_exact_case_count = _safe_int(receipt_summary.get("loadcomb_exact_case_count", 0))
    unknown_rows_zero_case_count = _safe_int(receipt_summary.get("unknown_rows_zero_case_count", 0))
    structure_type_batch_count = _safe_int(receipt_summary.get("structure_type_batch_count", 0))
    exact_topology_candidate_total = _safe_int(
        receipt_summary.get("exact_topology_structural_preview_candidate_total", 0)
    )
    exact_topology_pending_candidate_count = _safe_int(
        receipt_summary.get("exact_topology_structural_preview_pending_candidate_count", 0)
    )
    exact_topology_public_archive_promoted_candidate_count = _safe_int(
        receipt_summary.get("exact_topology_structural_preview_public_archive_promoted_candidate_count", 0)
    )
    exact_topology_korean_candidate_total = _safe_int(
        receipt_summary.get("exact_topology_structural_preview_korean_candidate_total", 0)
    )
    exact_topology_korean_pending_candidate_count = _safe_int(
        receipt_summary.get("exact_topology_structural_preview_korean_pending_candidate_count", 0)
    )
    korean_structural_preview_promotion_receipt_count = _safe_int(
        receipt_summary.get("korean_structural_preview_promotion_receipt_count", 0)
    )
    exact_topology_promoted_candidate_count = max(
        exact_topology_candidate_total - exact_topology_pending_candidate_count, 0
    )
    korean_exact_topology_promoted_candidate_count = max(
        exact_topology_korean_candidate_total - exact_topology_korean_pending_candidate_count, 0
    )

    checks = {
        "corpus_manifest_present_pass": bool(corpus_manifest.get("contract_pass", False)),
        "native_text_case_present_pass": native_text_case_count >= 1,
        "fixture_native_text_case_present_pass": _safe_int(corpus_summary.get("fixture_native_text_case_count", 0)) >= 1,
        "archive_case_present_pass": _safe_int(corpus_summary.get("archive_case_count", 0)) >= 1,
        "native_writeback_ready_pass": ready_case_count >= 1,
        "public_native_writeback_ready_pass": public_native_writeback_ready_count >= 1,
        "public_source_writeback_ready_pass": public_source_writeback_ready_count >= 1,
        "fixture_native_writeback_ready_pass": fixture_native_writeback_ready_count >= 1,
        "diff_receipt_coverage_pass": bool(
            diff_receipts_report.get("contract_pass", False)
            and _safe_int(receipt_summary.get("ready_case_count", 0)) == ready_case_count
            and receipt_count == ready_case_count
        ),
        "per_case_writeback_pass": receipt_pass_count == ready_case_count >= 1,
        "topology_stability_pass": topology_stable_case_count == ready_case_count >= 1,
        "load_contract_stability_pass": load_contract_stable_case_count == ready_case_count >= 1,
        "loadcomb_exact_roundtrip_pass": loadcomb_exact_case_count == ready_case_count >= 1,
        "unknown_rows_zero_pass": unknown_rows_zero_case_count == ready_case_count >= 1,
        "structure_type_batches_present_pass": structure_type_batch_count >= 1,
        "taxonomy_present_pass": bool(taxonomy_case_counts)
        and sum(_safe_int(v) for v in taxonomy_case_counts.values()) >= ready_case_count,
        "exact_topology_structural_preview_queue_present_pass": bool(exact_topology_queue_json)
        and bool(exact_topology_queue_markdown)
        and Path(exact_topology_queue_json).exists()
        and Path(exact_topology_queue_markdown).exists(),
        "exact_topology_structural_preview_queue_summary_aligned_pass": bool(exact_topology_queue_summary)
        and _safe_int(exact_topology_queue_summary.get("candidate_total", 0)) == exact_topology_candidate_total
        and _safe_int(exact_topology_queue_summary.get("pending_candidate_count", 0))
        == exact_topology_pending_candidate_count
        and _safe_int(exact_topology_queue_summary.get("public_archive_promoted_candidate_count", 0))
        == exact_topology_public_archive_promoted_candidate_count
        and _safe_int(exact_topology_queue_summary.get("korean_candidate_total", 0))
        == exact_topology_korean_candidate_total
        and _safe_int(exact_topology_queue_summary.get("korean_pending_candidate_count", 0))
        == exact_topology_korean_pending_candidate_count,
        "exact_topology_structural_preview_queue_rows_aligned_pass": len(exact_topology_pending_candidate_rows)
        == exact_topology_pending_candidate_count
        and len(exact_topology_queue_pending_candidate_rows) == exact_topology_pending_candidate_count,
        "korean_exact_topology_candidates_accounted_pass": exact_topology_korean_candidate_total
        >= korean_exact_topology_candidate_count,
        "korean_structural_preview_promotion_receipts_present_pass": korean_structural_preview_promotion_receipt_count
        >= exact_topology_korean_pending_candidate_count,
        "korean_structural_preview_promotion_receipt_rows_aligned_pass": len(korean_promotion_receipt_rows)
        == korean_structural_preview_promotion_receipt_count,
    }
    contract_pass = bool(
        checks["corpus_manifest_present_pass"]
        and checks["native_text_case_present_pass"]
        and checks["archive_case_present_pass"]
        and checks["native_writeback_ready_pass"]
        and checks["public_native_writeback_ready_pass"]
        and checks["diff_receipt_coverage_pass"]
        and checks["per_case_writeback_pass"]
        and checks["topology_stability_pass"]
        and checks["load_contract_stability_pass"]
        and checks["loadcomb_exact_roundtrip_pass"]
        and checks["unknown_rows_zero_pass"]
        and checks["structure_type_batches_present_pass"]
        and checks["taxonomy_present_pass"]
        and checks["exact_topology_structural_preview_queue_present_pass"]
        and checks["exact_topology_structural_preview_queue_summary_aligned_pass"]
        and checks["exact_topology_structural_preview_queue_rows_aligned_pass"]
        and checks["korean_exact_topology_candidates_accounted_pass"]
        and checks["korean_structural_preview_promotion_receipts_present_pass"]
        and checks["korean_structural_preview_promotion_receipt_rows_aligned_pass"]
    )
    if not checks["corpus_manifest_present_pass"]:
        reason_code = "ERR_CORPUS"
    elif not checks["diff_receipt_coverage_pass"]:
        reason_code = "ERR_RECEIPTS"
    elif not contract_pass:
        reason_code = "ERR_WRITEBACK"
    else:
        reason_code = "PASS"

    summary = {
        "corpus_case_count": int(corpus_summary.get("corpus_case_count", 0) or 0),
        "actual_source_count": int(corpus_summary.get("actual_source_count", 0) or 0),
        "quality_actual_source_count": int(corpus_summary.get("quality_actual_source_count", 0) or 0),
        "public_raw_actual_source_count": int(corpus_summary.get("public_raw_actual_source_count", 0) or 0),
        "native_text_case_count": native_text_case_count,
        "public_native_text_case_count": int(corpus_summary.get("public_native_text_case_count", 0) or 0),
        "public_raw_native_text_case_count": int(corpus_summary.get("public_raw_native_text_case_count", 0) or 0),
        "public_bridge_text_case_count": int(corpus_summary.get("public_bridge_text_case_count", 0) or 0),
        "public_archive_preview_text_case_count": int(corpus_summary.get("public_archive_preview_text_case_count", 0) or 0),
        "public_archive_structural_preview_text_case_count": int(
            corpus_summary.get("public_archive_structural_preview_text_case_count", 0) or 0
        ),
        "fixture_native_text_case_count": int(corpus_summary.get("fixture_native_text_case_count", 0) or 0),
        "repo_native_text_case_count": int(corpus_summary.get("repo_native_text_case_count", 0) or 0),
        "experiment_native_text_case_count": int(corpus_summary.get("experiment_native_text_case_count", 0) or 0),
        "archive_case_count": int(corpus_summary.get("archive_case_count", 0) or 0),
        "native_writeback_ready_count": ready_case_count,
        "public_native_writeback_ready_count": int(corpus_summary.get("public_native_writeback_ready_count", 0) or 0),
        "public_raw_native_writeback_ready_count": int(
            corpus_summary.get("public_raw_native_writeback_ready_count", 0) or 0
        ),
        "public_bridge_writeback_ready_count": int(corpus_summary.get("public_bridge_writeback_ready_count", 0) or 0),
        "public_archive_preview_writeback_ready_count": int(
            corpus_summary.get("public_archive_preview_writeback_ready_count", 0) or 0
        ),
        "public_archive_structural_preview_writeback_ready_count": int(
            corpus_summary.get("public_archive_structural_preview_writeback_ready_count", 0) or 0
        ),
        "public_source_writeback_ready_count": public_source_writeback_ready_count,
        "fixture_native_writeback_ready_count": fixture_native_writeback_ready_count,
        "repo_native_writeback_ready_count": int(corpus_summary.get("repo_native_writeback_ready_count", 0) or 0),
        "experiment_native_writeback_ready_count": int(corpus_summary.get("experiment_native_writeback_ready_count", 0) or 0),
        "native_writeback_ready_gap_count": _gap(native_text_case_count, ready_case_count),
        "public_source_writeback_ready_gap_count": _gap(ready_case_count, public_source_writeback_ready_count),
        "receipt_pass_gap_count": _gap(ready_case_count, receipt_pass_count),
        "topology_stability_gap_count": _gap(ready_case_count, topology_stable_case_count),
        "load_contract_stability_gap_count": _gap(ready_case_count, load_contract_stable_case_count),
        "loadcomb_exact_gap_count": _gap(ready_case_count, loadcomb_exact_case_count),
        "unknown_rows_zero_gap_count": _gap(ready_case_count, unknown_rows_zero_case_count),
        "native_writeback_ready_coverage_ratio": _coverage_ratio(ready_case_count, native_text_case_count),
        "public_source_writeback_ready_coverage_ratio": _coverage_ratio(
            public_source_writeback_ready_count, ready_case_count
        ),
        "receipt_pass_coverage_ratio": _coverage_ratio(receipt_pass_count, ready_case_count),
        "topology_stability_coverage_ratio": _coverage_ratio(topology_stable_case_count, ready_case_count),
        "load_contract_stability_coverage_ratio": _coverage_ratio(
            load_contract_stable_case_count, ready_case_count
        ),
        "loadcomb_exact_roundtrip_coverage_ratio": _coverage_ratio(
            loadcomb_exact_case_count, ready_case_count
        ),
        "unknown_rows_zero_coverage_ratio": _coverage_ratio(unknown_rows_zero_case_count, ready_case_count),
        "korean_source_catalog_record_count": int(corpus_summary.get("korean_source_catalog_record_count", 0) or 0),
        "korean_source_catalog_exact_topology_candidate_count": int(
            corpus_summary.get("korean_source_catalog_exact_topology_candidate_count", 0) or 0
        ),
        "korean_source_catalog_curated_local_ifc_required_count": int(
            corpus_summary.get("korean_source_catalog_curated_local_ifc_required_count", 0) or 0
        ),
        "korean_source_catalog_curated_local_ifc_attached_count": int(
            corpus_summary.get("korean_source_catalog_curated_local_ifc_attached_count", 0) or 0
        ),
        "korean_source_catalog_exact_topology_candidate_pending_count": int(
            corpus_summary.get("korean_source_catalog_exact_topology_candidate_pending_count", 0) or 0
        ),
        "source_family_count": int(corpus_summary.get("source_family_count", 0) or 0),
        "structure_type_count": int(corpus_summary.get("structure_type_count", 0) or 0),
        "receipt_count": receipt_count,
        "receipt_pass_count": receipt_pass_count,
        "topology_stable_case_count": topology_stable_case_count,
        "load_contract_stable_case_count": load_contract_stable_case_count,
        "loadcomb_exact_case_count": loadcomb_exact_case_count,
        "pending_review_total": int(receipt_summary.get("pending_review_total", 0) or 0),
        "exact_topology_structural_preview_candidate_total": exact_topology_candidate_total,
        "exact_topology_structural_preview_pending_candidate_count": exact_topology_pending_candidate_count,
        "exact_topology_structural_preview_promoted_candidate_count": exact_topology_promoted_candidate_count,
        "exact_topology_structural_preview_public_archive_promoted_candidate_count": (
            exact_topology_public_archive_promoted_candidate_count
        ),
        "exact_topology_structural_preview_candidate_closure_ratio": _coverage_ratio(
            exact_topology_promoted_candidate_count, exact_topology_candidate_total
        ),
        "exact_topology_structural_preview_korean_candidate_total": exact_topology_korean_candidate_total,
        "exact_topology_structural_preview_korean_pending_candidate_count": (
            exact_topology_korean_pending_candidate_count
        ),
        "korean_exact_topology_promoted_candidate_count": korean_exact_topology_promoted_candidate_count,
        "korean_exact_topology_candidate_closure_ratio": _coverage_ratio(
            korean_exact_topology_promoted_candidate_count, exact_topology_korean_candidate_total
        ),
        "korean_structural_preview_promotion_receipt_count": korean_structural_preview_promotion_receipt_count,
        "korean_solver_ready_reconstruction_candidate_count": korean_reconstruction_candidate_count,
        "korean_solver_ready_reconstruction_prepared_count": korean_reconstruction_prepared_count,
        "korean_solver_ready_reconstruction_gap_count": _gap(
            korean_reconstruction_candidate_count, korean_reconstruction_prepared_count
        ),
        "korean_solver_ready_reconstruction_prepared_ratio": _coverage_ratio(
            korean_reconstruction_prepared_count, korean_reconstruction_candidate_count
        ),
        "korean_solver_ready_reconstruction_missing_curated_local_ifc_reference_count": int(
            corpus_summary.get("korean_solver_ready_reconstruction_missing_curated_local_ifc_reference_count", 0)
            or 0
        ),
        "structure_type_batch_count": structure_type_batch_count,
        "taxonomy_case_counts": taxonomy_case_counts,
        "taxonomy_card_family_histogram": taxonomy_card_family_histogram,
        "structure_type_batch_markdowns": [
            str(row.get("batch_markdown", "") or "")
            for row in (diff_receipts_report.get("structure_type_batches") or [])
            if isinstance(row, dict) and str(row.get("batch_markdown", "") or "").strip()
        ],
        "unsupported_lossy_card_family_appendix_markdown": str(
            diff_receipts_report.get("unsupported_lossy_card_family_appendix_markdown", "") or ""
        ),
        "unsupported_lossy_card_family_appendix_json": str(
            diff_receipts_report.get("unsupported_lossy_card_family_appendix_json", "") or ""
        ),
        "exact_topology_structural_preview_promotion_queue_json": exact_topology_queue_json,
        "exact_topology_structural_preview_promotion_queue_markdown": exact_topology_queue_markdown,
        "exact_topology_structural_preview_pending_candidate_rows": exact_topology_pending_candidate_rows,
        "korean_structural_preview_promotion_receipt_rows": korean_promotion_receipt_rows,
    }
    summary_line = (
        "MIDAS native roundtrip: "
        f"{'PASS' if contract_pass else 'CHECK'} | corpus={summary['corpus_case_count']} | "
        f"native_text={summary['native_text_case_count']} | public_native={summary['public_native_text_case_count']} | "
        f"public_raw_native={summary['public_raw_native_text_case_count']} | "
        f"public_bridge_native={summary['public_bridge_text_case_count']} | "
        f"public_preview_native={summary['public_archive_preview_text_case_count']} | "
        f"public_structural_preview_native={summary['public_archive_structural_preview_text_case_count']} | "
        f"fixture_native={summary['fixture_native_text_case_count']} | repo_native={summary['repo_native_text_case_count']} | "
        f"experiment_native={summary['experiment_native_text_case_count']} | archives={summary['archive_case_count']} | "
        f"ready={summary['native_writeback_ready_count']} | public_ready={summary['public_source_writeback_ready_count']} | "
        f"public_native_ready={summary['public_native_writeback_ready_count']} | "
        f"public_raw_ready={summary['public_raw_native_writeback_ready_count']} | "
        f"public_bridge_ready={summary['public_bridge_writeback_ready_count']} | "
        f"public_preview_ready={summary['public_archive_preview_writeback_ready_count']} | "
        f"public_structural_preview_ready={summary['public_archive_structural_preview_writeback_ready_count']} | "
        f"exact_queue={summary['exact_topology_structural_preview_pending_candidate_count']}/"
        f"{summary['exact_topology_structural_preview_candidate_total']} | "
        f"korean_reconstruction={summary['korean_solver_ready_reconstruction_prepared_count']}/"
        f"{summary['korean_solver_ready_reconstruction_candidate_count']} | "
        f"korean_promotions={summary['korean_structural_preview_promotion_receipt_count']}/"
        f"{summary['exact_topology_structural_preview_korean_pending_candidate_count']} | "
        f"fixture_ready={summary['fixture_native_writeback_ready_count']} | repo_ready={summary['repo_native_writeback_ready_count']} | "
        f"experiment_ready={summary['experiment_native_writeback_ready_count']} | "
        f"receipts={summary['receipt_pass_count']}/{summary['receipt_count']} | "
        f"topology={summary['topology_stable_case_count']}/{summary['native_writeback_ready_count']} | "
        f"load={summary['load_contract_stable_case_count']}/{summary['native_writeback_ready_count']} | "
        f"loadcomb={summary['loadcomb_exact_case_count']}/{summary['native_writeback_ready_count']} exact | "
        f"coverage=ready:{summary['native_writeback_ready_coverage_ratio']:.0%},"
        f"receipts:{summary['receipt_pass_coverage_ratio']:.0%},"
        f"loadcomb:{summary['loadcomb_exact_roundtrip_coverage_ratio']:.0%},"
        f"public_source:{summary['public_source_writeback_ready_coverage_ratio']:.0%},"
        f"exact_queue:{summary['exact_topology_structural_preview_candidate_closure_ratio']:.0%},"
        f"kr_recon:{summary['korean_solver_ready_reconstruction_prepared_ratio']:.0%} | "
        f"gaps=ready:{summary['native_writeback_ready_gap_count']},"
        f"receipts:{summary['receipt_pass_gap_count']},"
        f"topology:{summary['topology_stability_gap_count']},"
        f"load:{summary['load_contract_stability_gap_count']},"
        f"loadcomb:{summary['loadcomb_exact_gap_count']},"
        f"public_source:{summary['public_source_writeback_ready_gap_count']},"
        f"exact_queue:{summary['exact_topology_structural_preview_pending_candidate_count']},"
        f"korean_reconstruction:{summary['korean_solver_ready_reconstruction_gap_count']} | "
        f"types={summary['structure_type_batch_count']} | "
        f"taxonomy=exact:{int(taxonomy_case_counts.get('preserved_exact', 0) or 0)},canonical:{int(taxonomy_case_counts.get('canonical_rewrite', 0) or 0)},"
        f"lossy:{int(taxonomy_case_counts.get('lossy_rewrite', 0) or 0)},unsupported:{int(taxonomy_case_counts.get('unsupported_card', 0) or 0)},"
        f"manual:{int(taxonomy_case_counts.get('manual_review_required', 0) or 0)} | "
        f"pending_review={summary['pending_review_total']}"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-midas-native-roundtrip-gate",
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
    parser.add_argument(
        "--corpus-manifest",
        default="implementation/phase1/open_data/midas/midas_native_corpus_manifest.json",
    )
    parser.add_argument(
        "--diff-receipts-report",
        default="implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
    )
    parser.add_argument("--out", default="implementation/phase1/midas_native_roundtrip_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "corpus_manifest": str(args.corpus_manifest),
        "diff_receipts_report": str(args.diff_receipts_report),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_midas_native_roundtrip_gate")
        report = run_gate(
            corpus_manifest=_load_json(Path(args.corpus_manifest)),
            diff_receipts_report=_load_json(Path(args.diff_receipts_report)),
        )
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-midas-native-roundtrip-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote MIDAS native roundtrip gate report: {out}")
    raise SystemExit(0 if bool(report.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
