#!/usr/bin/env python3
"""Emit a compare-readiness report for the PEER blind-prediction family."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_CASES = Path("implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json")
DEFAULT_BUILD_REPORT = Path("implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_case_build_report.json")
DEFAULT_MEASURED_NORMALIZED = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json"
)
DEFAULT_MEASURED_LANDING_MANIFEST = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
)
DEFAULT_OUT = Path("implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_report(
    cases_payload: dict[str, Any],
    build_report: dict[str, Any],
    measured_normalized: dict[str, Any],
    measured_landing_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    measured_landing_manifest = measured_landing_manifest if isinstance(measured_landing_manifest, dict) else {}
    landing_manifest_present = bool(measured_landing_manifest)
    landing_manifest_contract_pass = bool(measured_landing_manifest.get("contract_pass", False))
    cases = cases_payload.get("cases") if isinstance(cases_payload.get("cases"), list) else []
    summary = build_report.get("summary") if isinstance(build_report.get("summary"), dict) else {}
    measured_summary = measured_normalized.get("summary") if isinstance(measured_normalized.get("summary"), dict) else {}
    landing_summary = (
        measured_landing_manifest.get("summary")
        if isinstance(measured_landing_manifest.get("summary"), dict)
        else {}
    )
    compare_ready = bool(measured_normalized.get("contract_pass", False))
    source_family = str(build_report.get("results_explorer", {}).get("source_family", "") or "edefense_peer_blind_prediction")
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS" if compare_ready else "PASS_COMPARE_PENDING_MEASURED_RESPONSE",
        "reason": (
            "Blind-prediction compare inputs are ready."
            if compare_ready
            else "Blind-prediction compare lane is staged, but measured response still gates actual compare."
        ),
        "summary_line": (
            f"PEER blind compare lane: {'READY' if compare_ready else 'PENDING'} | "
            f"cases={len(cases)} | measured_response={'ready' if compare_ready else 'pending'} | "
            f"channels={int(measured_summary.get('acceleration_channel_count', 0) or 0)} | "
            f"landing_manifest={'recorded' if landing_manifest_present else 'missing'}"
        ),
        "summary": {
            "case_count": len(cases),
            "measured_response_ready": compare_ready,
            "measured_response_landing_manifest_ready": landing_manifest_contract_pass,
            "acceleration_channel_count": int(measured_summary.get("acceleration_channel_count", 0) or 0),
            "drift_channel_count": int(measured_summary.get("drift_channel_count", 0) or 0),
            "build_case_count": int(summary.get("case_count", len(cases)) or len(cases)),
            "landing_manifest_matched_file_count": int(landing_summary.get("matched_file_count", 0) or 0),
            "landing_manifest_contract_pass": landing_manifest_contract_pass,
        },
        "results_explorer": {
            "entry_kind": "blind_prediction_compare_family",
            "entry_label": "PEER Blind Prediction Compare Family",
            "source_family": source_family,
            "summary_label": (
                "compare-ready blind prediction family"
                if compare_ready
                else "blind prediction compare pending measured response"
            ),
        },
        "evidence": {
            "cases_path": str(DEFAULT_CASES),
            "build_report_path": str(DEFAULT_BUILD_REPORT),
            "measured_normalized_path": str(DEFAULT_MEASURED_NORMALIZED),
            "measured_landing_manifest_path": str(DEFAULT_MEASURED_LANDING_MANIFEST),
            "measured_landing_manifest_summary_line": str(measured_landing_manifest.get("summary_line", "") or ""),
            "measured_landing_manifest_contract_pass": landing_manifest_contract_pass,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--build-report", default=str(DEFAULT_BUILD_REPORT))
    parser.add_argument("--measured-normalized", default=str(DEFAULT_MEASURED_NORMALIZED))
    parser.add_argument("--measured-landing-manifest", default=str(DEFAULT_MEASURED_LANDING_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_report(
        _load_json(Path(args.cases)),
        _load_json(Path(args.build_report)),
        _load_json(Path(args.measured_normalized)),
        _load_json(Path(args.measured_landing_manifest)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER blind compare report: {out_path}")


if __name__ == "__main__":
    main()
