#!/usr/bin/env python3
"""Probe frame tangent finite-difference epsilon sensitivity at the G1 frontier."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from g1_global_newton_operator import DEFAULT_JVP_EPS
from g1_regularized_direction import regularize_matrix
from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-frame-tangent-fd-epsilon-sweep-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_INITIAL_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_TRUE_NEWTON_JSON = (
    PRODUCTIZATION / "g1_true_newton_from_active_set_ls_trust_mu_0p03_candidate.json"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_frame_tangent_fd_epsilon_sweep_probe.json"
DEFAULT_EPS_VALUES = (
    1.0e-3,
    3.0e-4,
    1.0e-4,
    3.0e-5,
    1.0e-5,
    3.0e-6,
    1.0e-6,
    3.0e-7,
    1.0e-7,
)
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
FrameComponentFn = Callable[[np.ndarray], np.ndarray]


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


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
        direct_residual = float(
            np.asarray(
                archive[
                    "direct_residual_inf_n"
                    if "direct_residual_inf_n" in archive.files
                    else "residual_inf_n"
                ]
            ).item()
        )
    if int(displacement.size) != int(dof_count):
        raise ValueError(
            f"checkpoint dof_count {displacement.size} does not match {dof_count}"
        )
    free_idx = np.asarray(free, dtype=np.int64)
    return {
        "schema": schema,
        "load_scale": load_scale,
        "direct_residual_inf_n": direct_residual,
        "free_state": displacement[free_idx].copy(),
    }


def _candidate_row_indices(path: Path) -> list[int]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    contracts = (
        payload.get("summary", {})
        .get("directional_residual_jvp_contract", {})
        .get("direction_solve_contracts", {})
    )
    dominant = contracts.get("dominant_jvp_gap_row_set", {})
    rows = dominant.get("dominant_jvp_minus_unregularized_tangent_action_rows", [])
    result: list[int] = []
    for row in rows:
        if isinstance(row, dict) and row.get("reduced_index") is not None:
            result.append(int(row["reduced_index"]))
    return result


def _annotate_row(
    *,
    reduced_index: int,
    free: np.ndarray | None,
    node_id: np.ndarray | None,
    dof_per_node: int,
    values: dict[str, float],
) -> dict[str, Any]:
    row: dict[str, Any] = {"reduced_index": int(reduced_index), **values}
    if free is None:
        return row
    free_np = np.asarray(free, dtype=np.int64)
    if reduced_index < 0 or reduced_index >= int(free_np.size):
        return row
    global_dof = int(free_np[reduced_index])
    node_index = global_dof // int(dof_per_node)
    local_dof_index = global_dof % int(dof_per_node)
    row.update(
        {
            "global_dof": global_dof,
            "node_index": int(node_index),
            "local_dof_index": int(local_dof_index),
            "dof_label": (
                DOF_LABELS[local_dof_index]
                if 0 <= local_dof_index < len(DOF_LABELS)
                else f"DOF{local_dof_index}"
            ),
        }
    )
    if node_id is not None:
        node_ids = np.asarray(node_id, dtype=np.int64)
        if 0 <= node_index < int(node_ids.size):
            row["node_id"] = int(node_ids[node_index])
    return row


def frame_tangent_fd_epsilon_sweep_summary(
    *,
    x: np.ndarray,
    p: np.ndarray,
    frame_component_fn: FrameComponentFn,
    frame_tangent_action: np.ndarray,
    residual_inf_n: float,
    eps_values: tuple[float, ...] = DEFAULT_EPS_VALUES,
    selected_rows: list[int] | None = None,
    free: np.ndarray | None = None,
    node_id: np.ndarray | None = None,
    dof_per_node: int = 6,
) -> dict[str, Any]:
    x_np = np.asarray(x, dtype=np.float64)
    p_np = np.asarray(p, dtype=np.float64)
    action = np.asarray(frame_tangent_action, dtype=np.float64)
    if x_np.shape != p_np.shape or action.shape != x_np.shape:
        raise ValueError("x, p, and frame_tangent_action must share shape")
    residual_scale = max(float(residual_inf_n), 1.0)
    base_frame = np.asarray(frame_component_fn(x_np), dtype=np.float64)
    if base_frame.shape != x_np.shape:
        raise ValueError("frame_component_fn returned an unexpected shape")

    rows_out: list[dict[str, Any]] = []
    selected = [int(row) for row in (selected_rows or [])]
    for eps in eps_values:
        step = float(eps)
        if step <= 0.0:
            raise ValueError("eps values must be positive")
        plus = np.asarray(frame_component_fn(x_np + step * p_np), dtype=np.float64)
        minus = np.asarray(frame_component_fn(x_np - step * p_np), dtype=np.float64)
        jvp = (plus - minus) / (2.0 * step)
        gap = jvp - action
        top = np.argsort(-np.abs(gap))[:5]
        selected_set = selected or [int(index) for index in top]
        selected_rows_out = [
            _annotate_row(
                reduced_index=int(index),
                free=free,
                node_id=node_id,
                dof_per_node=dof_per_node,
                values={
                    "frame_jvp_n": float(jvp[index]),
                    "frame_tangent_action_n": float(action[index]),
                    "gap_n": float(gap[index]),
                    "base_frame_force_n": float(base_frame[index]),
                },
            )
            for index in selected_set
            if 0 <= int(index) < int(gap.size)
        ]
        rows_out.append(
            {
                "eps": step,
                "max_frame_jvp_minus_tangent_action_inf_n": _max_abs(gap),
                "max_frame_jvp_minus_tangent_action_relative_inf": (
                    _max_abs(gap) / residual_scale
                ),
                "frame_jvp_inf_n": _max_abs(jvp),
                "frame_tangent_action_inf_n": _max_abs(action),
                "selected_rows": selected_rows_out,
                "top_gap_rows": [
                    _annotate_row(
                        reduced_index=int(index),
                        free=free,
                        node_id=node_id,
                        dof_per_node=dof_per_node,
                        values={
                            "frame_jvp_n": float(jvp[index]),
                            "frame_tangent_action_n": float(action[index]),
                            "gap_n": float(gap[index]),
                            "base_frame_force_n": float(base_frame[index]),
                        },
                    )
                    for index in top
                ],
            }
        )
    default_row = min(
        rows_out,
        key=lambda row: abs(float(row["eps"]) - DEFAULT_JVP_EPS),
    )
    best_row = min(
        rows_out,
        key=lambda row: float(row["max_frame_jvp_minus_tangent_action_inf_n"]),
    )
    default_gap = float(default_row["max_frame_jvp_minus_tangent_action_inf_n"])
    best_gap = float(best_row["max_frame_jvp_minus_tangent_action_inf_n"])
    return {
        "residual_inf_n": float(residual_inf_n),
        "direction_inf_m": _max_abs(p_np),
        "frame_force_inf_n": _max_abs(base_frame),
        "frame_tangent_action_inf_n": _max_abs(action),
        "default_jvp_eps": float(DEFAULT_JVP_EPS),
        "default_eps_row": default_row,
        "best_eps_row": best_row,
        "eps_rows": rows_out,
        "fd_step_sensitivity_observed": bool(default_gap > max(best_gap * 10.0, 1.0e-12)),
        "default_eps_artifact_likely": bool(default_gap > max(best_gap * 100.0, 1.0e-9)),
        "default_to_best_gap_ratio": default_gap / max(best_gap, 1.0e-30),
    }


def run_g1_frame_tangent_fd_epsilon_sweep_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    checkpoint_npz: Path = DEFAULT_INITIAL_CHECKPOINT_NPZ,
    true_newton_json: Path = DEFAULT_TRUE_NEWTON_JSON,
    load_scale: float = 1.0,
    frame_tangent_source: str = "force_based_residual_tangent",
    regularization_mode: str = "relative_diagonal_shift",
    regularization_mu: float = 0.03,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    residual_fn, _x0, meta = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=float(load_scale),
        frame_tangent_source=frame_tangent_source,
    )
    free = np.asarray(meta["free"], dtype=np.int64)
    checkpoint = _load_checkpoint_free_state(
        checkpoint_npz=Path(checkpoint_npz),
        free=free,
        dof_count=int(meta["dof_count"]),
    )
    x = np.asarray(checkpoint["free_state"], dtype=np.float64)
    residual = np.asarray(residual_fn(x), dtype=np.float64)
    k_state, rebuild_meta = meta["tangent_rebuild_fn"](x)
    k_reg, effective_shift, scale_source = regularize_matrix(
        k_state,
        regularization_mode,
        regularization_mu,
    )
    p = np.asarray(splu(csc_matrix(k_reg)).solve(-residual), dtype=np.float64)
    frame_stiffness = rebuild_meta["component_stiffness_free"]["frame"]
    frame_action = np.asarray(frame_stiffness @ p, dtype=np.float64)

    def frame_component_fn(x_free: np.ndarray) -> np.ndarray:
        components = meta["component_residual_fn"](x_free)
        return np.asarray(components["frame"], dtype=np.float64)

    selected_rows = _candidate_row_indices(Path(true_newton_json))
    sweep = frame_tangent_fd_epsilon_sweep_summary(
        x=x,
        p=p,
        frame_component_fn=frame_component_fn,
        frame_tangent_action=frame_action,
        residual_inf_n=_max_abs(residual),
        selected_rows=selected_rows,
        free=free,
        node_id=np.asarray(meta.get("node_id"), dtype=np.int64),
        dof_per_node=int(meta.get("dof_per_node") or 6),
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "is_candidate_only": True,
        "promotes_g1_closure": False,
        "mgt_model": str(mgt_model),
        "checkpoint_npz": str(checkpoint_npz),
        "true_newton_json": str(true_newton_json),
        "load_scale": float(load_scale),
        "frame_tangent_source": frame_tangent_source,
        "regularization": {
            "mode": regularization_mode,
            "mu": float(regularization_mu),
            "effective_shift": float(effective_shift),
            "scale_source": str(scale_source),
        },
        "checkpoint": {
            key: value for key, value in checkpoint.items() if key != "free_state"
        },
        "selected_reduced_rows": selected_rows,
        "summary": sweep,
        "claim_boundary": (
            "Frame tangent FD epsilon sweep only. This probes whether the "
            "default finite-difference JVP gap is step-size/cancellation "
            "sensitive; it does not change the solver path or promote G1 closure."
        ),
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
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_INITIAL_CHECKPOINT_NPZ)
    parser.add_argument("--true-newton-json", type=Path, default=DEFAULT_TRUE_NEWTON_JSON)
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument("--frame-tangent-source", default="force_based_residual_tangent")
    parser.add_argument("--regularization-mode", default="relative_diagonal_shift")
    parser.add_argument("--regularization-mu", type=float, default=0.03)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_g1_frame_tangent_fd_epsilon_sweep_probe(
        mgt_model=args.mgt_model,
        checkpoint_npz=args.checkpoint_npz,
        true_newton_json=args.true_newton_json,
        load_scale=args.load_scale,
        frame_tangent_source=args.frame_tangent_source,
        regularization_mode=args.regularization_mode,
        regularization_mu=args.regularization_mu,
        output_json=args.output_json,
    )
    summary = payload["summary"]
    print(
        "g1-frame-tangent-fd-epsilon-sweep-probe: "
        f"status={payload['status']} "
        f"default_gap={summary['default_eps_row']['max_frame_jvp_minus_tangent_action_inf_n']} "
        f"best_eps={summary['best_eps_row']['eps']} "
        f"best_gap={summary['best_eps_row']['max_frame_jvp_minus_tangent_action_inf_n']} "
        f"artifact_likely={summary['default_eps_artifact_likely']} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
