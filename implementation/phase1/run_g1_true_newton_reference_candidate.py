#!/usr/bin/env python3
"""Non-promoting true Newton reference candidate (F2g-2).

F2g showed a modified Newton (reference tangent reused) reduces the physical
residual monotonically at the real MGT reference state but converges linearly and
plateaus above the gate. F2g-2 re-linearizes the regularized assembled tangent at
**every** step (true Newton) and contrasts it with the modified-Newton baseline.

Candidate runner only: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion, no material-Newton-breadth claim. Output is an
untracked ``*.local.json``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from g1_assembled_tangent_solve import assembled_tangent_parity
from g1_regularized_direction import PRODUCTION_LAMBDA, regularize_matrix
from run_g1_mgt_physical_line_search_smoke import (
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)
from run_g1_regularized_reference_newton_candidate import (
    STOP_GATE,
    STOP_MAX_STEPS,
    STOP_STALLED,
    run_multistep_newton,
)


SCHEMA_VERSION = "g1-true-newton-reference-candidate.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_true_newton_reference_candidate.local.json"

PARITY_TOLERANCE = 5.0e-2


def _make_modified_direction_fn(k_free: Any, mode: str, mu: float):
    k_reg, _shift, _src = regularize_matrix(k_free, mode, mu)
    factor = splu(csc_matrix(k_reg))

    def direction_fn(x: np.ndarray, r: np.ndarray):
        try:
            p = np.asarray(factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            return None, {"reason_code": f"solve_error:{type(exc).__name__}"}
        return p, {"reason_code": "ok", "tangent_rebuilt": False}

    return direction_fn


def _make_true_direction_fn(residual_fn, tangent_rebuild_fn, mode: str, mu: float):
    rng = np.random.default_rng(0)

    def direction_fn(x: np.ndarray, r: np.ndarray):
        try:
            k_state = tangent_rebuild_fn(x)
        except Exception as exc:  # noqa: BLE001
            return None, {"reason_code": f"tangent_rebuild_error:{type(exc).__name__}",
                          "solve_stop_reason": "solve_failed"}
        # per-step parity: re-linearized tangent must match the physical residual JVP
        n = int(np.asarray(x).size)
        v = rng.standard_normal(n)
        v = v / max(float(np.linalg.norm(v)), 1.0e-30)
        parity = assembled_tangent_parity(k_state, residual_fn, x, relative_tolerance=PARITY_TOLERANCE)
        if not parity["pass"]:
            return None, {"reason_code": "assembled_tangent_parity_failed",
                          "solve_stop_reason": "parity_failed",
                          "assembled_tangent_parity_pass": False}
        k_reg, _shift, _src = regularize_matrix(k_state, mode, mu)
        try:
            factor = splu(csc_matrix(k_reg))
            p = np.asarray(factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            return None, {"reason_code": f"solve_error:{type(exc).__name__}",
                          "solve_stop_reason": "solve_failed"}
        return p, {"reason_code": "ok", "tangent_rebuilt": True,
                   "assembled_tangent_parity_pass": True}

    return direction_fn


def run_g1_true_newton_reference_candidate(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_service_tangent_source: str = "real_per_element",
    regularization_mode: str = "relative_diagonal_shift",
    regularization_mu: float = 0.1,
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
            "regularization": {"mode": regularization_mode, "mu": regularization_mu, "fixed_or_adaptive": "fixed"},
            "newton_mode": "true_newton_per_step_relinearization",
            "material_tangent_update": {
                "mode": "real_per_element_state_updated",
                "state_updated": True,
                "claim_boundary": "not_material_newton_breadth",
            },
            "production_lambda": PRODUCTION_LAMBDA,
            "claim_boundary": "non_promoting_true_newton_reference_candidate_only",
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
            tangent_rebuild_fn = meta["tangent_rebuild_fn"]

            # modified-Newton baseline (reference tangent reused)
            mod_dir = _make_modified_direction_fn(k_free, regularization_mode, regularization_mu)
            mod = run_multistep_newton(residual_fn, x0, mod_dir,
                                       max_newton_steps=max_newton_steps, residual_gate_n=residual_gate_n)
            # true-Newton candidate (per-step re-linearization)
            true_dir = _make_true_direction_fn(residual_fn, tangent_rebuild_fn, regularization_mode, regularization_mu)
            true = run_multistep_newton(residual_fn, x0, true_dir,
                                        max_newton_steps=max_newton_steps, residual_gate_n=residual_gate_n)

            ts = true["summary"]
            status = "ready" if ts["stop_reason"] in {STOP_GATE, STOP_MAX_STEPS, STOP_STALLED} else "review"
            payload = {
                **_base(),
                "status": status,
                "reason_code": ts["stop_reason"],
                "uses_real_mgt_model": True,
                "mgt_source": str(mgt_model),
                "modified_newton_baseline": {
                    "steps": mod["summary"]["steps_taken"],
                    "initial_residual_n": mod["summary"]["initial_residual_n"],
                    "final_residual_n": mod["summary"]["final_residual_n"],
                    "total_reduction_ratio": mod["summary"]["total_reduction_ratio"],
                    "residual_gate_passed": mod["summary"]["residual_gate_passed"],
                    "stop_reason": mod["summary"]["stop_reason"],
                },
                "true_newton_candidate": {
                    "steps": ts["steps_taken"],
                    "initial_residual_n": ts["initial_residual_n"],
                    "final_residual_n": ts["final_residual_n"],
                    "total_reduction_ratio": ts["total_reduction_ratio"],
                    "monotonic_residual_decrease": ts["monotonic_residual_decrease"],
                    "residual_gate_n": residual_gate_n,
                    "residual_gate_passed": ts["residual_gate_passed"],
                    "stop_reason": ts["stop_reason"],
                },
                "true_newton_faster_than_modified": bool(
                    ts["final_residual_n"] is not None
                    and mod["summary"]["final_residual_n"] is not None
                    and ts["final_residual_n"] < mod["summary"]["final_residual_n"]
                ),
                "history": true["newton_history"],
                "summary": ts,
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
    parser.add_argument("--max-newton-steps", type=int, default=12)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_true_newton_reference_candidate(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        regularization_mode=args.regularization_mode, regularization_mu=args.regularization_mu,
        max_newton_steps=args.max_newton_steps, residual_gate_n=args.residual_gate_n,
        output_json=args.output_json,
    )
    tn = payload.get("true_newton_candidate", {})
    mod = payload.get("modified_newton_baseline", {})
    print(
        "g1-true-newton-reference-candidate: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"true[steps={tn.get('steps')} final={tn.get('final_residual_n')} gate={tn.get('residual_gate_passed')}] "
        f"mod[final={mod.get('final_residual_n')}] faster={payload.get('true_newton_faster_than_modified')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
