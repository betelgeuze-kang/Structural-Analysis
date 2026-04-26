from __future__ import annotations

import numpy as np

from implementation.phase1.run_nonlinear_ndtha_stress import (
    _build_ndtha_solver_control_summary,
    _run_ndtha_case,
    _sanitize_ndtha_residual_metrics,
)
from implementation.phase1.rust_nonlinear_frame_bridge import RustNonlinearFrameConfig


def test_sanitize_ndtha_residual_metrics_falls_back_to_history_tail() -> None:
    out = _sanitize_ndtha_residual_metrics(
        raw_top_m=2.1e48,
        raw_drift_pct=5.9e48,
        top_history_m=[0.0, 0.012, 0.021],
        drift_history_pct=[0.0, 0.15, 0.22],
        final_story_drift_pct=[0.18, 0.22, 0.11],
        collapsed=False,
        collapse_top_m=0.0,
        collapse_drift_pct=0.0,
        collapse_drift_threshold_pct=10.0,
    )
    assert out["residual_metric_fallback_used"] is True
    assert out["residual_metric_source"] == "history_tail"
    assert abs(float(out["residual_top_displacement_m"]) - 0.021) < 1e-12
    assert abs(float(out["residual_drift_ratio_pct"]) - 0.22) < 1e-12


def test_run_ndtha_case_sanitizes_absurd_solver_residuals(monkeypatch) -> None:
    def _fake_solver(**_kwargs):
        return {
            "backend": "rust_ffi_nonlinear_frame_ndtha",
            "status": 0,
            "converged_all_steps": True,
            "rust_backend_all_steps": True,
            "collapsed": False,
            "collapse_step": -1,
            "collapse_time_s": 0.0,
            "collapse_drift_ratio_pct": 0.0,
            "collapse_top_displacement_m": 0.0,
            "step_count_completed": 3,
            "max_plastic_story_count": 4,
            "max_drift_ratio_pct": 0.22,
            "avg_step_iterations": 5.0,
            "residual_pre_settle_top_displacement_m": 0.75,
            "residual_pre_settle_drift_ratio_pct": 2.6,
            "residual_top_displacement_m": 3.0e30,
            "residual_drift_ratio_pct": 7.0e30,
            "residual_settle_applied": True,
            "residual_settle_steps": 32,
            "response": {
                "top_displacement_m": [0.0, 0.01, 0.015],
                "drift_ratio_pct": [0.0, 0.12, 0.18],
                "base_shear_kN": [0.0, 100.0, 110.0],
                "core_drift_pct": [0.0, 0.09, 0.14],
                "core_shear_kN": [0.0, 40.0, 45.0],
                "step_converged": [True, True, True],
                "step_iterations": [4, 5, 6],
                "step_plastic_story_count": [1, 3, 4],
                "step_residual_inf": [1e-6, 2e-6, 2e-6],
                "story_drift_envelope_pct": [0.10, 0.18],
                "final_story_drift_pct": [0.11, 0.17],
            },
        }

    monkeypatch.setattr(
        "implementation.phase1.run_nonlinear_ndtha_stress.solve_nonlinear_frame_ndtha",
        _fake_solver,
    )

    out = _run_ndtha_case(
        rust_cfg=RustNonlinearFrameConfig(
            tolerance=1e-5,
            max_iter=20,
            hardening_ratio=0.2,
            pdelta_factor=1.0,
        ),
        story_k=np.asarray([2.0e6, 1.8e6], dtype=np.float64),
        story_h=np.asarray([3.2, 3.2], dtype=np.float64),
        story_p=np.asarray([1.0e6, 0.8e6], dtype=np.float64),
        story_yield_drift=np.asarray([0.01, 0.01], dtype=np.float64),
        story_mass=np.asarray([2.0e5, 1.8e5], dtype=np.float64),
        story_damp=np.asarray([1.0e3, 1.0e3], dtype=np.float64),
        floor_load_base=np.asarray([1.0e5, 2.0e5], dtype=np.float64),
        ag=np.asarray([0.0, 0.1, -0.1], dtype=np.float64),
        dt=0.01,
        beta=0.25,
        gamma=0.5,
        max_step_iterations=8,
        step_tol=1e-4,
        adaptive_load_decay=0.82,
        damping_force_cap_ratio=0.6,
        collapse_drift_threshold_pct=10.0,
    )

    assert out["residual_metric_fallback_used"] is True
    assert out["residual_metric_source"] == "history_tail"
    assert abs(float(out["residual_top_displacement_m"]) - 0.015) < 1e-12
    assert abs(float(out["residual_drift_ratio_pct"]) - 0.17) < 1e-12
    assert abs(float(out["residual_pre_settle_top_displacement_m"]) - 0.75) < 1e-12
    assert abs(float(out["residual_pre_settle_drift_ratio_pct"]) - 2.6) < 1e-12
    assert out["residual_settle_applied"] is True
    assert int(out["residual_settle_steps"]) == 32
    assert float(out["raw_residual_top_displacement_m"]) > 1.0e20
    solver_control = out["solver_control"]
    assert int(solver_control["event_count"]) >= 1
    assert int(solver_control["cutback_recommended_step_count"]) >= 1
    assert solver_control["event_history_available"] is True
    assert float((solver_control["next_run_control"] or {})["recommended_dt_scale_min"]) <= 0.75


