#!/usr/bin/env python3
"""Adaptive controller for the direct-residual preconditioned global Krylov lane."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_mgt_direct_residual_newton_probe import (
    DEFAULT_CHECKPOINT,
    DEFAULT_MGT,
    PRODUCTIZATION,
    _load_checkpoint,
    run_mgt_direct_residual_newton_probe,
)


SCHEMA_VERSION = "mgt-direct-residual-adaptive-preconditioned-global-newton.v1"


def _parse_float_csv(text: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(text).split(",") if value.strip())


def _factor_label(value: float) -> str:
    return f"{float(value):.0e}".replace("-", "m").replace("+", "")


def _get_direct_residual(payload: dict[str, Any], field: str) -> float | None:
    group = payload.get(field)
    if not isinstance(group, dict):
        return None
    value = group.get("direct_residual_inf_n")
    return float(value) if value is not None else None


def _best_global_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    krylov = payload.get("matrix_free_global_krylov")
    if not isinstance(krylov, dict):
        return {}
    best = krylov.get("best_candidate")
    return best if isinstance(best, dict) else {}


def _accepted_component_flags(payload: dict[str, Any]) -> dict[str, bool]:
    def _accepted(name: str) -> bool:
        component = payload.get(name)
        return bool(component.get("accepted")) if isinstance(component, dict) else False

    return {
        "secant_family": _accepted("secant_family_globalization"),
        "matrix_free_global_krylov": _accepted("matrix_free_global_krylov"),
        "matrix_free_jacobian_subspace": _accepted(
            "matrix_free_consistent_jacobian_subspace"
        ),
        "current_tangent_residual_row": _accepted(
            "current_tangent_residual_row_correction"
        ),
    }


def _child_strict_hip_promotion_blockers(
    *,
    require_hip_batch_replay: bool,
    child_payload: dict[str, Any],
) -> list[str]:
    if not require_hip_batch_replay:
        return []
    blockers: list[str] = []
    gate = child_payload.get("gate_assessment")
    if not isinstance(gate, dict) or gate.get("fallback_zero_passed") is not True:
        blockers.append("child_fallback_zero_audit_not_closed")
    residual_contract = child_payload.get("residual_contract")
    if (
        not isinstance(residual_contract, dict)
        or residual_contract.get("hip_residual_engine_contract_passed") is not True
    ):
        blockers.append("child_hip_residual_engine_contract_not_proven")
    return blockers


def _row_hip_residual_engine_contract_passed(row: dict[str, Any]) -> bool:
    if row.get("child_hip_residual_engine_contract_passed") is True:
        return True
    residual_contract = row.get("child_residual_contract")
    return (
        isinstance(residual_contract, dict)
        and residual_contract.get("hip_residual_engine_contract_passed") is True
    )


def _csv(values: tuple[float, ...] | tuple[int, ...]) -> str:
    return ",".join(str(value) for value in values)


def _build_adaptive_global_claim_boundary(
    *,
    require_hip_batch_replay: bool,
    backend_is_hip: bool,
    hip_preflight_available: bool,
    runtime_budget_exceeded: bool,
    promoted_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    conservative = {
        "cpu_diagnostic_only": True,
        "official_rocm_hip_closure_required": True,
        "residual_replay_is_regularization_free": True,
        "regularization_used_only_for_preconditioner_direction": True,
        "ai_residual_correction_is_candidate_generation_only": True,
    }
    if not require_hip_batch_replay:
        return conservative
    if not backend_is_hip:
        return conservative
    if not hip_preflight_available:
        return conservative
    if runtime_budget_exceeded:
        return conservative
    if not promoted_rows:
        return conservative
    child_timeout_occurred = any(
        bool(row.get("subprocess_timeout")) for row in rows
    )
    if child_timeout_occurred:
        return conservative
    host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency = False
    for row in promoted_rows:
        if not _row_hip_residual_engine_contract_passed(row):
            return conservative
        gate = row.get("child_gate_assessment")
        if not isinstance(gate, dict):
            return conservative
        if gate.get("fallback_zero_passed") is not True:
            return conservative
        claim_boundary = row.get("child_claim_boundary")
        if isinstance(claim_boundary, dict):
            if claim_boundary.get("cpu_diagnostic_only") is True:
                return conservative
            if claim_boundary.get("official_rocm_hip_closure_required") is True:
                return conservative
        elif isinstance(claim_boundary, str) and claim_boundary:
            lowered = claim_boundary.lower()
            if any(
                token in lowered
                for token in ("cpu", "host", "fallback", "rocm", "hip-required", "hip")
            ):
                residual_contract = row.get("child_residual_contract")
                if isinstance(residual_contract, dict):
                    if (
                        residual_contract.get(
                        "allow_state_dependent_shell_material_tangent_hip_replay"
                        )
                        and residual_contract.get(
                            "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency"
                        )
                    ):
                        host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency = True
                    elif residual_contract.get(
                        "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure"
                    ):
                        return conservative
                    else:
                        return conservative
                else:
                    return conservative
        child_blockers = row.get("child_blockers")
        if isinstance(child_blockers, list):
            for blocker in child_blockers:
                text = str(blocker)
                if any(
                    token in text
                    for token in (
                        "fallback",
                        "cpu_",
                        "host_",
                        "rocm_hip",
                        "hip_required",
                        "hip_batch_replay_required_unavailable",
                        "hip_krylov_solver_required_unavailable",
                    )
                ):
                    return conservative
    return {
        "cpu_diagnostic_only": False,
        "official_rocm_hip_closure_required": False,
        "residual_replay_is_regularization_free": True,
        "regularization_used_only_for_preconditioner_direction": True,
        "ai_residual_correction_is_candidate_generation_only": True,
        "host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency": (
            host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency
        ),
    }


def _collect_hip_preflight() -> dict[str, Any]:
    preflight: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "hip_available": False,
        "torch_importable": False,
        "cuda_device_count": 0,
        "diagnostic": "",
    }
    try:
        import torch
        preflight["torch_importable"] = True
    except ImportError:
        preflight["diagnostic"] = "torch_not_importable"
        return preflight
    try:
        preflight["cuda_device_count"] = torch.cuda.device_count()
        preflight["hip_available"] = bool(torch.cuda.is_available())
    except Exception as exc:
        preflight["diagnostic"] = str(exc)
    return preflight


def _child_launch_receipt(
    *,
    child_json: Path,
    child_checkpoint: Path,
    checkpoint_npz: Path,
    tangent_regularization_factor: float,
    preconditioner_input_scale: float,
    difference_scheme: str,
    preconditioner_mode: str,
    batch_replay_backend: str,
    require_hip_batch_replay: bool,
    linear_solver_backend: str,
    child_timeout_seconds: float | None,
    command: list[str],
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": "mgt-direct-residual-adaptive-child-launch.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
        "checkpoint": str(checkpoint_npz),
        "output_json": str(child_json),
        "output_final_checkpoint_npz": str(child_checkpoint),
        "tangent_regularization_factor": float(tangent_regularization_factor),
        "preconditioner_input_scale": float(preconditioner_input_scale),
        "difference_scheme": str(difference_scheme),
        "preconditioner_mode": str(preconditioner_mode),
        "batch_replay_backend": str(batch_replay_backend),
        "require_hip_batch_replay": bool(require_hip_batch_replay),
        "linear_solver_backend": str(linear_solver_backend),
        "child_timeout_seconds": (
            None if child_timeout_seconds is None else float(child_timeout_seconds)
        ),
        "command": command,
        "allow_frozen_shell_material_tangent_hip_replay": bool(
            allow_frozen_shell_material_tangent_hip_replay
        ),
        "allow_state_dependent_shell_material_tangent_hip_replay": bool(
            allow_state_dependent_shell_material_tangent_hip_replay
        ),
        "claim_boundary": (
            "Controller launch receipt only. A completed or timeout child receipt must "
            "replace this before claiming residual progress."
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _run_child_subprocess(
    *,
    mgt_path: Path,
    checkpoint_npz: Path,
    child_json: Path,
    child_checkpoint: Path,
    compact_output_final_checkpoint: bool,
    factor: float,
    preconditioner_input_scale: float,
    shell_pressure_load_path_policy: str,
    apply_shell_material_tangent: bool,
    allow_frozen_shell_material_tangent_hip_replay: bool,
    allow_state_dependent_shell_material_tangent_hip_replay: bool,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
    matrix_free_global_krylov_max_iterations: int,
    matrix_free_global_krylov_difference_scheme: str,
    matrix_free_global_krylov_probe_epsilon: float,
    matrix_free_global_krylov_probe_max_step: float,
    matrix_free_global_krylov_residual_scale_floor: float,
    matrix_free_global_krylov_preconditioner_mode: str,
    matrix_free_global_krylov_alpha_values: tuple[float, ...],
    matrix_free_global_krylov_max_alpha: float,
    matrix_free_global_krylov_min_relative_improvement: float,
    matrix_free_global_krylov_full_assembly_trial_replay: bool,
    matrix_free_global_krylov_batch_replay_backend: str,
    matrix_free_global_krylov_require_hip_batch_replay: bool,
    matrix_free_global_krylov_linear_solver_backend: str,
    enable_secant_family_seed: bool,
    max_secant_family_promotions: int,
    secant_family_window_sizes: tuple[int, ...],
    secant_family_ridge_factors: tuple[float, ...],
    secant_family_alpha_values: tuple[float, ...],
    secant_family_min_relative_improvement: float,
    child_timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    script = Path(__file__).resolve().with_name("run_mgt_direct_residual_newton_probe.py")
    cmd = [
        sys.executable,
        str(script),
        "--mgt-path",
        str(mgt_path),
        "--checkpoint-npz",
        str(checkpoint_npz),
        "--output-json",
        str(child_json),
        "--output-final-checkpoint-npz",
        str(child_checkpoint),
        "--shell-pressure-load-path-policy",
        str(shell_pressure_load_path_policy),
        "--residual-tolerance-n",
        str(float(residual_tolerance_n)),
        "--relative-increment-tolerance",
        str(float(relative_increment_tolerance)),
        "--max-trust-iterations",
        "0",
        "--disable-secant-subspace-globalization",
        "--disable-matrix-free-jacobian-subspace",
        "--enable-matrix-free-global-krylov",
        "--matrix-free-global-krylov-max-iterations",
        str(int(matrix_free_global_krylov_max_iterations)),
        "--matrix-free-global-krylov-difference-scheme",
        str(matrix_free_global_krylov_difference_scheme),
        "--matrix-free-global-krylov-probe-epsilon",
        str(float(matrix_free_global_krylov_probe_epsilon)),
        "--matrix-free-global-krylov-probe-max-step",
        str(float(matrix_free_global_krylov_probe_max_step)),
        "--matrix-free-global-krylov-scaling-mode",
        "residual_diagonal_displacement",
        "--matrix-free-global-krylov-residual-scale-floor",
        str(float(matrix_free_global_krylov_residual_scale_floor)),
        "--matrix-free-global-krylov-preconditioner-mode",
        str(matrix_free_global_krylov_preconditioner_mode),
        "--matrix-free-global-krylov-preconditioner-input-scale",
        str(float(preconditioner_input_scale)),
        "--matrix-free-global-krylov-tangent-regularization-factor",
        str(float(factor)),
        "--matrix-free-global-krylov-allow-negative-alphas",
        "--matrix-free-global-krylov-max-alpha",
        str(float(matrix_free_global_krylov_max_alpha)),
        "--matrix-free-global-krylov-alpha-values",
        _csv(matrix_free_global_krylov_alpha_values),
        "--matrix-free-global-krylov-min-relative-improvement",
        str(float(matrix_free_global_krylov_min_relative_improvement)),
        "--matrix-free-global-krylov-batch-replay-backend",
        str(matrix_free_global_krylov_batch_replay_backend),
        "--matrix-free-global-krylov-linear-solver-backend",
        str(matrix_free_global_krylov_linear_solver_backend),
    ]
    if matrix_free_global_krylov_require_hip_batch_replay:
        cmd.append("--matrix-free-global-krylov-require-hip-batch-replay")
    if matrix_free_global_krylov_full_assembly_trial_replay:
        cmd.append("--matrix-free-global-krylov-full-assembly-trial-replay")
    if not matrix_free_global_krylov_require_hip_batch_replay:
        cmd.append("--allow-cpu-diagnostic")
    if compact_output_final_checkpoint:
        insertion = cmd.index("--shell-pressure-load-path-policy")
        cmd[insertion:insertion] = ["--compact-output-final-checkpoint"]
    if apply_shell_material_tangent:
        insertion = cmd.index("--residual-tolerance-n")
        cmd[insertion:insertion] = ["--apply-shell-material-tangent"]
    if (
        apply_shell_material_tangent
        and allow_frozen_shell_material_tangent_hip_replay
        and not allow_state_dependent_shell_material_tangent_hip_replay
    ):
        cmd.append("--allow-frozen-shell-material-tangent-hip-replay")
    if (
        apply_shell_material_tangent
        and allow_state_dependent_shell_material_tangent_hip_replay
    ):
        cmd.append("--allow-state-dependent-shell-material-tangent-hip-replay")
    if enable_secant_family_seed:
        cmd.extend(
            [
                "--enable-secant-family-globalization",
                "--max-secant-family-promotions",
                str(int(max_secant_family_promotions)),
                "--secant-family-window-sizes",
                _csv(secant_family_window_sizes),
                "--secant-family-ridge-factors",
                _csv(secant_family_ridge_factors),
                "--secant-family-alpha-values",
                _csv(secant_family_alpha_values),
                "--secant-family-min-relative-improvement",
                str(float(secant_family_min_relative_improvement)),
            ]
        )
    _write_json(
        child_json,
        _child_launch_receipt(
            child_json=child_json,
            child_checkpoint=child_checkpoint,
            checkpoint_npz=checkpoint_npz,
            tangent_regularization_factor=factor,
            preconditioner_input_scale=preconditioner_input_scale,
            difference_scheme=matrix_free_global_krylov_difference_scheme,
            preconditioner_mode=matrix_free_global_krylov_preconditioner_mode,
            batch_replay_backend=matrix_free_global_krylov_batch_replay_backend,
            require_hip_batch_replay=(
                matrix_free_global_krylov_require_hip_batch_replay
            ),
            linear_solver_backend=matrix_free_global_krylov_linear_solver_backend,
            child_timeout_seconds=child_timeout_seconds,
            command=cmd,
            allow_frozen_shell_material_tangent_hip_replay=bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            allow_state_dependent_shell_material_tangent_hip_replay=bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
        ),
    )
    try:
        completed = subprocess.run(
            cmd,
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(child_timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        checkpoint_meta, _u, _state_history, _residual_history = _load_checkpoint(
            checkpoint_npz
        )
        timeout_payload = {
            "schema_version": "mgt-direct-residual-adaptive-child-timeout.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "timeout",
            "checkpoint": str(checkpoint_npz),
            "base_direct_residual": {
                "direct_residual_inf_n": checkpoint_meta.get("residual_inf_n"),
            },
            "tangent_regularization_factor": float(factor),
            "preconditioner_input_scale": float(preconditioner_input_scale),
            "difference_scheme": str(matrix_free_global_krylov_difference_scheme),
            "preconditioner_mode": str(
                matrix_free_global_krylov_preconditioner_mode
            ),
            "batch_replay_backend": str(
                matrix_free_global_krylov_batch_replay_backend
            ),
            "require_hip_batch_replay": bool(
                matrix_free_global_krylov_require_hip_batch_replay
            ),
            "linear_solver_backend": str(
                matrix_free_global_krylov_linear_solver_backend
            ),
            "apply_shell_material_tangent": bool(apply_shell_material_tangent),
            "allow_frozen_shell_material_tangent_hip_replay": bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "matrix_free_global_krylov": {
                "enabled": True,
                "attempted": True,
                "accepted": False,
                "stop_reason": "child_timeout_seconds_exceeded",
            },
            "child_timeout_seconds": float(child_timeout_seconds),
            "command": cmd,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "output_final_checkpoint_written": False,
            "claim_boundary": (
                "Timeout receipt only. No residual descent is claimed because the child "
                "probe did not finish and no final checkpoint was written."
            ),
        }
        _write_json(child_json, timeout_payload)
        return timeout_payload, {
            "subprocess_returncode": None,
            "subprocess_timeout": True,
            "subprocess_stdout": exc.stdout or "",
            "subprocess_stderr": exc.stderr or "",
            "subprocess_command": cmd,
        }
    if not child_json.is_file():
        child_payload = {
            "schema_version": "mgt-direct-residual-adaptive-child-missing-output.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "tangent_regularization_factor": float(factor),
            "preconditioner_input_scale": float(preconditioner_input_scale),
            "difference_scheme": str(matrix_free_global_krylov_difference_scheme),
            "matrix_free_global_krylov": {
                "enabled": True,
                "attempted": True,
                "accepted": False,
                "stop_reason": "child_output_json_missing",
            },
            "command": cmd,
        }
        _write_json(child_json, child_payload)
    else:
        child_payload = json.loads(child_json.read_text(encoding="utf-8"))
        if not isinstance(child_payload, dict):
            child_payload = {"status": "blocked", "reason": "child_payload_not_object"}
    return child_payload, {
        "subprocess_returncode": int(completed.returncode),
        "subprocess_timeout": False,
        "subprocess_stdout": completed.stdout,
        "subprocess_stderr": completed.stderr,
        "subprocess_command": cmd,
    }


def run_adaptive_preconditioned_global_newton(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = None,
    output_final_checkpoint_npz: Path | None = None,
    compact_output_final_checkpoint: bool = False,
    child_output_dir: Path | None = None,
    tangent_regularization_factors: tuple[float, ...] = (1.0e-6, 3.0e-6),
    max_controller_steps: int = 1,
    matrix_free_global_krylov_max_iterations: int = 3,
    matrix_free_global_krylov_difference_scheme: str = "forward",
    matrix_free_global_krylov_probe_epsilon: float = 1.0e-6,
    matrix_free_global_krylov_probe_max_step: float = 1.0e-5,
    matrix_free_global_krylov_residual_scale_floor: float = 1.0,
    matrix_free_global_krylov_preconditioner_mode: str = "current_tangent",
    matrix_free_global_krylov_preconditioner_input_scales: tuple[float, ...] = (1.0,),
    matrix_free_global_krylov_alpha_values: tuple[float, ...] = (
        8.0,
        4.0,
        2.0,
        1.0,
        0.5,
        0.25,
    ),
    matrix_free_global_krylov_max_alpha: float = 8.0,
    matrix_free_global_krylov_min_relative_improvement: float = 1.0e-6,
    matrix_free_global_krylov_full_assembly_trial_replay: bool = True,
    matrix_free_global_krylov_batch_replay_backend: str = "cpu",
    matrix_free_global_krylov_require_hip_batch_replay: bool = False,
    matrix_free_global_krylov_linear_solver_backend: str = "scipy_host_gmres",
    enable_secant_family_seed: bool = False,
    max_secant_family_promotions: int = 1,
    secant_family_window_sizes: tuple[int, ...] = (4, 8, 16),
    secant_family_ridge_factors: tuple[float, ...] = (0.0, 1.0e-8),
    secant_family_alpha_values: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
    ),
    secant_family_min_relative_improvement: float = 1.0e-6,
    shell_pressure_load_path_policy: str = "all_components",
    apply_shell_material_tangent: bool = False,
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
    residual_tolerance_n: float = 5.0e-4,
    relative_increment_tolerance: float = 1.0e-4,
    max_controller_runtime_seconds: float | None = None,
    child_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    output_json = output_json or (
        PRODUCTIZATION / "mgt_direct_residual_adaptive_preconditioned_global_newton_smoke.json"
    )
    child_output_dir = child_output_dir or output_json.parent
    child_output_dir.mkdir(parents=True, exist_ok=True)

    current_checkpoint = Path(checkpoint_npz)
    initial_checkpoint = Path(checkpoint_npz)
    controller_rows: list[dict[str, Any]] = []
    promotion_count = 0
    stop_reason = "max_controller_steps_reached"
    final_checkpoint = current_checkpoint
    final_residual_inf_n: float | None = None
    runtime_budget_exceeded = False
    runtime_budget_seconds = (
        float(max_controller_runtime_seconds)
        if max_controller_runtime_seconds is not None
        else None
    )
    global_krylov_batch_replay_backend = str(
        matrix_free_global_krylov_batch_replay_backend
    ).strip().lower()
    if global_krylov_batch_replay_backend not in {
        "cpu",
        "hip_full_residual",
        "hip_full_residual_resident",
        "rust_hip_full_residual_ffi",
    }:
        global_krylov_batch_replay_backend = "cpu"
    if (
        matrix_free_global_krylov_require_hip_batch_replay
        and global_krylov_batch_replay_backend == "cpu"
    ):
        raise ValueError(
            "matrix_free_global_krylov_require_hip_batch_replay=True requires "
            "a HIP batch replay backend (hip_full_residual, "
            "hip_full_residual_resident, rust_hip_full_residual_ffi), "
            "but matrix_free_global_krylov_batch_replay_backend is 'cpu'"
        )
    global_krylov_difference_scheme = (
        str(matrix_free_global_krylov_difference_scheme).strip().lower()
    )
    if global_krylov_difference_scheme not in {"forward", "central"}:
        global_krylov_difference_scheme = "forward"
    global_krylov_preconditioner_mode = (
        str(matrix_free_global_krylov_preconditioner_mode).strip().lower()
    )
    if global_krylov_preconditioner_mode not in {"none", "current_tangent"}:
        global_krylov_preconditioner_mode = "current_tangent"
    preconditioner_mode_disabled_reason = ""
    if (
        matrix_free_global_krylov_require_hip_batch_replay
        and global_krylov_preconditioner_mode == "current_tangent"
    ):
        preconditioner_mode_disabled_reason = (
            "hip_batch_replay_required_suppresses_cpu_current_tangent_preconditioner"
        )
        global_krylov_preconditioner_mode = "none"
    global_krylov_linear_solver_backend = str(
        matrix_free_global_krylov_linear_solver_backend
    ).strip().lower()
    if global_krylov_linear_solver_backend not in {
        "scipy_host_gmres",
        "torch_hip_gmres",
    }:
        global_krylov_linear_solver_backend = "scipy_host_gmres"
    linear_solver_backend_auto_selected_reason = ""
    if (
        matrix_free_global_krylov_require_hip_batch_replay
        and global_krylov_linear_solver_backend == "scipy_host_gmres"
    ):
        linear_solver_backend_auto_selected_reason = (
            "hip_batch_replay_required_suppresses_host_gmres"
        )
        global_krylov_linear_solver_backend = "torch_hip_gmres"

    hip_preflight = None
    needs_hip_preflight = (
        matrix_free_global_krylov_require_hip_batch_replay
        or global_krylov_linear_solver_backend == "torch_hip_gmres"
    )
    if needs_hip_preflight:
        hip_preflight = _collect_hip_preflight()
        if not hip_preflight.get("hip_available"):
            stop_reason = "hip_runtime_unavailable"
            output_json.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": generated_at,
                "status": "partial",
                "adaptive_preconditioned_global_newton_ready": False,
                "hip_preflight": hip_preflight,
                "controller": {
                    "enabled": True,
                    "attempted": False,
                    "promotion_count": 0,
                    "max_controller_steps": int(max_controller_steps),
                    "stop_reason": stop_reason,
                    "tangent_regularization_factors": [
                        float(value) for value in tangent_regularization_factors
                    ],
                    "matrix_free_global_krylov_max_iterations": int(
                        matrix_free_global_krylov_max_iterations
                    ),
                    "matrix_free_global_krylov_difference_scheme": (
                        global_krylov_difference_scheme
                    ),
                    "matrix_free_global_krylov_alpha_values": [
                        float(value) for value in matrix_free_global_krylov_alpha_values
                    ],
                    "matrix_free_global_krylov_preconditioner_input_scales": [
                        float(value)
                        for value in (
                            matrix_free_global_krylov_preconditioner_input_scales
                            or (1.0,)
                        )
                        if float(value) > 0.0
                    ],
                    "matrix_free_global_krylov_residual_scale_floor": float(
                        matrix_free_global_krylov_residual_scale_floor
                    ),
                    "matrix_free_global_krylov_preconditioner_mode": str(
                        global_krylov_preconditioner_mode
                    ),
                    "matrix_free_global_krylov_preconditioner_mode_disabled_reason": (
                        preconditioner_mode_disabled_reason
                    ),
                    "matrix_free_global_krylov_max_alpha": float(
                        matrix_free_global_krylov_max_alpha
                    ),
                    "matrix_free_global_krylov_full_assembly_trial_replay": bool(
                        matrix_free_global_krylov_full_assembly_trial_replay
                    ),
                    "matrix_free_global_krylov_batch_replay_backend": str(
                        global_krylov_batch_replay_backend
                    ),
                    "matrix_free_global_krylov_require_hip_batch_replay": bool(
                        matrix_free_global_krylov_require_hip_batch_replay
                    ),
                    "matrix_free_global_krylov_linear_solver_backend": str(
                        global_krylov_linear_solver_backend
                    ),
                    "matrix_free_global_krylov_linear_solver_backend_auto_selected_reason": (
                        linear_solver_backend_auto_selected_reason
                    ),
                    "minimum_relative_improvement": float(
                        matrix_free_global_krylov_min_relative_improvement
                    ),
                    "secant_family_seed_enabled": bool(enable_secant_family_seed),
                    "max_secant_family_promotions": int(max_secant_family_promotions),
                    "secant_family_window_sizes": [
                        int(value) for value in secant_family_window_sizes
                    ],
                    "secant_family_ridge_factors": [
                        float(value) for value in secant_family_ridge_factors
                    ],
                    "secant_family_alpha_values": [
                        float(value) for value in secant_family_alpha_values
                    ],
                    "secant_family_minimum_relative_improvement": float(
                        secant_family_min_relative_improvement
                    ),
                    "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
                    "apply_shell_material_tangent": bool(apply_shell_material_tangent),
                    "allow_frozen_shell_material_tangent_hip_replay": bool(
                        allow_frozen_shell_material_tangent_hip_replay
                    ),
                    "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                        allow_state_dependent_shell_material_tangent_hip_replay
                    ),
                    "compact_output_final_checkpoint": bool(compact_output_final_checkpoint),
                    "runtime_budget_seconds": runtime_budget_seconds,
                    "runtime_budget_exceeded": False,
                    "child_timeout_seconds": (
                        None if child_timeout_seconds is None else float(child_timeout_seconds)
                    ),
                },
                "initial_checkpoint_path": str(initial_checkpoint),
                "final_checkpoint_path": str(current_checkpoint),
                "final_direct_residual_inf_n": None,
                "rows": [],
                "promoted_rows": [],
                "best_candidate_row": {},
                "runtime_seconds": float(time.perf_counter() - started),
                "claim_boundary": {
                    "cpu_diagnostic_only": True,
                    "official_rocm_hip_closure_required": True,
                    "residual_replay_is_regularization_free": True,
                    "regularization_used_only_for_preconditioner_direction": True,
                    "ai_residual_correction_is_candidate_generation_only": True,
                },
            }
            output_json.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return payload

    for step_index in range(max(int(max_controller_steps), 0)):
        step_promoted = False
        preconditioner_input_scales = tuple(
            float(value)
            for value in matrix_free_global_krylov_preconditioner_input_scales
            if float(value) > 0.0
        ) or (1.0,)
        for factor in tangent_regularization_factors:
            for preconditioner_input_scale in preconditioner_input_scales:
                if (
                    runtime_budget_seconds is not None
                    and time.perf_counter() - started >= runtime_budget_seconds
                ):
                    runtime_budget_exceeded = True
                    stop_reason = "runtime_budget_exceeded"
                    break
                label = _factor_label(float(factor))
                scale_label = _factor_label(float(preconditioner_input_scale))
                child_json = child_output_dir / (
                    f"{output_json.stem}_step{step_index + 1}_reg{label}_scale{scale_label}.json"
                )
                child_checkpoint = child_output_dir / (
                    f"{output_json.stem}_step{step_index + 1}_reg{label}_scale{scale_label}_final_checkpoint.npz"
                )
                child_started = time.perf_counter()
                child_subprocess_meta: dict[str, Any] = {}
                effective_child_timeout_seconds = (
                    float(child_timeout_seconds)
                    if child_timeout_seconds is not None and float(child_timeout_seconds) > 0.0
                    else None
                )
                if effective_child_timeout_seconds is None and runtime_budget_seconds is not None:
                    remaining_runtime_budget = runtime_budget_seconds - (
                        time.perf_counter() - started
                    )
                    if remaining_runtime_budget <= 0.0:
                        runtime_budget_exceeded = True
                        stop_reason = "runtime_budget_exceeded"
                        break
                    effective_child_timeout_seconds = max(float(remaining_runtime_budget), 1.0e-6)
                if effective_child_timeout_seconds is not None:
                    child_payload, child_subprocess_meta = _run_child_subprocess(
                        mgt_path=mgt_path,
                        checkpoint_npz=current_checkpoint,
                        child_json=child_json,
                        child_checkpoint=child_checkpoint,
                        compact_output_final_checkpoint=bool(compact_output_final_checkpoint),
                        factor=float(factor),
                        preconditioner_input_scale=float(preconditioner_input_scale),
                        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
                        apply_shell_material_tangent=bool(apply_shell_material_tangent),
                        allow_frozen_shell_material_tangent_hip_replay=bool(
                            allow_frozen_shell_material_tangent_hip_replay
                        ),
                        allow_state_dependent_shell_material_tangent_hip_replay=bool(
                            allow_state_dependent_shell_material_tangent_hip_replay
                        ),
                        residual_tolerance_n=residual_tolerance_n,
                        relative_increment_tolerance=relative_increment_tolerance,
                        matrix_free_global_krylov_max_iterations=(
                            matrix_free_global_krylov_max_iterations
                        ),
                        matrix_free_global_krylov_difference_scheme=(
                            global_krylov_difference_scheme
                        ),
                        matrix_free_global_krylov_probe_epsilon=(
                            matrix_free_global_krylov_probe_epsilon
                        ),
                        matrix_free_global_krylov_probe_max_step=(
                            matrix_free_global_krylov_probe_max_step
                        ),
                        matrix_free_global_krylov_residual_scale_floor=(
                            matrix_free_global_krylov_residual_scale_floor
                        ),
                        matrix_free_global_krylov_preconditioner_mode=(
                            global_krylov_preconditioner_mode
                        ),
                        matrix_free_global_krylov_alpha_values=(
                            matrix_free_global_krylov_alpha_values
                        ),
                        matrix_free_global_krylov_max_alpha=(
                            matrix_free_global_krylov_max_alpha
                        ),
                        matrix_free_global_krylov_min_relative_improvement=(
                            matrix_free_global_krylov_min_relative_improvement
                        ),
                        matrix_free_global_krylov_full_assembly_trial_replay=(
                            matrix_free_global_krylov_full_assembly_trial_replay
                        ),
                        matrix_free_global_krylov_batch_replay_backend=(
                            global_krylov_batch_replay_backend
                        ),
                        matrix_free_global_krylov_require_hip_batch_replay=(
                            matrix_free_global_krylov_require_hip_batch_replay
                        ),
                        matrix_free_global_krylov_linear_solver_backend=(
                            global_krylov_linear_solver_backend
                        ),
                        enable_secant_family_seed=bool(enable_secant_family_seed),
                        max_secant_family_promotions=max_secant_family_promotions,
                        secant_family_window_sizes=secant_family_window_sizes,
                        secant_family_ridge_factors=secant_family_ridge_factors,
                        secant_family_alpha_values=secant_family_alpha_values,
                        secant_family_min_relative_improvement=(
                            secant_family_min_relative_improvement
                        ),
                        child_timeout_seconds=float(effective_child_timeout_seconds),
                    )
                else:
                    child_payload = run_mgt_direct_residual_newton_probe(
                        mgt_path=mgt_path,
                        checkpoint_npz=current_checkpoint,
                        output_json=child_json,
                        output_final_checkpoint_npz=child_checkpoint,
                        compact_output_final_checkpoint=bool(compact_output_final_checkpoint),
                        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
                        apply_shell_material_tangent=bool(apply_shell_material_tangent),
                        allow_frozen_shell_material_tangent_hip_replay=bool(
                            allow_frozen_shell_material_tangent_hip_replay
                        ),
                        allow_state_dependent_shell_material_tangent_hip_replay=bool(
                            allow_state_dependent_shell_material_tangent_hip_replay
                        ),
                        residual_tolerance_n=residual_tolerance_n,
                        relative_increment_tolerance=relative_increment_tolerance,
                        max_trust_iterations=0,
                        enable_secant_subspace_globalization=False,
                        enable_secant_family_globalization=bool(enable_secant_family_seed),
                        max_secant_family_promotions=max_secant_family_promotions,
                        secant_family_window_sizes=secant_family_window_sizes,
                        secant_family_ridge_factors=secant_family_ridge_factors,
                        secant_family_alpha_values=secant_family_alpha_values,
                        secant_family_min_relative_improvement=(
                            secant_family_min_relative_improvement
                        ),
                        enable_matrix_free_jacobian_subspace=False,
                        enable_matrix_free_global_krylov=True,
                        matrix_free_global_krylov_max_iterations=(
                            matrix_free_global_krylov_max_iterations
                        ),
                        matrix_free_global_krylov_difference_scheme=(
                            global_krylov_difference_scheme
                        ),
                        matrix_free_global_krylov_probe_epsilon=(
                            matrix_free_global_krylov_probe_epsilon
                        ),
                        matrix_free_global_krylov_probe_max_step=(
                            matrix_free_global_krylov_probe_max_step
                        ),
                        matrix_free_global_krylov_scaling_mode="residual_diagonal_displacement",
                        matrix_free_global_krylov_residual_scale_floor=(
                            matrix_free_global_krylov_residual_scale_floor
                        ),
                        matrix_free_global_krylov_preconditioner_mode=(
                            global_krylov_preconditioner_mode
                        ),
                        matrix_free_global_krylov_preconditioner_input_scale=(
                            float(preconditioner_input_scale)
                        ),
                        matrix_free_global_krylov_tangent_regularization_factor=float(factor),
                        matrix_free_global_krylov_allow_negative_alphas=True,
                        matrix_free_global_krylov_max_alpha=matrix_free_global_krylov_max_alpha,
                        matrix_free_global_krylov_alpha_values=(
                            matrix_free_global_krylov_alpha_values
                        ),
                        matrix_free_global_krylov_min_relative_improvement=(
                            matrix_free_global_krylov_min_relative_improvement
                        ),
                        matrix_free_global_krylov_full_assembly_trial_replay=(
                            matrix_free_global_krylov_full_assembly_trial_replay
                        ),
                        matrix_free_global_krylov_batch_replay_backend=(
                            global_krylov_batch_replay_backend
                        ),
                        matrix_free_global_krylov_require_hip_batch_replay=(
                            matrix_free_global_krylov_require_hip_batch_replay
                        ),
                        matrix_free_global_krylov_linear_solver_backend=(
                            global_krylov_linear_solver_backend
                        ),
                    )
                child_runtime_seconds = float(time.perf_counter() - child_started)
                krylov = child_payload.get("matrix_free_global_krylov")
                krylov = krylov if isinstance(krylov, dict) else {}
                best = _best_global_candidate(child_payload)
                component_flags = _accepted_component_flags(child_payload)
                base_residual = _get_direct_residual(child_payload, "base_direct_residual")
                final_residual = _get_direct_residual(child_payload, "final_direct_residual")
                final_improvement = (
                    base_residual - final_residual
                    if base_residual is not None and final_residual is not None
                    else None
                )
                final_relative_improvement = (
                    final_improvement / max(base_residual, 1.0e-30)
                    if final_improvement is not None and base_residual is not None
                    else None
                )
                child_gate = child_payload.get("gate_assessment")
                child_claim_boundary = child_payload.get("claim_boundary")
                child_blockers = child_payload.get("blockers")
                child_residual_contract = child_payload.get("residual_contract")
                child_hip_residual_engine_contract_passed = bool(
                    isinstance(child_residual_contract, dict)
                    and child_residual_contract.get(
                        "hip_residual_engine_contract_passed"
                    )
                    is True
                )
                child_strict_hip_promotion_blockers = (
                    _child_strict_hip_promotion_blockers(
                        require_hip_batch_replay=bool(
                            matrix_free_global_krylov_require_hip_batch_replay
                        ),
                        child_payload=child_payload,
                    )
                )
                child_promoted = bool(
                    final_relative_improvement is not None
                    and final_relative_improvement
                    >= matrix_free_global_krylov_min_relative_improvement
                    and any(component_flags.values())
                    and not child_strict_hip_promotion_blockers
                )
                row = {
                    "step_index": int(step_index + 1),
                    "tangent_regularization_factor": float(factor),
                    "preconditioner_input_scale": float(preconditioner_input_scale),
                    "child_receipt_path": str(child_json),
                    "child_checkpoint_path": str(child_checkpoint),
                    "status": child_payload.get("status"),
                    "child_gate_assessment": (
                        child_gate if isinstance(child_gate, dict) else None
                    ),
                    "child_claim_boundary": (
                        child_claim_boundary
                        if isinstance(child_claim_boundary, (dict, str))
                        else None
                    ),
                    "child_blockers": (
                        child_blockers if isinstance(child_blockers, list) else []
                    ),
                    "child_residual_contract": (
                        child_residual_contract
                        if isinstance(child_residual_contract, dict)
                        else None
                    ),
                    "child_hip_residual_engine_contract_passed": (
                        child_hip_residual_engine_contract_passed
                    ),
                    "child_strict_hip_promotion_blockers": (
                        child_strict_hip_promotion_blockers
                    ),
                    "accepted": child_promoted,
                    "stop_reason": krylov.get("stop_reason"),
                    "base_direct_residual_inf_n": base_residual,
                    "final_direct_residual_inf_n": final_residual,
                    "final_relative_improvement": final_relative_improvement,
                    "component_acceptance": component_flags,
                    "best_candidate_direct_residual_inf_n": best.get(
                        "direct_residual_inf_n"
                    ),
                    "best_candidate_relative_improvement": best.get(
                        "relative_improvement"
                    ),
                    "best_candidate_alpha": best.get("alpha"),
                    "best_candidate_alpha_source": best.get("alpha_source"),
                    "relative_increment_gate_passed": best.get(
                        "relative_increment_gate_passed"
                    ),
                    "residual_gate_passed": best.get("residual_gate_passed"),
                    "matvec_count": krylov.get("matvec_count"),
                    "difference_scheme": krylov.get("difference_scheme"),
                    "residual_only_matvec_count": krylov.get("residual_only_matvec_count"),
                    "full_assembly_matvec_count": krylov.get("full_assembly_matvec_count"),
                    "residual_only_trial_count": krylov.get("residual_only_trial_count"),
                    "full_assembly_trial_count": krylov.get("full_assembly_trial_count"),
                    "preconditioner_solve_count": krylov.get("preconditioner_solve_count"),
                    "preconditioner_regularization": krylov.get(
                        "preconditioner_regularization"
                    ),
                    "child_runtime_seconds": child_runtime_seconds,
                    "runtime_budget_seconds": runtime_budget_seconds,
                    "child_timeout_seconds": (
                        None
                        if effective_child_timeout_seconds is None
                        else float(effective_child_timeout_seconds)
                    ),
                    **child_subprocess_meta,
                }
                controller_rows.append(row)
                if bool(row.get("subprocess_timeout")):
                    runtime_budget_exceeded = True
                    stop_reason = "child_timeout_seconds_exceeded"
                if (
                    runtime_budget_seconds is not None
                    and time.perf_counter() - started >= runtime_budget_seconds
                ):
                    runtime_budget_exceeded = True
                if child_promoted:
                    promotion_count += 1
                    current_checkpoint = child_checkpoint
                    final_checkpoint = child_checkpoint
                    final_residual_inf_n = row["final_direct_residual_inf_n"]
                    step_promoted = True
                    break
                if runtime_budget_exceeded:
                    if stop_reason != "child_timeout_seconds_exceeded":
                        stop_reason = "runtime_budget_exceeded"
                    break
            if (
                runtime_budget_seconds is not None
                and time.perf_counter() - started >= runtime_budget_seconds
            ):
                runtime_budget_exceeded = True
                stop_reason = "runtime_budget_exceeded"
                break
            if step_promoted or runtime_budget_exceeded:
                break
        if runtime_budget_exceeded:
            if final_residual_inf_n is None and controller_rows:
                final_residual_inf_n = controller_rows[-1]["base_direct_residual_inf_n"]
            break
        if not step_promoted:
            stop_reason = "no_regularization_factor_promoted"
            final_residual_inf_n = controller_rows[-1]["base_direct_residual_inf_n"]
            break

    if output_final_checkpoint_npz is not None and final_checkpoint.is_file():
        output_final_checkpoint_npz.parent.mkdir(parents=True, exist_ok=True)
        if final_checkpoint.resolve() != output_final_checkpoint_npz.resolve():
            shutil.copyfile(final_checkpoint, output_final_checkpoint_npz)
        final_checkpoint = output_final_checkpoint_npz

    if not controller_rows and not runtime_budget_exceeded:
        stop_reason = "no_controller_steps_requested"

    promoted_rows = [row for row in controller_rows if bool(row.get("accepted"))]
    best_row = min(
        (
            row
            for row in controller_rows
            if row.get("best_candidate_direct_residual_inf_n") is not None
        ),
        key=lambda row: float(row["best_candidate_direct_residual_inf_n"]),
        default={},
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "partial",
        "adaptive_preconditioned_global_newton_ready": False,
        "hip_preflight": hip_preflight,
        "controller": {
            "enabled": True,
            "attempted": True,
            "promotion_count": int(promotion_count),
            "max_controller_steps": int(max_controller_steps),
            "stop_reason": stop_reason,
            "tangent_regularization_factors": [
                float(value) for value in tangent_regularization_factors
            ],
            "matrix_free_global_krylov_max_iterations": int(
                matrix_free_global_krylov_max_iterations
            ),
            "matrix_free_global_krylov_difference_scheme": (
                global_krylov_difference_scheme
            ),
            "matrix_free_global_krylov_alpha_values": [
                float(value) for value in matrix_free_global_krylov_alpha_values
            ],
            "matrix_free_global_krylov_preconditioner_input_scales": [
                float(value)
                for value in (
                    matrix_free_global_krylov_preconditioner_input_scales
                    or (1.0,)
                )
                if float(value) > 0.0
            ],
            "matrix_free_global_krylov_residual_scale_floor": float(
                matrix_free_global_krylov_residual_scale_floor
            ),
            "matrix_free_global_krylov_preconditioner_mode": str(
                global_krylov_preconditioner_mode
            ),
            "matrix_free_global_krylov_preconditioner_mode_disabled_reason": (
                preconditioner_mode_disabled_reason
            ),
            "matrix_free_global_krylov_max_alpha": float(
                matrix_free_global_krylov_max_alpha
            ),
            "matrix_free_global_krylov_full_assembly_trial_replay": bool(
                matrix_free_global_krylov_full_assembly_trial_replay
            ),
            "matrix_free_global_krylov_batch_replay_backend": str(
                global_krylov_batch_replay_backend
            ),
            "matrix_free_global_krylov_require_hip_batch_replay": bool(
                matrix_free_global_krylov_require_hip_batch_replay
            ),
            "hip_preflight": hip_preflight,
            "matrix_free_global_krylov_linear_solver_backend": str(
                global_krylov_linear_solver_backend
            ),
            "matrix_free_global_krylov_linear_solver_backend_auto_selected_reason": (
                linear_solver_backend_auto_selected_reason
            ),
            "minimum_relative_improvement": float(
                matrix_free_global_krylov_min_relative_improvement
            ),
            "secant_family_seed_enabled": bool(enable_secant_family_seed),
            "max_secant_family_promotions": int(max_secant_family_promotions),
            "secant_family_window_sizes": [
                int(value) for value in secant_family_window_sizes
            ],
            "secant_family_ridge_factors": [
                float(value) for value in secant_family_ridge_factors
            ],
            "secant_family_alpha_values": [
                float(value) for value in secant_family_alpha_values
            ],
            "secant_family_minimum_relative_improvement": float(
                secant_family_min_relative_improvement
            ),
            "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
            "apply_shell_material_tangent": bool(apply_shell_material_tangent),
            "allow_frozen_shell_material_tangent_hip_replay": bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "compact_output_final_checkpoint": bool(compact_output_final_checkpoint),
            "runtime_budget_seconds": runtime_budget_seconds,
            "runtime_budget_exceeded": bool(runtime_budget_exceeded),
            "child_timeout_seconds": (
                None if child_timeout_seconds is None else float(child_timeout_seconds)
            ),
        },
        "initial_checkpoint_path": str(initial_checkpoint),
        "final_checkpoint_path": str(final_checkpoint),
        "final_direct_residual_inf_n": final_residual_inf_n,
        "rows": controller_rows,
        "promoted_rows": promoted_rows,
        "best_candidate_row": best_row,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": _build_adaptive_global_claim_boundary(
            require_hip_batch_replay=bool(
                matrix_free_global_krylov_require_hip_batch_replay
            ),
            backend_is_hip=bool(
                global_krylov_batch_replay_backend
                != "cpu"
            ),
            hip_preflight_available=bool(
                hip_preflight and hip_preflight.get("hip_available")
            ),
            runtime_budget_exceeded=bool(runtime_budget_exceeded),
            promoted_rows=promoted_rows,
            rows=controller_rows,
        ),
    }
    if hip_preflight is not None:
        payload["hip_preflight"] = hip_preflight
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument(
        "--compact-output-final-checkpoint",
        action="store_true",
        help="Forward compact checkpoint writing to child direct-residual probes.",
    )
    parser.add_argument("--child-output-dir", type=Path, default=None)
    parser.add_argument(
        "--adaptive-tangent-regularization-factors",
        default="1e-6,3e-6",
    )
    parser.add_argument("--max-controller-steps", type=int, default=1)
    parser.add_argument("--matrix-free-global-krylov-max-iterations", type=int, default=3)
    parser.add_argument(
        "--matrix-free-global-krylov-difference-scheme",
        choices=("forward", "central"),
        default="forward",
        help=(
            "Finite-difference stencil forwarded to child global residual-JVP "
            "Krylov probes."
        ),
    )
    parser.add_argument("--matrix-free-global-krylov-probe-epsilon", type=float, default=1.0e-6)
    parser.add_argument("--matrix-free-global-krylov-probe-max-step", type=float, default=1.0e-5)
    parser.add_argument(
        "--matrix-free-global-krylov-residual-scale-floor",
        type=float,
        default=1.0,
        help=(
            "Minimum residual magnitude for D_r row scaling passed to each child "
            "global Krylov probe."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-alpha-values",
        default="8,4,2,1,0.5,0.25",
    )
    parser.add_argument(
        "--matrix-free-global-krylov-preconditioner-input-scales",
        default="1.0",
        help=(
            "Comma-separated force-like input scales applied before the "
            "current-tangent right preconditioner."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-preconditioner-mode",
        choices=("none", "current_tangent"),
        default="current_tangent",
        help=(
            "Right preconditioner forwarded to child global Krylov probes. "
            "Use none for HIP-required no-CPU-preconditioner runs."
        ),
    )
    parser.add_argument("--matrix-free-global-krylov-max-alpha", type=float, default=8.0)
    parser.add_argument(
        "--matrix-free-global-krylov-min-relative-improvement",
        type=float,
        default=1.0e-6,
    )
    parser.add_argument(
        "--disable-matrix-free-global-krylov-full-assembly-trial-replay",
        action="store_true",
        help=(
            "Do not ask child probes to replay global Krylov line-search candidates "
            "through full physical residual assembly before promotion."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-batch-replay-backend",
        choices=("cpu", "hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"),
        default="cpu",
        help=(
            "Residual replay backend forwarded to child global Krylov probes. "
            "HIP backends use the native full-residual batch engine."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-require-hip-batch-replay",
        action="store_true",
        help=(
            "Require child global Krylov residual replay to use a HIP backend and "
            "suppress CPU batch fallback."
        ),
    )
    parser.add_argument(
        "--matrix-free-global-krylov-linear-solver-backend",
        choices=("scipy_host_gmres", "torch_hip_gmres"),
        default="scipy_host_gmres",
        help=(
            "Linear Krylov backend forwarded to child global Krylov probes. "
            "torch_hip_gmres requires a ROCm torch HIP device and suppresses "
            "SciPy host-GMRES fallback."
        ),
    )
    parser.add_argument(
        "--enable-secant-family-seed",
        action="store_true",
        help=(
            "Run secant-family candidate generation before each global Krylov factor. "
            "The controller still promotes only direct-residual replay improvements."
        ),
    )
    parser.add_argument("--max-secant-family-promotions", type=int, default=1)
    parser.add_argument("--secant-family-window-sizes", default="4,8,16")
    parser.add_argument("--secant-family-ridge-factors", default="0,1e-8")
    parser.add_argument("--secant-family-alpha-values", default="1,0.5,0.25,0.125,0.0625")
    parser.add_argument("--secant-family-min-relative-improvement", type=float, default=1.0e-6)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only", "structural_components_only"),
        default="all_components",
    )
    parser.add_argument(
        "--apply-shell-material-tangent",
        action="store_true",
        help=(
            "Forward the shell-material tangent/residual mode to child direct-residual "
            "probes. Required when continuing shell-material G1 frontier checkpoints."
        ),
    )
    parser.add_argument(
        "--allow-frozen-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "Forward frozen shell-material tangent HIP replay to child probes. "
            "Frozen replay is NOT material Newton closure and does NOT satisfy "
            "strict G1 closure by itself."
        ),
    )
    parser.add_argument(
        "--allow-state-dependent-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "Forward candidate-state shell-material tangent HIP replay to child "
            "probes. Residual evaluation remains on HIP, but host shell operator "
            "refresh is not full production ROCm/HIP residency closure."
        ),
    )
    parser.add_argument("--residual-tolerance-n", type=float, default=5.0e-4)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument(
        "--max-controller-runtime-seconds",
        type=float,
        default=None,
        help=(
            "Optional controller runtime budget. The current in-process child "
            "probe is allowed to finish; the controller records its runtime and "
            "blocks any further child launches once the budget is exceeded."
        ),
    )
    parser.add_argument(
        "--child-timeout-seconds",
        type=float,
        default=None,
        help=(
            "Optional hard timeout for each child probe. When set, the controller "
            "launches child probes in a subprocess and writes a timeout receipt "
            "instead of waiting indefinitely."
        ),
    )
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help="Acknowledge this controller orchestrates CPU-diagnostic residual-JVP receipts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if (
        args.matrix_free_global_krylov_require_hip_batch_replay
        and args.matrix_free_global_krylov_batch_replay_backend == "cpu"
    ):
        print(
            "adaptive-preconditioned-global-newton: blocked "
            "--matrix-free-global-krylov-require-hip-batch-replay requires "
            "a HIP batch replay backend",
            file=sys.stderr,
        )
        return 2
    needs_cpu_ack = not (
        args.matrix_free_global_krylov_require_hip_batch_replay
        and args.matrix_free_global_krylov_batch_replay_backend != "cpu"
    )
    if needs_cpu_ack and not args.allow_cpu_diagnostic:
        print(
            "adaptive-preconditioned-global-newton: blocked cpu diagnostic requires "
            "--allow-cpu-diagnostic",
        )
        return 2
    payload = run_adaptive_preconditioned_global_newton(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        compact_output_final_checkpoint=args.compact_output_final_checkpoint,
        child_output_dir=args.child_output_dir,
        tangent_regularization_factors=_parse_float_csv(
            args.adaptive_tangent_regularization_factors
        ),
        max_controller_steps=args.max_controller_steps,
        matrix_free_global_krylov_max_iterations=args.matrix_free_global_krylov_max_iterations,
        matrix_free_global_krylov_difference_scheme=(
            args.matrix_free_global_krylov_difference_scheme
        ),
        matrix_free_global_krylov_probe_epsilon=args.matrix_free_global_krylov_probe_epsilon,
        matrix_free_global_krylov_probe_max_step=args.matrix_free_global_krylov_probe_max_step,
        matrix_free_global_krylov_residual_scale_floor=(
            args.matrix_free_global_krylov_residual_scale_floor
        ),
        matrix_free_global_krylov_preconditioner_mode=(
            args.matrix_free_global_krylov_preconditioner_mode
        ),
        matrix_free_global_krylov_alpha_values=_parse_float_csv(
            args.matrix_free_global_krylov_alpha_values
        ),
        matrix_free_global_krylov_preconditioner_input_scales=_parse_float_csv(
            args.matrix_free_global_krylov_preconditioner_input_scales
        ),
        matrix_free_global_krylov_max_alpha=args.matrix_free_global_krylov_max_alpha,
        matrix_free_global_krylov_min_relative_improvement=(
            args.matrix_free_global_krylov_min_relative_improvement
        ),
        matrix_free_global_krylov_full_assembly_trial_replay=(
            not args.disable_matrix_free_global_krylov_full_assembly_trial_replay
        ),
        matrix_free_global_krylov_batch_replay_backend=(
            args.matrix_free_global_krylov_batch_replay_backend
        ),
        matrix_free_global_krylov_require_hip_batch_replay=(
            args.matrix_free_global_krylov_require_hip_batch_replay
        ),
        matrix_free_global_krylov_linear_solver_backend=(
            args.matrix_free_global_krylov_linear_solver_backend
        ),
        enable_secant_family_seed=args.enable_secant_family_seed,
        max_secant_family_promotions=args.max_secant_family_promotions,
        secant_family_window_sizes=tuple(
            int(value.strip())
            for value in str(args.secant_family_window_sizes).split(",")
            if value.strip()
        ),
        secant_family_ridge_factors=_parse_float_csv(args.secant_family_ridge_factors),
        secant_family_alpha_values=_parse_float_csv(args.secant_family_alpha_values),
        secant_family_min_relative_improvement=args.secant_family_min_relative_improvement,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        apply_shell_material_tangent=args.apply_shell_material_tangent,
        allow_frozen_shell_material_tangent_hip_replay=(
            args.allow_frozen_shell_material_tangent_hip_replay
        ),
        allow_state_dependent_shell_material_tangent_hip_replay=(
            args.allow_state_dependent_shell_material_tangent_hip_replay
        ),
        residual_tolerance_n=args.residual_tolerance_n,
        relative_increment_tolerance=args.relative_increment_tolerance,
        max_controller_runtime_seconds=args.max_controller_runtime_seconds,
        child_timeout_seconds=args.child_timeout_seconds,
    )
    controller = payload["controller"]
    print(
        "adaptive-preconditioned-global-newton: "
        f"status={payload['status']} promotions={controller['promotion_count']} "
        f"stop={controller['stop_reason']} final={payload['final_direct_residual_inf_n']} "
        f"-> {args.output_json or PRODUCTIZATION / 'mgt_direct_residual_adaptive_preconditioned_global_newton_smoke.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
