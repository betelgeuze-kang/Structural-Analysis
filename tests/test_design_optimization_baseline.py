from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


@pytest.mark.parametrize("custom_prices", [False, True])
def test_run_design_optimization_baseline(tmp_path: Path, custom_prices: bool) -> None:
    dataset = tmp_path / "dataset.npz"
    np.savez_compressed(
        dataset,
        group_index_per_member=np.asarray([0, 0, 1, 1], dtype=np.int32),
        unique_group_ids=np.asarray(["G0", "G1"]),
        rebar_ratio=np.asarray([0.03, 0.03, 0.02, 0.02], dtype=np.float64),
        max_dcr=np.asarray([0.55, 0.58, 0.90, 0.92], dtype=np.float64),
        congestion_index=np.asarray([0.20, 0.20, 0.35, 0.35], dtype=np.float64),
        lap_splice_ratio=np.asarray([0.10, 0.10, 0.18, 0.18], dtype=np.float64),
        anchorage_complexity=np.asarray([0.15, 0.15, 0.30, 0.30], dtype=np.float64),
        detailing_violation_ratio=np.asarray([0.02, 0.02, 0.12, 0.12], dtype=np.float64),
        volume_m3=np.asarray([1.0, 1.0, 1.5, 1.5], dtype=np.float64),
        steel_mass_kg=np.asarray([80.0, 80.0, 120.0, 120.0], dtype=np.float64),
        member_types=np.asarray(["beam", "beam", "column", "column"]),
        drift_envelope_max_pct=np.asarray([1.2, 1.2, 1.2, 1.2], dtype=np.float64),
        residual_drift_pct_max_abs=np.asarray([0.3, 0.3, 0.3, 0.3], dtype=np.float64),
        action_mask=np.asarray([[True, True], [True, True]], dtype=np.bool_),
    )
    out = tmp_path / "baseline.json"
    price_args = []
    if custom_prices:
        prices = tmp_path / "prices.json"
        prices.write_text(json.dumps({"concrete_per_m3": 220.0, "steel_per_kg": 3.6, "rebar_per_kg": 2.6,
                                     "table_version": "test-double-index-v1"}), encoding="utf-8")
        price_args = ["--price-table", str(prices)]
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_design_optimization_baseline.py",
            "--dataset-npz",
            str(dataset),
            "--out",
            str(out),
            "--max-iterations",
            "12",
            *price_args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["group_count"] == 2
    assert payload["summary"]["final_violation_score"] <= payload["summary"]["baseline_violation_score"]
    basis = payload["cost_basis"]
    assert basis["verified_construction_savings"] is False
    assert basis["monetary_savings"] is None
    assert basis["price_provenance"]["currency"] is None
    expected_materials = 5.0 * 110.0 + 400.0 * 1.8 + (2 * 0.03 + 3 * 0.02) * 7850.0 * 1.3
    assert payload["summary"]["baseline_cost_proxy"] == pytest.approx(expected_materials * (2 if custom_prices else 1))
    assert payload["performance"]["search_wall_seconds"] >= 0
    assert payload["performance"]["speedup"] is None
    assert payload["performance"]["solver_wall_seconds"] is None
    assert payload["structural_verification"]["final_design_eligible"] is False
