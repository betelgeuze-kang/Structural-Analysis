from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys


def _write_wave(path: Path, *, scale: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "acc_x_g", "disp_top_mm", "disp_mid_mm"])
        for i in range(240):
            t = i * 0.01
            disp = scale * (0.8 if (i % 24) < 12 else -0.8) * (1.0 + 0.25 * (i / 239.0))
            w.writerow([f"{t:.4f}", "0.0", f"{disp:.6f}", f"{0.75*disp:.6f}"])


def test_damper_validation_gate_pass(tmp_path: Path) -> None:
    sensor = tmp_path / "sensor.csv"
    baseline = tmp_path / "baseline.csv"
    _write_wave(sensor, scale=0.9)
    _write_wave(baseline, scale=1.0)

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "D1",
                        "real_source": True,
                        "source_url": "https://example.org/d1",
                        "sensor_csv_path": str(sensor),
                        "baseline_csv_path": str(baseline),
                        "damper_type": "viscoelastic",
                        "damper_params": {"c": 0.08, "k": 0.04},
                    },
                    {
                        "case_id": "D2",
                        "real_source": True,
                        "source_url": "https://example.org/d2",
                        "sensor_csv_path": str(sensor),
                        "baseline_csv_path": str(baseline),
                        "damper_type": "tmd",
                        "damper_params": {"c": 0.07, "k": 0.03, "omega": 2.3, "zeta": 0.15},
                    },
                    {
                        "case_id": "D3",
                        "real_source": True,
                        "source_url": "https://example.org/d3",
                        "sensor_csv_path": str(sensor),
                        "baseline_csv_path": str(baseline),
                        "damper_type": "fps",
                        "damper_params": {"c": 0.06, "mu": 0.05, "slip_mm": 0.8},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "damper_gate_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_damper_validation_gate.py",
        "--catalog",
        str(catalog),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["damper_type_diversity_pass"] is True
    assert report["checks"]["waveform_corr_pass"] is True
    assert report["checks"]["section_family_pass"] is True
    assert report["checks"]["material_model_pass"] is True
    assert int(report["summary"]["case_count"]) == 3
    assert float(report["summary"]["section_family_coverage_min"]) >= 0.95
    assert float(report["summary"]["section_family_beam_tangent_scale_min"]) > 0.0
    assert float(report["summary"]["section_family_beam_max_trial_end_moment_ratio"]) > 0.0
    assert float(report["summary"]["section_family_beam_stability_index_max"]) > 0.0
    assert float(report["summary"]["section_family_beam_strain_energy_total_n_m"]) > 0.0
    assert report["summary_line"].startswith("Damper validation: PASS")
    assert "section_demand=pass(" in report["summary_line"]
    assert any("section_family_demand=pass" in item for item in report["reasons"])
