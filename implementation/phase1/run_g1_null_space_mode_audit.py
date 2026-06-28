#!/usr/bin/env python3
"""Non-promoting null-space mode audit (F2g-alt).

F2g-3 showed the reference-state residual plateau is structural (near-null-space),
not a regularization-magnitude problem. This audit identifies which free DOFs /
modes drive the singular / near-null space of the assembled tangent, maps them to
node / DOF types, and proposes (does NOT apply) pinning candidates.

Audit only: no pinning applied, no production solver path change, no 0.656
continuation regeneration, no G1 promotion. Output is an untracked ``*.local.json``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import eigsh, splu

from g1_null_space_audit import (
    aggregate_pinning_candidates,
    classify_mode,
    map_mode_to_dofs,
    scan_diagonal,
)
from run_g1_mgt_physical_line_search_smoke import (
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-null-space-mode-audit.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_null_space_mode_audit.local.json"

PASS = "PASS"
ERR_EIGEN_SOLVE_FAILED = "ERR_EIGEN_SOLVE_FAILED"
ERR_NO_NEAR_NULL_MODES_FOUND = "ERR_NO_NEAR_NULL_MODES_FOUND"
NEAR_NULL_EIGENVALUE_TOLERANCE = 1.0e-3


def _diag_stats(k_free: Any) -> dict[str, Any]:
    diag = np.asarray(k_free.diagonal(), dtype=np.float64)
    stats = scan_diagonal(diag)
    stats["free_dof_count"] = int(k_free.shape[0])
    stats["nnz"] = int(k_free.nnz)
    return stats


def _singularity_indicator(k_free: Any) -> dict[str, Any]:
    try:
        splu(csc_matrix(k_free))
        return {"unregularized_factorization": "ok", "singular": False}
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        pivot = None
        for tok in detail.replace(",", " ").split():
            if tok.isdigit():
                pivot = int(tok)
                break
        return {"unregularized_factorization": "failed", "singular": True,
                "singular_pivot_hint": pivot, "detail": detail[:160]}


def build_null_space_report(
    *,
    k_free: Any,
    free: np.ndarray,
    node_id: np.ndarray,
    dof_per_node: int,
    max_modes: int = 8,
    scan_only: bool = False,
    uses_real_mgt_model: bool = False,
    mgt_source: str | None = None,
    load_scale: float | None = None,
    frame_service_tangent_source: str | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_audit_only": True,
        "promotes_g1_closure": False,
        "uses_real_mgt_model": bool(uses_real_mgt_model),
        "mgt_source": mgt_source,
        "load_scale": load_scale,
        "frame_service_tangent_source": frame_service_tangent_source,
        "assembled_tangent": _diag_stats(k_free),
        "resource_usage": resource_usage or {},
        "claim_boundary": "non_promoting_null_space_audit_only",
    }
    singular = _singularity_indicator(k_free)

    if scan_only:
        base.update({
            "status": "ready", "reason_code": PASS,
            "singularity_indicators": {**singular, "smallest_eigen_attempted": False},
            "mode_rows": [], "pinning_candidates": [],
        })
        return base

    try:
        # shift-invert near zero (sigma slightly negative so K - sigma I is factorable)
        vals, vecs = eigsh(csc_matrix(k_free), k=int(max_modes), sigma=-1.0, which="LM")
    except Exception as exc:  # noqa: BLE001
        base.update({
            "status": "review", "reason_code": ERR_EIGEN_SOLVE_FAILED,
            "singularity_indicators": {**singular, "smallest_eigen_attempted": True,
                                       "eigen_error": str(exc)[:160]},
            "mode_rows": [], "pinning_candidates": [],
        })
        return base

    order = np.argsort(np.abs(vals))
    mode_rows: list[dict[str, Any]] = []
    near_null = 0
    for rank, idx in enumerate(order.tolist()):
        z = np.asarray(vecs[:, idx], dtype=np.float64)
        mapped = map_mode_to_dofs(z, free, node_id, dof_per_node)
        diagnosis = classify_mode(mapped["dominant_dof_types"])
        ev = float(vals[idx])
        is_near_null = bool(abs(ev) <= NEAR_NULL_EIGENVALUE_TOLERANCE * max(base["assembled_tangent"]["diag_max_abs"], 1.0))
        if is_near_null:
            near_null += 1
        mode_rows.append({
            "mode_index": rank,
            "eigenvalue": ev,
            "near_null": is_near_null,
            "energy_norm": float(np.linalg.norm(z)),
            "dominant_dof_types": mapped["dominant_dof_types"],
            "dominant_nodes": mapped["dominant_nodes"][:8],
            "diagnosis": diagnosis,
        })

    reason = PASS if mode_rows else ERR_NO_NEAR_NULL_MODES_FOUND
    base.update({
        "status": "ready" if mode_rows else "review",
        "reason_code": reason,
        "singularity_indicators": {
            **singular, "smallest_eigen_attempted": True,
            "smallest_eigenvalues": [float(v) for v in np.sort(np.abs(vals)).tolist()],
            "near_null_mode_count": int(near_null),
            "near_null_eigenvalue_tolerance_relative": NEAR_NULL_EIGENVALUE_TOLERANCE,
        },
        "mode_rows": mode_rows,
        "pinning_candidates": aggregate_pinning_candidates(mode_rows),
    })
    return base


def run_g1_null_space_mode_audit(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_service_tangent_source: str = "real_per_element",
    max_modes: int = 8,
    scan_only: bool = False,
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
            "claim_boundary": "non_promoting_null_space_audit_only",
        }
    else:
        try:
            _residual_fn, _x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
                frame_service_tangent_source=frame_service_tangent_source,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_audit_only": True, "promotes_g1_closure": False,
                "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                "detail": f"{type(exc).__name__}:{exc}",
                "claim_boundary": "non_promoting_null_space_audit_only",
            }
        else:
            payload = build_null_space_report(
                k_free=meta["tangent_free_csr"], free=meta["free"], node_id=meta["node_id"],
                dof_per_node=meta["dof_per_node"], max_modes=max_modes, scan_only=scan_only,
                uses_real_mgt_model=True, mgt_source=str(mgt_model), load_scale=load_scale,
                frame_service_tangent_source=meta.get("frame_service_tangent_source"),
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
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"], default="real_per_element",
    )
    parser.add_argument("--max-modes", type=int, default=8)
    parser.add_argument("--scan-only", action="store_true", default=False)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_null_space_mode_audit(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        max_modes=args.max_modes, scan_only=args.scan_only, output_json=args.output_json,
    )
    si = payload.get("singularity_indicators", {})
    rows = payload.get("mode_rows", [])
    top = rows[0]["diagnosis"] if rows else None
    print(
        "g1-null-space-mode-audit: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"singular={si.get('singular')} pivot={si.get('singular_pivot_hint')} "
        f"near_null_modes={si.get('near_null_mode_count')} top_mode={top} "
        f"pinning={[c['target_dof_type'] for c in payload.get('pinning_candidates', [])]} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