def test_build_ndtha_solver_control_summary_marks_nonconverged_and_plastic_events() -> None:
    out = _build_ndtha_solver_control_summary(
        step_conv=np.asarray([True, False, True, True], dtype=np.bool_),
        step_iters=np.asarray([4, 8, 7, 3], dtype=np.int32),
        step_plastic=np.asarray([0, 1, 3, 3], dtype=np.int32),
        step_resid=np.asarray([1.0e-6, 5.0e-2, 3.0e-3, 5.0e-7], dtype=np.float64),
        dt=0.02,
        max_step_iterations=8,
        step_tol=1.0e-4,
        adaptive_load_decay=0.82,
        collapsed=False,
        collapse_step=-1,
    )

    assert out["event_history_available"] is True
    assert int(out["nonconverged_step_count"]) == 1
    assert int(out["cutback_recommended_step_count"]) >= 2
    assert int(out["plastic_transition_step_count"]) == 2
    assert float((out["next_run_control"] or {})["recommended_dt_scale_min"]) <= 0.5
    events = [str(row.get("event", "")) for row in out["event_history_head"]]
    assert "step_nonconverged" in events


def test_run_ndtha_case_reruns_host_response_when_device_series_is_empty(monkeypatch) -> None:
    calls: list[bool] = []

    def _fake_solver(*, keep_device_artifacts=False, **_kwargs):
        calls.append(bool(keep_device_artifacts))
        if keep_device_artifacts:
            return {
                "backend": "rust_ffi_nonlinear_frame_ndtha",
                "status": 0,
                "converged_all_steps": True,
                "rust_backend_all_steps": True,
                "collapsed": False,
                "collapse_step": -1,
                "collapse_time_s": 0.0,
                "collapse_drift_ratio_pct": 0.0,
                "collapse_top_displacement_m": 0.0,
                "step_count_completed": 3,
                "max_plastic_story_count": 2,
                "max_drift_ratio_pct": 0.18,
                "avg_step_iterations": 4.0,
                "residual_pre_settle_top_displacement_m": 0.1,
                "residual_pre_settle_drift_ratio_pct": 0.2,
                "residual_top_displacement_m": 0.015,
                "residual_drift_ratio_pct": 0.17,
                "residual_settle_applied": False,
                "residual_settle_steps": 0,
                "device_artifacts_available": True,
                "device_artifacts": {"broken": object()},
            }
        return {
            "backend": "rust_ffi_nonlinear_frame_ndtha",
            "status": 0,
            "converged_all_steps": True,
            "rust_backend_all_steps": True,
            "collapsed": False,
            "collapse_step": -1,
            "collapse_time_s": 0.0,
            "collapse_drift_ratio_pct": 0.0,
            "collapse_top_displacement_m": 0.0,
            "step_count_completed": 3,
            "max_plastic_story_count": 2,
            "max_drift_ratio_pct": 0.18,
            "avg_step_iterations": 4.0,
            "residual_pre_settle_top_displacement_m": 0.1,
            "residual_pre_settle_drift_ratio_pct": 0.2,
            "residual_top_displacement_m": 0.015,
            "residual_drift_ratio_pct": 0.17,
            "residual_settle_applied": False,
            "residual_settle_steps": 0,
            "response": {
                "top_displacement_m": [0.0, 0.01, 0.015],
                "drift_ratio_pct": [0.0, 0.12, 0.18],
                "base_shear_kN": [0.0, 100.0, 110.0],
                "core_drift_pct": [0.0, 0.09, 0.14],
                "core_shear_kN": [0.0, 40.0, 45.0],
                "step_converged": [True, True, True],
                "step_iterations": [3, 4, 5],
                "step_plastic_story_count": [0, 1, 2],
                "step_residual_inf": [1e-6, 1e-6, 2e-6],
                "story_drift_envelope_pct": [0.10, 0.18],
                "final_story_drift_pct": [0.11, 0.17],
            },
        }

    monkeypatch.setattr(
        "implementation.phase1.run_nonlinear_ndtha_stress.solve_nonlinear_frame_ndtha",
        _fake_solver,
    )
    monkeypatch.setattr(
        "implementation.phase1.run_nonlinear_ndtha_stress.consume_dlpack_bundle",
        lambda _artifacts: (_ for _ in ()).throw(RuntimeError("dlpack unavailable")),
    )

    out = _run_ndtha_case(
        rust_cfg=RustNonlinearFrameConfig(
            tolerance=1e-5,
            max_iter=20,
            hardening_ratio=0.2,
            pdelta_factor=1.0,
        ),
        story_k=np.asarray([2.0e6, 1.8e6], dtype=np.float64),
        story_h=np.asarray([3.2, 3.2], dtype=np.float64),
        story_p=np.asarray([1.0e6, 0.8e6], dtype=np.float64),
        story_yield_drift=np.asarray([0.01, 0.01], dtype=np.float64),
        story_mass=np.asarray([2.0e5, 1.8e5], dtype=np.float64),
        story_damp=np.asarray([1.0e3, 1.0e3], dtype=np.float64),
        floor_load_base=np.asarray([1.0e5, 2.0e5], dtype=np.float64),
        ag=np.asarray([0.0, 0.1, -0.1], dtype=np.float64),
        dt=0.01,
        beta=0.25,
        gamma=0.5,
        max_step_iterations=8,
        step_tol=1e-4,
        adaptive_load_decay=0.82,
        damping_force_cap_ratio=0.6,
        collapse_drift_threshold_pct=10.0,
    )

    assert calls == [True, False]
    assert out["response_device_consumer"] == "host_response_rerun"
    assert out["response_full_step_count"] == 3
    assert len(out["response_artifact_data"]["time_s"]) == 3
    assert len(out["response_artifact_data"]["top_velocity_mps"]) == 3
    assert len(out["response"]["ground_acceleration_g"]) == 3
