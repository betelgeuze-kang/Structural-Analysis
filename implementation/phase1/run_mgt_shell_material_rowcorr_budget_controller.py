#!/usr/bin/env python3
"""Budgeted controller for shell-material direct-residual row correction."""

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
)


SCHEMA_VERSION = "mgt-shell-material-rowcorr-budget-controller.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_PROBE = (
    PRODUCTIZATION / "mgt_direct_residual_shell_material_tangent_rowcorr_min_followup380_probe.json"
)
DEFAULT_OUTPUT = PRODUCTIZATION / "mgt_shell_material_rowcorr_budget_controller.json"
DEFAULT_SHELL_MATERIAL_CHECKPOINT = (
    PRODUCTIZATION
    / "mgt_equilibrium_newton_focused_followup365_attached_regularized_direct_final_checkpoint.npz"
)


def _parse_int_csv(text: str) -> tuple[int, ...]:
    return tuple(int(value.strip()) for value in str(text).split(",") if value.strip())


def _parse_float_csv(text: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(text).split(",") if value.strip())


def _csv(values: tuple[int, ...] | tuple[float, ...]) -> str:
    return ",".join(str(value) for value in values)


def _child_strict_hip_promotion_blockers(
    *,
    require_hip: bool,
    child_payload: dict[str, Any],
) -> list[str]:
    if not require_hip:
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


def _row_reports_hip_runtime_unavailable(row: dict[str, Any]) -> bool:
    child_blockers = row.get("child_blockers")
    if isinstance(child_blockers, list) and any(
        str(blocker) == "rocm_hip_runtime_unavailable" for blocker in child_blockers
    ):
        return True
    residual_contract = row.get("child_residual_contract")
    if isinstance(residual_contract, dict):
        engine_blockers = residual_contract.get("hip_residual_engine_blockers")
        if isinstance(engine_blockers, list) and any(
            str(blocker) == "rocm_hip_runtime_unavailable"
            for blocker in engine_blockers
        ):
            return True
    gate = row.get("child_gate_assessment")
    return isinstance(gate, dict) and gate.get("rocm_hip_runtime_available") is False


