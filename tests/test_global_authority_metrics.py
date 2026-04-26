from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_compute_authority_metrics_sac_pass(tmp_path: Path) -> None:
    out = tmp_path / "sac_metrics.json"
    cmd = [
        sys.executable,
        "implementation/phase1/compute_global_authority_metrics.py",
        "--mode",
        "sac",
        "--hf-csv",
        "implementation/phase1/commercial_hf_export_sample.csv",
        "--lf-csv",
        "implementation/phase1/commercial_lf_export_sample.csv",
        "--max-error-pct",
        "20",
        "--min-mac",
        "0.90",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["metric_source"] == "direct_reference"
    assert report["checks"]["member_force_components_5d_pass"] is True


def test_compute_authority_metrics_nheri_pass(tmp_path: Path) -> None:
    out = tmp_path / "nheri_metrics.json"
    cmd = [
        sys.executable,
        "implementation/phase1/compute_global_authority_metrics.py",
        "--mode",
        "nheri",
        "--sensor-csv",
        "implementation/phase1/open_data/megastructure/field_sensor_record.csv",
        "--baseline-csv",
        "implementation/phase1/open_data/megastructure/field_sensor_record.csv",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["metric_source"] == "direct_reference"
    assert report["checks"]["waveform_corr_pass"] is True
