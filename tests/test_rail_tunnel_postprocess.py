from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from rail_tunnel_postprocess import build_benchmark_payload, build_postprocess_report


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT_DIR / "implementation" / "phase1" / "rail_tunnel_postprocess.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_postprocess_report_summarizes_lining_and_serviceability() -> None:
    case_payload = {
        "case_id": "unit_case",
        "metadata": {
            "source_mode": "unit_fixture",
            "nominal_clearance_mm": 105.0,
        },
        "track_samples": [
            {"location_id": "CH000", "chainage_m": 0.0, "rail_settlement_mm": -1.0, "tunnel_crown_settlement_mm": -0.5},
            {"location_id": "CH010", "chainage_m": 10.0, "rail_settlement_mm": -3.0, "tunnel_crown_settlement_mm": -1.0},
            {"location_id": "CH020", "chainage_m": 20.0, "rail_settlement_mm": -2.0, "tunnel_crown_settlement_mm": -0.7, "clearance_mm": 98.0},
        ],
        "lining_samples": [
            {
                "ring_id": "R-A",
                "position_deg": 0.0,
                "moment_kNm": 220.0,
                "moment_capacity_kNm": 400.0,
                "axial_force_kN": 820.0,
                "axial_capacity_kN": 1600.0,
                "shear_kN": 42.0,
                "shear_capacity_kN": 100.0,
                "longitudinal_strain": 0.0010,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-A",
                "position_deg": 180.0,
                "moment_kNm": 260.0,
                "moment_capacity_kNm": 400.0,
                "axial_force_kN": 910.0,
                "axial_capacity_kN": 1600.0,
                "shear_kN": 48.0,
                "shear_capacity_kN": 100.0,
                "longitudinal_strain": 0.0012,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-B",
                "position_deg": 90.0,
                "moment_kNm": 180.0,
                "moment_capacity_kNm": 450.0,
                "utilization": 0.88,
            },
        ],
        "vibration_samples": [
            {"location_id": "V1", "chainage_m": 10.0, "freq_hz": 16.0, "velocity_mm_s": 0.19},
            {"location_id": "V2", "chainage_m": 20.0, "freq_hz": 31.5, "velocity_mm_s": 0.22},
        ],
    }
    thresholds = {
        "max_abs_settlement_mm": 8.0,
        "max_diff_settlement_mm": 3.0,
        "min_clearance_mm": 95.0,
        "max_lining_utilization": 1.0,
        "max_vibration_velocity_mm_s": 0.25,
        "nominal_clearance_mm": 105.0,
        "lining_moment_capacity_kNm": 650.0,
        "lining_strain_capacity": 0.0025,
    }

    report = build_postprocess_report(case_payload, thresholds=thresholds)
    benchmark = build_benchmark_payload(report)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summaries"]["settlement"]["max_abs_rail_settlement_mm"] == 3.0
    assert report["summaries"]["settlement"]["max_diff_settlement_mm"] == 2.0
    assert report["summaries"]["clearance"]["min_clearance_mm"] == 98.0
    assert report["summaries"]["utilization"]["governing_ring_id"] == "R-B"
    assert report["summaries"]["utilization"]["max_lining_utilization"] == 0.88
    assert report["summaries"]["maintenance"]["priority"] == "inspect_soon"
    assert "lining_joint_detail_inspection" in report["summaries"]["maintenance"]["recommended_actions"]
    assert "clearance_recheck_before_speed_change" in report["summaries"]["maintenance"]["recommended_actions"]
    assert report["benchmark_overview"]["governing_metric"] == "min_clearance_mm"
    assert benchmark["contract_pass"] is True
    assert len(benchmark["benchmark_rows"]) == 5


