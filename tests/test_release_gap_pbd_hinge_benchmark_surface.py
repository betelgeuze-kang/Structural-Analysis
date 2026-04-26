from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_release_gap_report_surfaces_pbd_hinge_benchmark_metrics(tmp_path: Path) -> None:
    compare_payload = _load_json(
        Path("implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json")
    )
    landing_payload = _load_json(
        Path(
            "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
        )
    )
    paths = {
        "pbd": tmp_path / "pbd_review_package_report.json",
        "pbd_hinge": tmp_path / "pbd_hinge_refresh_report.json",
        "panel": tmp_path / "panel_zone_clash_report.json",
        "foundation": tmp_path / "foundation_optimization_report.json",
        "wind": tmp_path / "wind_raw_mapping_report.json",
        "midas": tmp_path / "midas_mgt_conversion_report.json",
        "committee": tmp_path / "committee_summary.json",
        "out_json": tmp_path / "release_gap_report.json",
        "out_md": tmp_path / "release_gap_report.md",
    }
    _write_json(paths["pbd"], {"contract_pass": True, "metrics": {"response_storage": "npz", "case_metrics_npz_case_count": 5}})
    _write_json(
        paths["pbd_hinge"],
        {
            "contract_pass": True,
            "reason": "dynamic hinge-refresh evidence is attached",
            "summary": {
                "hinge_state_mode": "computed_member_local_hinge_refresh",
                "hinge_refresh_artifact_present": True,
                "hinge_refresh_artifact_kind": "hinge_refresh_source_json",
                "hinge_refresh_source_mode": "rebar_sensitive_member_local_refresh",
                "hinge_refresh_overlap_member_count": 4,
                "hinge_refresh_rebar_sensitive_member_count": 2,
                "hinge_benchmark_gate_pass": True,
                "hinge_benchmark_fixture_regression_pass": True,
                "hinge_benchmark_alignment_pass": True,
                "hinge_benchmark_asset_count": 5,
                "hinge_benchmark_train_count": 2,
                "hinge_benchmark_val_count": 2,
                "hinge_benchmark_holdout_count": 1,
                "hinge_benchmark_rebar_sensitive_count": 1,
                "hinge_benchmark_confinement_sensitive_count": 1,
                "hinge_benchmark_fixture_count": 5,
                "hinge_benchmark_fixture_min_point_count": 449,
                "hinge_benchmark_fixture_min_peak_drift_ratio": 0.03662513089005235,
                "hinge_benchmark_alignment_refresh_column_row_count": 5,
                "hinge_benchmark_alignment_rebar_sensitive_column_count": 5,
                "hinge_benchmark_alignment_benchmark_rebar_ratio_min": 0.0127,
                "hinge_benchmark_alignment_benchmark_rebar_ratio_max": 0.0603,
                "hinge_benchmark_alignment_refresh_rebar_ratio_min": 0.064,
                "hinge_benchmark_alignment_refresh_rebar_ratio_max": 0.074,
            },
        },
    )
    _write_json(paths["panel"], {"contract_pass": False, "summary": {}, "reason": "panel open"})
    _write_json(paths["foundation"], {"contract_pass": True, "summary": {}, "reason": "foundation closed"})
    _write_json(paths["wind"], {"contract_pass": True, "summary": {}, "reason": "wind closed"})
    _write_json(paths["midas"], {"contract_pass": True})
    _write_json(paths["committee"], {"metrics": {}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_release_gap_report.py",
            "--pbd-package",
            str(paths["pbd"]),
            "--pbd-hinge-refresh-report",
            str(paths["pbd_hinge"]),
            "--panel-zone-clash-report",
            str(paths["panel"]),
            "--foundation-optimization-report",
            str(paths["foundation"]),
            "--wind-raw-mapping-report",
            str(paths["wind"]),
            "--midas-conversion",
            str(paths["midas"]),
            "--committee-summary",
            str(paths["committee"]),
            "--out-json",
            str(paths["out_json"]),
            "--out-md",
            str(paths["out_md"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = _load_json(paths["out_json"])
    summary = payload["summary"]
    assert summary["pbd_hinge_benchmark_gate_pass"] is True
    assert summary["pbd_hinge_benchmark_fixture_regression_pass"] is True
    assert summary["pbd_hinge_benchmark_alignment_pass"] is True
    assert summary["pbd_hinge_benchmark_asset_count"] == 5
    assert summary["pbd_hinge_benchmark_train_count"] == 2
    assert summary["pbd_hinge_benchmark_val_count"] == 2
    assert summary["pbd_hinge_benchmark_holdout_count"] == 1
    assert summary["pbd_hinge_benchmark_rebar_sensitive_count"] == 1
    assert summary["pbd_hinge_benchmark_confinement_sensitive_count"] == 1
    assert summary["pbd_hinge_benchmark_fixture_count"] == 5
    assert summary["pbd_hinge_benchmark_fixture_min_point_count"] == 449
    assert summary["pbd_hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert summary["pbd_hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert summary["peer_blind_prediction_compare_summary_line"] == compare_payload["summary_line"]
    assert summary["peer_blind_prediction_compare_build_case_count"] == 10
    assert summary["peer_blind_prediction_compare_entry_label"] == compare_payload["results_explorer"]["entry_label"]
    assert summary["peer_blind_prediction_compare_source_family"] == compare_payload["results_explorer"]["source_family"]
    assert (
        summary["peer_blind_prediction_measured_response_landing_summary_line"]
        == landing_payload["summary_line"]
    )
    assert summary["peer_blind_prediction_measured_response_landing_state"] == "pending"
    assert summary["peer_blind_prediction_measured_response_landing_csv_file_count"] == 0
    assert summary["peer_blind_prediction_measured_response_landing_sensor_candidate_count"] == 0
    pbd_row = next(row for row in payload["advanced_holdouts"] if row["id"] == "pbd_dynamic_hinge_refresh")
    assert "benchmark_assets=5" in pbd_row["evidence"]
    assert "benchmark_gate_pass=True" in pbd_row["evidence"]
    assert "benchmark_fixture_regression_pass=True" in pbd_row["evidence"]
    assert "benchmark_alignment_pass=True" in pbd_row["evidence"]
    assert "peer_blind_compare_cases=10" in pbd_row["evidence"]
    assert "peer_blind_compare_build_cases=10" in pbd_row["evidence"]
    assert "peer_blind_landing_state=pending" in pbd_row["evidence"]
    assert "peer_blind_landing_matched_files=0" in pbd_row["evidence"]
