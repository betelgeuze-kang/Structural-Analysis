from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from wind_workflow import build_story_wind_profile, generate_wind_load_cases, run_wind_workflow


def _payload() -> dict:
    return {
        "site": {
            "basic_wind_speed_mps": 45.0,
            "exposure": "C",
            "topographic_factor": 1.0,
            "directionality_factor": 0.85,
            "importance_factor": 1.0,
            "gust_factor": 0.85,
        },
        "building": {
            "name": "River Tower",
            "story_count": 6,
            "plan_dim_x_m": 32.0,
            "plan_dim_y_m": 26.0,
            "story_heights_m": [4.0, 4.0, 4.0, 4.0, 4.0, 4.2],
            "story_masses_t": [1100.0, 1080.0, 1060.0, 1040.0, 1020.0, 1000.0],
            "story_stiffness_kNpm": [900000.0, 840000.0, 780000.0, 720000.0, 660000.0, 600000.0],
            "fundamental_period_s": 3.6,
            "damping_ratio": 0.025,
            "mode_shape_exponent": 1.1,
            "force_coefficient": 1.30,
            "across_wind_factor": 1.25,
            "strength_scale": 1.0,
            "service_scale": 0.70,
        },
        "criteria": {
            "strength_drift_limit_ratio": 0.020,
            "service_drift_limit_ratio": 0.010,
            "peak_acceleration_limit_mg": 24.0,
            "rms_acceleration_limit_mg": 10.0,
        },
    }


def test_build_story_wind_profile_and_generate_load_cases() -> None:
    payload = _payload()

    story_profile = build_story_wind_profile(payload)
    assert len(story_profile) == 6
    assert story_profile[0]["qz_kpa"] < story_profile[-1]["qz_kpa"]
    assert story_profile[-1]["service_force_y_kN"] > story_profile[-1]["service_force_x_kN"]

    load_cases = generate_wind_load_cases(payload, story_profile)
    assert len(load_cases) == 8

    by_case = {case["case_id"]: case for case in load_cases}
    assert by_case["W_STR_X_POS"]["direction"] == "X"
    assert by_case["W_SVC_Y_NEG"]["sign"] == -1
    assert by_case["W_STR_Y_POS"]["base_shear_kN"] > by_case["W_STR_X_POS"]["base_shear_kN"]

    report = run_wind_workflow(payload)
    assert report["contract_pass"] is True
    assert report["checks"]["serviceability_pass"] is True
    assert report["serviceability"]["status"] == "PASS"
    assert report["summary"]["story_count"] == 6
    assert report["summary"]["occupant_comfort_class"] in {"calm", "acceptable", "perceptible", "attention"}
    assert report["occupant_comfort"]["governing_case_id"].startswith("W_SVC_")
    assert len(report["occupant_comfort"]["case_rows"]) == 4
    assert report["occupant_comfort"]["crosswind_bias_ratio"] > 1.0
    assert report["summary_line"].startswith("Wind workflow: PASS")
    assert report["drift_summary"]["service_max_story_drift_ratio"] == pytest.approx(
        by_case["W_SVC_Y_POS"]["max_story_drift_ratio"]
    )


def test_run_wind_workflow_reports_serviceability_check() -> None:
    payload = _payload()
    payload["criteria"]["peak_acceleration_limit_mg"] = 6.0
    payload["criteria"]["rms_acceleration_limit_mg"] = 3.0

    report = run_wind_workflow(payload)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "CHECK"
    assert report["checks"]["serviceability_pass"] is False
    assert report["checks"]["service_drift_within_limit"] is True
    assert report["checks"]["peak_acceleration_within_limit"] is False
    assert report["serviceability"]["status"] == "CHECK"
    assert report["serviceability"]["governing_metric"] in {"peak_acceleration_mg", "rms_acceleration_mg"}
    assert report["occupant_comfort"]["overall_class"] == "exceedance"
    assert report["summary"]["occupant_comfort_class"] == "exceedance"
    assert report["occupant_comfort"]["peak_reserve_mg"] < 0.0
    assert report["summary_line"].startswith("Wind workflow: CHECK")


def test_wind_workflow_cli_writes_report_json(tmp_path: Path) -> None:
    out_path = tmp_path / "wind_workflow_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/wind_workflow.py",
            "--name",
            "CLI Tower",
            "--basic-wind-speed-mps",
            "42.0",
            "--exposure",
            "B",
            "--story-count",
            "5",
            "--story-height-m",
            "3.8",
            "--plan-dim-x-m",
            "30.0",
            "--plan-dim-y-m",
            "24.0",
            "--story-mass-t",
            "900.0",
            "--stiffness-base-kNpm",
            "700000.0",
            "--stiffness-top-kNpm",
            "350000.0",
            "--fundamental-period-s",
            "3.2",
            "--damping-ratio",
            "0.025",
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Wrote wind workflow report" in proc.stdout

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["artifacts"]["report_json"] == str(out_path)
    assert report["inputs"]["site"]["exposure"] == "B"
    assert report["summary"]["story_count"] == 5
    assert len(report["story_profile"]) == 5
    assert report["load_cases"][0]["case_id"] == "W_STR_X_POS"
    assert report["inputs"]["building"]["story_stiffness_kNpm"][0] == pytest.approx(700000.0)
    assert report["inputs"]["building"]["story_stiffness_kNpm"][-1] == pytest.approx(350000.0)
    assert report["occupant_comfort"]["governing_case_id"].startswith("W_SVC_")
    assert len(report["occupant_comfort"]["case_rows"]) == 4
