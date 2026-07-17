#!/usr/bin/env python3
"""Probe active-set displacement plus load-parameter continuation directions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy.optimize import linprog

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_g1_active_set_ls_trust_candidate import _top_free_rows  # noqa: E402
from run_g1_active_set_minimax_trust_candidate import (  # noqa: E402
    _support_columns_for_active_rows,
)
from run_g1_mgt_physical_line_search_smoke import (  # noqa: E402
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)
from run_g1_true_newton_reference_candidate import _max_abs  # noqa: E402


SCHEMA_VERSION = "g1-active-set-load-parameter-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_INITIAL_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_active_set_load_parameter_probe.json"
DEFAULT_ACTIVE_ROW_COUNTS = (8, 16, 32)
DEFAULT_ALPHA_VALUES = (1.0, 0.5, 0.25)
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")


def _load_checkpoint_free_state(
    *,
    checkpoint_npz: Path,
    free: np.ndarray,
    dof_count: int,
) -> dict[str, Any]:
    with np.load(checkpoint_npz, allow_pickle=False) as archive:
        displacement = np.asarray(archive["displacement_u"], dtype=np.float64)
        schema = str(np.asarray(archive["checkpoint_schema"]).item())
        load_scale = float(np.asarray(archive["load_scale"]).item())
        direct_residual = float(
            np.asarray(
                archive[
                    "direct_residual_inf_n"
                    if "direct_residual_inf_n" in archive.files
                    else "residual_inf_n"
                ]
            ).item()
        )
    if int(displacement.size) != int(dof_count):
        raise ValueError(
            f"checkpoint dof_count {displacement.size} does not match {dof_count}"
        )
    free_idx = np.asarray(free, dtype=np.int64)
    return {
        "schema": schema,
        "load_scale": load_scale,
        "direct_residual_inf_n": direct_residual,
        "full_displacement": displacement.copy(),
        "free_state": displacement[free_idx].copy(),
    }


def _annotate_rows(
    rows: np.ndarray,
    *,
    values: np.ndarray,
    free: np.ndarray,
    node_id: np.ndarray | None,
    dof_per_node: int,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    free_np = np.asarray(free, dtype=np.int64)
    node_ids = np.asarray(node_id, dtype=np.int64) if node_id is not None else None
    for row in np.asarray(rows, dtype=np.int64).tolist():
        global_dof = int(free_np[int(row)])
        node_index = global_dof // int(dof_per_node)
        local_dof_index = global_dof % int(dof_per_node)
        item: dict[str, Any] = {
            "reduced_index": int(row),
            "value": float(values[int(row)]),
            "abs": float(abs(values[int(row)])),
            "global_dof": global_dof,
            "node_index": int(node_index),
            "local_dof_index": int(local_dof_index),
            "dof_label": (
                DOF_LABELS[local_dof_index]
                if 0 <= local_dof_index < len(DOF_LABELS)
                else f"DOF{local_dof_index}"
            ),
        }
        if node_ids is not None and 0 <= node_index < int(node_ids.size):
            item["node_id"] = int(node_ids[node_index])
        annotated.append(item)
    return annotated


def active_set_load_parameter_direction(
    *,
    k_free: Any,
    residual: np.ndarray,
    load_derivative: np.ndarray,
    active_rows: np.ndarray,
    displacement_trust_radius_m: float,
    load_trust_radius: float,
    support_strongest_per_row: int,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    active_rows = np.asarray(active_rows, dtype=np.int64)
    support_cols = _support_columns_for_active_rows(
        k_ff=k_free,
        active_rows=active_rows,
        strongest_per_row=int(support_strongest_per_row),
    )
    active_matrix = k_free[active_rows, :][:, support_cols].toarray()
    active_residual = np.asarray(residual, dtype=np.float64)[active_rows]
    active_load_derivative = np.asarray(load_derivative, dtype=np.float64)[active_rows]
    row_count, col_count = active_matrix.shape
    if row_count <= 0 or col_count <= 0:
        raise ValueError("empty_active_set_load_parameter_matrix")
    # Variables: selected displacement corrections, delta_lambda, t.
    c = np.zeros(col_count + 2, dtype=np.float64)
    c[-1] = 1.0
    load_col = active_load_derivative.reshape((-1, 1))
    a_linear = np.hstack([active_matrix, load_col])
    a_ub = np.vstack(
        [
            np.hstack([a_linear, -np.ones((row_count, 1), dtype=np.float64)]),
            np.hstack([-a_linear, -np.ones((row_count, 1), dtype=np.float64)]),
        ]
    )
    b_ub = np.concatenate([-active_residual, active_residual])
    bounds = [
        (-float(displacement_trust_radius_m), float(displacement_trust_radius_m))
        for _ in range(col_count)
    ]
    bounds.append((-float(load_trust_radius), float(load_trust_radius)))
    bounds.append((0.0, None))
    solve_result = linprog(
        c,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
    )
    if not solve_result.success:
        raise ValueError(f"linprog_failed:{solve_result.status}:{solve_result.message}")
    local_direction = np.asarray(solve_result.x[:col_count], dtype=np.float64)
    delta_lambda = float(solve_result.x[col_count])
    direction_free = np.zeros(int(np.asarray(residual).size), dtype=np.float64)
    direction_free[support_cols] = local_direction
    active_linear_residual = (
        active_matrix @ local_direction
        + active_load_derivative * delta_lambda
        + active_residual
    )
    return (
        direction_free,
        delta_lambda,
        {
            "active_row_count": int(active_rows.size),
            "support_column_count": int(support_cols.size),
            "support_strongest_per_row": int(support_strongest_per_row),
            "displacement_trust_radius_m": float(displacement_trust_radius_m),
            "load_trust_radius": float(load_trust_radius),
            "direction_inf_m": _max_abs(direction_free),
            "delta_load_scale": delta_lambda,
            "active_linear_residual_inf_n": _max_abs(active_linear_residual),
            "active_linear_improvement_inf_n": _max_abs(active_residual)
            - _max_abs(active_linear_residual),
            "active_load_derivative_inf_n_per_load": _max_abs(active_load_derivative),
            "solver": "scipy_linprog_highs_active_set_displacement_plus_load_parameter",
            "solver_stats": {
                "status": int(solve_result.status),
                "message": str(solve_result.message),
                "nit": int(getattr(solve_result, "nit", 0) or 0),
                "objective": float(solve_result.fun),
            },
        },
    )


def _parse_int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in value.split(",") if item.strip())


def _parse_float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in value.split(",") if item.strip())


def run_g1_active_set_load_parameter_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    checkpoint_npz: Path = DEFAULT_INITIAL_CHECKPOINT_NPZ,
    load_scale: float = 1.0,
    load_derivative_eps: float = 1.0e-3,
    frame_tangent_source: str = "force_based_residual_tangent",
    active_row_counts: tuple[int, ...] = DEFAULT_ACTIVE_ROW_COUNTS,
    support_strongest_per_row: int = 32,
    displacement_trust_radius_m: float = 1.0e-8,
    load_trust_radius: float = 0.02,
    alpha_values: tuple[float, ...] = DEFAULT_ALPHA_VALUES,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    load_scale = float(load_scale)
    eps = float(load_derivative_eps)
    residual_fn, _x0, meta = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=load_scale,
        frame_tangent_source=frame_tangent_source,
    )
    residual_plus_fn, _xp, meta_plus = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=load_scale + eps,
        frame_tangent_source=frame_tangent_source,
    )
    residual_minus_fn, _xm, meta_minus = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=load_scale - eps,
        frame_tangent_source=frame_tangent_source,
    )
    free = np.asarray(meta["free"], dtype=np.int64)
    free_plus = np.asarray(meta_plus["free"], dtype=np.int64)
    free_minus = np.asarray(meta_minus["free"], dtype=np.int64)
    free_maps_match = bool(
        free.shape == free_plus.shape
        and np.array_equal(free, free_plus)
        and free.shape == free_minus.shape
        and np.array_equal(free, free_minus)
    )
    if not free_maps_match:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "reason_code": "load_derivative_free_dof_map_changed",
            "promotes_g1_closure": False,
            "load_scale": load_scale,
            "load_derivative_eps": eps,
            "claim_boundary": "Load-parameter probe only; no G1 closure.",
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        return payload
    checkpoint = _load_checkpoint_free_state(
        checkpoint_npz=Path(checkpoint_npz),
        free=free,
        dof_count=int(meta["dof_count"]),
    )
    x = np.asarray(checkpoint["free_state"], dtype=np.float64)
    residual = np.asarray(residual_fn(x), dtype=np.float64)
    residual_plus = np.asarray(residual_plus_fn(x), dtype=np.float64)
    residual_minus = np.asarray(residual_minus_fn(x), dtype=np.float64)
    load_derivative = (residual_plus - residual_minus) / (2.0 * eps)
    k_state, _rebuild_meta = meta["tangent_rebuild_fn"](x)

    attempts: list[dict[str, Any]] = []
    best_attempt: dict[str, Any] | None = None
    best_direction: np.ndarray | None = None
    best_delta_load = 0.0
    for count in active_row_counts:
        active_rows = _top_free_rows(residual, int(count))
        try:
            direction, delta_load, direction_meta = active_set_load_parameter_direction(
                k_free=k_state,
                residual=residual,
                load_derivative=load_derivative,
                active_rows=active_rows,
                displacement_trust_radius_m=displacement_trust_radius_m,
                load_trust_radius=load_trust_radius,
                support_strongest_per_row=support_strongest_per_row,
            )
        except Exception as exc:  # noqa: BLE001
            attempts.append(
                {
                    "active_row_count": int(count),
                    "status": "blocked",
                    "reason_code": f"{type(exc).__name__}:{exc}",
                }
            )
            continue
        attempt = {
            "active_row_count": int(count),
            "status": "ready",
            "active_rows": _annotate_rows(
                active_rows,
                values=residual,
                free=free,
                node_id=np.asarray(meta.get("node_id"), dtype=np.int64),
                dof_per_node=int(meta.get("dof_per_node") or 6),
            ),
            "direction": direction_meta,
        }
        attempts.append(attempt)
        if (
            best_attempt is None
            or direction_meta["active_linear_residual_inf_n"]
            < best_attempt["direction"]["active_linear_residual_inf_n"]
        ):
            best_attempt = attempt
            best_direction = direction
            best_delta_load = delta_load

    replay_rows: list[dict[str, Any]] = []
    restored_full_load_rows: list[dict[str, Any]] = []
    if best_direction is not None and best_attempt is not None:
        for alpha in alpha_values:
            alpha_float = float(alpha)
            trial_load = load_scale + alpha_float * best_delta_load
            trial_x = x + alpha_float * np.asarray(best_direction, dtype=np.float64)
            restored_residual = np.asarray(residual_fn(trial_x), dtype=np.float64)
            restored_inf = _max_abs(restored_residual)
            restored_full_load_rows.append(
                {
                    "alpha": alpha_float,
                    "load_scale": load_scale,
                    "delta_load_scale": 0.0,
                    "direct_residual_inf_n": restored_inf,
                    "improvement_inf_n": _max_abs(residual) - restored_inf,
                    "residual_gate_passed": restored_inf <= 5.0e-4,
                    "status": "ready",
                    "claim_boundary": (
                        "Restores the continuation displacement to the original "
                        "full-load residual; this is the relevant full-load check."
                    ),
                }
            )
            if trial_load <= 0.0:
                replay_rows.append(
                    {
                        "alpha": alpha_float,
                        "load_scale": trial_load,
                        "status": "blocked",
                        "reason_code": "nonpositive_trial_load_scale",
                    }
                )
                continue
            trial_fn, _xt, trial_meta = build_mgt_physical_residual_closure(
                mgt_path=Path(mgt_model),
                roundtrip_npz=None,
                load_scale=trial_load,
                frame_tangent_source=frame_tangent_source,
            )
            trial_free = np.asarray(trial_meta["free"], dtype=np.int64)
            stable = bool(
                trial_free.shape == free.shape and np.array_equal(trial_free, free)
            )
            if not stable:
                replay_rows.append(
                    {
                        "alpha": alpha_float,
                        "load_scale": trial_load,
                        "status": "blocked",
                        "reason_code": "trial_free_dof_map_changed",
                    }
                )
                continue
            trial_residual = np.asarray(trial_fn(trial_x), dtype=np.float64)
            trial_inf = _max_abs(trial_residual)
            replay_rows.append(
                {
                    "alpha": alpha_float,
                    "load_scale": trial_load,
                    "delta_load_scale": alpha_float * best_delta_load,
                    "free_dof_set_stable": stable,
                    "direct_residual_inf_n": trial_inf,
                    "improvement_inf_n": _max_abs(residual) - trial_inf,
                    "residual_gate_passed": trial_inf <= 5.0e-4,
                    "status": "ready",
                }
            )

    best_replay = min(
        [row for row in replay_rows if row.get("status") == "ready"],
        key=lambda row: float(row.get("direct_residual_inf_n", float("inf"))),
        default={},
    )
    best_restored = min(
        [row for row in restored_full_load_rows if row.get("status") == "ready"],
        key=lambda row: float(row.get("direct_residual_inf_n", float("inf"))),
        default={},
    )
    initial_inf = _max_abs(residual)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "is_candidate_only": True,
        "promotes_g1_closure": False,
        "mgt_model": str(mgt_model),
        "checkpoint_npz": str(checkpoint_npz),
        "load_scale": load_scale,
        "frame_tangent_source": frame_tangent_source,
        "load_derivative_eps": eps,
        "displacement_trust_radius_m": float(displacement_trust_radius_m),
        "load_trust_radius": float(load_trust_radius),
        "checkpoint": {
            key: value
            for key, value in checkpoint.items()
            if key not in {"free_state", "full_displacement"}
        },
        "summary": {
            "initial_residual_inf_n": initial_inf,
            "load_derivative_inf_n_per_load": _max_abs(load_derivative),
            "active_row_count_schedule": [int(value) for value in active_row_counts],
            "ready_attempt_count": sum(
                1 for row in attempts if row.get("status") == "ready"
            ),
            "best_linear_active_row_count": (
                best_attempt.get("active_row_count") if best_attempt else None
            ),
            "best_linear_active_residual_inf_n": (
                best_attempt["direction"]["active_linear_residual_inf_n"]
                if best_attempt
                else None
            ),
            "best_linear_active_improvement_inf_n": (
                best_attempt["direction"]["active_linear_improvement_inf_n"]
                if best_attempt
                else None
            ),
            "best_linear_delta_load_scale": best_delta_load if best_attempt else None,
            "best_linear_direction_inf_m": (
                best_attempt["direction"]["direction_inf_m"] if best_attempt else None
            ),
            "actual_replay_attempted": bool(replay_rows),
            "actual_replay_descent_observed": any(
                float(row.get("improvement_inf_n") or 0.0) > 0.0
                for row in replay_rows
                if row.get("status") == "ready"
            ),
            "best_actual_replay_load_scale": best_replay.get("load_scale"),
            "best_actual_replay_residual_inf_n": best_replay.get(
                "direct_residual_inf_n"
            ),
            "best_actual_replay_improvement_inf_n": best_replay.get(
                "improvement_inf_n"
            ),
            "best_actual_replay_residual_gate_passed": (
                best_replay.get("residual_gate_passed") is True
            ),
            "restored_full_load_replay_attempted": bool(restored_full_load_rows),
            "restored_full_load_descent_observed": any(
                float(row.get("improvement_inf_n") or 0.0) > 0.0
                for row in restored_full_load_rows
                if row.get("status") == "ready"
            ),
            "best_restored_full_load_residual_inf_n": best_restored.get(
                "direct_residual_inf_n"
            ),
            "best_restored_full_load_improvement_inf_n": best_restored.get(
                "improvement_inf_n"
            ),
            "best_restored_full_load_residual_gate_passed": (
                best_restored.get("residual_gate_passed") is True
            ),
        },
        "attempts": attempts,
        "actual_replay_rows": replay_rows,
        "restored_full_load_replay_rows": restored_full_load_rows,
        "claim_boundary": (
            "Active-set load-parameter continuation probe only. Any residual "
            "descent at load_scale != 1.0 is routing evidence for arc-length/"
            "continuation design and does not close G1 full-load equilibrium."
        ),
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument(
        "--checkpoint-npz", type=Path, default=DEFAULT_INITIAL_CHECKPOINT_NPZ
    )
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument("--load-derivative-eps", type=float, default=1.0e-3)
    parser.add_argument(
        "--frame-tangent-source", default="force_based_residual_tangent"
    )
    parser.add_argument(
        "--active-row-counts",
        default=",".join(str(value) for value in DEFAULT_ACTIVE_ROW_COUNTS),
    )
    parser.add_argument("--support-strongest-per-row", type=int, default=32)
    parser.add_argument("--displacement-trust-radius-m", type=float, default=1.0e-8)
    parser.add_argument("--load-trust-radius", type=float, default=0.02)
    parser.add_argument(
        "--alpha-values",
        default=",".join(str(value) for value in DEFAULT_ALPHA_VALUES),
    )
    parser.add_argument(
        "--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_g1_active_set_load_parameter_probe(
        mgt_model=args.mgt_model,
        checkpoint_npz=args.checkpoint_npz,
        load_scale=args.load_scale,
        load_derivative_eps=args.load_derivative_eps,
        frame_tangent_source=args.frame_tangent_source,
        active_row_counts=_parse_int_tuple(args.active_row_counts),
        support_strongest_per_row=args.support_strongest_per_row,
        displacement_trust_radius_m=args.displacement_trust_radius_m,
        load_trust_radius=args.load_trust_radius,
        alpha_values=_parse_float_tuple(args.alpha_values),
        output_json=args.output_json,
    )
    summary = payload.get("summary", {})
    print(
        "g1-active-set-load-parameter-probe: "
        f"status={payload['status']} "
        f"linear_delta_load={summary.get('best_linear_delta_load_scale')} "
        f"actual_descent={summary.get('actual_replay_descent_observed')} "
        f"best_actual_residual={summary.get('best_actual_replay_residual_inf_n')} "
        f"best_actual_load={summary.get('best_actual_replay_load_scale')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
