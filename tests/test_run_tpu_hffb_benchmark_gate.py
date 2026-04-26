from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_tpu_hffb_benchmark_gate_passes_with_isolated_and_interference(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "benchmark_ready_assets": [
                    {
                        "real_source": True,
                        "source_origin_class": "official_external_benchmark",
                        "benchmark_seed_id": "tpu_hffb_isolated_highrise_seed_01",
                        "case_role": "baseline_isolated_highrise",
                        "holdout_split": "val",
                        "data_path": str(tmp_path / "isolated.csv"),
                        "row_count": 100,
                        "signal_column_count": 200,
                        "dt_s": 0.001,
                        "duration_hours": 0.01,
                        "raw_hffb_mapping_eligible": True,
                        "wind_time_history_gate_eligible": False,
                        "wind_time_history_gate_blocker": "missing_across_wind_force_kN_column",
                        "source_name": "TPU isolated",
                        "source_url": "https://example.test/616",
                    },
                    {
                        "real_source": True,
                        "source_origin_class": "official_external_benchmark",
                        "benchmark_seed_id": "tpu_hffb_interference_highrise_seed_01",
                        "case_role": "neighbor_interference_highrise",
                        "holdout_split": "holdout",
                        "data_path": str(tmp_path / "interference.csv"),
                        "row_count": 80,
                        "signal_column_count": 252,
                        "dt_s": 0.0012,
                        "duration_hours": 0.002,
                        "raw_hffb_mapping_eligible": True,
                        "wind_time_history_gate_eligible": False,
                        "wind_time_history_gate_blocker": "missing_across_wind_force_kN_column",
                        "source_name": "TPU interference",
                        "source_url": "https://example.test/917",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_tpu_hffb_benchmark_gate.py",
            "--asset-registry",
            str(registry),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out)
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["selected_asset_count"] == 2
    assert report["summary"]["isolated_case_count"] == 1
    assert report["summary"]["interference_case_count"] == 1
    assert report["summary"]["wind_time_history_gate_eligible_count"] == 0
    assert report["checks"]["raw_hffb_mapping_eligible_pass"] is True


def test_run_tpu_hffb_benchmark_gate_requires_interference_case(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "benchmark_ready_assets": [
                    {
                        "real_source": True,
                        "source_origin_class": "official_external_benchmark",
                        "benchmark_seed_id": "tpu_hffb_isolated_highrise_seed_01",
                        "case_role": "baseline_isolated_highrise",
                        "holdout_split": "val",
                        "data_path": str(tmp_path / "isolated.csv"),
                        "row_count": 100,
                        "signal_column_count": 200,
                        "dt_s": 0.001,
                        "duration_hours": 0.01,
                        "raw_hffb_mapping_eligible": True,
                        "wind_time_history_gate_eligible": False,
                        "wind_time_history_gate_blocker": "missing_across_wind_force_kN_column",
                        "source_name": "TPU isolated",
                        "source_url": "https://example.test/616",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_tpu_hffb_benchmark_gate.py",
            "--asset-registry",
            str(registry),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out)
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_TPU_ASSET_COUNT"

