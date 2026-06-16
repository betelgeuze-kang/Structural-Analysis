#!/usr/bin/env python3
"""Materialize NDTHA corrected-state residual recompute evidence.

The checked-in NDTHA stress report carries row-level residual metrics rather
than full global DOF states. This script applies the local LF->GNN residual
correction model to a deterministic row-level residual graph, then recomputes
the corrected residual under that same row contract. It does not claim a full
finite-element rerun.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation" / "phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

from gnn_residual_model import MODEL_API_VERSION, run_one_batch_with_metrics  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _finite(value: Any, default: float = math.nan) -> float:
    try:
        candidate = float(value)
    except Exception:
        return default
    return candidate if math.isfinite(candidate) else default


def _row_recompute(
    row: dict[str, Any],
    *,
    recommended_top_m: float,
    recommended_drift_pct: float,
    min_reduction_ratio: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row_summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    case_id = str(row.get("case_id", "") or "")
    top = _finite(row_summary.get("residual_top_displacement_m"))
    drift = _finite(row_summary.get("residual_drift_ratio_pct"))
    source = str(row_summary.get("residual_metric_source", "") or "")
    fallback_used = bool(row_summary.get("residual_metric_fallback_used", False))
    residual_l1 = abs(top) + abs(drift) if math.isfinite(top) and math.isfinite(drift) else math.nan

    nodes = [
        {"node_id": f"{case_id or 'case'}::support", "ux": 0.0, "uy": 0.0, "uz": 0.0, "f_norm": 0.0, "bc_type": "fixed"},
        {
            "node_id": f"{case_id or 'case'}::residual",
            "ux": top if math.isfinite(top) else 0.0,
            "uy": drift * 0.01 if math.isfinite(drift) else 0.0,
            "uz": 0.0,
            "f_norm": residual_l1 if math.isfinite(residual_l1) else 0.0,
            "bc_type": "free",
        },
    ]
    edges = [{"from": nodes[0]["node_id"], "to": nodes[1]["node_id"]}]
    meta = {"unit_system": "SI", "solver": "ndtha_row_residual_contract", "case_id": case_id}
    corrected_nodes, metrics = run_one_batch_with_metrics(nodes, edges, meta, gain=0.001)
    before = _finite(metrics.get("residual_l1_before"), default=0.0)
    after = _finite(metrics.get("residual_l1_after"), default=before)
    residual_scale = 1.0 if before <= 1.0e-12 else max(0.0, min(1.0, after / before))
    corrected_top = top * residual_scale if math.isfinite(top) else math.nan
    corrected_drift = drift * residual_scale if math.isfinite(drift) else math.nan
    reduction_ratio = _finite(metrics.get("residual_reduction_ratio"), default=0.0)

    pass_value = bool(
        math.isfinite(corrected_top)
        and math.isfinite(corrected_drift)
        and source == "solver_raw"
        and not fallback_used
        and reduction_ratio >= float(min_reduction_ratio)
        and abs(corrected_top) <= abs(top) + 1.0e-12
        and abs(corrected_drift) <= abs(drift) + 1.0e-12
        and abs(corrected_top) <= float(recommended_top_m)
        and abs(corrected_drift) <= float(recommended_drift_pct)
        and bool(metrics.get("linear_complexity_observed", False))
    )
    recompute = {
        "contract_pass": pass_value,
        "source": "gnn_residual_model_row_contract_recompute",
        "recompute_basis": "row_level_residual_contract_replay_not_full_fe_rerun",
        "model_api_version": MODEL_API_VERSION,
        "original_residual_top_displacement_m": top,
        "original_residual_drift_ratio_pct": drift,
        "residual_top_displacement_m": corrected_top,
        "residual_drift_ratio_pct": corrected_drift,
        "residual_metric_source": source,
        "residual_metric_fallback_used": fallback_used,
        "residual_l1_before": before,
        "residual_l1_after": after,
        "residual_reduction_ratio": reduction_ratio,
        "linear_complexity_observed": bool(metrics.get("linear_complexity_observed", False)),
        "operation_count_estimate": int(metrics.get("operation_count_estimate", 0) or 0),
        "corrected_node_count": len(corrected_nodes),
        "corrected_sample_node": corrected_nodes[-1] if corrected_nodes else None,
    }
    row_report = {
        "case_id": case_id,
        "contract_pass": pass_value,
        "source": recompute["source"],
        "original_residual_top_displacement_m": top,
        "original_residual_drift_ratio_pct": drift,
        "corrected_residual_top_displacement_m": corrected_top,
        "corrected_residual_drift_ratio_pct": corrected_drift,
        "residual_reduction_ratio": reduction_ratio,
        "reason_code": "PASS" if pass_value else "ERR_CORRECTED_STATE_RECOMPUTE",
    }
    return recompute, row_report


def materialize(
    *,
    ndtha_report: dict[str, Any],
    recommended_top_m: float,
    recommended_drift_pct: float,
    min_reduction_ratio: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = deepcopy(ndtha_report)
    rows = patched.get("rows") if isinstance(patched.get("rows"), list) else []
    recompute_rows: list[dict[str, Any]] = []
    corrected_top_values: list[float] = []
    corrected_drift_values: list[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        row_summary = row.setdefault("summary", {})
        if not isinstance(row_summary, dict):
            row["summary"] = {}
            row_summary = row["summary"]
        recompute, row_report = _row_recompute(
            row,
            recommended_top_m=recommended_top_m,
            recommended_drift_pct=recommended_drift_pct,
            min_reduction_ratio=min_reduction_ratio,
        )
        row_summary["gnn_corrected_state_recompute"] = recompute
        recompute_rows.append(row_report)
        if math.isfinite(float(recompute["residual_top_displacement_m"])):
            corrected_top_values.append(abs(float(recompute["residual_top_displacement_m"])))
        if math.isfinite(float(recompute["residual_drift_ratio_pct"])):
            corrected_drift_values.append(abs(float(recompute["residual_drift_ratio_pct"])))

    pass_count = sum(1 for row in recompute_rows if bool(row.get("contract_pass", False)))
    case_count = len(recompute_rows)
    contract_pass = bool(case_count > 0 and pass_count == case_count)

    patched_summary = patched.setdefault("summary", {})
    if isinstance(patched_summary, dict):
        patched_summary["gnn_corrected_state_recompute_case_count"] = case_count
        patched_summary["gnn_corrected_state_recompute_pass_count"] = pass_count
        patched_summary["gnn_corrected_state_residual_top_displacement_m_max_abs"] = (
            max(corrected_top_values) if corrected_top_values else 0.0
        )
        patched_summary["gnn_corrected_state_residual_drift_ratio_pct_max_abs"] = (
            max(corrected_drift_values) if corrected_drift_values else 0.0
        )

    sidecar = {
        "schema_version": "ndtha-corrected-state-recompute.v1",
        "run_id": "pm-release-ndtha-corrected-state-recompute",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_CORRECTED_STATE_RECOMPUTE",
        "checks": {
            "rows_present": case_count > 0,
            "all_rows_pass": pass_count == case_count and case_count > 0,
            "row_level_recompute_basis_declared": True,
            "full_fe_rerun_claimed": False,
        },
        "summary": {
            "case_count": case_count,
            "pass_count": pass_count,
            "recommended_residual_top_displacement_m": float(recommended_top_m),
            "recommended_residual_drift_ratio_pct": float(recommended_drift_pct),
            "min_reduction_ratio": float(min_reduction_ratio),
            "corrected_residual_top_displacement_m_max_abs": max(corrected_top_values) if corrected_top_values else 0.0,
            "corrected_residual_drift_ratio_pct_max_abs": max(corrected_drift_values) if corrected_drift_values else 0.0,
        },
        "limitations": [
            "This is a row-level NDTHA residual contract recompute because the checked-in NDTHA report does not contain full global DOF state.",
            "The recompute applies gnn_residual_model to a deterministic residual graph and replays the corrected residual metrics under the same row contract.",
            "This evidence is suitable for PM release traceability, but it is not an independent full finite-element rerun.",
        ],
        "rows": recompute_rows,
    }
    return patched, sidecar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ndtha-stress", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    parser.add_argument(
        "--out",
        default="implementation/phase1/release_evidence/productization/nonlinear_ndtha_stress.corrected_state_recompute.json",
    )
    parser.add_argument(
        "--sidecar-out",
        default="implementation/phase1/release_evidence/productization/ndtha_corrected_state_recompute_report.json",
    )
    parser.add_argument("--recommended-residual-top-displacement-m", type=float, default=1.0)
    parser.add_argument("--recommended-residual-drift-ratio-pct", type=float, default=2.0)
    parser.add_argument("--min-reduction-ratio", type=float, default=0.5)
    args = parser.parse_args()

    patched, sidecar = materialize(
        ndtha_report=_load_json(Path(args.ndtha_stress)),
        recommended_top_m=float(args.recommended_residual_top_displacement_m),
        recommended_drift_pct=float(args.recommended_residual_drift_ratio_pct),
        min_reduction_ratio=float(args.min_reduction_ratio),
    )

    out = Path(args.out)
    sidecar_out = Path(args.sidecar_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sidecar_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(patched, ensure_ascii=False, indent=2), encoding="utf-8")
    sidecar_out.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote corrected NDTHA stress report: {out}")
    print(f"Wrote corrected-state recompute sidecar: {sidecar_out}")
    return 0 if sidecar.get("contract_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
