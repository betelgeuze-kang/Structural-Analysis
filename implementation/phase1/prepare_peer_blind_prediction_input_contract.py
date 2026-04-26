#!/usr/bin/env python3
"""Build a normalized input contract for the public PEER blind-prediction bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_BUNDLE_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_public_input_bundle_report.json"
)
DEFAULT_SOURCE_MANIFEST = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json"
)
DEFAULT_MEASURED_STATUS = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json"
)
DEFAULT_MEASURED_LANDING_MANIFEST = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _gm_case_labels(gm_workbook_summary: dict[str, Any]) -> list[str]:
    names = [str(item) for item in (gm_workbook_summary.get("gm_names") or []) if str(item or "")]
    if names:
        return names
    sequence = [str(item) for item in (gm_workbook_summary.get("sequence_labels") or []) if str(item or "")]
    seen: set[str] = set()
    labels: list[str] = []
    for item in sequence:
        if item in seen:
            continue
        seen.add(item)
        labels.append(item)
    return labels


def build_contract(
    bundle_report: dict[str, Any],
    source_manifest: dict[str, Any],
    measured_status: dict[str, Any],
    measured_landing_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    measured_landing_manifest = measured_landing_manifest if isinstance(measured_landing_manifest, dict) else {}
    landing_manifest_present = bool(measured_landing_manifest)
    landing_manifest_contract_pass = bool(measured_landing_manifest.get("contract_pass", False))
    bundle_summary = bundle_report.get("summary") if isinstance(bundle_report.get("summary"), dict) else {}
    gm_workbook_summary = (
        bundle_report.get("gm_workbook_summary")
        if isinstance(bundle_report.get("gm_workbook_summary"), dict)
        else {}
    )
    materials_bundle_summary = (
        bundle_report.get("materials_bundle_summary")
        if isinstance(bundle_report.get("materials_bundle_summary"), dict)
        else {}
    )
    source_manifest_summary = (
        source_manifest.get("summary")
        if isinstance(source_manifest.get("summary"), dict)
        else {}
    )
    expected_groups = (
        source_manifest.get("expected_groups")
        if isinstance(source_manifest.get("expected_groups"), dict)
        else {}
    )
    landing_summary = (
        measured_landing_manifest.get("summary")
        if isinstance(measured_landing_manifest.get("summary"), dict)
        else {}
    )
    gm_case_labels = _gm_case_labels(gm_workbook_summary)
    public_input_ready = bool(bundle_report.get("contract_pass", False))
    measured_response_ready = bool(measured_status.get("measured_response_present", False))
    normalization_ready = public_input_ready
    benchmark_case_ready = public_input_ready and measured_response_ready
    required_group_pass_count = int(source_manifest_summary.get("required_group_pass_count", 0) or 0)
    required_group_count = int(source_manifest_summary.get("required_group_count", 0) or 0)
    material_sheets = (
        materials_bundle_summary.get("materials_workbook", {}).get("sheet_names", [])
        if isinstance(materials_bundle_summary.get("materials_workbook"), dict)
        else []
    )
    reason_code = (
        "PASS_INPUT_CONTRACT_READY"
        if benchmark_case_ready
        else "PASS_INPUT_CONTRACT_READY_MEASURED_PENDING"
        if public_input_ready
        else "ERR_PUBLIC_INPUT_CONTRACT_INCOMPLETE"
    )
    reason = (
        "Public blind-prediction input contract is complete and ready for benchmark-case normalization."
        if benchmark_case_ready
        else "Public blind-prediction input contract is ready; measured response remains the only missing contract group."
        if public_input_ready
        else "Public blind-prediction input bundle is still incomplete for contract-based normalization."
    )
    proposed_case_ids = [
        f"edefense_peer_blind_prediction_seed_01::{label.lower().replace(' ', '_')}"
        for label in gm_case_labels
    ]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_family": str(source_manifest.get("source_family", "") or "edefense_peer_blind_prediction"),
        "seed_id": str(source_manifest.get("seed_id", "") or "edefense_peer_blind_prediction_seed_01"),
        "benchmark_track": str(source_manifest.get("benchmark_track", "") or "blind_prediction_dynamic_holdout"),
        "source_manifest": str(DEFAULT_SOURCE_MANIFEST),
        "bundle_report": str(DEFAULT_BUNDLE_REPORT),
        "measured_response_status": str(DEFAULT_MEASURED_STATUS),
        "measured_response_landing_manifest": str(DEFAULT_MEASURED_LANDING_MANIFEST),
        "input_root": str(source_manifest.get("local_input_root", "") or measured_status.get("input_root", "")),
        "contract_pass": public_input_ready,
        "reason_code": reason_code,
        "reason": reason,
        "summary_line": (
            f"PEER blind input contract: {'PASS' if public_input_ready else 'CHECK'} | "
            f"gm_cases={len(gm_case_labels)} | groups={required_group_pass_count}/{required_group_count} | "
            f"measured_response={'ready' if measured_response_ready else 'pending'} | "
            f"landing_manifest={'recorded' if landing_manifest_present else 'missing'}"
        ),
        "summary": {
            "geometry_doc_count": int(bundle_summary.get("geometry_doc_count", 0) or 0),
            "material_sheet_count": len(material_sheets),
            "gm_name_count": int(gm_workbook_summary.get("gm_name_count", 0) or len(gm_case_labels)),
            "gm_sequence_step_count": int(gm_workbook_summary.get("sequence_step_count", 0) or 0),
            "required_group_pass_count": required_group_pass_count,
            "required_group_count": required_group_count,
            "landing_manifest_contract_pass": landing_manifest_contract_pass,
            "landing_manifest_matched_file_count": int(landing_summary.get("matched_file_count", 0) or 0),
            "landing_manifest_csv_file_count": int(landing_summary.get("csv_file_count", 0) or 0),
        },
        "readiness": {
            "public_input_ready": public_input_ready,
            "measured_response_ready": measured_response_ready,
            "measured_response_landing_manifest_ready": landing_manifest_contract_pass,
            "normalization_ready": normalization_ready,
            "benchmark_case_ready": benchmark_case_ready,
            "compare_report_ready": benchmark_case_ready,
            "viewer_entry_ready": benchmark_case_ready,
        },
        "geometry_package": {
            "doc_count": int(bundle_summary.get("geometry_doc_count", 0) or 0),
            "docs": [str(item) for item in (bundle_report.get("geometry_docs") or []) if str(item or "")],
            "present": bool(bundle_summary.get("geometry_doc_count", 0) or 0),
        },
        "material_package": {
            "bundle_present": bool(bundle_summary.get("material_bundle_present", False)),
            "bundle_files": [
                str(item)
                for item in (materials_bundle_summary.get("bundle_files") or [])
                if str(item or "")
            ],
            "sheet_names": [str(item) for item in material_sheets if str(item or "")],
        },
        "excitation_package": {
            "gm_workbook_present": bool(bundle_summary.get("gm_workbook_present", False)),
            "gm_name_count": int(gm_workbook_summary.get("gm_name_count", 0) or len(gm_case_labels)),
            "gm_case_labels": gm_case_labels,
            "sequence_labels": [
                str(item)
                for item in (gm_workbook_summary.get("sequence_labels") or [])
                if str(item or "")
            ],
        },
        "measured_response_package": {
            "present": measured_response_ready,
            "expected_patterns": [
                str(item)
                for item in (measured_status.get("expected_patterns") or [])
                if str(item or "")
            ],
            "matched_files": [
                str(item)
                for item in (measured_status.get("matched_files") or [])
                if str(item or "")
            ],
            "landing_manifest_summary_line": str(measured_landing_manifest.get("summary_line", "") or ""),
            "landing_manifest_matched_file_count": int(landing_summary.get("matched_file_count", 0) or 0),
            "landing_manifest_present": landing_manifest_present,
            "landing_manifest_contract_pass": landing_manifest_contract_pass,
        },
        "measured_response_landing_manifest": {
            "present": landing_manifest_present,
            "contract_pass": landing_manifest_contract_pass,
            "landing_state": str(measured_landing_manifest.get("landing_state", "") or ""),
            "reason_code": str(measured_landing_manifest.get("reason_code", "") or ""),
            "summary_line": str(measured_landing_manifest.get("summary_line", "") or ""),
            "matched_file_count": int(landing_summary.get("matched_file_count", 0) or 0),
            "csv_file_count": int(landing_summary.get("csv_file_count", 0) or 0),
        },
        "expected_groups": expected_groups,
        "proposed_case_ids": proposed_case_ids,
        "next_actions": [
            (
                "Place measured response bundle under the blind-prediction landing root and rerun source-manifest + landing-status scripts."
                if not measured_response_ready
                else "Measured response is present; proceed to benchmark-case normalization."
            ),
            "Normalize the public input family into blind-prediction benchmark_case scaffolds.",
            "Build compare_report and viewer_entry artifacts once measured response is available.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-report", default=str(DEFAULT_BUNDLE_REPORT))
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--measured-status", default=str(DEFAULT_MEASURED_STATUS))
    parser.add_argument("--measured-landing-manifest", default=str(DEFAULT_MEASURED_LANDING_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_contract(
        _load_json(Path(args.bundle_report)),
        _load_json(Path(args.source_manifest)),
        _load_json(Path(args.measured_status)),
        _load_json(Path(args.measured_landing_manifest)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER blind input contract: {out_path}")


if __name__ == "__main__":
    main()
