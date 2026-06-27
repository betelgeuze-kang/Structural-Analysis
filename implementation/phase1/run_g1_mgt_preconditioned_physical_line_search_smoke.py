#!/usr/bin/env python3
"""Non-promoting preconditioned real-MGT physical line-search smoke (F2b-i).

F2a established that, on the real MGT model, the physical residual closure and
the physical-consistent JVP wire up (JVP parity ~2.7e-16) but the unpreconditioned
matrix-free Newton direction solve is blocked (``gmres_not_converged_maxiter``).

F2b-i attaches a free-space diagonal (Jacobi) preconditioner to the matrix-free
direction solve and reports a ``none`` vs ``preconditioned`` comparison on the same
real-model reference state, then a physical-residual line-search preview if the
preconditioned solve succeeds.

It does not change the default solver path, does not promote G1, does not
regenerate the 0.656 continuation checkpoint (F2b-ii), and writes only an untracked
``*.local.json``. The default preconditioner is ``none``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from g1_global_newton_operator import (
    DEFAULT_GLOBAL_NEWTON_OPERATOR,
    GLOBAL_NEWTON_OPERATOR_CURRENT,
    GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    jvp_parity_report,
    normalize_global_newton_operator,
    operator_uses_solver_normalization_lambda,
    physical_consistent_jvp,
)
from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    DEFAULT_PRECONDITIONER,
    PRECONDITIONER_MODES,
    build_jacobi_preconditioner,
    physical_residual_backtracking_line_search,
    solve_physical_newton_direction,
)
from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    ERR_DIRECTION_SOLVE_BLOCKED,
    ERR_JVP_PARITY_FAILED,
    ERR_LINE_SEARCH_NO_DESCENT,
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    ERR_NAN_RESIDUAL,
    ERR_OPERATOR_SHAPE_MISMATCH,
    PASS,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-mgt-preconditioned-physical-line-search-smoke.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_mgt_preconditioned_physical_line_search_smoke.local.json"

ReducedResidualFn = Callable[[np.ndarray], np.ndarray]


def _solve_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ready" if meta.get("converged") else "blocked",
        "reason_code": meta.get("reason_code"),
        "iterations": meta.get("iterations"),
        "residual_norm_before": meta.get("residual_norm_before"),
        "residual_norm_after": meta.get("residual_norm_after"),
        "preconditioned": bool(meta.get("preconditioned", False)),
    }


def _report(**kw: Any) -> dict[str, Any]:
    operator = kw["operator"]
    base = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_smoke_only": True,
        "promotes_g1_closure": False,
        "uses_real_mgt_model": kw.get("uses_real_mgt_model", False),
        "mgt_source": kw.get("mgt_source"),
        "load_scale": kw.get("load_scale"),
        "checkpoint_kind": kw.get("checkpoint_kind", "reference_or_lightweight_state"),
        "global_newton_operator": operator,
        "baseline_operator": GLOBAL_NEWTON_OPERATOR_CURRENT,
        "default_global_newton_operator": DEFAULT_GLOBAL_NEWTON_OPERATOR,
        "default_preconditioner": DEFAULT_PRECONDITIONER,
        "physical_residual_formula": "R(u,lambda)=F_int(u)-lambda*F_ext",
        "uses_solver_normalization_lambda": operator_uses_solver_normalization_lambda(operator),
        "normalization_lambda_excluded": not operator_uses_solver_normalization_lambda(operator),
        "status": kw["status"],
        "reason_code": kw["reason_code"],
        "jvp_parity": kw.get("jvp_parity", {"attempted": False, "pass": False, "reason_code": None}),
        "preconditioner": kw.get("preconditioner", {"mode": "none"}),
        "direction_solve": kw.get("direction_solve", {}),
        "direction_solve_comparison": kw.get("direction_solve_comparison", {}),
        "line_search_preview": kw.get("line_search_preview", {"attempted": False, "status": "not_attempted"}),
        "resource_usage": kw.get("resource_usage", {}),
        "f2b_ii_scope_note": "0.656 continuation checkpoint regeneration/application is F2b-ii; not done here",
        "claim_boundary": "non_promoting_preconditioned_real_mgt_smoke_only",
    }
    return base


def run_preconditioned_smoke_from_closure(
    residual_fn: ReducedResidualFn,
    x0: np.ndarray,
    diag_free: np.ndarray,
    *,
    preconditioner_mode: str = "damped_jacobi_diag",
    operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    gmres_maxiter: int = 200,
    gmres_rtol: float = 1.0e-6,
    gmres_atol: float = 1.0e-10,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Testable core: none-vs-preconditioned direction solve on a reduced closure."""
    operator = normalize_global_newton_operator(operator)
    x0 = np.asarray(x0, dtype=np.float64)
    diag_free = np.asarray(diag_free, dtype=np.float64)
    common = dict(
        operator=operator, uses_real_mgt_model=uses_real_mgt_model,
        mgt_source=mgt_source, load_scale=load_scale, resource_usage=resource_usage or {},
    )

    # base residual contract
    try:
        r0 = np.asarray(residual_fn(x0), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        return _report(status="blocked", reason_code=ERR_MGT_STATE_BUILD_FAILED,
                       jvp_parity={"attempted": False, "pass": False,
                                   "reason_code": f"closure_eval_raised:{type(exc).__name__}"},
                       **common)
    if r0.shape != x0.shape:
        return _report(status="blocked", reason_code=ERR_OPERATOR_SHAPE_MISMATCH, **common)
    if not bool(np.all(np.isfinite(r0))):
        return _report(status="blocked", reason_code=ERR_NAN_RESIDUAL, **common)
    if diag_free.shape != x0.shape:
        return _report(status="blocked", reason_code=ERR_OPERATOR_SHAPE_MISMATCH,
                       jvp_parity={"attempted": False, "pass": False,
                                   "reason_code": "diag_free_shape_ne_state_shape"},
                       **common)

    # JVP parity
    rng = np.random.default_rng(0)
    v = rng.standard_normal(int(x0.size))
    v = v / max(float(np.linalg.norm(v)), 1.0e-30)
    parity = jvp_parity_report(residual_fn, x0, v)
    parity["attempted"] = True
    if not bool(np.all(np.isfinite(physical_consistent_jvp(residual_fn, x0, v)))):
        parity["reason_code"] = "nonfinite_jvp"
        return _report(status="blocked", reason_code=ERR_JVP_PARITY_FAILED, jvp_parity=parity, **common)

    # baseline (no preconditioner)
    _p_none, meta_none = solve_physical_newton_direction(
        residual_fn, x0, mode="matrix_free_gmres",
        gmres_maxiter=gmres_maxiter, gmres_tol=gmres_rtol, gmres_atol=gmres_atol,
        preconditioner_minv=None,
    )
    # preconditioned
    minv, precond_meta = build_jacobi_preconditioner(diag_free, preconditioner_mode)
    p_pre, meta_pre = solve_physical_newton_direction(
        residual_fn, x0, mode="matrix_free_gmres",
        gmres_maxiter=gmres_maxiter, gmres_tol=gmres_rtol, gmres_atol=gmres_atol,
        preconditioner_minv=minv,
    )

    def _ra(meta):
        ra = meta.get("residual_norm_after")
        return ra if ra is not None else float("inf")

    improved = bool(
        (meta_pre.get("converged") and not meta_none.get("converged"))
        or (_ra(meta_pre) < _ra(meta_none))
        or (meta_pre.get("converged") and meta_none.get("converged")
            and int(meta_pre.get("iterations") or 0) < int(meta_none.get("iterations") or 0))
    )
    comparison = {
        "none": _solve_summary(meta_none),
        preconditioner_mode: {**_solve_summary(meta_pre), "improved_vs_none": improved},
    }
    direction_solve = {
        "solver": "gmres",
        "preconditioned": True,
        **_solve_summary(meta_pre),
    }

    if p_pre is None or not meta_pre.get("converged"):
        line_search = {"attempted": True, "status": "blocked",
                       "reason_code": meta_pre.get("reason_code"), "accepted_alpha": None,
                       "residual_reduction_ratio": None}
        return _report(status="review" if improved else "blocked",
                       reason_code=ERR_DIRECTION_SOLVE_BLOCKED, jvp_parity=parity,
                       preconditioner=precond_meta, direction_solve=direction_solve,
                       direction_solve_comparison=comparison, line_search_preview=line_search,
                       **common)

    # line-search with preconditioned direction
    jvp_action = physical_consistent_jvp(residual_fn, x0, p_pre)
    ls_raw = physical_residual_backtracking_line_search(
        residual_fn, x0, p_pre, jvp_action=jvp_action, alphas=DEFAULT_ALPHAS,
    )
    line_search = {
        "attempted": True,
        "status": ls_raw.get("status"),
        "accepted_alpha": ls_raw.get("accepted_alpha"),
        "residual_before_n": ls_raw.get("residual_before_n"),
        "residual_after_n": ls_raw.get("residual_after_n"),
        "residual_reduction_ratio": ls_raw.get("residual_reduction_ratio"),
        "beats_d_tiny_alpha_threshold": ls_raw.get("beats_d_tiny_alpha_threshold"),
        "beats_d_residual_reduction_baseline": ls_raw.get("beats_d_residual_reduction_baseline"),
        "reason_code": ls_raw.get("reason_code"),
    }
    if ls_raw.get("status") != "ready":
        return _report(status="review", reason_code=ERR_LINE_SEARCH_NO_DESCENT, jvp_parity=parity,
                       preconditioner=precond_meta, direction_solve=direction_solve,
                       direction_solve_comparison=comparison, line_search_preview=line_search,
                       **common)
    return _report(status="ready", reason_code=PASS, jvp_parity=parity,
                   preconditioner=precond_meta, direction_solve=direction_solve,
                   direction_solve_comparison=comparison, line_search_preview=line_search,
                   **common)


def run_g1_mgt_preconditioned_physical_line_search_smoke(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    preconditioner: str = "damped_jacobi_diag",
    global_newton_operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    load_scale: float = 0.1,
    gmres_maxiter: int = 200,
    gmres_rtol: float = 1.0e-6,
    gmres_atol: float = 1.0e-10,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    operator = normalize_global_newton_operator(global_newton_operator)
    mgt_model = Path(mgt_model)
    if not mgt_model.is_file():
        payload = _report(status="blocked", reason_code=ERR_MGT_INPUT_MISSING,
                          operator=operator, uses_real_mgt_model=False, mgt_source=str(mgt_model))
    else:
        try:
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
            )
        except Exception as exc:  # noqa: BLE001
            payload = _report(status="blocked", reason_code=ERR_MGT_STATE_BUILD_FAILED,
                              operator=operator, uses_real_mgt_model=True, mgt_source=str(mgt_model),
                              jvp_parity={"attempted": False, "pass": False,
                                          "reason_code": f"{type(exc).__name__}:{exc}"})
        else:
            payload = run_preconditioned_smoke_from_closure(
                residual_fn, x0, meta["diag_free"], preconditioner_mode=preconditioner,
                operator=operator, uses_real_mgt_model=True, mgt_source=str(mgt_model),
                load_scale=load_scale, gmres_maxiter=gmres_maxiter,
                gmres_rtol=gmres_rtol, gmres_atol=gmres_atol,
                resource_usage={
                    "dof_count": meta["dof_count"], "node_count": meta["node_count"],
                    "element_count": meta["element_count"], "free_dof_count": meta["free_dof_count"],
                    "peak_memory_mb": None,
                },
            )

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
    parser.add_argument("--preconditioner", choices=list(PRECONDITIONER_MODES), default="damped_jacobi_diag")
    parser.add_argument(
        "--global-newton-operator",
        choices=[GLOBAL_NEWTON_OPERATOR_CURRENT, GLOBAL_NEWTON_OPERATOR_PHYSICAL],
        default=GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    )
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument("--gmres-maxiter", type=int, default=200)
    parser.add_argument("--gmres-rtol", type=float, default=1.0e-6)
    parser.add_argument("--gmres-atol", type=float, default=1.0e-10)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_mgt_preconditioned_physical_line_search_smoke(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        preconditioner=args.preconditioner, global_newton_operator=args.global_newton_operator,
        load_scale=args.load_scale, gmres_maxiter=args.gmres_maxiter,
        gmres_rtol=args.gmres_rtol, gmres_atol=args.gmres_atol, output_json=args.output_json,
    )
    cmp = payload.get("direction_solve_comparison", {})
    none = cmp.get("none", {})
    pre = next((v for k, v in cmp.items() if k != "none"), {})
    ls = payload["line_search_preview"]
    print(
        "g1-mgt-preconditioned-physical-line-search-smoke: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"none[{none.get('status')},iters={none.get('iterations')}] "
        f"pre[{pre.get('status')},iters={pre.get('iterations')},improved={pre.get('improved_vs_none')}] "
        f"ls={ls.get('status')} accepted_alpha={ls.get('accepted_alpha')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
