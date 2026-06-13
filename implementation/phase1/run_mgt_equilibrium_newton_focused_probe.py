#!/usr/bin/env python3
"""Focused equilibrium Newton probe from an accepted checkpoint."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_equilibrium_replay import run_equilibrium_newton  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    _load_checkpoint,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-equilibrium-newton-focused-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_equilibrium_newton_focused_probe.json"
DEFAULT_CHECKPOINT_OUT = (
    PRODUCTIZATION / "mgt_equilibrium_newton_focused_probe_final_checkpoint.npz"
)


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _translation_metrics(u: np.ndarray) -> dict[str, float]:
    arr = np.asarray(u, dtype=np.float64)
    if arr.size % 6 != 0:
        return {"max_translation_m": _max_abs(arr)}
    translations = arr.reshape((-1, 6))[:, :3]
    return {
        "max_translation_m": float(np.max(np.linalg.norm(translations, axis=1)))
        if translations.size
        else 0.0
    }


def _same_state_exact(left: np.ndarray, right: np.ndarray) -> bool:
    return bool(
        np.array_equal(
            np.asarray(left, dtype=np.float64),
            np.asarray(right, dtype=np.float64),
        )
    )


def _write_equilibrium_checkpoint(
    *,
    path: Path,
    source_checkpoint_npz: Path,
    checkpoint_meta: dict[str, Any],
    u0: np.ndarray,
    final_u: np.ndarray,
    base_residual: np.ndarray,
    final_residual: np.ndarray,
    final_rhs: np.ndarray,
    loaded_state_history: np.ndarray | None,
    loaded_residual_history: np.ndarray | None,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    final_u = np.asarray(final_u, dtype=np.float64)
    u0 = np.asarray(u0, dtype=np.float64)
    final_residual = np.asarray(final_residual, dtype=np.float64)
    final_rhs = np.asarray(final_rhs, dtype=np.float64)
    base_residual = np.asarray(base_residual, dtype=np.float64)

    state_rows: list[np.ndarray] = []
    if (
        loaded_state_history is not None
        and loaded_state_history.ndim == 2
        and loaded_state_history.shape[1] == final_u.size
    ):
        state_rows = [np.asarray(row, dtype=np.float64).copy() for row in loaded_state_history]
    if not state_rows or not _same_state_exact(state_rows[-1], u0):
        state_rows.append(u0.copy())
    if not _same_state_exact(state_rows[-1], final_u):
        state_rows.append(final_u.copy())

    residual_rows: list[np.ndarray] = []
    if (
        loaded_residual_history is not None
        and loaded_residual_history.ndim == 2
        and loaded_residual_history.shape[1] == final_residual.size
    ):
        residual_rows = [
            np.asarray(row, dtype=np.float64).copy() for row in loaded_residual_history
        ]
    while len(residual_rows) < max(len(state_rows) - 1, 0):
        residual_rows.append(base_residual.copy())
    if len(residual_rows) < len(state_rows):
        residual_rows.append(final_residual.copy())
    else:
        residual_rows[-1] = final_residual.copy()

    state_history = np.vstack(state_rows)
    residual_history = np.vstack(residual_rows)
    final_residual_inf = _max_abs(final_residual)
    rhs_inf = _max_abs(final_rhs)
    translation = _translation_metrics(final_u)
    load_scale = float(checkpoint_meta["load_scale"])
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        source_schema_version=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(load_scale, dtype=np.float64),
        displacement_u=final_u,
        residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_relative_residual_inf=np.asarray(
            final_residual_inf / max(rhs_inf, 1.0),
            dtype=np.float64,
        ),
        max_translation_m=np.asarray(translation["max_translation_m"], dtype=np.float64),
        accepted_state_history_u=state_history,
        accepted_residual_history=residual_history,
        accepted_history_count=np.asarray(state_history.shape[0], dtype=np.int64),
        source_checkpoint_path=np.asarray(str(source_checkpoint_npz)),
    )
    return {
        "written": True,
        "path": str(path),
        "schema": "mgt-direct-residual-newton-state.v1",
        "load_scale": load_scale,
        "dof_count": int(final_u.size),
        "direct_residual_inf_n": final_residual_inf,
        "direct_relative_residual_inf": final_residual_inf / max(rhs_inf, 1.0),
        "max_translation_m": translation["max_translation_m"],
        "accepted_history_count": int(state_history.shape[0]),
        "source_checkpoint_path": str(source_checkpoint_npz),
    }


def run_mgt_equilibrium_newton_focused_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    max_newton_iterations: int = 8,
    residual_tolerance_n: float = 5.0e-4,
    prefer_host_ilu: bool = True,
    allow_negative_alphas: bool = False,
    linear_solver_profile: str = "production",
    state_scale_line_search_values: tuple[float, ...] = (),
    state_scale_only: bool = False,
    output_final_checkpoint_npz: Path | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    u0 = np.asarray(setup_meta["u0"])
    initial_assembly = assemble_residual(u0)
    _stiffness, _f_ext, _free, base_residual, _rhs, _meta = initial_assembly
    base_residual_inf = float(np.max(np.abs(base_residual))) if base_residual.size else 0.0
    newton = run_equilibrium_newton(
        u0=u0,
        assemble_residual=assemble_residual,
        initial_assembly=initial_assembly,
        max_newton_iterations=max_newton_iterations,
        residual_tolerance_n=residual_tolerance_n,
        prefer_host_ilu=prefer_host_ilu,
        allow_negative_alphas=bool(allow_negative_alphas),
        linear_solver_profile=str(linear_solver_profile or "production"),
        state_scale_line_search_values=state_scale_line_search_values,
        state_scale_only=bool(state_scale_only),
    )
    output_checkpoint_meta: dict[str, Any] | None = None
    if output_final_checkpoint_npz is not None and float(newton.get("final_residual_inf_n") or 0.0) < base_residual_inf:
        checkpoint_meta, _loaded_u, loaded_state_history, loaded_residual_history = _load_checkpoint(
            checkpoint_npz
        )
        final_u = np.asarray(newton["final_u"], dtype=np.float64)
        final_residual_value = newton.get("final_residual")
        final_rhs_value = newton.get("final_rhs")
        if isinstance(final_residual_value, np.ndarray) and isinstance(final_rhs_value, np.ndarray):
            final_residual = np.asarray(final_residual_value, dtype=np.float64)
            final_rhs = np.asarray(final_rhs_value, dtype=np.float64)
        else:
            _final_k, _final_f, _final_free, final_residual, final_rhs, _final_meta = assemble_residual(
                final_u
            )
        output_checkpoint_meta = _write_equilibrium_checkpoint(
            path=output_final_checkpoint_npz,
            source_checkpoint_npz=checkpoint_npz,
            checkpoint_meta=checkpoint_meta,
            u0=u0,
            final_u=final_u,
            base_residual=np.asarray(base_residual, dtype=np.float64),
            final_residual=np.asarray(final_residual, dtype=np.float64),
            final_rhs=np.asarray(final_rhs, dtype=np.float64),
            loaded_state_history=loaded_state_history,
            loaded_residual_history=loaded_residual_history,
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if newton["converged"] else "partial",
        "equilibrium_newton_ready": bool(newton["converged"]),
        "checkpoint": setup_meta.get("checkpoint"),
        "load_scale": setup_meta.get("load_scale"),
        "base_residual_inf_n": base_residual_inf,
        "initial_residual_inf_n": newton.get("initial_residual_inf_n"),
        "final_residual_inf_n": newton.get("final_residual_inf_n"),
        "accepted_newton_iteration_count": newton.get("accepted_newton_iteration_count"),
        "allow_negative_alphas": bool(allow_negative_alphas),
        "linear_solver_profile": str(linear_solver_profile or "production"),
        "state_scale_line_search_values": [
            float(value) for value in state_scale_line_search_values
        ],
        "state_scale_only": bool(state_scale_only),
        "residual_tolerance_n": float(residual_tolerance_n),
        "newton_iterations": newton.get("iterations"),
        "output_final_checkpoint": output_checkpoint_meta,
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Equilibrium Newton on the physical residual R=F_int-F_ext with tangent J delta_u=-R, "
            "host ILU + ROCm matvec GMRES when available, and residual-norm line search."
        ),
        "blockers": [] if newton["converged"] else ["equilibrium_newton_gate_not_closed"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--output-final-checkpoint-npz",
        type=Path,
        default=None,
        help="Write a resumable mgt-direct-residual-newton-state checkpoint when the Newton state improves the residual.",
    )
    parser.add_argument("--max-newton-iterations", type=int, default=8)
    parser.add_argument(
        "--allow-negative-alphas",
        action="store_true",
        help="Opt in to signed alpha search for residual-descent globalization.",
    )
    parser.add_argument(
        "--linear-solver-profile",
        choices=(
            "production",
            "regularized_direct",
            "block_jacobi_gmres",
            "host_ilu_device_gmres",
        ),
        default="production",
        help=(
            "Use production iterative attempts, bypass them for a focused "
            "regularized-direct diagnostic, use a block-Jacobi GMRES-only "
            "diagnostic profile, or force the ROCm host-ILU/device-GMRES "
            "path first."
        ),
    )
    parser.add_argument(
        "--state-scale-line-search-values",
        default="",
        help=(
            "Comma-separated state scales evaluated before Newton correction. "
            "Useful for diagnosing/rescuing incompatible checkpoint states."
        ),
    )
    parser.add_argument(
        "--state-scale-only",
        action="store_true",
        help="Evaluate state-scale candidates and skip the Newton linear solve.",
    )
    args = parser.parse_args()
    state_scale_line_search_values = tuple(
        float(value.strip())
        for value in str(args.state_scale_line_search_values).split(",")
        if value.strip()
    )
    payload = run_mgt_equilibrium_newton_focused_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        max_newton_iterations=args.max_newton_iterations,
        allow_negative_alphas=bool(args.allow_negative_alphas),
        linear_solver_profile=str(args.linear_solver_profile),
        state_scale_line_search_values=state_scale_line_search_values,
        state_scale_only=bool(args.state_scale_only),
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
    )
    print(
        "equilibrium-newton-focused:",
        payload["status"],
        f"final={payload.get('final_residual_inf_n')}",
        "->",
        args.output_json,
    )
    return 0 if payload.get("equilibrium_newton_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