def _build_shell_rowcorr_claim_boundary(
    *,
    require_hip: bool,
    backend_is_hip: bool,
    preflight_blockers_exist: bool,
    runtime_budget_exceeded: bool,
    promoted_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    child_hip_runtime_unavailable = any(
        _row_reports_hip_runtime_unavailable(row) for row in [*rows, *promoted_rows]
    )
    hip_backend_available = bool(
        require_hip
        and backend_is_hip
        and not preflight_blockers_exist
        and not child_hip_runtime_unavailable
    )
    conservative = {
        "cpu_diagnostic_only": True,
        "official_rocm_hip_closure_required": True,
        "shell_material_tangent_required": True,
        "child_receipts_are_source_of_residual_progress": True,
        "timeouts_do_not_claim_descent": True,
        "hip_required_material_tangent_backend_available": hip_backend_available,
        "rocm_hip_runtime_available": hip_backend_available,
    }
    if not require_hip:
        return conservative
    if not backend_is_hip:
        return conservative
    if preflight_blockers_exist:
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
        "shell_material_tangent_required": True,
        "child_receipts_are_source_of_residual_progress": True,
        "timeouts_do_not_claim_descent": True,
        "hip_required_material_tangent_backend_available": True,
        "rocm_hip_runtime_available": True,
        "host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency": (
            host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _direct_residual(payload: dict[str, Any], field: str) -> float | None:
    group = payload.get(field)
    if not isinstance(group, dict):
        return None
    value = group.get("direct_residual_inf_n")
    return float(value) if value is not None else None


def _rowcorr_group(payload: dict[str, Any]) -> dict[str, Any]:
    group = payload.get("current_tangent_residual_row_correction")
    return group if isinstance(group, dict) else {}


def _checkpoint_from_seed(payload: dict[str, Any]) -> Path | None:
    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        return None
    path = checkpoint.get("path")
    if not path:
        return None
    return Path(str(path))


def _probe_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    base = _direct_residual(payload, "base_direct_residual")
    final = _direct_residual(payload, "final_direct_residual")
    if base is None:
        base = (
            float(payload["initial_frontier_direct_residual_inf_n"])
            if payload.get("initial_frontier_direct_residual_inf_n") is not None
            else None
        )
    if final is None:
        final = (
            float(payload["final_direct_residual_inf_n"])
            if payload.get("final_direct_residual_inf_n") is not None
            else None
        )
    improvement = base - final if base is not None and final is not None else None
    relative = (
        improvement / max(base, 1.0e-30)
        if improvement is not None and base is not None
        else None
    )
    rowcorr = _rowcorr_group(payload)
    return {
        "path": str(path),
        "available": bool(payload),
        "status": payload.get("status"),
        "base_direct_residual_inf_n": base,
        "final_direct_residual_inf_n": final,
        "direct_residual_improvement_inf_n": improvement,
        "direct_residual_relative_improvement": relative,
        "row_correction_accepted": bool(rowcorr.get("accepted")),
        "row_correction_promotion_count": int(rowcorr.get("promotion_count") or 0),
        "row_correction_stop_reason": rowcorr.get("stop_reason"),
        "residual_gate_passed": (
            bool(payload.get("final_direct_residual", {}).get("residual_gate_passed"))
            if isinstance(payload.get("final_direct_residual"), dict)
            else None
        ),
    }


def _build_child_command(
    *,
    python_exe: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
    child_json: Path,
    child_checkpoint: Path | None,
    compact_child_checkpoint: bool,
    shell_pressure_load_path_policy: str,
    row_target_mode: str,
    row_frontier_probe_json: Path | None,
    row_frontier_component_scale_mode: str,
    target_row_count: int,
    support_column_count: int,
    alpha_values: tuple[float, ...],
    row_jacobian_mode: str,
    row_fd_epsilon: float,
    row_fd_max_support_columns: int,
    row_batch_fd_replay: bool,
    row_batch_fd_replay_chunk_size: int,
    row_batch_replay_backend: str,
    row_require_hip_batch_replay: bool,
    allow_frozen_shell_material_tangent_hip_replay: bool,
    allow_state_dependent_shell_material_tangent_hip_replay: bool,
    row_use_residual_only_assembly: bool,
    row_batch_alpha_replay: bool,
    max_row_promotions: int,
    row_min_relative_improvement: float,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
    row_support_selection: str = "row_strongest",
) -> list[str]:
    script = Path(__file__).resolve().with_name("run_mgt_direct_residual_newton_probe.py")
    command = [
        str(python_exe),
        str(script),
        "--mgt-path",
        str(mgt_path),
        "--checkpoint-npz",
        str(checkpoint_npz),
        "--output-json",
        str(child_json),
        "--shell-pressure-load-path-policy",
        str(shell_pressure_load_path_policy),
        "--residual-tolerance-n",
        str(float(residual_tolerance_n)),
        "--relative-increment-tolerance",
        str(float(relative_increment_tolerance)),
        "--apply-shell-material-tangent",
        "--max-trust-iterations",
        "0",
        "--disable-secant-subspace-globalization",
        "--disable-matrix-free-jacobian-subspace",
        "--enable-current-tangent-residual-row-correction",
        "--max-current-tangent-residual-row-corrections",
        str(int(max_row_promotions)),
        "--current-tangent-residual-row-target-mode",
        str(row_target_mode),
        "--current-tangent-residual-row-target-counts",
        str(int(target_row_count)),
        "--current-tangent-residual-row-support-column-counts",
        str(int(support_column_count)),
        "--current-tangent-residual-row-frontier-component-scale-mode",
        str(row_frontier_component_scale_mode),
        "--current-tangent-residual-row-jacobian-mode",
        str(row_jacobian_mode),
        "--current-tangent-residual-row-fd-epsilon",
        str(float(row_fd_epsilon)),
        "--current-tangent-residual-row-fd-max-support-columns",
        str(int(row_fd_max_support_columns)),
        "--current-tangent-residual-row-alpha-values",
        _csv(alpha_values),
        "--current-tangent-residual-row-min-relative-improvement",
        str(float(row_min_relative_improvement)),
        "--current-tangent-residual-row-support-selection",
        str(row_support_selection),
    ]
    if not row_require_hip_batch_replay:
        command.append("--allow-cpu-diagnostic")
    if row_frontier_probe_json is not None:
        command.extend(
            [
                "--current-tangent-residual-row-frontier-probe-json",
                str(row_frontier_probe_json),
            ]
        )
    if row_batch_fd_replay:
        command.extend(
            [
                "--current-tangent-residual-row-batch-fd-replay",
                "--current-tangent-residual-row-batch-fd-replay-chunk-size",
                str(int(row_batch_fd_replay_chunk_size)),
            ]
        )
    if row_batch_replay_backend != "cpu":
        command.extend(
            [
                "--current-tangent-residual-row-batch-replay-backend",
                str(row_batch_replay_backend),
            ]
        )
    if row_require_hip_batch_replay:
        command.append("--current-tangent-residual-row-require-hip-batch-replay")
    if (
        allow_frozen_shell_material_tangent_hip_replay
        and not allow_state_dependent_shell_material_tangent_hip_replay
    ):
        command.append("--allow-frozen-shell-material-tangent-hip-replay")
    if allow_state_dependent_shell_material_tangent_hip_replay:
        command.append("--allow-state-dependent-shell-material-tangent-hip-replay")
    if row_use_residual_only_assembly:
        command.append("--current-tangent-residual-row-use-residual-only-assembly")
    if row_batch_alpha_replay:
        command.append("--current-tangent-residual-row-batch-alpha-replay")
    if child_checkpoint is not None:
        insertion = command.index("--shell-pressure-load-path-policy")
        command[insertion:insertion] = [
            "--output-final-checkpoint-npz",
            str(child_checkpoint),
        ]
        if compact_child_checkpoint:
            command[insertion + 2 : insertion + 2] = [
                "--compact-output-final-checkpoint",
            ]
    return command


def _launch_receipt(
    *,
    child_json: Path,
    child_checkpoint: Path | None,
    checkpoint_npz: Path,
    row_target_mode: str,
    row_jacobian_mode: str,
    target_row_count: int,
    support_column_count: int,
    alpha_values: tuple[float, ...],
    child_timeout_seconds: float,
    command: list[str],
    row_support_selection: str = "row_strongest",
) -> dict[str, Any]:
    return {
        "schema_version": "mgt-shell-material-rowcorr-child-launch.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
        "checkpoint": str(checkpoint_npz),
        "output_json": str(child_json),
        "output_final_checkpoint_npz": (
            None if child_checkpoint is None else str(child_checkpoint)
        ),
        "row_target_mode": str(row_target_mode),
        "row_jacobian_mode": str(row_jacobian_mode),
        "row_support_selection": str(row_support_selection),
        "target_row_count": int(target_row_count),
        "support_column_count": int(support_column_count),
        "alpha_values": [float(value) for value in alpha_values],
        "child_timeout_seconds": float(child_timeout_seconds),
        "command": command,
        "claim_boundary": (
            "Launch receipt only. A completed child direct-residual receipt is required "
            "before claiming residual progress."
        ),
    }


def _timeout_receipt(
    *,
    child_json: Path,
    child_checkpoint: Path | None,
    checkpoint_npz: Path,
    command: list[str],
    timeout: subprocess.TimeoutExpired,
    child_timeout_seconds: float,
) -> dict[str, Any]:
    payload = {
        "schema_version": "mgt-shell-material-rowcorr-child-timeout.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "timeout",
        "checkpoint": str(checkpoint_npz),
        "output_json": str(child_json),
        "output_final_checkpoint_npz": (
            None if child_checkpoint is None else str(child_checkpoint)
        ),
        "current_tangent_residual_row_correction": {
            "enabled": True,
            "attempted": True,
            "accepted": False,
            "stop_reason": "child_timeout_seconds_exceeded",
        },
        "child_timeout_seconds": float(child_timeout_seconds),
        "command": command,
        "stdout": timeout.stdout or "",
        "stderr": timeout.stderr or "",
        "output_final_checkpoint_written": False,
        "claim_boundary": (
            "Timeout receipt only. No residual descent is claimed because the child "
            "probe did not finish and no final checkpoint was written."
        ),
    }
    _write_json(child_json, payload)
    return payload


def _run_child(
    *,
    python_exe: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
    child_json: Path,
    child_checkpoint: Path | None,
    shell_pressure_load_path_policy: str,
    row_target_mode: str,
    row_frontier_probe_json: Path | None,
    row_frontier_component_scale_mode: str,
    target_row_count: int,
    support_column_count: int,
    alpha_values: tuple[float, ...],
    row_jacobian_mode: str,
    row_fd_epsilon: float,
    row_fd_max_support_columns: int,
    row_batch_fd_replay: bool,
    row_batch_fd_replay_chunk_size: int,
    row_batch_replay_backend: str,
    row_require_hip_batch_replay: bool,
    allow_frozen_shell_material_tangent_hip_replay: bool,
    allow_state_dependent_shell_material_tangent_hip_replay: bool,
    row_use_residual_only_assembly: bool,
    row_batch_alpha_replay: bool,
    max_row_promotions: int,
    compact_child_checkpoint: bool,
    row_min_relative_improvement: float,
    residual_tolerance_n: float,
    relative_increment_tolerance: float,
    child_timeout_seconds: float,
    row_support_selection: str = "row_strongest",
) -> tuple[dict[str, Any], dict[str, Any]]:
    command = _build_child_command(
        python_exe=python_exe,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        child_json=child_json,
        child_checkpoint=child_checkpoint,
        compact_child_checkpoint=compact_child_checkpoint,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
        row_target_mode=row_target_mode,
        row_frontier_probe_json=row_frontier_probe_json,
        row_frontier_component_scale_mode=row_frontier_component_scale_mode,
        target_row_count=target_row_count,
        support_column_count=support_column_count,
        alpha_values=alpha_values,
        row_jacobian_mode=row_jacobian_mode,
        row_fd_epsilon=row_fd_epsilon,
        row_fd_max_support_columns=row_fd_max_support_columns,
        row_batch_fd_replay=row_batch_fd_replay,
        row_batch_fd_replay_chunk_size=row_batch_fd_replay_chunk_size,
        row_batch_replay_backend=row_batch_replay_backend,
        row_require_hip_batch_replay=row_require_hip_batch_replay,
        allow_frozen_shell_material_tangent_hip_replay=(
            allow_frozen_shell_material_tangent_hip_replay
        ),
        allow_state_dependent_shell_material_tangent_hip_replay=(
            allow_state_dependent_shell_material_tangent_hip_replay
        ),
        row_use_residual_only_assembly=row_use_residual_only_assembly,
        row_batch_alpha_replay=row_batch_alpha_replay,
        max_row_promotions=max_row_promotions,
        row_min_relative_improvement=row_min_relative_improvement,
        residual_tolerance_n=residual_tolerance_n,
        relative_increment_tolerance=relative_increment_tolerance,
        row_support_selection=row_support_selection,
    )
    _write_json(
        child_json,
        _launch_receipt(
            child_json=child_json,
            child_checkpoint=child_checkpoint,
            checkpoint_npz=checkpoint_npz,
            row_target_mode=row_target_mode,
            row_jacobian_mode=row_jacobian_mode,
            target_row_count=target_row_count,
            support_column_count=support_column_count,
            alpha_values=alpha_values,
            child_timeout_seconds=child_timeout_seconds,
            command=command,
            row_support_selection=row_support_selection,
        ),
    )
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(child_timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        payload = _timeout_receipt(
            child_json=child_json,
            child_checkpoint=child_checkpoint,
            checkpoint_npz=checkpoint_npz,
            command=command,
            timeout=exc,
            child_timeout_seconds=child_timeout_seconds,
        )
        return payload, {
            "subprocess_returncode": None,
            "subprocess_timeout": True,
            "subprocess_stdout": exc.stdout or "",
            "subprocess_stderr": exc.stderr or "",
            "subprocess_command": command,
        }

    child_payload = _read_json(child_json)
    if not child_payload:
        child_payload = {
            "schema_version": "mgt-shell-material-rowcorr-child-missing-output.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "current_tangent_residual_row_correction": {
                "enabled": True,
                "attempted": True,
                "accepted": False,
                "stop_reason": "child_output_json_missing",
            },
            "command": command,
        }
        _write_json(child_json, child_payload)

    return child_payload, {
        "subprocess_returncode": int(completed.returncode),
        "subprocess_timeout": False,
        "subprocess_stdout": completed.stdout,
        "subprocess_stderr": completed.stderr,
        "subprocess_command": command,
    }


def run_shell_material_rowcorr_budget_controller(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_SHELL_MATERIAL_CHECKPOINT,
    seed_probe_json: Path = DEFAULT_SEED_PROBE,
    output_json: Path = DEFAULT_OUTPUT,
    output_final_checkpoint_npz: Path | None = None,
    child_output_dir: Path | None = None,
    python_exe: Path | None = None,
    row_target_counts: tuple[int, ...] = (1,),
    row_support_column_counts: tuple[int, ...] = (4,),
    row_alpha_values: tuple[float, ...] = (0.015625,),
    row_target_mode: str = "largest_rows",
    row_frontier_probe_json: Path | None = None,
    row_frontier_component_scale_mode: str = "none",
    row_jacobian_mode: str = "current_tangent",
    row_fd_epsilon: float = 1.0e-6,
    row_fd_max_support_columns: int = 12,
    row_batch_fd_replay: bool = False,
    row_batch_fd_replay_chunk_size: int = 64,
    row_batch_replay_backend: str = "cpu",
    row_require_hip_batch_replay: bool = False,
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
    row_use_residual_only_assembly: bool = False,
    row_batch_alpha_replay: bool = False,
    max_candidates: int = 1,
    max_row_promotions: int = 1,
    write_child_checkpoints: bool = False,
    compact_child_checkpoints: bool = True,
    row_min_relative_improvement: float = 0.0,
    controller_min_relative_improvement: float = 1.0e-7,
    shell_pressure_load_path_policy: str = "structural_components_only",
    residual_tolerance_n: float = 5.0e-4,
    relative_increment_tolerance: float = 1.0e-4,
    max_controller_runtime_seconds: float | None = None,
    child_timeout_seconds: float = 120.0,
    row_support_selection: str = "row_strongest",
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    runtime_budget_seconds = (
        float(max_controller_runtime_seconds)
        if max_controller_runtime_seconds is not None
        else None
    )
    child_output_dir = child_output_dir or output_json.parent / f"{output_json.stem}_children"
    child_output_dir.mkdir(parents=True, exist_ok=True)
    python_exe = python_exe or Path(sys.executable)

    row_batch_replay_backend = str(row_batch_replay_backend).strip().lower()
    row_support_selection = str(row_support_selection).strip().lower()
    if row_support_selection not in {
        "row_strongest",
        "residual_weighted",
        "target_rows",
    }:
        row_support_selection = "row_strongest"
    if row_require_hip_batch_replay and row_batch_replay_backend == "cpu":
        raise ValueError(
            "row_require_hip_batch_replay=True requires a HIP row batch replay backend, "
            f"got row_batch_replay_backend={row_batch_replay_backend!r}"
        )

    seed_payload = _read_json(seed_probe_json)
    if Path(checkpoint_npz) == DEFAULT_CHECKPOINT:
        checkpoint_npz = _checkpoint_from_seed(seed_payload) or DEFAULT_SHELL_MATERIAL_CHECKPOINT
    seed_summary = _probe_summary(seed_probe_json, seed_payload)
    seed_frontier = seed_summary.get("final_direct_residual_inf_n")
    current_frontier = float(seed_frontier) if seed_frontier is not None else None
    final_residual = current_frontier
    final_checkpoint = Path(checkpoint_npz)
    rows: list[dict[str, Any]] = []
    promoted_rows: list[dict[str, Any]] = []
    runtime_budget_exceeded = False
    promotion_count = 0
    stop_reason = "max_candidates_reached"
    preflight_blockers: list[str] = []
    if (
        row_require_hip_batch_replay
        and not allow_frozen_shell_material_tangent_hip_replay
        and not allow_state_dependent_shell_material_tangent_hip_replay
    ):
        preflight_blockers.append(
            "hip_required_shell_material_tangent_batch_backend_unavailable"
        )
        stop_reason = "hip_required_shell_material_tangent_backend_unavailable"

    candidates: list[tuple[int, int]] = []
    for target_count in row_target_counts or (1,):
        for support_count in row_support_column_counts or (4,):
            candidates.append((int(target_count), int(support_count)))
    if max_candidates >= 0:
        candidates = candidates[: max(int(max_candidates), 0)]

    if runtime_budget_seconds is not None and time.perf_counter() - started >= runtime_budget_seconds:
        runtime_budget_exceeded = True
        stop_reason = "runtime_budget_exceeded"

    for candidate_index, (target_count, support_count) in enumerate(
        [] if preflight_blockers else candidates,
        start=1,
    ):
        if runtime_budget_seconds is not None and time.perf_counter() - started >= runtime_budget_seconds:
            runtime_budget_exceeded = True
            stop_reason = "runtime_budget_exceeded"
            break
        remaining_budget = (
            None
            if runtime_budget_seconds is None
            else max(runtime_budget_seconds - (time.perf_counter() - started), 0.0)
        )
        effective_timeout = float(child_timeout_seconds)
        if remaining_budget is not None:
            if remaining_budget <= 0.0:
                runtime_budget_exceeded = True
                stop_reason = "runtime_budget_exceeded"
                break
            effective_timeout = min(effective_timeout, remaining_budget)
        if effective_timeout <= 0.0:
            runtime_budget_exceeded = True
            stop_reason = "runtime_budget_exceeded"
            break

        label = f"candidate{candidate_index}_target{target_count}_support{support_count}"
        child_json = child_output_dir / f"{output_json.stem}_{label}.json"
        child_checkpoint = (
            child_output_dir / f"{output_json.stem}_{label}_final_checkpoint.npz"
            if write_child_checkpoints
            else None
        )
        child_started = time.perf_counter()
        child_payload, subprocess_meta = _run_child(
            python_exe=python_exe,
            mgt_path=mgt_path,
            checkpoint_npz=checkpoint_npz,
            child_json=child_json,
            child_checkpoint=child_checkpoint,
            shell_pressure_load_path_policy=shell_pressure_load_path_policy,
            row_target_mode=row_target_mode,
            row_frontier_probe_json=row_frontier_probe_json,
            row_frontier_component_scale_mode=row_frontier_component_scale_mode,
            target_row_count=target_count,
            support_column_count=support_count,
            alpha_values=row_alpha_values,
            row_jacobian_mode=row_jacobian_mode,
            row_fd_epsilon=row_fd_epsilon,
            row_fd_max_support_columns=row_fd_max_support_columns,
            row_batch_fd_replay=row_batch_fd_replay,
            row_batch_fd_replay_chunk_size=row_batch_fd_replay_chunk_size,
            row_batch_replay_backend=row_batch_replay_backend,
            row_require_hip_batch_replay=row_require_hip_batch_replay,
            allow_frozen_shell_material_tangent_hip_replay=(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            allow_state_dependent_shell_material_tangent_hip_replay=(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            row_use_residual_only_assembly=row_use_residual_only_assembly,
            row_batch_alpha_replay=row_batch_alpha_replay,
            max_row_promotions=max_row_promotions,
            compact_child_checkpoint=compact_child_checkpoints,
            row_min_relative_improvement=row_min_relative_improvement,
            residual_tolerance_n=residual_tolerance_n,
            relative_increment_tolerance=relative_increment_tolerance,
            child_timeout_seconds=effective_timeout,
            row_support_selection=row_support_selection,
        )
        child_runtime_seconds = float(time.perf_counter() - child_started)
        child_summary = _probe_summary(child_json, child_payload)
        child_final = child_summary.get("final_direct_residual_inf_n")
        child_final_value = float(child_final) if child_final is not None else None
        frontier_improvement = (
            current_frontier - child_final_value
            if current_frontier is not None and child_final_value is not None
            else None
        )
        frontier_relative_improvement = (
            frontier_improvement / max(current_frontier, 1.0e-30)
            if frontier_improvement is not None and current_frontier is not None
            else None
        )
        child_gate = child_payload.get("gate_assessment")
        child_claim_boundary = child_payload.get("claim_boundary")
        child_blockers = child_payload.get("blockers")
        child_residual_contract = child_payload.get("residual_contract")
        child_hip_residual_engine_contract_passed = bool(
            isinstance(child_residual_contract, dict)
            and child_residual_contract.get("hip_residual_engine_contract_passed")
            is True
        )
        child_strict_hip_promotion_blockers = _child_strict_hip_promotion_blockers(
            require_hip=bool(row_require_hip_batch_replay),
            child_payload=child_payload,
        )
        rowcorr_accepted = bool(child_summary.get("row_correction_accepted"))
        accepted = bool(
            rowcorr_accepted
            and child_final_value is not None
            and not child_strict_hip_promotion_blockers
            and (
                current_frontier is None
                or (
                    frontier_improvement is not None
                    and frontier_relative_improvement is not None
                    and frontier_improvement > 0.0
                    and frontier_relative_improvement
                    >= max(float(controller_min_relative_improvement), 0.0)
                )
            )
        )
        row = {
            "candidate_index": int(candidate_index),
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
            "child_strict_hip_promotion_blockers": child_strict_hip_promotion_blockers,
            "target_row_count": int(target_count),
            "support_column_count": int(support_count),
            "alpha_values": [float(value) for value in row_alpha_values],
            "row_target_mode": str(row_target_mode),
            "row_support_selection": str(row_support_selection),
            "row_frontier_probe_json": (
                None if row_frontier_probe_json is None else str(row_frontier_probe_json)
            ),
            "row_frontier_component_scale_mode": str(
                row_frontier_component_scale_mode
            ),
            "row_jacobian_mode": str(row_jacobian_mode),
            "row_fd_epsilon": float(row_fd_epsilon),
            "row_fd_max_support_columns": int(row_fd_max_support_columns),
            "row_batch_fd_replay": bool(row_batch_fd_replay),
            "row_batch_fd_replay_chunk_size": int(row_batch_fd_replay_chunk_size),
            "row_batch_replay_backend": str(row_batch_replay_backend),
            "row_require_hip_batch_replay": bool(row_require_hip_batch_replay),
            "allow_frozen_shell_material_tangent_hip_replay": bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "row_use_residual_only_assembly": bool(row_use_residual_only_assembly),
            "row_batch_alpha_replay": bool(row_batch_alpha_replay),
            "child_receipt_path": str(child_json),
            "child_checkpoint_path": (
                None if child_checkpoint is None else str(child_checkpoint)
            ),
            "status": child_summary.get("status"),
            "accepted": accepted,
            "row_correction_accepted": rowcorr_accepted,
            "row_correction_promotion_count": child_summary.get(
                "row_correction_promotion_count"
            ),
            "row_correction_stop_reason": child_summary.get("row_correction_stop_reason"),
            "base_direct_residual_inf_n": child_summary.get("base_direct_residual_inf_n"),
            "final_direct_residual_inf_n": child_final_value,
            "seed_frontier_direct_residual_inf_n": current_frontier,
            "frontier_improvement_inf_n": frontier_improvement,
            "frontier_relative_improvement": frontier_relative_improvement,
            "residual_gate_passed": child_summary.get("residual_gate_passed"),
            "child_runtime_seconds": child_runtime_seconds,
            "runtime_budget_seconds": runtime_budget_seconds,
            "child_timeout_seconds": effective_timeout,
            **subprocess_meta,
        }
        rows.append(row)

        if bool(row.get("subprocess_timeout")):
            runtime_budget_exceeded = True
            stop_reason = "child_timeout_seconds_exceeded"
            break
        if accepted:
            promotion_count += 1
            promoted_rows.append(row)
            current_frontier = child_final_value
            final_residual = child_final_value
            if child_checkpoint is not None and child_checkpoint.is_file():
                final_checkpoint = child_checkpoint
            stop_reason = "candidate_promoted"
            break
        if runtime_budget_seconds is not None and time.perf_counter() - started >= runtime_budget_seconds:
            runtime_budget_exceeded = True
            stop_reason = "runtime_budget_exceeded"
            break

    if not candidates and not runtime_budget_exceeded and not preflight_blockers:
        stop_reason = "no_candidates_requested"
    if rows and stop_reason == "max_candidates_reached":
        final_residual = current_frontier

    output_final_checkpoint_written = False
    if (
        output_final_checkpoint_npz is not None
        and promotion_count > 0
        and final_checkpoint.is_file()
    ):
        output_final_checkpoint_npz.parent.mkdir(parents=True, exist_ok=True)
        if final_checkpoint.resolve() != output_final_checkpoint_npz.resolve():
            shutil.copyfile(final_checkpoint, output_final_checkpoint_npz)
        final_checkpoint = output_final_checkpoint_npz
        output_final_checkpoint_written = True

    best_row = min(
        (row for row in rows if row.get("final_direct_residual_inf_n") is not None),
        key=lambda row: float(row["final_direct_residual_inf_n"]),
        default={},
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "partial",
        "shell_material_rowcorr_budget_controller_ready": True,
        "direct_residual_gate_passed": bool(
            final_residual is not None and final_residual <= float(residual_tolerance_n)
        ),
        "seed_probe": seed_summary,
        "controller": {
            "enabled": True,
            "attempted": True,
            "promotion_count": int(promotion_count),
            "max_candidates": int(max_candidates),
            "stop_reason": stop_reason,
            "preflight_blockers": preflight_blockers,
            "row_target_counts": [int(value) for value in row_target_counts],
            "row_support_column_counts": [
                int(value) for value in row_support_column_counts
            ],
            "row_alpha_values": [float(value) for value in row_alpha_values],
            "row_target_mode": str(row_target_mode),
            "row_support_selection": str(row_support_selection),
            "row_frontier_probe_json": (
                None if row_frontier_probe_json is None else str(row_frontier_probe_json)
            ),
            "row_frontier_component_scale_mode": str(
                row_frontier_component_scale_mode
            ),
            "row_jacobian_mode": str(row_jacobian_mode),
            "row_fd_epsilon": float(row_fd_epsilon),
            "row_fd_max_support_columns": int(row_fd_max_support_columns),
            "row_batch_fd_replay": bool(row_batch_fd_replay),
            "row_batch_fd_replay_chunk_size": int(row_batch_fd_replay_chunk_size),
            "row_batch_replay_backend": str(row_batch_replay_backend),
            "row_require_hip_batch_replay": bool(row_require_hip_batch_replay),
            "allow_frozen_shell_material_tangent_hip_replay": bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "row_use_residual_only_assembly": bool(row_use_residual_only_assembly),
            "row_batch_alpha_replay": bool(row_batch_alpha_replay),
            "max_row_promotions_per_child": int(max_row_promotions),
            "write_child_checkpoints": bool(write_child_checkpoints),
            "compact_child_checkpoints": bool(compact_child_checkpoints),
            "row_min_relative_improvement": float(row_min_relative_improvement),
            "controller_min_relative_improvement": float(
                controller_min_relative_improvement
            ),
            "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
            "residual_tolerance_n": float(residual_tolerance_n),
            "relative_increment_tolerance": float(relative_increment_tolerance),
            "runtime_budget_seconds": runtime_budget_seconds,
            "runtime_budget_exceeded": bool(runtime_budget_exceeded),
            "child_timeout_seconds": float(child_timeout_seconds),
        },
        "initial_checkpoint_path": str(checkpoint_npz),
        "final_checkpoint_path": str(final_checkpoint),
        "output_final_checkpoint_written": bool(output_final_checkpoint_written),
        "initial_frontier_direct_residual_inf_n": seed_frontier,
        "final_direct_residual_inf_n": final_residual,
        "rows": rows,
        "promoted_rows": promoted_rows,
        "best_candidate_row": best_row,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": _build_shell_rowcorr_claim_boundary(
            require_hip=bool(row_require_hip_batch_replay),
            backend_is_hip=bool(row_batch_replay_backend != "cpu"),
            preflight_blockers_exist=bool(preflight_blockers),
            runtime_budget_exceeded=bool(runtime_budget_exceeded),
            promoted_rows=promoted_rows,
            rows=rows,
        ),
    }
    _write_json(output_json, payload)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_SHELL_MATERIAL_CHECKPOINT)
    parser.add_argument("--seed-probe-json", type=Path, default=DEFAULT_SEED_PROBE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument("--child-output-dir", type=Path, default=None)
    parser.add_argument("--python-exe", type=Path, default=Path(sys.executable))
    parser.add_argument("--row-target-counts", default="1")
    parser.add_argument("--row-support-column-counts", default="4")
    parser.add_argument("--row-alpha-values", default="0.015625")
    parser.add_argument(
        "--row-target-mode",
        choices=(
            "largest_rows",
            "residual_node_blocks",
            "residual_element_blocks",
            "residual_frame_element_blocks",
            "residual_shell_element_blocks",
            "residual_shell_bending_drilling_rows",
            "residual_shell_normal_rows",
            "residual_shell_geometry_normal_rows",
            "residual_shell_geometry_normal_bending_rows",
            "frontier_component_rows",
            "current_component_rows",
        ),
        default="largest_rows",
    )
    parser.add_argument("--row-frontier-probe-json", type=Path, default=None)
    parser.add_argument(
        "--row-frontier-component-scale-mode",
        choices=("none", "dominant_component_magnitude", "total_component_magnitude"),
        default="none",
    )
    parser.add_argument(
        "--row-jacobian-mode",
        choices=("current_tangent", "finite_difference"),
        default="current_tangent",
    )
    parser.add_argument(
        "--row-support-selection",
        choices=("row_strongest", "residual_weighted", "target_rows"),
        default="row_strongest",
    )
    parser.add_argument("--row-fd-epsilon", type=float, default=1.0e-6)
    parser.add_argument("--row-fd-max-support-columns", type=int, default=12)
    parser.add_argument("--row-batch-fd-replay", action="store_true")
    parser.add_argument("--row-batch-fd-replay-chunk-size", type=int, default=64)
    parser.add_argument(
        "--row-batch-replay-backend",
        choices=("cpu", "hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"),
        default="cpu",
    )
    parser.add_argument("--row-require-hip-batch-replay", action="store_true")
    parser.add_argument(
        "--allow-frozen-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "Forward the direct-probe frozen shell-material tangent HIP replay flag. "
            "This uses a frozen current-state shell material CSR and is not full "
            "state-dependent material Newton closure."
        ),
    )
    parser.add_argument(
        "--allow-state-dependent-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "Forward candidate-state shell-material tangent HIP replay to child "
            "direct probes. Residual replay stays on HIP, but host shell operator "
            "refresh is not production residency closure."
        ),
    )
    parser.add_argument("--row-use-residual-only-assembly", action="store_true")
    parser.add_argument("--row-batch-alpha-replay", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=1)
    parser.add_argument("--max-row-promotions", type=int, default=1)
    parser.add_argument(
        "--write-child-checkpoints",
        action="store_true",
        help=(
            "Ask child probes to write final checkpoint NPZ files. The default records "
            "JSON receipts only to keep broad sweeps storage-bounded."
        ),
    )
    parser.add_argument(
        "--write-full-child-checkpoints",
        action="store_true",
        help=(
            "When --write-child-checkpoints is enabled, keep full accepted history "
            "arrays instead of compact displacement-only checkpoints."
        ),
    )
    parser.add_argument("--row-min-relative-improvement", type=float, default=0.0)
    parser.add_argument("--controller-min-relative-improvement", type=float, default=1.0e-7)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only", "structural_components_only"),
        default="structural_components_only",
    )
    parser.add_argument("--residual-tolerance-n", type=float, default=5.0e-4)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--max-controller-runtime-seconds", type=float, default=None)
    parser.add_argument("--child-timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--current-tangent-residual-row-support-selection",
        choices=("row_strongest", "residual_weighted", "target_rows"),
        default=None,
        help=(
            "Deprecated alias for --row-support-selection. Accepted for older "
            "dispatch prompts and forwarded to child direct probes."
        ),
    )
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help="Acknowledge this controller orchestrates CPU-diagnostic child probes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    needs_cpu_ack = not (
        args.row_require_hip_batch_replay
        and args.row_batch_replay_backend != "cpu"
    )
    if needs_cpu_ack and not args.allow_cpu_diagnostic:
        print(
            "mgt-shell-material-rowcorr-budget-controller: blocked cpu diagnostic "
            "requires --allow-cpu-diagnostic",
            file=sys.stderr,
        )
        return 2
    try:
        row_support_selection = args.row_support_selection
        if args.current_tangent_residual_row_support_selection is not None:
            row_support_selection = args.current_tangent_residual_row_support_selection
        payload = run_shell_material_rowcorr_budget_controller(
            mgt_path=args.mgt_path,
            checkpoint_npz=args.checkpoint_npz,
            seed_probe_json=args.seed_probe_json,
            output_json=args.output_json,
            output_final_checkpoint_npz=args.output_final_checkpoint_npz,
            child_output_dir=args.child_output_dir,
            python_exe=args.python_exe,
            row_target_counts=_parse_int_csv(args.row_target_counts) or (1,),
            row_support_column_counts=_parse_int_csv(args.row_support_column_counts) or (4,),
            row_alpha_values=_parse_float_csv(args.row_alpha_values) or (0.015625,),
            row_target_mode=args.row_target_mode,
            row_frontier_probe_json=args.row_frontier_probe_json,
            row_frontier_component_scale_mode=args.row_frontier_component_scale_mode,
            row_jacobian_mode=args.row_jacobian_mode,
            row_support_selection=row_support_selection,
            row_fd_epsilon=args.row_fd_epsilon,
            row_fd_max_support_columns=args.row_fd_max_support_columns,
            row_batch_fd_replay=args.row_batch_fd_replay,
            row_batch_fd_replay_chunk_size=args.row_batch_fd_replay_chunk_size,
            row_batch_replay_backend=args.row_batch_replay_backend,
            row_require_hip_batch_replay=args.row_require_hip_batch_replay,
            allow_frozen_shell_material_tangent_hip_replay=(
                args.allow_frozen_shell_material_tangent_hip_replay
            ),
            allow_state_dependent_shell_material_tangent_hip_replay=(
                args.allow_state_dependent_shell_material_tangent_hip_replay
            ),
            row_use_residual_only_assembly=args.row_use_residual_only_assembly,
            row_batch_alpha_replay=args.row_batch_alpha_replay,
            max_candidates=args.max_candidates,
            max_row_promotions=args.max_row_promotions,
            write_child_checkpoints=args.write_child_checkpoints,
            compact_child_checkpoints=not args.write_full_child_checkpoints,
            row_min_relative_improvement=args.row_min_relative_improvement,
            controller_min_relative_improvement=args.controller_min_relative_improvement,
            shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
            residual_tolerance_n=args.residual_tolerance_n,
            relative_increment_tolerance=args.relative_increment_tolerance,
            max_controller_runtime_seconds=args.max_controller_runtime_seconds,
            child_timeout_seconds=args.child_timeout_seconds,
        )
    except ValueError as exc:
        print(
            f"mgt-shell-material-rowcorr-budget-controller: {exc}",
            file=sys.stderr,
        )
        return 2
    controller = payload["controller"]
    print(
        "mgt-shell-material-rowcorr-budget-controller: "
        f"status={payload['status']} promotions={controller['promotion_count']} "
        f"stop={controller['stop_reason']} final={payload['final_direct_residual_inf_n']} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
