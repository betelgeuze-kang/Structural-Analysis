#!/usr/bin/env python3
"""Non-promoting assembled-tangent (sparse-direct/ILU) MGT line-search smoke (F2b-ii-a).

F2b-i showed diagonal (Jacobi) preconditioning cannot fix the real MGT model's
extreme stiffness-contrast ill-conditioning. F2b-ii-a builds the assembled
free-space tangent, verifies it is consistent with the physical residual operator
(parity vs the matrix-free JVP), and solves the Newton direction with a
sparse-direct factorization or an ILU-preconditioned matrix-free GMRES, then runs
a physical-residual line-search preview.

It does not change the default solver path (default solver remains
``gmres_matrix_free``), does not promote G1, does not regenerate the 0.656
continuation checkpoint (F2b-ii-b), and writes only an untracked ``*.local.json``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
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
from g1_assembled_tangent_solve import (
    DEFAULT_DIRECTION_SOLVER,
    DIRECTION_SOLVERS,
    ERR_ASSEMBLED_TANGENT_PARITY_FAILED,
    ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH,
    PASS,
    assembled_tangent_parity,
    solve_direction_assembled,
)
from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
    solve_physical_newton_direction,
)
from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    ERR_LINE_SEARCH_NO_DESCENT,
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    ERR_NAN_RESIDUAL,
    ERR_OPERATOR_SHAPE_MISMATCH,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-mgt-sparse-direct-physical-line-search-smoke.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_mgt_sparse_direct_physical_line_search_smoke.local.json"

ReducedResidualFn = Callable[[np.ndarray], np.ndarray]


def _report(**kw: Any) -> dict[str, Any]:
    operator = kw["operator"]
    return {
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
        "default_direction_solver": DEFAULT_DIRECTION_SOLVER,
        "physical_residual_formula": "R(u,lambda)=F_int(u)-lambda*F_ext",
        "uses_solver_normalization_lambda": operator_uses_solver_normalization_lambda(operator),
        "normalization_lambda_excluded": not operator_uses_solver_normalization_lambda(operator),
        "status": kw["status"],
        "reason_code": kw["reason_code"],
        "free_space": kw.get("free_space", {}),
        "assembled_tangent": kw.get("assembled_tangent", {}),
        "assembled_tangent_parity": kw.get("assembled_tangent_parity", {"attempted": False, "pass": False}),
        "jvp_parity": kw.get("jvp_parity", {"attempted": False, "pass": False}),
        "direction_solve_comparison": kw.get("direction_solve_comparison", {}),
        "line_search_preview": kw.get("line_search_preview", {"attempted": False, "status": "not_attempted"}),
        "resource_usage": kw.get("resource_usage", {}),
        "f2b_ii_b_scope_note": "0.656 continuation checkpoint regeneration/application is F2b-ii-b; not done here",
        "claim_boundary": "non_promoting_sparse_direct_real_mgt_smoke_only",
    }


def _solve_summary(meta: dict[str, Any]) -> dict[str, Any]:
    keys = ("status", "reason_code", "iterations", "residual_norm_before",
            "residual_norm_after", "residual_norm_after_linear_solve", "preconditioned")
    return {k: meta.get(k) for k in keys if k in meta}


def run_sparse_direct_smoke_from_closure(
    residual_fn: ReducedResidualFn,
    x0: np.ndarray,
    k_free: Any,
    *,
    direction_solver: str = "sparse_direct_spsolve",
    operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    parity_relative_tolerance: float = 1.0e-3,
    ilu_drop_tol: float = 1.0e-4,
    ilu_fill_factor: float = 10.0,
    gmres_maxiter: int = 400,
    assembled_tangent_meta: dict[str, Any] | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Testable core: assembled-tangent direction solve + line-search on a closure."""
    operator = normalize_global_newton_operator(operator)
    x0 = np.asarray(x0, dtype=np.float64)
    n = int(x0.size)
    common = dict(operator=operator, uses_real_mgt_model=uses_real_mgt_model,
                  mgt_source=mgt_source, load_scale=load_scale,
                  resource_usage=resource_usage or {},
                  assembled_tangent=assembled_tangent_meta or {},
                  free_space={"free_dof_count": n, "residual_shape": [n],
                              "tangent_shape": list(k_free.shape)})

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
    if tuple(k_free.shape) != (n, n):
        return _report(status="blocked", reason_code=ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH, **common)

    # JVP parity (operator wiring) + assembled-tangent parity (K ~ dR/du)
    rng = np.random.default_rng(0)
    v = rng.standard_normal(n)
    v = v / max(float(np.linalg.norm(v)), 1.0e-30)
    jvp_parity = jvp_parity_report(residual_fn, x0, v)
    jvp_parity["attempted"] = True
    tangent_parity = assembled_tangent_parity(
        k_free, residual_fn, x0, relative_tolerance=parity_relative_tolerance
    )
    if not tangent_parity["pass"]:
        return _report(status="review", reason_code=ERR_ASSEMBLED_TANGENT_PARITY_FAILED,
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity, **common)

    # baseline matrix-free (none) for comparison
    _pn, meta_none = solve_physical_newton_direction(
        residual_fn, x0, mode="matrix_free_gmres", gmres_maxiter=gmres_maxiter,
        gmres_tol=1.0e-6, preconditioner_minv=None,
    )
    # chosen assembled-tangent solver
    p, meta_dir = solve_direction_assembled(
        k_free, residual_fn, x0, solver=direction_solver,
        ilu_drop_tol=ilu_drop_tol, ilu_fill_factor=ilu_fill_factor, gmres_maxiter=gmres_maxiter,
    )
    comparison = {
        "gmres_matrix_free_none": {
            "status": "ready" if meta_none.get("converged") else "blocked",
            "reason_code": meta_none.get("reason_code"),
            "iterations": meta_none.get("iterations"),
            "residual_norm_before": meta_none.get("residual_norm_before"),
            "residual_norm_after": meta_none.get("residual_norm_after"),
        },
        direction_solver: _solve_summary(meta_dir),
    }

    if p is None or meta_dir.get("status") != "ready":
        line_search = {"attempted": True, "status": "blocked",
                       "reason_code": meta_dir.get("reason_code"), "accepted_alpha": None}
        return _report(status="blocked", reason_code=meta_dir.get("reason_code", "ERR_DIRECTION_SOLVE_BLOCKED"),
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                       direction_solve_comparison=comparison, line_search_preview=line_search, **common)

    jvp_action = physical_consistent_jvp(residual_fn, x0, p)
    ls_raw = physical_residual_backtracking_line_search(
        residual_fn, x0, p, jvp_action=jvp_action, alphas=DEFAULT_ALPHAS,
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
        return _report(status="review", reason_code=ERR_LINE_SEARCH_NO_DESCENT,
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                       direction_solve_comparison=comparison, line_search_preview=line_search, **common)
    return _report(status="ready", reason_code=PASS,
                   jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                   direction_solve_comparison=comparison, line_search_preview=line_search, **common)


def run_g1_mgt_sparse_direct_physical_line_search_smoke(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    direction_solver: str = "sparse_direct_spsolve",
    global_newton_operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    load_scale: float = 0.1,
    ilu_drop_tol: float = 1.0e-4,
    ilu_fill_factor: float = 10.0,
    gmres_maxiter: int = 400,
    frame_service_tangent_source: str = "real_per_element",
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    operator = normalize_global_newton_operator(global_newton_operator)
    mgt_model = Path(mgt_model)
    if not mgt_model.is_file():
        payload = _report(status="blocked", reason_code=ERR_MGT_INPUT_MISSING,
                          operator=operator, uses_real_mgt_model=False, mgt_source=str(mgt_model))
    else:
        try:
            t0 = time.perf_counter()
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
                frame_service_tangent_source=frame_service_tangent_source,
            )
            build_seconds = time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001
            payload = _report(status="blocked", reason_code=ERR_MGT_STATE_BUILD_FAILED,
                              operator=operator, uses_real_mgt_model=True, mgt_source=str(mgt_model),
                              jvp_parity={"attempted": False, "pass": False,
                                          "reason_code": f"{type(exc).__name__}:{exc}"})
        else:
            k_free = meta["tangent_free_csr"]
            diag = np.asarray(k_free.diagonal(), dtype=np.float64)
            assembled_tangent_meta = {
                "format": "csr",
                "nnz": int(meta["tangent_free_nnz"]),
                "build_seconds": float(build_seconds),
                "diag_min_abs": float(np.min(np.abs(diag))) if diag.size else 0.0,
                "diag_max_abs": float(np.max(np.abs(diag))) if diag.size else 0.0,
                "frame_service_tangent_source": meta.get("frame_service_tangent_source"),
                "frame_service_tangent_stats_mpa": meta.get("frame_service_tangent_stats_mpa"),
            }
            payload = run_sparse_direct_smoke_from_closure(
                residual_fn, x0, k_free, direction_solver=direction_solver, operator=operator,
                uses_real_mgt_model=True, mgt_source=str(mgt_model), load_scale=load_scale,
                ilu_drop_tol=ilu_drop_tol, ilu_fill_factor=ilu_fill_factor, gmres_maxiter=gmres_maxiter,
                assembled_tangent_meta=assembled_tangent_meta,
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
    parser.add_argument("--direction-solver", choices=list(DIRECTION_SOLVERS), default="sparse_direct_spsolve")
    parser.add_argument(
        "--global-newton-operator",
        choices=[GLOBAL_NEWTON_OPERATOR_CURRENT, GLOBAL_NEWTON_OPERATOR_PHYSICAL],
        default=GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    )
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument("--ilu-drop-tol", type=float, default=1.0e-4)
    parser.add_argument("--ilu-fill-factor", type=float, default=10.0)
    parser.add_argument("--gmres-maxiter", type=int, default=400)
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"], default="real_per_element",
    )
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_mgt_sparse_direct_physical_line_search_smoke(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        direction_solver=args.direction_solver, global_newton_operator=args.global_newton_operator,
        load_scale=args.load_scale, ilu_drop_tol=args.ilu_drop_tol,
        ilu_fill_factor=args.ilu_fill_factor, gmres_maxiter=args.gmres_maxiter,
        frame_service_tangent_source=args.frame_service_tangent_source,
        output_json=args.output_json,
    )
    tp = payload.get("assembled_tangent_parity", {})
    ls = payload["line_search_preview"]
    print(
        "g1-mgt-sparse-direct-physical-line-search-smoke: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"tangent_parity_pass={tp.get('pass')} (rel={tp.get('max_relative_error')}) "
        f"ls={ls.get('status')} accepted_alpha={ls.get('accepted_alpha')} "
        f"reduction={ls.get('residual_reduction_ratio')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
