"""Tests for story-model reanalysis module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_NPZ = REPO_ROOT / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz"
CHANGES = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json"
)


def test_story_reanalysis_cli_writes_receipt() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/story_model_reanalysis_test.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_story_model_reanalysis.py"),
        "--state-npz",
        str(STATE_NPZ),
        "--changes-json",
        str(CHANGES),
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    receipt = payload["story_model_reanalysis"]
    assert receipt["schema_version"] == "story-model-reanalysis-receipt.v1"
    assert receipt["status"] in {"pass", "warn", "blocked"}
    assert float(receipt["metrics"]["max_drift_ratio_pct"]) > 0
    assert str(receipt["solver"]["backend_ndtha"])
    assert payload["mgt_provenance"]["mgt_exists"] is True


def test_apply_changes_updates_group_rebar() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    import numpy as np
    from run_story_model_reanalysis import apply_optimization_changes_to_state  # noqa: E402

    state = {
        "rebar_ratio": np.asarray([0.01, 0.02], dtype=np.float64),
        "thickness_scale": np.asarray([1.0, 1.0], dtype=np.float64),
        "max_dcr": np.asarray([0.5, 0.6], dtype=np.float64),
        "story_band": np.asarray([0, 1], dtype=np.int32),
        "repair_influence": np.asarray([1.0, 1.0], dtype=np.float64),
        "congestion": np.asarray([0.0, 0.0], dtype=np.float64),
        "detailing": np.asarray([1.0, 1.0], dtype=np.float64),
        "zone_label": np.asarray(["intermediate", "intermediate"], dtype="<U32"),
    }
    updated = apply_optimization_changes_to_state(
        state,
        [{"group_index": 1, "after_rebar_ratio": 0.004}],
    )
    assert float(updated["rebar_ratio"][1]) == 0.004
