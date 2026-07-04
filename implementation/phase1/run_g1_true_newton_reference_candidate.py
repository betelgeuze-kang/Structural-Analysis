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
import hashlib
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
    _direction_row_metadata,
    regularized_direction_solve_contract,
    run_multistep_newton,
    tangent_component_actions,
)


SCHEMA_VERSION = "g1-true-newton-reference-candidate.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_true_newton_reference_candidate.local.json"
DEFAULT_FINAL_CHECKPOINT_NPZ: Path | None = None
DEFAULT_INITIAL_CHECKPOINT_NPZ: Path | None = None

PARITY_TOLERANCE = 5.0e-2
CHECKPOINT_SCHEMA = "mgt-direct-residual-newton-state.v1"
LOAD_SCALE_TOLERANCE = 1.0e-12


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _translation_metrics(u: np.ndarray) -> dict[str, float]:
    arr = np.asarray(u, dtype=np.float64)
    if arr.size % 6 != 0:
        return {"max_translation_m": _max_abs(arr)}
    translations = arr.reshape((-1, 6))[:, :3]
    return {
        "max_translation_m": float(np.max(np.linalg.norm(translations, axis=1)))
        if translations.size
        else 0.0
    }


def _scalar_string(value: Any) -> str:
    arr = np.asarray(value)
    if arr.shape == ():
        return str(arr.item())
    return str(value)


def _scalar_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(np.asarray(value).item())
    except Exception:
        return default


