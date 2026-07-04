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
from run_g1_true_newton_reference_candidate import (
    CHECKPOINT_SCHEMA,
    _load_initial_checkpoint_state,
    _max_abs,
    _translation_metrics,
)


SCHEMA_VERSION = "g1-adaptive-regularization-reference-newton.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_adaptive_regularization_reference_newton.local.json"
DEFAULT_MU_CANDIDATES = (0.1, 0.03, 0.01, 0.003, 0.001, 0.0003, 0.0001, 0.00003, 0.00001)
TANGENT_UPDATE_FIXED_REFERENCE = "fixed_reference"
TANGENT_UPDATE_PER_STEP_RELINEARIZED = "per_step_relinearized"
TANGENT_UPDATE_MODES = (
    TANGENT_UPDATE_FIXED_REFERENCE,
    TANGENT_UPDATE_PER_STEP_RELINEARIZED,
)

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
    allow_signed_direction_globalization: bool = False,
    return_final_state: bool = False,
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
            direction_sign = 1
            line_search_status = ls.get("status")
            reverse_status = None
            if line_search_status != "ready" and allow_signed_direction_globalization:
                reverse_ls = physical_residual_backtracking_line_search(
                    residual_fn, x, -p, jvp_action=-jvp_action, alphas=alphas,
                )
                reverse_status = reverse_ls.get("status")
                if reverse_status == "ready":
                    ls = reverse_ls
                    direction_sign = -1
                    line_search_status = "ready_reverse_direction"
            row = {"mu": mu, "direction_solve_status": "ready",
                   "line_search_status": line_search_status,
                   "forward_line_search_status": ls.get("status") if direction_sign == 1 else "no_descent_found",
                   "reverse_line_search_status": reverse_status,
                   "accepted_direction_sign": direction_sign if ls.get("status") == "ready" else None,
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
        p = float(best.get("accepted_direction_sign") or 1) * sel_solve(r)
        alpha = float(best["accepted_alpha"])
        ra = float(best["residual_after_n"])
        if ra > rb:
            monotonic = False
        history.append({"iteration": it, "residual_before_n": rb,
                        "candidate_results": candidate_results,
                        "selected_mu": sel_mu, "selected_alpha": alpha,
                        "accepted_direction_sign": int(best.get("accepted_direction_sign") or 1),
                        "line_search_status": best.get("line_search_status"),
                        "residual_after_n": ra,
                        "residual_reduction_ratio": (rb - ra) / max(rb, 1.0e-30)})
        x = x + alpha * np.asarray(p, dtype=np.float64)
    final_r = np.asarray(residual_fn(x), dtype=np.float64)
    final = _inf_norm(final_r) if _finite(final_r) else None
    result = {
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
    if return_final_state:
        result["final_state"] = x.copy()
    return result


def _matrix_from_rebuild_result(rebuilt: Any) -> Any:
    if isinstance(rebuilt, tuple):
        return rebuilt[0]
    return rebuilt


def run_adaptive_relinearized_newton(
    residual_fn: ResidualFn,
    x0: np.ndarray,
    tangent_rebuild_fn: Callable[[np.ndarray], Any],
    *,
    regularization_mode: str,
    mu_candidates: tuple[float, ...],
    max_newton_steps: int = 12,
    residual_gate_n: float = 5.0e-4,
    alphas: tuple[float, ...] = DEFAULT_ALPHAS,
    allow_signed_direction_globalization: bool = False,
    return_final_state: bool = False,
) -> dict[str, Any]:
    """Greedy adaptive Newton with per-step tangent re-linearization."""
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
        try:
            k_state = _matrix_from_rebuild_result(tangent_rebuild_fn(x))
        except Exception as exc:  # noqa: BLE001
            history.append({
                "iteration": it,
                "residual_before_n": rb,
                "candidate_results": [],
                "selected_mu": None,
                "tangent_rebuilt": False,
                "reason_code": f"tangent_rebuild_error:{type(exc).__name__}",
            })
            stop_reason = STOP_SOLVE_FAILED
            break
        mu_solvers = _prefactor_mu_solvers(k_state, regularization_mode, mu_candidates)
        if not mu_solvers:
            history.append({
                "iteration": it,
                "residual_before_n": rb,
                "candidate_results": [],
                "selected_mu": None,
                "tangent_rebuilt": True,
                "factorable_mu_count": 0,
            })
            stop_reason = STOP_SOLVE_FAILED
            break
        candidate_results: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
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
            jvp_action = physical_consistent_jvp(residual_fn, x, p)
            ls = physical_residual_backtracking_line_search(
                residual_fn, x, p, jvp_action=jvp_action, alphas=alphas,
            )
            direction_sign = 1
            line_search_status = ls.get("status")
            reverse_status = None
            if line_search_status != "ready" and allow_signed_direction_globalization:
                reverse_ls = physical_residual_backtracking_line_search(
                    residual_fn, x, -p, jvp_action=-jvp_action, alphas=alphas,
                )
                reverse_status = reverse_ls.get("status")
                if reverse_status == "ready":
                    ls = reverse_ls
                    direction_sign = -1
                    line_search_status = "ready_reverse_direction"
            row = {"mu": mu, "direction_solve_status": "ready",
                   "line_search_status": line_search_status,
                   "forward_line_search_status": ls.get("status") if direction_sign == 1 else "no_descent_found",
                   "reverse_line_search_status": reverse_status,
                   "accepted_direction_sign": direction_sign if ls.get("status") == "ready" else None,
                   "accepted_alpha": ls.get("accepted_alpha"),
                   "residual_after_n": ls.get("residual_after_n"),
                   "residual_reduction_ratio": ls.get("residual_reduction_ratio")}
            candidate_results.append(row)
            if ls.get("status") == "ready":
                if best is None or float(row["residual_after_n"]) < float(best["residual_after_n"]):
                    best = row
        if best is None:
            history.append({"iteration": it, "residual_before_n": rb,
                            "candidate_results": candidate_results, "selected_mu": None,
                            "tangent_rebuilt": True,
                            "factorable_mu_count": len(mu_solvers)})
            stop_reason = STOP_NO_DESCENT
            break
        sel_mu = best["mu"]
        sel_solve = next(s for m, s in mu_solvers if m == sel_mu)
        p = float(best.get("accepted_direction_sign") or 1) * sel_solve(r)
        alpha = float(best["accepted_alpha"])
        ra = float(best["residual_after_n"])
        if ra > rb:
            monotonic = False
        history.append({"iteration": it, "residual_before_n": rb,
                        "candidate_results": candidate_results,
                        "selected_mu": sel_mu, "selected_alpha": alpha,
                        "accepted_direction_sign": int(best.get("accepted_direction_sign") or 1),
                        "line_search_status": best.get("line_search_status"),
                        "residual_after_n": ra,
                        "residual_reduction_ratio": (rb - ra) / max(rb, 1.0e-30),
                        "tangent_rebuilt": True,
                        "factorable_mu_count": len(mu_solvers)})
        x = x + alpha * np.asarray(p, dtype=np.float64)
    final_r = np.asarray(residual_fn(x), dtype=np.float64)
    final = _inf_norm(final_r) if _finite(final_r) else None
    result = {
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
    if return_final_state:
        result["final_state"] = x.copy()
    return result


def _write_adaptive_checkpoint(
    *,
    path: Path,
    load_scale: float,
    final_free_state: np.ndarray,
    final_residual: np.ndarray,
    meta: dict[str, Any],
    residual_gate_n: float,
    steps_taken: int,
    residual_gate_passed: bool,
) -> dict[str, Any]:
    free = np.asarray(meta["free"], dtype=np.int64)
    frame_inputs = meta.get("frame_inputs") if isinstance(meta.get("frame_inputs"), dict) else {}
    u0_source = meta.get("u0", frame_inputs.get("u0"))
    if u0_source is None:
        raise KeyError("u0")
    u0 = np.asarray(u0_source, dtype=np.float64)
    final_u = u0.copy()
    final_u[free] = np.asarray(final_free_state, dtype=np.float64)
    final_residual_np = np.asarray(final_residual, dtype=np.float64)
    final_residual_inf = _max_abs(final_residual_np)
    rhs_inf = float(meta.get("external_load_inf_n") or 0.0)
    translation = _translation_metrics(final_u)
    shell_policy = str(meta.get("shell_pressure_load_path_policy") or "all_components")
    frame_tangent_source = str(
        meta.get("frame_tangent_source") or "service_material_plus_geometric_delta"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray(CHECKPOINT_SCHEMA),
        source_schema_version=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(float(load_scale), dtype=np.float64),
        displacement_u=final_u,
        residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_residual_inf_n=np.asarray(final_residual_inf, dtype=np.float64),
        direct_relative_residual_inf=np.asarray(
            final_residual_inf / max(rhs_inf, 1.0),
            dtype=np.float64,
        ),
        max_translation_m=np.asarray(translation["max_translation_m"], dtype=np.float64),
        accepted_history_count=np.asarray(0, dtype=np.int64),
        accepted_iteration_count=np.asarray(int(steps_taken), dtype=np.int64),
        residual_gate_n=np.asarray(float(residual_gate_n), dtype=np.float64),
        residual_gate_passed=np.asarray(bool(residual_gate_passed)),
        frame_tangent_source=np.asarray(frame_tangent_source),
        shell_pressure_load_path_policy=np.asarray(shell_policy),
        adaptive_regularization_candidate_only=np.asarray(True),
        promotes_g1_closure=np.asarray(False),
        checkpoint_claim_boundary=np.asarray(
            "non_promoting_adaptive_regularization_checkpoint_candidate"
        ),
    )
    return {
        "written": True,
        "path": str(path),
        "schema": CHECKPOINT_SCHEMA,
        "load_scale": float(load_scale),
        "dof_count": int(final_u.size),
        "free_dof_count": int(final_free_state.size),
        "direct_residual_inf_n": final_residual_inf,
        "direct_relative_residual_inf": final_residual_inf / max(rhs_inf, 1.0),
        "max_translation_m": translation["max_translation_m"],
        "accepted_iteration_count": int(steps_taken),
        "accepted_history_count": 0,
        "residual_gate_n": float(residual_gate_n),
        "residual_gate_passed": bool(residual_gate_passed),
        "frame_tangent_source": frame_tangent_source,
        "shell_pressure_load_path_policy": shell_policy,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This is a loadable adaptive-regularization checkpoint candidate only. "
            "It does not close G1 unless direct residual, increment, full-mesh, "
            "material breadth, and production ROCm/HIP gates also pass."
        ),
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
    frame_tangent_source: str = "service_material_plus_geometric_delta",
    shell_pressure_load_path_policy: str = "all_components",
    initial_checkpoint_npz: Path | None = None,
    tangent_update_mode: str = TANGENT_UPDATE_FIXED_REFERENCE,
    allow_signed_direction_globalization: bool = False,
    regularization_mode: str = "relative_diagonal_shift",
    mu_candidates: tuple[float, ...] = DEFAULT_MU_CANDIDATES,
    baseline_mu: float = 0.1,
    max_newton_steps: int = 12,
    residual_gate_n: float = 5.0e-4,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
    output_final_checkpoint_npz: Path | None = None,
) -> dict[str, Any]:
    mgt_model = Path(mgt_model)
    if tangent_update_mode not in TANGENT_UPDATE_MODES:
        raise ValueError(
            f"unknown tangent_update_mode {tangent_update_mode!r}; "
            f"expected {TANGENT_UPDATE_MODES!r}"
        )

    def _base() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_candidate_only": True,
            "promotes_g1_closure": False,
            "load_scale": load_scale,
            "frame_service_tangent_source": frame_service_tangent_source,
            "frame_tangent_source": frame_tangent_source,
            "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
            "initial_checkpoint_npz": str(initial_checkpoint_npz) if initial_checkpoint_npz else None,
            "output_final_checkpoint_npz": (
                str(output_final_checkpoint_npz) if output_final_checkpoint_npz else None
            ),
            "adaptive_strategy": {
                "mode": "greedy_per_step_mu_selection",
                "tangent_update_mode": tangent_update_mode,
                "allow_signed_direction_globalization": bool(allow_signed_direction_globalization),
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
                frame_tangent_source=frame_tangent_source,
                shell_pressure_load_path_policy=shell_pressure_load_path_policy,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                       "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                       "detail": f"{type(exc).__name__}:{exc}",
                       "history": [], "summary": {"stop_reason": "state_build_failed"}}
        else:
            initial_checkpoint: dict[str, Any] | None = None
            x_start = x0
            if initial_checkpoint_npz is not None:
                x_start, initial_checkpoint = _load_initial_checkpoint_state(
                    path=Path(initial_checkpoint_npz),
                    free=np.asarray(meta["free"], dtype=np.int64),
                    dof_count=int(meta["dof_count"]),
                    load_scale=float(load_scale),
                )
            k_free = meta["tangent_free_csr"]
            if tangent_update_mode == TANGENT_UPDATE_PER_STEP_RELINEARIZED:
                tangent_rebuild_fn = meta.get("tangent_rebuild_fn")
                if tangent_rebuild_fn is None:
                    raise KeyError("tangent_rebuild_fn")
                adaptive = run_adaptive_relinearized_newton(
                    residual_fn,
                    x_start,
                    tangent_rebuild_fn,
                    regularization_mode=regularization_mode,
                    mu_candidates=mu_candidates,
                    max_newton_steps=max_newton_steps,
                    residual_gate_n=residual_gate_n,
                    allow_signed_direction_globalization=allow_signed_direction_globalization,
                    return_final_state=output_final_checkpoint_npz is not None,
                )
                baseline = run_adaptive_relinearized_newton(
                    residual_fn,
                    x_start,
                    tangent_rebuild_fn,
                    regularization_mode=regularization_mode,
                    mu_candidates=(baseline_mu,),
                    max_newton_steps=max_newton_steps,
                    residual_gate_n=residual_gate_n,
                    allow_signed_direction_globalization=allow_signed_direction_globalization,
                )
            else:
                mu_solvers = _prefactor_mu_solvers(k_free, regularization_mode, mu_candidates)
                adaptive = run_adaptive_greedy_newton(
                    residual_fn,
                    x_start,
                    mu_solvers,
                    max_newton_steps=max_newton_steps,
                    residual_gate_n=residual_gate_n,
                    allow_signed_direction_globalization=allow_signed_direction_globalization,
                    return_final_state=output_final_checkpoint_npz is not None,
                )
                baseline_solvers = _prefactor_mu_solvers(k_free, regularization_mode, (baseline_mu,))
                baseline = run_adaptive_greedy_newton(
                    residual_fn,
                    x_start,
                    baseline_solvers,
                    max_newton_steps=max_newton_steps,
                    residual_gate_n=residual_gate_n,
                    allow_signed_direction_globalization=allow_signed_direction_globalization,
                )
            a_sum, b_sum = adaptive["summary"], baseline["summary"]
            beats = bool(a_sum["final_residual_n"] is not None and b_sum["final_residual_n"] is not None
                         and a_sum["final_residual_n"] < b_sum["final_residual_n"])
            status = "ready" if a_sum["stop_reason"] in {STOP_GATE, STOP_MAX_STEPS} else "review"
            output_final_checkpoint: dict[str, Any] | None = None
            final_state = adaptive.get("final_state")
            if output_final_checkpoint_npz is not None and final_state is not None:
                final_residual = np.asarray(residual_fn(final_state), dtype=np.float64)
                output_final_checkpoint = _write_adaptive_checkpoint(
                    path=Path(output_final_checkpoint_npz),
                    load_scale=float(load_scale),
                    final_free_state=np.asarray(final_state, dtype=np.float64),
                    final_residual=final_residual,
                    meta=meta,
                    residual_gate_n=float(residual_gate_n),
                    steps_taken=int(a_sum["steps_taken"]),
                    residual_gate_passed=bool(a_sum["residual_gate_passed"]),
                )
            payload = {
                **_base(),
                "status": status,
                "reason_code": a_sum["stop_reason"],
                "uses_real_mgt_model": True,
                "mgt_source": str(mgt_model),
                "initial_state": {
                    "source": (
                        "checkpoint" if initial_checkpoint is not None else "zero_reference_state"
                    ),
                    "checkpoint": initial_checkpoint,
                },
                "baseline_fixed_mu": {
                    "mu": baseline_mu,
                    "final_residual_n": b_sum["final_residual_n"],
                    "total_reduction_ratio": b_sum["total_reduction_ratio"],
                    "residual_gate_passed": b_sum["residual_gate_passed"],
                    "stop_reason": b_sum["stop_reason"],
                },
                "history": adaptive["history"],
                "summary": {**a_sum, "beats_fixed_mu_baseline": beats},
                "output_final_checkpoint": output_final_checkpoint,
                "resource_usage": {
                    "dof_count": meta["dof_count"], "free_dof_count": meta["free_dof_count"],
                    "element_count": meta["element_count"],
                    "factorable_mu_count": (
                        len(mu_solvers)
                        if tangent_update_mode == TANGENT_UPDATE_FIXED_REFERENCE
                        else None
                    ),
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
    parser.add_argument(
        "--frame-tangent-source",
        choices=["service_material_plus_geometric_delta", "force_based_residual_tangent"],
        default="service_material_plus_geometric_delta",
    )
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=["all_components", "attached_components_only", "structural_components_only"],
        default="all_components",
    )
    parser.add_argument("--initial-checkpoint-npz", type=Path, default=None)
    parser.add_argument(
        "--tangent-update-mode",
        choices=list(TANGENT_UPDATE_MODES),
        default=TANGENT_UPDATE_FIXED_REFERENCE,
    )
    parser.add_argument("--allow-signed-direction-globalization", action="store_true")
    parser.add_argument("--regularization-mode", default="relative_diagonal_shift")
    parser.add_argument("--mu-candidates", type=str, default=",".join(str(x) for x in DEFAULT_MU_CANDIDATES))
    parser.add_argument("--baseline-mu", type=float, default=0.1)
    parser.add_argument("--max-newton-steps", type=int, default=12)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    args = parser.parse_args()
    payload = run_g1_adaptive_regularization_reference_newton(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        frame_tangent_source=args.frame_tangent_source,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        initial_checkpoint_npz=args.initial_checkpoint_npz,
        tangent_update_mode=args.tangent_update_mode,
        allow_signed_direction_globalization=args.allow_signed_direction_globalization,
        regularization_mode=args.regularization_mode, mu_candidates=_parse_mu(args.mu_candidates),
        baseline_mu=args.baseline_mu, max_newton_steps=args.max_newton_steps,
        residual_gate_n=args.residual_gate_n, output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
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
