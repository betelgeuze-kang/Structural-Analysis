#!/usr/bin/env python3
"""Replay cached residual-JVP correction vectors with wider alpha sweeps."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_mgt_cached_residual_jvp_batch_probe import (  # noqa: E402
    _parse_float_csv,
    _translation_metrics,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    _load_checkpoint,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_frame_hotspot_diagonal_newton_probe import _write_checkpoint  # noqa: E402
from run_mgt_residual_jacobian_consistency_probe import _max_abs  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-cached-residual-jvp-replay-probe.v1"
DEFAULT_CORRECTION_NPZ = (
    PRODUCTIZATION
    / "mgt_cached_residual_jvp_batch_component_dof_frontier_rows8_support24_probe.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "mgt_cached_residual_jvp_replay_probe.json"


def _npz_scalar_string(archive: np.lib.npyio.NpzFile, key: str) -> str | None:
    if key not in archive.files:
        return None
    value = np.asarray(archive[key])
    if value.shape == ():
        return str(value.item())
    return str(value)


def _load_correction_npz(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as archive:
        correction = np.asarray(archive["correction_u"], dtype=np.float64)
        payload: dict[str, Any] = {
            "path": str(path),
            "schema_version": _npz_scalar_string(archive, "schema_version"),
            "checkpoint_npz": _npz_scalar_string(archive, "checkpoint_npz"),
            "correction_u": correction,
            "correction_inf_m": _max_abs(correction),
            "target_row_count": int(
                np.asarray(archive["target_rows"]).size
                if "target_rows" in archive.files
                else 0
            ),
            "support_size": int(
                np.asarray(archive["support_cols"]).size
                if "support_cols" in archive.files
                else 0
            ),
        }
        if "target_global_dofs" in archive.files:
            payload["target_global_dofs"] = [
                int(value) for value in np.asarray(archive["target_global_dofs"]).tolist()
            ]
        if "support_global_dofs" in archive.files:
            payload["support_global_dofs"] = [
                int(value) for value in np.asarray(archive["support_global_dofs"]).tolist()
            ]
    return payload


def run_mgt_cached_residual_jvp_replay_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    correction_npz: Path = DEFAULT_CORRECTION_NPZ,
    output_json: Path | None = DEFAULT_OUT,
    output_final_checkpoint_npz: Path | None = None,
    promote_gate_eligible: bool = False,
    alpha_values: tuple[float, ...] = (1.0, 3.0e-1, 1.0e-1, 3.0e-2, 1.0e-2),
    allow_negative_alphas: bool = False,
    residual_tolerance_n: float = 1.0e-3,
    relative_increment_tolerance: float = 1.0e-4,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    correction_payload = _load_correction_npz(correction_npz)
    correction = np.asarray(correction_payload["correction_u"], dtype=np.float64)

    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    base_u = np.asarray(setup_meta["u0"], dtype=np.float64)
    base_started = time.perf_counter()
    _stiffness, f_ext, free, residual, rhs, _base_meta = assemble_residual(base_u)
    base_assembly_seconds = float(time.perf_counter() - base_started)
    free_idx = np.asarray(free, dtype=np.int64)
    base_residual = np.asarray(residual, dtype=np.float64)
    rhs_np = np.asarray(rhs, dtype=np.float64)
    base_residual_inf = _max_abs(base_residual)
    rhs_inf = _max_abs(rhs_np)
    max_abs_u = max(_max_abs(base_u), 1.0e-12)

    candidate_rows: list[dict[str, Any]] = []
    candidate_vectors: list[np.ndarray] = []
    candidate_residuals: list[np.ndarray] = []
    candidate_rhs: list[np.ndarray] = []
    residual_only_trial_count = 0
    full_assembly_trial_count = 0
    if correction.shape != base_u.shape:
        correction_shape_matches = False
    else:
        correction_shape_matches = True
        sweep_alpha_values = [float(value) for value in alpha_values]
        if allow_negative_alphas:
            sweep_alpha_values.extend(
                -float(value) for value in alpha_values if float(value) > 0.0
            )
        sweep_alpha_values = sorted(set(sweep_alpha_values), reverse=True)
        for alpha in sweep_alpha_values:
            alpha_float = float(alpha)
            candidate_u = base_u + alpha_float * correction
            trial_started = time.perf_counter()
            used_residual_only = False
            try:
                _k, _f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
                    candidate_u,
                    residual_only=True,
                    free_override=free_idx,
                    external_load_override=f_ext,
                )
                used_residual_only = True
                residual_only_trial_count += 1
            except TypeError:
                _k, _f, trial_free, trial_residual, trial_rhs, _trial_meta = assemble_residual(
                    candidate_u,
                    external_load_override=f_ext,
                )
                full_assembly_trial_count += 1
            trial_seconds = float(time.perf_counter() - trial_started)
            trial_free_idx = np.asarray(trial_free, dtype=np.int64)
            free_stable = bool(
                trial_free_idx.shape == free_idx.shape
                and np.array_equal(trial_free_idx, free_idx)
            )
            trial_residual_np = np.asarray(trial_residual, dtype=np.float64)
            trial_rhs_np = np.asarray(trial_rhs, dtype=np.float64)
            residual_inf = _max_abs(trial_residual_np)
            increment = _max_abs(candidate_u - base_u)
            max_abs_candidate = max(_max_abs(candidate_u), max_abs_u, 1.0e-12)
            metrics = _translation_metrics(candidate_u)
            candidate_rows.append(
                {
                    "alpha": alpha_float,
                    "free_dof_set_stable": free_stable,
                    "residual_only_assembly": bool(used_residual_only),
                    "assembly_seconds": trial_seconds,
                    "direct_residual_inf_n": residual_inf,
                    "direct_relative_residual_inf": residual_inf
                    / max(_max_abs(trial_rhs_np), rhs_inf, 1.0),
                    "improvement_inf_n": base_residual_inf - residual_inf,
                    "relative_improvement": (base_residual_inf - residual_inf)
                    / max(base_residual_inf, 1.0),
                    "relative_increment": increment / max_abs_candidate,
                    "max_increment_m": increment,
                    "max_translation_m": metrics["max_translation_m"],
                    "residual_gate_passed": residual_inf <= float(residual_tolerance_n),
                    "relative_increment_gate_passed": increment / max_abs_candidate
                    <= float(relative_increment_tolerance),
                }
            )
            candidate_vectors.append(np.asarray(candidate_u, dtype=np.float64).copy())
            candidate_residuals.append(trial_residual_np.copy())
            candidate_rhs.append(trial_rhs_np.copy())

    best_candidate_index, best_candidate_row = min(
        (
            (index, row)
            for index, row in enumerate(candidate_rows)
            if bool(row.get("free_dof_set_stable"))
        ),
        key=lambda item: float(item[1]["direct_residual_inf_n"]),
        default=(None, {}),
    )
    best_gate_candidate_index, best_gate_candidate_row = min(
        (
            (index, row)
            for index, row in enumerate(candidate_rows)
            if bool(row.get("free_dof_set_stable"))
            and bool(row.get("relative_increment_gate_passed"))
            and float(row.get("improvement_inf_n", 0.0)) > 0.0
        ),
        key=lambda item: float(item[1]["direct_residual_inf_n"]),
        default=(None, {}),
    )
    output_final_checkpoint: dict[str, Any] = {
        "written": False,
        "path": str(output_final_checkpoint_npz)
        if output_final_checkpoint_npz is not None
        else None,
        "reason": (
            "not_requested"
            if output_final_checkpoint_npz is None
            else "promote_gate_eligible_disabled"
            if not promote_gate_eligible
            else "correction_shape_mismatch"
            if not correction_shape_matches
            else "no_gate_eligible_candidate"
        ),
    }
    if (
        promote_gate_eligible
        and output_final_checkpoint_npz is not None
        and best_gate_candidate_index is not None
    ):
        checkpoint_meta, _loaded_u, state_history, residual_history = _load_checkpoint(
            checkpoint_npz
        )
        output_final_checkpoint = _write_checkpoint(
            path=output_final_checkpoint_npz,
            source_checkpoint_npz=checkpoint_npz,
            checkpoint_meta=checkpoint_meta,
            u0=base_u,
            final_u=candidate_vectors[int(best_gate_candidate_index)],
            base_residual=base_residual,
            final_residual=candidate_residuals[int(best_gate_candidate_index)],
            rhs=candidate_rhs[int(best_gate_candidate_index)],
            loaded_state_history=state_history,
            loaded_residual_history=residual_history,
        )
        output_final_checkpoint["written"] = True
        output_final_checkpoint["source"] = "cached_residual_jvp_replay_best_gate_candidate"
        output_final_checkpoint["alpha"] = float(
            best_gate_candidate_row.get("alpha") or 0.0
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "partial",
        "checkpoint": str(checkpoint_npz),
        "correction_npz": {
            key: value
            for key, value in correction_payload.items()
            if key != "correction_u"
        },
        "correction_checkpoint_matches_requested": bool(
            str(correction_payload.get("checkpoint_npz") or "") == str(checkpoint_npz)
        ),
        "correction_shape_matches": bool(correction_shape_matches),
        "output_final_checkpoint": output_final_checkpoint,
        "promoted_to_final_state": bool(output_final_checkpoint.get("written")),
        "base_direct_residual": {
            "direct_residual_inf_n": base_residual_inf,
            "direct_relative_residual_inf": base_residual_inf / max(rhs_inf, 1.0),
            "rhs_inf_n": rhs_inf,
        },
        "residual_only_trial_count": int(residual_only_trial_count),
        "full_assembly_trial_count": int(full_assembly_trial_count),
        "allow_negative_alphas": bool(allow_negative_alphas),
        "candidate_rows": candidate_rows,
        "best_candidate": best_candidate_row,
        "best_gate_eligible_candidate": best_gate_candidate_row,
        "base_assembly_seconds": base_assembly_seconds,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "Cached correction replay only. A promoted checkpoint remains an "
            "incremental frontier advance, not full nonlinear residual closure."
        ),
        "blockers": [
            "direct_residual_gate_not_closed",
            "cached_replay_is_diagnostic_not_final_newton_closure",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--correction-npz", type=Path, default=DEFAULT_CORRECTION_NPZ)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument("--promote-gate-eligible", action="store_true")
    parser.add_argument("--alpha-values", default="1,3e-1,1e-1,3e-2,1e-2")
    parser.add_argument("--allow-negative-alphas", action="store_true")
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    parser.add_argument("--relative-increment-tolerance", type=float, default=1.0e-4)
    parser.add_argument(
        "--allow-cpu-diagnostic",
        action="store_true",
        help="Acknowledge this replay is diagnostic and does not close G1 by itself.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_cpu_diagnostic:
        print("cached-residual-jvp-replay: blocked diagnostic requires --allow-cpu-diagnostic")
        return 2
    payload = run_mgt_cached_residual_jvp_replay_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        correction_npz=args.correction_npz,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        promote_gate_eligible=bool(args.promote_gate_eligible),
        alpha_values=_parse_float_csv(args.alpha_values),
        allow_negative_alphas=bool(args.allow_negative_alphas),
        residual_tolerance_n=args.residual_tolerance_n,
        relative_increment_tolerance=args.relative_increment_tolerance,
    )
    print(
        "cached-residual-jvp-replay: "
        f"promoted={payload['promoted_to_final_state']} "
        f"base={payload['base_direct_residual']['direct_residual_inf_n']} "
        f"best={payload['best_candidate'].get('direct_residual_inf_n')} "
        f"runtime={payload['runtime_seconds']:.3f}s -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
