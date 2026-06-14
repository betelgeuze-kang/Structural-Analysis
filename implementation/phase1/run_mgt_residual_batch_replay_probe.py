#!/usr/bin/env python3
"""Validate batch residual-only replay for G1 JVP/alpha candidate acceleration."""

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

from mgt_frame_force_based_assembly import prepack_frame_force_based_assembly  # noqa: E402
from mgt_physical_residual_assembly import assemble_physical_internal_forces_batch  # noqa: E402
from run_mgt_direct_residual_newton_probe import DEFAULT_CHECKPOINT, PRODUCTIZATION  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-residual-batch-replay-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_residual_batch_replay_probe.json"


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _summary_seconds(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min_seconds": float(np.min(arr)) if arr.size else 0.0,
        "mean_seconds": float(np.mean(arr)) if arr.size else 0.0,
        "max_seconds": float(np.max(arr)) if arr.size else 0.0,
    }


def _candidate_state_batch(
    *,
    u0: np.ndarray,
    free: np.ndarray,
    batch_size: int,
    perturbation_scale: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    u_ref = np.asarray(u0, dtype=np.float64)
    free_dofs = np.asarray(free, dtype=np.int64)
    size = max(int(batch_size), 1)
    rows = np.repeat(u_ref[None, :], size, axis=0)
    meta: list[dict[str, Any]] = [{"kind": "checkpoint", "global_dof": None, "epsilon": 0.0}]
    if size == 1 or free_dofs.size == 0:
        return rows, meta
    selected = np.linspace(0, free_dofs.size - 1, num=size - 1, dtype=np.int64)
    for row_index, free_index in enumerate(selected.tolist(), start=1):
        global_dof = int(free_dofs[int(free_index)])
        sign = -1.0 if row_index % 2 == 0 else 1.0
        epsilon = sign * float(perturbation_scale) * max(abs(float(u_ref[global_dof])), 1.0)
        rows[row_index, global_dof] += epsilon
        meta.append(
            {
                "kind": "single_dof_fd_like_perturbation",
                "global_dof": global_dof,
                "free_index": int(free_index),
                "epsilon": float(epsilon),
            }
        )
    return rows, meta


def run_mgt_residual_batch_replay_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    shell_pressure_load_path_policy: str = "attached_components_only",
    batch_size: int = 64,
    reps: int = 3,
    perturbation_scale: float = 1.0e-6,
) -> dict[str, Any]:
    started = time.perf_counter()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    node_xyz = np.asarray(setup_meta["_node_xyz"], dtype=np.float64)
    frame_elements = list(setup_meta["_frame_elements"])
    elem_type_code = np.asarray(setup_meta["_elem_type_code"], dtype=np.int32)
    elem_section_id = np.asarray(setup_meta["_elem_section_id"], dtype=np.int32)
    elem_material_id = np.asarray(setup_meta["_elem_material_id"], dtype=np.int32)
    conn_ptr = np.asarray(setup_meta["_conn_ptr"], dtype=np.int64)
    conn_idx = np.asarray(setup_meta["_conn_idx"], dtype=np.int64)
    section_props = setup_meta["_section_props"]
    material_props = setup_meta["_material_props"]
    plate_thickness_props = setup_meta["_plate_thickness_props"]
    base_axial_forces = setup_meta["_base_axial_forces"]
    spring_stiffness = setup_meta["_spring_stiffness"]
    load_scale = float(setup_meta["load_scale"])
    frame_gravity_load_scale = float(setup_meta["frame_gravity_load_scale"])

    _k, f_ext, free, base_residual, rhs, base_meta = assemble_residual(u0)
    states, state_meta = _candidate_state_batch(
        u0=u0,
        free=free,
        batch_size=batch_size,
        perturbation_scale=perturbation_scale,
    )
    axial_forces = {
        int(elem_id): float(force) * frame_gravity_load_scale * load_scale
        for elem_id, force in base_axial_forces.items()
    }
    frame_force_cache = prepack_frame_force_based_assembly(
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    shell_operator_cache: dict[str, Any] = {}

    def sequential_once() -> np.ndarray:
        residual_rows: list[np.ndarray] = []
        for state in states:
            _seq_k, _seq_f, seq_free, seq_residual, _seq_rhs, _seq_meta = assemble_residual(
                state,
                external_load_override=f_ext,
                residual_only=True,
                free_override=free,
            )
            if not (seq_free.shape == free.shape and np.array_equal(seq_free, free)):
                raise RuntimeError("free DOF set changed during sequential residual replay")
            residual_rows.append(np.asarray(seq_residual, dtype=np.float64))
        return np.vstack(residual_rows)

    def batch_once() -> tuple[np.ndarray, dict[str, Any]]:
        f_int_batch, batch_meta = assemble_physical_internal_forces_batch(
            u_batch=states,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            shell_operator_cache=shell_operator_cache,
            frame_force_cache=frame_force_cache,
        )
        residual_batch = np.asarray(f_int_batch[:, free] - np.asarray(f_ext[free]), dtype=np.float64)
        return residual_batch, batch_meta

    # Warm both paths so the timing comparison is about replay, not shell operator construction.
    sequential_once()
    batch_once()

    sequential_times: list[float] = []
    batch_times: list[float] = []
    sequential_residual = np.zeros((0, int(free.size)), dtype=np.float64)
    batch_residual = np.zeros((0, int(free.size)), dtype=np.float64)
    batch_meta: dict[str, Any] = {}
    for _rep in range(max(int(reps), 1)):
        seq_started = time.perf_counter()
        sequential_residual = sequential_once()
        sequential_times.append(float(time.perf_counter() - seq_started))

        batch_started = time.perf_counter()
        batch_residual, batch_meta = batch_once()
        batch_times.append(float(time.perf_counter() - batch_started))

    diff = np.asarray(batch_residual - sequential_residual, dtype=np.float64)
    max_abs_difference = _max_abs(diff)
    seq_inf = np.max(np.abs(sequential_residual), axis=1) if sequential_residual.size else np.zeros(0)
    batch_inf = np.max(np.abs(batch_residual), axis=1) if batch_residual.size else np.zeros(0)
    inf_diff = np.asarray(batch_inf - seq_inf, dtype=np.float64)
    sequential_mean = float(np.mean(np.asarray(sequential_times, dtype=np.float64)))
    batch_mean = float(np.mean(np.asarray(batch_times, dtype=np.float64)))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if max_abs_difference <= 1.0e-7 else "warn",
        "mgt_path": str(mgt_path),
        "checkpoint_npz": str(checkpoint_npz),
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "batch_size": int(states.shape[0]),
        "dof_count": int(u0.size),
        "free_dof_count": int(free.size),
        "reps": int(max(int(reps), 1)),
        "perturbation_scale": float(perturbation_scale),
        "base_direct_residual_inf_n": _max_abs(base_residual),
        "rhs_inf_n": _max_abs(rhs),
        "sequential": _summary_seconds(sequential_times),
        "batch": _summary_seconds(batch_times),
        "speedup_factor": sequential_mean / max(batch_mean, 1.0e-12),
        "max_abs_residual_difference_n": max_abs_difference,
        "max_abs_residual_inf_difference_n": _max_abs(inf_diff),
        "max_sequential_candidate_residual_inf_n": float(np.max(seq_inf)) if seq_inf.size else 0.0,
        "min_sequential_candidate_residual_inf_n": float(np.min(seq_inf)) if seq_inf.size else 0.0,
        "max_batch_candidate_residual_inf_n": float(np.max(batch_inf)) if batch_inf.size else 0.0,
        "min_batch_candidate_residual_inf_n": float(np.min(batch_inf)) if batch_inf.size else 0.0,
        "state_meta_sample": state_meta[: min(len(state_meta), 8)],
        "base_meta_summary": {
            "residual_only_assembly": bool(base_meta.get("residual_only_assembly")),
            "shell_operator_cache_size": int(base_meta.get("shell_operator_cache_size") or 0),
            "free_dof_count": int(base_meta.get("free_dof_count") or 0),
        },
        "batch_meta": batch_meta,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "This validates a CPU batch residual-only replay interface for G1 JVP/alpha "
            "candidate evaluation. It is the host-side contract that a Rust/HIP backend can "
            "replace, but it does not claim full residual gate closure."
        ),
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only"),
        default="attached_components_only",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--perturbation-scale", type=float, default=1.0e-6)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_residual_batch_replay_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        batch_size=args.batch_size,
        reps=args.reps,
        perturbation_scale=args.perturbation_scale,
    )
    print(
        "mgt-residual-batch-replay: "
        f"status={payload['status']} "
        f"diff={payload['max_abs_residual_difference_n']:.6g} "
        f"speedup={payload['speedup_factor']:.3f}x "
        f"runtime={payload['runtime_seconds']:.3f}s -> {args.output_json}"
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