def test_cli_writes_report_and_benchmark_from_combined_input(tmp_path: Path) -> None:
    input_path = tmp_path / "rail_tunnel_input.json"
    report_path = tmp_path / "rail_tunnel_postprocess_report.json"
    benchmark_path = tmp_path / "rail_tunnel_postprocess_benchmark.json"
    _write_json(
        input_path,
        {
            "case_id": "cli_case",
            "metadata": {
                "source_mode": "combined_input_json",
                "nominal_clearance_mm": 112.0,
            },
            "track_samples": [
                {"chainage_m": 0.0, "rail_settlement_mm": -0.8, "tunnel_crown_settlement_mm": -0.4},
                {"chainage_m": 12.0, "rail_settlement_mm": -2.8, "tunnel_crown_settlement_mm": -1.2, "clearance_mm": 104.5},
                {"chainage_m": 24.0, "rail_settlement_mm": -1.1, "tunnel_crown_settlement_mm": -0.6},
            ],
            "lining_samples": [
                {
                    "ring_id": "R-201",
                    "moment_kNm": 240.0,
                    "moment_capacity_kNm": 520.0,
                    "axial_force_kN": 880.0,
                    "axial_capacity_kN": 1600.0,
                    "shear_kN": 58.0,
                    "shear_capacity_kN": 130.0,
                    "longitudinal_strain": 0.0011,
                    "strain_capacity": 0.0025,
                },
                {
                    "ring_id": "R-202",
                    "moment_kNm": 210.0,
                    "moment_capacity_kNm": 520.0,
                    "utilization_ratio": 0.79,
                },
            ],
            "vibration_samples": [
                {"chainage_m": 12.0, "freq_hz": 16.0, "velocity_mm_s": 0.15},
                {"chainage_m": 24.0, "freq_hz": 31.5, "velocity_mm_s": 0.18},
            ],
            "benchmarks": {
                "max_abs_settlement_mm": 8.0,
                "max_diff_settlement_mm": 3.0,
                "min_clearance_mm": 95.0,
                "max_lining_utilization": 1.0,
                "max_vibration_velocity_mm_s": 0.25,
            },
        },
    )

    proc = _run_cli(
        [
            "--input",
            str(input_path),
            "--out",
            str(report_path),
            "--benchmark-out",
            str(benchmark_path),
        ]
    )

    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_path.read_text(encoding="utf-8"))
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["benchmark_pass"] is True
    assert report["summaries"]["lining_response"]["ring_count"] == 2
    assert report["summaries"]["clearance"]["min_clearance_mm"] == 104.5
    assert benchmark["contract_pass"] is True
    assert benchmark["reason_code"] == "PASS"
    assert any(row["metric"] == "max_vibration_velocity_mm_s" for row in benchmark["benchmark_rows"])


def test_cli_fails_benchmark_when_component_reports_exceed_limits(tmp_path: Path) -> None:
    track_report = tmp_path / "track_lf_solver_report.json"
    tunnel_report = tmp_path / "tunnel_seismic_longitudinal_report.json"
    segment_report = tmp_path / "tunnel_segment_joint_report.json"
    vibration_report = tmp_path / "vibration_compliance_report.json"
    report_path = tmp_path / "rail_tunnel_postprocess_report.json"
    benchmark_path = tmp_path / "rail_tunnel_postprocess_benchmark.json"

    _write_json(
        track_report,
        {
            "contract_pass": True,
            "inputs": {"length_m": 24.0},
            "benchmarks": {"timoshenko": {"w_mid_m": 0.024}},
        },
    )
    _write_json(
        tunnel_report,
        {
            "contract_pass": True,
            "metrics": {
                "max_disp_m": 0.012,
                "max_longitudinal_strain": 0.0032,
            },
        },
    )
    _write_json(
        segment_report,
        {
            "contract_pass": True,
            "metrics": {
                "peak_moment_n_m": 820000.0,
                "post_peak_max_n_m": 610000.0,
            },
        },
    )
    _write_json(
        vibration_report,
        {
            "contract_pass": True,
            "curve_head": [
                {"freq_hz": 16.0, "distance_m": 0.0, "velocity_mm_s": 0.33},
                {"freq_hz": 31.5, "distance_m": 12.0, "velocity_mm_s": 0.28},
            ],
        },
    )

    proc = _run_cli(
        [
            "--track-report",
            str(track_report),
            "--tunnel-seismic-report",
            str(tunnel_report),
            "--segment-report",
            str(segment_report),
            "--vibration-report",
            str(vibration_report),
            "--out",
            str(report_path),
            "--benchmark-out",
            str(benchmark_path),
        ]
    )

    assert proc.returncode != 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))

    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_BENCHMARK_FAIL"
    assert report["summaries"]["settlement"]["max_abs_rail_settlement_mm"] == 24.0
    assert report["summaries"]["clearance"]["min_clearance_mm"] == 74.0
    assert report["summaries"]["maintenance"]["priority"] == "urgent"
    assert any(row["metric"] == "max_lining_utilization" and row["pass"] is False for row in report["benchmark_rows"])
    assert benchmark["contract_pass"] is False
    assert benchmark["reason_code"] == "ERR_BENCHMARK_FAIL"
