#!/usr/bin/env python3
"""Non-promoting frame operator reconciliation audit (F2d-frame).

F2c localized the assembled-tangent / physical-residual decorrelation to the
**frame** component (frame carries ~99.98% of ||J_phys.v||, while the assembled
tangent is decorrelated and ~54x smaller). This audit decomposes the frame
operator further to name which frame sub-term drives the mismatch:

  - the residual-side frame directional derivative ``J_frame.v`` (from the
    force-based corotational internal force);
  - assembled frame tangent blocks ``K_frame.v`` split into ``material`` (a chosen
    service tangent) and ``geometric_delta`` (axial preload P-Delta), plus the
    ``elastic`` reference, built with both the smoke closure's placeholder
    (1.0 MPa) service tangent and the real per-element service tangent.

Each block is compared to ``J_frame.v`` by cosine, norm, best scalar fit and
scaled relative error, and classified as consistent / scale_factor /
decorrelated. It is an audit only: no solver fix, no assembled-tangent change,
no sparse-direct/ILU retry, no 0.656 regeneration, no G1 promotion.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from g1_global_newton_operator import DEFAULT_JVP_EPS
from g1_operator_component_audit import classify_mismatch, safe_cosine
from run_g1_mgt_physical_line_search_smoke import (
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-frame-operator-reconciliation-audit.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_frame_operator_reconciliation_audit.local.json"

PASS = "PASS"
ERR_FRAME_COMPONENT_MISSING = "ERR_FRAME_COMPONENT_MISSING"
ERR_FRAME_COMPONENT_SHAPE_MISMATCH = "ERR_FRAME_COMPONENT_SHAPE_MISMATCH"

PLACEHOLDER_SERVICE_TANGENT_MPA = 1.0


def _norm(x: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(x, dtype=np.float64)))


def block_mismatch(kv: np.ndarray, jv: np.ndarray) -> dict[str, Any]:
    """Compare an assembled block action K.v against the frame residual JVP J.v."""
    kv = np.asarray(kv, dtype=np.float64)
    jv = np.asarray(jv, dtype=np.float64)
    nk, nj = _norm(kv), _norm(jv)
    cos = safe_cosine(kv, jv)
    # best scalar alpha minimizing ||alpha*kv - jv||
    kk = float(np.dot(kv, kv))
    alpha = float(np.dot(kv, jv) / kk) if kk > 0.0 else 0.0
    scaled_rel_err = _norm(alpha * kv - jv) / max(nj, 1.0e-30)
    return {
        "norm_k": nk,
        "norm_j": nj,
        "norm_ratio_k_over_j": (nk / nj) if nj > 0.0 else float("inf"),
        "cosine_with_j_frame": cos,
        "best_scalar_fit": alpha,
        "scaled_relative_error": float(scaled_rel_err),
        "classification": classify_mismatch(kv, jv),
    }


def build_frame_tangent_blocks(
    frame_inputs: dict[str, Any],
    service_tangent_by_element: dict[int, float],
) -> dict[str, Any]:
    """Assemble free-restricted frame tangent blocks (material/geometric_delta/total)."""
    from run_mgt_frame_material_nonlinear_tangent import _assemble_material_tangent_frame
    from run_mgt_full_frame_6dof_sparse_equilibrium import _assemble_sparse_frame

    fe = frame_inputs["frame_elements"]
    node_xyz = frame_inputs["node_xyz"]
    section_props = frame_inputs["section_props"]
    material_props = frame_inputs["material_props"]
    base_axial = frame_inputs["base_axial"]
    fgls = frame_inputs["frame_gravity_load_scale"]
    load_scale = frame_inputs["load_scale"]
    free = np.asarray(frame_inputs["free"], dtype=np.int64)
    axial = {int(e): float(f) * fgls * load_scale for e, f in base_axial.items()}

    k_material, _f, _m = _assemble_material_tangent_frame(
        elements=fe, node_xyz=node_xyz, section_props=section_props,
        material_props=material_props, tangent_by_element_mpa=service_tangent_by_element,
    )
    k_elastic, _ef, _em = _assemble_sparse_frame(
        elements=fe, node_xyz=node_xyz, section_props=section_props, material_props=material_props,
    )
    k_geo_total, _gf, _gm = _assemble_sparse_frame(
        elements=fe, node_xyz=node_xyz, section_props=section_props, material_props=material_props,
        element_axial_forces=axial, include_geometric=True,
    )
    geom_delta = k_geo_total - k_elastic
    total = k_material + geom_delta

    def fr(mat: Any) -> Any:
        return mat.tocsr()[free][:, free].tocsr()

    return {
        "material": fr(k_material),
        "geometric_delta": fr(geom_delta),
        "elastic": fr(k_elastic),
        "total": fr(total),
    }


def _real_service_tangent(frame_inputs: dict[str, Any]) -> dict[int, float]:
    from run_mgt_direct_residual_newton_probe import _service_tangent_by_element

    tangent, _meta = _service_tangent_by_element(
        elements=frame_inputs["frame_elements"],
        node_xyz=frame_inputs["node_xyz"],
        u=frame_inputs["u0"],
        material_props=frame_inputs["material_props"],
    )
    return tangent


def build_frame_audit_report(
    *,
    j_frame_v: np.ndarray,
    blocks_by_service: dict[str, dict[str, np.ndarray]],
    frame_share_of_jphys_norm: float | None = None,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure-numeric report core: frame block mismatches + ranked frame suspects."""
    j_frame_v = np.asarray(j_frame_v, dtype=np.float64)
    subcomponents: list[dict[str, Any]] = []
    for service_name, blocks in blocks_by_service.items():
        for block_name, action in blocks.items():
            action = np.asarray(action, dtype=np.float64)
            if action.shape != j_frame_v.shape:
                return {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "is_audit_only": True, "promotes_g1_closure": False,
                    "status": "blocked", "reason_code": ERR_FRAME_COMPONENT_SHAPE_MISMATCH,
                    "focus_component": "frame",
                    "claim_boundary": "non_promoting_frame_operator_audit_only",
                }
            row = {"service_tangent": service_name, "block": block_name, **block_mismatch(action, j_frame_v)}
            subcomponents.append(row)

    # rank: the block that best matches J_frame (highest cosine, lowest scaled error)
    # tells us which assembled configuration would reconcile; the suspect is the
    # term whose absence/placeholder most degrades the match.
    ranked = sorted(
        subcomponents,
        key=lambda r: (r["cosine_with_j_frame"], -r["scaled_relative_error"]),
        reverse=True,
    )
    best_match = ranked[0] if ranked else None
    suspects: list[dict[str, Any]] = []
    # any "total" block that is still decorrelated is a suspect configuration
    for row in subcomponents:
        if row["block"] == "total" and row["classification"] != "consistent":
            suspects.append({
                "service_tangent": row["service_tangent"],
                "block": "total",
                "classification": row["classification"],
                "cosine_with_j_frame": row["cosine_with_j_frame"],
                "scaled_relative_error": row["scaled_relative_error"],
                "reason": "assembled frame total tangent does not reconcile with J_frame",
            })

    # reconciliation finding: which service-tangent configuration reconciles the
    # assembled frame total tangent with the physical-residual frame JVP
    total_rows = [r for r in subcomponents if r["block"] == "total"]
    consistent_totals = [r["service_tangent"] for r in total_rows if r["classification"] == "consistent"]
    decorrelated_totals = [r["service_tangent"] for r in total_rows if r["classification"] != "consistent"]
    reconciliation_summary = {
        "j_frame_matches_elastic_block": any(
            r["block"] == "elastic" and r["classification"] == "consistent" for r in subcomponents
        ),
        "service_tangent_configs_reconciling_total": consistent_totals,
        "service_tangent_configs_decorrelated_total": decorrelated_totals,
        "root_cause_hint": (
            "assembled frame total reconciles with J_frame under the real per-element "
            "service material tangent; it decorrelates only under the placeholder "
            "(1.0 MPa) service tangent used by the smoke closure builder"
            if consistent_totals and decorrelated_totals
            else "see frame_subcomponents"
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_audit_only": True,
        "promotes_g1_closure": False,
        "uses_real_mgt_model": bool(uses_real_mgt_model),
        "mgt_source": mgt_source,
        "load_scale": load_scale,
        "focus_component": "frame",
        "global_context": {
            "frame_share_of_jphys_norm": frame_share_of_jphys_norm,
            "spring_is_suspect": False,
            "shell_is_suspect": False,
            "note": "F2c ranked frame as the sole dominant suspect; spring is linear-consistent and shell is small",
        },
        "frame_residual_jvp": {"norm_j_frame": _norm(j_frame_v)},
        "frame_subcomponents": subcomponents,
        "best_matching_block": best_match,
        "reconciliation_summary": reconciliation_summary,
        "ranked_frame_suspects": suspects,
        "status": "ready",
        "reason_code": PASS,
        "resource_usage": resource_usage or {},
        "claim_boundary": "non_promoting_frame_operator_audit_only",
    }


def run_g1_frame_operator_reconciliation_audit(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    eps: float = DEFAULT_JVP_EPS,
    seed: int = 0,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    mgt_model = Path(mgt_model)
    if not mgt_model.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_audit_only": True, "promotes_g1_closure": False,
            "status": "blocked", "reason_code": ERR_MGT_INPUT_MISSING,
            "uses_real_mgt_model": False, "mgt_source": str(mgt_model),
            "focus_component": "frame",
            "claim_boundary": "non_promoting_frame_operator_audit_only",
        }
    else:
        try:
            _residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_audit_only": True, "promotes_g1_closure": False,
                "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                "detail": f"{type(exc).__name__}:{exc}",
                "focus_component": "frame",
                "claim_boundary": "non_promoting_frame_operator_audit_only",
            }
        else:
            rng = np.random.default_rng(seed)
            n = int(x0.size)
            v = rng.standard_normal(n)
            v = v / max(float(np.linalg.norm(v)), 1.0e-30)

            comp_fn = meta["component_residual_fn"]
            plus = comp_fn(x0 + eps * v)
            minus = comp_fn(x0 - eps * v)
            if "frame" not in plus:
                payload = {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "is_audit_only": True, "promotes_g1_closure": False,
                    "status": "blocked", "reason_code": ERR_FRAME_COMPONENT_MISSING,
                    "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                    "focus_component": "frame",
                    "claim_boundary": "non_promoting_frame_operator_audit_only",
                }
            else:
                j_frame_v = (np.asarray(plus["frame"], dtype=np.float64)
                             - np.asarray(minus["frame"], dtype=np.float64)) / (2.0 * eps)
                j_total_v = sum(
                    (np.asarray(plus[k], dtype=np.float64) - np.asarray(minus[k], dtype=np.float64)) / (2.0 * eps)
                    for k in plus
                )
                frame_share = _norm(j_frame_v) / max(_norm(j_total_v), 1.0e-30)

                frame_inputs = meta["frame_inputs"]
                fe = frame_inputs["frame_elements"]
                placeholder = {int(e.elem_id): PLACEHOLDER_SERVICE_TANGENT_MPA for e in fe}
                real = _real_service_tangent(frame_inputs)
                blocks_by_service = {
                    "placeholder_1mpa": build_frame_tangent_blocks(frame_inputs, placeholder),
                    "service_real": build_frame_tangent_blocks(frame_inputs, real),
                }
                # restrict block actions to K.v
                blocks_actions = {
                    sname: {bname: np.asarray(b @ v, dtype=np.float64) for bname, b in blocks.items()}
                    for sname, blocks in blocks_by_service.items()
                }
                payload = build_frame_audit_report(
                    j_frame_v=j_frame_v, blocks_by_service=blocks_actions,
                    frame_share_of_jphys_norm=float(frame_share),
                    uses_real_mgt_model=True, mgt_source=str(mgt_model), load_scale=load_scale,
                    resource_usage={
                        "dof_count": meta["dof_count"], "free_dof_count": meta["free_dof_count"],
                        "element_count": meta["element_count"],
                    },
                )

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
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_frame_operator_reconciliation_audit(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        load_scale=args.load_scale, seed=args.seed, output_json=args.output_json,
    )
    best = payload.get("best_matching_block")
    print(
        "g1-frame-operator-reconciliation-audit: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"frame_share={payload.get('global_context', {}).get('frame_share_of_jphys_norm')} "
        f"best_block={(best or {}).get('service_tangent')}/{(best or {}).get('block')} "
        f"best_cos={(best or {}).get('cosine_with_j_frame')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
