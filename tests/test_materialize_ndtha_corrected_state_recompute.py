from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from implementation.phase1.run_ndtha_residual_gate import run_ndtha_residual_gate


SCRIPT = Path("scripts/materialize_ndtha_corrected_state_recompute.py")
SPEC = importlib.util.spec_from_file_location("materialize_ndtha_corrected_state_recompute", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _ndtha_report() -> dict:
    return {
        "contract_pass": True,
        "checks": {"no_collapse_detected": True, "solver_control_history_pass": True},
        "summary": {
            "solver_control_event_count_total": 0,
            "solver_control_nonconverged_step_total": 0,
            "solver_control_cutback_case_ids": [],
            "solver_control_recommended_dt_scale_min": 1.0,
        },
        "rows": [
            {
                "case_id": "C1",
                "checks": {"collapsed": False},
                "summary": {
                    "residual_top_displacement_m": 0.2,
                    "residual_drift_ratio_pct": 0.8,
                    "raw_residual_top_displacement_m": 0.2,
                    "raw_residual_drift_ratio_pct": 0.8,
                    "residual_metric_source": "solver_raw",
                    "residual_metric_fallback_used": False,
                    "solver_control": {
                        "event_history_available": True,
                        "event_count": 0,
                        "cutback_recommended_step_count": 0,
                        "nonconverged_step_count": 0,
                        "event_sequence_pass": True,
                        "next_run_control": {"recommended_dt_scale_min": 1.0},
                    },
                },
            }
        ],
    }


def test_heuristic_proposal_cannot_satisfy_corrected_state_recompute_gate() -> None:
    original = _ndtha_report()
    patched, sidecar = MODULE.materialize(
        ndtha_report=original,
        recommended_top_m=1.0,
        recommended_drift_pct=2.0,
        min_reduction_ratio=0.5,
    )

    assert sidecar["contract_pass"] is False
    assert sidecar["reason_code"] == "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE"
    assert sidecar["checks"]["full_fe_rerun_claimed"] is False
    recompute = patched["rows"][0]["summary"]["gnn_corrected_state_recompute"]
    assert recompute["contract_pass"] is False
    assert recompute["source"] == "gnn_residual_model_row_heuristic_proposal"
    assert recompute["residual_metric_source"] == "unavailable"
    assert recompute["original_residual_metric_source"] == "solver_raw"
    assert recompute["residual_top_displacement_m"] is None
    assert recompute["residual_drift_ratio_pct"] is None
    assert recompute["residual_reduction_ratio"] is None
    assert recompute["physical_accuracy_pct"] is None
    assert recompute["heuristic_state_reduction_ratio"] > 0.5
    assert "gnn_corrected_state_recompute" not in original["rows"][0]["summary"]
    assert patched["rows"][0]["summary"]["residual_top_displacement_m"] == 0.2
    assert sidecar["summary"]["corrected_residual_top_displacement_m_max_abs"] is None
    assert patched["summary"]["gnn_corrected_state_residual_drift_ratio_pct_max_abs"] is None
    json.dumps(sidecar, allow_nan=False)

    gate = run_ndtha_residual_gate(
        ndtha_report=patched,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=0.05,
        strict_recommended_residual_hard_fail=True,
        require_corrected_state_recompute=True,
    )
    assert gate["contract_pass"] is False
    assert gate["checks"]["corrected_state_recompute_pass"] is False
    assert gate["summary"]["corrected_state_recompute_pass_count"] == 0


def test_materialize_recompute_cli_writes_patched_report_and_sidecar(tmp_path: Path) -> None:
    ndtha = tmp_path / "ndtha.json"
    out = tmp_path / "ndtha.corrected.json"
    sidecar = tmp_path / "sidecar.json"
    ndtha.write_text(json.dumps(_ndtha_report(), ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ndtha-stress",
            str(ndtha),
            "--out",
            str(out),
            "--sidecar-out",
            str(sidecar),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stderr
    assert json.loads(sidecar.read_text(encoding="utf-8"))["contract_pass"] is False
    patched = json.loads(out.read_text(encoding="utf-8"))
    assert patched["summary"]["gnn_corrected_state_recompute_pass_count"] == 0


@pytest.mark.parametrize("spoof_finite_values", [False, True])
def test_heuristic_contract_pass_edit_does_not_promote_corrected_state(spoof_finite_values: bool) -> None:
    patched, _ = MODULE.materialize(
        ndtha_report=_ndtha_report(),
        recommended_top_m=1.0,
        recommended_drift_pct=2.0,
        min_reduction_ratio=0.5,
    )
    recompute = patched["rows"][0]["summary"]["gnn_corrected_state_recompute"]
    recompute["contract_pass"] = True
    if spoof_finite_values:
        recompute["residual_top_displacement_m"] = 0.1
        recompute["residual_drift_ratio_pct"] = 0.2
        recompute["solver_recomputed"] = True

    gate = run_ndtha_residual_gate(
        ndtha_report=patched,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=0.05,
        require_corrected_state_recompute=True,
    )

    assert gate["contract_pass"] is False
    assert gate["reason_code"] == "ERR_CORRECTED_STATE_RECOMPUTE"
    assert gate["summary"]["corrected_state_recompute_pass_count"] == 0
    corrected = gate["rows"][0]["corrected_state_recompute"]
    assert corrected["pass"] is False
    assert "heuristic_is_not_solver_recompute" in corrected["blockers"]
    assert "corrected_state_recompute_verifier_not_implemented" in corrected["blockers"]
