from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from implementation.phase1.design_optimization_env import DesignOptimizationConfig
from implementation.phase1.run_design_optimization_cost_reduction_smoke import run_cost_reduction_smoke


SCRIPT = Path("implementation/phase1/run_design_optimization_cost_reduction_smoke.py")


def _smoke_state() -> dict[str, np.ndarray]:
    return {
        "group_ids": np.asarray(["G0", "G1"], dtype="<U8"),
        "rebar_ratio": np.asarray([0.020, 0.016], dtype=np.float64),
        "max_dcr": np.asarray([0.82, 0.74], dtype=np.float64),
        "congestion": np.asarray([0.20, 0.15], dtype=np.float64),
        "lap_splice": np.asarray([0.10, 0.08], dtype=np.float64),
        "anchorage": np.asarray([0.25, 0.22], dtype=np.float64),
        "detailing": np.asarray([0.30, 0.25], dtype=np.float64),
        "group_cost_proxy": np.asarray([1200.0, 1100.0], dtype=np.float64),
        "member_type": np.asarray(["beam", "slab"], dtype="<U16"),
        "zone_label": np.asarray(["perimeter", "perimeter"], dtype="<U16"),
        "semantic_group": np.asarray(["", ""], dtype="<U16"),
        "story_band": np.asarray([0, 1], dtype=np.int32),
        "repair_influence": np.asarray([1.15, 1.05], dtype=np.float64),
        "combination_match_score": np.asarray([0.92, 0.85], dtype=np.float64),
        "combination_risk": np.asarray([1.04, 1.08], dtype=np.float64),
        "global_drift_pct": np.asarray([1.2], dtype=np.float64),
        "global_residual_drift_pct": np.asarray([0.25], dtype=np.float64),
        "action_mask": np.asarray([[True, True], [True, True]], dtype=np.bool_),
        "action_mask_extended": np.asarray(
            [
                [True, False, True, False, True, False],
                [True, False, True, False, True, False],
            ],
            dtype=np.bool_,
        ),
        "thickness_scale": np.asarray([1.0, 1.0], dtype=np.float64),
        "detailing_quality": np.asarray([1.0, 1.0], dtype=np.float64),
        "robustness_margin": np.asarray([0.10, 0.10], dtype=np.float64),
    }


def test_cost_reduction_smoke_runs_baseline_and_trial(monkeypatch, tmp_path) -> None:
    def _solver(*, state, cfg, step_count):
        rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
        return {
            "violation_score": 0.0,
            "feasible": True,
            "max_dcr": float(np.max(rebar) * 10.0),
            "max_drift_pct": 1.0,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_cost_reduction_smoke._solver_stage_state",
        _solver,
    )
    result = run_cost_reduction_smoke(
        state=_smoke_state(),
        cfg=DesignOptimizationConfig(),
        dataset_npz_path=None,
        ndtha_step_count=16,
    )
    assert result["contract_pass"] is True
    assert result["reason_code"] == "PASS"
    assert result["summary"]["trial_action_available"] is True
    assert result["summary"]["solver_backend_static"] == "rocm_torch_hip_mainloop"


def test_cost_reduction_smoke_reports_no_action_when_mask_blocks(monkeypatch) -> None:
    state = _smoke_state()
    state["action_mask_extended"][:] = False

    def _solver(*, state, cfg, step_count):
        return {
            "violation_score": 0.0,
            "feasible": True,
            "max_dcr": 0.8,
            "max_drift_pct": 1.0,
            "residual_drift_pct": 0.2,
            "backend_static": "rocm_torch_hip_mainloop",
            "backend_ndtha": "rocm_torch_hip_mainloop",
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_cost_reduction_smoke._solver_stage_state",
        _solver,
    )
    result = run_cost_reduction_smoke(
        state=state,
        cfg=DesignOptimizationConfig(),
        dataset_npz_path=None,
        ndtha_step_count=16,
    )
    assert result["contract_pass"] is False
    assert result["reason_code"] == "ERR_NO_SMOKE_ACTION"
    assert result["summary"]["trial_action_available"] is False


def test_cost_reduction_smoke_cli_runs_without_pythonpath(tmp_path: Path) -> None:
    out = tmp_path / "design_optimization_cost_reduction_smoke_report.json"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--ndtha-step-count", "1", "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["run_id"] == "phase1-design-optimization-cost-reduction-smoke"
    assert payload["reason_code"] in {"PASS", "ERR_CPU_BACKEND", "ERR_NO_SMOKE_ACTION"}
