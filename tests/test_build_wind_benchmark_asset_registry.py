from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_wind_benchmark_asset_registry_collects_manifests_and_probe(tmp_path: Path) -> None:
    wind_root = tmp_path / "wind"
    wind_root.mkdir(parents=True)
    manifest = wind_root / "sample.source_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_name": "TPU Sample",
                "source_url": "https://example.test/tpu",
                "real_source": True,
                "source_origin_class": "official_external_benchmark",
                "benchmark_seed_id": "tpu_hffb_interference_highrise_seed_01",
                "case_role": "neighbor_interference_highrise",
                "holdout_split": "holdout",
                "contract_pass": True,
                "reason_code": "PASS",
                "data_path": str(wind_root / "sample.csv"),
                "sha256": "abc",
                "csv_profile": {"row_count": 10, "signal_columns": ["signal_01", "signal_02"]},
            }
        ),
        encoding="utf-8",
    )
    probe_report = tmp_path / "probe.json"
    probe_report.write_text(
        json.dumps(
            {
                "rows": [
                    {"case_id": "917", "contract_pass": True},
                    {"case_id": "1202", "contract_pass": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    tpu_report = tmp_path / "tpu_report.json"
    tpu_report.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "summary": {
                    "selected_asset_count": 2,
                    "isolated_case_count": 1,
                    "interference_case_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    out_report = tmp_path / "registry.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_wind_benchmark_asset_registry.py",
            "--wind-root",
            str(wind_root),
            "--probe-report",
            str(probe_report),
            "--tpu-hffb-benchmark-report",
            str(tpu_report),
            "--out",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    assert report["summary"]["benchmark_ready_asset_count"] == 1
    assert report["summary"]["raw_probe_manifest_count"] == 0
    assert report["summary"]["official_external_benchmark_count"] == 1
    assert report["summary"]["materialized_tpu_seed_count"] == 1
    assert report["summary"]["probe_case_count"] == 2
    assert report["summary"]["probe_pass_count"] == 1
    assert report["summary"]["tpu_hffb_benchmark_contract_pass"] is True
    assert report["summary"]["tpu_hffb_selected_asset_count"] == 2
    assert report["summary"]["tpu_hffb_isolated_case_count"] == 1
    assert report["summary"]["tpu_hffb_interference_case_count"] == 1
    assert report["benchmark_ready_assets"][0]["signal_column_count"] == 2
    assert report["benchmark_ready_assets"][0]["raw_hffb_mapping_eligible"] is True
    assert report["benchmark_ready_assets"][0]["wind_time_history_gate_eligible"] is False
    assert report["benchmark_ready_assets"][0]["wind_time_history_gate_blocker"] == "missing_time_s_column"


def test_build_wind_benchmark_asset_registry_separates_raw_probe_manifests(tmp_path: Path) -> None:
    wind_root = tmp_path / "wind"
    wind_root.mkdir(parents=True)
    raw_manifest = wind_root / "sample.manifest.json"
    raw_manifest.write_text(
        json.dumps(
            {
                "source_name": "TPU Raw Probe",
                "source_url": "https://example.test/raw",
                "real_source": True,
                "source_origin_class": "official_external_benchmark",
                "contract_pass": True,
                "reason_code": "PASS",
                "data_path": str(wind_root / "sample.mat"),
                "sha256": "abc",
            }
        ),
        encoding="utf-8",
    )
    probe_report = tmp_path / "probe.json"
    probe_report.write_text(json.dumps({"rows": []}), encoding="utf-8")
    out_report = tmp_path / "registry.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_wind_benchmark_asset_registry.py",
            "--wind-root",
            str(wind_root),
            "--probe-report",
            str(probe_report),
            "--tpu-hffb-benchmark-report",
            str(tmp_path / "missing_tpu_report.json"),
            "--out",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    assert report["summary"]["benchmark_ready_asset_count"] == 0
    assert report["summary"]["raw_probe_manifest_count"] == 1
    assert report["raw_probe_manifests"][0]["asset_type"] == "raw_manifest"


def test_build_wind_benchmark_asset_registry_dedupes_raw_probes_by_case_id(tmp_path: Path) -> None:
    wind_root = tmp_path / "wind"
    wind_root.mkdir(parents=True)
    for name in ["case_917_a.manifest.json", "case_917_b.manifest.json"]:
        path = wind_root / name
        path.write_text(
            json.dumps(
                {
                    "source_name": "TPU Raw Probe",
                    "source_url": "https://example.test/raw",
                    "real_source": True,
                    "source_origin_class": "official_external_benchmark",
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "case_id": "917",
                    "data_path": str(wind_root / f"{name}.mat"),
                    "sha256": "abc",
                }
            ),
            encoding="utf-8",
        )
    probe_report = tmp_path / "probe.json"
    probe_report.write_text(json.dumps({"rows": []}), encoding="utf-8")
    out_report = tmp_path / "registry.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_wind_benchmark_asset_registry.py",
            "--wind-root",
            str(wind_root),
            "--probe-report",
            str(probe_report),
            "--tpu-hffb-benchmark-report",
            str(tmp_path / "missing_tpu_report.json"),
            "--out",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    assert report["summary"]["raw_probe_manifest_count"] == 1


def test_build_wind_benchmark_asset_registry_profiles_csv_for_gate_eligibility(tmp_path: Path) -> None:
    wind_root = tmp_path / "wind"
    wind_root.mkdir(parents=True)
    csv_path = wind_root / "wind.csv"
    csv_path.write_text(
        "time_s,across_wind_force_kN\n0.0,1.0\n36000.0,1.1\n",
        encoding="utf-8",
    )
    manifest = wind_root / "wind.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_name": "CAARC-like wind",
                "source_url": "https://example.test/wind",
                "real_source": True,
                "data_path": str(csv_path),
                "sha256": "abc",
            }
        ),
        encoding="utf-8",
    )
    probe_report = tmp_path / "probe.json"
    probe_report.write_text(json.dumps({"rows": []}), encoding="utf-8")
    out_report = tmp_path / "registry.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_wind_benchmark_asset_registry.py",
            "--wind-root",
            str(wind_root),
            "--probe-report",
            str(probe_report),
            "--tpu-hffb-benchmark-report",
            str(tmp_path / "missing_tpu_report.json"),
            "--out",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    row = report["benchmark_ready_assets"][0]
    assert row["row_count"] == 2
    assert row["dt_s"] == 36000.0
    assert row["duration_hours"] == 10.0
    assert row["wind_time_history_gate_eligible"] is True
