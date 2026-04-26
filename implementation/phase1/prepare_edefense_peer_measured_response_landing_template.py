#!/usr/bin/env python3
"""Generate a landing template that explains how to place measured-response artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_MANIFEST = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json"
)
DEFAULT_INPUT_CONTRACT = Path(
    "implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_template.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_template(source_manifest: dict[str, Any], input_contract: dict[str, Any]) -> dict[str, Any]:
    expected_groups = (
        source_manifest.get("expected_groups")
        if isinstance(source_manifest.get("expected_groups"), dict)
        else {}
    )
    measured_group = (
        expected_groups.get("measured_response")
        if isinstance(expected_groups.get("measured_response"), dict)
        else {}
    )
    input_root = str(
        source_manifest.get("local_input_root", "")
        or input_contract.get("input_root", "")
        or "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01"
    )
    gm_case_labels = (
        input_contract.get("excitation_package", {}).get("gm_case_labels", [])
        if isinstance(input_contract.get("excitation_package"), dict)
        else []
    )
    preferred_bundle_layout = [
        {
            "path": "measured_response_acceleration.csv",
            "kind": "acceleration_history",
            "required_columns": ["time_s", "sensor_id", "accel_x_g", "accel_y_g", "accel_z_g"],
        },
        {
            "path": "measured_response_drift.csv",
            "kind": "story_drift_history",
            "required_columns": ["time_s", "story_label", "drift_ratio_x", "drift_ratio_y"],
        },
        {
            "path": "sensor_manifest.json",
            "kind": "sensor_layout_manifest",
            "required_columns": [],
        },
    ]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_family": str(source_manifest.get("source_family", "") or "edefense_peer_blind_prediction"),
        "seed_id": str(source_manifest.get("seed_id", "") or "edefense_peer_blind_prediction_seed_01"),
        "input_root": input_root,
        "contract_pass": True,
        "summary_line": (
            f"E-Defense/PEER measured-response template: READY | root={Path(input_root).name} | "
            f"expected_patterns={len(measured_group.get('patterns') or [])} | gm_cases={len(gm_case_labels)}"
        ),
        "accepted_file_patterns": [
            str(item)
            for item in (measured_group.get("patterns") or [])
            if str(item or "")
        ],
        "preferred_bundle_layout": preferred_bundle_layout,
        "channel_groups": [
            {
                "group_id": "acceleration",
                "required": True,
                "description": "At least one sensor acceleration history aligned to the blind-prediction excitation sequence.",
                "minimum_channels": 1,
                "example_headers": ["time_s", "sensor_id", "accel_x_g", "accel_y_g", "accel_z_g"],
            },
            {
                "group_id": "drift",
                "required": False,
                "description": "Story drift or interstory displacement ratios when available.",
                "minimum_channels": 1,
                "example_headers": ["time_s", "story_label", "drift_ratio_x", "drift_ratio_y"],
            },
            {
                "group_id": "displacement",
                "required": False,
                "description": "Absolute displacement channels for selected DOFs or roof points.",
                "minimum_channels": 1,
                "example_headers": ["time_s", "sensor_id", "disp_x_m", "disp_y_m", "disp_z_m"],
            },
            {
                "group_id": "metadata",
                "required": True,
                "description": "Sensor map or channel legend that ties measured channels back to geometry/story labels.",
                "minimum_channels": 1,
                "example_headers": ["sensor_id", "story_label", "component", "units"],
            },
        ],
        "gm_case_labels": [str(item) for item in gm_case_labels if str(item or "")],
        "csv_header_templates": {
            "acceleration_history": ["time_s", "sensor_id", "accel_x_g", "accel_y_g", "accel_z_g"],
            "story_drift_history": ["time_s", "story_label", "drift_ratio_x", "drift_ratio_y"],
            "sensor_manifest": ["sensor_id", "story_label", "component", "units"],
        },
        "next_actions": [
            f"Place measured-response files under {input_root}.",
            "Rerun prepare_edefense_peer_blind_prediction_source_manifest.py.",
            "Rerun prepare_edefense_peer_measured_response_landing_status.py.",
            "Rerun build_peer_blind_prediction_prebenchmark_scaffold.py.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--input-contract", default=str(DEFAULT_INPUT_CONTRACT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_template(_load_json(Path(args.source_manifest)), _load_json(Path(args.input_contract)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense/PEER measured-response landing template: {out_path}")


if __name__ == "__main__":
    main()
