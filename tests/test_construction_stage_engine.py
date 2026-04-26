from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from implementation.phase1.construction_stage_engine import (
    generate_construction_stage_report,
    validate_construction_stage_payload,
)


def _sample_payload() -> dict:
    return {
        "elements": [
            {"id": "FOUND", "kind": "foundation", "stiffness": 120.0, "capacity": 2.0, "self_weight": 12.0},
            {"id": "COL1", "kind": "column", "stiffness": 100.0, "capacity": 1.5, "self_weight": 10.0},
            {"id": "BEAM1", "kind": "beam", "stiffness": 80.0, "capacity": 1.0, "self_weight": 8.0},
        ],
        "loads": [
            {"id": "DL_COL", "target": "COL1", "magnitude": 30.0},
            {"id": "DL_BEAM", "target": "BEAM1", "magnitude": 20.0},
        ],
        "stages": [
            {
                "name": "foundation_and_core",
                "duration_days": 10.0,
                "load_scale": 0.5,
                "activate_elements": ["FOUND", "COL1"],
                "activate_loads": ["DL_COL"],
            },
            {
                "name": "framing",
                "duration_days": 20.0,
                "load_scale": 1.0,
                "activate_elements": ["BEAM1"],
                "activate_loads": ["DL_BEAM"],
            },
            {
                "name": "strip_beam",
                "duration_days": 5.0,
                "load_scale": 1.0,
                "deactivate_elements": ["BEAM1"],
            },
        ],
        "max_utilization_ratio": 1.0,
    }


def test_generate_construction_stage_report_tracks_history_and_auto_deactivation() -> None:
    report = generate_construction_stage_report(_sample_payload())

    history = report["history_snapshots"]
    assert report["contract_pass"] is True
    assert report["checks"]["cumulative_total_monotonic_pass"] is True
    assert report["summary"]["history_snapshot_count"] == 3
    assert report["summary"]["auto_deactivated_load_count_total"] == 1
    assert report["summary"]["validation_warning_count"] == 1
    assert report["summary_line"].startswith("Construction stage engine: PASS")

    assert history[0]["active_element_ids"] == ["FOUND", "COL1"]
    assert history[1]["active_element_ids"] == ["FOUND", "COL1", "BEAM1"]
    assert history[2]["operations"]["auto_deactivated_loads"] == ["DL_BEAM"]
    assert history[2]["active_element_ids"] == ["FOUND", "COL1"]
    assert history[2]["active_load_ids"] == ["DL_COL"]

    assert history[0]["cumulative_demand_by_element"]["COL1"] == pytest.approx(0.3333333333)
    assert history[1]["element_stage_total_demand"]["BEAM1"] == pytest.approx(0.6416666667)
    assert history[2]["cumulative_total_demand"] == pytest.approx(2.4833333333)
    assert report["summary"]["max_utilization_ratio"] == pytest.approx(0.9777777778)
    assert any("utilization=pass" in item for item in report["reasons"])
    assert any("auto-deactivates loads DL_BEAM" in item for item in report["validation"]["warnings"])


def test_validate_construction_stage_payload_rejects_load_activation_before_target_is_active() -> None:
    payload = _sample_payload()
    payload["stages"] = [{"name": "bad_start", "activate_loads": ["DL_BEAM"]}]

    validation = validate_construction_stage_payload(payload)

    assert validation["valid"] is False
    assert validation["stage_count"] == 1
    assert validation["errors"] == [
        "stage 1 'bad_start' activates loads before their target elements are active: DL_BEAM"
    ]


def test_construction_stage_engine_cli_writes_report_json(tmp_path: Path) -> None:
    payload_path = tmp_path / "construction_stage_input.json"
    out_path = tmp_path / "construction_stage_report.json"
    payload_path.write_text(json.dumps(_sample_payload()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/construction_stage_engine.py",
            "--input",
            str(payload_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Wrote construction stage engine report" in proc.stdout

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["stage_count"] == 3
    assert report["summary"]["final_active_element_count"] == 2
    assert report["summary"]["final_active_load_count"] == 1
    assert report["final_snapshot"]["active_element_ids"] == ["FOUND", "COL1"]


def test_construction_stage_engine_cli_reports_invalid_sequence(tmp_path: Path) -> None:
    payload = _sample_payload()
    payload["stages"] = [{"name": "bad_start", "activate_loads": ["DL_BEAM"]}]
    payload_path = tmp_path / "construction_stage_bad_input.json"
    out_path = tmp_path / "construction_stage_bad_report.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/construction_stage_engine.py",
            "--input",
            str(payload_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_INVALID_INPUT"
    assert "activates loads before their target elements are active" in report["validation"]["errors"][0]
