#!/usr/bin/env python3
"""Non-promoting regularized reference Newton candidate (F2g).

F2f showed that, at the real MGT reference state (load_scale=0.1, real per-element
service tangent), a moderate relative-diagonal regularization (mu=0.1) makes the
consistent assembled tangent factorable and yields a full-step (alpha=1.0), ~87%
residual-reduction physical-residual descent direction.

F2g asks the next question: does a regularized physical-consistent Newton iterate
reduce the physical residual *over multiple steps* (convergence), not just once?

This is a candidate runner, not a fix and not a closure: no production solver path
change, no 0.656 continuation regeneration, no G1 promotion. Output is an untracked
``*.local.json``. It uses a modified-Newton scheme (the regularized reference
tangent is factorized once and reused; the physical residual is re-evaluated each
step), which directly probes whether the reference operator drives convergence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from g1_global_newton_operator import physical_consistent_jvp
from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
)
from g1_regularized_direction import PRODUCTION_LAMBDA, regularize_matrix
from run_g1_mgt_physical_line_search_smoke import (
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-regularized-reference-newton-candidate.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_regularized_reference_newton_candidate.local.json"

DirectionFn = Callable[[np.ndarray, np.ndarray], "tuple[np.ndarray | None, dict[str, Any]]"]
ResidualFn = Callable[[np.ndarray], np.ndarray]

STOP_MAX_STEPS = "max_steps"
STOP_GATE = "residual_gate_passed"
STOP_NO_DESCENT = "line_search_no_descent"
STOP_SOLVE_FAILED = "solve_failed"
STOP_NAN = "fail_closed_nan"
STOP_STALLED = "stalled_min_reduction"
STOP_PARITY_FAILED = "parity_failed"


def _inf_norm(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.max(np.abs(x))) if x.size else 0.0


def _finite(x: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(x, dtype=np.float64))))


def run_multistep_newton(
    residual_fn: ResidualFn,
    x0: np.ndarray,
    direction_fn: DirectionFn,
    *,
    max_newton_steps: int = 8,
    residual_gate_n: float = 5.0e-4,
    min_reduction_per_step: float = 1.0e-6,
    alphas: tuple[float, ...] = DEFAULT_ALPHAS,
) -> dict[str, Any]:
    """Testable multi-step Newton loop on a physical residual with line-search.

    ``direction_fn(x, r)`` returns ``(p, meta)`` (p=None on solve failure).
    """
    x = np.asarray(x0, dtype=np.float64).copy()
    r = np.asarray(residual_fn(x), dtype=np.float64)
    if not _finite(r):
        return {"newton_history": [],
                "summary": {"initial_residual_n": None, "final_residual_n": None,
                            "total_reduction_ratio": None, "monotonic_residual_decrease": False,
                            "residual_gate_passed": False, "stop_reason": STOP_NAN}}
    initial = _inf_norm(r)
    history: list[dict[str, Any]] = []
    monotonic = True
    stop_reason = STOP_MAX_STEPS
    for it in range(int(max_newton_steps)):
        r = np.asarray(residual_fn(x), dtype=np.float64)
        if not _finite(r):
            stop_reason = STOP_NAN
            break
        rb = _inf_norm(r)
        if rb <= residual_gate_n:
            stop_reason = STOP_GATE
            break
        p, meta = direction_fn(x, r)
        if p is None or not _finite(p):
            history.append({"iteration": it, "residual_before_n": rb,
                            "direction_solve_status": "blocked",
                            "reason_code": (meta or {}).get("reason_code", "solve_failed"),
                            "accepted_alpha": None})
            stop_reason = (meta or {}).get("solve_stop_reason", STOP_SOLVE_FAILED)
            break
        jvp_action = physical_consistent_jvp(residual_fn, x, p)
        ls = physical_residual_backtracking_line_search(
            residual_fn, x, p, jvp_action=jvp_action, alphas=alphas,
        )
        if ls.get("status") != "ready":
            history.append({"iteration": it, "residual_before_n": rb,
                            "direction_solve_status": "ready",
                            "line_search_status": ls.get("status"), "accepted_alpha": None})
            stop_reason = STOP_NO_DESCENT
            break
        alpha = float(ls["accepted_alpha"])
        ra = float(ls["residual_after_n"])
        reduction = (rb - ra) / max(rb, 1.0e-30)
        row = {"iteration": it, "residual_before_n": rb,
               "direction_solve_status": "ready", "accepted_alpha": alpha,
               "residual_after_n": ra, "residual_reduction_ratio": reduction,
               "line_search_status": "ready"}
        for key in ("tangent_rebuilt", "assembled_tangent_parity_pass"):
            if meta and key in meta:
                row[key] = meta[key]
        history.append(row)
        if ra > rb:
            monotonic = False
        x = x + alpha * p
        if reduction < min_reduction_per_step:
            stop_reason = STOP_STALLED
            break
    final_r = np.asarray(residual_fn(x), dtype=np.float64)
    final = _inf_norm(final_r) if _finite(final_r) else None
    summary = {
        "initial_residual_n": initial,
        "final_residual_n": final,
        "total_reduction_ratio": ((initial - final) / max(initial, 1.0e-30)) if final is not None else None,
        "monotonic_residual_decrease": bool(monotonic),
        "residual_gate_passed": bool(final is not None and final <= residual_gate_n),
        "stop_reason": stop_reason,
        "steps_taken": len(history),
    }
    return {"newton_history": history, "summary": summary}


def run_g1_regularized_reference_newton_candidate(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_service_tangent_source: str = "real_per_element",
    regularization_mode: str = "relative_diagonal_shift",
    regularization_mu: float = 0.1,
    max_newton_steps: int = 8,
    residual_gate_n: float = 5.0e-4,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    mgt_model = Path(mgt_model)

    def _base() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_candidate_only": True,
            "promotes_g1_closure": False,
            "load_scale": load_scale,
            "frame_service_tangent_source": frame_service_tangent_source,
            "regularization": {
                "mode": regularization_mode, "mu": regularization_mu, "selected_from_f2f": True,
            },
            "production_lambda": PRODUCTION_LAMBDA,
            "claim_boundary": "non_promoting_regularized_reference_newton_candidate_only",
        }

    if not mgt_model.is_file():
        payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_INPUT_MISSING,
                   "uses_real_mgt_model": False, "mgt_source": str(mgt_model),
                   "newton_history": [], "summary": {"stop_reason": "mgt_input_missing"}}
    else:
        try:
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
                frame_service_tangent_source=frame_service_tangent_source,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                       "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                       "detail": f"{type(exc).__name__}:{exc}",
                       "newton_history": [], "summary": {"stop_reason": "state_build_failed"}}
        else:
            k_free = meta["tangent_free_csr"]
            k_reg, eff_shift, scale_source = regularize_matrix(k_free, regularization_mode, regularization_mu)
            try:
                factor = splu(csc_matrix(k_reg))
            except Exception as exc:  # noqa: BLE001
                payload = {**_base(), "status": "blocked", "reason_code": "ERR_REGULARIZED_FACTOR_FAILED",
                           "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                           "detail": str(exc)[:160], "newton_history": [],
                           "summary": {"stop_reason": "solve_failed"}}
            else:
                def direction_fn(x: np.ndarray, r: np.ndarray):
                    try:
                        p = np.asarray(factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
                    except Exception as exc:  # noqa: BLE001
                        return None, {"reason_code": f"solve_error:{type(exc).__name__}"}
                    return p, {"reason_code": "ok", "modified_newton_reused_factor": True}

                result = run_multistep_newton(
                    residual_fn, x0, direction_fn,
                    max_newton_steps=max_newton_steps, residual_gate_n=residual_gate_n,
                )
                summary = result["summary"]
                status = "ready" if summary["stop_reason"] in {STOP_GATE, STOP_MAX_STEPS, STOP_STALLED} else "review"
                payload = {
                    **_base(),
                    "status": status,
                    "reason_code": summary["stop_reason"],
                    "uses_real_mgt_model": True,
                    "mgt_source": str(mgt_model),
                    "regularization": {
                        "mode": regularization_mode, "mu": regularization_mu,
                        "effective_shift": eff_shift, "scale_source": scale_source,
                        "selected_from_f2f": True,
                        "effective_shift_vs_production_515_ratio": (
                            eff_shift / PRODUCTION_LAMBDA if PRODUCTION_LAMBDA else None),
                    },
                    "newton_history": result["newton_history"],
                    "summary": summary,
                    "resource_usage": {
                        "dof_count": meta["dof_count"], "free_dof_count": meta["free_dof_count"],
                        "element_count": meta["element_count"],
                    },
                }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"], default="real_per_element",
    )
    parser.add_argument("--regularization-mode", default="relative_diagonal_shift")
    parser.add_argument("--regularization-mu", type=float, default=0.1)
    parser.add_argument("--direction-solver", default="sparse_direct_spsolve")  # interface parity
    parser.add_argument("--max-newton-steps", type=int, default=8)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_regularized_reference_newton_candidate(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        regularization_mode=args.regularization_mode, regularization_mu=args.regularization_mu,
        max_newton_steps=args.max_newton_steps, residual_gate_n=args.residual_gate_n,
        output_json=args.output_json,
    )
    s = payload.get("summary", {})
    print(
        "g1-regularized-reference-newton-candidate: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"steps={s.get('steps_taken')} init={s.get('initial_residual_n')} final={s.get('final_residual_n')} "
        f"total_reduction={s.get('total_reduction_ratio')} monotonic={s.get('monotonic_residual_decrease')} "
        f"gate={s.get('residual_gate_passed')} -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
