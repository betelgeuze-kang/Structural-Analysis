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
continuation checkpoint (F2b-ii-b), and writes only an untracked ``*.local.json``
unless an explicit non-promoting output checkpoint path is supplied.
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
    PREVIEW_INCOMPLETE_GMRES_DIRECTION,
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
    FRAME_TANGENT_SOURCE_CHOICES,
    FRAME_TANGENT_SOURCE_SERVICE,
    SHELL_PRESSURE_LOAD_PATH_POLICIES,
    build_mgt_physical_residual_closure,
)
from run_g1_true_newton_reference_candidate import (
    CHECKPOINT_SCHEMA,
    _max_abs,
    _translation_metrics,
)


SCHEMA_VERSION = "g1-mgt-sparse-direct-physical-line-search-smoke.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_mgt_sparse_direct_physical_line_search_smoke.local.json"
DEFAULT_SCALED_LSMR_FRONTIER_CHECKPOINT = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
)

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
        "jvp_eps": kw.get("jvp_eps"),
        "gmres_rtol": kw.get("gmres_rtol"),
        "allow_incomplete_gmres_direction": kw.get("allow_incomplete_gmres_direction"),
        "incomplete_gmres_relative_tolerance": kw.get(
            "incomplete_gmres_relative_tolerance"
        ),
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
        "output_final_checkpoint": kw.get("output_final_checkpoint"),
        "resource_usage": kw.get("resource_usage", {}),
        "f2b_ii_b_scope_note": "0.656 continuation checkpoint regeneration/application is F2b-ii-b; not done here",
        "claim_boundary": "non_promoting_sparse_direct_real_mgt_smoke_only",
    }


def _solve_summary(meta: dict[str, Any]) -> dict[str, Any]:
    keys = ("status", "reason_code", "iterations", "residual_norm_before",
            "residual_norm_after", "residual_norm_after_linear_solve",
            "residual_norm_after_shifted_linear_solve", "shifted_operator",
            "residual_norm_after_ratio", "preview_reason_code",
            "incomplete_direction_preview",
            "incomplete_gmres_relative_tolerance",
            "preconditioned", "preconditioner", "scaling",
            "condition_estimate", "istop")
    return {k: meta.get(k) for k in keys if k in meta}


