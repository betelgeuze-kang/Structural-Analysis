from __future__ import annotations

import pytest

from implementation.phase1.run_ndtha_residual_gate import run_ndtha_residual_gate


def _base_report() -> dict:
    return {
        "contract_pass": True,
        "checks": {"no_collapse_detected": True, "solver_control_history_pass": True},
        "summary": {
            "solver_control_event_count_total": 2,
            "solver_control_nonconverged_step_total": 0,
            "solver_control_cutback_case_ids": ["C2"],
            "solver_control_recommended_dt_scale_min": 0.75,
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
            },
            {
                "case_id": "C2",
                "checks": {"collapsed": False},
                "summary": {
                    "residual_top_displacement_m": 0.4,
                    "residual_drift_ratio_pct": 1.5,
                    "raw_residual_top_displacement_m": 0.4,
                    "raw_residual_drift_ratio_pct": 1.5,
                    "residual_metric_source": "history_tail",
                    "residual_metric_fallback_used": True,
                    "solver_control": {
                        "event_history_available": True,
                        "event_count": 2,
                        "cutback_recommended_step_count": 1,
                        "nonconverged_step_count": 0,
                        "event_sequence_pass": True,
                        "next_run_control": {"recommended_dt_scale_min": 0.75},
                    },
                },
            },
        ],
    }


def test_ndtha_residual_gate_passes_hard_limits() -> None:
    report = run_ndtha_residual_gate(
        ndtha_report=_base_report(),
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
    )
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["residual_metric_trace_pass"] is True
    assert report["checks"]["solver_control_trace_pass"] is True
    assert report["checks"]["solver_control_rollup_pass"] is True
    assert report["checks"]["solver_control_event_sequence_pass"] is True
    assert report["summary"]["solver_control_event_count_total"] == 2
    assert report["summary"]["solver_control_cutback_case_ids"] == ["C2"]
    assert report["summary"]["solver_raw_ratio"] == 0.5
    assert report["summary"]["residual_metric_source_ratios"] == {"history_tail": 0.5, "solver_raw": 0.5}
    assert report["rows"][0]["normalized_residual"]["hard_max_ratio"] > 0.0


