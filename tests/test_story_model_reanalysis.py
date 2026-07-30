"""Tests for story-model reanalysis module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_story_reanalysis_cli_writes_receipt(tmp_path: Path) -> None:
    state_npz = tmp_path / "solver_state.npz"
    np.savez(
        state_npz,
        story_band=np.asarray([0, 1], dtype=np.int32),
        rebar_ratio=np.asarray([0.018, 0.022], dtype=np.float64),
        max_dcr=np.asarray([0.72, 0.81], dtype=np.float64),
        repair_influence=np.asarray([1.0, 1.1], dtype=np.float64),
        congestion=np.asarray([0.1, 0.2], dtype=np.float64),
        detailing=np.asarray([0.2, 0.3], dtype=np.float64),
        zone_label=np.asarray(["core", "perimeter"], dtype="<U32"),
        group_cost_proxy=np.asarray([1.0, 1.2], dtype=np.float64),
    )
    changes = tmp_path / "changes.json"
    changes.write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "group_index": 1,
                        "after_rebar_ratio": 0.024,
                        "max_dcr_after": 0.78,
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mgt = tmp_path / "source.mgt"
    mgt.write_text("*UNIT\n", encoding="utf-8")
    roundtrip = tmp_path / "roundtrip.json"
    roundtrip.write_text(
        json.dumps(
            {
                "source": {"path": str(mgt), "sha256": "0" * 64},
                "parser": {"section_counts": {"ELEMENT": 2, "NODE": 3}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "story_model_reanalysis.json"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_story_model_reanalysis.py"),
        "--state-npz",
        str(state_npz),
        "--changes-json",
        str(changes),
        "--roundtrip-json",
        str(roundtrip),
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
