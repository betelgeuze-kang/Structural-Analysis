#!/usr/bin/env python3
"""Replay the active frontier under shell pressure load-path policies."""

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
if str(PHASE1) in sys.path:
    sys.path.remove(str(PHASE1))
sys.path.insert(0, str(PHASE1))

from run_g1_active_frontier_residual_ownership_probe import (  # noqa: E402
    _load_checkpoint_free_state,
    residual_ownership_breakdown,
)
from run_g1_mgt_physical_line_search_smoke import (  # noqa: E402
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)
from run_g1_true_newton_reference_candidate import _max_abs  # noqa: E402


SCHEMA_VERSION = "g1-active-frontier-shell-policy-replay-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_active_frontier_shell_policy_replay_probe.json"
DEFAULT_POLICIES = (
    "all_components",
    "attached_components_only",
    "structural_components_only",
)


def _parse_policies(value: str) -> tuple[str, ...]:
    policies = tuple(item.strip() for item in str(value).split(",") if item.strip())
    return policies or DEFAULT_POLICIES


def _anchor_row(
    *,
    residual: np.ndarray,
    component_forces: dict[str, np.ndarray],
    free: np.ndarray,
    global_dof: int,
) -> dict[str, Any]:
    free_np = np.asarray(free, dtype=np.int64)
    matches = np.where(free_np == int(global_dof))[0]
    if not matches.size:
        return {
            "found": False,
            "global_dof": int(global_dof),
            "reason": "anchor_global_dof_not_free",
        }
    row = int(matches[0])
    component_values = {
        str(name): float(np.asarray(values, dtype=np.float64)[row])
        for name, values in component_forces.items()
        if row < int(np.asarray(values).size)
    }
    internal_sum = float(sum(component_values.values()))
    residual_value = float(np.asarray(residual, dtype=np.float64)[row])
    external = internal_sum - residual_value
    dominant = max(
        component_values,
        key=lambda name: abs(component_values[name]),
        default="none",
    )
    return {
        "found": True,
        "reduced_index": row,
        "global_dof": int(global_dof),
        "residual_n": residual_value,
        "residual_abs_n": abs(residual_value),
        "internal_sum_n": internal_sum,
        "inferred_external_load_n": external,
        "component_values_n": component_values,
        "dominant_internal_component": dominant,
    }


def _best_policy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in rows if row.get("status") == "ready"]
    return min(
        candidates,
        key=lambda row: float(row.get("residual_inf_n", float("inf"))),
        default={},
    )


