from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_rc_benchmark_lock_gate_pass(tmp_path: Path) -> None:
    cases = tmp_path / "rc_cases.json"
    out = tmp_path / "rc_report.json"
    cases.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "RC-1",
                        "benchmark_family": "cyclic_wall_cracking",
                        "story_k_n_per_m": [2200000] * 6,
                        "story_yield_drift_m": [0.02] * 6,
                        "story_mass_kg": [210000] * 6,
                        "story_h_m": [3.2] * 6,
                        "drift_ratio_proxy": [0.006, 0.007, 0.008, 0.009, 0.010, 0.011],
                        "elapsed_hours": 4.0,
                        "cycle_count": 40,
                        "expected_ranges": {
                            "cracking_index_mean": [0.95, 1.0],
                            "stiffness_scale_mean": [0.68, 0.76],
                            "yield_scale_mean": [0.85, 0.90]
                        }
                    },
                    {
                        "case_id": "RC-2",
                        "benchmark_family": "bond_slip_pullout",
                        "story_k_n_per_m": [1800000] * 6,
                        "story_yield_drift_m": [0.018] * 6,
                        "story_mass_kg": [160000] * 6,
                        "story_h_m": [3.1] * 6,
                        "drift_ratio_proxy": [0.004, 0.005, 0.006, 0.007, 0.008, 0.009],
                        "elapsed_hours": 1.0,
                        "cycle_count": 120,
                        "expected_ranges": {
                            "bond_slip_index_mean": [0.80, 1.0],
                            "yield_scale_mean": [0.80, 0.90]
                        }
                    },
                    {
                        "case_id": "RC-3",
                        "benchmark_family": "creep_shrinkage_column",
                        "story_k_n_per_m": [2600000] * 6,
                        "story_yield_drift_m": [0.022] * 6,
                        "story_mass_kg": [240000] * 6,
                        "story_h_m": [3.4] * 6,
                        "drift_ratio_proxy": [0.00001, 0.00001, 0.00002, 0.00002, 0.00003, 0.00003],
                        "elapsed_hours": 4320.0,
                        "cycle_count": 2,
                        "expected_ranges": {
                            "creep_index_mean": [0.95, 1.0],
                            "stiffness_scale_mean": [0.64, 0.70]
                        }
                    },
                    {
                        "case_id": "RC-4",
                        "benchmark_family": "slab_wall_interaction",
                        "story_k_n_per_m": [2000000] * 6,
                        "story_yield_drift_m": [0.019] * 6,
                        "story_mass_kg": [175000] * 6,
                        "story_h_m": [3.2] * 6,
                        "drift_ratio_proxy": [0.002, 0.003, 0.004, 0.005, 0.006, 0.007],
                        "elapsed_hours": 48.0,
                        "cycle_count": 60,
                        "expected_ranges": {
                            "bond_slip_index_mean": [0.60, 0.95],
                            "yield_scale_mean": [0.84, 0.93]
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_rc_benchmark_lock_gate.py",
            "--cases",
            str(cases),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["cracking_case_pass"] is True
    assert report["checks"]["bond_slip_case_pass"] is True
    assert report["checks"]["creep_case_pass"] is True


def test_rc_benchmark_lock_gate_fail_on_bad_range(tmp_path: Path) -> None:
    cases = tmp_path / "rc_cases_bad.json"
    out = tmp_path / "rc_report_bad.json"
    cases.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "RC-1",
                        "benchmark_family": "cyclic_wall_cracking",
                        "story_k_n_per_m": [2200000] * 6,
                        "story_yield_drift_m": [0.02] * 6,
                        "story_mass_kg": [210000] * 6,
                        "story_h_m": [3.2] * 6,
                        "drift_ratio_proxy": [0.006, 0.007, 0.008, 0.009, 0.010, 0.011],
                        "elapsed_hours": 4.0,
                        "cycle_count": 40,
                        "expected_ranges": {
                            "cracking_index_mean": [0.0, 0.1]
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_rc_benchmark_lock_gate.py",
            "--cases",
            str(cases),
            "--min-case-count",
            "1",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_BENCHMARK_LOCK_FAIL"


def test_rc_benchmark_lock_gate_authority_pass(tmp_path: Path) -> None:
    sensor = tmp_path / "sensor.csv"
    baseline = tmp_path / "baseline.csv"
    sensor.write_text("time_s,disp_top_mm\n0.0,0.0\n0.01,0.1\n0.02,0.2\n", encoding="utf-8")
    baseline.write_text("time_s,disp_top_mm\n0.0,0.0\n0.01,0.1\n0.02,0.2\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()

    sensor_sha = _sha(sensor)
    baseline_sha = _sha(baseline)

    metrics = tmp_path / "nheri_case01_waveform_metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_pass": True,
                "checks": {
                    "waveform_corr_pass": True,
                    "phase_error_pass": True,
                    "residual_drift_pass": True,
                },
                "metrics": {
                    "waveform_corr": 0.99,
                    "phase_error_ms": 1.2,
                    "residual_drift_mm": 0.4,
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "nheri_case01_source_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_url": "https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/",
                "source_sha256": sensor_sha,
            }
        ),
        encoding="utf-8",
    )
    # Duplicate the authority artifacts for the 3-case minimum.
    authority_cases = []
    authority_cases.append(
        {
            "case_id": "NHERI-1",
            "real_source": True,
            "source_url": "https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/",
            "sensor_csv_path": str(sensor),
            "baseline_csv_path": str(baseline),
            "waveform_metrics_path": str(metrics),
            "sensor_csv_sha256": sensor_sha,
            "baseline_csv_sha256": baseline_sha,
        }
    )
    for i in range(2, 4):
        metrics_i = tmp_path / f"nheri_case0{i}_waveform_metrics.json"
        manifest_i = tmp_path / f"nheri_case0{i}_source_manifest.json"
        metrics_i.write_text(metrics.read_text(encoding="utf-8"), encoding="utf-8")
        manifest_i.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
        authority_cases.append(
            {
                "case_id": f"NHERI-{i}",
                "real_source": True,
                "source_url": "https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/",
                "sensor_csv_path": str(sensor),
                "baseline_csv_path": str(baseline),
                "waveform_metrics_path": str(metrics_i),
                "sensor_csv_sha256": sensor_sha,
                "baseline_csv_sha256": baseline_sha,
            }
        )

    catalog = tmp_path / "authority_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tracks": {
                    "nheri": {
                        "cases": authority_cases
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    cases = tmp_path / "rc_cases.json"
    out = tmp_path / "rc_report_authority.json"
    cases.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "RC-1",
                        "benchmark_family": "cyclic_wall_cracking",
                        "story_k_n_per_m": [2200000] * 6,
                        "story_yield_drift_m": [0.02] * 6,
                        "story_mass_kg": [210000] * 6,
                        "story_h_m": [3.2] * 6,
                        "drift_ratio_proxy": [0.006, 0.007, 0.008, 0.009, 0.010, 0.011],
                        "elapsed_hours": 4.0,
                        "cycle_count": 40,
                        "expected_ranges": {
                            "cracking_index_mean": [0.95, 1.0],
                            "stiffness_scale_mean": [0.68, 0.76],
                            "yield_scale_mean": [0.85, 0.90],
                        },
                    },
                    {
                        "case_id": "RC-2",
                        "benchmark_family": "bond_slip_pullout",
                        "story_k_n_per_m": [1800000] * 6,
                        "story_yield_drift_m": [0.018] * 6,
                        "story_mass_kg": [160000] * 6,
                        "story_h_m": [3.1] * 6,
                        "drift_ratio_proxy": [0.004, 0.005, 0.006, 0.007, 0.008, 0.009],
                        "elapsed_hours": 1.0,
                        "cycle_count": 120,
                        "expected_ranges": {
                            "bond_slip_index_mean": [0.80, 1.0],
                            "yield_scale_mean": [0.80, 0.90],
                        },
                    },
                    {
                        "case_id": "RC-3",
                        "benchmark_family": "creep_shrinkage_column",
                        "story_k_n_per_m": [2600000] * 6,
                        "story_yield_drift_m": [0.022] * 6,
                        "story_mass_kg": [240000] * 6,
                        "story_h_m": [3.4] * 6,
                        "drift_ratio_proxy": [0.00001, 0.00001, 0.00002, 0.00002, 0.00003, 0.00003],
                        "elapsed_hours": 4320.0,
                        "cycle_count": 2,
                        "expected_ranges": {
                            "creep_index_mean": [0.95, 1.0],
                            "stiffness_scale_mean": [0.64, 0.70],
                        },
                    },
                    {
                        "case_id": "RC-4",
                        "benchmark_family": "slab_wall_interaction",
                        "story_k_n_per_m": [2000000] * 6,
                        "story_yield_drift_m": [0.019] * 6,
                        "story_mass_kg": [175000] * 6,
                        "story_h_m": [3.2] * 6,
                        "drift_ratio_proxy": [0.002, 0.003, 0.004, 0.005, 0.006, 0.007],
                        "elapsed_hours": 48.0,
                        "cycle_count": 60,
                        "expected_ranges": {
                            "bond_slip_index_mean": [0.60, 0.95],
                            "yield_scale_mean": [0.84, 0.93],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_rc_benchmark_lock_gate.py",
            "--cases",
            str(cases),
            "--authority-catalog",
            str(catalog),
            "--require-authority",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["authority_track_pass"] is True
    assert report["summary"]["validation_mode"] == "hybrid_authority_locked"
