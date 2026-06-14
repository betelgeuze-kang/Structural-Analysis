#!/usr/bin/env python3
"""Validate prepacked frame force-based residual replay for G1."""

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

from mgt_frame_force_based_assembly import (  # noqa: E402
    assemble_frame_force_based_f_int,
    prepack_frame_force_based_assembly,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_residual_jacobian_consistency_probe import _max_abs  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-frame-force-fastpath-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_frame_force_fastpath_probe.json"


def _time_call(fn: Any, *, reps: int) -> tuple[Any, list[float]]:
    values: list[float] = []
    result: Any = None
    for _idx in range(max(int(reps), 1)):
        started = time.perf_counter()
        result = fn()
        values.append(float(time.perf_counter() - started))
    return result, values


def _summary_seconds(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min_seconds": float(np.min(arr)) if arr.size else 0.0,
        "mean_seconds": float(np.mean(arr)) if arr.size else 0.0,
        "max_seconds": float(np.max(arr)) if arr.size else 0.0,
    }


def run_mgt_frame_force_fastpath_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    reps: int = 8,
) -> dict[str, Any]:
    started = time.perf_counter()
    _assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    node_xyz = np.asarray(setup_meta["_node_xyz"], dtype=np.float64)
    frame_elements = list(setup_meta["_frame_elements"])
    section_props = setup_meta["_section_props"]
    material_props = setup_meta["_material_props"]
    load_scale = float(setup_meta["load_scale"])
    frame_gravity_load_scale = float(setup_meta["frame_gravity_load_scale"])
    base_axial_forces = setup_meta["_base_axial_forces"]
    axial_forces = {
        int(elem_id): float(force) * frame_gravity_load_scale * load_scale
        for elem_id, force in base_axial_forces.items()
    }

    pack_started = time.perf_counter()
    prepacked = prepack_frame_force_based_assembly(
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    pack_seconds = float(time.perf_counter() - pack_started)

    perturb = np.zeros_like(u0)
    if perturb.size:
        indices = np.linspace(0, perturb.size - 1, num=min(17, perturb.size), dtype=np.int64)
        perturb[indices] = np.linspace(-1.0e-9, 1.0e-9, num=indices.size)
    states = [("checkpoint", u0), ("checkpoint_plus_micro_perturb", u0 + perturb)]

    state_rows: list[dict[str, Any]] = []
    all_diff_inf = 0.0
    all_diff_l2 = 0.0
    original_times: list[float] = []
    fast_times: list[float] = []
    for label, state_u in states:
        (original_result, original_state_times) = _time_call(
            lambda: assemble_frame_force_based_f_int(
                u=state_u,
                node_xyz=node_xyz,
                frame_elements=frame_elements,
                section_props=section_props,
                material_props=material_props,
                element_axial_forces=axial_forces,
                include_geometric=True,
            ),
            reps=max(int(reps), 1),
        )
        (fast_result, fast_state_times) = _time_call(
            lambda: assemble_frame_force_based_f_int(
                u=state_u,
                node_xyz=node_xyz,
                frame_elements=frame_elements,
                section_props=section_props,
                material_props=material_props,
                element_axial_forces=axial_forces,
                include_geometric=True,
                prepacked=prepacked,
            ),
            reps=max(int(reps), 1),
        )
        original_force, original_meta = original_result
        fast_force, fast_meta = fast_result
        diff = np.asarray(fast_force, dtype=np.float64) - np.asarray(
            original_force,
            dtype=np.float64,
        )
        diff_inf = _max_abs(diff)
        diff_l2 = float(np.linalg.norm(diff)) if diff.size else 0.0
        force_inf = max(_max_abs(original_force), 1.0)
        all_diff_inf = max(all_diff_inf, diff_inf)
        all_diff_l2 = max(all_diff_l2, diff_l2)
        original_times.extend(original_state_times)
        fast_times.extend(fast_state_times)
        state_rows.append(
            {
                "state": label,
                "max_abs_difference_n": diff_inf,
                "l2_difference_n": diff_l2,
                "relative_difference_inf": diff_inf / force_inf,
                "original": _summary_seconds(original_state_times),
                "fastpath": _summary_seconds(fast_state_times),
                "original_meta": original_meta,
                "fastpath_meta": fast_meta,
            }
        )

    original_mean = float(np.mean(np.asarray(original_times, dtype=np.float64)))
    fast_mean = float(np.mean(np.asarray(fast_times, dtype=np.float64)))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all_diff_inf <= 1.0e-6 else "warn",
        "mgt_path": str(mgt_path),
        "checkpoint_npz": str(checkpoint_npz),
        "frame_element_count": int(len(frame_elements)),
        "dof_count": int(u0.size),
        "prepack_seconds": pack_seconds,
        "reps_per_state": int(reps),
        "state_rows": state_rows,
        "max_abs_difference_n": all_diff_inf,
        "max_l2_difference_n": all_diff_l2,
        "original_mean_seconds": original_mean,
        "fastpath_mean_seconds": fast_mean,
        "speedup_factor": original_mean / max(fast_mean, 1.0e-12),
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "Validates the prepacked frame force replay only. This does not close "
            "the full G1 residual gate; it reduces the residual replay cost that "
            "dominates finite-difference/JVP polishing."
        ),
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
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reps", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_frame_force_fastpath_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        reps=args.reps,
    )
    print(
        "mgt-frame-force-fastpath: "
        f"status={payload['status']} "
        f"diff={payload['max_abs_difference_n']:.6g} "
        f"speedup={payload['speedup_factor']:.3f}x "
        f"runtime={payload['runtime_seconds']:.3f}s -> {args.output_json}"
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
