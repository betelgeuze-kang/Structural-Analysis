#!/usr/bin/env python3
"""Create a pre-benchmark scaffold that bridges public input readiness to future compare artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT_CONTRACT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json"
)
DEFAULT_MEASURED_STATUS = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_prebenchmark_scaffold.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_scaffold(input_contract: dict[str, Any], measured_status: dict[str, Any]) -> dict[str, Any]:
    readiness = input_contract.get("readiness") if isinstance(input_contract.get("readiness"), dict) else {}
    excitation_package = (
        input_contract.get("excitation_package")
        if isinstance(input_contract.get("excitation_package"), dict)
        else {}
    )
    gm_case_labels = [str(item) for item in (excitation_package.get("gm_case_labels") or []) if str(item or "")]
    measured_ready = bool(measured_status.get("measured_response_present", False))
    candidate_cases = []
    for index, label in enumerate(gm_case_labels, start=1):
        case_kind = "random_noise" if label.lower() == "random noise" else "ground_motion"
        normalized_label = label.lower().replace(" ", "_")
        case_id = f"{input_contract.get('seed_id', 'edefense_peer_blind_prediction_seed_01')}::{normalized_label}"
        candidate_cases.append(
            {
                "case_id": case_id,
                "excitation_label": label,
                "excitation_kind": case_kind,
                "priority": index,
                "benchmark_case_status": "ready" if measured_ready else "pending_measured_response",
                "compare_report_status": "ready" if measured_ready else "pending_measured_response",
                "viewer_entry_status": "ready" if measured_ready else "pending_measured_response",
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_family": str(input_contract.get("source_family", "") or "edefense_peer_blind_prediction"),
        "seed_id": str(input_contract.get("seed_id", "") or "edefense_peer_blind_prediction_seed_01"),
        "benchmark_track": str(input_contract.get("benchmark_track", "") or "blind_prediction_dynamic_holdout"),
        "input_contract": str(DEFAULT_INPUT_CONTRACT),
        "measured_response_status": str(DEFAULT_MEASURED_STATUS),
        "contract_pass": bool(input_contract.get("contract_pass", False)),
        "summary_line": (
            f"PEER blind prebenchmark scaffold: {'READY' if readiness.get('benchmark_case_ready') else 'PENDING'} | "
            f"cases={len(candidate_cases)} | measured_response={'ready' if measured_ready else 'pending'}"
        ),
        "readiness": {
            "input_contract_ready": bool(readiness.get("public_input_ready", False)),
            "measured_response_ready": measured_ready,
            "benchmark_case_ready": bool(readiness.get("benchmark_case_ready", False)),
            "compare_report_ready": bool(readiness.get("compare_report_ready", False)),
            "viewer_entry_ready": bool(readiness.get("viewer_entry_ready", False)),
        },
        "pending_boundary": "" if measured_ready else "measured_response_missing",
        "pending_reason": (
            "Measured response bundle still needs manual landing before benchmark-case normalization can close."
            if not measured_ready
            else "All contract groups are present."
        ),
        "candidate_cases": candidate_cases,
        "expected_outputs": {
            "benchmark_cases_out": "implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json",
            "compare_report_out": "implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json",
            "viewer_entry_out": "implementation/phase1/release/visualization/entries/peer_blind_prediction_family.html",
        },
        "next_actions": [
            (
                "Land measured response bundle and rerun source-manifest/status/template scripts."
                if not measured_ready
                else "Proceed to benchmark-case normalization."
            ),
            "Map each GM / Random Noise label to a benchmark_case row.",
            "Generate compare_report and viewer_entry once response channels are available.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-contract", default=str(DEFAULT_INPUT_CONTRACT))
    parser.add_argument("--measured-status", default=str(DEFAULT_MEASURED_STATUS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_scaffold(_load_json(Path(args.input_contract)), _load_json(Path(args.measured_status)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER blind prebenchmark scaffold: {out_path}")


if __name__ == "__main__":
    main()