def _write_checkpoint(
    *,
    path: Path,
    load_scale: float,
    displacement_u: np.ndarray,
    final_residual: np.ndarray,
    residual_before_n: float | None,
    external_load_inf_n: float | None,
    accepted_alpha: float,
    direction_solver: str,
    frame_tangent_source: str,
    shell_pressure_load_path_policy: str,
    residual_gate_n: float = 5.0e-4,
    direction_status: str = "ready",
    incomplete_gmres_direction_preview: bool = False,
    preview_reason_code: str | None = None,
    checkpoint_claim_boundary: str = (
        "non_promoting_sparse_direct_scaled_lsmr_checkpoint_candidate"
    ),
) -> dict[str, Any]:
    residual_inf = _max_abs(final_residual)
    relative_residual = residual_inf / max(
        float(external_load_inf_n) if external_load_inf_n is not None else 1.0,
        1.0,
    )
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
            relative_residual,
            dtype=np.float64,
        ),
        max_translation_m=np.asarray(
            translation["max_translation_m"],
            dtype=np.float64,
        ),
        accepted_iteration_count=np.asarray(1, dtype=np.int64),
        accepted_history_count=np.asarray(1, dtype=np.int64),
        residual_before_n=np.asarray(
            float(residual_before_n) if residual_before_n is not None else np.nan,
            dtype=np.float64,
        ),
        accepted_alpha=np.asarray(float(accepted_alpha), dtype=np.float64),
        residual_gate_n=np.asarray(float(residual_gate_n), dtype=np.float64),
        residual_gate_passed=np.asarray(bool(residual_inf <= float(residual_gate_n))),
        direction_solver=np.asarray(direction_solver),
        direction_status=np.asarray(direction_status),
        incomplete_gmres_direction_preview=np.asarray(
            bool(incomplete_gmres_direction_preview)
        ),
        preview_reason_code=np.asarray(str(preview_reason_code or "")),
        frame_tangent_source=np.asarray(frame_tangent_source),
        shell_pressure_load_path_policy=np.asarray(shell_pressure_load_path_policy),
        sparse_direct_line_search_candidate_only=np.asarray(True),
        promotes_g1_closure=np.asarray(False),
        checkpoint_claim_boundary=np.asarray(checkpoint_claim_boundary),
    )
    return {
        "written": True,
        "path": str(path),
        "schema": CHECKPOINT_SCHEMA,
        "load_scale": float(load_scale),
        "dof_count": int(np.asarray(displacement_u).size),
        "direct_residual_inf_n": residual_inf,
        "direct_relative_residual_inf": relative_residual,
        "external_load_inf_n": (
            float(external_load_inf_n) if external_load_inf_n is not None else None
        ),
        "max_translation_m": translation["max_translation_m"],
        "accepted_iteration_count": 1,
        "accepted_history_count": 1,
        "residual_before_n": (
            float(residual_before_n) if residual_before_n is not None else None
        ),
        "accepted_alpha": float(accepted_alpha),
        "residual_gate_n": float(residual_gate_n),
        "residual_gate_passed": bool(residual_inf <= float(residual_gate_n)),
        "direction_solver": str(direction_solver),
        "direction_status": str(direction_status),
        "incomplete_gmres_direction_preview": bool(incomplete_gmres_direction_preview),
        "preview_reason_code": str(preview_reason_code or ""),
        "frame_tangent_source": str(frame_tangent_source),
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "promotes_g1_closure": False,
        "claim_boundary": (
            "Loadable sparse-direct line-search checkpoint candidate only. It "
            "does not close G1 without direct residual, material Newton, "
            "full-mesh, and production ROCm/HIP gates."
        ),
    }


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
    checkpoint_kind: str = "reference_or_lightweight_state",
    parity_relative_tolerance: float = 1.0e-3,
    ilu_drop_tol: float = 1.0e-4,
    ilu_fill_factor: float = 10.0,
    ilu_shift_mode: str = "relative_diagonal_shift",
    ilu_shift_mu: float = 1.0e-6,
    gmres_maxiter: int = 400,
    gmres_rtol: float = 1.0e-6,
    jvp_eps: float = 1.0e-6,
    allow_incomplete_gmres_direction: bool = False,
    incomplete_gmres_relative_tolerance: float = 0.0,
    assembled_tangent_meta: dict[str, Any] | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Testable core: assembled-tangent direction solve + line-search on a closure."""
    operator = normalize_global_newton_operator(operator)
    x0 = np.asarray(x0, dtype=np.float64)
    n = int(x0.size)
    common = dict(operator=operator, uses_real_mgt_model=uses_real_mgt_model,
                  mgt_source=mgt_source, load_scale=load_scale,
                  jvp_eps=float(jvp_eps),
                  gmres_rtol=float(gmres_rtol),
                  allow_incomplete_gmres_direction=bool(allow_incomplete_gmres_direction),
                  incomplete_gmres_relative_tolerance=float(
                      incomplete_gmres_relative_tolerance
                  ),
                  checkpoint_kind=checkpoint_kind,
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
    jvp_parity = jvp_parity_report(residual_fn, x0, v, eps=float(jvp_eps))
    jvp_parity["attempted"] = True
    tangent_parity = assembled_tangent_parity(
        k_free,
        residual_fn,
        x0,
        eps=float(jvp_eps),
        relative_tolerance=parity_relative_tolerance,
    )
    if not tangent_parity["pass"]:
        return _report(status="review", reason_code=ERR_ASSEMBLED_TANGENT_PARITY_FAILED,
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity, **common)

    # baseline matrix-free (none) for comparison
    _pn, meta_none = solve_physical_newton_direction(
        residual_fn, x0, mode="matrix_free_gmres", gmres_maxiter=gmres_maxiter,
        gmres_tol=float(gmres_rtol), preconditioner_minv=None, eps=float(jvp_eps),
    )
    # chosen assembled-tangent solver
    p, meta_dir = solve_direction_assembled(
        k_free, residual_fn, x0, solver=direction_solver,
        eps=float(jvp_eps),
        ilu_drop_tol=ilu_drop_tol,
        ilu_fill_factor=ilu_fill_factor,
        ilu_shift_mode=ilu_shift_mode,
        ilu_shift_mu=ilu_shift_mu,
        gmres_maxiter=gmres_maxiter,
        gmres_rtol=float(gmres_rtol),
        allow_incomplete_gmres_direction=allow_incomplete_gmres_direction,
        incomplete_gmres_relative_tolerance=float(incomplete_gmres_relative_tolerance),
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

    direction_status = str(meta_dir.get("status") or "")
    incomplete_preview = direction_status == "preview"
    if p is None or direction_status not in {"ready", "preview"}:
        line_search = {"attempted": True, "status": "blocked",
                       "reason_code": meta_dir.get("reason_code"), "accepted_alpha": None}
        return _report(status="blocked", reason_code=meta_dir.get("reason_code", "ERR_DIRECTION_SOLVE_BLOCKED"),
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                       direction_solve_comparison=comparison, line_search_preview=line_search, **common)

    jvp_action = physical_consistent_jvp(residual_fn, x0, p, eps=float(jvp_eps))
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
        "incomplete_gmres_direction_preview": incomplete_preview,
    }
    if ls_raw.get("status") != "ready":
        return _report(status="review", reason_code=ERR_LINE_SEARCH_NO_DESCENT,
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                       direction_solve_comparison=comparison, line_search_preview=line_search, **common)
    if incomplete_preview:
        return _report(status="review", reason_code=PREVIEW_INCOMPLETE_GMRES_DIRECTION,
                       jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                       direction_solve_comparison=comparison, line_search_preview=line_search, **common)
    return _report(status="ready", reason_code=PASS,
                   jvp_parity=jvp_parity, assembled_tangent_parity=tangent_parity,
                   direction_solve_comparison=comparison, line_search_preview=line_search, **common)


def run_g1_mgt_sparse_direct_physical_line_search_smoke(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    checkpoint_npz: Path | None = None,
    direction_solver: str = "sparse_direct_spsolve",
    global_newton_operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    load_scale: float = 0.1,
    frame_tangent_source: str = FRAME_TANGENT_SOURCE_SERVICE,
    shell_pressure_load_path_policy: str = "all_components",
    ilu_drop_tol: float = 1.0e-4,
    ilu_fill_factor: float = 10.0,
    ilu_shift_mode: str = "relative_diagonal_shift",
    ilu_shift_mu: float = 1.0e-6,
    gmres_maxiter: int = 400,
    gmres_rtol: float = 1.0e-6,
    jvp_eps: float = 1.0e-6,
    allow_incomplete_gmres_direction: bool = False,
    incomplete_gmres_relative_tolerance: float = 0.0,
    write_incomplete_gmres_preview_checkpoint: bool = False,
    frame_service_tangent_source: str = "real_per_element",
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
    output_final_checkpoint_npz: Path | None = None,
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
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz,
                checkpoint_npz=checkpoint_npz, load_scale=load_scale,
                frame_tangent_source=frame_tangent_source,
                shell_pressure_load_path_policy=shell_pressure_load_path_policy,
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
                checkpoint_kind=str(meta.get("checkpoint_kind") or "reference_or_lightweight_state"),
                jvp_eps=float(jvp_eps),
                ilu_drop_tol=ilu_drop_tol,
                ilu_fill_factor=ilu_fill_factor,
                ilu_shift_mode=ilu_shift_mode,
                ilu_shift_mu=ilu_shift_mu,
                gmres_maxiter=gmres_maxiter,
                gmres_rtol=float(gmres_rtol),
                allow_incomplete_gmres_direction=allow_incomplete_gmres_direction,
                incomplete_gmres_relative_tolerance=float(
                    incomplete_gmres_relative_tolerance
                ),
                assembled_tangent_meta=assembled_tangent_meta,
                resource_usage={
                    "dof_count": meta["dof_count"], "node_count": meta["node_count"],
                    "element_count": meta["element_count"], "free_dof_count": meta["free_dof_count"],
                    "peak_memory_mb": None,
                    "checkpoint": meta.get("checkpoint", {}),
                },
            )
            payload["write_incomplete_gmres_preview_checkpoint"] = bool(
                write_incomplete_gmres_preview_checkpoint
            )
            line_search_ready = (
                payload.get("line_search_preview", {}).get("status") == "ready"
            )
            direction_meta = payload.get("direction_solve_comparison", {}).get(
                direction_solver,
                {},
            )
            preview_checkpoint_allowed = bool(
                write_incomplete_gmres_preview_checkpoint
                and payload.get("status") == "review"
                and payload.get("reason_code") == PREVIEW_INCOMPLETE_GMRES_DIRECTION
                and direction_meta.get("status") == "preview"
            )
            if (
                output_final_checkpoint_npz is not None
                and line_search_ready
                and (payload.get("status") == "ready" or preview_checkpoint_allowed)
            ):
                line_search = payload["line_search_preview"]
                accepted_alpha = float(line_search["accepted_alpha"])
                p, recomputed_meta = solve_direction_assembled(
                    k_free,
                    residual_fn,
                    x0,
                    solver=direction_solver,
                        eps=float(jvp_eps),
                        ilu_drop_tol=ilu_drop_tol,
                        ilu_fill_factor=ilu_fill_factor,
                        ilu_shift_mode=ilu_shift_mode,
                        ilu_shift_mu=ilu_shift_mu,
                        gmres_maxiter=gmres_maxiter,
                        gmres_rtol=float(gmres_rtol),
                        allow_incomplete_gmres_direction=allow_incomplete_gmres_direction,
                        incomplete_gmres_relative_tolerance=float(
                            incomplete_gmres_relative_tolerance
                        ),
                )
                allowed_direction_statuses = {"ready"}
                if preview_checkpoint_allowed:
                    allowed_direction_statuses.add("preview")
                if (
                    p is None
                    or recomputed_meta.get("status") not in allowed_direction_statuses
                ):
                    payload["output_final_checkpoint"] = {
                        "written": False,
                        "reason_code": recomputed_meta.get(
                            "reason_code",
                            "ERR_DIRECTION_SOLVE_BLOCKED",
                        ),
                    }
                else:
                    final_x = np.asarray(x0, dtype=np.float64) + accepted_alpha * np.asarray(
                        p,
                        dtype=np.float64,
                    )
                    final_residual = np.asarray(residual_fn(final_x), dtype=np.float64)
                    full_u = np.asarray(meta["frame_inputs"]["u0"], dtype=np.float64).copy()
                    full_u[np.asarray(meta["free"], dtype=np.int64)] = final_x
                    payload["output_final_checkpoint"] = _write_checkpoint(
                        path=Path(output_final_checkpoint_npz),
                        load_scale=float(load_scale),
                        displacement_u=full_u,
                        final_residual=final_residual,
                        residual_before_n=line_search.get("residual_before_n"),
                        external_load_inf_n=meta.get("external_load_inf_n"),
                        accepted_alpha=accepted_alpha,
                        direction_solver=str(direction_meta.get("solver") or direction_solver),
                        direction_status=str(recomputed_meta.get("status") or ""),
                        incomplete_gmres_direction_preview=bool(
                            preview_checkpoint_allowed
                            and recomputed_meta.get("status") == "preview"
                        ),
                        preview_reason_code=str(
                            recomputed_meta.get("preview_reason_code") or ""
                        ),
                        frame_tangent_source=str(meta.get("frame_tangent_source") or ""),
                        shell_pressure_load_path_policy=str(
                            meta.get("shell_pressure_load_path_policy") or ""
                        ),
                        checkpoint_claim_boundary=(
                            "non_promoting_incomplete_gmres_preview_checkpoint_candidate"
                            if preview_checkpoint_allowed
                            else "non_promoting_sparse_direct_scaled_lsmr_checkpoint_candidate"
                        ),
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
    parser.add_argument("--checkpoint-npz", type=Path, default=None)
    parser.add_argument("--direction-solver", choices=list(DIRECTION_SOLVERS), default="sparse_direct_spsolve")
    parser.add_argument(
        "--global-newton-operator",
        choices=[GLOBAL_NEWTON_OPERATOR_CURRENT, GLOBAL_NEWTON_OPERATOR_PHYSICAL],
        default=GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    )
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument(
        "--frame-tangent-source",
        choices=FRAME_TANGENT_SOURCE_CHOICES,
        default=FRAME_TANGENT_SOURCE_SERVICE,
    )
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=SHELL_PRESSURE_LOAD_PATH_POLICIES,
        default="all_components",
    )
    parser.add_argument("--ilu-drop-tol", type=float, default=1.0e-4)
    parser.add_argument("--ilu-fill-factor", type=float, default=10.0)
    parser.add_argument(
        "--ilu-shift-mode",
        choices=["scalar_shift", "relative_diagonal_shift"],
        default="relative_diagonal_shift",
    )
    parser.add_argument("--ilu-shift-mu", type=float, default=1.0e-6)
    parser.add_argument("--gmres-maxiter", type=int, default=400)
    parser.add_argument("--gmres-rtol", type=float, default=1.0e-6)
    parser.add_argument(
        "--jvp-eps",
        type=float,
        default=1.0e-6,
        help="Opt-in central-difference epsilon for matrix-free JVP/parity diagnostics.",
    )
    parser.add_argument(
        "--allow-incomplete-gmres-direction",
        action="store_true",
        help="Preview non-converged GMRES directions that meet the residual-ratio tolerance.",
    )
    parser.add_argument(
        "--incomplete-gmres-relative-tolerance",
        type=float,
        default=0.0,
        help="Maximum linear residual ratio allowed for an incomplete GMRES preview direction.",
    )
    parser.add_argument(
        "--write-incomplete-gmres-preview-checkpoint",
        action="store_true",
        help=(
            "Write a non-promoting checkpoint for an accepted incomplete-GMRES preview "
            "line-search step."
        ),
    )
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"], default="real_per_element",
    )
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument(
        "--output-final-checkpoint-npz",
        type=Path,
        default=None,
        help="Optional non-promoting loadable checkpoint for an accepted line-search step.",
    )
    args = parser.parse_args()
    payload = run_g1_mgt_sparse_direct_physical_line_search_smoke(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        checkpoint_npz=args.checkpoint_npz,
        direction_solver=args.direction_solver, global_newton_operator=args.global_newton_operator,
        load_scale=args.load_scale, frame_tangent_source=args.frame_tangent_source,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        ilu_drop_tol=args.ilu_drop_tol,
        ilu_fill_factor=args.ilu_fill_factor,
        ilu_shift_mode=args.ilu_shift_mode,
        ilu_shift_mu=args.ilu_shift_mu,
        gmres_maxiter=args.gmres_maxiter,
        gmres_rtol=args.gmres_rtol,
        jvp_eps=args.jvp_eps,
        allow_incomplete_gmres_direction=args.allow_incomplete_gmres_direction,
        incomplete_gmres_relative_tolerance=args.incomplete_gmres_relative_tolerance,
        write_incomplete_gmres_preview_checkpoint=(
            args.write_incomplete_gmres_preview_checkpoint
        ),
        frame_service_tangent_source=args.frame_service_tangent_source,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
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
