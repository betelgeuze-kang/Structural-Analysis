#!/usr/bin/env python3
"""Run condensed global-FEA proxy solve from MGT roundtrip NPZ mesh (wired native path)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from assemble_mgt_mesh_condensed_story import assemble_story_model_from_mgt_npz
from design_optimization.io import load_json
from rust_nonlinear_frame_bridge import RustNonlinearFrameConfig, RustNonlinearNdthaConfig, solve_nonlinear_frame, solve_nonlinear_frame_ndtha


SCHEMA_VERSION = "mgt-global-fea-condensed-solve.v1"


def _deterministic_ag(*, dt_s: float, step_count: int) -> np.ndarray:
    t = np.arange(step_count, dtype=np.float64) * float(dt_s)
    return 0.35 * np.sin(2.0 * np.pi * 1.7 * t) + 0.12 * np.sin(2.0 * np.pi * 4.3 * t + 0.4)


def run_mgt_global_fea_condensed_solve(
    *,
    roundtrip_json: Path,
    roundtrip_npz: Path | None = None,
    step_count: int = 120,
) -> dict[str, Any]:
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    blockers: list[str] = []
    if not roundtrip_json.is_file():
        blockers.append("roundtrip_json_missing")
    if not roundtrip_npz.is_file():
        blockers.append("roundtrip_npz_missing")
    if blockers:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "native_solve_status": "not_wired",
            "blockers": blockers,
        }

    story = assemble_story_model_from_mgt_npz(roundtrip_npz=roundtrip_npz)
    static_cfg = RustNonlinearFrameConfig(tolerance=1.0e-6, max_iter=120)
    ndtha_cfg = RustNonlinearNdthaConfig(dt_s=0.02, newton_max_iter=90, max_step_iterations=14)
    ag = _deterministic_ag(dt_s=float(ndtha_cfg.dt_s), step_count=int(step_count))

    static = solve_nonlinear_frame(
        story_k_n_per_m=story["story_k_n_per_m"],
        story_h_m=story["story_h_m"],
        story_axial_n=story["story_axial_n"],
        story_yield_drift_m=story["story_yield_drift_m"],
        floor_load_n=story["floor_load_base_n"],
        cfg=static_cfg,
    )
    ndtha = solve_nonlinear_frame_ndtha(
        story_k_n_per_m=story["story_k_n_per_m"],
        story_h_m=story["story_h_m"],
        story_axial_n=story["story_axial_n"],
        story_yield_drift_m=story["story_yield_drift_m"],
        story_mass_kg=story["story_mass_kg"],
        story_damping_n_s_per_m=story["story_damping_n_s_per_m"],
        floor_load_base_n=story["floor_load_base_n"],
        ag_g=ag,
        cfg=ndtha_cfg,
    )

    static_runtime = static.get("runtime") if isinstance(static.get("runtime"), dict) else {}
    ndtha_runtime = ndtha.get("runtime") if isinstance(ndtha.get("runtime"), dict) else {}
    static_backend = static_runtime.get("main_loop_backend") or static.get("backend")
    ndtha_backend = ndtha_runtime.get("main_loop_backend") or ndtha.get("backend")
    observed_backends = {
        str(value)
        for value in (static_backend, ndtha_backend)
        if str(value)
    }
    hip_backend_ready = observed_backends == {"rocm_torch_hip_mainloop"}
    converged = bool(static.get("converged")) and bool(ndtha.get("converged_all_steps"))
    if not hip_backend_ready:
        blockers.append("rocm_hip_backend_unavailable_or_cpu_fallback")
    if not converged:
        blockers.append("condensed_solve_not_converged")
    ready = bool(converged and hip_backend_ready)

    roundtrip = load_json(roundtrip_json)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "warn",
        "claim": (
            "MGT NPZ mesh condensed to story-level nonlinear frame and solved in-repo; "
            "not a full 3D global FEA licensed-engine replay."
        ),
        "native_solve_status": (
            "condensed_global_fea_wired"
            if ready
            else "condensed_global_fea_backend_blocked"
            if not hip_backend_ready
            else "condensed_solve_failed"
        ),
        "solve_mode": "mgt_npz_mesh_condensed_story",
        "backend_policy": {
            "required_backend": "rocm_torch_hip_mainloop",
            "observed_backends": sorted(observed_backends),
            "hip_backend_ready": hip_backend_ready,
            "cpu_fallback_non_promoting": not hip_backend_ready,
        },
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "story_assembly": {
            "story_count": story["story_count"],
            "elevation_levels_m": story["elevation_levels_m"],
            "elem_per_story": story["elem_per_story"],
        },
        "static_solve": {
            "converged": static.get("converged"),
            "iterations": static.get("iterations"),
            "top_displacement_m": static.get("top_displacement_m"),
            "base_shear_kn": float(static.get("base_shear_kn") or 0.0),
            "backend": static_backend,
        },
        "ndtha_solve": {
            "converged_all_steps": ndtha.get("converged_all_steps"),
            "max_drift_ratio_pct": ndtha.get("max_drift_ratio_pct"),
            "backend": ndtha_backend,
        },
        "blockers": blockers,
    }