def test_ndtha_residual_gate_fails_hard_drift_limit() -> None:
    ndtha_report = _base_report()
    ndtha_report["rows"][1]["summary"]["residual_drift_ratio_pct"] = 12.5
    report = run_ndtha_residual_gate(
        ndtha_report=ndtha_report,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_RESIDUAL_HARD_LIMIT"
    assert report["checks"]["residual_drift_hard_pass"] is False


def test_ndtha_residual_gate_strict_recommended_is_release_hard_fail() -> None:
    ndtha_report = _base_report()
    ndtha_report["rows"][1]["summary"]["residual_drift_ratio_pct"] = 2.5
    report = run_ndtha_residual_gate(
        ndtha_report=ndtha_report,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
        strict_recommended_residual_hard_fail=True,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_RESIDUAL_RECOMMENDED_LIMIT"
    assert report["checks"]["residual_drift_hard_pass"] is True
    assert report["checks"]["strict_recommended_residual_pass"] is False


def test_ndtha_residual_gate_blocks_release_when_corrected_state_recompute_is_required() -> None:
    report = run_ndtha_residual_gate(
        ndtha_report=_base_report(),
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
        require_corrected_state_recompute=True,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_CORRECTED_STATE_RECOMPUTE"
    assert report["summary"]["corrected_state_recompute_present_count"] == 0


@pytest.mark.parametrize("key", ["corrected_state_recompute", "gnn_corrected_state_recompute"])
@pytest.mark.parametrize("reported_value", [None, float("nan"), float("inf"), "0.1", True, 0.1])
def test_self_declared_recompute_cannot_bypass_missing_solver_verifier(key: str, reported_value: object) -> None:
    ndtha_report = _base_report()
    for row in ndtha_report["rows"]:
        row["summary"][key] = {
            "contract_pass": True,
            "pass": True,
            "source": "solver_corrected_state_recompute",
            "solver_recomputed": True,
            "provenance_verified": True,
            "verification_status": "verified",
            "receipt": {"status": "pass", "source_sha": "a" * 40, "corrected_state_sha256": "b" * 64},
            "residual_top_displacement_m": reported_value,
            "residual_drift_ratio_pct": 0.2,
        }

    report = run_ndtha_residual_gate(
        ndtha_report=ndtha_report,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
        require_corrected_state_recompute=True,
    )

    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_CORRECTED_STATE_RECOMPUTE"
    assert report["summary"]["corrected_state_recompute_present_count"] == 2
    assert report["summary"]["corrected_state_recompute_pass_count"] == 0
    corrected = report["rows"][0]["corrected_state_recompute"]
    assert corrected["declared_pass"] is True
    assert corrected["pass"] is False
    assert corrected["provenance_verified"] is False
    assert corrected["verification_status"] == "unavailable"
    assert corrected["residual_top_displacement_m"] is None
    assert corrected["residual_drift_ratio_pct"] is None
    assert "corrected_state_recompute_verifier_not_implemented" in corrected["blockers"]
    if type(reported_value) is float and reported_value == 0.1:
        assert corrected["reported_metrics_finite"] is True
        assert corrected["reported_residual_top_displacement_m"] == 0.1
    else:
        assert corrected["reported_metrics_finite"] is False
        assert corrected["reported_residual_top_displacement_m"] is None
        assert "corrected_state_metrics_missing_or_non_finite" in corrected["blockers"]


def test_ndtha_residual_gate_fails_missing_solver_control_trace() -> None:
    ndtha_report = _base_report()
    ndtha_report["checks"]["solver_control_history_pass"] = False
    ndtha_report["summary"].pop("solver_control_event_count_total")
    ndtha_report["summary"].pop("solver_control_nonconverged_step_total")
    ndtha_report["summary"].pop("solver_control_cutback_case_ids")
    ndtha_report["summary"].pop("solver_control_recommended_dt_scale_min")
    ndtha_report["rows"][0]["summary"].pop("solver_control")
    ndtha_report["rows"][1]["summary"].pop("solver_control")
    report = run_ndtha_residual_gate(
        ndtha_report=ndtha_report,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_SOLVER_CONTROL_TRACE"
    assert report["checks"]["solver_control_trace_pass"] is False


def test_ndtha_residual_gate_fails_nonconverged_solver_control_sequence() -> None:
    ndtha_report = _base_report()
    ndtha_report["summary"]["solver_control_nonconverged_step_total"] = 1
    ndtha_report["rows"][1]["summary"]["solver_control"]["nonconverged_step_count"] = 1
    ndtha_report["rows"][1]["summary"]["solver_control"]["event_sequence_pass"] = False
    report = run_ndtha_residual_gate(
        ndtha_report=ndtha_report,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
    )
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_SOLVER_CONTROL_LIMIT"
    assert report["checks"]["solver_control_event_sequence_pass"] is False


def test_ndtha_residual_gate_uses_steps_head_fallback_for_solver_control_trace() -> None:
    ndtha_report = _base_report()
    ndtha_report["rows"][0]["summary"].pop("solver_control")
    ndtha_report["rows"][0]["steps_head"] = [
        {
            "status": "OK",
            "converged": True,
            "solver_event": "",
            "recommended_dt_scale": 1.0,
        }
    ]
    report = run_ndtha_residual_gate(
        ndtha_report=ndtha_report,
        max_residual_top_displacement_m=5.0,
        max_residual_drift_ratio_pct=10.0,
        recommended_residual_top_displacement_m=1.0,
        recommended_residual_drift_ratio_pct=2.0,
        max_fallback_rate=1.0,
    )
    assert report["contract_pass"] is True
    assert report["rows"][0]["solver_control_trace_source"] == "steps_head_fallback"
