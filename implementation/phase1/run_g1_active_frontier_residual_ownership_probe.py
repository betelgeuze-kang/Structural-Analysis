#!/usr/bin/env python3
"""Probe residual ownership at the active-set full-load frontier."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_g1_mgt_physical_line_search_smoke import (  # noqa: E402
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)
from run_g1_true_newton_reference_candidate import _max_abs  # noqa: E402


SCHEMA_VERSION = "g1-active-frontier-residual-ownership-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_active_frontier_residual_ownership_probe.json"
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")


def _load_checkpoint_free_state(
    *,
    checkpoint_npz: Path,
    free: np.ndarray,
    dof_count: int,
) -> dict[str, Any]:
    with np.load(checkpoint_npz, allow_pickle=False) as archive:
        displacement = np.asarray(archive["displacement_u"], dtype=np.float64)
        schema = str(np.asarray(archive["checkpoint_schema"]).item())
        load_scale = float(np.asarray(archive["load_scale"]).item())
        residual_key = (
            "direct_residual_inf_n"
            if "direct_residual_inf_n" in archive.files
            else "residual_inf_n"
        )
        direct_residual = float(np.asarray(archive[residual_key]).item())
    if int(displacement.size) != int(dof_count):
        raise ValueError(
            f"checkpoint dof_count {displacement.size} does not match {dof_count}"
        )
    free_idx = np.asarray(free, dtype=np.int64)
    return {
        "schema": schema,
        "load_scale": load_scale,
        "direct_residual_inf_n": direct_residual,
        "full_displacement": displacement.copy(),
        "free_state": displacement[free_idx].copy(),
    }


def _component_free_values(
    *,
    component_forces: dict[str, np.ndarray],
    free: np.ndarray,
    residual_size: int,
) -> dict[str, np.ndarray]:
    free_idx = np.asarray(free, dtype=np.int64)
    values_by_name: dict[str, np.ndarray] = {}
    for name, values in component_forces.items():
        arr = np.asarray(values, dtype=np.float64)
        if int(arr.size) == int(residual_size):
            values_by_name[str(name)] = arr.copy()
            continue
        if free_idx.size and int(arr.size) > int(np.max(free_idx)):
            values_by_name[str(name)] = arr[free_idx].copy()
            continue
        raise ValueError(
            f"component {name!r} size {arr.size} does not match free residual "
            f"size {residual_size} or global free map"
        )
    return values_by_name


def _top_rows(values: np.ndarray, top_count: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if not arr.size:
        return np.asarray([], dtype=np.int64)
    count = min(max(int(top_count), 1), int(arr.size))
    rows = np.argpartition(np.abs(arr), -count)[-count:]
    return rows[np.argsort(-np.abs(arr[rows]))].astype(np.int64)


def _balance_driver(
    *,
    dominant_component: str,
    max_component_abs: float,
    external_abs: float,
    tolerance: float,
) -> str:
    if max_component_abs <= tolerance and external_abs > tolerance:
        return "external_only_unassembled"
    if external_abs > max_component_abs * 1.1 and external_abs > tolerance:
        return "external_load_balance"
    if max_component_abs > external_abs * 1.1 and max_component_abs > tolerance:
        return f"{dominant_component}_internal_force"
    if max_component_abs <= tolerance and external_abs <= tolerance:
        return "near_zero_balance"
    return "component_external_cancellation"


def residual_ownership_breakdown(
    *,
    residual: np.ndarray,
    component_forces: dict[str, np.ndarray],
    free: np.ndarray,
    node_id: np.ndarray | None = None,
    dof_per_node: int = 6,
    top_count: int = 16,
    load_derivative: np.ndarray | None = None,
    tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    residual_np = np.asarray(residual, dtype=np.float64)
    free_idx = np.asarray(free, dtype=np.int64)
    if int(free_idx.size) != int(residual_np.size):
        raise ValueError("free map size must match residual size")
    component_free = _component_free_values(
        component_forces=component_forces,
        free=free_idx,
        residual_size=int(residual_np.size),
    )
    internal_sum = np.zeros_like(residual_np)
    for values in component_free.values():
        internal_sum += values
    inferred_external = internal_sum - residual_np
    load_derivative_np = (
        np.asarray(load_derivative, dtype=np.float64)
        if load_derivative is not None
        else None
    )
    if load_derivative_np is not None and load_derivative_np.size != residual_np.size:
        raise ValueError("load_derivative size must match residual size")

    component_inf = {
        name: _max_abs(values) for name, values in sorted(component_free.items())
    }
    node_ids = np.asarray(node_id, dtype=np.int64) if node_id is not None else None
    rows: list[dict[str, Any]] = []
    dominant_counts: dict[str, int] = {}
    balance_counts: dict[str, int] = {}
    for row in _top_rows(residual_np, top_count).tolist():
        component_values = {
            name: float(values[int(row)])
            for name, values in sorted(component_free.items())
        }
        dominant_component = max(
            component_values,
            key=lambda name: abs(component_values[name]),
            default="none",
        )
        max_component_abs = max(
            (abs(value) for value in component_values.values()),
            default=0.0,
        )
        external_value = float(inferred_external[int(row)])
        driver = _balance_driver(
            dominant_component=dominant_component,
            max_component_abs=float(max_component_abs),
            external_abs=abs(external_value),
            tolerance=float(tolerance),
        )
        dominant_counts[dominant_component] = (
            dominant_counts.get(dominant_component, 0) + 1
        )
        balance_counts[driver] = balance_counts.get(driver, 0) + 1
        global_dof = int(free_idx[int(row)])
        node_index = int(global_dof // int(dof_per_node))
        local_dof_index = int(global_dof % int(dof_per_node))
        item: dict[str, Any] = {
            "reduced_index": int(row),
            "global_dof": global_dof,
            "node_index": node_index,
            "local_dof_index": local_dof_index,
            "dof_label": (
                DOF_LABELS[local_dof_index]
                if 0 <= local_dof_index < len(DOF_LABELS)
                else f"DOF{local_dof_index}"
            ),
            "residual_n": float(residual_np[int(row)]),
            "residual_abs_n": float(abs(residual_np[int(row)])),
            "internal_sum_n": float(internal_sum[int(row)]),
            "inferred_external_load_n": external_value,
            "component_values_n": component_values,
            "dominant_internal_component": dominant_component,
            "max_component_abs_n": float(max_component_abs),
            "balance_driver": driver,
            "residual_reconstruction_error_n": float(
                internal_sum[int(row)] - external_value - residual_np[int(row)]
            ),
        }
        if node_ids is not None and 0 <= node_index < int(node_ids.size):
            item["node_id"] = int(node_ids[node_index])
        if load_derivative_np is not None:
            item["load_derivative_n_per_load"] = float(load_derivative_np[int(row)])
        rows.append(item)

    top_row = rows[0] if rows else {}
    return {
        "top_residual_inf_n": _max_abs(residual_np),
        "top_count": int(min(max(int(top_count), 1), int(residual_np.size)))
        if residual_np.size
        else 0,
        "component_inf_n": component_inf,
        "internal_sum_inf_n": _max_abs(internal_sum),
        "inferred_external_load_inf_n": _max_abs(inferred_external),
        "load_derivative_inf_n_per_load": (
            _max_abs(load_derivative_np) if load_derivative_np is not None else None
        ),
        "top_row_dominant_internal_component_counts": dominant_counts,
        "top_row_balance_driver_counts": balance_counts,
        "top_row": top_row,
        "top_rows": rows,
        "claim_boundary": (
            "Residual ownership breakdown only. It identifies component/load "
            "balance at the active-set frontier and does not promote G1 closure."
        ),
    }


def run_g1_active_frontier_residual_ownership_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    load_scale: float = 1.0,
    frame_tangent_source: str = "force_based_residual_tangent",
    shell_pressure_load_path_policy: str = "all_components",
    top_count: int = 16,
    load_derivative_eps: float = 1.0e-3,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    residual_fn, _x0, meta = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=float(load_scale),
        frame_tangent_source=frame_tangent_source,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )
    free = np.asarray(meta["free"], dtype=np.int64)
    checkpoint = _load_checkpoint_free_state(
        checkpoint_npz=Path(checkpoint_npz),
        free=free,
        dof_count=int(meta["dof_count"]),
    )
    x = np.asarray(checkpoint["free_state"], dtype=np.float64)
    residual = np.asarray(residual_fn(x), dtype=np.float64)
    component_fn = meta.get("component_residual_fn")
    if not callable(component_fn):
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "reason_code": "component_residual_fn_missing",
            "promotes_g1_closure": False,
            "claim_boundary": "No component ownership claim without component residual function.",
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return payload
    components = {
        str(name): np.asarray(values, dtype=np.float64)
        for name, values in component_fn(x).items()
    }

    load_derivative: np.ndarray | None = None
    free_maps_match = True
    if float(load_derivative_eps) > 0.0:
        eps = float(load_derivative_eps)
        residual_plus_fn, _xp, meta_plus = build_mgt_physical_residual_closure(
            mgt_path=Path(mgt_model),
            roundtrip_npz=None,
            load_scale=float(load_scale) + eps,
            frame_tangent_source=frame_tangent_source,
            shell_pressure_load_path_policy=shell_pressure_load_path_policy,
        )
        residual_minus_fn, _xm, meta_minus = build_mgt_physical_residual_closure(
            mgt_path=Path(mgt_model),
            roundtrip_npz=None,
            load_scale=float(load_scale) - eps,
            frame_tangent_source=frame_tangent_source,
            shell_pressure_load_path_policy=shell_pressure_load_path_policy,
        )
        free_plus = np.asarray(meta_plus["free"], dtype=np.int64)
        free_minus = np.asarray(meta_minus["free"], dtype=np.int64)
        free_maps_match = bool(
            free.shape == free_plus.shape
            and np.array_equal(free, free_plus)
            and free.shape == free_minus.shape
            and np.array_equal(free, free_minus)
        )
        if free_maps_match:
            residual_plus = np.asarray(residual_plus_fn(x), dtype=np.float64)
            residual_minus = np.asarray(residual_minus_fn(x), dtype=np.float64)
            load_derivative = (residual_plus - residual_minus) / (2.0 * eps)

    breakdown = residual_ownership_breakdown(
        residual=residual,
        component_forces=components,
        free=free,
        node_id=np.asarray(meta.get("node_id"), dtype=np.int64),
        dof_per_node=int(meta.get("dof_per_node") or 6),
        top_count=int(top_count),
        load_derivative=load_derivative,
    )
    top_row = breakdown.get("top_row") if isinstance(breakdown.get("top_row"), dict) else {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "is_candidate_only": True,
        "promotes_g1_closure": False,
        "mgt_model": str(mgt_model),
        "checkpoint_npz": str(checkpoint_npz),
        "load_scale": float(load_scale),
        "frame_tangent_source": frame_tangent_source,
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "top_count": int(top_count),
        "load_derivative_eps": float(load_derivative_eps),
        "load_derivative_free_dof_maps_match": free_maps_match,
        "checkpoint": {
            key: value
            for key, value in checkpoint.items()
            if key not in {"free_state", "full_displacement"}
        },
        "summary": {
            "top_residual_inf_n": breakdown["top_residual_inf_n"],
            "residual_gate_passed": breakdown["top_residual_inf_n"] <= 5.0e-4,
            "top_row_global_dof": top_row.get("global_dof"),
            "top_row_node_id": top_row.get("node_id"),
            "top_row_node_index": top_row.get("node_index"),
            "top_row_dof_label": top_row.get("dof_label"),
            "top_row_residual_n": top_row.get("residual_n"),
            "top_row_internal_sum_n": top_row.get("internal_sum_n"),
            "top_row_inferred_external_load_n": top_row.get(
                "inferred_external_load_n"
            ),
            "top_row_dominant_internal_component": top_row.get(
                "dominant_internal_component"
            ),
            "top_row_balance_driver": top_row.get("balance_driver"),
            "top_row_load_derivative_n_per_load": top_row.get(
                "load_derivative_n_per_load"
            ),
            "dominant_internal_component_counts": breakdown[
                "top_row_dominant_internal_component_counts"
            ],
            "balance_driver_counts": breakdown["top_row_balance_driver_counts"],
            "component_inf_n": breakdown["component_inf_n"],
            "internal_sum_inf_n": breakdown["internal_sum_inf_n"],
            "inferred_external_load_inf_n": breakdown[
                "inferred_external_load_inf_n"
            ],
            "load_derivative_inf_n_per_load": breakdown[
                "load_derivative_inf_n_per_load"
            ],
        },
        "residual_ownership_breakdown": breakdown,
        "claim_boundary": breakdown["claim_boundary"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT_NPZ)
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument("--frame-tangent-source", default="force_based_residual_tangent")
    parser.add_argument("--shell-pressure-load-path-policy", default="all_components")
    parser.add_argument("--top-count", type=int, default=16)
    parser.add_argument("--load-derivative-eps", type=float, default=1.0e-3)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_g1_active_frontier_residual_ownership_probe(
        mgt_model=args.mgt_model,
        checkpoint_npz=args.checkpoint_npz,
        load_scale=args.load_scale,
        frame_tangent_source=args.frame_tangent_source,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        top_count=args.top_count,
        load_derivative_eps=args.load_derivative_eps,
        output_json=args.output_json,
    )
    summary = payload.get("summary", {})
    print(
        "g1-active-frontier-residual-ownership-probe: "
        f"status={payload['status']} "
        f"top_residual={summary.get('top_residual_inf_n')} "
        f"top_component={summary.get('top_row_dominant_internal_component')} "
        f"balance_driver={summary.get('top_row_balance_driver')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
