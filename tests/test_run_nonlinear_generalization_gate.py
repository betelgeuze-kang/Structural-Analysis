from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_nonlinear_generalization_gate_passes(tmp_path: Path) -> None:
    nonlinear = tmp_path / "nonlinear.json"
    pushover = tmp_path / "pushover.json"
    ndtha = tmp_path / "ndtha.json"
    foundation = tmp_path / "foundation.json"
    out = tmp_path / "out.json"

    _write(nonlinear, {"contract_pass": True, "checks": {"rust_backend_used_pass": True}})
    _write(pushover, {"contract_pass": True, "checks": {"section_family_pass": True}})
    _write(ndtha, {"contract_pass": True, "checks": {"section_family_pass": True, "rust_backend_used_pass": True}})
    _write(
        foundation,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "foundation_link_models_ready": True,
            },
            "summary": {"foundation_link_model_types": ["compression_only", "frictional_gap"]},
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_nonlinear_generalization_gate.py",
            "--nonlinear-engine-report",
            str(nonlinear),
            "--pushover-stress-report",
            str(pushover),
            "--ndtha-stress-report",
            str(ndtha),
            "--foundation-soil-link-gate-report",
            str(foundation),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["beam_column_generalization_pass"] is True
    assert report["summary"]["beam_family_count"] >= 6
    assert report["summary"]["beam_max_trial_end_moment_ratio"] > 1.0
    assert report["summary"]["beam_stability_index_max"] > 0.0
    assert report["summary"]["beam_strain_energy_max_n_m"] > 0.0
    assert report["summary"]["fiber_family_count"] >= 6
    assert report["summary"]["fiber_max_abs_strain"] > 0.0
    assert report["summary"]["fiber_steel_yield_ratio_max"] > 1.0
    assert report["summary"]["fiber_concrete_crack_ratio_max"] > 0.0
    assert report["summary"]["fiber_section_strain_energy_max_n"] > 0.0
    assert "yield_ratio_max=" in report["summary_line"]
    assert report["summary"]["layered_family_count"] >= 6
    assert report["checks"]["joint_panel_family_pass"] is True
    assert report["checks"]["foundation_section_family_pass"] is True
    assert report["checks"]["connection_section_family_pass"] is True
    assert report["checks"]["substructure_section_family_pass"] is True
    assert report["checks"]["device_section_family_pass"] is True
    assert report["checks"]["isolation_section_family_pass"] is True
    assert report["checks"]["soil_interface_section_family_pass"] is True
    assert report["checks"]["bearing_section_family_pass"] is True
    assert report["checks"]["retrofit_section_family_pass"] is True
    assert report["checks"]["ground_improvement_section_family_pass"] is True
    assert report["summary"]["joint_panel_family_count"] >= 4
    assert report["summary"]["foundation_section_family_count"] >= 4
    assert report["summary"]["connection_section_family_count"] >= 4
    assert report["summary"]["substructure_section_family_count"] >= 4
    assert report["summary"]["device_section_family_count"] >= 4
    assert report["summary"]["isolation_section_family_count"] >= 4
    assert report["summary"]["soil_interface_section_family_count"] >= 4
    assert report["summary"]["bearing_section_family_count"] >= 4
    assert report["summary"]["retrofit_section_family_count"] >= 4
    assert report["summary"]["ground_improvement_section_family_count"] >= 4
    assert report["checks"]["layered_shell_wall_pass"] is True
