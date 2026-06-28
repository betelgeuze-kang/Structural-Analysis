#!/usr/bin/env python3
"""Non-promoting adaptive-regularization reference Newton candidate (F2g-3).

F2g-2 showed that, at the real MGT reference state, true (per-step re-linearized)
Newton matches modified Newton to ~6 significant figures: the residual plateau is
driven by the fixed regularization (mu=0.1), not by tangent staleness. F2g-3 tests
whether an *adaptive* relative-diagonal regularization (greedy per-step selection of
mu from a schedule) breaks the plateau and approaches the residual gate, versus the
fixed mu=0.1 baseline.

Candidate runner only: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion, no material-Newton-breadth claim. Output is an
untracked ``*.local.json``.
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


SCHEMA_VERSION = "g1-adaptive-regularization-reference-newton.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_adaptive_regularization_reference_newton.local.json"
DEFAULT_MU_CANDIDATES = (0.1, 0.03, 0.01, 0.003, 0.001, 0.0003, 0.0001, 0.00003, 0.00001)

STOP_GATE = "residual_gate_passed"
STOP_MAX_STEPS = "max_steps"
STOP_NO_DESCENT = "no_candidate_descent"
STOP_SOLVE_FAILED = "solve_failed"
STOP_NAN = "fail_closed_nan"

ResidualFn = Callable[[np.ndarray], np.ndarray]
# a mu-solver maps a rhs residual r to a direction p (or None on failure)
MuSolver = "tuple[float, Callable[[np.ndarray], np.ndarray | None]]"


def _inf_norm(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.max(np.abs(x))) if x.size else 0.0


def _finite(x: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(x, dtype=np.float64))))


def run_adaptive_greedy_newton(
    residual_fn: ResidualFn,
    x0: np.ndarray,
    mu_solvers: "list[MuSolver]",
    *,
    max_newton_steps: int = 12,
    residual_gate_n: float = 5.0e-4,
    alphas: tuple[float, ...] = DEFAULT_ALPHAS,
) -> dict[str, Any]:
    """Greedy per-step mu selection: pick the candidate with the lowest post-line-search residual."""
    x = np.asarray(x0, dtype=np.float64).copy()
    r = np.asarray(residual_fn(x), dtype=np.float64)
    if not _finite(r):
        return {"history": [], "summary": {"initial_residual_n": None, "final_residual_n": None,
                "total_reduction_ratio": None, "monotonic_residual_decrease": False,
                "residual_gate_passed": False, "stop_reason": STOP_NAN, "steps_taken": 0}}
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
        candidate_results: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
        any_factored = False
        for mu, solve_fn in mu_solvers:
            try:
                p = solve_fn(r)
            except Exception:  # noqa: BLE001
                candidate_results.append({"mu": mu, "direction_solve_status": "blocked",
                                          "reason_code": "solve_error"})
                continue
            if p is None or not _finite(p):
                candidate_results.append({"mu": mu, "direction_solve_status": "blocked",
                                          "reason_code": "solve_failed_or_nan"})
                continue
            any_factored = True
            jvp_action = physical_consistent_jvp(residual_fn, x, p)
            ls = physical_residual_backtracking_line_search(
                residual_fn, x, p, jvp_action=jvp_action, alphas=alphas,
            )
            row = {"mu": mu, "direction_solve_status": "ready",
                   "line_search_status": ls.get("status"),
                   "accepted_alpha": ls.get("accepted_alpha"),
                   "residual_after_n": ls.get("residual_after_n"),
                   "residual_reduction_ratio": ls.get("residual_reduction_ratio")}
            candidate_results.append(row)
            if ls.get("status") == "ready":
                if best is None or float(row["residual_after_n"]) < float(best["residual_after_n"]):
                    best = row
        if best is None:
            history.append({"iteration": it, "residual_before_n": rb,
                            "candidate_results": candidate_results, "selected_mu": None})
            stop_reason = STOP_NO_DESCENT if any_factored else STOP_SOLVE_FAILED
            break
        # recompute the accepted direction for the selected mu to advance the state
        sel_mu = best["mu"]
        sel_solve = next(s for m, s in mu_solvers if m == sel_mu)
        p = sel_solve(r)
        alpha = float(best["accepted_alpha"])
        ra = float(best["residual_after_n"])
        if ra > rb:
            monotonic = False
        history.append({"iteration": it, "residual_before_n": rb,
                        "candidate_results": candidate_results,
                        "selected_mu": sel_mu, "selected_alpha": alpha,
                        "residual_after_n": ra,
                        "residual_reduction_ratio": (rb - ra) / max(rb, 1.0e-30)})
        x = x + alpha * np.asarray(p, dtype=np.float64)
    final_r = np.asarray(residual_fn(x), dtype=np.float64)
    final = _inf_norm(final_r) if _finite(final_r) else None
    return {
        "history": history,
        "summary": {
            "initial_residual_n": initial,
            "final_residual_n": final,
            "total_reduction_ratio": ((initial - final) / max(initial, 1.0e-30)) if final is not None else None,
            "monotonic_residual_decrease": bool(monotonic),
            "residual_gate_n": residual_gate_n,
            "residual_gate_passed": bool(final is not None and final <= residual_gate_n),
            "stop_reason": stop_reason,
            "steps_taken": len(history),
            "selected_mu_schedule": [h.get("selected_mu") for h in history],
        },
    }


def _prefactor_mu_solvers(k_free: Any, mode: str, mu_candidates: tuple[float, ...]) -> "list[MuSolver]":
    """Factorize K + reg(mu) once per candidate (reference tangent is fixed)."""
    solvers: list[Any] = []
    for mu in mu_candidates:
        k_reg, _shift, _src = regularize_matrix(k_free, mode, mu)
        try:
            factor = splu(csc_matrix(k_reg))
        except Exception:  # noqa: BLE001 - singular at this mu; skip candidate
            continue

        def _solve(r: np.ndarray, _factor=factor) -> np.ndarray | None:
            try:
                p = np.asarray(_factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
            except Exception:  # noqa: BLE001
                return None
            return p

        solvers.append((float(mu), _solve))
    return solvers


def run_g1_adaptive_regularization_reference_newton(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_service_tangent_source: str = "real_per_element",
    regularization_mode: str = "relative_diagonal_shift",
    mu_candidates: tuple[float, ...] = DEFAULT_MU_CANDIDATES,
    baseline_mu: float = 0.1,
    max_newton_steps: int = 12,
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
            "adaptive_strategy": {
                "mode": "greedy_per_step_mu_selection",
                "regularization_mode": regularization_mode,
                "mu_candidates": list(mu_candidates),
                "selection_metric": "min_residual_after_line_search",
            },
            "production_lambda": PRODUCTION_LAMBDA,
            "material_tangent_update": {"claim_boundary": "not_material_newton_breadth"},
            "claim_boundary": "non_promoting_adaptive_regularization_reference_candidate_only",
        }

    if not mgt_model.is_file():
        payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_INPUT_MISSING,
                   "uses_real_mgt_model": False, "mgt_source": str(mgt_model),
                   "history": [], "summary": {"stop_reason": "mgt_input_missing"}}
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
                       "history": [], "summary": {"stop_reason": "state_build_failed"}}
        else:
            k_free = meta["tangent_free_csr"]
            mu_solvers = _prefactor_mu_solvers(k_free, regularization_mode, mu_candidates)
            adaptive = run_adaptive_greedy_newton(
                residual_fn, x0, mu_solvers, max_newton_steps=max_newton_steps,
                residual_gate_n=residual_gate_n)
            baseline_solvers = _prefactor_mu_solvers(k_free, regularization_mode, (baseline_mu,))
            baseline = run_adaptive_greedy_newton(
                residual_fn, x0, baseline_solvers, max_newton_steps=max_newton_steps,
                residual_gate_n=residual_gate_n)
            a_sum, b_sum = adaptive["summary"], baseline["summary"]
            beats = bool(a_sum["final_residual_n"] is not None and b_sum["final_residual_n"] is not None
                         and a_sum["final_residual_n"] < b_sum["final_residual_n"])
            status = "ready" if a_sum["stop_reason"] in {STOP_GATE, STOP_MAX_STEPS} else "review"
            payload = {
                **_base(),
                "status": status,
                "reason_code": a_sum["stop_reason"],
                "uses_real_mgt_model": True,
                "mgt_source": str(mgt_model),
                "baseline_fixed_mu": {
                    "mu": baseline_mu,
                    "final_residual_n": b_sum["final_residual_n"],
                    "total_reduction_ratio": b_sum["total_reduction_ratio"],
                    "residual_gate_passed": b_sum["residual_gate_passed"],
                    "stop_reason": b_sum["stop_reason"],
                },
                "history": adaptive["history"],
                "summary": {**a_sum, "beats_fixed_mu_baseline": beats},
                "resource_usage": {
                    "dof_count": meta["dof_count"], "free_dof_count": meta["free_dof_count"],
                    "element_count": meta["element_count"],
                    "factorable_mu_count": len(mu_solvers),
                },
            }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def _parse_mu(raw: str) -> tuple[float, ...]:
    return tuple(float(x) for x in raw.split(",") if x.strip())


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
    parser.add_argument("--mu-candidates", type=str, default=",".join(str(x) for x in DEFAULT_MU_CANDIDATES))
    parser.add_argument("--baseline-mu", type=float, default=0.1)
    parser.add_argument("--max-newton-steps", type=int, default=12)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_adaptive_regularization_reference_newton(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        regularization_mode=args.regularization_mode, mu_candidates=_parse_mu(args.mu_candidates),
        baseline_mu=args.baseline_mu, max_newton_steps=args.max_newton_steps,
        residual_gate_n=args.residual_gate_n, output_json=args.output_json,
    )
    s = payload.get("summary", {})
    b = payload.get("baseline_fixed_mu", {})
    print(
        "g1-adaptive-regularization-reference-newton: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"adaptive_final={s.get('final_residual_n')} baseline_final={b.get('final_residual_n')} "
        f"beats_baseline={s.get('beats_fixed_mu_baseline')} gate={s.get('residual_gate_passed')} "
        f"mu_schedule={s.get('selected_mu_schedule')} -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
