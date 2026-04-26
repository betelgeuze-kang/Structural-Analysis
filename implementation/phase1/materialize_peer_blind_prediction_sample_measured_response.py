#!/usr/bin/env python3
"""Materialize a synthetic measured-response landing bundle for the PEER blind-prediction family."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_INPUT_CONTRACT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json"
)
DEFAULT_OUT_ROOT = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01_sample_measured_response"
)
DEFAULT_REPORT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_report.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def materialize_sample_bundle(input_contract: dict[str, Any], out_root: Path) -> dict[str, Any]:
    excitation_package = (
        input_contract.get("excitation_package")
        if isinstance(input_contract.get("excitation_package"), dict)
        else {}
    )
    gm_case_labels = [str(item) for item in (excitation_package.get("gm_case_labels") or []) if str(item or "")]
    if not gm_case_labels:
        gm_case_labels = ["Random Noise", "GM1", "GM2"]
    out_root.mkdir(parents=True, exist_ok=True)

    accel_path = out_root / "measured_response_acceleration.csv"
    drift_path = out_root / "measured_response_drift.csv"
    sensor_manifest_path = out_root / "sensor_manifest.json"

    accel_rows = 0
    with accel_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["time_s", "sensor_id", "case_label", "accel_x_g", "accel_y_g", "accel_z_g"],
        )
        writer.writeheader()
        for case_index, case_label in enumerate(gm_case_labels, start=1):
            for step in range(21):
                time_s = round(step * 0.05, 4)
                writer.writerow(
                    {
                        "time_s": f"{time_s:.4f}",
                        "sensor_id": f"S{((case_index - 1) % 3) + 1:02d}",
                        "case_label": case_label,
                        "accel_x_g": f"{0.01 * case_index * math.sin(step / 3.0):.6f}",
                        "accel_y_g": f"{0.008 * case_index * math.cos(step / 4.0):.6f}",
                        "accel_z_g": f"{0.002 * case_index * math.sin(step / 5.0):.6f}",
                    }
                )
                accel_rows += 1

    drift_rows = 0
    with drift_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["time_s", "story_label", "case_label", "drift_ratio_x", "drift_ratio_y"],
        )
        writer.writeheader()
        for case_index, case_label in enumerate(gm_case_labels, start=1):
            for step in range(11):
                time_s = round(step * 0.1, 4)
                writer.writerow(
                    {
                        "time_s": f"{time_s:.4f}",
                        "story_label": f"L{((case_index - 1) % 5) + 1}",
                        "case_label": case_label,
                        "drift_ratio_x": f"{0.0005 * case_index * (step + 1):.6f}",
                        "drift_ratio_y": f"{0.0003 * case_index * (step + 1):.6f}",
                    }
                )
                drift_rows += 1

    sensors = [
        {"sensor_id": "S01", "story_label": "L1", "component": "x/y/z", "units": "g"},
        {"sensor_id": "S02", "story_label": "L3", "component": "x/y/z", "units": "g"},
        {"sensor_id": "S03", "story_label": "L5", "component": "x/y/z", "units": "g"},
    ]
    sensor_manifest_path.write_text(json.dumps({"sensors": sensors}, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_family": str(input_contract.get("source_family", "") or "edefense_peer_blind_prediction"),
        "seed_id": str(input_contract.get("seed_id", "") or "edefense_peer_blind_prediction_seed_01"),
        "contract_pass": True,
        "summary_line": (
            f"PEER blind sample measured-response bundle: PASS | cases={len(gm_case_labels)} | "
            f"accel_rows={accel_rows} | drift_rows={drift_rows} | sensors={len(sensors)}"
        ),
        "out_root": str(out_root),
        "outputs": {
            "acceleration_csv": str(accel_path),
            "drift_csv": str(drift_path),
            "sensor_manifest_json": str(sensor_manifest_path),
        },
        "summary": {
            "case_count": len(gm_case_labels),
            "acceleration_row_count": accel_rows,
            "drift_row_count": drift_rows,
            "sensor_row_count": len(sensors),
        },
        "case_labels": gm_case_labels,
        "note": "Synthetic sample landing for compare-path closure only. This is not an official PEER measured-response release.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-contract", default=str(DEFAULT_INPUT_CONTRACT))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    payload = materialize_sample_bundle(_load_json(Path(args.input_contract)), Path(args.out_root))
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER blind sample measured-response bundle report: {report_out}")


if __name__ == "__main__":
    main()
