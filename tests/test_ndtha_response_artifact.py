from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from implementation.phase1.run_nonlinear_ndtha_stress import (
    _build_ndtha_report_surfaces,
    _write_ndtha_response_npz,
)


def test_write_ndtha_response_npz(tmp_path: Path) -> None:
    out = tmp_path / "ndtha.response.npz"
    rows = [
        {
            "case_id": "CASE-A",
            "artifacts": {"response_npz_key_prefix": "CASE_A"},
            "response_artifact_data": {
                "time_s": [0.0, 0.1, 0.2],
                "top_displacement_m": [0.0, 0.01, 0.02],
                "top_velocity_mps": [0.0, 0.1, 0.1],
                "top_acceleration_mps2": [0.0, 0.0, 0.0],
                "ground_acceleration_g": [0.0, 0.2, -0.2],
                "drift_ratio_pct": [0.0, 0.2, 0.3],
                "base_shear_kN": [0.0, 10.0, 12.0],
                "core_drift_pct": [0.0, 0.1, 0.15],
                "core_shear_kN": [0.0, 5.0, 6.0],
                "step_converged": [True, True, False],
                "step_iterations": [3, 4, 8],
                "step_plastic_story_count": [0, 1, 2],
                "step_residual_inf": [1.0e-6, 2.0e-6, 5.0e-5],
                "story_drift_envelope_pct": [0.1, 0.3],
                "final_story_drift_pct": [0.05, 0.2],
            },
        }
    ]

    summary = _write_ndtha_response_npz(out, rows)
    assert out.exists()
    assert summary["case_count"] == 1
    assert summary["storage"] == "npz_external"

    payload = np.load(out)
    assert payload["case_keys"].tolist() == ["CASE_A"]
    assert payload["case_ids"].tolist() == ["CASE-A"]
    assert payload["CASE_A__top_displacement_m"].shape == (3,)
    assert payload["CASE_A__top_velocity_mps"].tolist() == [0.0, 0.1, 0.1]
    assert payload["CASE_A__ground_acceleration_g"].tolist() == [0.0, 0.2, -0.2]
    assert payload["CASE_A__step_iterations"].tolist() == [3, 4, 8]
    assert payload["CASE_A__step_converged"].tolist() == [True, True, False]


def test_build_ndtha_report_surfaces_rolls_up_solver_and_residual_fields() -> None:
    rows = [
        {
            "case_id": "CASE-A",
            "summary": {
                "residual_metric_source": "solver_raw",
                "residual_metric_fallback_used": False,
                "residual_top_displacement_m": 0.02,
                "residual_drift_ratio_pct": 0.25,
                "residual_pre_settle_top_displacement_m": 0.08,
                "residual_pre_settle_drift_ratio_pct": 0.7,
                "residual_settle_applied": True,
                "solver_control": {
                    "event_sequence_pass": True,
                    "event_count": 2,
                    "nonconverged_step_count": 0,
                    "cutback_recommended_step_count": 1,
                    "next_run_control": {"recommended_dt_scale_min": 0.75},
                },
            },
            "response": {
                "story_drift_envelope_pct": [0.1, 0.3],
                "final_story_drift_pct": [0.05, 0.2],
            },
            "artifacts": {
                "response_npz_key_prefix": "CASE_A",
                "response_full_step_count": 10,
                "response_inline_step_count": 4,
            },
        }
    ]
    surfaces = _build_ndtha_report_surfaces(
        case_rows=rows,
        checks={"solver_control_history_pass": True, "residual_metric_sanity_pass": True},
        response_npz_summary={"path": "tmp/report.response.npz", "case_count": 1, "array_count": 14, "storage": "npz_external"},
    )

    assert surfaces["summary_line"].startswith("Nonlinear NDTHA stress: PASS")
    assert "step_series=1/1" in surfaces["summary_line"]
    assert surfaces["solver_control"]["event_count_total"] == 2
    assert surfaces["solver_control"]["cutback_case_ids"] == ["CASE-A"]
    assert surfaces["response_npz"]["case_keys"] == ["CASE_A"]
    assert surfaces["response_npz"]["series_case_count"] == 1
    assert surfaces["response_npz"]["series_contract_pass"] is True
    assert surfaces["residual_metric"]["source_counts"] == {"solver_raw": 1}
    assert surfaces["residual_metric"]["settle_case_count"] == 1
    assert surfaces["residual_tail_metrics"]["story_drift_envelope_pct_max_abs"] == 0.3


def test_checked_in_ndtha_report_surfaces_include_response_npz_and_solver_control() -> None:
    report_path = Path("implementation/phase1/nonlinear_ndtha_stress_report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["summary_line"].startswith("Nonlinear NDTHA stress:")
    assert "step_series=3/3" in report["summary_line"]
    assert report["solver_control"]["history_pass"] is True
    assert report["residual_metric"]["sanity_pass"] is True
    assert report["response_npz"]["case_count"] == report["summary"]["response_npz_case_count"]
    assert len(report["response_npz"]["case_keys"]) == report["response_npz"]["case_count"]
    assert "series_case_count" in report["response_npz"]
    assert report["response_npz"]["series_case_count"] == report["response_npz"]["case_count"]
    assert report["response_npz"]["series_contract_pass"] is True
    npz_path = Path(str(report["response_npz"]["path"]))
    assert npz_path.exists()
    payload = np.load(npz_path)
    case_key = str(report["response_npz"]["case_keys"][0])
    assert payload[f"{case_key}__top_displacement_m"].shape[0] > 0
    assert payload[f"{case_key}__top_velocity_mps"].shape[0] == payload[f"{case_key}__top_displacement_m"].shape[0]
