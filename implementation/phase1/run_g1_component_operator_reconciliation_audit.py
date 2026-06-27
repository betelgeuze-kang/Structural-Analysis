#!/usr/bin/env python3
"""Non-promoting component-wise operator reconciliation audit (F2c).

F2b-ii-a found that the assembled free-space tangent is decorrelated from the
physical residual directional derivative (cosine(K.v, J_phys.v) ~= 0.02). This
audit decomposes J_phys.v component by component (frame / spring / shell / ...)
and ranks which component drives the decorrelation, so a later slice can adjust
only the offending component.

It is an audit only: it does not modify the solver, does not promote G1, does not
regenerate the 0.656 continuation checkpoint, and writes only an untracked
``*.local.json``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from g1_global_newton_operator import DEFAULT_JVP_EPS, physical_consistent_jvp
from g1_operator_component_audit import (
    ERR_COMPONENT_SHAPE_MISMATCH,
    classify_mismatch,
    component_rows,
    rank_suspects,
    safe_cosine,
)
from run_g1_mgt_physical_line_search_smoke import (
    DEFAULT_MGT_MODEL,
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-component-operator-reconciliation-audit.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_component_operator_reconciliation_audit.local.json"

PASS = "PASS"


def _norm(x: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(x, dtype=np.float64)))


def build_component_audit_report(
    *,
    jphys_v: np.ndarray,
    ktotal_v: np.ndarray,
    component_actions: dict[str, np.ndarray],
    spring_tangent_action: np.ndarray | None = None,
    spring_residual_action: np.ndarray | None = None,
    parity_rel_tol: float = 1.0e-3,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    free_dof_count: int | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure-numeric report core: global parity + component rows + ranked suspects."""
    jphys_v = np.asarray(jphys_v, dtype=np.float64)
    ktotal_v = np.asarray(ktotal_v, dtype=np.float64)
    cos_global = safe_cosine(ktotal_v, jphys_v)
    classification = classify_mismatch(ktotal_v, jphys_v, parity_rel_tol=parity_rel_tol)
    parity_pass = classification == "consistent"

    base = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_audit_only": True,
        "promotes_g1_closure": False,
        "uses_real_mgt_model": bool(uses_real_mgt_model),
        "mgt_source": mgt_source,
        "load_scale": load_scale,
        "free_space": {
            "free_dof_count": free_dof_count,
            "residual_shape": [int(jphys_v.size)],
            "assembled_tangent_action_shape": [int(ktotal_v.size)],
        },
        "global_parity": {
            "assembled_tangent_parity_pass": bool(parity_pass),
            "cosine_kv_vs_jvp": float(cos_global),
            "norm_jvp": _norm(jphys_v),
            "norm_kv": _norm(ktotal_v),
            "diagnosis": classification,
        },
        "resource_usage": resource_usage or {},
        "claim_boundary": "non_promoting_component_operator_audit_only",
    }

    try:
        rows = component_rows(component_actions, jphys_v, expected_shape=(int(jphys_v.size),))
    except ValueError as exc:
        base["status"] = "blocked"
        base["reason_code"] = (
            ERR_COMPONENT_SHAPE_MISMATCH if ERR_COMPONENT_SHAPE_MISMATCH in str(exc)
            else "ERR_COMPONENT_DECOMPOSITION_FAILED"
        )
        base["component_rows"] = []
        base["ranked_suspects"] = []
        return base

    # cross-check: sum of component JVPs should reconstruct J_phys.v
    present = [np.asarray(a, dtype=np.float64) for a in component_actions.values() if a is not None]
    recon = np.sum(present, axis=0) if present else np.zeros_like(jphys_v)
    recon_cos = safe_cosine(recon, jphys_v)
    recon_rel = _norm(recon - jphys_v) / max(_norm(jphys_v), 1.0e-30)

    spring_consistency = None
    if spring_tangent_action is not None and spring_residual_action is not None:
        st = np.asarray(spring_tangent_action, dtype=np.float64)
        sr = np.asarray(spring_residual_action, dtype=np.float64)
        spring_consistency = {
            "spring_tangent_vs_residual_cosine": safe_cosine(st, sr),
            "spring_tangent_vs_residual_rel_error": _norm(st - sr) / max(_norm(sr), 1.0e-30),
            "note": "spring internal force is K_spring @ u (linear); tangent and residual must agree",
        }

    suspects = rank_suspects(rows, parity_pass=parity_pass)
    base["status"] = "ready"
    base["reason_code"] = PASS
    base["component_decomposition_reconstruction"] = {
        "sum_component_jvp_vs_total_cosine": float(recon_cos),
        "sum_component_jvp_vs_total_rel_error": float(recon_rel),
    }
    base["component_rows"] = rows
    base["spring_consistency_cross_check"] = spring_consistency
    base["ranked_suspects"] = suspects
    return base


def run_g1_component_operator_reconciliation_audit(
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
            "claim_boundary": "non_promoting_component_operator_audit_only",
        }
    else:
        try:
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
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
                "claim_boundary": "non_promoting_component_operator_audit_only",
            }
        else:
            rng = np.random.default_rng(seed)
            n = int(x0.size)
            v = rng.standard_normal(n)
            v = v / max(float(np.linalg.norm(v)), 1.0e-30)

            jphys_v = physical_consistent_jvp(residual_fn, x0, v, eps=eps)
            ktotal_v = np.asarray(meta["tangent_free_csr"] @ v, dtype=np.float64)

            component_fn: Callable[[np.ndarray], dict[str, np.ndarray]] = meta["component_residual_fn"]
            comp_plus = component_fn(x0 + eps * v)
            comp_minus = component_fn(x0 - eps * v)
            component_actions = {
                name: (np.asarray(comp_plus[name], dtype=np.float64)
                       - np.asarray(comp_minus[name], dtype=np.float64)) / (2.0 * eps)
                for name in comp_plus
            }
            spring_tangent_action = np.asarray(meta["spring_free_csr"] @ v, dtype=np.float64)
            spring_residual_action = component_actions.get("spring")

            payload = build_component_audit_report(
                jphys_v=jphys_v, ktotal_v=ktotal_v, component_actions=component_actions,
                spring_tangent_action=spring_tangent_action,
                spring_residual_action=spring_residual_action,
                uses_real_mgt_model=True, mgt_source=str(mgt_model), load_scale=load_scale,
                free_dof_count=meta["free_dof_count"],
                resource_usage={
                    "dof_count": meta["dof_count"], "node_count": meta["node_count"],
                    "element_count": meta["element_count"], "free_dof_count": meta["free_dof_count"],
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
    payload = run_g1_component_operator_reconciliation_audit(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz,
        load_scale=args.load_scale, seed=args.seed, output_json=args.output_json,
    )
    gp = payload.get("global_parity", {})
    suspects = payload.get("ranked_suspects", [])
    top = suspects[0]["component"] if suspects else None
    print(
        "g1-component-operator-reconciliation-audit: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"cosine={gp.get('cosine_kv_vs_jvp')} diagnosis={gp.get('diagnosis')} "
        f"top_suspect={top} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
