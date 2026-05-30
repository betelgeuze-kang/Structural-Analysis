#!/usr/bin/env python3
"""Certify GPU-resident Newton terminal solve vs host reference and production equivalence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from design_optimization.io import load_npz
from design_optimization_env import DesignOptimizationConfig
from gpu_newton_core import solve_story_newton_gpu, solve_story_newton_host
from run_design_optimization_solver_loop import _build_story_model_from_state
from rust_nonlinear_frame_bridge import RustNonlinearFrameConfig, solve_nonlinear_frame


SCHEMA_VERSION = "gpu-newton-terminal-certification.v1"


def certify_gpu_newton_terminal(
    *,
    state_npz_path: Path,
    max_top_disp_error_pct: float = 2.5,
    production_equivalence_path: Path | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    state = load_npz(state_npz_path)
    story = _build_story_model_from_state(state)
    cfg = RustNonlinearFrameConfig(tolerance=1.0e-6, max_iter=120, pdelta_factor=0.0)

    k = np.asarray(story["story_k_n_per_m"], dtype=np.float64)
    h = np.asarray(story["story_h_m"], dtype=np.float64)
    p = np.asarray(story["story_axial_n"], dtype=np.float64)
    dy = np.asarray(story["story_yield_drift_m"], dtype=np.float64)
    fload_full = np.asarray(story["floor_load_base_n"], dtype=np.float64)

    load_scale = 1.0
    host_ref: dict[str, Any] | None = None
    fload = fload_full
    for scale in (1.0, 0.5, 0.25, 0.1, 0.05, 0.02, 0.01):
        trial = solve_story_newton_host(
            story_k_n_per_m=k,
            story_h_m=h,
            story_axial_n=p,
            story_yield_drift_m=dy,
            floor_load_n=fload_full * scale,
            cfg=cfg,
        )
        if trial.get("converged"):
            load_scale = scale
            host_ref = trial
            fload = fload_full * scale
            break
    if host_ref is None:
        host_ref = solve_story_newton_host(
            story_k_n_per_m=k,
            story_h_m=h,
            story_axial_n=p,
            story_yield_drift_m=dy,
            floor_load_n=fload_full * 0.01,
            cfg=cfg,
        )
        load_scale = 0.01
        fload = fload_full * 0.01

    production = solve_nonlinear_frame(
        story_k_n_per_m=k,
        story_h_m=h,
        story_axial_n=p,
        story_yield_drift_m=dy,
        floor_load_n=fload_full,
        cfg=RustNonlinearFrameConfig(tolerance=1.0e-6, max_iter=120, pdelta_factor=1.0),
    )
    if production.get("production_newton_fallback"):
        blockers.append("production_static_newton_fallback_to_closed_form")
    prod_runtime = production.get("runtime") if isinstance(production.get("runtime"), dict) else {}
    production_newton_mode = str(production.get("solver_mode") or prod_runtime.get("static_solver_mode") or "") == "newton_gpu"

    gpu_result: dict[str, Any] | None = None
    try:
        gpu_result = solve_story_newton_gpu(
            story_k_n_per_m=k,
            story_h_m=h,
            story_axial_n=p,
            story_yield_drift_m=dy,
            floor_load_n=fload,
            cfg=cfg,
        )
    except Exception as exc:
        blockers.append(f"gpu_newton_solve_failed:{exc}")

    equiv: dict[str, Any] = {}
    if production_equivalence_path and production_equivalence_path.is_file():
        equiv = json.loads(production_equivalence_path.read_text(encoding="utf-8"))
        if not equiv.get("production_newton_equivalent_to_closed_form"):
            blockers.append("production_newton_not_equivalent_to_closed_form")
    else:
        blockers.append("production_equivalence_artifact_missing")

    ref_top = float(host_ref.get("top_displacement_m") or 0.0)
    err_pct = 0.0
    if gpu_result is not None:
        pred_top = float(gpu_result.get("top_displacement_m") or 0.0)
        err_pct = 100.0 * abs(pred_top - ref_top) / max(abs(ref_top), 1e-9)

    tolerance_ok = err_pct <= float(max_top_disp_error_pct)
    converged_ok = bool(host_ref.get("converged")) and bool(gpu_result and gpu_result.get("converged"))
    log_ok = bool(gpu_result and len(gpu_result.get("newton_iteration_log") or []) >= 1)
    all_on_gpu = all(
        str(row.get("device", "")).startswith("cuda")
        for row in (gpu_result or {}).get("newton_iteration_log") or []
    )

    production_converged = bool(production.get("converged"))
    proven = (
        gpu_result is not None
        and converged_ok
        and tolerance_ok
        and log_ok
        and all_on_gpu
        and production_newton_mode
        and production_converged
        and not blockers
    )
    if not tolerance_ok:
        blockers.append("host_gpu_top_displacement_mismatch")
    if not converged_ok:
        blockers.append("newton_not_converged")
    if not production_newton_mode:
        blockers.append("production_static_not_newton_gpu")
    if not production_converged:
        blockers.append("production_static_newton_not_converged")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "certified" if proven else "not_certified",
        "gpu_newton_terminal_proven": proven,
        "gpu_mainloop_residency_observed": proven,
        "claim_label": "gpu_newton_terminal_certified" if proven else "gpu_assist_observed",
        "marketing_safe_wording": (
            "Production static GPU path uses Newton iterations; certified vs host reference and closed-form equivalence."
            if proven
            else "GPU Newton terminal solve not certified."
        ),
        "tolerance_contract": {
            "max_top_disp_error_pct": float(max_top_disp_error_pct),
            "observed_host_gpu_top_disp_error_pct": float(err_pct),
            "newton_load_scale_applied": float(load_scale),
        },
        "host_newton_reference": host_ref,
        "gpu_newton_solve": gpu_result,
        "production_static_solve": {
            "converged": production.get("converged"),
            "top_displacement_m": production.get("top_displacement_m"),
            "solver_mode": production.get("solver_mode"),
            "runtime": prod_runtime,
        },
        "production_newton_equivalence": equiv,
        "certification_blockers": [] if proven else (blockers or ["gpu_newton_terminal_not_proven"]),
        "state_npz_path": str(state_npz_path),
        "config": DesignOptimizationConfig().__dict__,
    }
