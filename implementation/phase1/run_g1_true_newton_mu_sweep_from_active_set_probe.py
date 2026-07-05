#!/usr/bin/env python3
"""Sweep true-Newton regularization mu from the active-set G1 frontier."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
)
from g1_regularized_direction import regularize_matrix
from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-true-newton-mu-sweep-from-active-set-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_INITIAL_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_true_newton_from_active_set_mu_sweep_probe.json"
DEFAULT_MU_VALUES = (0.1, 0.03, 0.01, 0.003, 0.001, 0.0003, 0.0001)
EXTENDED_ALPHAS = tuple(
    list(DEFAULT_ALPHAS)
    + [
        6.103515625e-05,
        3.0517578125e-05,
        1.52587890625e-05,
        7.62939453125e-06,
        3.814697265625e-06,
        1.9073486328125e-06,
        9.5367431640625e-07,
    ]
)
ResidualFn = Callable[[np.ndarray], np.ndarray]


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


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
        "free_state": displacement[free_idx].copy(),
    }


def _best_trial(line_search: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in line_search.get("alpha_rows", [])
        if isinstance(row, dict) and row.get("finite") is True
    ]
    if not rows:
        return {}
    return min(rows, key=lambda row: float(row.get("residual_inf_n", float("inf"))))


def _line_search_summary(line_search: dict[str, Any], residual_before: float) -> dict[str, Any]:
    best = _best_trial(line_search)
    best_residual = (
        float(best.get("residual_inf_n"))
        if best.get("residual_inf_n") is not None
        else None
    )
    return {
        "status": str(line_search.get("status") or ""),
        "reason_code": str(line_search.get("reason_code") or ""),
        "accepted_alpha": line_search.get("accepted_alpha"),
        "descent_found": line_search.get("status") == "ready",
        "best_alpha": best.get("alpha"),
        "best_residual_inf_n": best_residual,
        "best_improvement_inf_n": (
            float(residual_before - best_residual)
            if best_residual is not None
            else None
        ),
        "best_reduction_ratio": (
            float((residual_before - best_residual) / max(residual_before, 1.0e-30))
            if best_residual is not None
            else None
        ),
        "best_trial": best,
        "alpha_row_count": len(line_search.get("alpha_rows", [])),
    }


def true_newton_mu_sweep_summary(
    *,
    residual_fn: ResidualFn,
    x: np.ndarray,
    k_state: Any,
    mu_values: Iterable[float] = DEFAULT_MU_VALUES,
    regularization_mode: str = "relative_diagonal_shift",
    alphas: tuple[float, ...] = EXTENDED_ALPHAS,
) -> dict[str, Any]:
    x_np = np.asarray(x, dtype=np.float64)
    residual = np.asarray(residual_fn(x_np), dtype=np.float64)
    residual_inf = _max_abs(residual)
    rows: list[dict[str, Any]] = []
    for mu in mu_values:
        mu_float = float(mu)
        k_reg, effective_shift, scale_source = regularize_matrix(
            k_state,
            regularization_mode,
            mu_float,
        )
        row: dict[str, Any] = {
            "regularization_mu": mu_float,
            "regularization_mode": regularization_mode,
            "effective_shift": float(effective_shift),
            "scale_source": str(scale_source),
        }
        try:
            factor = splu(csc_matrix(k_reg))
            direction = np.asarray(factor.solve(-residual), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    **row,
                    "factorization_passed": False,
                    "reason_code": f"solve_error:{type(exc).__name__}",
                }
            )
            continue
        if not bool(np.all(np.isfinite(direction))):
            rows.append(
                {
                    **row,
                    "factorization_passed": True,
                    "finite_direction": False,
                    "reason_code": "nonfinite_direction",
                }
            )
            continue
        k_action = np.asarray(k_state @ direction, dtype=np.float64)
        kreg_action = np.asarray(k_reg @ direction, dtype=np.float64)
        regularized_solve_residual = kreg_action + residual
        unregularized_linearized_residual = k_action + residual
        regularization_action = kreg_action - k_action
        forward = physical_residual_backtracking_line_search(
            residual_fn,
            x_np,
            direction,
            jvp_action=k_action,
            alphas=alphas,
        )
        reverse = physical_residual_backtracking_line_search(
            residual_fn,
            x_np,
            -direction,
            jvp_action=-k_action,
            alphas=alphas,
        )
        forward_summary = _line_search_summary(forward, residual_inf)
        reverse_summary = _line_search_summary(reverse, residual_inf)
        candidates = [
            ("forward", forward_summary),
            ("reverse", reverse_summary),
        ]
        best_sign, best_summary = min(
            candidates,
            key=lambda item: float(
                item[1].get("best_residual_inf_n")
                if item[1].get("best_residual_inf_n") is not None
                else float("inf")
            ),
        )
        best_residual = best_summary.get("best_residual_inf_n")
        rows.append(
            {
                **row,
                "factorization_passed": True,
                "finite_direction": True,
                "reason_code": "ok",
                "direction_inf_m": _max_abs(direction),
                "direction_l2_m": float(np.linalg.norm(direction)),
                "regularized_linear_solve_relative_inf": (
                    _max_abs(regularized_solve_residual) / max(residual_inf, 1.0)
                ),
                "unregularized_tangent_plus_residual_relative_inf": (
                    _max_abs(unregularized_linearized_residual)
                    / max(residual_inf, 1.0)
                ),
                "regularization_action_vs_residual_inf": (
                    _max_abs(regularization_action) / max(residual_inf, 1.0)
                ),
                "forward_line_search": forward_summary,
                "reverse_line_search": reverse_summary,
                "best_direction_sign": best_sign,
                "best_residual_inf_n": best_residual,
                "best_improvement_inf_n": (
                    float(residual_inf - best_residual)
                    if best_residual is not None
                    else None
                ),
                "best_reduction_ratio": (
                    float((residual_inf - best_residual) / max(residual_inf, 1.0e-30))
                    if best_residual is not None
                    else None
                ),
                "descent_found": bool(
                    forward_summary["descent_found"]
                    or reverse_summary["descent_found"]
                ),
            }
        )
    factorable = [row for row in rows if row.get("factorization_passed") is True]
    best_row = min(
        factorable,
        key=lambda row: float(
            row.get("best_residual_inf_n")
            if row.get("best_residual_inf_n") is not None
            else float("inf")
        ),
        default={},
    )
    return {
        "initial_residual_inf_n": residual_inf,
        "evaluated_mu_count": len(rows),
        "factorable_mu_count": len(factorable),
        "descent_observed": any(row.get("descent_found") is True for row in rows),
        "best_mu": best_row.get("regularization_mu"),
        "best_effective_shift": best_row.get("effective_shift"),
        "best_direction_sign": best_row.get("best_direction_sign"),
        "best_residual_inf_n": best_row.get("best_residual_inf_n"),
        "best_improvement_inf_n": best_row.get("best_improvement_inf_n"),
        "best_reduction_ratio": best_row.get("best_reduction_ratio"),
        "best_direction_inf_m": best_row.get("direction_inf_m"),
        "best_unregularized_tangent_plus_residual_relative_inf": (
            best_row.get("unregularized_tangent_plus_residual_relative_inf")
        ),
        "best_regularization_action_vs_residual_inf": (
            best_row.get("regularization_action_vs_residual_inf")
        ),
        "mu_rows": rows,
    }


def run_g1_true_newton_mu_sweep_from_active_set_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    checkpoint_npz: Path = DEFAULT_INITIAL_CHECKPOINT_NPZ,
    load_scale: float = 1.0,
    frame_tangent_source: str = "force_based_residual_tangent",
    regularization_mode: str = "relative_diagonal_shift",
    mu_values: tuple[float, ...] = DEFAULT_MU_VALUES,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    residual_fn, _x0, meta = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=float(load_scale),
        frame_tangent_source=frame_tangent_source,
    )
    free = np.asarray(meta["free"], dtype=np.int64)
    checkpoint = _load_checkpoint_free_state(
        checkpoint_npz=Path(checkpoint_npz),
        free=free,
        dof_count=int(meta["dof_count"]),
    )
    x = np.asarray(checkpoint["free_state"], dtype=np.float64)
    k_state, _rebuild_meta = meta["tangent_rebuild_fn"](x)
    summary = true_newton_mu_sweep_summary(
        residual_fn=residual_fn,
        x=x,
        k_state=k_state,
        mu_values=mu_values,
        regularization_mode=regularization_mode,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "is_candidate_only": True,
        "promotes_g1_closure": False,
        "mgt_model": str(mgt_model),
        "checkpoint_npz": str(checkpoint_npz),
        "load_scale": float(load_scale),
        "frame_tangent_source": frame_tangent_source,
        "regularization_mode": regularization_mode,
        "mu_values": [float(value) for value in mu_values],
        "checkpoint": {
            key: value for key, value in checkpoint.items() if key != "free_state"
        },
        "summary": summary,
        "claim_boundary": (
            "Regularization mu sweep from the active-set frontier only. This "
            "checks whether lowering the diagonal shift yields physical residual "
            "descent; it does not create a full-load checkpoint or promote G1 closure."
        ),
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def _parse_mu_values(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in value.split(",") if item.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_INITIAL_CHECKPOINT_NPZ)
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument("--frame-tangent-source", default="force_based_residual_tangent")
    parser.add_argument("--regularization-mode", default="relative_diagonal_shift")
    parser.add_argument(
        "--mu-values",
        default=",".join(str(value) for value in DEFAULT_MU_VALUES),
    )
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_g1_true_newton_mu_sweep_from_active_set_probe(
        mgt_model=args.mgt_model,
        checkpoint_npz=args.checkpoint_npz,
        load_scale=args.load_scale,
        frame_tangent_source=args.frame_tangent_source,
        regularization_mode=args.regularization_mode,
        mu_values=_parse_mu_values(args.mu_values),
        output_json=args.output_json,
    )
    summary = payload["summary"]
    print(
        "g1-true-newton-mu-sweep-from-active-set-probe: "
        f"status={payload['status']} "
        f"descent={summary['descent_observed']} "
        f"best_mu={summary['best_mu']} "
        f"best_residual={summary['best_residual_inf_n']} "
        f"best_improvement={summary['best_improvement_inf_n']} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
