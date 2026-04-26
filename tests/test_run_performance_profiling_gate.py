from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_performance_profiling_gate_generates_expected_outputs(tmp_path: Path) -> None:
    p0 = tmp_path / "p0_engine_perf_report.json"
    gpu = tmp_path / "gpu_bottleneck_audit_report.json"
    ndtha = tmp_path / "ndtha_long_profile_report.json"
    track = tmp_path / "track_lf_solver_report.json"
    moving = tmp_path / "moving_load_integrator_report.json"
    moving_large = tmp_path / "moving_load_integrator_large_report.json"
    moving_xlarge = tmp_path / "moving_load_integrator_xlarge_report.json"
    vti = tmp_path / "vti_coupled_solver_report.json"
    vti_sweep = tmp_path / "vti_contact_window_variant_sweep_report.json"
    ssi = tmp_path / "ssi_boundary_gate_report.json"
    contact = tmp_path / "contact_readiness_report.json"
    foundation = tmp_path / "foundation_soil_link_gate_report.json"
    hip = tmp_path / "solver_hip_e2e_contract_report.json"
    out = tmp_path / "performance_profiling_gate_report.json"
    bottleneck_md = tmp_path / "performance_bottleneck_map.md"
    sprint_json = tmp_path / "performance_optimization_sprint_targets.json"
    sprint_md = tmp_path / "performance_optimization_sprint_targets.md"

    _write_json(
        p0,
        {
            "contract_pass": True,
            "performance": {
                "zero_copy_timing_breakdown_seconds": {"compute": 1.2, "copy": 0.0},
            },
        },
    )
    _write_json(
        gpu,
        {
            "contract_pass": True,
            "remaining_unavoidable_host_ops": ["csv_artifact_ingest", "report_generation_json_io"],
            "remaining_optimizable_host_ops": [],
        },
    )
    _write_json(
        ndtha,
        {
            "contract_pass": True,
            "summary": {
                "elapsed_wall_s_mean": 103.192538948,
                "elapsed_wall_s_cov": 0.0030221758,
                "peak_vram_mb_mean": 0.0,
                "step_wall_seconds_mean": 102.95,
                "halo_exchange_seconds_mean": 0.181,
                "retry_overhead_seconds_mean": 0.012,
                "retry_attempt_count_mean": 0.0,
                "retry_attempts_per_completed_step_mean": 0.0,
            },
        },
    )
    _write_json(
        track,
        {
            "contract_pass": True,
            "benchmarks": {
                "euler": {"elapsed_seconds": 1.303590091, "warmup_elapsed_seconds": 1.302, "steady_state_elapsed_seconds": 0.001590091},
                "timoshenko": {"elapsed_seconds": 0.000720452, "warmup_elapsed_seconds": 0.000420452, "steady_state_elapsed_seconds": 0.0003},
            },
            "performance_profile": {},
        },
    )
    _write_json(
        moving,
        {
            "contract_pass": True,
            "metrics": {
                "residual_ratio": 1.2149377974e-13,
                "max_residual": 2.7538590075e-08,
                "elapsed_seconds": 0.619,
                "time_steps_per_second": 775.0,
            },
        },
    )
    _write_json(
        moving_large,
        {
            "contract_pass": True,
            "metrics": {
                "elapsed_seconds": 1.226,
                "time_steps_per_second": 391.4,
                "cached_track_solve_inverse_enabled": True,
            },
        },
    )
    _write_json(
        moving_xlarge,
        {
            "contract_pass": True,
            "metrics": {
                "elapsed_seconds": 2.464,
                "time_steps_per_second": 194.8,
                "cached_track_solve_inverse_enabled": True,
            },
        },
    )
    _write_json(
        vti,
        {
            "contract_pass": True,
            "metrics": {
                "step_count": 160,
                "mean_coupling_iters": 1.64375,
                "adaptive_newton_call_count": 1052,
                "adaptive_newton_avg_iterations": 1.0846007604,
                "broadphase_pair_count_total": 1280,
                "broadphase_candidate_pair_count_total": 992,
                "broadphase_rejected_pair_count_total": 288,
                "broadphase_candidate_pair_ratio": 0.775,
                "broadphase_rejected_pair_ratio": 0.225,
            },
        },
    )
    _write_json(
        vti_sweep,
        {
            "contract_pass": True,
            "summary": {
                "variant_count": 4,
                "pass_count": 4,
                "zero_gap_positive_count": 4,
                "retained_force_positive_count": 0,
                "track_static_pruned_positive_count": 4,
                "stable_zero_gap_skip_ratio_min": 1.0,
                "stable_zero_gap_skip_ratio_max": 1.0,
                "track_static_pruned_ratio_min": 0.21,
                "track_static_pruned_ratio_max": 0.46,
            },
        },
    )
    _write_json(
        ssi,
        {
            "contract_pass": True,
            "summary": {"residual_settle_case_count": 4},
        },
    )
    _write_json(
        contact,
        {
            "contract_pass": True,
            "solver_evidence": {"converged_ratio": 0.99375},
        },
    )
    _write_json(foundation, {"contract_pass": True})
    _write_json(
        hip,
        {
            "contract_pass": True,
            "summary": {"hip_kernel_invocation_count_total": 848},
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/run_performance_profiling_gate.py",
        "--p0-engine-perf-report",
        str(p0),
        "--gpu-bottleneck-audit-report",
        str(gpu),
        "--ndtha-long-profile-report",
        str(ndtha),
        "--track-lf-solver-report",
        str(track),
        "--moving-load-integrator-report",
        str(moving),
        "--moving-load-integrator-large-report",
        str(moving_large),
        "--moving-load-integrator-xlarge-report",
        str(moving_xlarge),
        "--vti-coupled-solver-report",
        str(vti),
        "--vti-contact-window-variant-sweep-report",
        str(vti_sweep),
        "--ssi-boundary-report",
        str(ssi),
        "--contact-readiness-report",
        str(contact),
        "--foundation-soil-link-report",
        str(foundation),
        "--solver-hip-e2e-report",
        str(hip),
        "--bottleneck-map-md",
        str(bottleneck_md),
        "--sprint-targets-json",
        str(sprint_json),
        "--sprint-targets-md",
        str(sprint_md),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=Path.cwd())
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    sprint_targets = json.loads(sprint_json.read_text(encoding="utf-8"))

    assert report["contract_pass"] is True
    assert report["summary_line"].startswith("Performance profiling: PASS")
    assert report["summary"]["ndtha_halo_exchange_seconds_mean"] == 0.181
    assert report["summary"]["ssi_broadphase_candidate_pair_count_total"] == 992
    assert report["summary"]["moving_load_track_euler_warmup_elapsed_seconds"] == 1.302
    assert report["summary"]["moving_load_track_timoshenko_steady_state_elapsed_seconds"] == 0.0003
    assert report["summary"]["ssi_variant_sweep_pass_count"] == 4
    assert report["summary"]["moving_load_large_elapsed_seconds"] == 1.226
    assert report["summary"]["moving_load_xlarge_elapsed_seconds"] == 2.464
    assert "sweep=4/4" in report["summary_line"]
    assert "scale=0.619/1.226/2.464s" in report["summary_line"]
    assert len(report["bottleneck_map"]) == 3
    assert len(report["sprint_targets"]) == 3
    assert sprint_targets["summary_line"] == report["summary_line"]
    assert [item["target_id"] for item in report["sprint_targets"]] == [
        "ndtha_partitioned_runtime",
        "ssi_contact_convergence_path",
        "moving_load_kernel_warmup_observability",
    ]
    assert "Performance Bottleneck Map" in bottleneck_md.read_text(encoding="utf-8")
    assert "NDTHA halo exchange mean" in bottleneck_md.read_text(encoding="utf-8")
    assert "SSI/contact candidate pairs" in bottleneck_md.read_text(encoding="utf-8")
    assert "First Optimization Sprint Targets" in sprint_md.read_text(encoding="utf-8")
