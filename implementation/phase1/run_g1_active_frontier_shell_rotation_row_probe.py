#!/usr/bin/env python3
"""Probe shell bending/drilling rotational rows at the G1 active frontier."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) in sys.path:
    sys.path.remove(str(PHASE1))
sys.path.insert(0, str(PHASE1))

from run_g1_true_newton_reference_candidate import (  # noqa: E402
    CHECKPOINT_SCHEMA,
    _max_abs,
    _translation_metrics,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    ENGINE_VERSION,
    PRODUCTIZATION,
    _git_head,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "g1-active-frontier-shell-rotation-row-probe.v1"
DEFAULT_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.npz"
)
DEFAULT_OWNERSHIP_JSON = (
    PRODUCTIZATION / "g1_active_frontier_structural_policy_residual_ownership_probe.json"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_active_frontier_structural_policy_shell_rotation_row_probe.json"
DEFAULT_OUT_NPZ = (
    PRODUCTIZATION / "g1_active_frontier_structural_policy_shell_rotation_row_candidate.npz"
)
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
ROTATION_LABELS = {"RX", "RY", "RZ"}

AssembleResidual = Callable[
    [np.ndarray],
    tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]],
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _parse_float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in str(value).split(",") if item.strip())


def _parse_int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in str(value).split(",") if item.strip())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _row_descriptor(*, global_dof: int, free_row: int, residual: np.ndarray) -> dict[str, Any]:
    global_dof_int = int(global_dof)
    local_dof = int(global_dof_int % DOF_PER_NODE)
    return {
        "global_dof": global_dof_int,
        "free_row": int(free_row),
        "node_index": int(global_dof_int // DOF_PER_NODE),
        "node_id": int(global_dof_int // DOF_PER_NODE) + 1,
        "dof_label": DOF_LABELS[local_dof],
        "base_residual_n": float(np.asarray(residual, dtype=np.float64)[int(free_row)]),
    }


def _ownership_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    breakdown = payload.get("residual_ownership_breakdown")
    if isinstance(breakdown, dict) and isinstance(breakdown.get("top_rows"), list):
        return [row for row in breakdown["top_rows"] if isinstance(row, dict)]
    rows = payload.get("top_rows")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _select_rotation_rows(
    *,
    residual: np.ndarray,
    free: np.ndarray,
    max_rows: int,
    ownership_payload: dict[str, Any] | None = None,
    component_filter: str = "shell_bending_drilling",
    target_global_dofs: tuple[int, ...] = (),
) -> list[dict[str, Any]]:
    residual_np = np.asarray(residual, dtype=np.float64)
    free_idx = np.asarray(free, dtype=np.int64)
    free_row_by_global = {
        int(global_dof): int(row) for row, global_dof in enumerate(free_idx.tolist())
    }
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add_global(global_dof: int) -> None:
        if len(selected) >= max(int(max_rows), 0):
            return
        global_dof_int = int(global_dof)
        if global_dof_int in seen or global_dof_int not in free_row_by_global:
            return
        local_dof = int(global_dof_int % DOF_PER_NODE)
        if DOF_LABELS[local_dof] not in ROTATION_LABELS:
            return
        free_row = int(free_row_by_global[global_dof_int])
        selected.append(
            _row_descriptor(
                global_dof=global_dof_int,
                free_row=free_row,
                residual=residual_np,
            )
        )
        seen.add(global_dof_int)

    for global_dof in target_global_dofs:
        add_global(int(global_dof))
    if len(selected) >= max(int(max_rows), 0):
        return selected

    for row in _ownership_rows(ownership_payload or {}):
        if str(row.get("dof_label") or "").upper() not in ROTATION_LABELS:
            continue
        if component_filter not in {"all", ""} and str(
            row.get("dominant_internal_component") or ""
        ) != component_filter:
            continue
        add_global(int(row.get("global_dof", -1)))
        if len(selected) >= max(int(max_rows), 0):
            return selected

    order = np.argsort(-np.abs(residual_np))
    for free_row in order.tolist():
        global_dof = int(free_idx[int(free_row)])
        add_global(global_dof)
        if len(selected) >= max(int(max_rows), 0):
            break
    return selected


def _sparse_column(stiffness: Any, free: np.ndarray, global_dof: int) -> np.ndarray:
    col = stiffness[np.asarray(free, dtype=np.int64), int(global_dof)]
    return np.asarray(col.toarray() if hasattr(col, "toarray") else col, dtype=np.float64).reshape(-1)


def _diag_value(stiffness: Any, global_dof: int) -> float:
    value = stiffness[int(global_dof), int(global_dof)]
    if hasattr(value, "toarray"):
        arr = np.asarray(value.toarray(), dtype=np.float64)
        return float(arr.reshape(-1)[0]) if arr.size else 0.0
    return float(value)


def run_shell_rotation_row_probe(
    *,
    assemble_residual: AssembleResidual,
    u0: np.ndarray,
    ownership_payload: dict[str, Any] | None = None,
    target_global_dofs: tuple[int, ...] = (),
    max_rows: int = 4,
    fd_step: float = 1.0e-6,
    alpha_values: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125),
    residual_gate_n: float = 5.0e-4,
    component_filter: str = "shell_bending_drilling",
) -> dict[str, Any]:
    base_u = np.asarray(u0, dtype=np.float64)
    stiffness, _f_ext, free, residual, rhs, _meta = assemble_residual(base_u)
    free = np.asarray(free, dtype=np.int64)
    residual = np.asarray(residual, dtype=np.float64)
    rhs = np.asarray(rhs, dtype=np.float64)
    selected_rows = _select_rotation_rows(
        residual=residual,
        free=free,
        max_rows=max_rows,
        ownership_payload=ownership_payload or {},
        component_filter=component_filter,
        target_global_dofs=target_global_dofs,
    )

    jvp_rows: list[dict[str, Any]] = []
    correction = np.zeros_like(base_u)
    for row in selected_rows:
        global_dof = int(row["global_dof"])
        free_row = int(row["free_row"])
        direction = np.zeros_like(base_u)
        direction[global_dof] = 1.0
        plus_u = base_u + float(fd_step) * direction
        minus_u = base_u - float(fd_step) * direction
        _kp, _fp, plus_free, plus_residual, _plus_rhs, _plus_meta = assemble_residual(
            plus_u,
            residual_only=True,
            free_override=free,
        )
        _km, _fm, minus_free, minus_residual, _minus_rhs, _minus_meta = assemble_residual(
            minus_u,
            residual_only=True,
            free_override=free,
        )
        free_stable = bool(
            np.asarray(plus_free, dtype=np.int64).shape == free.shape
            and np.array_equal(np.asarray(plus_free, dtype=np.int64), free)
            and np.asarray(minus_free, dtype=np.int64).shape == free.shape
            and np.array_equal(np.asarray(minus_free, dtype=np.int64), free)
        )
        tangent_action = _sparse_column(stiffness, free, global_dof)
        fd_action = (
            np.asarray(plus_residual, dtype=np.float64)
            - np.asarray(minus_residual, dtype=np.float64)
        ) / (2.0 * float(fd_step))
        diff = tangent_action - fd_action
        tangent_inf = _max_abs(tangent_action)
        fd_inf = _max_abs(fd_action)
        diff_inf = _max_abs(diff)
        tangent_l2 = float(np.linalg.norm(tangent_action)) if tangent_action.size else 0.0
        fd_l2 = float(np.linalg.norm(fd_action)) if fd_action.size else 0.0
        denom = tangent_l2 * fd_l2
        cosine = float(np.dot(tangent_action, fd_action) / denom) if denom > 0.0 else 0.0
        diagonal = _diag_value(stiffness, global_dof)
        residual_value = float(residual[free_row])
        delta = -residual_value / diagonal if abs(diagonal) > 1.0e-18 else 0.0
        correction[global_dof] = delta
        selected_tangent = float(tangent_action[free_row])
        selected_fd = float(fd_action[free_row])
        selected_diff = selected_tangent - selected_fd
        jvp_rows.append(
            {
                **row,
                "evaluated": True,
                "fd_step": float(fd_step),
                "free_dof_set_stable": free_stable,
                "diagonal_tangent_n_per_rad": diagonal,
                "unit_alpha_correction_rad": float(delta),
                "selected_row_tangent_action_n_per_rad": selected_tangent,
                "selected_row_fd_action_n_per_rad": selected_fd,
                "selected_row_diff_n_per_rad": selected_diff,
                "selected_row_relative_error": abs(selected_diff)
                / max(abs(selected_tangent), abs(selected_fd), 1.0e-30),
                "tangent_action_inf_n_per_rad": tangent_inf,
                "fd_action_inf_n_per_rad": fd_inf,
                "diff_inf_n_per_rad": diff_inf,
                "relative_inf_error": diff_inf / max(tangent_inf, fd_inf, 1.0e-30),
                "tangent_action_l2_n_per_rad": tangent_l2,
                "fd_action_l2_n_per_rad": fd_l2,
                "diff_l2_n_per_rad": float(np.linalg.norm(diff)) if diff.size else 0.0,
                "action_cosine": cosine,
            }
        )

    base_residual_inf = _max_abs(residual)
    rhs_inf = _max_abs(rhs)
    correction_inf = _max_abs(correction)
    candidate_rows: list[dict[str, Any]] = []
    best_state = base_u.copy()
    best_residual = residual.copy()
    best_rhs = rhs.copy()
    best_inf = base_residual_inf
    best_state_alpha = 0.0
    max_abs_u = max(_max_abs(base_u), 1.0e-12)
    for alpha in alpha_values:
        trial_u = base_u + float(alpha) * correction
        _trial_k, _trial_f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(trial_u)
        trial_free = np.asarray(trial_free, dtype=np.int64)
        trial_residual = np.asarray(trial_residual, dtype=np.float64)
        trial_rhs = np.asarray(trial_rhs, dtype=np.float64)
        trial_inf = _max_abs(trial_residual)
        relative_increment = abs(float(alpha)) * correction_inf / max_abs_u
        candidate_rows.append(
            {
                "alpha": float(alpha),
                "free_dof_set_stable": bool(
                    trial_free.shape == free.shape and np.array_equal(trial_free, free)
                ),
                "direct_residual_inf_n": trial_inf,
                "direct_relative_residual_inf": trial_inf / max(_max_abs(trial_rhs), 1.0),
                "improvement_inf_n": base_residual_inf - trial_inf,
                "relative_improvement": (base_residual_inf - trial_inf)
                / max(base_residual_inf, 1.0e-30),
                "relative_increment": relative_increment,
                "residual_gate_passed": trial_inf <= float(residual_gate_n),
            }
        )
        if trial_inf < best_inf and bool(
            trial_free.shape == free.shape and np.array_equal(trial_free, free)
        ):
            best_inf = trial_inf
            best_state = trial_u.copy()
            best_residual = trial_residual.copy()
            best_rhs = trial_rhs.copy()
            best_state_alpha = float(alpha)

    best_candidate = min(
        (row for row in candidate_rows if bool(row.get("free_dof_set_stable"))),
        key=lambda row: float(row["direct_residual_inf_n"]),
        default={},
    )
    evaluated_rows = [row for row in jvp_rows if bool(row.get("evaluated"))]
    max_selected_error = max(
        (float(row.get("selected_row_relative_error") or 0.0) for row in evaluated_rows),
        default=0.0,
    )
    max_relative_error = max(
        (float(row.get("relative_inf_error") or 0.0) for row in evaluated_rows),
        default=0.0,
    )
    min_cosine = min(
        (float(row.get("action_cosine") or 0.0) for row in evaluated_rows),
        default=0.0,
    )
    return {
        "summary": {
            "base_residual_inf_n": base_residual_inf,
            "base_relative_residual_inf": base_residual_inf / max(rhs_inf, 1.0),
            "residual_gate_n": float(residual_gate_n),
            "base_residual_gate_passed": bool(base_residual_inf <= float(residual_gate_n)),
            "selected_rotation_row_count": int(len(selected_rows)),
            "evaluated_jvp_row_count": int(len(evaluated_rows)),
            "max_selected_row_relative_error": max_selected_error,
            "max_relative_inf_error": max_relative_error,
            "min_action_cosine": min_cosine,
            "fd_consistent": bool(
                evaluated_rows
                and max_selected_error <= 0.25
                and max_relative_error <= 0.25
                and min_cosine >= 0.8
            ),
            "correction_inf_rad": correction_inf,
            "best_direct_residual_inf_n": float(
                best_candidate.get("direct_residual_inf_n", base_residual_inf)
            ),
            "best_improvement_inf_n": float(
                best_candidate.get("improvement_inf_n", 0.0)
            ),
            "direct_descent_observed": bool(
                float(best_candidate.get("improvement_inf_n", 0.0)) > 0.0
            ),
            "best_residual_gate_passed": (
                best_candidate.get("residual_gate_passed") is True
            ),
        },
        "selected_rotation_rows": selected_rows,
        "jvp_rows": jvp_rows,
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate,
        "best_state": best_state,
        "best_residual": best_residual,
        "best_rhs": best_rhs,
        "best_state_alpha": best_state_alpha,
    }


def _write_checkpoint(
    *,
    path: Path,
    load_scale: float,
    displacement_u: np.ndarray,
    final_residual: np.ndarray,
    final_rhs: np.ndarray,
    residual_gate_n: float,
    shell_pressure_load_path_policy: str,
    best_alpha: float,
) -> dict[str, Any]:
    residual_inf = _max_abs(final_residual)
    rhs_inf = _max_abs(final_rhs)
    translation = _translation_metrics(displacement_u)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray(CHECKPOINT_SCHEMA),
        source_schema_version=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(float(load_scale), dtype=np.float64),
        displacement_u=np.asarray(displacement_u, dtype=np.float64),
        residual_inf_n=np.asarray(residual_inf, dtype=np.float64),
        direct_residual_inf_n=np.asarray(residual_inf, dtype=np.float64),
        direct_relative_residual_inf=np.asarray(
            residual_inf / max(rhs_inf, 1.0),
            dtype=np.float64,
        ),
        max_translation_m=np.asarray(
            translation["max_translation_m"],
            dtype=np.float64,
        ),
        accepted_iteration_count=np.asarray(1 if best_alpha != 0.0 else 0, dtype=np.int64),
        accepted_history_count=np.asarray(1 if best_alpha != 0.0 else 0, dtype=np.int64),
        residual_gate_n=np.asarray(float(residual_gate_n), dtype=np.float64),
        residual_gate_passed=np.asarray(bool(residual_inf <= float(residual_gate_n))),
        shell_pressure_load_path_policy=np.asarray(shell_pressure_load_path_policy),
        shell_rotation_row_candidate_only=np.asarray(True),
        promotes_g1_closure=np.asarray(False),
        checkpoint_claim_boundary=np.asarray(
            "non_promoting_shell_rotation_row_checkpoint_candidate"
        ),
    )
    return {
        "written": True,
        "path": str(path),
        "schema": CHECKPOINT_SCHEMA,
        "load_scale": float(load_scale),
        "dof_count": int(np.asarray(displacement_u).size),
        "direct_residual_inf_n": residual_inf,
        "direct_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
        "max_translation_m": translation["max_translation_m"],
        "accepted_iteration_count": int(1 if best_alpha != 0.0 else 0),
        "accepted_history_count": int(1 if best_alpha != 0.0 else 0),
        "residual_gate_n": float(residual_gate_n),
        "residual_gate_passed": bool(residual_inf <= float(residual_gate_n)),
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "best_alpha": float(best_alpha),
        "promotes_g1_closure": False,
        "claim_boundary": (
            "Loadable shell-rotation-row checkpoint candidate only. It does not "
            "close G1 without direct residual, material Newton, full-mesh, and "
            "production ROCm/HIP gates."
        ),
    }


def run_g1_active_frontier_shell_rotation_row_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    ownership_json: Path = DEFAULT_OWNERSHIP_JSON,
    shell_pressure_load_path_policy: str = "structural_components_only",
    target_global_dofs: tuple[int, ...] = (),
    max_rows: int = 4,
    fd_step: float = 1.0e-6,
    alpha_values: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125),
    residual_gate_n: float = 5.0e-4,
    output_json: Path = DEFAULT_OUT,
    output_final_checkpoint_npz: Path | None = DEFAULT_OUT_NPZ,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )
    result = run_shell_rotation_row_probe(
        assemble_residual=assemble_residual,
        u0=np.asarray(setup_meta["u0"], dtype=np.float64),
        ownership_payload=_load_json(ownership_json),
        target_global_dofs=target_global_dofs,
        max_rows=max_rows,
        fd_step=fd_step,
        alpha_values=alpha_values,
        residual_gate_n=residual_gate_n,
    )
    best_alpha = float(result.get("best_state_alpha", 0.0) or 0.0)
    final_checkpoint = None
    if output_final_checkpoint_npz is not None:
        final_checkpoint = _write_checkpoint(
            path=Path(output_final_checkpoint_npz),
            load_scale=float(setup_meta.get("load_scale") or 0.0),
            displacement_u=np.asarray(result["best_state"], dtype=np.float64),
            final_residual=np.asarray(result["best_residual"], dtype=np.float64),
            final_rhs=np.asarray(result["best_rhs"], dtype=np.float64),
            residual_gate_n=float(residual_gate_n),
            shell_pressure_load_path_policy=str(shell_pressure_load_path_policy),
            best_alpha=best_alpha,
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "status": "ready",
        "promotes_g1_closure": False,
        "mgt_model": str(mgt_path),
        "checkpoint_npz": str(checkpoint_npz),
        "ownership_json": str(ownership_json),
        "load_scale": setup_meta.get("load_scale"),
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "summary": result["summary"],
        "selected_rotation_rows": result["selected_rotation_rows"],
        "jvp_rows": result["jvp_rows"],
        "candidate_rows": result["candidate_rows"],
        "best_candidate": result["best_candidate"],
        "output_final_checkpoint": final_checkpoint,
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Diagnostic shell rotational-row tangent and diagonal replay evidence only. "
            "It targets RX/RY/RZ shell bending/drilling residual rows and does not "
            "close G1 full-load, material Newton, full-mesh, or production HIP gates."
        ),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT_NPZ)
    parser.add_argument("--ownership-json", type=Path, default=DEFAULT_OWNERSHIP_JSON)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only", "structural_components_only"),
        default="structural_components_only",
    )
    parser.add_argument("--target-global-dofs", default="")
    parser.add_argument("--max-rows", type=int, default=4)
    parser.add_argument("--fd-step", type=float, default=1.0e-6)
    parser.add_argument("--alpha-values", default="1,0.5,0.25,0.125,0.0625,0.03125")
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--output-json", "--out", dest="output_json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-final-checkpoint-npz",
        type=Path,
        default=DEFAULT_OUT_NPZ,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_g1_active_frontier_shell_rotation_row_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        ownership_json=args.ownership_json,
        shell_pressure_load_path_policy=str(args.shell_pressure_load_path_policy),
        target_global_dofs=(
            _parse_int_tuple(args.target_global_dofs)
            if str(args.target_global_dofs).strip()
            else ()
        ),
        max_rows=int(args.max_rows),
        fd_step=float(args.fd_step),
        alpha_values=_parse_float_tuple(args.alpha_values),
        residual_gate_n=float(args.residual_gate_n),
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
    )
    summary = payload["summary"]
    print(
        "g1-active-frontier-shell-rotation-row-probe:",
        payload["status"],
        f"base={summary.get('base_residual_inf_n')}",
        f"rows={summary.get('selected_rotation_row_count')}",
        f"fd_consistent={summary.get('fd_consistent')}",
        f"best={summary.get('best_direct_residual_inf_n')}",
        f"descent={summary.get('direct_descent_observed')}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
