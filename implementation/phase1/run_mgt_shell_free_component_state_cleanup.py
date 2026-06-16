#!/usr/bin/env python3
"""Clean displacement state on unattached shell pressure components."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_shell_load_path import surface_pressure_load_path_components  # noqa: E402
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    PRODUCTIZATION,
    _load_checkpoint,
)
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    DOF_PER_NODE,
    _translation_metrics,
)
from run_mgt_residual_jacobian_consistency_probe import _component_breakdown, _max_abs  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-shell-free-component-state-cleanup.v1"
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION
    / "mgt_direct_residual_latest_frontier_shell_geometry_normal_row_support8_probe_final_checkpoint.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "mgt_shell_free_component_state_cleanup_probe.json"
DEFAULT_OUTPUT_CHECKPOINT = (
    PRODUCTIZATION / "mgt_shell_free_component_state_cleanup_checkpoint.npz"
)


def _component_cleanup_dofs(
    *,
    component_nodes: set[int],
    dof_per_node: int = DOF_PER_NODE,
    dof_slots: tuple[int, ...] = tuple(range(DOF_PER_NODE)),
) -> np.ndarray:
    dofs = [
        int(node) * int(dof_per_node) + int(slot)
        for node in sorted(int(node) for node in component_nodes)
        for slot in dof_slots
    ]
    return np.asarray(dofs, dtype=np.int64)


def _relax_component_state(
    *,
    u: np.ndarray,
    cleanup_dofs: np.ndarray,
    relaxation_factor: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    source = np.asarray(u, dtype=np.float64)
    cleaned = source.copy()
    dofs = np.asarray(cleanup_dofs, dtype=np.int64)
    valid = dofs[(dofs >= 0) & (dofs < int(cleaned.size))]
    before_values = cleaned[valid] if valid.size else np.asarray([], dtype=np.float64)
    cleaned[valid] *= float(relaxation_factor)
    after_values = cleaned[valid] if valid.size else np.asarray([], dtype=np.float64)
    delta = cleaned - source
    return cleaned, {
        "cleanup_dof_count": int(valid.size),
        "cleanup_max_abs_before_m": _max_abs(before_values),
        "cleanup_max_abs_after_m": _max_abs(after_values),
        "cleanup_delta_linf_m": _max_abs(delta),
    }


def _residual_snapshot(
    *,
    u: np.ndarray,
    assemble_residual: Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    top_count: int,
) -> tuple[dict[str, Any], np.ndarray]:
    _stiffness, _f_ext, free, residual, rhs, meta = assemble_residual(
        np.asarray(u, dtype=np.float64),
        include_component_forces=True,
    )
    residual_np = np.asarray(residual, dtype=np.float64)
    rhs_np = np.asarray(rhs, dtype=np.float64)
    component_forces = meta.pop("component_forces", {})
    component_breakdown = _component_breakdown(
        component_forces=component_forces if isinstance(component_forces, dict) else {},
        free=np.asarray(free, dtype=np.int64),
        residual=residual_np,
        rhs=rhs_np,
        top_count=top_count,
    )
    residual_inf = _max_abs(residual_np)
    rhs_inf = _max_abs(rhs_np)
    return {
        "direct_residual_inf_n": residual_inf,
        "direct_residual_l2_n": float(np.linalg.norm(residual_np)) if residual_np.size else 0.0,
        "direct_relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
        "rhs_inf_n": rhs_inf,
        "free_dof_count": int(np.asarray(free, dtype=np.int64).size),
        "component_inf_n": component_breakdown.get("component_inf_n"),
        "top_rows": component_breakdown.get("top_rows"),
        "top_row_dominant_component_counts": component_breakdown.get(
            "top_row_dominant_component_counts"
        ),
        "assembly_meta": meta,
    }, residual_np


def _append_state_history(
    *,
    state_history: np.ndarray | None,
    source_u: np.ndarray,
    cleaned_u: np.ndarray,
) -> np.ndarray:
    rows: list[np.ndarray] = []
    if (
        state_history is not None
        and state_history.ndim == 2
        and state_history.shape[1] == int(cleaned_u.size)
    ):
        rows.extend(np.asarray(row, dtype=np.float64).copy() for row in state_history)
    if not rows or not np.allclose(rows[-1], source_u):
        rows.append(np.asarray(source_u, dtype=np.float64).copy())
    if not np.allclose(rows[-1], cleaned_u):
        rows.append(np.asarray(cleaned_u, dtype=np.float64).copy())
    return np.vstack(rows).astype(np.float64)


def _append_residual_history(
    *,
    residual_history: np.ndarray | None,
    cleaned_residual: np.ndarray,
    state_history_count: int,
) -> np.ndarray:
    rows: list[np.ndarray] = []
    if (
        residual_history is not None
        and residual_history.ndim == 2
        and residual_history.shape[1] == int(cleaned_residual.size)
    ):
        rows.extend(np.asarray(row, dtype=np.float64).copy() for row in residual_history)
    while len(rows) < max(int(state_history_count) - 1, 0):
        rows.append(np.asarray(cleaned_residual, dtype=np.float64).copy())
    rows.append(np.asarray(cleaned_residual, dtype=np.float64).copy())
    return np.vstack(rows).astype(np.float64)


def run_mgt_shell_free_component_state_cleanup(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    output_checkpoint_npz: Path = DEFAULT_OUTPUT_CHECKPOINT,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    shell_pressure_load_path_policy: str = "attached_components_only",
    relaxation_factor: float = 0.0,
    residual_tolerance_n: float = 1.0e-3,
    top_residual_count: int = 24,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    if not mgt_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_missing"],
        }
    if not checkpoint_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["checkpoint_missing"],
        }

    checkpoint_meta, source_u, state_history, residual_history = _load_checkpoint(checkpoint_npz)
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        frame_gravity_load_scale=frame_gravity_load_scale,
        stiffness_scale_to_si=stiffness_scale_to_si,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )
    before_snapshot, _before_residual = _residual_snapshot(
        u=source_u,
        assemble_residual=assemble_residual,
        top_count=top_residual_count,
    )
    restrained = {
        int(dof)
        for dof in np.asarray(setup_meta.get("_restrained_dofs", []), dtype=np.int64).tolist()
    }
    components = surface_pressure_load_path_components(
        frame_elements=setup_meta.get("_frame_elements", []),
        elem_type_code=np.asarray(setup_meta.get("_elem_type_code", []), dtype=np.int32),
        conn_ptr=np.asarray(setup_meta.get("_conn_ptr", [0]), dtype=np.int64),
        conn_idx=np.asarray(setup_meta.get("_conn_idx", []), dtype=np.int64),
        restrained=restrained,
    )
    free_components = [component for component in components if not bool(component["attached"])]
    cleanup_nodes = {
        int(node)
        for component in free_components
        for node in component["surface_node_indices"]
    }
    cleanup_dofs = _component_cleanup_dofs(component_nodes=cleanup_nodes)
    cleaned_u, cleanup_meta = _relax_component_state(
        u=source_u,
        cleanup_dofs=cleanup_dofs,
        relaxation_factor=relaxation_factor,
    )
    after_snapshot, cleaned_residual = _residual_snapshot(
        u=cleaned_u,
        assemble_residual=assemble_residual,
        top_count=top_residual_count,
    )
    node_xyz = np.asarray(setup_meta.get("_node_xyz", np.zeros((0, 3))), dtype=np.float64)
    translation_metrics = _translation_metrics(cleaned_u, node_xyz)
    accepted_state_history = _append_state_history(
        state_history=state_history,
        source_u=source_u,
        cleaned_u=cleaned_u,
    )
    accepted_residual_history = _append_residual_history(
        residual_history=residual_history,
        cleaned_residual=cleaned_residual,
        state_history_count=int(accepted_state_history.shape[0]),
    )

    output_checkpoint_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_checkpoint_npz,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        source_transform_schema=np.asarray(SCHEMA_VERSION),
        load_scale=np.asarray(float(checkpoint_meta["load_scale"]), dtype=np.float64),
        displacement_u=np.asarray(cleaned_u, dtype=np.float64),
        residual_inf_n=np.asarray(after_snapshot["direct_residual_inf_n"], dtype=np.float64),
        direct_residual_inf_n=np.asarray(after_snapshot["direct_residual_inf_n"], dtype=np.float64),
        direct_relative_residual_inf=np.asarray(
            after_snapshot["direct_relative_residual_inf"],
            dtype=np.float64,
        ),
        fixed_point_relative_increment=np.asarray(0.0, dtype=np.float64),
        max_translation_m=np.asarray(translation_metrics["max_translation_m"], dtype=np.float64),
        accepted_state_history_u=accepted_state_history,
        accepted_residual_history=accepted_residual_history,
        source_checkpoint_path=np.asarray(str(checkpoint_npz)),
        shell_pressure_load_path_policy=np.asarray(str(shell_pressure_load_path_policy)),
        cleaned_surface_node_indices=np.asarray(sorted(cleanup_nodes), dtype=np.int64),
        cleaned_global_dofs=np.asarray(cleanup_dofs, dtype=np.int64),
        relaxation_factor=np.asarray(float(relaxation_factor), dtype=np.float64),
    )

    after_inf = float(after_snapshot["direct_residual_inf_n"])
    gate_passed = after_inf <= float(residual_tolerance_n)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if gate_passed else "partial",
        "mgt_path": str(mgt_path),
        "checkpoint": checkpoint_meta,
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "relaxation_factor": float(relaxation_factor),
        "surface_component_summary": {
            "surface_component_count": int(len(components)),
            "free_pressure_surface_component_count": int(len(free_components)),
            "cleaned_surface_node_count": int(len(cleanup_nodes)),
            "cleaned_dof_count": int(cleanup_meta["cleanup_dof_count"]),
            "free_components": [
                {
                    "surface_element_count": int(len(component["surface_element_indices"])),
                    "surface_node_count": int(len(component["surface_node_indices"])),
                    "surface_element_indices_head": [
                        int(elem) for elem in component["surface_element_indices"][:12]
                    ],
                    "surface_node_indices": [
                        int(node) for node in component["surface_node_indices"]
                    ],
                    "frame_connected_node_count": int(component["frame_connected_node_count"]),
                    "restrained_translation_dof_count": int(
                        component["restrained_translation_dof_count"]
                    ),
                }
                for component in free_components
            ],
        },
        "cleanup": cleanup_meta,
        "before_cleanup_direct_residual": before_snapshot,
        "after_cleanup_direct_residual": after_snapshot,
        "residual_gate": {
            "tolerance_n": float(residual_tolerance_n),
            "passed": bool(gate_passed),
        },
        "output_checkpoint": {
            "written": True,
            "path": str(output_checkpoint_npz),
            "schema": "mgt-direct-residual-newton-state.v1",
            "direct_residual_inf_n": after_inf,
            "source_checkpoint_path": str(checkpoint_npz),
        },
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "Diagnostic/correction-lane state transform: displacement DOFs belonging only to "
            "surface shell components with no frame-connected node and no authored translational "
            "restraint are relaxed after the attached-only pressure policy suppresses their load."
        ),
        "blockers": []
        if gate_passed
        else [
            "direct_residual_gate_not_closed",
            "remaining_attached_shell_component_residual_requires_correction",
        ],
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
    parser.add_argument("--output-checkpoint-npz", type=Path, default=DEFAULT_OUTPUT_CHECKPOINT)
    parser.add_argument("--frame-gravity-load-scale", type=float, default=0.01)
    parser.add_argument("--stiffness-scale-to-si", type=float, default=1000.0)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only", "structural_components_only"),
        default="attached_components_only",
    )
    parser.add_argument("--relaxation-factor", type=float, default=0.0)
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    parser.add_argument("--top-residual-count", type=int, default=24)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_shell_free_component_state_cleanup(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        output_checkpoint_npz=args.output_checkpoint_npz,
        frame_gravity_load_scale=args.frame_gravity_load_scale,
        stiffness_scale_to_si=args.stiffness_scale_to_si,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        relaxation_factor=args.relaxation_factor,
        residual_tolerance_n=args.residual_tolerance_n,
        top_residual_count=args.top_residual_count,
    )
    print(
        "mgt-shell-free-component-state-cleanup:",
        f"{payload.get('status')} before={payload.get('before_cleanup_direct_residual', {}).get('direct_residual_inf_n')} "
        f"after={payload.get('after_cleanup_direct_residual', {}).get('direct_residual_inf_n')} "
        f"-> {args.output_json}",
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
