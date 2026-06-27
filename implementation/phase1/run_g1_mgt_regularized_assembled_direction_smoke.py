#!/usr/bin/env python3
"""Non-promoting regularized assembled-tangent direction smoke (F2f).

F2e: with the real per-element service tangent the assembled free-space tangent is
consistent with the physical residual (parity pass) but singular for direct
factorization. F2f sweeps a principled regularization, solves the regularized
direction, runs a physical-residual line-search preview, and quantifies how small a
regularization is needed for a factorable, descent-yielding direction relative to
the production lambda ~= 515.

Not a fix and not a closure: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion. Output is an untracked ``*.local.json``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from g1_global_newton_operator import (
    GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    jvp_parity_report,
    normalize_global_newton_operator,
    physical_consistent_jvp,
)
from g1_assembled_tangent_solve import assembled_tangent_parity
from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
)
from g1_regularized_direction import (
    ERR_LINE_SEARCH_NO_DESCENT,
    ERR_PARITY_REQUIRED_BUT_FAILED,
    ERR_REGULARIZATION_SWEEP_NO_FACTORABLE_CANDIDATE,
    ERR_REGULARIZATION_TOO_LARGE,
    ERR_UNREGULARIZED_TANGENT_SINGULAR,
    GRADIENT_COLLAPSE_COSINE,
    PASS,
    PRODUCTION_LAMBDA,
    REGULARIZATION_MODES,
    solve_regularized_direction,
)
from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-mgt-regularized-assembled-direction-smoke.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_mgt_regularized_assembled_direction_smoke.local.json"
DEFAULT_SWEEP = (0.0, 1e-9, 1e-6, 1e-3, 1e-1, 1.0, 10.0, 100.0, 515.0, 1000.0)

ReducedResidualFn = Callable[[np.ndarray], np.ndarray]


def run_regularized_sweep_from_closure(
    residual_fn: ReducedResidualFn,
    x0: np.ndarray,
    k_free: Any,
    *,
    regularization_mode: str = "relative_diagonal_shift",
    sweep: tuple[float, ...] = DEFAULT_SWEEP,
    operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    require_parity: bool = True,
    parity_relative_tolerance: float = 1.0e-2,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    frame_service_tangent_source: str | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Testable core: regularization sweep + line-search on a reduced closure."""
    operator = normalize_global_newton_operator(operator)
    x0 = np.asarray(x0, dtype=np.float64)
    n = int(x0.size)

    def base() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_smoke_only": True,
            "promotes_g1_closure": False,
            "uses_real_mgt_model": bool(uses_real_mgt_model),
            "mgt_source": mgt_source,
            "load_scale": load_scale,
            "frame_service_tangent_source": frame_service_tangent_source,
            "global_newton_operator": operator,
            "regularization_mode": regularization_mode,
            "production_lambda": PRODUCTION_LAMBDA,
            "resource_usage": resource_usage or {},
            "claim_boundary": "non_promoting_regularized_direction_smoke_only",
        }

    # parity gate (operator consistency must already hold from F2e)
    rng = np.random.default_rng(0)
    v = rng.standard_normal(n)
    v = v / max(float(np.linalg.norm(v)), 1.0e-30)
    parity = assembled_tangent_parity(k_free, residual_fn, x0, relative_tolerance=parity_relative_tolerance)
    jvp_parity = jvp_parity_report(residual_fn, x0, v)
    if require_parity and not parity["pass"]:
        return {**base(), "status": "blocked", "reason_code": ERR_PARITY_REQUIRED_BUT_FAILED,
                "assembled_tangent_parity": parity, "jvp_parity": jvp_parity,
                "unregularized_baseline": {}, "regularization_sweep": [], "best_regularized_candidate": None}

    # unregularized baseline
    _p0, m0 = solve_regularized_direction(k_free, residual_fn, x0, mode="none", mu=0.0)
    unreg = {
        "factorization_status": "ok" if m0.get("factorization_pass") else "singular",
        "reason_code": m0.get("reason_code"),
    }

    r0 = np.asarray(residual_fn(x0), dtype=np.float64)
    r0_norm = float(np.max(np.abs(r0))) if r0.size else 0.0
    sweep_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for mu in sweep:
        if regularization_mode == "none" and mu == 0.0:
            continue
        p, meta = solve_regularized_direction(k_free, residual_fn, x0, mode=regularization_mode, mu=float(mu))
        row: dict[str, Any] = {
            "mode": regularization_mode, "mu": float(mu),
            "effective_shift": meta.get("effective_shift"),
            "scale_source": meta.get("scale_source"),
            "factorization_pass": bool(meta.get("factorization_pass")),
            "reason_code": meta.get("reason_code"),
            "cosine_with_neg_residual": meta.get("cosine_with_neg_residual"),
            "line_search_attempted": False,
            "accepted_alpha": None,
            "residual_reduction_ratio": None,
        }
        if p is not None and meta.get("factorization_pass"):
            collapsed = float(meta.get("cosine_with_neg_residual") or 0.0) > GRADIENT_COLLAPSE_COSINE
            row["regularization_too_large"] = bool(collapsed)
            jvp_action = physical_consistent_jvp(residual_fn, x0, p)
            ls = physical_residual_backtracking_line_search(
                residual_fn, x0, p, jvp_action=jvp_action, alphas=DEFAULT_ALPHAS,
            )
            row["line_search_attempted"] = True
            row["line_search_status"] = ls.get("status")
            row["accepted_alpha"] = ls.get("accepted_alpha")
            row["residual_reduction_ratio"] = ls.get("residual_reduction_ratio")
            row["beats_d_tiny_alpha_threshold"] = ls.get("beats_d_tiny_alpha_threshold")
            if ls.get("status") == "ready" and not collapsed:
                candidates.append(row)
            elif collapsed:
                row["reason_code"] = ERR_REGULARIZATION_TOO_LARGE
            elif ls.get("status") != "ready":
                row["reason_code"] = ERR_LINE_SEARCH_NO_DESCENT
        sweep_rows.append(row)

    best = None
    if candidates:
        # best Newton step = largest physical-residual reduction (not just factorable)
        best_row = max(candidates, key=lambda r: float(r["residual_reduction_ratio"] or 0.0))
        eff = float(best_row["effective_shift"] or 0.0)
        best = {
            "mode": best_row["mode"], "mu": best_row["mu"], "effective_shift": eff,
            "factorization_pass": True,
            "accepted_alpha": best_row["accepted_alpha"],
            "residual_reduction_ratio": best_row["residual_reduction_ratio"],
            "cosine_with_neg_residual": best_row["cosine_with_neg_residual"],
            "lambda_vs_production_515_ratio": (eff / PRODUCTION_LAMBDA) if PRODUCTION_LAMBDA else None,
            "smaller_than_production_lambda": bool(eff < PRODUCTION_LAMBDA),
            "selected_by": "max_residual_reduction_ratio",
        }
        status, reason = "ready", PASS
    else:
        factorable = [r for r in sweep_rows if r["factorization_pass"]]
        if not factorable:
            status, reason = "blocked", ERR_REGULARIZATION_SWEEP_NO_FACTORABLE_CANDIDATE
        else:
            # factorable but no descent / too large
            status = "review"
            reason = (ERR_REGULARIZATION_TOO_LARGE
                      if all(r.get("regularization_too_large") for r in factorable if r.get("line_search_attempted"))
                      else ERR_LINE_SEARCH_NO_DESCENT)

    return {
        **base(),
        "status": status,
        "reason_code": reason,
        "assembled_tangent_parity": parity,
        "jvp_parity": jvp_parity,
        "unregularized_baseline": {
            **unreg,
            "reason_code": (ERR_UNREGULARIZED_TANGENT_SINGULAR
                            if unreg["factorization_status"] == "singular" else unreg["reason_code"]),
            "residual_inf_n": r0_norm,
        },
        "regularization_sweep": sweep_rows,
        "smallest_factorable_candidate": (
            min(
                ({"mu": r["mu"], "effective_shift": r["effective_shift"],
                  "accepted_alpha": r.get("accepted_alpha"),
                  "residual_reduction_ratio": r.get("residual_reduction_ratio"),
                  "lambda_vs_production_515_ratio": (
                      float(r["effective_shift"]) / PRODUCTION_LAMBDA
                      if r.get("effective_shift") else None)}
                 for r in sweep_rows if r["factorization_pass"]),
                key=lambda r: float(r["effective_shift"] or float("inf")),
            ) if any(r["factorization_pass"] for r in sweep_rows) else None
        ),
        "best_regularized_candidate": best,
    }


