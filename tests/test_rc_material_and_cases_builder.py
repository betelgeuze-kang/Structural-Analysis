from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from implementation.phase1.rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile


def test_rc_composite_profile_degrades_stiffness() -> None:
    n = 6
    out = apply_rc_composite_profile(
        story_k_n_per_m=np.full(n, 2.0e6, dtype=np.float64),
        story_yield_drift_m=np.full(n, 0.02, dtype=np.float64),
        story_mass_kg=np.full(n, 2.0e5, dtype=np.float64),
        story_h_m=np.full(n, 3.2, dtype=np.float64),
        drift_ratio_proxy=np.linspace(0.008, 0.015, num=n, dtype=np.float64),
        elapsed_hours=6.0,
        cycle_count=120,
        cfg=RCCompositeMaterialConfig(),
    )
    k_mod = np.asarray(out["story_k_n_per_m"], dtype=np.float64)
    y_mod = np.asarray(out["story_yield_drift_m"], dtype=np.float64)
    idx = out["indices"]
    assert float(np.mean(k_mod)) < 2.0e6
    assert float(np.mean(y_mod)) < 0.02
    assert float(idx["cracking_index_mean"]) > 0.0
    assert float(idx["bond_slip_index_mean"]) > 0.0
    assert float(idx["compression_damage_mean"]) >= 0.0
    assert int(idx["tension_softening_story_count"]) >= 1


def test_build_cases_commercial_source_family_and_shell_beam(tmp_path: Path) -> None:
    merged = tmp_path / "merged.csv"
    out_json = tmp_path / "cases.json"
    rows = [
        {
            "case_id": "C-001",
            "split": "train",
            "ood_tag": "in_distribution",
            "topology_type": "rahmen",
            "hazard_type": "seismic",
            "load_scale": "1.0",
            "residual_norm": "0.1",
            "hf_drift_ratio_pct": "1.2",
            "lf_drift_ratio_pct": "1.4",
            "hf_base_shear_kN": "3200",
            "lf_base_shear_kN": "3000",
            "hf_mode_shape_mac": "0.95",
            "lf_mode_shape_mac": "0.90",
            "hf_buckling_factor": "2.2",
            "lf_buckling_factor": "2.0",
            "hf_equilibrium_residual": "0.03",
            "lf_equilibrium_residual": "0.05",
            "source_family": "family_a",
            "element_mix": "beam_only",
        },
        {
            "case_id": "C-002",
            "split": "test",
            "ood_tag": "ood_topology",
            "topology_type": "wall-frame",
            "hazard_type": "combined",
            "load_scale": "1.1",
            "residual_norm": "0.12",
            "hf_drift_ratio_pct": "1.8",
            "lf_drift_ratio_pct": "2.0",
            "hf_base_shear_kN": "4100",
            "lf_base_shear_kN": "3850",
            "hf_mode_shape_mac": "0.92",
            "lf_mode_shape_mac": "0.88",
            "hf_buckling_factor": "2.0",
            "lf_buckling_factor": "1.8",
            "hf_equilibrium_residual": "0.05",
            "lf_equilibrium_residual": "0.08",
            "source_family": "family_b",
            "element_mix": "shell_beam_mix",
        },
    ]
    with merged.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    cmd = [
        sys.executable,
        "implementation/phase1/build_cases_from_commercial_exports.py",
        "--merged-csv",
        str(merged),
        "--metric-source",
        "commercial_solver_export",
        "--min-source-families",
        "2",
        "--require-shell-beam-mix",
        "--out",
        str(out_json),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["source_family_summary"]["distinct_source_family_count"] >= 2
    assert payload["source_family_summary"]["shell_beam_mix_case_count"] >= 1
