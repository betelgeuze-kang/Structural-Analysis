#!/usr/bin/env python3
"""Build a cached residual-only finite-difference JVP batch for G1 probes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_cached_residual_jvp import (  # noqa: E402
    ResidualJvpBatchCache,
    build_fd_jvp_submatrix,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    _load_checkpoint,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_frame_hotspot_diagonal_newton_probe import (  # noqa: E402
    _equilibrate_lstsq_system,
    _expand_support_to_node_blocks,
    _ridge_coefficients,
    _select_block_lstsq_target_rows,
    _write_checkpoint,
)
from run_mgt_residual_jacobian_consistency_probe import (  # noqa: E402
    _component_breakdown,
    _max_abs,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-cached-residual-jvp-batch-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_cached_residual_jvp_batch_probe.json"


def _parse_float_csv(text: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(text).split(",") if value.strip())


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


def _select_support_columns(
    *,
    stiffness: Any,
    free: np.ndarray,
    target_rows: np.ndarray,
    support_columns_per_row: int,
    node_block_support: bool,
    max_support_columns: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    free_idx = np.asarray(free, dtype=np.int64)
    k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
    support: set[int] = set(int(row) for row in target_rows.tolist())
    selected_nodes = {
        int(free_idx[int(row)]) // 6
        for row in target_rows.tolist()
        if 0 <= int(row) < int(free_idx.size)
    }
    for local_col, global_dof in enumerate(free_idx.tolist()):
        if int(global_dof) // 6 in selected_nodes and int(global_dof) % 6 in {0, 1, 2}:
            support.add(int(local_col))
    for target_row in target_rows.tolist():
        start = int(k_ff.indptr[int(target_row)])
        end = int(k_ff.indptr[int(target_row) + 1])
        cols = k_ff.indices[start:end]
        vals = np.abs(k_ff.data[start:end])
        if cols.size:
            take = min(max(int(support_columns_per_row), 0), int(cols.size))
            if take:
                strongest = np.argpartition(vals, -take)[-take:]
                support.update(int(cols[index]) for index in strongest.tolist())
    support_cols = np.asarray(sorted(support), dtype=np.int64)
    pre_node_block_support_size = int(support_cols.size)
    if node_block_support:
        support_cols = _expand_support_to_node_blocks(support_cols, free_idx)
    pre_trim_support_size = int(support_cols.size)
    trimmed_by_limit = False
    if max_support_columns > 0 and support_cols.size > int(max_support_columns):
        k_ff = stiffness[free_idx, :][:, free_idx].tocsr()
        submatrix = k_ff[target_rows, :][:, support_cols].toarray()
        scores = np.linalg.norm(submatrix, axis=0)
        take = min(int(max_support_columns), int(support_cols.size))
        strongest = np.argpartition(scores, -take)[-take:]
        strongest = strongest[np.argsort(-scores[strongest], kind="stable")]
        support_cols = support_cols[strongest].astype(np.int64)
        support_cols = np.asarray(sorted(set(int(col) for col in support_cols.tolist())), dtype=np.int64)
        trimmed_by_limit = True
    return support_cols, {
        "pre_node_block_support_size": pre_node_block_support_size,
        "pre_trim_support_size": pre_trim_support_size,
        "support_size": int(support_cols.size),
        "node_block_support": bool(node_block_support),
        "support_trimmed_by_limit": bool(trimmed_by_limit),
        "max_support_columns": int(max_support_columns),
    }


def _torch_rocm_lstsq_probe(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    ridge_lambda: float,
) -> dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "attempted": False,
            "available": False,
            "reason": f"torch_import_failed:{type(exc).__name__}",
        }
    hip_version = getattr(getattr(torch, "version", None), "hip", None)
    device = "cuda" if bool(torch.cuda.is_available()) else "cpu"
    payload: dict[str, Any] = {
        "attempted": True,
        "available": True,
        "torch_version": str(getattr(torch, "__version__", "")),
        "torch_hip_version": str(hip_version) if hip_version is not None else None,
        "device": device,
        "rocm_device_available": bool(device == "cuda" and hip_version is not None),
    }
    try:
        started = time.perf_counter()
        a = torch.as_tensor(np.asarray(matrix, dtype=np.float64), device=device)
        b = torch.as_tensor(np.asarray(rhs, dtype=np.float64), device=device)
        if ridge_lambda > 0.0:
            eye = torch.eye(a.shape[1], dtype=a.dtype, device=device) * float(ridge_lambda)
            a = torch.cat([a, eye], dim=0)
            b = torch.cat([b, torch.zeros(a.shape[1], dtype=b.dtype, device=device)])
        solution = torch.linalg.lstsq(a, b).solution
        if device == "cuda":
            torch.cuda.synchronize()
        coeffs = solution.detach().cpu().numpy()
        residual = np.asarray(matrix, dtype=np.float64) @ coeffs - np.asarray(rhs, dtype=np.float64)
        payload.update(
            {
                "ok": True,
                "solve_seconds": float(time.perf_counter() - started),
                "coefficient_linf": _max_abs(coeffs),
                "linear_residual_inf_n_unscaled": _max_abs(residual),
            }
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        payload.update({"ok": False, "reason": f"{type(exc).__name__}:{exc}"})
    return payload


def run_mgt_cached_residual_jvp_batch_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    output_npz: Path | None = None,
    output_final_checkpoint_npz: Path | None = None,
    promote_gate_eligible: bool = False,
    top_residual_count: int = 64,
    max_rows: int = 8,
    component_filter: str = "all",
    selection_policy: str = "component_dof_round_robin",
    support_columns_per_row: int = 1,
    node_block_support: bool = True,
    max_support_columns: int = 48,
    finite_difference_epsilon_m: float = 1.0e-7,
    ridge_factor: float = 1.0e-3,
    alpha_values: tuple[float, ...] = (1.0e-6, 3.0e-7, 1.0e-7, 3.0e-8, 1.0e-8),
    allow_negative_alphas: bool = False,
    residual_tolerance_n: float = 1.0e-3,
    relative_increment_tolerance: float = 1.0e-4,
    enable_torch_rocm_lstsq: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    base_u = np.asarray(setup_meta["u0"], dtype=np.float64)
    base_started = time.perf_counter()
    stiffness, f_ext, free, residual, rhs, base_meta = assemble_residual(
        base_u,
        include_component_forces=True,
    )
    base_assembly_seconds = float(time.perf_counter() - base_started)
    component_forces = base_meta.pop("component_forces", {})
    component_breakdown = _component_breakdown(
        component_forces=component_forces if isinstance(component_forces, dict) else {},
        free=np.asarray(free, dtype=np.int64),
        residual=np.asarray(residual, dtype=np.float64),
        rhs=np.asarray(rhs, dtype=np.float64),
        top_count=int(top_residual_count),
    )
    free_idx = np.asarray(free, dtype=np.int64)
    local_row_by_global = {
        int(global_dof): int(local_row)
        for local_row, global_dof in enumerate(free_idx.tolist())
    }
    selected_rows, selected_local_rows, component_counts, dof_counts = (
        _select_block_lstsq_target_rows(
            top_rows=component_breakdown.get("top_rows", []),
            local_row_by_global=local_row_by_global,
            max_rows=int(max_rows),
            component_filter=str(component_filter),
            selection_policy=str(selection_policy),
        )
    )
    target_rows = np.asarray(selected_local_rows, dtype=np.int64)
    support_cols, support_meta = _select_support_columns(
        stiffness=stiffness,
        free=free_idx,
        target_rows=target_rows,
        support_columns_per_row=int(support_columns_per_row),
        node_block_support=bool(node_block_support),
        max_support_columns=int(max_support_columns),
    )
    cache = ResidualJvpBatchCache(
        assemble_residual=assemble_residual,
        base_u=base_u,
        base_free=free_idx,
        base_residual=np.asarray(residual, dtype=np.float64),
        reference_f_ext=np.asarray(f_ext, dtype=np.float64),
        prefer_residual_only=True,
    )
    jvp_started = time.perf_counter()
    fd_submatrix, jvp_rows, cache_summary = build_fd_jvp_submatrix(
        cache=cache,
        free=free_idx,
        target_rows=target_rows,
        support_cols=support_cols,
        epsilon=float(finite_difference_epsilon_m),
    )
    jvp_seconds = float(time.perf_counter() - jvp_started)
    base_residual_np = np.asarray(residual, dtype=np.float64)
    target_rhs = -base_residual_np[target_rows] if target_rows.size else np.asarray([], dtype=np.float64)
    candidate_rows: list[dict[str, Any]] = []
    candidate_vectors: list[np.ndarray] = []
    solve_meta: dict[str, Any] = {"evaluated": False}
    correction = np.zeros_like(base_u)
    torch_rocm_probe: dict[str, Any] = {"attempted": False}
    if fd_submatrix is not None and fd_submatrix.size and support_cols.size:
        scaled_submatrix, scaled_target_rhs, column_scales, equilibration_meta = (
            _equilibrate_lstsq_system(fd_submatrix, target_rhs, mode="row_column")
        )
        scaled_coeffs, solve_meta = _ridge_coefficients(
            scaled_submatrix,
            scaled_target_rhs,
            ridge_factor=float(ridge_factor),
        )
        solve_meta["equilibration"] = equilibration_meta
        coeffs = np.asarray(scaled_coeffs, dtype=np.float64) * np.asarray(
            column_scales,
            dtype=np.float64,
        )
        unscaled_residual_vector = np.asarray(fd_submatrix, dtype=np.float64) @ coeffs - target_rhs
        solve_meta["evaluated"] = True
        solve_meta["linear_residual_inf_n_unscaled"] = _max_abs(unscaled_residual_vector)
        solve_meta["linear_residual_l2_n_unscaled"] = (
            float(np.linalg.norm(unscaled_residual_vector))
            if unscaled_residual_vector.size
            else 0.0
        )
        for local_col, coeff in zip(support_cols.tolist(), coeffs.tolist(), strict=False):
            correction[int(free_idx[int(local_col)])] = float(coeff)
        correction_inf = _max_abs(correction)
        base_residual_inf = _max_abs(base_residual_np)
        rhs_inf = _max_abs(np.asarray(rhs, dtype=np.float64))
        max_abs_u = max(_max_abs(base_u), 1.0e-12)
        sweep_alpha_values = [float(value) for value in alpha_values]
        if allow_negative_alphas:
            sweep_alpha_values.extend(
                -float(value) for value in alpha_values if float(value) > 0.0
            )
        sweep_alpha_values = sorted(set(sweep_alpha_values), reverse=True)
        for alpha in sweep_alpha_values:
            alpha_float = float(alpha)
            candidate_u = base_u + alpha_float * correction
            trial_started = time.perf_counter()
            _k, _f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
                candidate_u,
                residual_only=True,
                free_override=free_idx,
                external_load_override=f_ext,
            )
            trial_seconds = float(time.perf_counter() - trial_started)
            free_stable = bool(
                np.asarray(trial_free, dtype=np.int64).shape == free_idx.shape
                and np.array_equal(np.asarray(trial_free, dtype=np.int64), free_idx)
            )
            residual_inf = _max_abs(np.asarray(trial_residual, dtype=np.float64))
            increment = _max_abs(candidate_u - base_u)
            max_abs_candidate = max(_max_abs(candidate_u), max_abs_u, 1.0e-12)
            metrics = _translation_metrics(candidate_u)
            candidate_rows.append(
                {
                    "alpha": alpha_float,
                    "free_dof_set_stable": free_stable,
                    "residual_only_assembly": True,
                    "assembly_seconds": trial_seconds,
                    "direct_residual_inf_n": residual_inf,
                    "direct_relative_residual_inf": residual_inf
                    / max(_max_abs(np.asarray(trial_rhs, dtype=np.float64)), rhs_inf, 1.0),
                    "improvement_inf_n": base_residual_inf - residual_inf,
                    "relative_improvement": (base_residual_inf - residual_inf)
                    / max(base_residual_inf, 1.0),
                    "relative_increment": increment / max_abs_candidate,
                    "max_increment_m": increment,
                    "max_translation_m": metrics["max_translation_m"],
                    "residual_gate_passed": residual_inf <= float(residual_tolerance_n),
                    "relative_increment_gate_passed": increment / max_abs_candidate
                    <= float(relative_increment_tolerance),
                }
            )
            candidate_vectors.append(np.asarray(candidate_u, dtype=np.float64).copy())
        if enable_torch_rocm_lstsq:
            torch_rocm_probe = _torch_rocm_lstsq_probe(
                fd_submatrix,
                target_rhs,
                ridge_lambda=float(solve_meta.get("ridge_lambda") or 0.0),
            )
    else:
        solve_meta = {
            "evaluated": False,
            "reason": "fd_jvp_submatrix_unavailable",
        }
        correction_inf = 0.0

    best_candidate = min(
        (
            (index, row)
            for index, row in enumerate(candidate_rows)
            if bool(row.get("free_dof_set_stable"))
        ),
        key=lambda item: float(item[1]["direct_residual_inf_n"]),
        default=(None, {}),
    )
    best_candidate_index, best_candidate_row = best_candidate
    best_gate_candidate = min(
        (
            (index, row)
            for index, row in enumerate(candidate_rows)
            if bool(row.get("free_dof_set_stable"))
            and bool(row.get("relative_increment_gate_passed"))
            and float(row.get("improvement_inf_n", 0.0)) > 0.0
        ),
        key=lambda item: float(item[1]["direct_residual_inf_n"]),
        default=(None, {}),
    )
    best_gate_candidate_index, best_gate_candidate_row = best_gate_candidate
    output_final_checkpoint: dict[str, Any] = {
        "written": False,
        "path": str(output_final_checkpoint_npz)
        if output_final_checkpoint_npz is not None
        else None,
        "reason": (
            "not_requested"
            if output_final_checkpoint_npz is None
            else "promote_gate_eligible_disabled"
            if not promote_gate_eligible
            else "no_gate_eligible_candidate"
        ),
    }
    if (
        promote_gate_eligible
        and output_final_checkpoint_npz is not None
        and best_gate_candidate_index is not None
    ):
        final_u = candidate_vectors[int(best_gate_candidate_index)]
        _k, _f, final_free, final_residual, final_rhs, _final_meta = assemble_residual(
            final_u,
            residual_only=True,
            free_override=free_idx,
            external_load_override=f_ext,
        )
        final_free_stable = bool(
            np.asarray(final_free, dtype=np.int64).shape == free_idx.shape
            and np.array_equal(np.asarray(final_free, dtype=np.int64), free_idx)
        )
        if final_free_stable:
            checkpoint_meta, _loaded_u, state_history, residual_history = _load_checkpoint(
                checkpoint_npz
            )
            output_final_checkpoint = _write_checkpoint(
                path=output_final_checkpoint_npz,
                source_checkpoint_npz=checkpoint_npz,
                checkpoint_meta=checkpoint_meta,
                u0=base_u,
                final_u=final_u,
                base_residual=base_residual_np,
                final_residual=np.asarray(final_residual, dtype=np.float64),
                rhs=np.asarray(final_rhs, dtype=np.float64),
                loaded_state_history=state_history,
                loaded_residual_history=residual_history,
            )
            output_final_checkpoint["written"] = True
            output_final_checkpoint["source"] = "cached_residual_jvp_best_gate_candidate"
            output_final_checkpoint["alpha"] = float(
                best_gate_candidate_row.get("alpha") or 0.0
            )
        else:
            output_final_checkpoint = {
                "written": False,
                "path": str(output_final_checkpoint_npz),
                "reason": "final_free_dof_set_changed",
            }
    if output_npz is not None and fd_submatrix is not None:
        output_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            output_npz,
            schema_version=np.asarray(SCHEMA_VERSION),
            checkpoint_npz=np.asarray(str(checkpoint_npz)),
            target_rows=target_rows,
            target_global_dofs=free_idx[target_rows] if target_rows.size else np.asarray([], dtype=np.int64),
            support_cols=support_cols,
            support_global_dofs=free_idx[support_cols] if support_cols.size else np.asarray([], dtype=np.int64),
            fd_submatrix=np.asarray(fd_submatrix, dtype=np.float64),
            target_rhs=np.asarray(target_rhs, dtype=np.float64),
            correction_u=np.asarray(correction, dtype=np.float64),
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "partial",
        "cached_residual_jvp_batch_ready": bool(fd_submatrix is not None),
        "checkpoint": str(checkpoint_npz),
        "output_npz": str(output_npz) if output_npz is not None else None,
        "output_final_checkpoint": output_final_checkpoint,
        "promoted_to_final_state": bool(output_final_checkpoint.get("written")),
        "base_direct_residual": {
            "direct_residual_inf_n": _max_abs(base_residual_np),
            "direct_relative_residual_inf": _max_abs(base_residual_np)
            / max(_max_abs(np.asarray(rhs, dtype=np.float64)), 1.0),
            "rhs_inf_n": _max_abs(np.asarray(rhs, dtype=np.float64)),
        },
        "target_selection": {
            "top_residual_count": int(top_residual_count),
            "max_rows": int(max_rows),
            "component_filter": str(component_filter),
            "selection_policy": str(selection_policy),
            "selected_hotspot_row_count": int(len(selected_rows)),
            "selected_hotspot_dominant_component_counts": component_counts,
            "selected_hotspot_dof_counts": dof_counts,
            "target_rows": [int(row) for row in target_rows.tolist()],
            "target_global_dofs": [
                int(free_idx[int(row)]) for row in target_rows.tolist()
            ],
        },
        "support": support_meta,
        "finite_difference_jvp_batch": {
            **cache_summary,
            "jvp_seconds": jvp_seconds,
            "jvp_rows": jvp_rows,
        },
        "linear_solve": solve_meta,
        "correction_inf_m": correction_inf,
        "allow_negative_alphas": bool(allow_negative_alphas),
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate_row,
        "best_gate_eligible_candidate": best_gate_candidate_row,
        "torch_rocm_lstsq_probe": torch_rocm_probe,
        "base_assembly_seconds": base_assembly_seconds,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "Cached residual-JVP batch replay only. A promoted checkpoint remains an "
            "incremental frontier advance, not full nonlinear residual closure."
        ),
        "blockers": [
            "direct_residual_gate_not_closed",
            "cached_batch_is_diagnostic_not_final_newton_closure",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--output-npz", type=Path, default=None)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument("--promote-gate-eligible", action="store_true")
    parser.add_argument("--top-residual-count", type=int, default=64)
    parser.add_argument("--max-rows", type=int, default=8)
    parser.add_argument("--component-filter", default="all")
    parser.add_argument("--selection-policy", default="component_dof_round_robin")
    parser.add_argument("--support-columns-per-row", type=int, default=1)
    parser.add_argument("--node-block-support", action="store_true")
    parser.add_argument("--max-support-columns", type=int, default=48)
    parser.add_argument("--finite-difference-epsilon-m", type=float, default=1.0e-7)
    parser.add_argument("--ridge-factor", type=float, default=1.0e-3)
    parser.add_argument("--alpha-values", default="1e-6,3e-7,1e-7,3e-8,1e-8")
    parser.add_argument("--allow-negative-alphas", action="store_true")
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--enable-torch-rocm-lstsq", action="store_true")
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help="Acknowledge this probe is diagnostic and does not close G1 by itself.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_cpu_diagnostic:
        print("cached-residual-jvp-batch: blocked diagnostic requires --allow-cpu-diagnostic")
        return 2
    payload = run_mgt_cached_residual_jvp_batch_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        output_npz=args.output_npz,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        promote_gate_eligible=bool(args.promote_gate_eligible),
        top_residual_count=args.top_residual_count,
        max_rows=args.max_rows,
        component_filter=args.component_filter,
        selection_policy=args.selection_policy,
        support_columns_per_row=args.support_columns_per_row,
        node_block_support=args.node_block_support,
        max_support_columns=args.max_support_columns,
        finite_difference_epsilon_m=args.finite_difference_epsilon_m,
        ridge_factor=args.ridge_factor,
        alpha_values=_parse_float_csv(args.alpha_values),
        allow_negative_alphas=bool(args.allow_negative_alphas),
        residual_tolerance_n=args.residual_tolerance_n,
        relative_increment_tolerance=args.relative_increment_tolerance,
        enable_torch_rocm_lstsq=bool(args.enable_torch_rocm_lstsq),
    )
    print(
        "cached-residual-jvp-batch: "
        f"ready={payload['cached_residual_jvp_batch_ready']} "
        f"promoted={payload['promoted_to_final_state']} "
        f"base={payload['base_direct_residual']['direct_residual_inf_n']} "
        f"best={payload['best_candidate'].get('direct_residual_inf_n')} "
        f"runtime={payload['runtime_seconds']:.3f}s -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
