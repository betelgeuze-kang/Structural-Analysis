from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_noise_convergence_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_noise_convergence_gate_accepts_requested_plus_minus_10_only(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    out_path = tmp_path / "noise_convergence.json"
    _write_json(
        cases_path,
        {
            "cases": [
                {
                    "case_id": "RWTH-001",
                    "split": "train",
                    "topology_type": "rahmen",
                    "hazard_type": "wind",
                    "metrics": {
                        "drift_ratio_pct": {"hf": 0.8},
                        "base_shear_kN": {"hf": 1200.0},
                        "buckling_factor": {"hf": 2.8},
                    },
                },
                {
                    "case_id": "RWTH-002",
                    "split": "train",
                    "topology_type": "truss",
                    "hazard_type": "seismic",
                    "metrics": {
                        "drift_ratio_pct": {"hf": 0.9},
                        "base_shear_kN": {"hf": 1225.0},
                        "buckling_factor": {"hf": 2.9},
                    },
                },
                {
                    "case_id": "RWTH-003",
                    "split": "val",
                    "topology_type": "rahmen",
                    "hazard_type": "seismic",
                    "metrics": {
                        "drift_ratio_pct": {"hf": 1.0},
                        "base_shear_kN": {"hf": 1250.0},
                        "buckling_factor": {"hf": 3.0},
                    },
                },
                {
                    "case_id": "RWTH-004",
                    "split": "test",
                    "topology_type": "truss",
                    "hazard_type": "wind",
                    "metrics": {
                        "drift_ratio_pct": {"hf": 1.1},
                        "base_shear_kN": {"hf": 1275.0},
                        "buckling_factor": {"hf": 3.1},
                    },
                },
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--cases",
            str(cases_path),
            "--target-split",
            "all",
            "--limit-cases",
            "4",
            "--seeds",
            "11,23,47",
            "--stiffness-noise-levels",
            "10",
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["includes_plus_minus_10"] is True
    assert payload["checks"]["includes_plus_minus_5"] is False
    assert payload["checks"]["requested_noise_pairs_present"] is True
    assert payload["summary"]["requested_abs_noise_levels"] == [10.0]

