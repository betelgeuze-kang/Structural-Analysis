#!/usr/bin/env python3
"""Build blind-prediction benchmark-case scaffolds from the PEER/E-Defense public input family."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT_CONTRACT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json"
)
DEFAULT_MEASURED_NORMALIZED = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json"
)
DEFAULT_SCAFFOLD = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_prebenchmark_scaffold.json"
)
DEFAULT_CASES_OUT = Path("implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json")
DEFAULT_REPORT_OUT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_case_build_report.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_cases(
    input_contract: dict[str, Any],
    measured_normalized: dict[str, Any],
    scaffold: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    readiness = input_contract.get("readiness") if isinstance(input_contract.get("readiness"), dict) else {}
    candidate_cases = scaffold.get("candidate_cases") if isinstance(scaffold.get("candidate_cases"), list) else []
    measured_summary = measured_normalized.get("summary") if isinstance(measured_normalized.get("summary"), dict) else {}
    acceleration_summary = (
        measured_normalized.get("acceleration_summary")
        if isinstance(measured_normalized.get("acceleration_summary"), dict)
        else {}
    )
    measured_ready = bool(measured_normalized.get("contract_pass", False))
    source_family = str(input_contract.get("source_family", "") or "edefense_peer_blind_prediction")
    cases: list[dict[str, Any]] = []
    public_cases: list[dict[str, Any]] = []
    for index, row in enumerate(candidate_cases, start=1):
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id", "") or f"{source_family}::{index:02d}")
        excitation_label = str(row.get("excitation_label", "") or f"GM{index}")
        hazard_type = "seismic"
        topology_type = "blind_prediction_frame"
        element_mix = "frame_wall_mix"
        blind_metrics = {
            "input_channel_count": int(acceleration_summary.get("channel_count", 0) or 0),
            "measured_channel_count": int(measured_summary.get("acceleration_channel_count", 0) or 0),
            "drift_channel_count": int(measured_summary.get("drift_channel_count", 0) or 0),
            "sensor_row_count": int(measured_summary.get("sensor_row_count", 0) or 0),
        }
        case_payload = {
            "case_id": case_id,
            "source_family": source_family,
            "element_mix": element_mix,
            "topology_type": topology_type,
            "hazard_type": hazard_type,
            "split": "holdout",
            "source_member": str(input_contract.get("bundle_report", "") or ""),
            "benchmark_case_status": "ready" if measured_ready else "pending_measured_response",
            "compare_ready": measured_ready,
            "viewer_entry_ready": measured_ready,
            "blind_prediction_targets": {
                "excitation_label": excitation_label,
                "excitation_kind": str(row.get("excitation_kind", "") or "ground_motion"),
                "measured_response_required": True,
                "measured_response_present": measured_ready,
                "input_contract_summary": str(input_contract.get("summary_line", "") or ""),
            },
            "blind_prediction_metrics": blind_metrics,
        }
        public_cases.append(
            {
                "case_id": case_id,
                "source_family": source_family,
                "element_mix": element_mix,
                "topology_type": topology_type,
                "hazard_type": hazard_type,
                "benchmark_case_status": case_payload["benchmark_case_status"],
                "excitation_label": excitation_label,
                "source_member": case_payload["source_member"],
            }
        )
        cases.append(case_payload)

    cases_payload = {
        "schema_version": "1.0",
        "run_id": "phase1-peer-blind-prediction-benchmark-cases",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "source_family": source_family,
            "input_contract": str(DEFAULT_INPUT_CONTRACT),
            "measured_normalized": str(DEFAULT_MEASURED_NORMALIZED),
            "prebenchmark_scaffold": str(DEFAULT_SCAFFOLD),
        },
        "source_family_summary": {
            "source_families": [source_family],
            "distinct_source_family_count": 1,
            "element_mixes": ["frame_wall_mix"],
            "shell_beam_mix_case_count": 0,
            "benchmark_case_status": "ready" if measured_ready else "pending_measured_response",
        },
        "split_counts": {"holdout": len(cases)},
        "public_benchmark_cases": public_cases,
        "cases": cases,
    }
    report_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS" if measured_ready else "PASS_PENDING_MEASURED_RESPONSE",
        "reason": (
            "Blind-prediction benchmark cases are built and compare-ready."
            if measured_ready
            else "Blind-prediction benchmark cases are scaffolded; measured response still gates compare readiness."
        ),
        "summary_line": (
            f"PEER blind benchmark-case build: {'READY' if measured_ready else 'PENDING'} | "
            f"cases={len(cases)} | measured_response={'ready' if measured_ready else 'pending'} | "
            f"channels={int(measured_summary.get('acceleration_channel_count', 0) or 0)}"
        ),
        "summary": {
            "case_count": len(cases),
            "measured_response_ready": measured_ready,
            "acceleration_channel_count": int(measured_summary.get("acceleration_channel_count", 0) or 0),
            "drift_channel_count": int(measured_summary.get("drift_channel_count", 0) or 0),
        },
        "results_explorer": {
            "entry_kind": "blind_prediction_compare_family",
            "entry_label": "PEER Blind Prediction Compare Family",
            "source_family": source_family,
            "summary_label": (
                "compare-ready blind prediction family"
                if measured_ready
                else "input-ready blind prediction family / measured response pending"
            ),
        },
        "outputs": {
            "benchmark_cases_out": str(DEFAULT_CASES_OUT),
        },
    }
    return cases_payload, report_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-contract", default=str(DEFAULT_INPUT_CONTRACT))
    parser.add_argument("--measured-normalized", default=str(DEFAULT_MEASURED_NORMALIZED))
    parser.add_argument("--scaffold", default=str(DEFAULT_SCAFFOLD))
    parser.add_argument("--cases-out", default=str(DEFAULT_CASES_OUT))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT_OUT))
    args = parser.parse_args()

    cases_payload, report_payload = build_cases(
        _load_json(Path(args.input_contract)),
        _load_json(Path(args.measured_normalized)),
        _load_json(Path(args.scaffold)),
    )
    cases_out = Path(args.cases_out)
    cases_out.parent.mkdir(parents=True, exist_ok=True)
    cases_out.write_text(json.dumps(cases_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER blind benchmark cases: {cases_out}")
    print(f"Wrote PEER blind benchmark-case build report: {report_out}")


if __name__ == "__main__":
    main()