def run_g1_active_frontier_shell_policy_replay_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    load_scale: float = 1.0,
    frame_tangent_source: str = "force_based_residual_tangent",
    policies: tuple[str, ...] = DEFAULT_POLICIES,
    top_count: int = 16,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    anchor_global_dof: int | None = None
    anchor_reduced_index: int | None = None
    checkpoint_summary: dict[str, Any] = {}
    for policy in policies:
        residual_fn, _x0, meta = build_mgt_physical_residual_closure(
            mgt_path=Path(mgt_model),
            roundtrip_npz=None,
            load_scale=float(load_scale),
            frame_tangent_source=frame_tangent_source,
            shell_pressure_load_path_policy=str(policy),
        )
        free = np.asarray(meta["free"], dtype=np.int64)
        checkpoint = _load_checkpoint_free_state(
            checkpoint_npz=Path(checkpoint_npz),
            free=free,
            dof_count=int(meta["dof_count"]),
        )
        if not checkpoint_summary:
            checkpoint_summary = {
                key: value
                for key, value in checkpoint.items()
                if key not in {"free_state", "full_displacement"}
            }
        x = np.asarray(checkpoint["free_state"], dtype=np.float64)
        residual = np.asarray(residual_fn(x), dtype=np.float64)
        component_fn = meta.get("component_residual_fn")
        if not callable(component_fn):
            rows.append(
                {
                    "policy": str(policy),
                    "status": "blocked",
                    "reason_code": "component_residual_fn_missing",
                }
            )
            continue
        components = {
            str(name): np.asarray(values, dtype=np.float64)
            for name, values in component_fn(x).items()
        }
        ownership = residual_ownership_breakdown(
            residual=residual,
            component_forces=components,
            free=free,
            node_id=np.asarray(meta.get("node_id"), dtype=np.int64),
            dof_per_node=int(meta.get("dof_per_node") or 6),
            top_count=int(top_count),
        )
        top_row = (
            ownership["top_rows"][0]
            if isinstance(ownership.get("top_rows"), list)
            and ownership["top_rows"]
            else {}
        )
        if anchor_global_dof is None and str(policy) == "all_components":
            anchor_global_dof = int(top_row.get("global_dof", -1))
            anchor_reduced_index = int(top_row.get("reduced_index", -1))
        if anchor_global_dof is None:
            anchor_global_dof = int(top_row.get("global_dof", -1))
            anchor_reduced_index = int(top_row.get("reduced_index", -1))
        pressure_meta = (
            meta.get("shell_pressure_load_path_meta")
            if isinstance(meta.get("shell_pressure_load_path_meta"), dict)
            else {}
        )
        rows.append(
            {
                "policy": str(policy),
                "canonical_policy": str(meta.get("shell_pressure_load_path_policy") or policy),
                "status": "ready",
                "residual_inf_n": _max_abs(residual),
                "residual_gate_passed": _max_abs(residual) <= 5.0e-4,
                "top_row": top_row,
                "anchor_all_components_top_row": _anchor_row(
                    residual=residual,
                    component_forces=components,
                    free=free,
                    global_dof=int(anchor_global_dof),
                )
                if anchor_global_dof is not None and anchor_global_dof >= 0
                else {},
                "pressure_load_path_meta": pressure_meta,
                "pressure_load_filter_enabled": (
                    pressure_meta.get("pressure_load_filter_enabled") is True
                ),
                "pressure_load_allowed_surface_element_count": pressure_meta.get(
                    "pressure_load_allowed_surface_element_count"
                ),
                "pressure_load_suppressed_surface_element_count": pressure_meta.get(
                    "pressure_load_suppressed_surface_element_count"
                ),
                "claim_boundary": (
                    "Policy replay only: re-evaluates the same active-frontier "
                    "checkpoint under a shell pressure load-path policy. It does "
                    "not create or promote a full-load G1 closure checkpoint."
                ),
            }
        )
    best = _best_policy(rows)
    baseline = next(
        (row for row in rows if row.get("policy") == "all_components"),
        {},
    )
    baseline_inf = float(baseline.get("residual_inf_n", 0.0) or 0.0)
    best_inf = float(best.get("residual_inf_n", 0.0) or 0.0)
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
        "policies": [str(policy) for policy in policies],
        "checkpoint": checkpoint_summary,
        "summary": {
            "anchor_global_dof": anchor_global_dof,
            "anchor_reduced_index": anchor_reduced_index,
            "baseline_policy": "all_components",
            "baseline_residual_inf_n": baseline_inf,
            "best_policy": str(best.get("policy") or ""),
            "best_residual_inf_n": best_inf,
            "best_residual_gate_passed": best.get("residual_gate_passed") is True,
            "best_improvement_inf_n": baseline_inf - best_inf,
            "best_reduction_ratio": (baseline_inf - best_inf) / max(baseline_inf, 1.0e-30),
            "ready_policy_count": sum(1 for row in rows if row.get("status") == "ready"),
            "structural_or_attached_policy_descent_observed": any(
                float(row.get("residual_inf_n", float("inf"))) < baseline_inf
                for row in rows
                if row.get("policy") in {"attached_components_only", "structural_components_only"}
            ),
            "best_policy_pressure_filter_enabled": (
                best.get("pressure_load_filter_enabled") is True
            ),
            "best_policy_pressure_suppressed_surface_element_count": best.get(
                "pressure_load_suppressed_surface_element_count"
            ),
        },
        "rows": rows,
        "claim_boundary": (
            "Shell pressure policy replay evidence only. A lower residual under "
            "a filtered policy is routing evidence for load-path policy repair; "
            "it does not by itself close G1 full-load nonlinear equilibrium."
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
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT_NPZ)
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument("--frame-tangent-source", default="force_based_residual_tangent")
    parser.add_argument(
        "--policies",
        default=",".join(DEFAULT_POLICIES),
    )
    parser.add_argument("--top-count", type=int, default=16)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_g1_active_frontier_shell_policy_replay_probe(
        mgt_model=args.mgt_model,
        checkpoint_npz=args.checkpoint_npz,
        load_scale=args.load_scale,
        frame_tangent_source=args.frame_tangent_source,
        policies=_parse_policies(args.policies),
        top_count=args.top_count,
        output_json=args.output_json,
    )
    summary = payload.get("summary", {})
    print(
        "g1-active-frontier-shell-policy-replay-probe: "
        f"status={payload['status']} "
        f"baseline={summary.get('baseline_residual_inf_n')} "
        f"best_policy={summary.get('best_policy')} "
        f"best={summary.get('best_residual_inf_n')} "
        f"improvement={summary.get('best_improvement_inf_n')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