def _scalar_int(value: Any, default: int = 0) -> int:
    try:
        return int(np.asarray(value).item())
    except Exception:
        return default


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load_initial_checkpoint_state(
    *,
    path: Path,
    free: np.ndarray,
    dof_count: int,
    load_scale: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    content_sha256 = _file_sha256(path)
    with np.load(path, allow_pickle=False) as archive:
        schema = _scalar_string(archive["checkpoint_schema"])
        checkpoint_load_scale = _scalar_float(archive["load_scale"])
        displacement = np.asarray(archive["displacement_u"], dtype=np.float64)
        residual_key = (
            "direct_residual_inf_n"
            if "direct_residual_inf_n" in archive.files
            else "residual_inf_n"
            if "residual_inf_n" in archive.files
            else ""
        )
        direct_residual_inf = (
            _scalar_float(archive[residual_key], default=float("nan"))
            if residual_key
            else float("nan")
        )
        accepted_iteration_count = _scalar_int(
            archive["accepted_iteration_count"]
            if "accepted_iteration_count" in archive.files
            else 0
        )
    if schema != CHECKPOINT_SCHEMA:
        raise ValueError(
            f"initial checkpoint schema {schema!r} does not match {CHECKPOINT_SCHEMA!r}"
        )
    if abs(float(checkpoint_load_scale) - float(load_scale)) > LOAD_SCALE_TOLERANCE:
        raise ValueError(
            "initial checkpoint load_scale "
            f"{checkpoint_load_scale} does not match requested {load_scale}"
        )
    if int(displacement.size) != int(dof_count):
        raise ValueError(
            f"initial checkpoint dof_count {displacement.size} does not match {dof_count}"
        )
    free_idx = np.asarray(free, dtype=np.int64)
    if free_idx.size and int(np.max(free_idx)) >= int(displacement.size):
        raise ValueError("initial checkpoint free DOF map is out of bounds")
    return displacement[free_idx].copy(), {
        "path": str(path),
        "content_sha256": content_sha256,
        "schema": schema,
        "load_scale": float(checkpoint_load_scale),
        "dof_count": int(displacement.size),
        "free_dof_count": int(free_idx.size),
        "accepted_iteration_count": int(accepted_iteration_count),
        "direct_residual_inf_n": float(direct_residual_inf),
    }


def _write_true_newton_checkpoint(
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
        true_newton_candidate_only=np.asarray(True),
        promotes_g1_closure=np.asarray(False),
        checkpoint_claim_boundary=np.asarray(
            "non_promoting_true_newton_checkpoint_candidate_residual_gate_not_required"
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
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This is a loadable true-Newton full-load checkpoint candidate only. "
            "It does not close G1 unless direct residual, increment, full-mesh, "
            "material breadth, and production ROCm/HIP gates also pass."
        ),
    }


def _make_modified_direction_fn(
    k_free: Any,
    mode: str,
    mu: float,
    *,
    row_metadata: dict[str, Any] | None = None,
    component_residual_fn: Any | None = None,
    tangent_component_stiffness_free: dict[str, Any] | None = None,
):
    k_reg, shift, scale_source = regularize_matrix(k_free, mode, mu)
    factor = splu(csc_matrix(k_reg))

    def direction_fn(x: np.ndarray, r: np.ndarray):
        try:
            p = np.asarray(factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            return None, {"reason_code": f"solve_error:{type(exc).__name__}"}
        contract, action_meta = regularized_direction_solve_contract(
            k_free,
            k_reg,
            p,
            r,
            regularization_mode=mode,
            regularization_mu=mu,
            effective_shift=shift,
            scale_source=scale_source,
        )
        return p, {
            "reason_code": "ok",
            "tangent_rebuilt": False,
            "direction_solve_contract": contract,
            "_row_metadata": row_metadata,
            "_component_residual_fn": component_residual_fn,
            "_tangent_component_actions": tangent_component_actions(
                tangent_component_stiffness_free,
                p,
            ),
            **action_meta,
        }

    return direction_fn


def _make_true_direction_fn(
    residual_fn,
    tangent_rebuild_fn,
    mode: str,
    mu: float,
    *,
    row_metadata: dict[str, Any] | None = None,
    component_residual_fn: Any | None = None,
):
    rng = np.random.default_rng(0)

    def direction_fn(x: np.ndarray, r: np.ndarray):
        try:
            rebuilt = tangent_rebuild_fn(x)
        except Exception as exc:  # noqa: BLE001
            return None, {"reason_code": f"tangent_rebuild_error:{type(exc).__name__}",
                          "solve_stop_reason": "solve_failed"}
        if isinstance(rebuilt, tuple):
            k_state, rebuild_meta = rebuilt
        else:
            k_state, rebuild_meta = rebuilt, {}
        # per-step parity: re-linearized tangent must match the physical residual JVP
        n = int(np.asarray(x).size)
        v = rng.standard_normal(n)
        v = v / max(float(np.linalg.norm(v)), 1.0e-30)
        parity = assembled_tangent_parity(k_state, residual_fn, x, relative_tolerance=PARITY_TOLERANCE)
        if not parity["pass"]:
            return None, {"reason_code": "assembled_tangent_parity_failed",
                          "solve_stop_reason": "parity_failed",
                          "assembled_tangent_parity_pass": False}
        k_reg, shift, scale_source = regularize_matrix(k_state, mode, mu)
        try:
            factor = splu(csc_matrix(k_reg))
            p = np.asarray(factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
        except Exception as exc:  # noqa: BLE001
            return None, {"reason_code": f"solve_error:{type(exc).__name__}",
                          "solve_stop_reason": "solve_failed"}
        contract, action_meta = regularized_direction_solve_contract(
            k_state,
            k_reg,
            p,
            r,
            regularization_mode=mode,
            regularization_mu=mu,
            effective_shift=shift,
            scale_source=scale_source,
        )
        return p, {
            "reason_code": "ok",
            "tangent_rebuilt": True,
            "assembled_tangent_parity_pass": True,
            "direction_solve_contract": contract,
            "_row_metadata": row_metadata,
            "_component_residual_fn": component_residual_fn,
            "_tangent_component_actions": tangent_component_actions(
                rebuild_meta.get("component_stiffness_free"),
                p,
            ),
            **action_meta,
        }

    return direction_fn


def run_g1_true_newton_reference_candidate(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_service_tangent_source: str = "real_per_element",
    frame_tangent_source: str = "service_material_plus_geometric_delta",
    regularization_mode: str = "relative_diagonal_shift",
    regularization_mu: float = 0.1,
    max_newton_steps: int = 12,
    residual_gate_n: float = 5.0e-4,
    allow_signed_direction_globalization: bool = False,
    initial_checkpoint_npz: Path | None = DEFAULT_INITIAL_CHECKPOINT_NPZ,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
    output_final_checkpoint_npz: Path | None = DEFAULT_FINAL_CHECKPOINT_NPZ,
) -> dict[str, Any]:
    mgt_model = Path(mgt_model)

    def _base() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_candidate_only": True,
            "promotes_g1_closure": False,
            "load_scale": load_scale,
            "initial_checkpoint_npz": str(initial_checkpoint_npz) if initial_checkpoint_npz else None,
            "frame_service_tangent_source": frame_service_tangent_source,
            "frame_tangent_source": frame_tangent_source,
            "regularization": {"mode": regularization_mode, "mu": regularization_mu, "fixed_or_adaptive": "fixed"},
            "newton_mode": "true_newton_per_step_relinearization",
            "material_tangent_update": {
                "mode": "real_per_element_state_updated",
                "state_updated": True,
                "claim_boundary": "not_material_newton_breadth",
            },
            "signed_direction_globalization": {
                "enabled": bool(allow_signed_direction_globalization),
                "claim_boundary": "non_promoting_diagnostic_globalization_only",
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
                frame_tangent_source=frame_tangent_source,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                       "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                       "detail": f"{type(exc).__name__}:{exc}",
                       "history": [], "summary": {"stop_reason": "state_build_failed"}}
        else:
            k_free = meta["tangent_free_csr"]
            tangent_rebuild_fn = meta["tangent_rebuild_fn"]
            initial_checkpoint: dict[str, Any] | None = None
            x_start = x0
            if initial_checkpoint_npz is not None:
                x_start, initial_checkpoint = _load_initial_checkpoint_state(
                    path=Path(initial_checkpoint_npz),
                    free=np.asarray(meta["free"], dtype=np.int64),
                    dof_count=int(meta["dof_count"]),
                    load_scale=float(load_scale),
                )
            initial_iteration_count = (
                int(initial_checkpoint.get("accepted_iteration_count", 0))
                if initial_checkpoint is not None
                else 0
            )
            row_metadata = _direction_row_metadata(meta)
            component_residual_fn = meta.get("component_residual_fn")

            # modified-Newton baseline (reference tangent reused)
            mod_dir = _make_modified_direction_fn(
                k_free,
                regularization_mode,
                regularization_mu,
                row_metadata=row_metadata,
                component_residual_fn=component_residual_fn,
                tangent_component_stiffness_free=meta.get(
                    "tangent_component_stiffness_free"
                ),
            )
            mod = run_multistep_newton(residual_fn, x_start, mod_dir,
                                       max_newton_steps=max_newton_steps,
                                       residual_gate_n=residual_gate_n,
                                       allow_signed_direction_globalization=(
                                           allow_signed_direction_globalization
                                       ))
            # true-Newton candidate (per-step re-linearization)
            true_dir = _make_true_direction_fn(
                residual_fn,
                tangent_rebuild_fn,
                regularization_mode,
                regularization_mu,
                row_metadata=row_metadata,
                component_residual_fn=component_residual_fn,
            )
            true = run_multistep_newton(residual_fn, x_start, true_dir,
                                        max_newton_steps=max_newton_steps, residual_gate_n=residual_gate_n,
                                        return_final_state=output_final_checkpoint_npz is not None,
                                        allow_signed_direction_globalization=(
                                            allow_signed_direction_globalization
                                        ))

            ts = true["summary"]
            status = "ready" if ts["stop_reason"] in {STOP_GATE, STOP_MAX_STEPS, STOP_STALLED} else "review"
            output_final_checkpoint: dict[str, Any] | None = None
            final_state = true.get("final_state")
            if output_final_checkpoint_npz is not None and final_state is not None:
                final_residual = np.asarray(residual_fn(final_state), dtype=np.float64)
                output_final_checkpoint = _write_true_newton_checkpoint(
                    path=Path(output_final_checkpoint_npz),
                    load_scale=float(load_scale),
                    final_free_state=np.asarray(final_state, dtype=np.float64),
                    final_residual=final_residual,
                    meta=meta,
                    residual_gate_n=float(residual_gate_n),
                    steps_taken=initial_iteration_count + int(ts["steps_taken"]),
                    residual_gate_passed=bool(ts["residual_gate_passed"]),
                )

            payload = {
                **_base(),
                "status": status,
                "reason_code": ts["stop_reason"],
                "uses_real_mgt_model": True,
                "mgt_source": str(mgt_model),
                "initial_state": {
                    "source": (
                        "checkpoint" if initial_checkpoint is not None else "zero_reference_state"
                    ),
                    "checkpoint": initial_checkpoint,
                    "initial_iteration_count": initial_iteration_count,
                },
                "modified_newton_baseline": {
                    "steps": mod["summary"]["steps_taken"],
                    "initial_residual_n": mod["summary"]["initial_residual_n"],
                    "final_residual_n": mod["summary"]["final_residual_n"],
                    "total_reduction_ratio": mod["summary"]["total_reduction_ratio"],
                    "residual_gate_passed": mod["summary"]["residual_gate_passed"],
                    "stop_reason": mod["summary"]["stop_reason"],
                    "signed_direction_globalization_used": mod["summary"].get(
                        "signed_direction_globalization_used"
                    ),
                    "signed_direction_step_count": mod["summary"].get(
                        "signed_direction_step_count"
                    ),
                    "directional_residual_jvp_contract": mod["summary"].get(
                        "directional_residual_jvp_contract"
                    ),
                },
                "true_newton_candidate": {
                    "steps": ts["steps_taken"],
                    "initial_checkpoint_iteration_count": initial_iteration_count,
                    "total_steps_including_initial_checkpoint": (
                        initial_iteration_count + int(ts["steps_taken"])
                    ),
                    "initial_residual_n": ts["initial_residual_n"],
                    "final_residual_n": ts["final_residual_n"],
                    "total_reduction_ratio": ts["total_reduction_ratio"],
                    "monotonic_residual_decrease": ts["monotonic_residual_decrease"],
                    "residual_gate_n": residual_gate_n,
                    "residual_gate_passed": ts["residual_gate_passed"],
                    "stop_reason": ts["stop_reason"],
                    "signed_direction_globalization_used": ts.get(
                        "signed_direction_globalization_used"
                    ),
                    "signed_direction_step_count": ts.get(
                        "signed_direction_step_count"
                    ),
                    "directional_residual_jvp_contract": ts.get(
                        "directional_residual_jvp_contract"
                    ),
                },
                "true_newton_faster_than_modified": bool(
                    ts["final_residual_n"] is not None
                    and mod["summary"]["final_residual_n"] is not None
                    and ts["final_residual_n"] < mod["summary"]["final_residual_n"]
                ),
                "history": true["newton_history"],
                "summary": ts,
                "output_final_checkpoint": output_final_checkpoint,
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
    parser.add_argument(
        "--frame-tangent-source",
        choices=["service_material_plus_geometric_delta", "force_based_residual_tangent"],
        default="service_material_plus_geometric_delta",
    )
    parser.add_argument("--regularization-mode", default="relative_diagonal_shift")
    parser.add_argument("--regularization-mu", type=float, default=0.1)
    parser.add_argument("--max-newton-steps", type=int, default=12)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--allow-signed-direction-globalization", action="store_true")
    parser.add_argument("--initial-checkpoint-npz", type=Path, default=DEFAULT_INITIAL_CHECKPOINT_NPZ)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=DEFAULT_FINAL_CHECKPOINT_NPZ)
    args = parser.parse_args()
    payload = run_g1_true_newton_reference_candidate(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        frame_tangent_source=args.frame_tangent_source,
        regularization_mode=args.regularization_mode, regularization_mu=args.regularization_mu,
        max_newton_steps=args.max_newton_steps, residual_gate_n=args.residual_gate_n,
        allow_signed_direction_globalization=args.allow_signed_direction_globalization,
        initial_checkpoint_npz=args.initial_checkpoint_npz,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
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
