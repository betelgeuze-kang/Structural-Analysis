from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_run_construction_sequence_gate_reports_section_family_beam_demand(tmp_path: Path) -> None:
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "C1",
                        "split": "test",
                        "topology_type": "wall-frame",
                        "material_type": "rc_composite",
                        "load_scale": 1.0,
                        "metrics": {
                            "drift_ratio_pct": {"hf": 1.1},
                            "base_shear_kN": {"hf": 1100.0},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "construction_sequence_gate_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_construction_sequence_gate.py",
            "--cases",
            str(cases),
            "--target-split",
            "test",
            "--min-case-count",
            "1",
            "--max-case-count",
            "1",
            "--stage-count",
            "6",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["section_family_pass"] is True
    assert payload["checks"]["all_stages_converged"] is True
    assert payload["checks"]["rust_backend_used_pass"] is True
    assert payload["summary"]["section_family_beam_tangent_scale_min"] > 0.0
    assert payload["summary"]["section_family_beam_max_trial_end_moment_ratio"] > 1.0
    assert payload["summary"]["section_family_beam_stability_index_max"] > 0.0
    assert payload["summary"]["section_family_beam_strain_energy_total_n_m"] > 0.0
    assert payload["summary_line"].startswith("Construction sequence: PASS")
    assert "section_demand=pass(" in payload["summary_line"]
    assert any("section_family_demand=pass" in item for item in payload["reasons"])
