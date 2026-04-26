from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from implementation.phase1.run_design_optimization_solver_loop_long import main


def test_long_runner_writes_report(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.npz"
    report_path = tmp_path / "long_report.json"
    state_path = tmp_path / "long_state.npz"
    np.savez_compressed(dataset_path, dummy=np.asarray([1.0], dtype=np.float64))

    def _aggregate_group_state(dataset):
        return {
            "group_ids": np.asarray(["G0"], dtype="<U8"),
            "rebar_ratio": np.asarray([0.02], dtype=np.float64),
            "max_dcr": np.asarray([0.95], dtype=np.float64),
            "congestion": np.asarray([0.20], dtype=np.float64),
            "lap_splice": np.asarray([0.10], dtype=np.float64),
            "anchorage": np.asarray([0.25], dtype=np.float64),
            "detailing": np.asarray([0.30], dtype=np.float64),
            "group_cost_proxy": np.asarray([1200.0], dtype=np.float64),
            "member_type": np.asarray(["column"], dtype="<U16"),
            "zone_label": np.asarray(["core"], dtype="<U16"),
            "semantic_group": np.asarray(["CORE"], dtype="<U16"),
            "story_band": np.asarray([0], dtype=np.int32),
            "repair_influence": np.asarray([1.10], dtype=np.float64),
            "combination_match_score": np.asarray([0.92], dtype=np.float64),
            "combination_risk": np.asarray([1.05], dtype=np.float64),
            "global_drift_pct": np.asarray([1.2], dtype=np.float64),
            "global_residual_drift_pct": np.asarray([0.2], dtype=np.float64),
            "action_mask": np.asarray([[True, True]], dtype=np.bool_),
        }

    def _run_solver_constrained_loop(**kwargs):
        state = kwargs["state"]
        return {
            "baseline_solver": {
                "violation_score": 10.0,
                "max_drift_pct": 1.2,
                "residual_drift_pct": 0.2,
                "max_dcr": 1.05,
                "backend_static": "rocm_torch_hip_mainloop",
                "backend_ndtha": "rocm_torch_hip_mainloop",
                "feasible": False,
                "cost_proxy": 1200.0,
            },
            "final_solver": {
                "violation_score": 5.0,
                "max_drift_pct": 1.1,
                "residual_drift_pct": 0.18,
                "max_dcr": 0.98,
                "backend_static": "rocm_torch_hip_mainloop",
                "backend_ndtha": "rocm_torch_hip_mainloop",
                "feasible": True,
                "cost_proxy": 1210.0,
            },
            "final_state": state,
            "accepted_stage1": [{"group_index": 0}],
            "accepted_stage1_extra": [],
            "accepted_stage1_dcr": [],
            "accepted_stage2": [],
            "proposed_stage1": [{"group_index": 0}],
            "proposed_stage2": [],
            "baseline_cost_proxy": 1200.0,
            "final_cost_proxy": 1210.0,
            "cost_reduction_proxy": -10.0,
            "baseline_violation_score_heuristic": 12.0,
            "final_violation_score_heuristic": 4.0,
        }

    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_solver_loop_long.aggregate_group_state",
        _aggregate_group_state,
    )
    monkeypatch.setattr(
        "implementation.phase1.run_design_optimization_solver_loop_long.run_solver_constrained_loop",
        _run_solver_constrained_loop,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_design_optimization_solver_loop_long.py",
            "--dataset-npz",
            str(dataset_path),
            "--out",
            str(report_path),
            "--state-out",
            str(state_path),
        ],
    )

    main()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "long_budget"
    assert "mode" not in payload["summary"]
    assert payload["summary"]["solver_feasible_final"] is True
    assert state_path.exists()
