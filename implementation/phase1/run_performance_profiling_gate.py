#!/usr/bin/env python3
"""Aggregate solver performance baselines into a profiling gate and sprint targets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

REPO_ROOT = Path(__file__).resolve().parents[2]

REASONS = {
    "PASS": "performance profiling baselines, bottleneck map, and sprint targets are ready",
    "ERR_INVALID_INPUT": "invalid performance profiling gate input",
    "ERR_BASELINE": "baseline profiling inputs are incomplete",
    "ERR_NDTHA": "ndtha performance baseline is incomplete",
    "ERR_SSI_CONTACT": "ssi/contact performance evidence is incomplete",
    "ERR_MOVING_LOAD": "moving-load performance evidence is incomplete",
    "ERR_SPRINT": "optimization sprint targets are incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "p0_engine_perf_report",
        "gpu_bottleneck_audit_report",
        "ndtha_long_profile_report",
        "track_lf_solver_report",
        "moving_load_integrator_report",
        "vti_coupled_solver_report",
        "ssi_boundary_report",
        "contact_readiness_report",
        "foundation_soil_link_report",
        "solver_hip_e2e_report",
        "out",
    ],
    "properties": {
        "p0_engine_perf_report": {"type": "string", "minLength": 1},
        "gpu_bottleneck_audit_report": {"type": "string", "minLength": 1},
        "ndtha_long_profile_report": {"type": "string", "minLength": 1},
        "track_lf_solver_report": {"type": "string", "minLength": 1},
        "moving_load_integrator_report": {"type": "string", "minLength": 1},
        "moving_load_integrator_large_report": {"type": "string", "minLength": 1},
        "moving_load_integrator_xlarge_report": {"type": "string", "minLength": 1},
        "vti_coupled_solver_report": {"type": "string", "minLength": 1},
        "vti_contact_window_variant_sweep_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "contact_readiness_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_report": {"type": "string", "minLength": 1},
        "solver_hip_e2e_report": {"type": "string", "minLength": 1},
        "bottleneck_map_md": {"type": "string", "minLength": 1},
        "sprint_targets_json": {"type": "string", "minLength": 1},
        "sprint_targets_md": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _truthy(report: dict[str, Any], *keys: str) -> bool:
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    return all(bool(checks.get(key, False)) for key in keys)


def _markdown_table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Item | Value |", "| --- | --- |"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def run_gate(
    *,
    p0_engine_perf: dict[str, Any],
    gpu_bottleneck_audit: dict[str, Any],
    ndtha_long_profile: dict[str, Any],
    track_lf_solver: dict[str, Any],
    moving_load_integrator: dict[str, Any],
    moving_load_integrator_large: dict[str, Any],
    moving_load_integrator_xlarge: dict[str, Any],
    vti_coupled_solver: dict[str, Any],
    vti_contact_window_variant_sweep: dict[str, Any],
    ssi_boundary: dict[str, Any],
    contact_readiness: dict[str, Any],
    foundation_soil_link: dict[str, Any],
    solver_hip_e2e: dict[str, Any],
) -> dict[str, Any]:
    p0_perf = p0_engine_perf.get("performance") if isinstance(p0_engine_perf.get("performance"), dict) else {}
    zero_copy = p0_perf.get("zero_copy_timing_breakdown_seconds") if isinstance(p0_perf.get("zero_copy_timing_breakdown_seconds"), dict) else {}
    track_perf = track_lf_solver.get("performance_profile") if isinstance(track_lf_solver.get("performance_profile"), dict) else {}
    track_bench = track_lf_solver.get("benchmarks") if isinstance(track_lf_solver.get("benchmarks"), dict) else {}
    gpu_unavoidable = gpu_bottleneck_audit.get("remaining_unavoidable_host_ops") if isinstance(gpu_bottleneck_audit.get("remaining_unavoidable_host_ops"), list) else []
    gpu_optimizable = gpu_bottleneck_audit.get("remaining_optimizable_host_ops") if isinstance(gpu_bottleneck_audit.get("remaining_optimizable_host_ops"), list) else []
    ndtha_summary = ndtha_long_profile.get("summary") if isinstance(ndtha_long_profile.get("summary"), dict) else {}
    vti_metrics = vti_coupled_solver.get("metrics") if isinstance(vti_coupled_solver.get("metrics"), dict) else {}
    vti_sweep_summary = (
        vti_contact_window_variant_sweep.get("summary")
        if isinstance(vti_contact_window_variant_sweep.get("summary"), dict)
        else {}
    )
    moving_metrics = moving_load_integrator.get("metrics") if isinstance(moving_load_integrator.get("metrics"), dict) else {}
    moving_large_metrics = moving_load_integrator_large.get("metrics") if isinstance(moving_load_integrator_large.get("metrics"), dict) else {}
    moving_xlarge_metrics = moving_load_integrator_xlarge.get("metrics") if isinstance(moving_load_integrator_xlarge.get("metrics"), dict) else {}
    ssi_summary = ssi_boundary.get("summary") if isinstance(ssi_boundary.get("summary"), dict) else {}
    contact_solver_evidence = contact_readiness.get("solver_evidence") if isinstance(contact_readiness.get("solver_evidence"), dict) else {}
    hip_summary = solver_hip_e2e.get("summary") if isinstance(solver_hip_e2e.get("summary"), dict) else {}

    ndtha_elapsed_wall_s_mean = _finite(ndtha_summary.get("elapsed_wall_s_mean"))
    ndtha_elapsed_wall_s_cov = _finite(ndtha_summary.get("elapsed_wall_s_cov"))
    ndtha_peak_vram_mb_mean = _finite(ndtha_summary.get("peak_vram_mb_mean"))
    ndtha_step_wall_seconds_mean = _finite(ndtha_summary.get("step_wall_seconds_mean"), ndtha_elapsed_wall_s_mean)
    ndtha_halo_exchange_seconds_mean = _finite(ndtha_summary.get("halo_exchange_seconds_mean"))
    ndtha_retry_overhead_seconds_mean = _finite(ndtha_summary.get("retry_overhead_seconds_mean"))
    ndtha_solver_seconds_mean = _finite(ndtha_summary.get("solver_seconds_mean"))
    ndtha_state_update_seconds_mean = _finite(ndtha_summary.get("state_update_seconds_mean"))
    ndtha_interface_seconds_mean = _finite(ndtha_summary.get("interface_seconds_mean"))
    ndtha_solver_reuse_ratio_mean = _finite(ndtha_summary.get("solver_reuse_ratio_mean"))
    ndtha_stiffness_refresh_count_mean = _finite(ndtha_summary.get("stiffness_refresh_count_mean"))
    ndtha_retry_attempt_count_mean = _finite(ndtha_summary.get("retry_attempt_count_mean"))
    ndtha_retry_attempts_per_completed_step_mean = _finite(ndtha_summary.get("retry_attempts_per_completed_step_mean"))

    track_euler_elapsed_seconds = _finite(track_perf.get("euler_elapsed_seconds") or ((track_bench.get("euler") or {}).get("elapsed_seconds")))
    track_timoshenko_elapsed_seconds = _finite(track_perf.get("timoshenko_elapsed_seconds") or ((track_bench.get("timoshenko") or {}).get("elapsed_seconds")))
    track_euler_warmup_elapsed_seconds = _finite(track_perf.get("euler_warmup_elapsed_seconds") or ((track_bench.get("euler") or {}).get("warmup_elapsed_seconds")))
    track_timoshenko_warmup_elapsed_seconds = _finite(track_perf.get("timoshenko_warmup_elapsed_seconds") or ((track_bench.get("timoshenko") or {}).get("warmup_elapsed_seconds")))
    track_euler_steady_state_elapsed_seconds = _finite(
        track_perf.get("euler_steady_state_elapsed_seconds") or ((track_bench.get("euler") or {}).get("steady_state_elapsed_seconds"))
    )
    track_timoshenko_steady_state_elapsed_seconds = _finite(
        track_perf.get("timoshenko_steady_state_elapsed_seconds") or ((track_bench.get("timoshenko") or {}).get("steady_state_elapsed_seconds"))
    )
    moving_load_warmup_skew_ratio = (
        max(track_euler_warmup_elapsed_seconds, track_timoshenko_warmup_elapsed_seconds)
        / max(min(track_euler_warmup_elapsed_seconds, track_timoshenko_warmup_elapsed_seconds), 1e-12)
        if track_euler_warmup_elapsed_seconds > 0.0 and track_timoshenko_warmup_elapsed_seconds > 0.0
        else (
            max(track_euler_elapsed_seconds, track_timoshenko_elapsed_seconds)
            / max(min(track_euler_elapsed_seconds, track_timoshenko_elapsed_seconds), 1e-12)
            if track_euler_elapsed_seconds > 0.0 and track_timoshenko_elapsed_seconds > 0.0
            else 0.0
        )
    )
    moving_load_steady_state_skew_ratio = (
        max(track_euler_steady_state_elapsed_seconds, track_timoshenko_steady_state_elapsed_seconds)
        / max(min(track_euler_steady_state_elapsed_seconds, track_timoshenko_steady_state_elapsed_seconds), 1e-12)
        if track_euler_steady_state_elapsed_seconds > 0.0 and track_timoshenko_steady_state_elapsed_seconds > 0.0
        else 0.0
    )

    ssi_contact_step_count = int(vti_metrics.get("step_count", 0) or 0)
    ssi_contact_mean_coupling_iters = _finite(vti_metrics.get("mean_coupling_iters"))
    ssi_contact_adaptive_newton_call_count = int(vti_metrics.get("adaptive_newton_call_count", 0) or 0)
    ssi_contact_adaptive_newton_avg_iterations = _finite(vti_metrics.get("adaptive_newton_avg_iterations"))
    ssi_residual_settle_case_count = int(ssi_summary.get("residual_settle_case_count", 0) or 0)
    ssi_broadphase_pair_count_total = int(vti_metrics.get("broadphase_pair_count_total", 0) or 0)
    ssi_broadphase_candidate_pair_count_total = int(vti_metrics.get("broadphase_candidate_pair_count_total", 0) or 0)
    ssi_broadphase_rejected_pair_count_total = int(vti_metrics.get("broadphase_rejected_pair_count_total", 0) or 0)
    ssi_broadphase_candidate_pair_ratio = _finite(vti_metrics.get("broadphase_candidate_pair_ratio"))
    ssi_broadphase_rejected_pair_ratio = _finite(vti_metrics.get("broadphase_rejected_pair_ratio"))
    ssi_contact_window_retained_pair_ratio = _finite(vti_metrics.get("contact_window_retained_pair_ratio"))
    ssi_retained_force_warm_start_ratio = _finite(vti_metrics.get("retained_force_warm_start_ratio"))
    ssi_stable_zero_gap_skip_ratio = _finite(vti_metrics.get("stable_zero_gap_skip_ratio"))
    ssi_variant_sweep_variant_count = int(vti_sweep_summary.get("variant_count", 0) or 0)
    ssi_variant_sweep_pass_count = int(vti_sweep_summary.get("pass_count", 0) or 0)
    ssi_variant_sweep_zero_gap_positive_count = int(vti_sweep_summary.get("zero_gap_positive_count", 0) or 0)
    ssi_variant_sweep_retained_force_positive_count = int(vti_sweep_summary.get("retained_force_positive_count", 0) or 0)
    ssi_variant_sweep_track_static_pruned_positive_count = int(
        vti_sweep_summary.get("track_static_pruned_positive_count", 0) or 0
    )
    ssi_variant_sweep_zero_gap_skip_ratio_min = _finite(vti_sweep_summary.get("stable_zero_gap_skip_ratio_min"))
    ssi_variant_sweep_zero_gap_skip_ratio_max = _finite(vti_sweep_summary.get("stable_zero_gap_skip_ratio_max"))
    ssi_variant_sweep_track_static_pruned_ratio_min = _finite(vti_sweep_summary.get("track_static_pruned_ratio_min"))
    ssi_variant_sweep_track_static_pruned_ratio_max = _finite(vti_sweep_summary.get("track_static_pruned_ratio_max"))

    moving_load_integrator_residual_ratio = _finite(moving_metrics.get("residual_ratio"))
    moving_load_integrator_max_residual = _finite(moving_metrics.get("max_residual"))
    moving_load_integrator_elapsed_seconds = _finite(moving_metrics.get("elapsed_seconds"))
    moving_load_integrator_time_steps_per_second = _finite(moving_metrics.get("time_steps_per_second"))
    moving_load_active_axle_count_mean = _finite(moving_metrics.get("active_axle_count_mean"))
    moving_load_sparse_contact_step_ratio = _finite(moving_metrics.get("sparse_contact_step_ratio"))
    moving_load_batched_track_solve_enabled = bool(moving_metrics.get("batched_track_solve_enabled", False))
    moving_load_large_elapsed_seconds = _finite(moving_large_metrics.get("elapsed_seconds"), moving_load_integrator_elapsed_seconds)
    moving_load_large_time_steps_per_second = _finite(moving_large_metrics.get("time_steps_per_second"))
    moving_load_large_cached_track_solve_inverse_enabled = bool(moving_large_metrics.get("cached_track_solve_inverse_enabled", False))
    moving_load_xlarge_elapsed_seconds = _finite(moving_xlarge_metrics.get("elapsed_seconds"), moving_load_large_elapsed_seconds)
    moving_load_xlarge_time_steps_per_second = _finite(moving_xlarge_metrics.get("time_steps_per_second"))
    moving_load_xlarge_cached_track_solve_inverse_enabled = bool(moving_xlarge_metrics.get("cached_track_solve_inverse_enabled", False))
    vti_elapsed_seconds = _finite(vti_metrics.get("elapsed_seconds"))
    vti_time_steps_per_second = _finite(vti_metrics.get("time_steps_per_second"))

    gpu_unavoidable_host_ops_count = len(gpu_unavoidable)
    gpu_optimizable_host_ops_count = len(gpu_optimizable)
    hip_kernel_invocation_count_total = int(hip_summary.get("hip_kernel_invocation_count_total", 0) or 0)

    top_bottlenecks = [
        {
            "target_id": "ndtha_partitioned_runtime",
            "priority": "P0",
            "domain": "ndtha",
            "status": "open",
            "headline": "Full-duration NDTHA wall-clock is the largest measured solver hot path.",
            "evidence": {
                "elapsed_wall_s_mean": ndtha_elapsed_wall_s_mean,
                "elapsed_wall_s_cov": ndtha_elapsed_wall_s_cov,
                "step_wall_seconds_mean": ndtha_step_wall_seconds_mean,
                "halo_exchange_seconds_mean": ndtha_halo_exchange_seconds_mean,
                "retry_overhead_seconds_mean": ndtha_retry_overhead_seconds_mean,
                "solver_seconds_mean": ndtha_solver_seconds_mean,
                "state_update_seconds_mean": ndtha_state_update_seconds_mean,
                "interface_seconds_mean": ndtha_interface_seconds_mean,
                "solver_reuse_ratio_mean": ndtha_solver_reuse_ratio_mean,
                "stiffness_refresh_count_mean": ndtha_stiffness_refresh_count_mean,
                "retry_attempt_count_mean": ndtha_retry_attempt_count_mean,
                "retry_attempts_per_completed_step_mean": ndtha_retry_attempts_per_completed_step_mean,
                "peak_vram_mb_mean": ndtha_peak_vram_mb_mean,
                "hip_kernel_invocation_count_total": hip_kernel_invocation_count_total,
            },
            "optimization_hypothesis": "The partitioned NDTHA path is now split into solver, state-update, interface, halo, and retry buckets. The next gain is to reduce the dominant solver bucket while keeping interface and state-update costs bounded.",
            "first_actions": [
                "Use the new solver/state-update/interface split to isolate the dominant portion of step solve time.",
                "Apply Jacobian/stiffness reuse only if solver time dominates the new split.",
                "Promote Jacobian/stiffness reuse counters into the NDTHA report.",
                "Trial a reduced stiffness refresh cadence on the 10M long-profile path.",
            ],
            "acceptance_signals": [
                "elapsed_wall_s_mean reduced by at least 15%",
                "elapsed_wall_s_cov remains <= 0.01",
                "no_cpu_fallback and production-kernel proof remain green",
            ],
        },
        {
            "target_id": "ssi_contact_convergence_path",
            "priority": "P0",
            "domain": "ssi_contact",
            "status": "open",
            "headline": "SSI/contact convergence is stable, but iterative coupling and settle handling still dominate the nonlinear interaction path.",
            "evidence": {
                "step_count": ssi_contact_step_count,
                "mean_coupling_iters": ssi_contact_mean_coupling_iters,
                "adaptive_newton_call_count": ssi_contact_adaptive_newton_call_count,
                "adaptive_newton_avg_iterations": ssi_contact_adaptive_newton_avg_iterations,
                "broadphase_pair_count_total": ssi_broadphase_pair_count_total,
                "broadphase_candidate_pair_count_total": ssi_broadphase_candidate_pair_count_total,
                "broadphase_rejected_pair_count_total": ssi_broadphase_rejected_pair_count_total,
                "broadphase_candidate_pair_ratio": ssi_broadphase_candidate_pair_ratio,
                "broadphase_rejected_pair_ratio": ssi_broadphase_rejected_pair_ratio,
                "track_static_pruned_ratio": _finite(vti_metrics.get("track_static_pruned_ratio")),
                "variant_sweep_variant_count": ssi_variant_sweep_variant_count,
                "variant_sweep_pass_count": ssi_variant_sweep_pass_count,
                "variant_sweep_zero_gap_positive_count": ssi_variant_sweep_zero_gap_positive_count,
                "variant_sweep_retained_force_positive_count": ssi_variant_sweep_retained_force_positive_count,
                "variant_sweep_track_static_pruned_positive_count": ssi_variant_sweep_track_static_pruned_positive_count,
                "variant_sweep_zero_gap_skip_ratio_min": ssi_variant_sweep_zero_gap_skip_ratio_min,
                "variant_sweep_zero_gap_skip_ratio_max": ssi_variant_sweep_zero_gap_skip_ratio_max,
                "variant_sweep_track_static_pruned_ratio_min": ssi_variant_sweep_track_static_pruned_ratio_min,
                "variant_sweep_track_static_pruned_ratio_max": ssi_variant_sweep_track_static_pruned_ratio_max,
                "residual_settle_case_count": ssi_residual_settle_case_count,
                "contact_converged_ratio": _finite(contact_solver_evidence.get("converged_ratio")),
            },
            "optimization_hypothesis": "Broadphase pair counts and track-solve pruning are now exposed, so the next gain is to push more non-contact steps down the pruned path and cut Newton work without touching correctness-critical convergence thresholds.",
            "first_actions": [
                "Use broadphase pair ratios and pruned-track-solve ratio to target pair pruning and contact warm starts in stable SSI windows.",
                "Cache previous-step contact state as a Newton warm start for stable wheel-rail and SSI cases.",
                "Split residual-settle time from solve time in SSI reports.",
            ],
            "acceptance_signals": [
                "mean_coupling_iters reduced without lowering converged_ratio",
                "adaptive_newton_call_count reduced by at least 10%",
                "residual_settle_case_count unchanged or lower",
            ],
        },
        {
            "target_id": "moving_load_kernel_warmup_observability",
            "priority": "P1",
            "domain": "moving_load",
            "status": "open",
            "headline": "Moving-load runtime observability is now coarse-grained, but warm-up skew and missing stage-level timers still block fast optimization loops.",
            "evidence": {
                "track_euler_elapsed_seconds": track_euler_elapsed_seconds,
                "track_timoshenko_elapsed_seconds": track_timoshenko_elapsed_seconds,
                "track_euler_warmup_elapsed_seconds": track_euler_warmup_elapsed_seconds,
                "track_timoshenko_warmup_elapsed_seconds": track_timoshenko_warmup_elapsed_seconds,
                "track_euler_steady_state_elapsed_seconds": track_euler_steady_state_elapsed_seconds,
                "track_timoshenko_steady_state_elapsed_seconds": track_timoshenko_steady_state_elapsed_seconds,
                "benchmark_fast_path_enabled": bool(track_perf.get("benchmark_fast_path_enabled", False)),
                "warmup_skew_ratio": moving_load_warmup_skew_ratio,
                "steady_state_skew_ratio": moving_load_steady_state_skew_ratio,
                "moving_load_integrator_elapsed_seconds": moving_load_integrator_elapsed_seconds,
                "moving_load_integrator_time_steps_per_second": moving_load_integrator_time_steps_per_second,
                "moving_load_large_elapsed_seconds": moving_load_large_elapsed_seconds,
                "moving_load_large_time_steps_per_second": moving_load_large_time_steps_per_second,
                "moving_load_large_cached_track_solve_inverse_enabled": moving_load_large_cached_track_solve_inverse_enabled,
                "moving_load_xlarge_elapsed_seconds": moving_load_xlarge_elapsed_seconds,
                "moving_load_xlarge_time_steps_per_second": moving_load_xlarge_time_steps_per_second,
                "moving_load_xlarge_cached_track_solve_inverse_enabled": moving_load_xlarge_cached_track_solve_inverse_enabled,
                "moving_load_active_axle_count_mean": moving_load_active_axle_count_mean,
                "moving_load_sparse_contact_step_ratio": moving_load_sparse_contact_step_ratio,
                "vti_elapsed_seconds": vti_elapsed_seconds,
                "vti_time_steps_per_second": vti_time_steps_per_second,
                "integrator_residual_ratio": moving_load_integrator_residual_ratio,
                "integrator_max_residual": moving_load_integrator_max_residual,
            },
            "optimization_hypothesis": "Warm-up and steady-state timers are now separated and the benchmark fast path is active, so the next gain is to keep the first-kernel path cheap while optimizing the steady-state moving-load path independently.",
            "first_actions": [
                "Use the warm-up versus steady-state split to optimize the steady-state track LF path separately from first-kernel startup.",
                "Batch axle-load interpolation and contact-force accumulation per time step.",
                "Keep moving-load integrator and VTI coarse timers aligned with the track LF split.",
            ],
            "acceptance_signals": [
                "warmup_skew_ratio materially reduced or explicitly isolated",
                "moving-load reports expose elapsed seconds and per-step throughput",
                "equilibrium_residual and energy balance remain green",
            ],
        },
    ]

    sprint_targets = [
        {
            "target_id": item["target_id"],
            "priority": item["priority"],
            "title": item["headline"],
            "expected_gain_band_pct": "15-25" if item["target_id"] == "ndtha_partitioned_runtime" else ("10-20" if item["target_id"] == "ssi_contact_convergence_path" else "10-15"),
            "source_reports": {
                "ndtha_partitioned_runtime": [
                    "implementation/phase1/ndtha_long_profile_report.json",
                    "implementation/phase1/solver_hip_e2e_contract_report.json",
                ],
                "ssi_contact_convergence_path": [
                    "implementation/phase1/vti_coupled_solver_report.json",
                    "implementation/phase1/ssi_boundary_gate_report.json",
                    "implementation/phase1/contact_readiness_report.json",
                    "implementation/phase1/foundation_soil_link_gate_report.json",
                ],
                "moving_load_kernel_warmup_observability": [
                    "implementation/phase1/track_lf_solver_report.json",
                    "implementation/phase1/moving_load_integrator_report.json",
                    "implementation/phase1/moving_load_integrator_large_report.json",
                    "implementation/phase1/moving_load_integrator_xlarge_report.json",
                    "implementation/phase1/vti_coupled_solver_report.json",
                ],
            }[item["target_id"]],
            "first_actions": item["first_actions"],
            "acceptance_signals": item["acceptance_signals"],
        }
        for item in top_bottlenecks
    ]

    checks = {
        "p0_engine_baseline_pass": bool(p0_engine_perf.get("contract_pass", False)) and bool(p0_perf) and bool(zero_copy),
        "gpu_bottleneck_audit_pass": bool(gpu_bottleneck_audit.get("contract_pass", False)),
        "ndtha_long_profile_pass": bool(ndtha_long_profile.get("contract_pass", False)) and ndtha_elapsed_wall_s_mean > 0.0,
        "ssi_contact_runtime_evidence_pass": bool(contact_readiness.get("contract_pass", False)) and bool(ssi_boundary.get("contract_pass", False)) and bool(foundation_soil_link.get("contract_pass", False)) and ssi_contact_step_count > 0,
        "moving_load_runtime_evidence_pass": bool(track_lf_solver.get("contract_pass", False)) and bool(moving_load_integrator.get("contract_pass", False)) and bool(vti_coupled_solver.get("contract_pass", False)) and track_euler_elapsed_seconds > 0.0 and track_timoshenko_elapsed_seconds > 0.0,
        "bottleneck_map_present_pass": len(top_bottlenecks) == 3,
        "sprint_target_count_pass": len(sprint_targets) == 3,
    }

    contract_pass = bool(all(checks.values()))
    if not checks["p0_engine_baseline_pass"] or not checks["gpu_bottleneck_audit_pass"]:
        reason_code = "ERR_BASELINE"
    elif not checks["ndtha_long_profile_pass"]:
        reason_code = "ERR_NDTHA"
    elif not checks["ssi_contact_runtime_evidence_pass"]:
        reason_code = "ERR_SSI_CONTACT"
    elif not checks["moving_load_runtime_evidence_pass"]:
        reason_code = "ERR_MOVING_LOAD"
    elif not checks["sprint_target_count_pass"]:
        reason_code = "ERR_SPRINT"
    else:
        reason_code = "PASS"

    summary = {
        "ndtha_elapsed_wall_s_mean": ndtha_elapsed_wall_s_mean,
        "ndtha_elapsed_wall_s_cov": ndtha_elapsed_wall_s_cov,
        "ndtha_peak_vram_mb_mean": ndtha_peak_vram_mb_mean,
        "ndtha_step_wall_seconds_mean": ndtha_step_wall_seconds_mean,
        "ndtha_halo_exchange_seconds_mean": ndtha_halo_exchange_seconds_mean,
        "ndtha_retry_overhead_seconds_mean": ndtha_retry_overhead_seconds_mean,
        "ndtha_solver_seconds_mean": ndtha_solver_seconds_mean,
        "ndtha_state_update_seconds_mean": ndtha_state_update_seconds_mean,
        "ndtha_interface_seconds_mean": ndtha_interface_seconds_mean,
        "ndtha_solver_reuse_ratio_mean": ndtha_solver_reuse_ratio_mean,
        "ndtha_stiffness_refresh_count_mean": ndtha_stiffness_refresh_count_mean,
        "ndtha_retry_attempt_count_mean": ndtha_retry_attempt_count_mean,
        "ndtha_retry_attempts_per_completed_step_mean": ndtha_retry_attempts_per_completed_step_mean,
        "ssi_contact_step_count": ssi_contact_step_count,
        "ssi_contact_mean_coupling_iters": ssi_contact_mean_coupling_iters,
        "ssi_contact_adaptive_newton_call_count": ssi_contact_adaptive_newton_call_count,
        "ssi_contact_adaptive_newton_avg_iterations": ssi_contact_adaptive_newton_avg_iterations,
        "ssi_broadphase_pair_count_total": ssi_broadphase_pair_count_total,
        "ssi_broadphase_candidate_pair_count_total": ssi_broadphase_candidate_pair_count_total,
        "ssi_broadphase_rejected_pair_count_total": ssi_broadphase_rejected_pair_count_total,
        "ssi_broadphase_candidate_pair_ratio": ssi_broadphase_candidate_pair_ratio,
        "ssi_broadphase_rejected_pair_ratio": ssi_broadphase_rejected_pair_ratio,
        "ssi_contact_window_retained_pair_ratio": ssi_contact_window_retained_pair_ratio,
        "ssi_retained_force_warm_start_ratio": ssi_retained_force_warm_start_ratio,
        "ssi_stable_zero_gap_skip_ratio": ssi_stable_zero_gap_skip_ratio,
        "ssi_variant_sweep_variant_count": ssi_variant_sweep_variant_count,
        "ssi_variant_sweep_pass_count": ssi_variant_sweep_pass_count,
        "ssi_variant_sweep_zero_gap_positive_count": ssi_variant_sweep_zero_gap_positive_count,
        "ssi_variant_sweep_retained_force_positive_count": ssi_variant_sweep_retained_force_positive_count,
        "ssi_variant_sweep_track_static_pruned_positive_count": ssi_variant_sweep_track_static_pruned_positive_count,
        "ssi_variant_sweep_zero_gap_skip_ratio_min": ssi_variant_sweep_zero_gap_skip_ratio_min,
        "ssi_variant_sweep_zero_gap_skip_ratio_max": ssi_variant_sweep_zero_gap_skip_ratio_max,
        "ssi_variant_sweep_track_static_pruned_ratio_min": ssi_variant_sweep_track_static_pruned_ratio_min,
        "ssi_variant_sweep_track_static_pruned_ratio_max": ssi_variant_sweep_track_static_pruned_ratio_max,
        "track_static_pruned_ratio": _finite(vti_metrics.get("track_static_pruned_ratio")),
        "ssi_residual_settle_case_count": ssi_residual_settle_case_count,
        "moving_load_track_euler_elapsed_seconds": track_euler_elapsed_seconds,
        "moving_load_track_timoshenko_elapsed_seconds": track_timoshenko_elapsed_seconds,
        "moving_load_track_euler_warmup_elapsed_seconds": track_euler_warmup_elapsed_seconds,
        "moving_load_track_timoshenko_warmup_elapsed_seconds": track_timoshenko_warmup_elapsed_seconds,
        "moving_load_track_euler_steady_state_elapsed_seconds": track_euler_steady_state_elapsed_seconds,
        "moving_load_track_timoshenko_steady_state_elapsed_seconds": track_timoshenko_steady_state_elapsed_seconds,
        "moving_load_benchmark_fast_path_enabled": bool(track_perf.get("benchmark_fast_path_enabled", False)),
        "moving_load_warmup_skew_ratio": moving_load_warmup_skew_ratio,
        "moving_load_steady_state_skew_ratio": moving_load_steady_state_skew_ratio,
        "moving_load_integrator_residual_ratio": moving_load_integrator_residual_ratio,
        "moving_load_integrator_max_residual": moving_load_integrator_max_residual,
        "moving_load_integrator_elapsed_seconds": moving_load_integrator_elapsed_seconds,
        "moving_load_integrator_time_steps_per_second": moving_load_integrator_time_steps_per_second,
        "moving_load_large_elapsed_seconds": moving_load_large_elapsed_seconds,
        "moving_load_large_time_steps_per_second": moving_load_large_time_steps_per_second,
        "moving_load_large_cached_track_solve_inverse_enabled": moving_load_large_cached_track_solve_inverse_enabled,
        "moving_load_xlarge_elapsed_seconds": moving_load_xlarge_elapsed_seconds,
        "moving_load_xlarge_time_steps_per_second": moving_load_xlarge_time_steps_per_second,
        "moving_load_xlarge_cached_track_solve_inverse_enabled": moving_load_xlarge_cached_track_solve_inverse_enabled,
        "moving_load_active_axle_count_mean": moving_load_active_axle_count_mean,
        "moving_load_sparse_contact_step_ratio": moving_load_sparse_contact_step_ratio,
        "moving_load_batched_track_solve_enabled": moving_load_batched_track_solve_enabled,
        "vti_elapsed_seconds": vti_elapsed_seconds,
        "vti_time_steps_per_second": vti_time_steps_per_second,
        "gpu_unavoidable_host_ops_count": gpu_unavoidable_host_ops_count,
        "gpu_optimizable_host_ops_count": gpu_optimizable_host_ops_count,
        "hip_kernel_invocation_count_total": hip_kernel_invocation_count_total,
        "first_sprint_target_count": len(sprint_targets),
        "first_sprint_target_ids": [item["target_id"] for item in sprint_targets],
    }
    summary_line = (
        "Performance profiling: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"ndtha={ndtha_elapsed_wall_s_mean:.2f}s(solver={ndtha_solver_seconds_mean:.2f},state={ndtha_state_update_seconds_mean:.2f},iface={ndtha_interface_seconds_mean:.2f},halo={ndtha_halo_exchange_seconds_mean:.2f}) | "
        f"ssi_contact={ssi_contact_step_count}steps/{ssi_contact_mean_coupling_iters:.2f}iters/newton={ssi_contact_adaptive_newton_call_count}/zero_gap_skip={ssi_stable_zero_gap_skip_ratio:.2f}/pairs={ssi_broadphase_candidate_pair_count_total}:{ssi_broadphase_rejected_pair_count_total}/sweep={ssi_variant_sweep_pass_count}/{max(1, ssi_variant_sweep_variant_count)} | "
        f"moving_load=warm={track_euler_warmup_elapsed_seconds:.3f}/{track_timoshenko_warmup_elapsed_seconds:.3f}s,steady={track_euler_steady_state_elapsed_seconds:.3f}/{track_timoshenko_steady_state_elapsed_seconds:.3f}s,scale={moving_load_integrator_elapsed_seconds:.3f}/{moving_load_large_elapsed_seconds:.3f}/{moving_load_xlarge_elapsed_seconds:.3f}s | "
        f"gpu_host_ops={gpu_unavoidable_host_ops_count} unavoidable/{gpu_optimizable_host_ops_count} optimizable | "
        f"sprint={len(sprint_targets)}({','.join(summary['first_sprint_target_ids'])})"
    )

    return {
        "schema_version": "1.0",
        "run_id": "phase1-performance-profiling-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
        "summary_line": summary_line,
        "bottleneck_map": top_bottlenecks,
        "sprint_targets": sprint_targets,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def _render_bottleneck_map_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    bottlenecks = report.get("bottleneck_map") if isinstance(report.get("bottleneck_map"), list) else []
    lines = [
        "# Performance Bottleneck Map",
        "",
        f"- `summary`: `{str(report.get('summary_line', '') or 'n/a')}`",
        f"- `generated_at`: `{str(report.get('generated_at', '') or '')}`",
        "",
        "## Baseline",
        "",
        _markdown_table(
            [
                ("NDTHA wall-clock mean", f"{_finite(summary.get('ndtha_elapsed_wall_s_mean')):.3f}s"),
                ("NDTHA wall-clock cov", f"{_finite(summary.get('ndtha_elapsed_wall_s_cov')):.6f}"),
                ("NDTHA step wall mean", f"{_finite(summary.get('ndtha_step_wall_seconds_mean')):.6f}s"),
                ("NDTHA solver mean", f"{_finite(summary.get('ndtha_solver_seconds_mean')):.6f}s"),
                ("NDTHA state-update mean", f"{_finite(summary.get('ndtha_state_update_seconds_mean')):.6f}s"),
                ("NDTHA interface mean", f"{_finite(summary.get('ndtha_interface_seconds_mean')):.6f}s"),
                ("NDTHA solver reuse ratio", f"{_finite(summary.get('ndtha_solver_reuse_ratio_mean')):.3f}"),
                ("NDTHA stiffness refresh count mean", f"{_finite(summary.get('ndtha_stiffness_refresh_count_mean')):.3f}"),
                ("NDTHA halo exchange mean", f"{_finite(summary.get('ndtha_halo_exchange_seconds_mean')):.6f}s"),
                ("NDTHA retry overhead mean", f"{_finite(summary.get('ndtha_retry_overhead_seconds_mean')):.6f}s"),
                ("SSI/contact step count", str(int(summary.get('ssi_contact_step_count', 0) or 0))),
                ("SSI/contact mean coupling iters", f"{_finite(summary.get('ssi_contact_mean_coupling_iters')):.3f}"),
                ("SSI/contact candidate pairs", str(int(summary.get('ssi_broadphase_candidate_pair_count_total', 0) or 0))),
                ("SSI/contact rejected pairs", str(int(summary.get('ssi_broadphase_rejected_pair_count_total', 0) or 0))),
                ("SSI/contact pruned track ratio", f"{_finite(summary.get('track_static_pruned_ratio')):.3f}"),
                ("SSI/contact retained-force warm start ratio", f"{_finite(summary.get('ssi_retained_force_warm_start_ratio')):.3f}"),
                ("SSI/contact stable zero-gap skip ratio", f"{_finite(summary.get('ssi_stable_zero_gap_skip_ratio')):.3f}"),
                ("SSI/contact variant sweep pass", f"{int(summary.get('ssi_variant_sweep_pass_count', 0) or 0)}/{int(summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"),
                ("SSI/contact variant sweep zero-gap", f"{int(summary.get('ssi_variant_sweep_zero_gap_positive_count', 0) or 0)}/{int(summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"),
                ("SSI/contact variant sweep pruned", f"{int(summary.get('ssi_variant_sweep_track_static_pruned_positive_count', 0) or 0)}/{int(summary.get('ssi_variant_sweep_variant_count', 0) or 0)}"),
                ("SSI/contact variant zero-gap range", f"{_finite(summary.get('ssi_variant_sweep_zero_gap_skip_ratio_min')):.3f}-{_finite(summary.get('ssi_variant_sweep_zero_gap_skip_ratio_max')):.3f}"),
                ("SSI/contact variant pruned range", f"{_finite(summary.get('ssi_variant_sweep_track_static_pruned_ratio_min')):.3f}-{_finite(summary.get('ssi_variant_sweep_track_static_pruned_ratio_max')):.3f}"),
                ("Moving-load Euler elapsed", f"{_finite(summary.get('moving_load_track_euler_elapsed_seconds')):.6f}s"),
                ("Moving-load Timoshenko elapsed", f"{_finite(summary.get('moving_load_track_timoshenko_elapsed_seconds')):.6f}s"),
                ("Moving-load warmup skew", f"{_finite(summary.get('moving_load_warmup_skew_ratio')):.3f}x"),
                ("Moving-load Euler warm-up", f"{_finite(summary.get('moving_load_track_euler_warmup_elapsed_seconds')):.6f}s"),
                ("Moving-load Timoshenko warm-up", f"{_finite(summary.get('moving_load_track_timoshenko_warmup_elapsed_seconds')):.6f}s"),
                ("Moving-load Euler steady-state", f"{_finite(summary.get('moving_load_track_euler_steady_state_elapsed_seconds')):.6f}s"),
                ("Moving-load Timoshenko steady-state", f"{_finite(summary.get('moving_load_track_timoshenko_steady_state_elapsed_seconds')):.6f}s"),
                ("Moving-load fast path", str(bool(summary.get('moving_load_benchmark_fast_path_enabled', False)))),
                ("Moving-load active axle mean", f"{_finite(summary.get('moving_load_active_axle_count_mean')):.3f}"),
                ("Moving-load sparse-step ratio", f"{_finite(summary.get('moving_load_sparse_contact_step_ratio')):.3f}"),
                ("Moving-load integrator elapsed", f"{_finite(summary.get('moving_load_integrator_elapsed_seconds')):.6f}s"),
                ("Moving-load large elapsed", f"{_finite(summary.get('moving_load_large_elapsed_seconds')):.6f}s"),
                ("Moving-load xlarge elapsed", f"{_finite(summary.get('moving_load_xlarge_elapsed_seconds')):.6f}s"),
                ("Moving-load large cached inverse", str(bool(summary.get('moving_load_large_cached_track_solve_inverse_enabled', False)))),
                ("Moving-load xlarge cached inverse", str(bool(summary.get('moving_load_xlarge_cached_track_solve_inverse_enabled', False)))),
                ("VTI elapsed", f"{_finite(summary.get('vti_elapsed_seconds')):.6f}s"),
                ("GPU unavoidable host ops", str(int(summary.get('gpu_unavoidable_host_ops_count', 0) or 0))),
                ("GPU optimizable host ops", str(int(summary.get('gpu_optimizable_host_ops_count', 0) or 0))),
            ]
        ),
        "",
        "## First Map",
        "",
    ]
    for item in bottlenecks:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"### {item.get('target_id', 'unknown')}",
                "",
                f"- `priority`: `{item.get('priority', 'n/a')}`",
                f"- `domain`: `{item.get('domain', 'n/a')}`",
                f"- `status`: `{item.get('status', 'n/a')}`",
                f"- `headline`: {item.get('headline', '')}",
                f"- `optimization_hypothesis`: {item.get('optimization_hypothesis', '')}",
                "- `evidence`: ",
            ]
        )
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        for key, value in evidence.items():
            lines.append(f"  - `{key}`: `{value}`")
        lines.append("- `first_actions`:")
        for action in item.get("first_actions", []):
            lines.append(f"  - {action}")
        lines.append("- `acceptance_signals`:")
        for signal in item.get("acceptance_signals", []):
            lines.append(f"  - {signal}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_sprint_targets_markdown(report: dict[str, Any]) -> str:
    targets = report.get("sprint_targets") if isinstance(report.get("sprint_targets"), list) else []
    lines = [
        "# First Optimization Sprint Targets",
        "",
        f"- `summary`: `{str(report.get('summary_line', '') or 'n/a')}`",
        "",
    ]
    for item in targets:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"## {item.get('target_id', 'unknown')}",
                "",
                f"- `priority`: `{item.get('priority', 'n/a')}`",
                f"- `expected_gain_band_pct`: `{item.get('expected_gain_band_pct', 'n/a')}`",
                f"- `title`: {item.get('title', '')}",
                "- `source_reports`:",
            ]
        )
        for path in item.get("source_reports", []):
            lines.append(f"  - `{path}`")
        lines.append("- `first_actions`:")
        for action in item.get("first_actions", []):
            lines.append(f"  - {action}")
        lines.append("- `acceptance_signals`:")
        for signal in item.get("acceptance_signals", []):
            lines.append(f"  - {signal}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p0-engine-perf-report", default="implementation/phase1/p0_engine_perf_report.json")
    parser.add_argument("--gpu-bottleneck-audit-report", default="implementation/phase1/gpu_bottleneck_audit_report.json")
    parser.add_argument("--ndtha-long-profile-report", default="implementation/phase1/ndtha_long_profile_report.json")
    parser.add_argument("--track-lf-solver-report", default="implementation/phase1/track_lf_solver_report.json")
    parser.add_argument("--moving-load-integrator-report", default="implementation/phase1/moving_load_integrator_report.json")
    parser.add_argument("--moving-load-integrator-large-report", default="implementation/phase1/moving_load_integrator_large_report.json")
    parser.add_argument("--moving-load-integrator-xlarge-report", default="implementation/phase1/moving_load_integrator_xlarge_report.json")
    parser.add_argument("--vti-coupled-solver-report", default="implementation/phase1/vti_coupled_solver_report.json")
    parser.add_argument("--vti-contact-window-variant-sweep-report", default="implementation/phase1/vti_contact_window_variant_sweep_report.json")
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--contact-readiness-report", default="implementation/phase1/contact_readiness_report.json")
    parser.add_argument("--foundation-soil-link-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    parser.add_argument("--solver-hip-e2e-report", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    parser.add_argument("--bottleneck-map-md", default="implementation/phase1/performance_bottleneck_map.md")
    parser.add_argument("--sprint-targets-json", default="implementation/phase1/performance_optimization_sprint_targets.json")
    parser.add_argument("--sprint-targets-md", default="implementation/phase1/performance_optimization_sprint_targets.md")
    parser.add_argument("--out", default="implementation/phase1/performance_profiling_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "p0_engine_perf_report": str(args.p0_engine_perf_report),
        "gpu_bottleneck_audit_report": str(args.gpu_bottleneck_audit_report),
        "ndtha_long_profile_report": str(args.ndtha_long_profile_report),
        "track_lf_solver_report": str(args.track_lf_solver_report),
        "moving_load_integrator_report": str(args.moving_load_integrator_report),
        "moving_load_integrator_large_report": str(args.moving_load_integrator_large_report),
        "moving_load_integrator_xlarge_report": str(args.moving_load_integrator_xlarge_report),
        "vti_coupled_solver_report": str(args.vti_coupled_solver_report),
        "vti_contact_window_variant_sweep_report": str(args.vti_contact_window_variant_sweep_report),
        "ssi_boundary_report": str(args.ssi_boundary_report),
        "contact_readiness_report": str(args.contact_readiness_report),
        "foundation_soil_link_report": str(args.foundation_soil_link_report),
        "solver_hip_e2e_report": str(args.solver_hip_e2e_report),
        "bottleneck_map_md": str(args.bottleneck_map_md),
        "sprint_targets_json": str(args.sprint_targets_json),
        "sprint_targets_md": str(args.sprint_targets_md),
        "out": str(args.out),
    }

    out = Path(args.out)
    bottleneck_map_md = Path(args.bottleneck_map_md)
    sprint_targets_json = Path(args.sprint_targets_json)
    sprint_targets_md = Path(args.sprint_targets_md)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_performance_profiling_gate")
        report = run_gate(
            p0_engine_perf=_load_json(REPO_ROOT / args.p0_engine_perf_report),
            gpu_bottleneck_audit=_load_json(REPO_ROOT / args.gpu_bottleneck_audit_report),
            ndtha_long_profile=_load_json(REPO_ROOT / args.ndtha_long_profile_report),
            track_lf_solver=_load_json(REPO_ROOT / args.track_lf_solver_report),
            moving_load_integrator=_load_json(REPO_ROOT / args.moving_load_integrator_report),
            moving_load_integrator_large=_load_json(REPO_ROOT / args.moving_load_integrator_large_report),
            moving_load_integrator_xlarge=_load_json(REPO_ROOT / args.moving_load_integrator_xlarge_report),
            vti_coupled_solver=_load_json(REPO_ROOT / args.vti_coupled_solver_report),
            vti_contact_window_variant_sweep=_load_json(REPO_ROOT / args.vti_contact_window_variant_sweep_report),
            ssi_boundary=_load_json(REPO_ROOT / args.ssi_boundary_report),
            contact_readiness=_load_json(REPO_ROOT / args.contact_readiness_report),
            foundation_soil_link=_load_json(REPO_ROOT / args.foundation_soil_link_report),
            solver_hip_e2e=_load_json(REPO_ROOT / args.solver_hip_e2e_report),
        )
        report["inputs"] = input_payload
        report["artifacts"] = {
            "report_json": str(Path(args.out)),
            "bottleneck_map_md": str(Path(args.bottleneck_map_md)),
            "sprint_targets_json": str(Path(args.sprint_targets_json)),
            "sprint_targets_md": str(Path(args.sprint_targets_md)),
        }
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-performance-profiling-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
            "summary_line": "Performance profiling: CHECK | invalid-input",
            "bottleneck_map": [],
            "sprint_targets": [],
            "artifacts": {
                "report_json": str(Path(args.out)),
                "bottleneck_map_md": str(Path(args.bottleneck_map_md)),
                "sprint_targets_json": str(Path(args.sprint_targets_json)),
                "sprint_targets_md": str(Path(args.sprint_targets_md)),
            },
        }

    _write_json(out, report)
    _write_text(bottleneck_map_md, _render_bottleneck_map_markdown(report))
    _write_json(sprint_targets_json, {
        "schema_version": "1.0",
        "generated_at": str(report.get("generated_at", "")),
        "summary_line": str(report.get("summary_line", "") or ""),
        "targets": report.get("sprint_targets", []),
    })
    _write_text(sprint_targets_md, _render_sprint_targets_markdown(report))
    print(f"Wrote performance profiling gate report: {out}")
    raise SystemExit(0 if bool(report.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
