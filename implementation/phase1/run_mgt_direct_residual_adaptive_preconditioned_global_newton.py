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


def _csv(values: tuple[float, ...] | tuple[int, ...]) -> str:
    return ",".join(str(value) for value in values)


def _child_launch_receipt(
    *,
    child_json: Path,
    child_checkpoint: Path,
    checkpoint_npz: Path,
    tangent_regularization_factor: float,
    preconditioner_input_scale: float,
    child_timeout_seconds: float | None,
    command: list[str],
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
        "child_timeout_seconds": (
            None if child_timeout_seconds is None else float(child_timeout_seconds)
        ),
        "command": command,
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
    factor: float,
    preconditioner_input_scale: float,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
    matrix_free_global_krylov_max_iterations: int,
    matrix_free_global_krylov_probe_epsilon: float,
    matrix_free_global_krylov_probe_max_step: float,
    matrix_free_global_krylov_alpha_values: tuple[float, ...],
    matrix_free_global_krylov_max_alpha: float,
    matrix_free_global_krylov_min_relative_improvement: float,
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
        "--matrix-free-global-krylov-probe-epsilon",
        str(float(matrix_free_global_krylov_probe_epsilon)),
        "--matrix-free-global-krylov-probe-max-step",
        str(float(matrix_free_global_krylov_probe_max_step)),
        "--matrix-free-global-krylov-scaling-mode",
        "residual_diagonal_displacement",
        "--matrix-free-global-krylov-preconditioner-mode",
        "current_tangent",
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
        "--allow-cpu-diagnostic",
    ]
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
            child_timeout_seconds=child_timeout_seconds,
            command=cmd,
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
    child_output_dir: Path | None = None,
    tangent_regularization_factors: tuple[float, ...] = (1.0e-6, 3.0e-6),
    max_controller_steps: int = 1,
    matrix_free_global_krylov_max_iterations: int = 3,
    matrix_free_global_krylov_probe_epsilon: float = 1.0e-6,
    matrix_free_global_krylov_probe_max_step: float = 1.0e-5,
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
                if child_timeout_seconds is not None and float(child_timeout_seconds) > 0.0:
                    child_payload, child_subprocess_meta = _run_child_subprocess(
                        mgt_path=mgt_path,
                        checkpoint_npz=current_checkpoint,
                        child_json=child_json,
                        child_checkpoint=child_checkpoint,
                        factor=float(factor),
                        preconditioner_input_scale=float(preconditioner_input_scale),
                        residual_tolerance_n=residual_tolerance_n,
                        relative_increment_tolerance=relative_increment_tolerance,
                        matrix_free_global_krylov_max_iterations=(
                            matrix_free_global_krylov_max_iterations
                        ),
                        matrix_free_global_krylov_probe_epsilon=(
                            matrix_free_global_krylov_probe_epsilon
                        ),
                        matrix_free_global_krylov_probe_max_step=(
                            matrix_free_global_krylov_probe_max_step
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
                        enable_secant_family_seed=bool(enable_secant_family_seed),
                        max_secant_family_promotions=max_secant_family_promotions,
                        secant_family_window_sizes=secant_family_window_sizes,
                        secant_family_ridge_factors=secant_family_ridge_factors,
                        secant_family_alpha_values=secant_family_alpha_values,
                        secant_family_min_relative_improvement=(
                            secant_family_min_relative_improvement
                        ),
                        child_timeout_seconds=float(child_timeout_seconds),
                    )
                else:
                    child_payload = run_mgt_direct_residual_newton_probe(
                        mgt_path=mgt_path,
                        checkpoint_npz=current_checkpoint,
                        output_json=child_json,
                        output_final_checkpoint_npz=child_checkpoint,
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
                        matrix_free_global_krylov_probe_epsilon=(
                            matrix_free_global_krylov_probe_epsilon
                        ),
                        matrix_free_global_krylov_probe_max_step=(
                            matrix_free_global_krylov_probe_max_step
                        ),
                        matrix_free_global_krylov_scaling_mode="residual_diagonal_displacement",
                        matrix_free_global_krylov_preconditioner_mode="current_tangent",
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
                child_promoted = bool(
                    final_relative_improvement is not None
                    and final_relative_improvement
                    >= matrix_free_global_krylov_min_relative_improvement
                    and any(component_flags.values())
                )
                row = {
                    "step_index": int(step_index + 1),
                    "tangent_regularization_factor": float(factor),
                    "preconditioner_input_scale": float(preconditioner_input_scale),
                    "child_receipt_path": str(child_json),
                    "child_checkpoint_path": str(child_checkpoint),
                    "status": child_payload.get("status"),
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
                        if child_timeout_seconds is None
                        else float(child_timeout_seconds)
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
            "matrix_free_global_krylov_max_alpha": float(
                matrix_free_global_krylov_max_alpha
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
        "claim_boundary": {
            "cpu_diagnostic_only": True,
            "official_rocm_hip_closure_required": True,
            "residual_replay_is_regularization_free": True,
            "regularization_used_only_for_preconditioner_direction": True,
            "ai_residual_correction_is_candidate_generation_only": True,
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument("--child-output-dir", type=Path, default=None)
    parser.add_argument(
        "--adaptive-tangent-regularization-factors",
        default="1e-6,3e-6",
    )
    parser.add_argument("--max-controller-steps", type=int, default=1)
    parser.add_argument("--matrix-free-global-krylov-max-iterations", type=int, default=3)
    parser.add_argument("--matrix-free-global-krylov-probe-epsilon", type=float, default=1.0e-6)
    parser.add_argument("--matrix-free-global-krylov-probe-max-step", type=float, default=1.0e-5)
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
    parser.add_argument("--matrix-free-global-krylov-max-alpha", type=float, default=8.0)
    parser.add_argument(
        "--matrix-free-global-krylov-min-relative-improvement",
        type=float,
        default=1.0e-6,
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
    if not args.allow_cpu_diagnostic:
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
        child_output_dir=args.child_output_dir,
        tangent_regularization_factors=_parse_float_csv(
            args.adaptive_tangent_regularization_factors
        ),
        max_controller_steps=args.max_controller_steps,
        matrix_free_global_krylov_max_iterations=args.matrix_free_global_krylov_max_iterations,
        matrix_free_global_krylov_probe_epsilon=args.matrix_free_global_krylov_probe_epsilon,
        matrix_free_global_krylov_probe_max_step=args.matrix_free_global_krylov_probe_max_step,
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
