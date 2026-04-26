from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def _write_wind_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "across_wind_force_kN", "along_wind_force_kN"])
        for i in range(120):
            t = i * 1.0
            w.writerow([f"{t:.1f}", f"{(10.0 if i % 2 == 0 else -10.0):.6f}", "0.0"])


def test_wind_gate_fails_without_wind_cases(tmp_path: Path) -> None:
    wind_csv = tmp_path / "wind.csv"
    _write_wind_csv(wind_csv)
    sha = hashlib.sha256(wind_csv.read_bytes()).hexdigest()
    manifest = tmp_path / "wind.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "real_source": True,
                "source_url": "https://example.org/wind",
                "data_path": str(wind_csv),
                "sha256": sha,
            }
        ),
        encoding="utf-8",
    )
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps({"cases": [{"case_id": "S1", "split": "test", "hazard_type": "seismic"}]}),
        encoding="utf-8",
    )
    out = tmp_path / "wind_gate_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_wind_time_history_gate.py",
        "--cases",
        str(cases),
        "--wind-csv",
        str(wind_csv),
        "--source-manifest",
        str(manifest),
        "--min-case-count",
        "1",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_INVALID_INPUT"


def test_ssi_gate_fails_without_seismic_cases(tmp_path: Path) -> None:
    gm = tmp_path / "gm.csv"
    with gm.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "accel_g"])
        for i in range(64):
            w.writerow([f"{0.01 * i:.3f}", f"{(0.1 if i % 2 == 0 else -0.1):.6f}"])

    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps({"cases": [{"case_id": "W1", "split": "test", "hazard_type": "wind"}]}),
        encoding="utf-8",
    )
    out = tmp_path / "ssi_gate_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_ssi_boundary_gate.py",
        "--cases",
        str(cases),
        "--ground-motion-csv",
        str(gm),
        "--min-case-count",
        "1",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_INVALID_INPUT"


def test_ssi_gate_pass_reports_section_family_beam_demand(tmp_path: Path) -> None:
    gm = tmp_path / "gm.csv"
    with gm.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "accel_g"])
        for i in range(96):
            amp = 0.02 + 0.001 * i if i < 48 else 0.068 - 0.001 * (i - 48)
            w.writerow([f"{0.01 * i:.3f}", f"{(amp if i % 2 == 0 else -amp):.6f}"])

    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "S1",
                        "split": "test",
                        "hazard_type": "seismic",
                        "topology_type": "wall-frame",
                        "material_type": "rc_composite",
                        "load_scale": 1.0,
                        "metrics": {
                            "drift_ratio_pct": {"hf": 1.2},
                            "base_shear_kN": {"hf": 1200.0},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "ssi_gate_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_ssi_boundary_gate.py",
        "--cases",
        str(cases),
        "--ground-motion-csv",
        str(gm),
        "--min-case-count",
        "1",
        "--max-case-count",
        "1",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["section_family_pass"] is True
    assert report["checks"]["material_model_pass"] is True
    assert report["summary"]["section_family_beam_tangent_scale_min"] > 0.0
    assert report["summary"]["section_family_beam_max_trial_end_moment_ratio"] > 1.0
    assert report["summary"]["section_family_beam_stability_index_max"] > 0.0
    assert report["summary"]["section_family_beam_strain_energy_total_n_m"] > 0.0
    assert report["summary_line"].startswith("SSI boundary: PASS")
    assert "section_demand=pass(" in report["summary_line"]
    assert any("section_family_demand=pass" in item for item in report["reasons"])