def run_g1_mgt_regularized_assembled_direction_smoke(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    regularization_mode: str = "relative_diagonal_shift",
    sweep: tuple[float, ...] = DEFAULT_SWEEP,
    frame_service_tangent_source: str = "real_per_element",
    load_scale: float = 0.1,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    mgt_model = Path(mgt_model)
    if not mgt_model.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_smoke_only": True, "promotes_g1_closure": False,
            "status": "blocked", "reason_code": ERR_MGT_INPUT_MISSING,
            "uses_real_mgt_model": False, "mgt_source": str(mgt_model),
            "regularization_mode": regularization_mode, "production_lambda": PRODUCTION_LAMBDA,
            "claim_boundary": "non_promoting_regularized_direction_smoke_only",
        }
    else:
        try:
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
                frame_service_tangent_source=frame_service_tangent_source,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_smoke_only": True, "promotes_g1_closure": False,
                "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                "detail": f"{type(exc).__name__}:{exc}",
                "regularization_mode": regularization_mode, "production_lambda": PRODUCTION_LAMBDA,
                "claim_boundary": "non_promoting_regularized_direction_smoke_only",
            }
        else:
            payload = run_regularized_sweep_from_closure(
                residual_fn, x0, meta["tangent_free_csr"],
                regularization_mode=regularization_mode, sweep=sweep,
                uses_real_mgt_model=True, mgt_source=str(mgt_model), load_scale=load_scale,
                frame_service_tangent_source=meta.get("frame_service_tangent_source"),
                resource_usage={
                    "dof_count": meta["dof_count"], "free_dof_count": meta["free_dof_count"],
                    "element_count": meta["element_count"],
                },
            )

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def _parse_sweep(raw: str) -> tuple[float, ...]:
    return tuple(float(x) for x in raw.split(",") if x.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--regularization-mode", choices=list(REGULARIZATION_MODES), default="relative_diagonal_shift")
    parser.add_argument("--regularization-sweep", type=str, default=",".join(str(x) for x in DEFAULT_SWEEP))
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"], default="real_per_element",
    )
    parser.add_argument("--direction-solver", default="sparse_direct_spsolve")  # accepted for interface parity
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_mgt_regularized_assembled_direction_smoke(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        regularization_mode=args.regularization_mode, sweep=_parse_sweep(args.regularization_sweep),
        frame_service_tangent_source=args.frame_service_tangent_source,
        load_scale=args.load_scale, output_json=args.output_json,
    )
    best = payload.get("best_regularized_candidate")
    print(
        "g1-mgt-regularized-assembled-direction-smoke: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"unreg={payload.get('unregularized_baseline', {}).get('factorization_status')} "
        f"best_mu={(best or {}).get('mu')} best_shift={(best or {}).get('effective_shift')} "
        f"accepted_alpha={(best or {}).get('accepted_alpha')} "
        f"vs515={(best or {}).get('lambda_vs_production_515_ratio')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
