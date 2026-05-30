#!/usr/bin/env python3
"""Record honest GPU vs CPU solver backend claims from a story-model solve (E-P1b)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_npz
from design_optimization_env import DesignOptimizationConfig
from run_design_optimization_solver_loop import _solver_stage_state


SCHEMA_VERSION = "gpu-solver-claim-receipt.v1"


def build_gpu_solver_claim_receipt(
    *,
    state_npz_path: Path,
    cfg: DesignOptimizationConfig | None = None,
) -> dict[str, Any]:
    state = load_npz(state_npz_path)
    stage = _solver_stage_state(state=state, cfg=cfg or DesignOptimizationConfig())
    backend_static = str(stage.get("backend_static") or "").lower()
    backend_ndtha = str(stage.get("backend_ndtha") or "").lower()
    gpu_used = any(token in backend_static for token in ("hip", "gpu", "rocm")) or any(
        token in backend_ndtha for token in ("hip", "gpu", "rocm")
    )
    cpu_only = bool(backend_static) and "cpu" in backend_static and not gpu_used
    runtime_static = stage.get("runtime_static") if isinstance(stage.get("runtime_static"), dict) else {}
    runtime_ndtha = stage.get("runtime_ndtha") if isinstance(stage.get("runtime_ndtha"), dict) else {}

    def _mainloop_residency(runtime: dict[str, Any]) -> bool:
        backend = str(runtime.get("main_loop_backend") or "").lower()
        return (
            not bool(runtime.get("cpu_fallback_used"))
            and "rocm" in backend
            and str(runtime.get("solver_path_kind") or "") == "production_hip_kernel"
        )

    gpu_mainloop_residency = _mainloop_residency(runtime_static) and _mainloop_residency(runtime_ndtha)
    claim = (
        "gpu_assist_observed"
        if gpu_used
        else "cpu_newton_primary"
        if cpu_only or backend_static
        else "backend_unknown"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_label": claim,
        "gpu_newton_terminal_proven": False,
        "gpu_mainloop_residency_observed": gpu_mainloop_residency,
        "gpu_assist_observed": gpu_used,
        "cpu_primary": cpu_only or not gpu_used,
        "backends": {
            "static": backend_static,
            "ndtha": backend_ndtha,
        },
        "runtime_telemetry": {
            "static": runtime_static,
            "ndtha": runtime_ndtha,
        },
        "marketing_safe_wording": (
            "GPU main-loop residency may be observed; nonlinear Newton terminal solve on GPU is not proven "
            "and must not be claimed without dedicated certification."
        ),
        "state_npz_path": str(state_npz_path),
    }
