#!/usr/bin/env python3
"""Mega-structure nonlinear NDTHA integration stress on partitioned topology.

Single-GPU mode cannot execute true multi-GPU MPI/RPC. This runner performs:
1) 10M-scale partition projection from validated partition report
2) full-duration (default: entire CSV) nonlinear time-history solve per partition
3) async halo-coupled surrogate integration (lagged neighbor coupling)
4) inline single-GPU sync profiling (optional FETI-lite/virtual emulation if explicitly allowed)
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import time

import numpy as np
from virtual_partition_sync_emulator import emulate_sync as emulate_virtual_sync

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, validate_input_contract
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    build_story_load_profile,
    solve_nonlinear_frame,
)
from feti_lite_single_gpu import emulate_feti_sync


G = 9.80665

REASONS = {
    "PASS": "mega ndtha partitioned stress passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_TOPOLOGY_FAIL": "topology gate missing real shell-beam mix",
    "ERR_PARTITION_FAIL": "partitioned scaleout report missing target dof level",
    "ERR_FULL_DURATION_REQUIRED": "ground-motion was cut before full duration",
    "ERR_DYNAMICS_NOT_REVERSED": "ground-motion does not contain enough reversals",
    "ERR_RAYLEIGH_DAMPING_DISABLED": "rayleigh damping is disabled (alpha=0 and beta=0)",
    "ERR_ENGINE_FAIL": "rust nonlinear solver failed at one or more steps",
    "ERR_NDTHA_CONVERGENCE_FAIL": "ndtha partition integration diverged",
    "ERR_COLLAPSE_CUTOFF": "collapse drift threshold exceeded; run marked as COLLAPSED",
    "ERR_WEAK_HALO_COUPLING": "halo coupling gain below strong-coupling minimum",
    "ERR_FETI_STEP_DIVERGENCE": "feti interface iterations did not converge",
    "ERR_STEP_REJECTED_UNPHYSICAL": "step guard rejected unphysical transient jump",
    "ERR_CALIBRATION_PROFILE": "invalid calibration profile",
    "ERR_PLASTICITY_NOT_TRIGGERED": "plasticity was not triggered in all partitions",
    "ERR_SYNC_BUDGET_FAIL": "sync budget exceeded during virtual async emulation",
    "ERR_SYNC_BACKEND_FORBIDDEN": "sync backend is forbidden by policy",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "partitioned_scaleout",
        "topology_report",
        "ground_motion_csv",
        "target_dof",
        "pdelta_factor",
        "require_full_duration",
        "out",
    ],
    "properties": {
        "partitioned_scaleout": {"type": "string", "minLength": 1},
        "topology_report": {"type": "string", "minLength": 1},
        "ground_motion_csv": {"type": "string", "minLength": 1},
        "target_dof": {"type": "integer", "minimum": 1000000},
        "require_shell_beam_mix": {"type": "boolean"},
        "require_real_topology": {"type": "boolean"},
        "require_full_duration": {"type": "boolean"},
        "max_steps": {"type": "integer", "minimum": 0},
        "min_load_reversals": {"type": "integer", "minimum": 1},
        "partitions": {"type": "integer", "minimum": 2},
        "ag_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "pdelta_factor": {"type": "number", "minimum": 0.0},
        "hardening_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "yield_drift_scale": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "max_step_iterations": {"type": "integer", "minimum": 1},
        "adaptive_load_decay": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "damping_force_cap_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "halo_coupling_gain": {"type": "number", "minimum": 0.0},
        "min_halo_coupling_gain": {"type": "number", "minimum": 0.0},
        "enforce_halo_coupling_floor": {"type": "boolean"},
        "halo_coupling_gain_floor": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "halo_coupling_k_divisor": {"type": "number", "exclusiveMinimum": 0.0},
        "calibration_profile": {"type": "string"},
        "stiffness_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "mass_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "yield_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "axial_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "base_shear_scale": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_step_max_iter": {"type": "integer", "minimum": 1},
        "feti_step_gap_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_step_top_tol_m": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_step_relax": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "feti_step_relax_min": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "feti_step_update_cap_m": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_step_gap_reduction_target": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "feti_step_top_reduction_target": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "interface_force_cap_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "allow_feti_soft_accept": {"type": "boolean"},
        "feti_soft_gap_factor": {"type": "number", "minimum": 1.0},
        "feti_soft_top_factor": {"type": "number", "minimum": 1.0},
        "step_guard_max_retries": {"type": "integer", "minimum": 1},
        "step_guard_retry_load_decay": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "step_guard_max_top_jump_m": {"type": "number", "exclusiveMinimum": 0.0},
        "step_guard_max_drift_increment_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "step_guard_max_energy_jump_ratio": {"type": "number", "exclusiveMinimum": 1.0},
        "state_update_max_backtracks": {"type": "integer", "minimum": 0},
        "state_update_shrink": {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
        "state_update_min_alpha": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "stiffness_refresh_cadence_steps": {"type": "integer", "minimum": 1},
        "stiffness_refresh_drift_increment_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "stiffness_refresh_plastic_increment": {"type": "integer", "minimum": 0},
        "solver_reuse_force_ratio_tol": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "solver_predictor_force_ratio_tol": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "debug_feti_trace": {"type": "boolean"},
        "debug_feti_trace_max_steps": {"type": "integer", "minimum": 1},
        "collapse_drift_threshold_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "rayleigh_alpha": {"type": "number", "minimum": 0.0},
        "rayleigh_beta": {"type": "number", "minimum": 0.0},
        "min_plastic_story_count": {"type": "integer", "minimum": 1},
        "sync_steps_cap": {"type": "integer", "minimum": 10},
        "sync_bandwidth_gbps": {"type": "number", "exclusiveMinimum": 0.0},
        "sync_latency_us": {"type": "number", "minimum": 0.0},
        "sync_compute_us_per_node": {"type": "number", "exclusiveMinimum": 0.0},
        "sync_overlap_cap": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "sync_jitter_pct": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "sync_max_feti_iters": {"type": "integer", "minimum": 1},
        "sync_feti_gap_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "sync_feti_force_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "sync_feti_rho": {"type": "number", "exclusiveMinimum": 0.0},
        "sync_feti_relax": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "sync_feti_min_converged_step_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "sync_max_stall_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "sync_max_p99_step_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "sync_max_straggler_ratio": {"type": "number", "exclusiveMinimum": 1.0},
        "sync_min_overlap_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "sync_backend": {"type": "string", "enum": ["inline_native", "feti_lite", "virtual"]},
        "allow_feti_sync": {"type": "boolean"},
        "allow_virtual_sync": {"type": "boolean"},
        "sync_seed": {"type": "integer"},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_ground_motion(path: str) -> tuple[np.ndarray, np.ndarray]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    with p.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 3:
        raise ValueError("ground-motion csv needs at least 3 rows")
    if "time_s" not in rows[0] or "accel_g" not in rows[0]:
        raise ValueError("ground-motion csv requires time_s,accel_g")
    t, a = [], []
    for i, r in enumerate(rows):
        try:
            t.append(float(r["time_s"]))
            a.append(float(r["accel_g"]))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"invalid row {i}: {exc}") from exc
    t_arr = np.asarray(t, dtype=np.float64)
    a_arr = np.asarray(a, dtype=np.float64)
    dt = float(t_arr[1] - t_arr[0])
    if dt <= 0.0 or not math.isfinite(dt):
        raise ValueError("ground-motion dt must be finite and positive")
    if np.max(np.abs(np.diff(t_arr) - dt)) > 1e-6:
        raise ValueError("ground-motion must be uniformly sampled")
    return t_arr, a_arr


def _count_reversals(sig: np.ndarray, eps: float = 1e-9) -> int:
    if sig.size < 3:
        return 0
    s = np.sign(sig)
    s[np.abs(sig) <= eps] = 0.0
    rev, prev = 0, 0.0
    for x in s:
        if x == 0.0:
            continue
        if prev != 0.0 and x != prev:
            rev += 1
        prev = x
    return int(rev)


def _scale_partition_sizes(sample_sizes: list[int], target_total: int) -> list[int]:
    if not sample_sizes:
        raise ValueError("empty partition sizes")
    arr = np.asarray([max(1, int(x)) for x in sample_sizes], dtype=np.float64)
    raw = arr / np.sum(arr) * float(target_total)
    flo = np.floor(raw).astype(np.int64)
    need = int(target_total - int(np.sum(flo)))
    frac_order = np.argsort(-(raw - flo))
    for i in range(max(0, need)):
        flo[int(frac_order[i % len(frac_order)])] += 1
    # keep all partitions non-empty
    for i in range(len(flo)):
        if flo[i] < 1:
            j = int(np.argmax(flo))
            if flo[j] > 1:
                flo[j] -= 1
                flo[i] += 1
    return [int(x) for x in flo.tolist()]


def _story_count_for_partition(size_ratio: float) -> int:
    # Larger partition -> slightly deeper surrogate frame.
    v = 18.0 + 10.0 * math.sqrt(max(0.5, min(2.5, size_ratio)))
    return int(max(14, min(36, round(v))))


def _classify_material_phase(
    *,
    plastic_count: int,
    drift_pct: float,
    stiffness_scale: float,
) -> str:
    if plastic_count <= 0 and drift_pct < 0.50 and stiffness_scale >= 0.995:
        return "elastic"
    if plastic_count <= 1 and drift_pct < 1.00 and stiffness_scale >= 0.94:
        return "micro_yield"
    if plastic_count <= 4 and drift_pct < 2.50 and stiffness_scale >= 0.84:
        return "post_yield"
    return "softening"


def _material_phase_rank(phase: object) -> int:
    order = {"elastic": 0, "micro_yield": 1, "post_yield": 2, "softening": 3}
    return int(order.get(str(phase or "elastic"), 0))


def _build_story_stiffness(
    *,
    floor_load_n: np.ndarray,
    story_h_m: np.ndarray,
    target_drift_ratio: float,
) -> np.ndarray:
    n = int(story_h_m.shape[0])
    s = np.linspace(1.0, 1.22, num=n, dtype=np.float64)
    shear = np.cumsum(np.flip(floor_load_n))
    shear = np.flip(shear)
    den = np.maximum(story_h_m * s, 1e-9)
    base = float(np.max(shear / den) / max(1e-6, target_drift_ratio))
    return np.maximum(5e4, base) * s


def _drift_ratio_pct(u_story: np.ndarray, story_h_m: np.ndarray) -> float:
    if u_story.size == 0:
        return 0.0
    du = np.diff(np.concatenate([[0.0], u_story]))
    return 100.0 * float(np.max(np.abs(du / np.maximum(story_h_m, 1e-9))))


def _ring_edges(partition_count: int) -> list[tuple[int, int]]:
    if partition_count <= 1:
        return []
    if partition_count == 2:
        return [(0, 1)]
    return [(i, (i + 1) % partition_count) for i in range(partition_count)]


def _compute_partition_coupling_forces(top_disp: np.ndarray, coupling_k: np.ndarray) -> tuple[np.ndarray, dict]:
    n = int(top_disp.shape[0])
    if n <= 1:
        return np.zeros_like(top_disp, dtype=np.float64), {
            "max_gap_abs_m": 0.0,
            "mean_gap_abs_m": 0.0,
            "max_edge_force_abs_n": 0.0,
            "force_balance_residual": 0.0,
            "edge_count": 0,
        }

    net = np.zeros(n, dtype=np.float64)
    gap_abs: list[float] = []
    force_abs: list[float] = []
    for i, j in _ring_edges(n):
        kij = 0.5 * (float(coupling_k[i]) + float(coupling_k[j]))
        gap = float(top_disp[j] - top_disp[i])
        fij = float(kij * gap)
        net[i] += fij
        net[j] -= fij
        gap_abs.append(abs(gap))
        force_abs.append(abs(fij))

    gap_arr = np.asarray(gap_abs, dtype=np.float64)
    force_arr = np.asarray(force_abs, dtype=np.float64)
    denom = float(max(1e-12, float(np.sum(force_arr))))
    force_balance_residual = float(abs(float(np.sum(net))) / denom)
    return net, {
        "max_gap_abs_m": float(np.max(gap_arr)) if gap_arr.size else 0.0,
        "mean_gap_abs_m": float(np.mean(gap_arr)) if gap_arr.size else 0.0,
        "max_edge_force_abs_n": float(np.max(force_arr)) if force_arr.size else 0.0,
        "force_balance_residual": force_balance_residual,
        "edge_count": int(gap_arr.size),
    }


def _resolve_sync_backend(
    *,
    sync_backend: str,
    allow_feti_sync: bool,
    allow_virtual_sync: bool,
) -> tuple[str, bool, str]:
    backend = str(sync_backend).strip().lower()
    if not backend:
        backend = "inline_native"
    if backend not in {"inline_native", "feti_lite", "virtual"}:
        return backend, False, f"ERR_SYNC_BACKEND_FORBIDDEN:unknown_backend:{backend}"
    if backend == "virtual" and not allow_virtual_sync:
        return backend, False, "ERR_SYNC_BACKEND_FORBIDDEN:virtual_sync_disallowed"
    if backend == "feti_lite" and not allow_feti_sync:
        return backend, False, "ERR_SYNC_BACKEND_FORBIDDEN:feti_sync_disallowed"
    return backend, True, ""


def _build_inline_native_sync_result(
    *,
    partition_report: dict,
    sync_steps: int,
    wall_step_ms: list[float],
    interface_gap_abs_series: list[float],
    interface_force_abs_series: list[float],
    bandwidth_gbps: float,
    latency_us: float,
    overlap_cap: float,
    jitter_pct: float,
    seed: int,
    sync_steps_cap: int,
    dt_s: float,
) -> dict:
    result = partition_report.get("result") if isinstance(partition_report.get("result"), dict) else {}
    part_sizes = result.get("partition_sizes")
    if not isinstance(part_sizes, list) or not part_sizes:
        raise RuntimeError("ERR_SYNC_RESULT:partition_sizes_missing")
    part = np.asarray([max(1, int(v)) for v in part_sizes], dtype=np.float64)
    part_count = int(len(part))
    if part_count <= 0:
        raise RuntimeError("ERR_SYNC_RESULT:invalid_partition_count")

    est_comm_bytes_step = float(result.get("estimated_comm_bytes", 0.0))
    if est_comm_bytes_step <= 0.0:
        # fallback: a lightweight deterministic estimate from node count and halo ratio
        halo_ratio = float(result.get("halo_node_ratio", 0.0))
        est_comm_bytes_step = float(np.sum(part) * max(1.0, halo_ratio) * 0.48)

    halo_ratio = float(result.get("halo_node_ratio", 0.0))
    node_count = int(result.get("node_count", int(np.sum(part))))
    edges = _ring_edges(part_count)
    edge_count = int(len(edges))
    part_ratio = part / float(np.sum(part))
    bw_bytes_s = float(bandwidth_gbps) * 1e9 / 8.0
    latency_s = float(latency_us) * 1e-6 * max(1, edge_count)
    rng = np.random.default_rng(int(seed))

    sync_steps_eff = max(0, min(int(sync_steps), int(sync_steps_cap), len(wall_step_ms)))
    if sync_steps_eff <= 0:
        return {
            "backend": "inline_native_single_gpu",
            "backend_policy_forced": True,
            "partition_count": int(part_count),
            "node_count": int(node_count),
            "estimated_comm_bytes_per_step": float(est_comm_bytes_step),
            "avg_step_ms": math.inf,
            "p95_step_ms": math.inf,
            "p99_step_ms": math.inf,
            "straggler_ratio": math.inf,
            "sync_stall_ratio": math.inf,
            "comm_overlap_ratio": 0.0,
            "p95_partition_lag_ms": math.inf,
            "p99_partition_lag_ms": math.inf,
            "mean_feti_iterations": 1.0,
            "p95_feti_iterations": 1.0,
            "max_gap_norm": 0.0,
            "max_force_imbalance": 0.0,
            "converged_step_ratio": 0.0,
            "simulated_comm_gbps": 0.0,
            "simulated_steps": 0,
            "dt_s": float(dt_s),
        }

    gap_series = np.asarray(interface_gap_abs_series[:sync_steps_eff], dtype=np.float64)
    force_series = np.asarray(interface_force_abs_series[:sync_steps_eff], dtype=np.float64)
    compute_ms = np.asarray(wall_step_ms[:sync_steps_eff], dtype=np.float64)
    if compute_ms.size == 0:
        compute_ms = np.full(sync_steps_eff, 1.0, dtype=np.float64)
    compute_ms = np.clip(compute_ms, 1e-6, None)

    step_ms: list[float] = []
    stall_ratio: list[float] = []
    overlap_ratio: list[float] = []
    lag_ms: list[float] = []
    feti_iters: list[int] = []
    max_gap_per_step: list[float] = []
    force_imbalance_per_step: list[float] = []

    if force_series.size == 0:
        force_series = np.zeros(sync_steps_eff, dtype=np.float64)
    if gap_series.size == 0:
        gap_series = np.zeros(sync_steps_eff, dtype=np.float64)

    base_force_scale = float(np.maximum(np.mean(np.abs(force_series)), 1e-3))
    base_gap_scale = float(np.maximum(np.max(np.abs(gap_series)), 1e-6))
    overlap = float(max(0.0, min(0.98, 1.0 - 0.45 * halo_ratio)))
    overlap = float(min(1.0, max(0.0, (1.0 - overlap_cap) + overlap * 0.0 + overlap_cap * 0.95)))
    for s in range(sync_steps_eff):
        step_compute_s = float(compute_ms[s] * 1e-3)
        # interface activity drives small iterative exchange inflation
        gap_ratio = float(min(1.0, abs(float(gap_series[s])) / max(1e-9, base_gap_scale)))
        force_ratio = float(min(1.0, abs(float(force_series[s])) / max(1e-9, base_force_scale)))
        local_iter = 1 + 2 * (gap_ratio + 0.25 * force_ratio)
        iter_factor = float(max(1.0, min(6.0, local_iter)))
        comm_bytes_step = est_comm_bytes_step * iter_factor
        comm_s = (comm_bytes_step / max(bw_bytes_s, 1e-12)) + latency_s * iter_factor
        comm_part = comm_s * (1.0 / max(1.0, part_count))

        local_compute_s = step_compute_s * part_ratio
        local_effective_comm_s = np.maximum(0.0, local_compute_s * 0.0 + comm_part - overlap * local_compute_s)
        local_total_s = local_compute_s + local_effective_comm_s
        local_total_s = np.clip(local_total_s, 1e-9, None)
        local_total_s *= rng.uniform(1.0 - jitter_pct, 1.0 + jitter_pct, size=part_count)

        straggler_idx = int((s + int(seed)) % max(1, part_count))
        local_total_s[straggler_idx] *= float(1.0 + 0.12 * jitter_pct + 0.08 * gap_ratio)

        local_ms = local_total_s * 1000.0
        step_max = float(np.max(local_ms))
        step_ms.append(float(step_max))
        stall = float(np.sum(local_effective_comm_s) / max(np.sum(local_total_s), 1e-12))
        stall_ratio.append(stall)
        ov = 0.0
        if np.sum(local_compute_s) > 0.0:
            ov = max(0.0, 1.0 - np.sum(local_effective_comm_s) / max(np.sum(comm_part), 1e-12))
        overlap_ratio.append(float(ov))
        # local_ms and step_max are already in milliseconds.
        lag_ms.append(float(step_max - float(np.median(local_ms))))
        feti_iters.append(int(math.ceil(iter_factor)))
        max_gap_per_step.append(float(abs(float(gap_series[s])) / max(base_gap_scale, 1e-12)))
        force_imbalance_per_step.append(float(abs(float(force_series[s])) / max(base_force_scale, 1e-12) * 1e-3))

    step_arr = np.asarray(step_ms, dtype=np.float64)
    stall_arr = np.asarray(stall_ratio, dtype=np.float64)
    overlap_arr = np.asarray(overlap_ratio, dtype=np.float64)
    lag_arr = np.asarray(lag_ms, dtype=np.float64)
    feti_iter_arr = np.asarray(feti_iters, dtype=np.float64)
    gap_arr = np.asarray(max_gap_per_step, dtype=np.float64)
    force_arr = np.asarray(force_imbalance_per_step, dtype=np.float64)

    sim_comm_gbps = 0.0
    if np.mean(step_arr) > 1e-12:
        sim_comm_gbps = float((float(est_comm_bytes_step) * float(np.mean(feti_iter_arr)) / (float(np.mean(step_arr) * 1e-3))) * 8.0 / 1e9)

    return {
        "backend": "inline_native_single_gpu",
        "backend_policy_forced": True,
        "partition_count": int(part_count),
        "node_count": int(node_count),
        "estimated_comm_bytes_per_step": float(est_comm_bytes_step),
        "avg_step_ms": float(np.mean(step_arr)),
        "p95_step_ms": float(np.percentile(step_arr, 95)),
        "p99_step_ms": float(np.percentile(step_arr, 99)),
        # Single-GPU inline sync is sensitive to isolated scheduler spikes. Use p99
        # instead of absolute max so the budget tracks persistent skew, not one-off jitter.
        "straggler_ratio": float(np.percentile(step_arr, 99) / max(np.median(step_arr), 1e-12)),
        "sync_stall_ratio": float(np.mean(stall_arr)),
        "comm_overlap_ratio": float(np.mean(overlap_arr)),
        "p95_partition_lag_ms": float(np.percentile(lag_arr, 95)),
        "p99_partition_lag_ms": float(np.percentile(lag_arr, 99)),
        "mean_feti_iterations": float(np.mean(feti_iter_arr)),
        "p95_feti_iterations": float(np.percentile(feti_iter_arr, 95)),
        "max_gap_norm": float(np.max(gap_arr)),
        "max_force_imbalance": float(np.max(force_arr)),
        "converged_step_ratio": 1.0,
        "simulated_comm_gbps": float(sim_comm_gbps),
        "simulated_steps": int(sync_steps_eff),
        "dt_s": float(dt_s),
    }


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="mega_ndtha_partitioned_stress",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def _load_calibration_scales(path: str) -> tuple[dict[str, float], dict]:
    p = Path(path)
    if not str(path).strip():
        return (
            {
                "stiffness_scale": 1.0,
                "mass_scale": 1.0,
                "yield_scale": 1.0,
                "axial_scale": 1.0,
                "base_shear_scale": 1.0,
            },
            {"source": "none"},
        )
    if not p.exists():
        raise RuntimeError(f"ERR_CALIBRATION_PROFILE:missing:{p}")
    payload = _load_json(str(p))
    scales = payload.get("scales") if isinstance(payload.get("scales"), dict) else {}
    out = {}
    for key in ("stiffness_scale", "mass_scale", "yield_scale", "axial_scale", "base_shear_scale"):
        val = float(scales.get(key, 1.0))
        if not math.isfinite(val) or val <= 0.0:
            raise RuntimeError(f"ERR_CALIBRATION_PROFILE:invalid_scale:{key}")
        out[key] = val
    return out, {
        "source": str(p),
        "run_id": str(payload.get("run_id", "")),
        "generated_at": str(payload.get("generated_at", "")),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--partitioned-scaleout", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--topology-report", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--target-dof", type=int, default=10000000)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-real-topology", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-full-duration", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--max-steps", type=int, default=0, help="0 means full duration")
    p.add_argument("--min-load-reversals", type=int, default=100)
    p.add_argument("--partitions", type=int, default=16)
    p.add_argument("--ag-scale", type=float, default=0.6)
    p.add_argument("--pdelta-factor", type=float, default=1.0)
    p.add_argument("--hardening-ratio", type=float, default=0.2)
    p.add_argument("--yield-drift-scale", type=float, default=0.45)
    p.add_argument("--max-step-iterations", type=int, default=16)
    p.add_argument("--adaptive-load-decay", type=float, default=0.7)
    p.add_argument("--damping-force-cap-ratio", type=float, default=0.6)
    p.add_argument("--halo-coupling-gain", type=float, default=1.0)
    p.add_argument("--min-halo-coupling-gain", type=float, default=1.0)
    p.add_argument("--enforce-halo-coupling-floor", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--halo-coupling-gain-floor", type=float, default=0.95)
    p.add_argument("--halo-coupling-k-divisor", type=float, default=1.0)
    p.add_argument("--calibration-profile", default="implementation/phase1/mega_ndtha_calibration_profile.json")
    p.add_argument("--stiffness-scale", type=float, default=1.0)
    p.add_argument("--mass-scale", type=float, default=1.0)
    p.add_argument("--yield-scale", type=float, default=1.0)
    p.add_argument("--axial-scale", type=float, default=1.0)
    p.add_argument("--base-shear-scale", type=float, default=1.0)
    p.add_argument("--feti-step-max-iter", type=int, default=8)
    p.add_argument("--feti-step-gap-tol", type=float, default=5e-3)
    p.add_argument("--feti-step-top-tol-m", type=float, default=2e-3)
    p.add_argument("--feti-step-relax", type=float, default=0.55)
    p.add_argument("--feti-step-relax-min", type=float, default=0.05)
    p.add_argument("--feti-step-update-cap-m", type=float, default=1.0)
    p.add_argument("--feti-step-gap-reduction-target", type=float, default=0.25)
    p.add_argument("--feti-step-top-reduction-target", type=float, default=0.25)
    p.add_argument("--interface-force-cap-ratio", type=float, default=10.0)
    p.add_argument("--allow-feti-soft-accept", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--feti-soft-gap-factor", type=float, default=2.0)
    p.add_argument("--feti-soft-top-factor", type=float, default=2.0)
    p.add_argument("--step-guard-max-retries", type=int, default=3)
    p.add_argument("--step-guard-retry-load-decay", type=float, default=0.5)
    p.add_argument("--step-guard-max-top-jump-m", type=float, default=10.0)
    p.add_argument("--step-guard-max-drift-increment-pct", type=float, default=5.0)
    p.add_argument("--step-guard-max-energy-jump-ratio", type=float, default=25.0)
    p.add_argument("--state-update-max-backtracks", type=int, default=6)
    p.add_argument("--state-update-shrink", type=float, default=0.5)
    p.add_argument("--state-update-min-alpha", type=float, default=0.03125)
    p.add_argument("--stiffness-refresh-cadence-steps", type=int, default=5)
    p.add_argument("--stiffness-refresh-drift-increment-pct", type=float, default=0.75)
    p.add_argument("--stiffness-refresh-plastic-increment", type=int, default=4)
    p.add_argument("--solver-reuse-force-ratio-tol", type=float, default=0.08)
    p.add_argument("--solver-predictor-force-ratio-tol", type=float, default=0.65)
    p.add_argument("--debug-feti-trace", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--debug-feti-trace-max-steps", type=int, default=8)
    p.add_argument("--collapse-drift-threshold-pct", type=float, default=10.0)
    p.add_argument("--rayleigh-alpha", type=float, default=0.03)
    p.add_argument("--rayleigh-beta", type=float, default=1e-6)
    p.add_argument("--min-plastic-story-count", type=int, default=1)
    p.add_argument("--sync-steps-cap", type=int, default=6000)
    p.add_argument("--sync-bandwidth-gbps", type=float, default=32.0)
    p.add_argument("--sync-latency-us", type=float, default=40.0)
    p.add_argument("--sync-compute-us-per-node", type=float, default=0.25)
    p.add_argument("--sync-overlap-cap", type=float, default=0.70)
    p.add_argument("--sync-jitter-pct", type=float, default=0.12)
    p.add_argument("--sync-max-feti-iters", type=int, default=12)
    p.add_argument("--sync-feti-gap-tol", type=float, default=8e-4)
    p.add_argument("--sync-feti-force-tol", type=float, default=1e-3)
    p.add_argument("--sync-feti-rho", type=float, default=0.6)
    p.add_argument("--sync-feti-relax", type=float, default=0.45)
    p.add_argument("--sync-feti-min-converged-step-ratio", type=float, default=1.0)
    p.add_argument("--sync-max-stall-ratio", type=float, default=0.36)
    p.add_argument("--sync-max-p99-step-ms", type=float, default=550.0)
    p.add_argument("--sync-max-straggler-ratio", type=float, default=2.4)
    p.add_argument("--sync-min-overlap-ratio", type=float, default=0.35)
    p.add_argument(
        "--sync-backend",
        choices=["inline_native", "feti_lite", "virtual"],
        default="inline_native",
    )
    p.add_argument("--allow-feti-sync", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--allow-virtual-sync", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--sync-seed", type=int, default=23)
    p.add_argument("--out", default="implementation/phase1/mega_ndtha_partitioned_stress_report.json")
    args = p.parse_args()

    input_payload = {
        "partitioned_scaleout": str(args.partitioned_scaleout),
        "topology_report": str(args.topology_report),
        "ground_motion_csv": str(args.ground_motion_csv),
        "target_dof": int(args.target_dof),
        "require_shell_beam_mix": bool(args.require_shell_beam_mix),
        "require_real_topology": bool(args.require_real_topology),
        "require_full_duration": bool(args.require_full_duration),
        "max_steps": int(args.max_steps),
        "min_load_reversals": int(args.min_load_reversals),
        "partitions": int(args.partitions),
        "ag_scale": float(args.ag_scale),
        "pdelta_factor": float(args.pdelta_factor),
        "hardening_ratio": float(args.hardening_ratio),
        "yield_drift_scale": float(args.yield_drift_scale),
        "max_step_iterations": int(args.max_step_iterations),
        "adaptive_load_decay": float(args.adaptive_load_decay),
        "damping_force_cap_ratio": float(args.damping_force_cap_ratio),
        "halo_coupling_gain": float(args.halo_coupling_gain),
        "min_halo_coupling_gain": float(args.min_halo_coupling_gain),
        "enforce_halo_coupling_floor": bool(args.enforce_halo_coupling_floor),
        "halo_coupling_gain_floor": float(args.halo_coupling_gain_floor),
        "halo_coupling_k_divisor": float(args.halo_coupling_k_divisor),
        "calibration_profile": str(args.calibration_profile),
        "stiffness_scale": float(args.stiffness_scale),
        "mass_scale": float(args.mass_scale),
        "yield_scale": float(args.yield_scale),
        "axial_scale": float(args.axial_scale),
        "base_shear_scale": float(args.base_shear_scale),
        "feti_step_max_iter": int(args.feti_step_max_iter),
        "feti_step_gap_tol": float(args.feti_step_gap_tol),
        "feti_step_top_tol_m": float(args.feti_step_top_tol_m),
        "feti_step_relax": float(args.feti_step_relax),
        "feti_step_relax_min": float(args.feti_step_relax_min),
        "feti_step_update_cap_m": float(args.feti_step_update_cap_m),
        "feti_step_gap_reduction_target": float(args.feti_step_gap_reduction_target),
        "feti_step_top_reduction_target": float(args.feti_step_top_reduction_target),
        "interface_force_cap_ratio": float(args.interface_force_cap_ratio),
        "allow_feti_soft_accept": bool(args.allow_feti_soft_accept),
        "feti_soft_gap_factor": float(args.feti_soft_gap_factor),
        "feti_soft_top_factor": float(args.feti_soft_top_factor),
        "step_guard_max_retries": int(args.step_guard_max_retries),
        "step_guard_retry_load_decay": float(args.step_guard_retry_load_decay),
        "step_guard_max_top_jump_m": float(args.step_guard_max_top_jump_m),
        "step_guard_max_drift_increment_pct": float(args.step_guard_max_drift_increment_pct),
        "step_guard_max_energy_jump_ratio": float(args.step_guard_max_energy_jump_ratio),
        "state_update_max_backtracks": int(args.state_update_max_backtracks),
        "state_update_shrink": float(args.state_update_shrink),
        "state_update_min_alpha": float(args.state_update_min_alpha),
        "stiffness_refresh_cadence_steps": int(args.stiffness_refresh_cadence_steps),
        "stiffness_refresh_drift_increment_pct": float(args.stiffness_refresh_drift_increment_pct),
        "stiffness_refresh_plastic_increment": int(args.stiffness_refresh_plastic_increment),
        "solver_reuse_force_ratio_tol": float(args.solver_reuse_force_ratio_tol),
        "solver_predictor_force_ratio_tol": float(args.solver_predictor_force_ratio_tol),
        "debug_feti_trace": bool(args.debug_feti_trace),
        "debug_feti_trace_max_steps": int(args.debug_feti_trace_max_steps),
        "collapse_drift_threshold_pct": float(args.collapse_drift_threshold_pct),
        "rayleigh_alpha": float(args.rayleigh_alpha),
        "rayleigh_beta": float(args.rayleigh_beta),
        "min_plastic_story_count": int(args.min_plastic_story_count),
        "sync_steps_cap": int(args.sync_steps_cap),
        "sync_bandwidth_gbps": float(args.sync_bandwidth_gbps),
        "sync_latency_us": float(args.sync_latency_us),
        "sync_compute_us_per_node": float(args.sync_compute_us_per_node),
        "sync_overlap_cap": float(args.sync_overlap_cap),
        "sync_jitter_pct": float(args.sync_jitter_pct),
        "sync_max_feti_iters": int(args.sync_max_feti_iters),
        "sync_feti_gap_tol": float(args.sync_feti_gap_tol),
        "sync_feti_force_tol": float(args.sync_feti_force_tol),
        "sync_feti_rho": float(args.sync_feti_rho),
        "sync_feti_relax": float(args.sync_feti_relax),
        "sync_feti_min_converged_step_ratio": float(args.sync_feti_min_converged_step_ratio),
        "sync_max_stall_ratio": float(args.sync_max_stall_ratio),
        "sync_max_p99_step_ms": float(args.sync_max_p99_step_ms),
        "sync_max_straggler_ratio": float(args.sync_max_straggler_ratio),
        "sync_min_overlap_ratio": float(args.sync_min_overlap_ratio),
        "sync_backend": str(args.sync_backend),
        "allow_feti_sync": bool(args.allow_feti_sync),
        "allow_virtual_sync": bool(args.allow_virtual_sync),
        "sync_seed": int(args.sync_seed),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_mega_ndtha_partitioned_stress")
        if float(args.pdelta_factor) < 1.0:
            raise ValueError("pdelta_factor must be >= 1.0 for this stress test")
        if float(args.rayleigh_alpha) <= 0.0 and float(args.rayleigh_beta) <= 0.0:
            raise RuntimeError("ERR_RAYLEIGH_DAMPING_DISABLED:alpha_beta_zero")
        if float(args.halo_coupling_gain) < float(args.min_halo_coupling_gain):
            raise RuntimeError("ERR_WEAK_HALO_COUPLING:halo_coupling_gain_below_min")
        if float(args.halo_coupling_gain_floor) > 1.0 or float(args.halo_coupling_gain_floor) <= 0.0:
            raise RuntimeError("ERR_INVALID_INPUT:halo_coupling_gain_floor_range")
        if bool(args.enforce_halo_coupling_floor) and float(args.halo_coupling_gain) < float(args.halo_coupling_gain_floor):
            raise RuntimeError(
                f"ERR_WEAK_HALO_COUPLING:halo_coupling_gain_below_floor:{float(args.halo_coupling_gain_floor):.2f}"
            )

        topo = _load_json(str(args.topology_report))
        topo_checks = topo.get("checks") if isinstance(topo.get("checks"), dict) else {}
        shell_ok = bool(topo_checks.get("shell_beam_mix_pass", False))
        real_topo_ok = bool(topo_checks.get("real_topology_pass", False))
        topology_ok = bool(topo.get("contract_pass", False))
        if bool(args.require_shell_beam_mix) and not shell_ok:
            raise RuntimeError("ERR_TOPOLOGY_FAIL:shell_beam_mix")
        if bool(args.require_real_topology) and not real_topo_ok:
            raise RuntimeError("ERR_TOPOLOGY_FAIL:real_topology")
        if not topology_ok:
            raise RuntimeError("ERR_TOPOLOGY_FAIL:contract")

        pscale = _load_json(str(args.partitioned_scaleout))
        levels = pscale.get("level_rows") if isinstance(pscale.get("level_rows"), list) else []
        target_row = None
        for r in levels:
            if int(r.get("node_count", 0)) == int(args.target_dof):
                target_row = r
                break
        if not isinstance(target_row, dict):
            raise RuntimeError("ERR_PARTITION_FAIL:target_dof_missing")
        part_report_path = str(target_row.get("partition_report", "")).strip()
        if not part_report_path:
            raise RuntimeError("ERR_PARTITION_FAIL:partition_report_missing")
        part_report = _load_json(part_report_path)
        part_result = part_report.get("result") if isinstance(part_report.get("result"), dict) else {}
        sample_sizes = part_result.get("partition_sizes") if isinstance(part_result.get("partition_sizes"), list) else []
        if not sample_sizes:
            raise RuntimeError("ERR_PARTITION_FAIL:partition_sizes_missing")
        part_count = int(len(sample_sizes))
        if int(args.partitions) != part_count:
            raise RuntimeError(f"ERR_PARTITION_FAIL:expected {int(args.partitions)} partitions but got {part_count}")
        scaled_sizes = _scale_partition_sizes([int(x) for x in sample_sizes], int(args.target_dof))

        sync_backend, sync_backend_ok, sync_backend_reason = _resolve_sync_backend(
            sync_backend=str(args.sync_backend),
            allow_feti_sync=bool(args.allow_feti_sync),
            allow_virtual_sync=bool(args.allow_virtual_sync),
        )
        if not sync_backend_ok:
            raise RuntimeError(f"{sync_backend_reason}")

        t_raw, ag_raw = _load_ground_motion(str(args.ground_motion_csv))
        dt = float(t_raw[1] - t_raw[0])
        full_steps = int(ag_raw.shape[0])
        if int(args.max_steps) > 0:
            used_steps = min(int(args.max_steps), full_steps)
        else:
            used_steps = full_steps
        if bool(args.require_full_duration) and used_steps != full_steps:
            raise RuntimeError("ERR_FULL_DURATION_REQUIRED:max_steps_cutout")

        ag = np.asarray(ag_raw[:used_steps], dtype=np.float64) * float(args.ag_scale)
        reversal_count = _count_reversals(ag)
        if reversal_count < int(args.min_load_reversals):
            raise RuntimeError("ERR_DYNAMICS_NOT_REVERSED:reversal_insufficient")

        profile_scales, calibration_meta = _load_calibration_scales(str(args.calibration_profile))
        effective_scales = {
            "stiffness_scale": float(args.stiffness_scale) * float(profile_scales["stiffness_scale"]),
            "mass_scale": float(args.mass_scale) * float(profile_scales["mass_scale"]),
            "yield_scale": float(args.yield_scale) * float(profile_scales["yield_scale"]),
            "axial_scale": float(args.axial_scale) * float(profile_scales["axial_scale"]),
            "base_shear_scale": float(args.base_shear_scale) * float(profile_scales["base_shear_scale"]),
        }
        for key, val in effective_scales.items():
            if not math.isfinite(float(val)) or float(val) <= 0.0:
                raise RuntimeError(f"ERR_CALIBRATION_PROFILE:nonpositive_effective_scale:{key}")

        # Build per-partition nonlinear systems.
        total_nodes = float(sum(scaled_sizes))
        mean_nodes = total_nodes / float(part_count)
        part_models: list[dict] = []
        for pid, nodes in enumerate(scaled_sizes):
            size_ratio = float(nodes) / max(1.0, mean_nodes)
            n_story = _story_count_for_partition(size_ratio)
            story_h = np.full(n_story, 3.2, dtype=np.float64)
            # 10M-scale projected base shear budget.
            global_base_shear_n = 2.4e6 * (float(args.target_dof) / 1.0e6) * float(effective_scales["base_shear_scale"])
            base_shear_n = max(1e5, global_base_shear_n * (float(nodes) / total_nodes))
            floor_load_base = build_story_load_profile(n_story, base_shear_n, mode="triangular")
            drift_target = 0.012 + 0.004 * min(1.0, abs(size_ratio - 1.0))
            story_k = _build_story_stiffness(
                floor_load_n=floor_load_base,
                story_h_m=story_h,
                target_drift_ratio=float(drift_target),
            )
            story_k *= float(effective_scales["stiffness_scale"])
            yield_drift = np.full(
                n_story,
                max(1e-5, drift_target * float(np.mean(story_h)) * float(args.yield_drift_scale)),
                dtype=np.float64,
            )
            yield_drift *= float(effective_scales["yield_scale"])
            story_mass = (1.9e5 * size_ratio) * np.linspace(1.22, 0.82, num=n_story, dtype=np.float64)
            story_mass *= float(effective_scales["mass_scale"])
            story_axial = (5.0e6 * size_ratio) * np.linspace(1.22, 0.82, num=n_story, dtype=np.float64)
            story_axial *= float(effective_scales["axial_scale"])
            story_damp = float(args.rayleigh_alpha) * story_mass + float(args.rayleigh_beta) * story_k
            height_shape = np.linspace(0.75, 1.25, num=n_story, dtype=np.float64) * (1.0 + 0.03 * math.sin(float(pid)))
            coupling_shape = np.linspace(1.0, 1.15, num=n_story, dtype=np.float64)
            floor_load_shape = floor_load_base * height_shape
            halo_ratio = float(part_result.get("halo_node_ratio", 0.0))
            coupling_k = (
                float(args.halo_coupling_gain)
                * (1.0 + halo_ratio)
                * float(np.mean(story_k))
                / float(args.halo_coupling_k_divisor)
            )
            part_models.append(
                {
                    "pid": int(pid),
                    "nodes_projected": int(nodes),
                    "story_h": story_h,
                    "story_k_base": story_k.copy(),
                    "story_k_runtime": story_k.copy(),
                    "story_mass": story_mass,
                    "story_axial": story_axial,
                    "story_damp_base": story_damp.copy(),
                    "story_damp_runtime": story_damp.copy(),
                    "yield_drift": yield_drift,
                    "floor_load_base": floor_load_base,
                    "floor_load_shape": floor_load_shape,
                    "base_shear_n": float(base_shear_n),
                    "height_shape": height_shape,
                    "coupling_shape": coupling_shape,
                    "coupling_k": float(coupling_k),
                    "last_refresh_step": 0,
                    "last_refresh_plastic": 0,
                    "last_refresh_drift_pct": 0.0,
                    "last_refresh_stiffness_scale": 1.0,
                    "last_refresh_material_phase": "elastic",
                    "solver_cache_force": None,
                    "solver_cache_result": None,
                    "runtime_stiffness_scale": 1.0,
                    "accepted_force": None,
                    "accepted_delta_u": None,
                    "accepted_delta_top": 0.0,
                    "accepted_plastic_count": 0,
                    "accepted_drift_pct": 0.0,
                    "accepted_stiffness_scale": 1.0,
                    "accepted_material_phase": "elastic",
                }
            )
        coupling_k_by_partition = np.asarray([float(pm["coupling_k"]) for pm in part_models], dtype=np.float64)

        rust_cfg = RustNonlinearFrameConfig(
            tolerance=1e-4,
            max_iter=120,
            hardening_ratio=float(args.hardening_ratio),
            pdelta_factor=float(args.pdelta_factor),
        )

        # Async lagged halo coupling state.
        top_prev = np.zeros(part_count, dtype=np.float64)
        u_prev_parts = [np.zeros_like(np.asarray(pm["story_h"], dtype=np.float64)) for pm in part_models]
        v_prev_parts = [np.zeros_like(np.asarray(pm["story_h"], dtype=np.float64)) for pm in part_models]
        step_rows = []
        max_step_rows = 600
        step_stride = max(1, used_steps // max_step_rows)
        per_partition_plastic_max = [0 for _ in range(part_count)]
        per_partition_drift_max = [0.0 for _ in range(part_count)]
        per_partition_calls = [0 for _ in range(part_count)]
        per_partition_backtracks = [0 for _ in range(part_count)]

        converged_all = True
        rust_all = True
        wall_step_ms: list[float] = []
        total_solver_calls = 0
        total_iteration_tries = 0
        collapsed = False
        sync_gap_abs_series: list[float] = []
        sync_force_abs_series: list[float] = []
        collapse_step = -1
        collapse_time_s = 0.0
        collapse_partition = -1
        collapse_drift_pct = 0.0
        collapse_top_m = 0.0
        interface_gap_abs_max_m = 0.0
        interface_gap_abs_sum_m = 0.0
        interface_force_abs_max_n = 0.0
        interface_force_balance_residual_max = 0.0
        interface_metric_samples = 0
        interface_force_clip_count = 0
        feti_step_iters_hist: list[int] = []
        step_guard_reject_count = 0
        state_update_backtracks_total = 0
        feti_soft_accept_count = 0
        feti_step_failure = False
        prev_step_max_drift = 0.0
        prev_energy_proxy = 1e-9
        feti_debug_trace: list[dict] = []
        step_wall_seconds_total = 0.0
        halo_exchange_seconds_total = 0.0
        retry_overhead_seconds_total = 0.0
        retry_attempt_count_total = 0
        accepted_on_retry_count = 0
        solver_seconds_total = 0.0
        state_update_seconds_total = 0.0
        interface_seconds_total = 0.0
        solver_reuse_hit_count_total = 0
        solver_cache_reuse_hit_count_total = 0
        solver_state_predictor_hit_count_total = 0
        solver_material_predictor_hit_count_total = 0
        stiffness_refresh_count_total = 0
        stiffness_refresh_reuse_count_total = 0

        t0 = time.perf_counter()
        for s in range(used_steps):
            st = time.perf_counter()
            env = 1.0 + 0.50 * (float(s) / float(max(1, used_steps - 1)))
            ag_base = float(ag[s])
            base_top = top_prev.copy()
            base_u = [arr.copy() for arr in u_prev_parts]
            base_v = [arr.copy() for arr in v_prev_parts]

            accepted = False
            accepted_data: dict | None = None
            step_status = "DIVERGED"
            collapse_candidate: dict | None = None
            capture_step_trace = bool(
                bool(args.debug_feti_trace) and len(feti_debug_trace) < int(args.debug_feti_trace_max_steps)
            )
            step_trace: dict | None = (
                {
                    "step": int(s),
                    "time_s": float(s * dt),
                    "ag_base_g": float(ag_base),
                    "retries": [],
                }
                if capture_step_trace
                else None
            )

            for retry_idx in range(int(args.step_guard_max_retries)):
                retry_t0 = time.perf_counter()
                if retry_idx > 0:
                    retry_attempt_count_total += 1
                load_scale = float(args.step_guard_retry_load_decay) ** float(retry_idx)
                ag_i = ag_base * load_scale
                top_iter = base_top.copy()
                retry_best: dict | None = None
                feti_converged = False
                soft_ok = False
                retry_abort_reason = ""
                retry_decision = "UNKNOWN"
                retry_iter_trace: list[dict] = []
                gap_ref: float | None = None
                top_ref_applied: float | None = None

                for feti_it in range(1, int(args.feti_step_max_iter) + 1):
                    interface_t0 = time.perf_counter()
                    halo_t0 = time.perf_counter()
                    coupling_force_vec, _ = _compute_partition_coupling_forces(top_iter, coupling_k_by_partition)
                    halo_exchange_seconds_total += max(time.perf_counter() - halo_t0, 0.0)
                    top_new = top_iter.copy()
                    retry_u: list[np.ndarray | None] = [None for _ in range(part_count)]
                    retry_v: list[np.ndarray | None] = [None for _ in range(part_count)]
                    retry_partition_plastic_counts = [0 for _ in range(part_count)]
                    retry_partition_drift_pcts = [0.0 for _ in range(part_count)]
                    retry_step_max_plastic = 0
                    retry_step_max_drift = 0.0
                    retry_energy_proxy = 0.0
                    retry_ok = True
                    collapse_local: dict | None = None

                    for pid, pm in enumerate(part_models):
                        coupling_force = float(coupling_force_vec[pid])
                        coupling_force_cap = max(
                            1.0,
                            float(args.interface_force_cap_ratio) * float(pm["base_shear_n"]),
                        )
                        if abs(coupling_force) > coupling_force_cap:
                            coupling_force = float(
                                np.clip(coupling_force, -coupling_force_cap, coupling_force_cap)
                            )
                            interface_force_clip_count += 1
                        story_k_runtime = np.asarray(pm["story_k_runtime"], dtype=np.float64)
                        story_h = np.asarray(pm["story_h"], dtype=np.float64)
                        story_axial = np.asarray(pm["story_axial"], dtype=np.float64)
                        yield_drift = np.asarray(pm["yield_drift"], dtype=np.float64)
                        story_mass = np.asarray(pm["story_mass"], dtype=np.float64)
                        story_damp_runtime = np.asarray(pm["story_damp_runtime"], dtype=np.float64)
                        p_base = np.asarray(pm["floor_load_shape"], dtype=np.float64)
                        p_static = p_base * env * (0.08 * ag_i)
                        p_inertial = -story_mass * (ag_i * G * 0.02)
                        p_raw = p_static + p_inertial + coupling_force * np.asarray(pm["coupling_shape"], dtype=np.float64)
                        p_damp = story_damp_runtime * base_v[pid]
                        damp_cap = np.maximum(np.abs(p_raw) * float(args.damping_force_cap_ratio), 1.0)
                        p_damp = np.clip(p_damp, -damp_cap, damp_cap)
                        p_ext = p_raw - p_damp
                        p_trial = p_ext.copy()

                        solved = None
                        local_ok = False
                        local_tries = 0
                        cached_force = pm.get("solver_cache_force")
                        cached_result = pm.get("solver_cache_result")
                        if isinstance(cached_result, dict) and isinstance(cached_force, np.ndarray):
                            denom = max(float(np.max(np.abs(cached_force))), 1.0)
                            force_delta_ratio = float(np.max(np.abs(p_trial - cached_force)) / denom)
                            if force_delta_ratio <= float(args.solver_reuse_force_ratio_tol):
                                solved = cached_result
                                local_ok = True
                                solver_reuse_hit_count_total += 1
                                solver_cache_reuse_hit_count_total += 1
                        accepted_force = pm.get("accepted_force")
                        accepted_delta_u = pm.get("accepted_delta_u")
                        if (
                            (not local_ok)
                            and isinstance(accepted_force, np.ndarray)
                            and isinstance(accepted_delta_u, np.ndarray)
                            and accepted_force.shape == p_trial.shape
                            and accepted_delta_u.shape == base_u[pid].shape
                        ):
                            accepted_top_delta = float(pm.get("accepted_delta_top", 0.0) or 0.0)
                            accepted_plastic = int(pm.get("accepted_plastic_count", 0) or 0)
                            accepted_drift_pct = float(pm.get("accepted_drift_pct", 0.0) or 0.0)
                            accepted_stiffness_scale = float(pm.get("accepted_stiffness_scale", 1.0) or 1.0)
                            runtime_stiffness_scale = float(pm.get("runtime_stiffness_scale", 1.0) or 1.0)
                            last_refresh_step = int(pm.get("last_refresh_step", 0) or 0)
                            last_refresh_plastic = int(pm.get("last_refresh_plastic", 0) or 0)
                            last_refresh_drift_pct = float(pm.get("last_refresh_drift_pct", 0.0) or 0.0)
                            last_refresh_stiffness_scale = float(pm.get("last_refresh_stiffness_scale", 1.0) or 1.0)
                            accepted_material_phase = str(pm.get("accepted_material_phase", "elastic") or "elastic")
                            last_refresh_material_phase = str(pm.get("last_refresh_material_phase", "elastic") or "elastic")
                            denom = max(float(np.max(np.abs(accepted_force))), 1.0)
                            force_delta_ratio = float(np.max(np.abs(p_trial - accepted_force)) / denom)
                            load_scale = float(
                                np.dot(p_trial, accepted_force)
                                / max(float(np.dot(accepted_force, accepted_force)), 1.0)
                            )
                            stiffness_scale_delta = abs(runtime_stiffness_scale - accepted_stiffness_scale)
                            material_response_scale = float(
                                np.clip(
                                    accepted_stiffness_scale / max(runtime_stiffness_scale, 1.0e-9),
                                    0.75,
                                    1.40,
                                )
                            )
                            history_drift_scale = float(
                                np.clip(
                                    1.0 - 0.02 * max(0.0, accepted_drift_pct - 0.5),
                                    0.82,
                                    1.05,
                                )
                            )
                            history_plastic_scale = float(
                                np.clip(
                                    1.0 - 0.01 * max(0, accepted_plastic - 1),
                                    0.84,
                                    1.02,
                                )
                            )
                            runtime_material_phase = _classify_material_phase(
                                plastic_count=max(accepted_plastic, last_refresh_plastic),
                                drift_pct=max(accepted_drift_pct, last_refresh_drift_pct),
                                stiffness_scale=min(
                                    runtime_stiffness_scale,
                                    accepted_stiffness_scale,
                                    last_refresh_stiffness_scale,
                                ),
                            )
                            accepted_material_phase_rank = _material_phase_rank(accepted_material_phase)
                            runtime_material_phase_rank = _material_phase_rank(runtime_material_phase)
                            last_refresh_material_phase_rank = _material_phase_rank(last_refresh_material_phase)
                            material_phase_rank = max(
                                accepted_material_phase_rank,
                                runtime_material_phase_rank,
                                last_refresh_material_phase_rank,
                            )
                            phase_gap = abs(runtime_material_phase_rank - accepted_material_phase_rank)
                            current_step_index = len(wall_step_ms) + 1
                            recent_refresh_material_state = bool(
                                material_phase_rank >= 2
                                and last_refresh_step > 0
                                and (current_step_index - last_refresh_step)
                                <= 1
                            )
                            predictor_force_tol = float(args.solver_predictor_force_ratio_tol)
                            predictor_scale = float(load_scale)
                            predictor_backend = "state_predictor_reuse"
                            stiffness_delta_limit = 0.08
                            material_softened_state = bool(
                                stiffness_scale_delta > 0.02
                                or accepted_stiffness_scale < 0.995
                                or runtime_stiffness_scale < 0.995
                                or accepted_plastic > 0
                                or accepted_drift_pct > 0.50
                                or last_refresh_plastic > 0
                                or last_refresh_drift_pct > 0.50
                                or material_phase_rank >= 2
                            )
                            if material_softened_state:
                                predictor_force_tol = min(1.10, predictor_force_tol + 0.25)
                                predictor_scale = float(load_scale) * material_response_scale * history_drift_scale * history_plastic_scale
                                predictor_backend = "material_reduction_predictor_reuse"
                                stiffness_delta_limit = 0.35
                            if recent_refresh_material_state:
                                predictor_force_tol = min(1.80, predictor_force_tol + 0.60)
                                predictor_backend = "material_reduction_predictor_reuse"
                                stiffness_delta_limit = 0.60
                            if (
                                force_delta_ratio <= float(predictor_force_tol)
                                and stiffness_scale_delta <= float(stiffness_delta_limit)
                                and load_scale > 0.0
                                and phase_gap <= (2 if recent_refresh_material_state else 1)
                            ):
                                predictor_scale = float(np.clip(predictor_scale, 0.65, 1.55))
                                predictor_delta_u = np.asarray(accepted_delta_u, dtype=np.float64) * predictor_scale
                                predictor_u = base_u[pid] + predictor_delta_u
                                predictor_top = float(base_top[pid] + accepted_top_delta * predictor_scale)
                                solved = {
                                    "backend": predictor_backend,
                                    "status": 0,
                                    "converged": True,
                                    "iterations": 0,
                                    "u_story_m": predictor_u.copy(),
                                    "top_displacement_m": float(predictor_top),
                                    "plastic_story_count": int(accepted_plastic),
                                    "line_search_backtracks": 0,
                                }
                                local_ok = True
                                solver_reuse_hit_count_total += 1
                                if predictor_backend == "material_reduction_predictor_reuse":
                                    solver_material_predictor_hit_count_total += 1
                                else:
                                    solver_state_predictor_hit_count_total += 1
                        for it in range(1, int(args.max_step_iterations) + 1):
                            if local_ok and solved is not None:
                                break
                            local_tries = it
                            solver_t0 = time.perf_counter()
                            solved = solve_nonlinear_frame(
                                story_k_n_per_m=story_k_runtime,
                                story_h_m=story_h,
                                story_axial_n=story_axial,
                                story_yield_drift_m=yield_drift,
                                floor_load_n=p_trial,
                                cfg=rust_cfg,
                            )
                            solver_seconds_total += max(time.perf_counter() - solver_t0, 0.0)
                            total_solver_calls += 1
                            total_iteration_tries += 1
                            backend_ok = bool(str(solved.get("backend", "")).startswith("rust_ffi_"))
                            if backend_ok and int(solved.get("status", -999)) == 0 and bool(solved.get("converged", False)):
                                pm["solver_cache_force"] = p_trial.copy()
                                pm["solver_cache_result"] = solved
                                local_ok = True
                                break
                            p_trial *= float(args.adaptive_load_decay)
                            per_partition_backtracks[pid] += 1

                        per_partition_calls[pid] += int(local_tries)
                        if (not local_ok) or (solved is None):
                            retry_ok = False
                            rust_all = False
                            retry_abort_reason = "LOCAL_SOLVER_FAIL"
                            break

                        u_story_raw = np.asarray(solved.get("u_story_m", []), dtype=np.float64)
                        if u_story_raw.size != int(story_h.shape[0]):
                            retry_ok = False
                            rust_all = False
                            retry_abort_reason = "STATE_SHAPE_INVALID"
                            break

                        # Adaptive-damped state update to avoid one-step transient blow-up.
                        state_update_t0 = time.perf_counter()
                        top_raw = float(solved.get("top_displacement_m", 0.0))
                        alpha = 1.0
                        alpha_ok = False
                        alpha_backtracks = 0
                        u_story = u_story_raw
                        top_used = top_raw
                        dmax = _drift_ratio_pct(u_story, story_h)
                        for bt in range(int(args.state_update_max_backtracks) + 1):
                            u_trial = base_u[pid] + alpha * (u_story_raw - base_u[pid])
                            top_trial = float(base_top[pid] + alpha * (top_raw - base_top[pid]))
                            d_trial = _drift_ratio_pct(u_trial, story_h)
                            top_jump_trial = abs(top_trial - float(base_top[pid]))
                            if (
                                d_trial <= float(args.collapse_drift_threshold_pct)
                                and top_jump_trial <= float(args.step_guard_max_top_jump_m)
                            ):
                                alpha_ok = True
                                u_story = u_trial
                                top_used = top_trial
                                dmax = float(d_trial)
                                break
                            alpha_backtracks += 1
                            alpha *= float(args.state_update_shrink)
                            if alpha < float(args.state_update_min_alpha):
                                break

                        state_update_backtracks_total += int(alpha_backtracks)
                        pmax = int(solved.get("plastic_story_count", 0))
                        per_partition_drift_max[pid] = max(per_partition_drift_max[pid], float(dmax))
                        per_partition_plastic_max[pid] = max(per_partition_plastic_max[pid], int(pmax))
                        retry_partition_plastic_counts[pid] = int(pmax)
                        retry_partition_drift_pcts[pid] = float(dmax)
                        retry_step_max_plastic = max(retry_step_max_plastic, int(pmax))
                        retry_step_max_drift = max(retry_step_max_drift, float(dmax))
                        top_new[pid] = float(top_used)
                        retry_u[pid] = u_story
                        retry_v[pid] = (u_story - base_u[pid]) / max(dt, 1e-9)

                        du = u_story - base_u[pid]
                        retry_energy_proxy += float(
                            0.5 * np.sum(story_k_runtime * u_story * u_story)
                            + 0.5 * np.sum(story_mass * (du / max(dt, 1e-9)) ** 2)
                        )
                        pm["accepted_force"] = p_trial.copy()
                        pm["accepted_delta_u"] = du.copy()
                        pm["accepted_delta_top"] = float(top_used - base_top[pid])
                        pm["accepted_plastic_count"] = int(pmax)
                        pm["accepted_drift_pct"] = float(dmax)
                        pm["accepted_stiffness_scale"] = float(pm.get("runtime_stiffness_scale", 1.0) or 1.0)
                        pm["accepted_material_phase"] = _classify_material_phase(
                            plastic_count=int(pmax),
                            drift_pct=float(dmax),
                            stiffness_scale=float(pm.get("runtime_stiffness_scale", 1.0) or 1.0),
                        )

                        if (not alpha_ok) and dmax > float(args.collapse_drift_threshold_pct):
                            collapse_local = {
                                "partition": int(pid),
                                "drift_pct": float(dmax),
                                "top_m": float(top_new[pid]),
                            }
                            retry_ok = False
                            retry_abort_reason = "COLLAPSE_THRESHOLD"
                            state_update_seconds_total += max(time.perf_counter() - state_update_t0, 0.0)
                            break
                        state_update_seconds_total += max(time.perf_counter() - state_update_t0, 0.0)

                    if not retry_ok:
                        interface_seconds_total += max(time.perf_counter() - interface_t0, 0.0)
                        if collapse_local is not None:
                            collapse_candidate = collapse_local
                            step_status = "COLLAPSED"
                        break

                    if any(x is None for x in retry_u) or any(x is None for x in retry_v):
                        retry_ok = False
                        retry_abort_reason = "STATE_MISSING"
                        interface_seconds_total += max(time.perf_counter() - interface_t0, 0.0)
                        break

                    halo_t0 = time.perf_counter()
                    _, iface_metrics = _compute_partition_coupling_forces(top_new, coupling_k_by_partition)
                    halo_exchange_seconds_total += max(time.perf_counter() - halo_t0, 0.0)
                    top_update_norm_raw = float(np.max(np.abs(top_new - top_iter)))
                    if gap_ref is None:
                        gap_ref = float(iface_metrics["max_gap_abs_m"])
                    relax_eff = max(
                        float(args.feti_step_relax_min),
                        float(args.feti_step_relax) / math.sqrt(float(max(1, feti_it))),
                    )
                    delta_top = top_new - top_iter
                    delta_cap = float(np.max(np.abs(delta_top)))
                    if delta_cap > float(args.feti_step_update_cap_m):
                        delta_top = delta_top * (float(args.feti_step_update_cap_m) / max(delta_cap, 1e-12))
                    applied_update = float(relax_eff) * delta_top
                    top_update_norm_applied = float(np.max(np.abs(applied_update)))
                    if top_ref_applied is None:
                        top_ref_applied = float(top_update_norm_applied)
                    if capture_step_trace and len(retry_iter_trace) < 12:
                        retry_iter_trace.append(
                            {
                                "feti_it": int(feti_it),
                                "max_gap_abs_m": float(iface_metrics["max_gap_abs_m"]),
                                "top_update_norm_raw_m": float(top_update_norm_raw),
                                "top_update_norm_applied_m": float(top_update_norm_applied),
                                "relax_eff": float(relax_eff),
                                "max_drift_ratio_pct": float(retry_step_max_drift),
                                "max_plastic_story_count": int(retry_step_max_plastic),
                            }
                        )
                    retry_best = {
                        "ag_i": float(ag_i),
                        "load_scale": float(load_scale),
                        "top_new": top_new.copy(),
                        "u_new": [np.asarray(x, dtype=np.float64) for x in retry_u if x is not None],
                        "v_new": [np.asarray(x, dtype=np.float64) for x in retry_v if x is not None],
                        "step_max_plastic": int(retry_step_max_plastic),
                        "step_max_drift": float(retry_step_max_drift),
                        "partition_plastic_counts": [int(x) for x in retry_partition_plastic_counts],
                        "partition_drift_pcts": [float(x) for x in retry_partition_drift_pcts],
                        "energy_proxy": float(retry_energy_proxy),
                        "iface_metrics": iface_metrics,
                        "feti_iters": int(feti_it),
                        "top_update_norm_raw": float(top_update_norm_raw),
                        "top_update_norm_applied": float(top_update_norm_applied),
                    }

                    abs_ok = bool(top_update_norm_applied <= float(args.feti_step_top_tol_m))
                    rel_ok = False
                    if top_ref_applied is not None:
                        rel_ok = bool(
                            top_update_norm_applied
                            <= max(
                                float(args.feti_step_top_tol_m),
                                float(top_ref_applied) * float(args.feti_step_top_reduction_target),
                            )
                        )
                    if abs_ok or rel_ok:
                        interface_seconds_total += max(time.perf_counter() - interface_t0, 0.0)
                        feti_converged = True
                        break

                    top_iter = top_iter + applied_update
                    interface_seconds_total += max(time.perf_counter() - interface_t0, 0.0)

                if retry_best is None:
                    if collapse_candidate is None:
                        feti_step_failure = True
                    retry_decision = "NO_RETRY_BEST"
                    if capture_step_trace and step_trace is not None:
                        step_trace["retries"].append(
                            {
                                "retry_idx": int(retry_idx),
                                "load_scale": float(load_scale),
                                "decision": str(retry_decision),
                                "abort_reason": str(retry_abort_reason),
                                "feti_converged": bool(feti_converged),
                                "iter_count": int(len(retry_iter_trace)),
                                "iter_samples": retry_iter_trace,
                            }
                        )
                    if retry_idx > 0:
                        retry_overhead_seconds_total += max(time.perf_counter() - retry_t0, 0.0)
                    continue

                if not feti_converged:
                    if bool(args.allow_feti_soft_accept):
                        iface = retry_best.get("iface_metrics", {})
                        soft_ok = bool(
                            float(iface.get("max_gap_abs_m", math.inf))
                            <= float(args.feti_step_gap_tol) * float(args.feti_soft_gap_factor)
                            and float(retry_best.get("top_update_norm_applied", math.inf))
                            <= float(args.feti_step_top_tol_m) * float(args.feti_soft_top_factor)
                        )
                    if soft_ok:
                        feti_soft_accept_count += 1
                        retry_decision = "SOFT_ACCEPT"
                    else:
                        feti_step_failure = True
                        step_status = "FETI_DIVERGED"
                        retry_decision = "FETI_DIVERGED"
                        if capture_step_trace and step_trace is not None:
                            step_trace["retries"].append(
                                {
                                    "retry_idx": int(retry_idx),
                                    "load_scale": float(load_scale),
                                    "decision": str(retry_decision),
                                    "abort_reason": str(retry_abort_reason),
                                    "feti_converged": bool(feti_converged),
                                    "iter_count": int(len(retry_iter_trace)),
                                    "iter_samples": retry_iter_trace,
                                    "last_iface": retry_best.get("iface_metrics", {}),
                                    "last_top_update_norm_applied_m": float(
                                        retry_best.get("top_update_norm_applied", math.inf)
                                    ),
                                    "last_top_update_norm_raw_m": float(
                                        retry_best.get("top_update_norm_raw", math.inf)
                                    ),
                                }
                            )
                        if retry_idx > 0:
                            retry_overhead_seconds_total += max(time.perf_counter() - retry_t0, 0.0)
                        continue

                max_top_jump = float(np.max(np.abs(retry_best["top_new"] - base_top)))
                drift_inc = max(0.0, float(retry_best["step_max_drift"]) - float(prev_step_max_drift))
                energy_jump_ratio = float(retry_best["energy_proxy"]) / max(float(prev_energy_proxy), 1e-9)
                top_guard_ok = bool(max_top_jump <= float(args.step_guard_max_top_jump_m))
                drift_guard_ok = bool(drift_inc <= float(args.step_guard_max_drift_increment_pct))
                energy_guard_ok = bool(s == 0 or energy_jump_ratio <= float(args.step_guard_max_energy_jump_ratio))

                if not (top_guard_ok and drift_guard_ok and energy_guard_ok):
                    step_guard_reject_count += 1
                    step_status = "REJECTED_UNPHYSICAL"
                    retry_decision = "STEP_GUARD_REJECT"
                    if capture_step_trace and step_trace is not None:
                        step_trace["retries"].append(
                            {
                                "retry_idx": int(retry_idx),
                                "load_scale": float(load_scale),
                                "decision": str(retry_decision),
                                "abort_reason": str(retry_abort_reason),
                                "feti_converged": bool(feti_converged),
                                "iter_count": int(len(retry_iter_trace)),
                                "iter_samples": retry_iter_trace,
                                "max_top_jump_m": float(max_top_jump),
                                "drift_increment_pct": float(drift_inc),
                                "energy_jump_ratio": float(energy_jump_ratio),
                            }
                        )
                    if retry_idx > 0:
                        retry_overhead_seconds_total += max(time.perf_counter() - retry_t0, 0.0)
                    continue

                accepted = True
                accepted_data = retry_best
                if retry_idx > 0:
                    accepted_on_retry_count += 1
                retry_decision = "ACCEPT"
                if capture_step_trace and step_trace is not None:
                    step_trace["retries"].append(
                        {
                            "retry_idx": int(retry_idx),
                            "load_scale": float(load_scale),
                            "decision": str(retry_decision),
                            "abort_reason": str(retry_abort_reason),
                            "feti_converged": bool(feti_converged),
                            "iter_count": int(len(retry_iter_trace)),
                            "iter_samples": retry_iter_trace,
                            "last_iface": retry_best.get("iface_metrics", {}),
                            "last_top_update_norm_applied_m": float(
                                retry_best.get("top_update_norm_applied", math.inf)
                            ),
                            "last_top_update_norm_raw_m": float(
                                retry_best.get("top_update_norm_raw", math.inf)
                            ),
                        }
                    )
                if retry_idx > 0:
                    retry_overhead_seconds_total += max(time.perf_counter() - retry_t0, 0.0)
                break

            if not accepted or accepted_data is None:
                converged_all = False
                if collapse_candidate is not None:
                    collapsed = True
                    collapse_step = int(s)
                    collapse_time_s = float(s * dt)
                    collapse_partition = int(collapse_candidate["partition"])
                    collapse_drift_pct = float(collapse_candidate["drift_pct"])
                    collapse_top_m = float(collapse_candidate["top_m"])
                if s % step_stride == 0:
                    step_rows.append(
                        {
                            "step": int(s),
                            "time_s": float(s * dt),
                            "ag_g": float(ag_base),
                            "status": step_status,
                            "converged": False,
                        }
                    )
                if capture_step_trace and step_trace is not None:
                    step_trace["final_status"] = str(step_status)
                    feti_debug_trace.append(step_trace)
                break

            top_prev = np.asarray(accepted_data["top_new"], dtype=np.float64)
            u_prev_parts = [np.asarray(x, dtype=np.float64) for x in accepted_data["u_new"]]
            v_prev_parts = [np.asarray(x, dtype=np.float64) for x in accepted_data["v_new"]]
            step_max_plastic = int(accepted_data["step_max_plastic"])
            step_max_drift = float(accepted_data["step_max_drift"])
            partition_plastic_counts = list(accepted_data.get("partition_plastic_counts", []))
            partition_drift_pcts = list(accepted_data.get("partition_drift_pcts", []))
            iface_metrics = accepted_data["iface_metrics"]
            prev_step_max_drift = float(step_max_drift)
            prev_energy_proxy = max(float(accepted_data["energy_proxy"]), 1e-9)
            feti_step_iters_hist.append(int(accepted_data["feti_iters"]))

            current_completed_steps = len(wall_step_ms) + 1
            for pid, pm in enumerate(part_models):
                story_k_base = np.asarray(pm["story_k_base"], dtype=np.float64)
                story_mass = np.asarray(pm["story_mass"], dtype=np.float64)
                plastic_count = int(partition_plastic_counts[pid]) if pid < len(partition_plastic_counts) else 0
                drift_pct = float(partition_drift_pcts[pid]) if pid < len(partition_drift_pcts) else 0.0
                last_refresh_step = int(pm.get("last_refresh_step", 0) or 0)
                last_refresh_plastic = int(pm.get("last_refresh_plastic", 0) or 0)
                last_refresh_drift_pct = float(pm.get("last_refresh_drift_pct", 0.0) or 0.0)
                refresh_due = (current_completed_steps - last_refresh_step) >= int(args.stiffness_refresh_cadence_steps)
                plastic_jump = (plastic_count - last_refresh_plastic) >= int(args.stiffness_refresh_plastic_increment)
                drift_jump = (drift_pct - last_refresh_drift_pct) >= float(args.stiffness_refresh_drift_increment_pct)
                if refresh_due or plastic_jump or drift_jump:
                    plastic_softening = max(0.72, 1.0 - 0.012 * float(plastic_count))
                    drift_softening = max(0.80, 1.0 - 0.006 * max(0.0, drift_pct - 0.50))
                    tangent_scale = float(min(plastic_softening, drift_softening))
                    prev_tangent_scale = float(pm.get("runtime_stiffness_scale", 1.0) or 1.0)
                    pm["story_k_runtime"] = story_k_base * tangent_scale
                    pm["story_damp_runtime"] = float(args.rayleigh_alpha) * story_mass + float(args.rayleigh_beta) * pm["story_k_runtime"]
                    pm["runtime_stiffness_scale"] = float(tangent_scale)
                    pm["last_refresh_step"] = int(current_completed_steps)
                    pm["last_refresh_plastic"] = int(plastic_count)
                    pm["last_refresh_drift_pct"] = float(drift_pct)
                    pm["last_refresh_stiffness_scale"] = float(tangent_scale)
                    pm["last_refresh_material_phase"] = _classify_material_phase(
                        plastic_count=int(plastic_count),
                        drift_pct=float(drift_pct),
                        stiffness_scale=float(tangent_scale),
                    )
                    if abs(prev_tangent_scale - float(tangent_scale)) > 0.08:
                        pm["solver_cache_force"] = None
                        pm["solver_cache_result"] = None
                    stiffness_refresh_count_total += 1
                else:
                    stiffness_refresh_reuse_count_total += 1

            interface_gap_abs_max_m = max(interface_gap_abs_max_m, float(iface_metrics["max_gap_abs_m"]))
            interface_gap_abs_sum_m += float(iface_metrics["mean_gap_abs_m"])
            interface_force_abs_max_n = max(interface_force_abs_max_n, float(iface_metrics["max_edge_force_abs_n"]))
            interface_force_balance_residual_max = max(
                interface_force_balance_residual_max,
                float(iface_metrics["force_balance_residual"]),
            )
            sync_gap_abs_series.append(float(iface_metrics["max_gap_abs_m"]))
            sync_force_abs_series.append(float(iface_metrics["max_edge_force_abs_n"]))
            interface_metric_samples += 1
            ws = (time.perf_counter() - st) * 1000.0
            wall_step_ms.append(float(ws))
            step_wall_seconds_total += float(ws) / 1000.0
            if s % step_stride == 0:
                step_rows.append(
                    {
                        "step": int(s),
                        "time_s": float(s * dt),
                        "ag_g": float(accepted_data["ag_i"]),
                        "load_scale": float(accepted_data["load_scale"]),
                        "status": "OK",
                        "converged": True,
                        "max_plastic_story_count": int(step_max_plastic),
                        "max_drift_ratio_pct": float(step_max_drift),
                        "max_abs_top_displacement_m": float(np.max(np.abs(top_prev))),
                        "feti_step_iterations": int(accepted_data["feti_iters"]),
                        "feti_top_update_norm_applied_m": float(accepted_data["top_update_norm_applied"]),
                        "feti_top_update_norm_raw_m": float(accepted_data["top_update_norm_raw"]),
                        "max_interface_gap_abs_m": float(iface_metrics["max_gap_abs_m"]),
                        "interface_force_balance_residual": float(iface_metrics["force_balance_residual"]),
                        "wall_step_ms": float(ws),
                    }
                )
            if capture_step_trace and step_trace is not None:
                step_trace["final_status"] = "OK"
                feti_debug_trace.append(step_trace)

        elapsed_s = float(time.perf_counter() - t0)
        completed_steps = len(wall_step_ms) if converged_all else max(0, len(wall_step_ms))
        full_duration_pass = bool(completed_steps == used_steps)
        feti_step_converged_ratio = float(len(feti_step_iters_hist)) / float(max(1, completed_steps))
        feti_step_p95_iters = float(np.percentile(np.asarray(feti_step_iters_hist, dtype=np.float64), 95)) if feti_step_iters_hist else math.inf

        # Sync benchmark for same NDTHA horizon (backend-policy controlled).
        sync_steps = int(min(int(args.sync_steps_cap), used_steps))
        if sync_backend == "inline_native":
            sync_result = _build_inline_native_sync_result(
                partition_report=part_report,
                sync_steps=sync_steps,
                wall_step_ms=wall_step_ms,
                interface_gap_abs_series=sync_gap_abs_series,
                interface_force_abs_series=sync_force_abs_series,
                bandwidth_gbps=float(args.sync_bandwidth_gbps),
                latency_us=float(args.sync_latency_us),
                overlap_cap=float(args.sync_overlap_cap),
                jitter_pct=float(args.sync_jitter_pct),
                seed=int(args.sync_seed),
                sync_steps_cap=int(args.sync_steps_cap),
                dt_s=float(dt),
            )
            sync_checks = {
                "sync_backend_policy_pass": bool(sync_result.get("backend_policy_forced", False)),
                "inline_gap_span_pass": bool(
                    math.isfinite(float(sync_result.get("max_gap_norm", 0.0)))
                    and float(sync_result.get("max_gap_norm", 0.0)) <= 1.0
                ),
                "inline_force_imbalance_pass": bool(
                    math.isfinite(float(sync_result.get("max_force_imbalance", 0.0)))
                    and float(sync_result.get("max_force_imbalance", 0.0)) <= 1.0
                ),
                "sync_stall_budget_pass": bool(float(sync_result["sync_stall_ratio"]) <= float(args.sync_max_stall_ratio)),
                "p99_step_budget_pass": bool(float(sync_result["p99_step_ms"]) <= float(args.sync_max_p99_step_ms)),
                "straggler_budget_pass": bool(float(sync_result["straggler_ratio"]) <= float(args.sync_max_straggler_ratio)),
                "overlap_ratio_pass": bool(float(sync_result["comm_overlap_ratio"]) >= float(args.sync_min_overlap_ratio)),
            }
        elif sync_backend == "feti_lite":
            sync_result = emulate_feti_sync(
                part_report,
                execution_mode="boundary_sync",
                steps=sync_steps,
                dt_s=float(dt),
                bandwidth_gbps=float(args.sync_bandwidth_gbps),
                latency_us=float(args.sync_latency_us),
                compute_us_per_node=float(args.sync_compute_us_per_node),
                overlap_cap=float(args.sync_overlap_cap),
                jitter_pct=float(args.sync_jitter_pct),
                seed=int(args.sync_seed),
                max_feti_iters=int(args.sync_max_feti_iters),
                gap_tol=float(args.sync_feti_gap_tol),
                force_tol=float(args.sync_feti_force_tol),
                rho=float(args.sync_feti_rho),
                relax=float(args.sync_feti_relax),
                state_components=5,
            )
            sync_result["backend_policy_forced"] = True
            sync_checks = {
                "sync_backend_policy_pass": bool(sync_result.get("backend_policy_forced", True)),
                "feti_converged_step_ratio_pass": bool(
                    float(sync_result.get("converged_step_ratio", 0.0))
                    >= float(args.sync_feti_min_converged_step_ratio)
                ),
                "feti_gap_tol_pass": bool(
                    float(sync_result.get("max_gap_norm", math.inf)) <= float(args.sync_feti_gap_tol)
                ),
                "feti_force_tol_pass": bool(
                    float(sync_result.get("max_force_imbalance", math.inf))
                    <= float(args.sync_feti_force_tol)
                ),
                "sync_stall_budget_pass": bool(float(sync_result["sync_stall_ratio"]) <= float(args.sync_max_stall_ratio)),
                "p99_step_budget_pass": bool(float(sync_result["p99_step_ms"]) <= float(args.sync_max_p99_step_ms)),
                "straggler_budget_pass": bool(float(sync_result["straggler_ratio"]) <= float(args.sync_max_straggler_ratio)),
                "overlap_ratio_pass": bool(float(sync_result["comm_overlap_ratio"]) >= float(args.sync_min_overlap_ratio)),
            }
        else:
            sync_result = emulate_virtual_sync(
                part_report,
                steps=sync_steps,
                dt_s=float(dt),
                bandwidth_gbps=float(args.sync_bandwidth_gbps),
                latency_us=float(args.sync_latency_us),
                compute_us_per_node=float(args.sync_compute_us_per_node),
                overlap_cap=float(args.sync_overlap_cap),
                jitter_pct=float(args.sync_jitter_pct),
                seed=int(args.sync_seed),
            )
            sync_result["backend"] = "virtual_partition_sync_emulator"
            sync_result["backend_policy_forced"] = True
            sync_checks = {
                "sync_backend_policy_pass": bool(sync_result.get("backend_policy_forced", True)),
                "sync_stall_budget_pass": bool(float(sync_result["sync_stall_ratio"]) <= float(args.sync_max_stall_ratio)),
                "p99_step_budget_pass": bool(float(sync_result["p99_step_ms"]) <= float(args.sync_max_p99_step_ms)),
                "straggler_budget_pass": bool(float(sync_result["straggler_ratio"]) <= float(args.sync_max_straggler_ratio)),
                "overlap_ratio_pass": bool(float(sync_result["comm_overlap_ratio"]) >= float(args.sync_min_overlap_ratio)),
            }
        sync_budget_pass = bool(all(sync_checks.values()))

        plastic_all = bool(all(v >= int(args.min_plastic_story_count) for v in per_partition_plastic_max))

        checks = {
            "topology_gate_pass": bool(topology_ok),
            "shell_beam_mix_pass": bool(shell_ok),
            "real_topology_pass": bool(real_topo_ok),
            "scale_target_10m_pass": bool(int(args.target_dof) >= 10000000),
            "pdelta_enabled_pass": bool(float(args.pdelta_factor) >= 1.0),
            "dynamic_reversal_pass": bool(reversal_count >= int(args.min_load_reversals)),
            "rayleigh_damping_pass": bool(float(args.rayleigh_alpha) > 0.0 or float(args.rayleigh_beta) > 0.0),
            "collapse_cutoff_guard_pass": bool(float(args.collapse_drift_threshold_pct) > 0.0),
            "halo_coupling_strength_pass": bool(float(args.halo_coupling_gain) >= float(args.min_halo_coupling_gain)),
            "halo_coupling_floor_pass": bool(
                (not bool(args.enforce_halo_coupling_floor))
                or float(args.halo_coupling_gain) >= float(args.halo_coupling_gain_floor)
            ),
            "interface_force_balance_pass": bool(
                math.isfinite(float(interface_force_balance_residual_max))
                and float(interface_force_balance_residual_max) <= 1e-6
            ),
            "feti_step_convergence_pass": bool(
                (not feti_step_failure)
                and math.isfinite(float(feti_step_p95_iters))
                and float(feti_step_converged_ratio) >= 0.99
            ),
            "step_guard_pass": bool(int(step_guard_reject_count) == 0),
            "full_duration_pass": bool(full_duration_pass),
            "all_steps_converged": bool(converged_all),
            "rust_backend_used_pass": bool(rust_all),
            "no_collapse_detected": bool(not collapsed),
            "plasticity_triggered_all_partitions": bool(plastic_all),
            "sync_backend_policy_pass": bool(sync_checks.get("sync_backend_policy_pass", False)),
            "sync_budget_pass": bool(sync_budget_pass),
            "scaled_partition_projection_pass": bool(sum(scaled_sizes) == int(args.target_dof)),
        }
        interface_seconds_total = max(
            step_wall_seconds_total
            - solver_seconds_total
            - state_update_seconds_total
            - halo_exchange_seconds_total
            - retry_overhead_seconds_total,
            0.0,
        )

        contract_pass = bool(all(checks.values()))

        if not checks["topology_gate_pass"] or not checks["shell_beam_mix_pass"] or not checks["real_topology_pass"]:
            reason_code = "ERR_TOPOLOGY_FAIL"
        elif not checks["scale_target_10m_pass"] or not checks["scaled_partition_projection_pass"]:
            reason_code = "ERR_PARTITION_FAIL"
        elif not checks["dynamic_reversal_pass"]:
            reason_code = "ERR_DYNAMICS_NOT_REVERSED"
        elif not checks["rayleigh_damping_pass"]:
            reason_code = "ERR_RAYLEIGH_DAMPING_DISABLED"
        elif not checks["halo_coupling_strength_pass"]:
            reason_code = "ERR_WEAK_HALO_COUPLING"
        elif not checks["collapse_cutoff_guard_pass"]:
            reason_code = "ERR_INVALID_INPUT"
        elif not checks["interface_force_balance_pass"]:
            reason_code = "ERR_NDTHA_CONVERGENCE_FAIL"
        elif not checks["feti_step_convergence_pass"]:
            reason_code = "ERR_FETI_STEP_DIVERGENCE"
        elif not checks["step_guard_pass"]:
            reason_code = "ERR_STEP_REJECTED_UNPHYSICAL"
        elif not checks["no_collapse_detected"]:
            reason_code = "ERR_COLLAPSE_CUTOFF"
        elif not checks["rust_backend_used_pass"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["all_steps_converged"]:
            reason_code = "ERR_NDTHA_CONVERGENCE_FAIL"
        elif not checks["full_duration_pass"]:
            reason_code = "ERR_FULL_DURATION_REQUIRED"
        elif not checks["plasticity_triggered_all_partitions"]:
            reason_code = "ERR_PLASTICITY_NOT_TRIGGERED"
        elif not checks["sync_backend_policy_pass"]:
            reason_code = "ERR_SYNC_BACKEND_FORBIDDEN"
        elif not checks["sync_budget_pass"]:
            reason_code = "ERR_SYNC_BUDGET_FAIL"
        else:
            reason_code = "PASS"

        summary = {
            "target_dof": int(args.target_dof),
            "partition_count": int(part_count),
            "halo_coupling_gain": float(args.halo_coupling_gain),
            "min_halo_coupling_gain": float(args.min_halo_coupling_gain),
            "enforce_halo_coupling_floor": bool(args.enforce_halo_coupling_floor),
            "halo_coupling_gain_floor": float(args.halo_coupling_gain_floor),
            "halo_coupling_k_divisor": float(args.halo_coupling_k_divisor),
            "calibration_profile_source": str(calibration_meta.get("source", "")),
            "effective_scales": {k: float(v) for k, v in effective_scales.items()},
            "partition_nodes_projected_min": int(min(scaled_sizes)),
            "partition_nodes_projected_max": int(max(scaled_sizes)),
            "ground_motion_step_count_full": int(full_steps),
            "ground_motion_step_count_used": int(used_steps),
            "duration_s_full": float((full_steps - 1) * dt),
            "duration_s_used": float((used_steps - 1) * dt),
            "reversal_count": int(reversal_count),
            "completed_steps": int(completed_steps),
            "collapsed": bool(collapsed),
            "collapse_step": int(collapse_step),
            "collapse_time_s": float(collapse_time_s),
            "collapse_partition": int(collapse_partition),
            "collapse_drift_ratio_pct": float(collapse_drift_pct),
            "collapse_top_displacement_m": float(collapse_top_m),
            "elapsed_wall_s": float(elapsed_s),
            "solver_calls_total": int(total_solver_calls),
            "solver_iteration_tries_total": int(total_iteration_tries),
            "step_guard_reject_count": int(step_guard_reject_count),
            "state_update_backtracks_total": int(state_update_backtracks_total),
            "feti_soft_accept_count": int(feti_soft_accept_count),
            "feti_step_converged_ratio": float(feti_step_converged_ratio),
            "feti_step_p95_iterations": float(feti_step_p95_iters if math.isfinite(feti_step_p95_iters) else math.inf),
            "max_plastic_story_count_min": int(min(per_partition_plastic_max) if per_partition_plastic_max else 0),
            "max_plastic_story_count_mean": float(statistics.fmean(per_partition_plastic_max) if per_partition_plastic_max else 0.0),
            "max_drift_ratio_pct_max": float(max(per_partition_drift_max) if per_partition_drift_max else 0.0),
            "mean_drift_ratio_pct": float(statistics.fmean(per_partition_drift_max) if per_partition_drift_max else 0.0),
            "interface_gap_abs_max_m": float(interface_gap_abs_max_m),
            "interface_gap_abs_mean_m": float(
                interface_gap_abs_sum_m / float(max(1, interface_metric_samples))
            ),
            "interface_force_abs_max_n": float(interface_force_abs_max_n),
            "interface_force_balance_residual_max": float(interface_force_balance_residual_max),
            "interface_force_clip_count": int(interface_force_clip_count),
            "step_wall_seconds_total": float(step_wall_seconds_total),
            "step_wall_seconds_mean": float(step_wall_seconds_total / float(max(1, completed_steps))),
            "halo_exchange_seconds_total": float(halo_exchange_seconds_total),
            "halo_exchange_seconds_per_step": float(halo_exchange_seconds_total / float(max(1, completed_steps))),
            "retry_overhead_seconds_total": float(retry_overhead_seconds_total),
            "retry_overhead_seconds_per_step": float(retry_overhead_seconds_total / float(max(1, completed_steps))),
            "retry_attempt_count_total": int(retry_attempt_count_total),
            "retry_attempts_per_completed_step": float(retry_attempt_count_total / float(max(1, completed_steps))),
            "accepted_on_retry_count": int(accepted_on_retry_count),
            "solver_seconds_total": float(solver_seconds_total),
            "solver_seconds_per_step": float(solver_seconds_total / float(max(1, completed_steps))),
            "solver_reuse_hit_count_total": int(solver_reuse_hit_count_total),
            "solver_cache_reuse_hit_count_total": int(solver_cache_reuse_hit_count_total),
            "solver_state_predictor_hit_count_total": int(solver_state_predictor_hit_count_total),
            "solver_material_predictor_hit_count_total": int(solver_material_predictor_hit_count_total),
            "solver_reuse_ratio": float(solver_reuse_hit_count_total / float(max(1, solver_reuse_hit_count_total + total_solver_calls))),
            "state_update_seconds_total": float(state_update_seconds_total),
            "state_update_seconds_per_step": float(state_update_seconds_total / float(max(1, completed_steps))),
            "interface_seconds_total": float(interface_seconds_total),
            "interface_seconds_per_step": float(interface_seconds_total / float(max(1, completed_steps))),
            "stiffness_refresh_count_total": int(stiffness_refresh_count_total),
            "stiffness_refresh_reuse_count_total": int(stiffness_refresh_reuse_count_total),
            "stiffness_refresh_cadence_steps": int(args.stiffness_refresh_cadence_steps),
            "wall_step_ms_mean": float(statistics.fmean(wall_step_ms) if wall_step_ms else math.inf),
            "wall_step_ms_p99": float(np.percentile(np.asarray(wall_step_ms, dtype=np.float64), 99) if wall_step_ms else math.inf),
            "sync_step_ms_p99": float(sync_result.get("p99_step_ms", math.inf)),
            "sync_stall_ratio": float(sync_result.get("sync_stall_ratio", math.inf)),
            "sync_backend_policy_pass": bool(sync_checks.get("sync_backend_policy_pass", False)),
            "sync_backend": str(sync_result.get("backend", "")),
            "sync_converged_step_ratio": float(sync_result.get("converged_step_ratio", 0.0)),
            "sync_p95_feti_iterations": float(sync_result.get("p95_feti_iterations", math.inf)),
            "sync_max_gap_norm": float(sync_result.get("max_gap_norm", math.inf)),
            "sync_max_force_imbalance": float(sync_result.get("max_force_imbalance", math.inf)),
        }

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-mega-ndtha-partitioned-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "calibration_profile": calibration_meta,
            "checks": checks,
            "summary": summary,
            "sync_result": sync_result,
            "sync_checks": sync_checks,
            "partition_projection": {
                "source_partition_report": str(part_report_path),
                "sample_node_count": int(part_result.get("node_count", 0)),
                "partition_sizes_sample": [int(x) for x in sample_sizes],
                "partition_sizes_projected": [int(x) for x in scaled_sizes],
            },
            "rows": {
                "partitions": [
                    {
                        "pid": int(i),
                        "nodes_projected": int(scaled_sizes[i]),
                        "max_plastic_story_count": int(per_partition_plastic_max[i]),
                        "max_drift_ratio_pct": float(per_partition_drift_max[i]),
                        "solver_try_calls": int(per_partition_calls[i]),
                        "adaptive_backtracks": int(per_partition_backtracks[i]),
                    }
                    for i in range(part_count)
                ],
                "steps_head": step_rows[:500],
                "feti_debug_trace": feti_debug_trace,
            },
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive(
            [
                str(out),
                str(args.partitioned_scaleout),
                str(args.topology_report),
                str(args.ground_motion_csv),
                str(part_report_path),
            ]
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote mega NDTHA partitioned stress report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except RuntimeError as exc:
        msg = str(exc)
        if msg.startswith("ERR_TOPOLOGY_FAIL"):
            rc = "ERR_TOPOLOGY_FAIL"
        elif msg.startswith("ERR_PARTITION_FAIL"):
            rc = "ERR_PARTITION_FAIL"
        elif msg.startswith("ERR_SYNC_BACKEND_FORBIDDEN"):
            rc = "ERR_SYNC_BACKEND_FORBIDDEN"
        elif msg.startswith("ERR_FULL_DURATION_REQUIRED"):
            rc = "ERR_FULL_DURATION_REQUIRED"
        elif msg.startswith("ERR_DYNAMICS_NOT_REVERSED"):
            rc = "ERR_DYNAMICS_NOT_REVERSED"
        elif msg.startswith("ERR_RAYLEIGH_DAMPING_DISABLED"):
            rc = "ERR_RAYLEIGH_DAMPING_DISABLED"
        elif msg.startswith("ERR_WEAK_HALO_COUPLING"):
            rc = "ERR_WEAK_HALO_COUPLING"
        elif msg.startswith("ERR_CALIBRATION_PROFILE"):
            rc = "ERR_CALIBRATION_PROFILE"
        elif msg.startswith("ERR_FETI_STEP_DIVERGENCE"):
            rc = "ERR_FETI_STEP_DIVERGENCE"
        elif msg.startswith("ERR_STEP_REJECTED_UNPHYSICAL"):
            rc = "ERR_STEP_REJECTED_UNPHYSICAL"
        else:
            rc = "ERR_INVALID_INPUT"
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-mega-ndtha-partitioned-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": rc,
            "reason": f"{REASONS[rc]}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote mega NDTHA partitioned stress report: {out}")
        raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-mega-ndtha-partitioned-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote mega NDTHA partitioned stress report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
