#!/usr/bin/env python3
"""Track closure progress for the MIDAS exact roundtrip gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "MIDAS exact roundtrip closure is satisfied for the current evidence set",
    "ERR_INVALID_INPUT": "invalid MIDAS exact roundtrip closure gate input",
    "ERR_NATIVE_GATE": "native MIDAS roundtrip gate is not passing",
    "ERR_INTEROPERABILITY_GATE": "MIDAS interoperability gate is not passing",
    "ERR_EXACT_CLOSURE_PENDING": "bounded-subset artifacts exist but exact roundtrip closure is still pending",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["native_roundtrip_report", "interoperability_report", "out"],
    "properties": {
        "native_roundtrip_report": {"type": "string", "minLength": 1},
        "interoperability_report": {"type": "string", "minLength": 1},
        "diff_receipts_report": {"type": "string", "minLength": 1},
        "corpus_manifest": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}

DEFAULT_NATIVE_ROUNDTRIP_REPORT = "implementation/phase1/midas_native_roundtrip_gate_report.json"
DEFAULT_INTEROPERABILITY_REPORT = "implementation/phase1/midas_interoperability_gate_report.json"
DEFAULT_DIFF_RECEIPTS_REPORT = (
    "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json"
)
DEFAULT_CORPUS_MANIFEST = "implementation/phase1/open_data/midas/midas_native_corpus_manifest.json"
DEFAULT_OUT = "implementation/phase1/midas_exact_roundtrip_closure_gate_report.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _row_taxonomy_counts(receipt_row: dict[str, Any]) -> dict[str, int]:
    taxonomy = receipt_row.get("taxonomy")
    if not isinstance(taxonomy, dict):
        return {}
    counts = taxonomy.get("counts")
    if not isinstance(counts, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in counts.items():
        try:
            normalized[str(key)] = int(value or 0)
        except (TypeError, ValueError):
            normalized[str(key)] = 0
    return normalized


def _is_intentional_optimized_writeback_case(case_row: dict[str, Any]) -> bool:
    if not isinstance(case_row, dict):
        return False
    metrics = case_row.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    case_id = str(case_row.get("case_id", "") or "")
    role = str(case_row.get("role", "") or "")
    source_family = str(case_row.get("source_family", "") or "")
    provenance_class = str(case_row.get("provenance_class", "") or "")
    writeback_mode = str(case_row.get("writeback_mode", "") or "")
    notes = str(case_row.get("notes", "") or "")
    direct_patch_change_count = int(metrics.get("direct_patch_change_count", 0) or 0)
    return bool(
        "optimized_writeback" in case_id
        and bool(case_row.get("native_writeback_ready", False))
        and (
            role == "native_writeback_public_derived"
            or source_family == "derived_native_writeback"
            or provenance_class == "public_derived_writeback"
        )
        and (
            writeback_mode.startswith("direct_patch")
            or direct_patch_change_count > 0
            or "Derived native MIDAS write-back candidate" in notes
        )
    )


def _is_parser_drop_fixture_case(case_row: dict[str, Any]) -> bool:
    if not isinstance(case_row, dict):
        return False
    checks = case_row.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    case_id = str(case_row.get("case_id", "") or "")
    role = str(case_row.get("role", "") or "")
    source_family = str(case_row.get("source_family", "") or "")
    source_class = str(case_row.get("source_class", "") or "")
    writeback_mode = str(case_row.get("writeback_mode", "") or "")
    notes = str(case_row.get("notes", "") or "")
    parser_drop_signal = bool(case_row.get("parser_drop_suspected", False)) or "parser_drop" in case_id or "parser_drop" in source_family
    fixture_signal = (
        role == "native_writeback_fixture_derived"
        or "fixture" in source_class
        or writeback_mode == "fixture_identity_baseline"
        or bool(checks.get("fixture_identity_mode", False))
        or "Fixture-native identity/canonical roundtrip baseline" in notes
    )
    return bool(parser_drop_signal and fixture_signal)


def _derive_closure_scope(
    *,
    native_summary: dict[str, Any],
    diff_receipts_report: dict[str, Any],
    corpus_manifest: dict[str, Any],
) -> dict[str, Any]:
    taxonomy_case_counts = (
        native_summary.get("taxonomy_case_counts")
        if isinstance(native_summary.get("taxonomy_case_counts"), dict)
        else {}
    )
    receipt_rows_raw = diff_receipts_report.get("receipt_rows")
    receipt_rows = receipt_rows_raw if isinstance(receipt_rows_raw, list) else []
    manifest_cases_raw = corpus_manifest.get("cases")
    manifest_cases = manifest_cases_raw if isinstance(manifest_cases_raw, list) else []
    manifest_by_case_id = {
        str(case_row.get("case_id", "") or ""): case_row
        for case_row in manifest_cases
        if isinstance(case_row, dict) and str(case_row.get("case_id", "") or "")
    }
    if not receipt_rows:
        return {
            "used_precise_scope": False,
            "ready_case_count": int(native_summary.get("native_writeback_ready_count", 0) or 0),
            "exact_case_count": int(taxonomy_case_counts.get("preserved_exact", 0) or 0),
            "canonical_case_count": int(taxonomy_case_counts.get("canonical_rewrite", 0) or 0),
            "lossy_case_count": int(taxonomy_case_counts.get("lossy_rewrite", 0) or 0),
            "unsupported_case_count": int(taxonomy_case_counts.get("unsupported_card", 0) or 0),
            "manual_review_case_count": int(taxonomy_case_counts.get("manual_review_required", 0) or 0),
            "parser_drop_suspected_case_count": int(taxonomy_case_counts.get("parser_drop_suspected", 0) or 0),
            "pending_review_total": int(native_summary.get("pending_review_total", 0) or 0),
            "excluded_case_ids": [],
            "excluded_case_counts_by_reason": {},
            "excluded_case_count": 0,
        }

    scoped_rows: list[dict[str, Any]] = []
    excluded_case_ids: list[str] = []
    excluded_case_counts_by_reason: dict[str, int] = {}
    for receipt_row in receipt_rows:
        if not isinstance(receipt_row, dict):
            continue
        case_id = str(receipt_row.get("case_id", "") or "")
        taxonomy_counts = _row_taxonomy_counts(receipt_row)
        manifest_case = manifest_by_case_id.get(case_id, {})
        excluded_reasons: list[str] = []
        if taxonomy_counts.get("canonical_rewrite", 0) > 0 and _is_intentional_optimized_writeback_case(manifest_case):
            excluded_reasons.append("intentional_optimized_writeback")
        if taxonomy_counts.get("parser_drop_suspected", 0) > 0 and _is_parser_drop_fixture_case(manifest_case):
            excluded_reasons.append("parser_drop_fixture")
        if excluded_reasons:
            excluded_case_ids.append(case_id)
            for reason in excluded_reasons:
                excluded_case_counts_by_reason[reason] = excluded_case_counts_by_reason.get(reason, 0) + 1
            continue
        scoped_rows.append(receipt_row)

    def _sum_taxonomy(label: str) -> int:
        return sum(_row_taxonomy_counts(row).get(label, 0) for row in scoped_rows)

    return {
        "used_precise_scope": True,
        "ready_case_count": len(scoped_rows),
        "exact_case_count": _sum_taxonomy("preserved_exact"),
        "canonical_case_count": _sum_taxonomy("canonical_rewrite"),
        "lossy_case_count": _sum_taxonomy("lossy_rewrite"),
        "unsupported_case_count": _sum_taxonomy("unsupported_card"),
        "manual_review_case_count": _sum_taxonomy("manual_review_required"),
        "parser_drop_suspected_case_count": _sum_taxonomy("parser_drop_suspected"),
        "pending_review_total": sum(int(row.get("review_pending_count", 0) or 0) for row in scoped_rows),
        "excluded_case_ids": excluded_case_ids,
        "excluded_case_counts_by_reason": excluded_case_counts_by_reason,
        "excluded_case_count": len(excluded_case_ids),
    }


def run_gate(
    *,
    native_roundtrip_report: dict[str, Any],
    interoperability_report: dict[str, Any],
    diff_receipts_report: dict[str, Any],
    corpus_manifest: dict[str, Any],
) -> dict[str, Any]:
    native_summary = (
        native_roundtrip_report.get("summary")
        if isinstance(native_roundtrip_report.get("summary"), dict)
        else {}
    )
    interoperability_summary = (
        interoperability_report.get("summary")
        if isinstance(interoperability_report.get("summary"), dict)
        else {}
    )
    remaining_limits = [
        str(item)
        for item in (interoperability_summary.get("remaining_limits") or [])
        if str(item).strip()
    ]
    closure_scope = _derive_closure_scope(
        native_summary=native_summary,
        diff_receipts_report=diff_receipts_report,
        corpus_manifest=corpus_manifest,
    )

    ready_case_count = int(closure_scope.get("ready_case_count", 0) or 0)
    exact_case_count = int(closure_scope.get("exact_case_count", 0) or 0)
    canonical_case_count = int(closure_scope.get("canonical_case_count", 0) or 0)
    lossy_case_count = int(closure_scope.get("lossy_case_count", 0) or 0)
    unsupported_case_count = int(closure_scope.get("unsupported_case_count", 0) or 0)
    manual_review_case_count = int(closure_scope.get("manual_review_case_count", 0) or 0)
    parser_drop_suspected_case_count = int(closure_scope.get("parser_drop_suspected_case_count", 0) or 0)
    pending_review_total = int(closure_scope.get("pending_review_total", 0) or 0)
    exact_queue_pending_candidate_count = int(
        native_summary.get("exact_topology_structural_preview_pending_candidate_count", 0) or 0
    )
    exact_queue_candidate_total = int(
        native_summary.get("exact_topology_structural_preview_candidate_total", 0) or 0
    )

    checks = {
        "native_roundtrip_gate_pass": bool(native_roundtrip_report.get("contract_pass", False)),
        "interoperability_gate_pass": bool(interoperability_report.get("contract_pass", False)),
        "ready_case_present_pass": ready_case_count >= 1,
        "all_ready_cases_exact_pass": ready_case_count >= 1 and exact_case_count == ready_case_count,
        "canonical_rewrite_zero_pass": canonical_case_count == 0,
        "lossy_rewrite_zero_pass": lossy_case_count == 0,
        "unsupported_card_zero_pass": unsupported_case_count == 0,
        "manual_review_zero_pass": manual_review_case_count == 0,
        "parser_drop_suspected_zero_pass": parser_drop_suspected_case_count == 0,
        "pending_review_zero_pass": pending_review_total == 0,
        "exact_queue_zero_pass": exact_queue_pending_candidate_count == 0,
        "remaining_limits_zero_pass": len(remaining_limits) == 0,
    }

    contract_pass = bool(
        checks["native_roundtrip_gate_pass"]
        and checks["interoperability_gate_pass"]
        and checks["ready_case_present_pass"]
        and checks["all_ready_cases_exact_pass"]
        and checks["canonical_rewrite_zero_pass"]
        and checks["lossy_rewrite_zero_pass"]
        and checks["unsupported_card_zero_pass"]
        and checks["manual_review_zero_pass"]
        and checks["parser_drop_suspected_zero_pass"]
        and checks["pending_review_zero_pass"]
        and checks["exact_queue_zero_pass"]
        and checks["remaining_limits_zero_pass"]
    )

    if not checks["native_roundtrip_gate_pass"]:
        reason_code = "ERR_NATIVE_GATE"
    elif not checks["interoperability_gate_pass"]:
        reason_code = "ERR_INTEROPERABILITY_GATE"
    elif not contract_pass:
        reason_code = "ERR_EXACT_CLOSURE_PENDING"
    else:
        reason_code = "PASS"

    exact_case_ratio = float(exact_case_count) / float(ready_case_count) if ready_case_count else 0.0
    summary = {
        "native_roundtrip_summary_line": str(native_roundtrip_report.get("summary_line", "") or ""),
        "interoperability_summary_line": str(interoperability_report.get("summary_line", "") or ""),
        "ready_case_count": ready_case_count,
        "exact_case_count": exact_case_count,
        "exact_case_ratio": exact_case_ratio,
        "eligible_exact_candidate_count": ready_case_count,
        "eligible_exact_case_count": exact_case_count,
        "canonical_rewrite_case_count": canonical_case_count,
        "lossy_rewrite_case_count": lossy_case_count,
        "unsupported_card_case_count": unsupported_case_count,
        "manual_review_case_count": manual_review_case_count,
        "parser_drop_suspected_case_count": parser_drop_suspected_case_count,
        "pending_review_total": pending_review_total,
        "exact_queue_pending_candidate_count": exact_queue_pending_candidate_count,
        "exact_queue_candidate_total": exact_queue_candidate_total,
        "closure_scope_used_precise_receipts": bool(closure_scope.get("used_precise_scope", False)),
        "closure_scope_excluded_case_count": int(closure_scope.get("excluded_case_count", 0) or 0),
        "closure_scope_excluded_case_ids": list(closure_scope.get("excluded_case_ids") or []),
        "closure_scope_excluded_case_counts_by_reason": dict(
            closure_scope.get("excluded_case_counts_by_reason") or {}
        ),
        "eligible_exact_exclusion_case_count": int(closure_scope.get("excluded_case_count", 0) or 0),
        "eligible_exact_exclusion_labels": sorted(
            str(label)
            for label in (closure_scope.get("excluded_case_counts_by_reason") or {}).keys()
            if str(label).strip()
        ),
        "eligible_exact_exclusion_label_counts": dict(
            sorted(
                (
                    str(label),
                    int(count or 0),
                )
                for label, count in (closure_scope.get("excluded_case_counts_by_reason") or {}).items()
                if str(label).strip()
            )
        ),
        "remaining_limits": remaining_limits,
        "bounded_subset_mode": str(interoperability_summary.get("bounded_subset_mode", "") or ""),
        "roundtrip_exact_entry_row_coverage_min": float(
            interoperability_summary.get("roundtrip_exact_entry_row_coverage_min", 0.0) or 0.0
        ),
        "roundtrip_exact_header_coverage_min": float(
            interoperability_summary.get("roundtrip_exact_header_coverage_min", 0.0) or 0.0
        ),
        "roundtrip_exact_factor_map_coverage_min": float(
            interoperability_summary.get("roundtrip_exact_factor_map_coverage_min", 0.0) or 0.0
        ),
    }
    summary_line = (
        "MIDAS exact roundtrip closure: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"exact={exact_case_count}/{ready_case_count} | "
        f"canonical={canonical_case_count} | "
        f"lossy={lossy_case_count} | "
        f"unsupported={unsupported_case_count} | "
        f"manual={manual_review_case_count} | "
        f"pending_review={pending_review_total} | "
        f"exact_queue={exact_queue_pending_candidate_count}/{exact_queue_candidate_total} | "
        f"scope_excluded={int(closure_scope.get('excluded_case_count', 0) or 0)} | "
        f"limits={'none' if not remaining_limits else ','.join(remaining_limits)}"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-midas-exact-roundtrip-closure-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "checks": checks,
        "summary": summary,
        "summary_line": summary_line,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-roundtrip-report", default=DEFAULT_NATIVE_ROUNDTRIP_REPORT)
    parser.add_argument("--interoperability-report", default=DEFAULT_INTEROPERABILITY_REPORT)
    parser.add_argument("--diff-receipts-report", default=DEFAULT_DIFF_RECEIPTS_REPORT)
    parser.add_argument("--corpus-manifest", default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    input_payload = {
        "native_roundtrip_report": str(args.native_roundtrip_report),
        "interoperability_report": str(args.interoperability_report),
        "diff_receipts_report": str(args.diff_receipts_report),
        "corpus_manifest": str(args.corpus_manifest),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(
            input_payload,
            INPUT_SCHEMA,
            label="phase1.run_midas_exact_roundtrip_closure_gate",
        )
        payload = run_gate(
            native_roundtrip_report=_load_json(Path(args.native_roundtrip_report)),
            interoperability_report=_load_json(Path(args.interoperability_report)),
            diff_receipts_report=_load_json(Path(args.diff_receipts_report)),
            corpus_manifest=_load_json(Path(args.corpus_manifest)),
        )
    except InputContractError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-midas-exact-roundtrip-closure-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
            "checks": {},
            "summary": {},
            "summary_line": "MIDAS exact roundtrip closure: CHECK | invalid input",
        }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote MIDAS exact roundtrip closure gate report: {out}")
    return 0 if bool(payload.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
