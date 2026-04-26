#!/usr/bin/env python3
"""P0 solver-wide HIP end-to-end contract.

This contract is intentionally stricter than HIP smoke:
- zero-copy strict probe must already be green
- nonlinear frame static loop must expose GPU main-loop telemetry
- nonlinear frame NDTHA loop must expose GPU main-loop telemetry
- track LF loop must expose GPU main-loop telemetry

If any solver path still reports CPU residency, the contract fails and keeps
the commercialization gap explicitly open.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    RustNonlinearNdthaConfig,
    build_story_load_profile,
    solve_nonlinear_frame,
    solve_nonlinear_frame_ndtha,
)
from rust_track_lf_bridge import RustTrackConfig, solve_track_point_load
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "solver-wide hip end-to-end contract passed",
    "ERR_INVALID_INPUT": "invalid solver hip e2e input",
    "ERR_STRICT_PROBE_FAIL": "strict zero-copy probe is not gpu-strict clean",
    "ERR_NONLINEAR_FRAME_GPU_FAIL": "nonlinear frame static loop is not GPU-resident",
    "ERR_NDTHA_GPU_FAIL": "nonlinear frame NDTHA loop is not GPU-resident",
    "ERR_TRACK_GPU_FAIL": "track LF loop is not GPU-resident",
    "ERR_PRODUCTION_KERNEL_FAIL": "one or more solver paths did not prove production-kernel residency",
    "ERR_SURROGATE_RUNTIME_FAIL": "one or more solver paths still advertise surrogate or simplified runtime markers",
    "ERR_GPU_POLICY_FAIL": "one or more solver paths violated GPU-only policy",
}


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["strict_probe", "min_device_residency_ratio", "out"],
    "properties": {
        "strict_probe": {"type": "string", "minLength": 1},
        "min_device_residency_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(x: object, default: float = 0.0) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    return v if math.isfinite(v) else default


def _runtime_gpu_pass(runtime: dict[str, Any], *, min_device_residency_ratio: float) -> tuple[bool, dict[str, Any]]:
    backend = str(runtime.get("main_loop_backend", runtime.get("runtime_backend", ""))).strip()
    hip_kernel_invocation_count = int(_finite(runtime.get("hip_kernel_invocation_count", 0), 0.0))
    cpu_backend = bool(runtime.get("cpu_backend", False))
    cpu_required = bool(runtime.get("cpu_required", False))
    cpu_fallback_used = bool(runtime.get("cpu_fallback_used", False))
    host_copy_bytes = int(_finite(runtime.get("host_copy_bytes", 0), 0.0))
    device_residency_ratio = _finite(runtime.get("device_residency_ratio", 0.0), 0.0)
    backend_tag = backend.lower()
    backend_gpu_named = ("hip" in backend_tag) or ("rocm" in backend_tag) or ("cuda" in backend_tag)
    passed = bool(
        backend_gpu_named
        and hip_kernel_invocation_count > 0
        and not cpu_backend
        and not cpu_required
        and not cpu_fallback_used
        and host_copy_bytes == 0
        and device_residency_ratio >= float(min_device_residency_ratio)
    )
    return passed, {
        "main_loop_backend": backend,
        "solver_path_kind": str(runtime.get("solver_path_kind", "")),
        "production_kernel_path": bool(runtime.get("production_kernel_path", False)),
        "force_jacobian_kernel_consistent": bool(runtime.get("force_jacobian_kernel_consistent", False)),
        "surrogate_runtime_used": bool(runtime.get("surrogate_runtime_used", False)),
        "simplified_runtime_used": bool(runtime.get("simplified_runtime_used", False)),
        "surrogate_runtime_markers": [
            str(item).strip()
            for item in (runtime.get("surrogate_runtime_markers") or [])
            if str(item).strip()
        ],
        "hip_kernel_invocation_count": hip_kernel_invocation_count,
        "cpu_backend": cpu_backend,
        "cpu_required": cpu_required,
        "cpu_fallback_used": cpu_fallback_used,
        "host_copy_bytes": host_copy_bytes,
        "device_residency_ratio": device_residency_ratio,
        "gpu_main_loop_pass": passed,
    }


def _runtime_production_kernel_pass(runtime: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    solver_path_kind = str(runtime.get("solver_path_kind", "") or "").strip().lower()
    production_kernel_path = bool(runtime.get("production_kernel_path", False))
    force_jacobian_kernel_consistent = bool(runtime.get("force_jacobian_kernel_consistent", False))
    passed = bool(
        production_kernel_path
        and force_jacobian_kernel_consistent
        and ("production" in solver_path_kind or "hip_kernel" in solver_path_kind)
    )
    return passed, {
        "solver_path_kind": str(runtime.get("solver_path_kind", "")),
        "production_kernel_path": production_kernel_path,
        "force_jacobian_kernel_consistent": force_jacobian_kernel_consistent,
        "production_kernel_pass": passed,
    }


def _runtime_surrogate_free_pass(runtime: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    surrogate_runtime_used = bool(runtime.get("surrogate_runtime_used", False))
    simplified_runtime_used = bool(runtime.get("simplified_runtime_used", False))
    surrogate_runtime_markers = [
        str(item).strip()
        for item in (runtime.get("surrogate_runtime_markers") or [])
        if str(item).strip()
    ]
    passed = bool(
        not surrogate_runtime_used
        and not simplified_runtime_used
        and not surrogate_runtime_markers
    )
    return passed, {
        "surrogate_runtime_used": surrogate_runtime_used,
        "simplified_runtime_used": simplified_runtime_used,
        "surrogate_runtime_markers": surrogate_runtime_markers,
        "surrogate_runtime_free_pass": passed,
    }


def _append_solver_result(
    row_results: list[dict[str, Any]],
    *,
    solver: str,
    elapsed_seconds: float,
    runtime: dict[str, Any],
    backend: str,
    status_fields: dict[str, Any],
    metadata: dict[str, Any] | None,
    min_device_residency_ratio: float,
) -> tuple[bool, bool, bool]:
    gpu_pass, diag = _runtime_gpu_pass(runtime, min_device_residency_ratio=min_device_residency_ratio)
    production_pass, production_diag = _runtime_production_kernel_pass(runtime)
    surrogate_free_pass, surrogate_diag = _runtime_surrogate_free_pass(runtime)
    diag.update(production_diag)
    diag.update(surrogate_diag)
    row_results.append(
        {
            "solver": solver,
            "elapsed_seconds": max(elapsed_seconds, 1e-12),
            "backend": str(backend),
            "runtime": diag,
            "metadata": dict(metadata or {}),
            **status_fields,
        }
    )
    return gpu_pass, production_pass, surrogate_free_pass


def run_solver_hip_e2e_contract(*, strict_probe: dict, min_device_residency_ratio: float) -> dict[str, Any]:
    strict_probe_pass = bool(
        strict_probe.get("pass", strict_probe.get("strict_rust_hip_pass", False))
        and bool(strict_probe.get("gpu_strict_pass", False))
        and not bool(strict_probe.get("cpu_required", False))
        and not bool(strict_probe.get("cpu_fallback_used", False))
    )

    row_results: list[dict[str, Any]] = []
    frame_gpu_results: list[bool] = []
    frame_production_results: list[bool] = []
    frame_surrogate_results: list[bool] = []
    ndtha_gpu_results: list[bool] = []
    ndtha_production_results: list[bool] = []
    ndtha_surrogate_results: list[bool] = []
    track_gpu_results: list[bool] = []
    track_production_results: list[bool] = []
    track_surrogate_results: list[bool] = []

    frame_static_cases = [
        {
            "solver": "nonlinear_frame_static_rc",
            "hazard_family": "gravity_plus_lateral",
            "topology_family": "regular_rc_frame",
            "story_h": np.full(8, 3.2, dtype=np.float64),
            "story_k": np.linspace(2.0e8, 2.6e8, num=8, dtype=np.float64),
            "story_axial": np.linspace(4.8e6, 3.2e6, num=8, dtype=np.float64),
            "yield_drift": np.full(8, 0.012, dtype=np.float64),
            "floor_load": build_story_load_profile(8, 3.6e6, mode="triangular"),
            "cfg": RustNonlinearFrameConfig(tolerance=1e-7, max_iter=40, hardening_ratio=0.05, pdelta_factor=1.0),
        },
        {
            "solver": "nonlinear_frame_static_steel_slender",
            "hazard_family": "gravity_plus_wind",
            "topology_family": "slender_steel_frame",
            "story_h": np.full(12, 3.5, dtype=np.float64),
            "story_k": np.linspace(1.4e8, 2.1e8, num=12, dtype=np.float64),
            "story_axial": np.linspace(3.4e6, 2.0e6, num=12, dtype=np.float64),
            "yield_drift": np.full(12, 0.015, dtype=np.float64),
            "floor_load": build_story_load_profile(12, 4.1e6, mode="uniform"),
            "cfg": RustNonlinearFrameConfig(tolerance=1e-7, max_iter=48, hardening_ratio=0.04, pdelta_factor=1.1),
        },
        {
            "solver": "nonlinear_frame_static_transfer_irregular",
            "hazard_family": "gravity_plus_transfer",
            "topology_family": "transfer_irregular_frame",
            "story_h": np.array([4.8, 4.2, 3.8, 3.5, 3.3, 3.3, 3.3, 3.3, 3.3], dtype=np.float64),
            "story_k": np.array([1.2e8, 1.5e8, 1.8e8, 2.1e8, 2.25e8, 2.30e8, 2.35e8, 2.40e8, 2.45e8], dtype=np.float64),
            "story_axial": np.linspace(5.2e6, 2.8e6, num=9, dtype=np.float64),
            "yield_drift": np.full(9, 0.013, dtype=np.float64),
            "floor_load": build_story_load_profile(9, 4.6e6, mode="triangular"),
            "cfg": RustNonlinearFrameConfig(tolerance=1e-7, max_iter=52, hardening_ratio=0.05, pdelta_factor=1.12),
        },
        {
            "solver": "nonlinear_frame_static_soft_story",
            "hazard_family": "gravity_plus_setback",
            "topology_family": "soft_story_frame",
            "story_h": np.array([5.0, 4.2, 3.6, 3.3, 3.3, 3.3, 3.3, 3.3], dtype=np.float64),
            "story_k": np.array([0.95e8, 1.35e8, 1.75e8, 1.95e8, 2.05e8, 2.10e8, 2.15e8, 2.20e8], dtype=np.float64),
            "story_axial": np.linspace(4.9e6, 2.7e6, num=8, dtype=np.float64),
            "yield_drift": np.array([0.018, 0.015, 0.013, 0.012, 0.012, 0.012, 0.012, 0.012], dtype=np.float64),
            "floor_load": build_story_load_profile(8, 4.0e6, mode="uniform"),
            "cfg": RustNonlinearFrameConfig(tolerance=1e-7, max_iter=56, hardening_ratio=0.06, pdelta_factor=1.15),
        },
        {
            "solver": "nonlinear_frame_static_podium_torsion",
            "hazard_family": "gravity_plus_torsion",
            "topology_family": "podium_setback_frame",
            "load_path_family": "torsion_biased_static",
            "story_h": np.array([4.6, 4.0, 3.6, 3.4, 3.4, 3.4, 3.4, 3.4, 3.4, 3.4], dtype=np.float64),
            "story_k": np.array([1.08e8, 1.28e8, 1.62e8, 1.85e8, 2.02e8, 2.12e8, 2.18e8, 2.23e8, 2.28e8, 2.32e8], dtype=np.float64),
            "story_axial": np.linspace(5.1e6, 2.6e6, num=10, dtype=np.float64),
            "yield_drift": np.array([0.017, 0.015, 0.014, 0.013, 0.012, 0.012, 0.012, 0.012, 0.012, 0.012], dtype=np.float64),
            "floor_load": build_story_load_profile(10, 4.8e6, mode="triangular"),
            "cfg": RustNonlinearFrameConfig(tolerance=1e-7, max_iter=58, hardening_ratio=0.06, pdelta_factor=1.16),
        },
        {
            "solver": "nonlinear_frame_static_diaphragm_transfer",
            "hazard_family": "gravity_plus_diaphragm",
            "topology_family": "coupled_diaphragm_frame",
            "load_path_family": "transfer_static_push",
            "story_h": np.array([4.4, 4.0, 3.8, 3.5, 3.4, 3.4, 3.4, 3.4, 3.4], dtype=np.float64),
            "story_k": np.array([1.15e8, 1.38e8, 1.74e8, 1.96e8, 2.08e8, 2.16e8, 2.21e8, 2.26e8, 2.31e8], dtype=np.float64),
            "story_axial": np.linspace(5.0e6, 2.7e6, num=9, dtype=np.float64),
            "yield_drift": np.array([0.016, 0.015, 0.014, 0.013, 0.0125, 0.0125, 0.0125, 0.0125, 0.0125], dtype=np.float64),
            "floor_load": build_story_load_profile(9, 4.5e6, mode="uniform"),
            "cfg": RustNonlinearFrameConfig(tolerance=1e-7, max_iter=60, hardening_ratio=0.055, pdelta_factor=1.14),
        },
    ]
    for case in frame_static_cases:
        case.setdefault("load_path_family", "gravity_biased_static")
    for case in frame_static_cases:
        frame_t0 = time.perf_counter()
        frame_out = solve_nonlinear_frame(
            story_k_n_per_m=case["story_k"],
            story_h_m=case["story_h"],
            story_axial_n=case["story_axial"],
            story_yield_drift_m=case["yield_drift"],
            floor_load_n=case["floor_load"],
            cfg=case["cfg"],
        )
        runtime = frame_out.get("runtime") if isinstance(frame_out.get("runtime"), dict) else {}
        gpu_pass, production_pass, surrogate_pass = _append_solver_result(
            row_results,
            solver=str(case["solver"]),
            elapsed_seconds=time.perf_counter() - frame_t0,
            runtime=runtime,
            backend=str(frame_out.get("backend", "")),
            status_fields={
                "converged": bool(frame_out.get("converged", False)),
                "status": int(frame_out.get("status", -1)),
            },
            metadata={
                "hazard_family": str(case["hazard_family"]),
                "topology_family": str(case["topology_family"]),
                "load_path_family": str(case["load_path_family"]),
            },
            min_device_residency_ratio=min_device_residency_ratio,
        )
        frame_gpu_results.append(gpu_pass)
        frame_production_results.append(production_pass)
        frame_surrogate_results.append(surrogate_pass)

    step_count = 64
    ndtha_cases = [
        {
            "solver": "nonlinear_frame_ndtha_service",
            "hazard_family": "seismic_service",
            "topology_family": "regular_rc_frame",
            "story_h": np.full(8, 3.2, dtype=np.float64),
            "story_k": np.linspace(1.8e8, 2.3e8, num=8, dtype=np.float64),
            "story_axial": np.linspace(4.8e6, 3.2e6, num=8, dtype=np.float64),
            "story_yield_drift": np.full(8, 0.010, dtype=np.float64),
            "story_mass": np.linspace(2.3e5, 1.7e5, num=8, dtype=np.float64),
            "story_damping": np.linspace(7.5e4, 5.5e4, num=8, dtype=np.float64),
            "floor_load": build_story_load_profile(8, 3.6e6, mode="triangular"),
            "ag": 0.18 * np.sin(np.linspace(0.0, 5.0 * math.pi, num=step_count, dtype=np.float64)),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=12,
                hardening_ratio=0.08,
                pdelta_factor=1.0,
            ),
        },
        {
            "solver": "nonlinear_frame_ndtha_pulse",
            "hazard_family": "seismic_pulse",
            "topology_family": "slender_steel_frame",
            "story_h": np.full(10, 3.4, dtype=np.float64),
            "story_k": np.linspace(1.6e8, 2.1e8, num=10, dtype=np.float64),
            "story_axial": np.linspace(4.0e6, 2.5e6, num=10, dtype=np.float64),
            "story_yield_drift": np.full(10, 0.011, dtype=np.float64),
            "story_mass": np.linspace(2.6e5, 1.9e5, num=10, dtype=np.float64),
            "story_damping": np.linspace(8.1e4, 5.9e4, num=10, dtype=np.float64),
            "floor_load": build_story_load_profile(10, 4.0e6, mode="triangular"),
            "ag": 0.22
            * np.sin(np.linspace(0.0, 6.0 * math.pi, num=step_count, dtype=np.float64))
            * np.exp(-np.linspace(0.0, 1.7, num=step_count, dtype=np.float64)),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=14,
                hardening_ratio=0.07,
                pdelta_factor=1.05,
            ),
        },
        {
            "solver": "nonlinear_frame_ndtha_wind_burst",
            "hazard_family": "wind_burst",
            "topology_family": "transfer_irregular_frame",
            "story_h": np.full(9, 3.5, dtype=np.float64),
            "story_k": np.linspace(1.5e8, 2.05e8, num=9, dtype=np.float64),
            "story_axial": np.linspace(4.2e6, 2.6e6, num=9, dtype=np.float64),
            "story_yield_drift": np.full(9, 0.012, dtype=np.float64),
            "story_mass": np.linspace(2.8e5, 1.8e5, num=9, dtype=np.float64),
            "story_damping": np.linspace(8.6e4, 6.0e4, num=9, dtype=np.float64),
            "floor_load": build_story_load_profile(9, 4.4e6, mode="uniform"),
            "ag": 0.12
            * np.sin(np.linspace(0.0, 7.0 * math.pi, num=step_count, dtype=np.float64))
            * (1.0 + 0.35 * np.sin(np.linspace(0.0, 1.5 * math.pi, num=step_count, dtype=np.float64))),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=16,
                hardening_ratio=0.06,
                pdelta_factor=1.08,
            ),
        },
        {
            "solver": "nonlinear_frame_ndtha_aftershock",
            "hazard_family": "aftershock_sequence",
            "topology_family": "dual_system_frame",
            "load_path_family": "aftershock_response_history",
            "story_h": np.full(11, 3.4, dtype=np.float64),
            "story_k": np.linspace(1.7e8, 2.4e8, num=11, dtype=np.float64),
            "story_axial": np.linspace(4.4e6, 2.4e6, num=11, dtype=np.float64),
            "story_yield_drift": np.full(11, 0.0115, dtype=np.float64),
            "story_mass": np.linspace(2.5e5, 1.7e5, num=11, dtype=np.float64),
            "story_damping": np.linspace(8.0e4, 5.6e4, num=11, dtype=np.float64),
            "floor_load": build_story_load_profile(11, 4.3e6, mode="triangular"),
            "ag": 0.16
            * (
                np.sin(np.linspace(0.0, 4.5 * math.pi, num=step_count, dtype=np.float64))
                + 0.55 * np.sin(np.linspace(0.0, 9.0 * math.pi, num=step_count, dtype=np.float64))
            )
            * np.exp(-np.linspace(0.0, 1.3, num=step_count, dtype=np.float64)),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=15,
                hardening_ratio=0.07,
                pdelta_factor=1.07,
            ),
        },
        {
            "solver": "nonlinear_frame_ndtha_bidirectional",
            "hazard_family": "seismic_bidirectional",
            "topology_family": "torsion_irregular_frame",
            "load_path_family": "bidirectional_response_history",
            "story_h": np.full(10, 3.5, dtype=np.float64),
            "story_k": np.linspace(1.65e8, 2.22e8, num=10, dtype=np.float64),
            "story_axial": np.linspace(4.3e6, 2.3e6, num=10, dtype=np.float64),
            "story_yield_drift": np.full(10, 0.011, dtype=np.float64),
            "story_mass": np.linspace(2.55e5, 1.75e5, num=10, dtype=np.float64),
            "story_damping": np.linspace(8.3e4, 5.8e4, num=10, dtype=np.float64),
            "floor_load": build_story_load_profile(10, 4.1e6, mode="uniform"),
            "ag": 0.18
            * (
                np.sin(np.linspace(0.0, 5.5 * math.pi, num=step_count, dtype=np.float64))
                + 0.35 * np.cos(np.linspace(0.0, 2.5 * math.pi, num=step_count, dtype=np.float64))
            )
            * np.exp(-np.linspace(0.0, 1.1, num=step_count, dtype=np.float64)),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=16,
                hardening_ratio=0.07,
                pdelta_factor=1.09,
            ),
        },
        {
            "solver": "nonlinear_frame_ndtha_transition_wind",
            "hazard_family": "wind_transition_gust",
            "topology_family": "setback_transition_frame",
            "load_path_family": "gust_history_transition",
            "story_h": np.array([4.2, 3.9, 3.7, 3.5, 3.4, 3.4, 3.4, 3.4, 3.4], dtype=np.float64),
            "story_k": np.linspace(1.58e8, 2.18e8, num=9, dtype=np.float64),
            "story_axial": np.linspace(4.1e6, 2.25e6, num=9, dtype=np.float64),
            "story_yield_drift": np.full(9, 0.0118, dtype=np.float64),
            "story_mass": np.linspace(2.45e5, 1.72e5, num=9, dtype=np.float64),
            "story_damping": np.linspace(8.4e4, 5.9e4, num=9, dtype=np.float64),
            "floor_load": build_story_load_profile(9, 4.2e6, mode="uniform"),
            "ag": 0.14
            * (
                np.sin(np.linspace(0.0, 7.5 * math.pi, num=step_count, dtype=np.float64))
                + 0.25 * np.sin(np.linspace(0.0, 1.2 * math.pi, num=step_count, dtype=np.float64))
            )
            * np.exp(-np.linspace(0.0, 0.9, num=step_count, dtype=np.float64)),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=17,
                hardening_ratio=0.065,
                pdelta_factor=1.1,
            ),
        },
        {
            "solver": "nonlinear_frame_ndtha_pounding_sequence",
            "hazard_family": "seismic_pounding_sequence",
            "topology_family": "adjacent_tower_frame",
            "load_path_family": "pounding_history",
            "story_h": np.full(12, 3.35, dtype=np.float64),
            "story_k": np.linspace(1.62e8, 2.32e8, num=12, dtype=np.float64),
            "story_axial": np.linspace(4.5e6, 2.35e6, num=12, dtype=np.float64),
            "story_yield_drift": np.full(12, 0.0112, dtype=np.float64),
            "story_mass": np.linspace(2.62e5, 1.78e5, num=12, dtype=np.float64),
            "story_damping": np.linspace(8.5e4, 5.7e4, num=12, dtype=np.float64),
            "floor_load": build_story_load_profile(12, 4.4e6, mode="triangular"),
            "ag": 0.19
            * (
                np.sin(np.linspace(0.0, 6.5 * math.pi, num=step_count, dtype=np.float64))
                + 0.22 * np.sign(np.sin(np.linspace(0.0, 2.0 * math.pi, num=step_count, dtype=np.float64)))
            )
            * np.exp(-np.linspace(0.0, 1.0, num=step_count, dtype=np.float64)),
            "cfg": RustNonlinearNdthaConfig(
                dt_s=0.01,
                tolerance=1e-5,
                max_step_iterations=18,
                hardening_ratio=0.07,
                pdelta_factor=1.11,
            ),
        },
    ]
    for case in ndtha_cases:
        case.setdefault("load_path_family", "single_axis_response_history")
    for case in ndtha_cases:
        ndtha_t0 = time.perf_counter()
        ndtha_out = solve_nonlinear_frame_ndtha(
            story_k_n_per_m=case["story_k"],
            story_h_m=case["story_h"],
            story_axial_n=case["story_axial"],
            story_yield_drift_m=case["story_yield_drift"],
            story_mass_kg=case["story_mass"],
            story_damping_n_s_per_m=case["story_damping"],
            floor_load_base_n=case["floor_load"],
            ag_g=case["ag"],
            cfg=case["cfg"],
        )
        runtime = ndtha_out.get("runtime") if isinstance(ndtha_out.get("runtime"), dict) else {}
        gpu_pass, production_pass, surrogate_pass = _append_solver_result(
            row_results,
            solver=str(case["solver"]),
            elapsed_seconds=time.perf_counter() - ndtha_t0,
            runtime=runtime,
            backend=str(ndtha_out.get("backend", "")),
            status_fields={
                "converged_all_steps": bool(ndtha_out.get("converged_all_steps", False)),
                "status": int(ndtha_out.get("status", -1)),
            },
            metadata={
                "hazard_family": str(case["hazard_family"]),
                "topology_family": str(case["topology_family"]),
                "load_path_family": str(case["load_path_family"]),
            },
            min_device_residency_ratio=min_device_residency_ratio,
        )
        ndtha_gpu_results.append(gpu_pass)
        ndtha_production_results.append(production_pass)
        ndtha_surrogate_results.append(surrogate_pass)

    track_cases = [
        (
            "track_lf_timoshenko",
            {
                "hazard_family": "moving_axle",
                "topology_family": "pinned_timoshenko_track",
                "load_path_family": "moving_point_load",
            },
            RustTrackConfig(
                length_m=25.0,
                node_count=129,
                support_type="pinned",
                theory="timoshenko",
                bending_stiffness_n_m2=6.5e6,
                shear_stiffness_n=2.45e8,
                winkler_k_n_per_m2=0.0,
                pasternak_g_n=0.0,
                tolerance=1e-8,
                cg_max_iter=1800,
                point_force_n=100_000.0,
                point_position_m=12.5,
            ),
        ),
        (
            "track_lf_euler_fixed",
            {
                "hazard_family": "settlement_contact",
                "topology_family": "fixed_euler_track",
                "load_path_family": "settlement_contact_load",
            },
            RustTrackConfig(
                length_m=32.0,
                node_count=161,
                support_type="fixed",
                theory="euler",
                bending_stiffness_n_m2=8.0e6,
                shear_stiffness_n=2.90e8,
                winkler_k_n_per_m2=1.2e6,
                pasternak_g_n=8.5e4,
                tolerance=1e-8,
                cg_max_iter=2200,
                point_force_n=140_000.0,
                point_position_m=16.0,
            ),
        ),
        (
            "track_lf_pasternak_transition",
            {
                "hazard_family": "transition_zone_coupling",
                "topology_family": "elastic_foundation_track",
                "load_path_family": "transition_zone_transfer",
            },
            RustTrackConfig(
                length_m=28.0,
                node_count=145,
                support_type="pinned",
                theory="timoshenko",
                bending_stiffness_n_m2=7.2e6,
                shear_stiffness_n=2.70e8,
                winkler_k_n_per_m2=9.0e5,
                pasternak_g_n=6.0e4,
                tolerance=1e-8,
                cg_max_iter=2100,
                point_force_n=125_000.0,
                point_position_m=14.0,
            ),
        ),
        (
            "track_lf_ballasted_wave",
            {
                "hazard_family": "ballast_wave_radiation",
                "topology_family": "ballasted_transition_track",
                "load_path_family": "ballast_radiation_wave",
            },
            RustTrackConfig(
                length_m=30.0,
                node_count=153,
                support_type="fixed",
                theory="timoshenko",
                bending_stiffness_n_m2=7.6e6,
                shear_stiffness_n=2.85e8,
                winkler_k_n_per_m2=1.05e6,
                pasternak_g_n=7.2e4,
                tolerance=1e-8,
                cg_max_iter=2300,
                point_force_n=132_000.0,
                point_position_m=15.5,
            ),
        ),
        (
            "track_lf_bridge_approach",
            {
                "hazard_family": "bridge_approach_impact",
                "topology_family": "bridge_approach_track",
                "load_path_family": "bridge_approach_point_load",
            },
            RustTrackConfig(
                length_m=34.0,
                node_count=173,
                support_type="fixed",
                theory="euler",
                bending_stiffness_n_m2=8.4e6,
                shear_stiffness_n=3.00e8,
                winkler_k_n_per_m2=1.15e6,
                pasternak_g_n=8.0e4,
                tolerance=1e-8,
                cg_max_iter=2400,
                point_force_n=145_000.0,
                point_position_m=17.0,
            ),
        ),
        (
            "track_lf_tunnel_transition",
            {
                "hazard_family": "tunnel_transition_settlement",
                "topology_family": "tunnel_transition_track",
                "load_path_family": "tunnel_transition_wave",
            },
            RustTrackConfig(
                length_m=36.0,
                node_count=181,
                support_type="fixed",
                theory="timoshenko",
                bending_stiffness_n_m2=8.8e6,
                shear_stiffness_n=3.10e8,
                winkler_k_n_per_m2=1.20e6,
                pasternak_g_n=8.6e4,
                tolerance=1e-8,
                cg_max_iter=2500,
                point_force_n=148_000.0,
                point_position_m=18.0,
            ),
        ),
        (
            "track_lf_crosswind_viaduct",
            {
                "hazard_family": "crosswind_viaduct",
                "topology_family": "viaduct_ballasted_track",
                "load_path_family": "crosswind_moving_load",
            },
            RustTrackConfig(
                length_m=38.0,
                node_count=193,
                support_type="pinned",
                theory="euler",
                bending_stiffness_n_m2=9.1e6,
                shear_stiffness_n=3.05e8,
                winkler_k_n_per_m2=1.08e6,
                pasternak_g_n=7.8e4,
                tolerance=1e-8,
                cg_max_iter=2550,
                point_force_n=150_000.0,
                point_position_m=19.0,
            ),
        ),
    ]
    for solver_name, metadata, cfg in track_cases:
        track_t0 = time.perf_counter()
        track_out = solve_track_point_load(cfg)
        runtime = track_out.get("runtime") if isinstance(track_out.get("runtime"), dict) else {}
        gpu_pass, production_pass, surrogate_pass = _append_solver_result(
            row_results,
            solver=solver_name,
            elapsed_seconds=time.perf_counter() - track_t0,
            runtime=runtime,
            backend=str(track_out.get("backend", "")),
            status_fields={
                "converged": bool(track_out.get("converged", False)),
                "status_code": int(track_out.get("status_code", -1)),
            },
            metadata=metadata,
            min_device_residency_ratio=min_device_residency_ratio,
        )
        track_gpu_results.append(gpu_pass)
        track_production_results.append(production_pass)
        track_surrogate_results.append(surrogate_pass)

    checks = {
        "strict_probe_pass": strict_probe_pass,
        "nonlinear_frame_gpu_pass": bool(all(frame_gpu_results)),
        "ndtha_gpu_pass": bool(all(ndtha_gpu_results)),
        "track_gpu_pass": bool(all(track_gpu_results)),
        "all_main_loops_gpu_pass": bool(all(frame_gpu_results) and all(ndtha_gpu_results) and all(track_gpu_results)),
        "nonlinear_frame_production_kernel_pass": bool(all(frame_production_results)),
        "ndtha_production_kernel_pass": bool(all(ndtha_production_results)),
        "track_production_kernel_pass": bool(all(track_production_results)),
        "all_production_kernel_pass": bool(
            all(frame_production_results) and all(ndtha_production_results) and all(track_production_results)
        ),
        "nonlinear_frame_surrogate_runtime_free_pass": bool(all(frame_surrogate_results)),
        "ndtha_surrogate_runtime_free_pass": bool(all(ndtha_surrogate_results)),
        "track_surrogate_runtime_free_pass": bool(all(track_surrogate_results)),
        "no_surrogate_runtime_markers_pass": bool(
            all(frame_surrogate_results) and all(ndtha_surrogate_results) and all(track_surrogate_results)
        ),
        "no_cpu_backend_pass": bool(all(not bool((row.get("runtime") or {}).get("cpu_backend", True)) for row in row_results)),
        "no_cpu_required_pass": bool(all(not bool((row.get("runtime") or {}).get("cpu_required", True)) for row in row_results)),
        "no_cpu_fallback_pass": bool(all(not bool((row.get("runtime") or {}).get("cpu_fallback_used", False)) for row in row_results)),
        "all_force_jacobian_consistent_pass": bool(
            all(bool((row.get("runtime") or {}).get("force_jacobian_kernel_consistent", False)) for row in row_results)
        ),
        "hazard_topology_diversity_pass": bool(
            len(
                {
                    str((row.get("metadata") or {}).get("hazard_family", "")).strip()
                    for row in row_results
                    if str((row.get("metadata") or {}).get("hazard_family", "")).strip()
                }
            )
            >= 6
            and len(
                {
                    str((row.get("metadata") or {}).get("topology_family", "")).strip()
                    for row in row_results
                    if str((row.get("metadata") or {}).get("topology_family", "")).strip()
                }
            )
            >= 6
            and len(
                {
                    str((row.get("metadata") or {}).get("load_path_family", "")).strip()
                    for row in row_results
                    if str((row.get("metadata") or {}).get("load_path_family", "")).strip()
                }
            )
            >= 9
        ),
    }
    contract_pass = bool(all(checks.values()))

    if not checks["strict_probe_pass"]:
        reason_code = "ERR_STRICT_PROBE_FAIL"
    elif not checks["nonlinear_frame_gpu_pass"]:
        reason_code = "ERR_NONLINEAR_FRAME_GPU_FAIL"
    elif not checks["ndtha_gpu_pass"]:
        reason_code = "ERR_NDTHA_GPU_FAIL"
    elif not checks["track_gpu_pass"]:
        reason_code = "ERR_TRACK_GPU_FAIL"
    elif not checks["all_production_kernel_pass"]:
        reason_code = "ERR_PRODUCTION_KERNEL_FAIL"
    elif not checks["no_surrogate_runtime_markers_pass"]:
        reason_code = "ERR_SURROGATE_RUNTIME_FAIL"
    elif not checks["all_force_jacobian_consistent_pass"]:
        reason_code = "ERR_PRODUCTION_KERNEL_FAIL"
    elif not checks["hazard_topology_diversity_pass"]:
        reason_code = "ERR_PRODUCTION_KERNEL_FAIL"
    elif not checks["no_cpu_backend_pass"] or not checks["no_cpu_required_pass"] or not checks["no_cpu_fallback_pass"]:
        reason_code = "ERR_GPU_POLICY_FAIL"
    else:
        reason_code = "PASS"

    summary_line = (
        "Solver HIP e2e: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"gpu_loops={sum(1 for row in row_results if bool((row.get('runtime') or {}).get('gpu_main_loop_pass', False)))}/{len(row_results)} | "
        f"production_kernel={sum(1 for row in row_results if bool((row.get('runtime') or {}).get('production_kernel_pass', False)))}/{len(row_results)} | "
        f"surrogate_free={sum(1 for row in row_results if bool((row.get('runtime') or {}).get('surrogate_runtime_free_pass', False)))}/{len(row_results)} | "
        f"variants={len(row_results)} | "
        f"hazards={len({str((row.get('metadata') or {}).get('hazard_family', '')).strip() for row in row_results if str((row.get('metadata') or {}).get('hazard_family', '')).strip()})} | "
        f"topologies={len({str((row.get('metadata') or {}).get('topology_family', '')).strip() for row in row_results if str((row.get('metadata') or {}).get('topology_family', '')).strip()})} | "
        f"load_paths={len({str((row.get('metadata') or {}).get('load_path_family', '')).strip() for row in row_results if str((row.get('metadata') or {}).get('load_path_family', '')).strip()})} | "
        f"device_residency_min={min((_finite((row.get('runtime') or {}).get('device_residency_ratio', 0.0), 0.0) for row in row_results), default=0.0):.2f} | "
        f"hip_kernels={sum(int(_finite((row.get('runtime') or {}).get('hip_kernel_invocation_count', 0), 0.0)) for row in row_results)}"
    )

    return {
        "schema_version": "1.1",
        "run_id": "phase1-solver-hip-e2e-contract",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "strict_probe_summary": {
            "runtime_backend": str(strict_probe.get("runtime_backend", "")),
            "gpu_strict_pass": bool(strict_probe.get("gpu_strict_pass", False)),
            "cpu_required": bool(strict_probe.get("cpu_required", False)),
            "cpu_fallback_used": bool(strict_probe.get("cpu_fallback_used", False)),
        },
        "summary": {
            "solver_count": len(row_results),
            "gpu_solver_count": sum(1 for row in row_results if bool((row.get("runtime") or {}).get("gpu_main_loop_pass", False))),
            "device_residency_ratio_min": min(
                (_finite((row.get("runtime") or {}).get("device_residency_ratio", 0.0), 0.0) for row in row_results),
                default=0.0,
            ),
            "production_kernel_solver_count": sum(
                1 for row in row_results if bool((row.get("runtime") or {}).get("production_kernel_pass", False))
            ),
            "surrogate_runtime_free_solver_count": sum(
                1 for row in row_results if bool((row.get("runtime") or {}).get("surrogate_runtime_free_pass", False))
            ),
            "force_jacobian_consistent_solver_count": sum(
                1 for row in row_results if bool((row.get("runtime") or {}).get("force_jacobian_kernel_consistent", False))
            ),
            "hazard_family_count": len(
                {
                    str((row.get("metadata") or {}).get("hazard_family", "")).strip()
                    for row in row_results
                    if str((row.get("metadata") or {}).get("hazard_family", "")).strip()
                }
            ),
            "topology_family_count": len(
                {
                    str((row.get("metadata") or {}).get("topology_family", "")).strip()
                    for row in row_results
                    if str((row.get("metadata") or {}).get("topology_family", "")).strip()
                }
            ),
            "load_path_family_count": len(
                {
                    str((row.get("metadata") or {}).get("load_path_family", "")).strip()
                    for row in row_results
                    if str((row.get("metadata") or {}).get("load_path_family", "")).strip()
                }
            ),
            "hip_kernel_invocation_count_total": sum(
                int(_finite((row.get("runtime") or {}).get("hip_kernel_invocation_count", 0), 0.0)) for row in row_results
            ),
        },
        "summary_line": summary_line,
        "solver_rows": row_results,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    logger = get_logger("phase1.solver_hip_e2e")
    p = argparse.ArgumentParser()
    p.add_argument("--strict-probe", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    p.add_argument("--min-device-residency-ratio", type=float, default=0.99)
    p.add_argument("--out", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    args = p.parse_args()

    input_payload = {
        "strict_probe": str(args.strict_probe),
        "min_device_residency_ratio": float(args.min_device_residency_ratio),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_solver_hip_e2e_contract")
        strict_probe = _load_json(Path(args.strict_probe))
        log_event(logger, 20, "solver_hip_e2e.start", inputs=input_payload)
        report = run_solver_hip_e2e_contract(
            strict_probe=strict_probe,
            min_device_residency_ratio=float(args.min_device_residency_ratio),
        )
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(
            logger,
            20,
            "solver_hip_e2e.completed",
            contract_pass=bool(report.get("contract_pass", False)),
            reason_code=str(report.get("reason_code", "")),
        )
        print(f"Wrote solver hip e2e contract report: {out}")
        if not bool(report.get("contract_pass", False)):
            raise SystemExit(1)
    except (FileNotFoundError, ValueError, InputContractError) as exc:
        report = {
            "schema_version": "1.1",
            "run_id": "phase1-solver-hip-e2e-contract",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote solver hip e2e contract report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
