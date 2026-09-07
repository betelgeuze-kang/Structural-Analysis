#!/usr/bin/env python3
"""Materialize a non-authoritative NDTHA correction proposal diagnostic.

The checked-in NDTHA stress report carries row-level residual metrics rather
than full global DOF states. This script applies the local LF->GNN residual
heuristic to a deterministic row-level graph. There is no force residual
operator or full global state here: corrected physical metrics remain null
and the corrected-state recompute contract cannot pass.
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
    # A reduction of this mixed-unit synthetic row scalar is not a recompute
    # of displacement, drift, or force equilibrium at the proposed state.
    pass_value = False
    unavailable_reason = "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE"
    recompute = {
        "contract_pass": pass_value,
        "source": "gnn_residual_model_row_heuristic_proposal",
        "recompute_basis": "unavailable_solver_recompute_required",
        "algorithm_kind": metrics["algorithm_kind"],
        "heuristic_basis": "mixed_unit_row_scalar_not_force_residual",
        "solver_recomputed": False,
        "physical_metrics_status": "unavailable",
        "reason_code": unavailable_reason,
        "model_api_version": MODEL_API_VERSION,
        "original_residual_top_displacement_m": top if math.isfinite(top) else None,
        "original_residual_drift_ratio_pct": drift if math.isfinite(drift) else None,
        "original_residual_metric_source": source,
        "original_residual_metric_fallback_used": fallback_used,
        "residual_top_displacement_m": None,
        "residual_drift_ratio_pct": None,
        "residual_metric_source": "unavailable",
        "residual_l1_before": None,
        "residual_l1_after": None,
        "residual_reduction_ratio": None,
        "physical_accuracy_pct": None,
        "heuristic_state_l1_before": metrics["heuristic_state_l1_before"],
        "heuristic_state_l1_after": metrics["heuristic_state_l1_after"],
        "heuristic_state_reduction_ratio": metrics["heuristic_state_reduction_ratio"],
        "requested_thresholds": {
            "recommended_residual_top_displacement_m": float(recommended_top_m),
            "recommended_residual_drift_ratio_pct": float(recommended_drift_pct),
            "min_reduction_ratio": float(min_reduction_ratio),
        },
        "linear_complexity_observed": bool(metrics.get("linear_complexity_observed", False)),
        "operation_count_estimate": int(metrics.get("operation_count_estimate", 0) or 0),
        "corrected_node_count": len(corrected_nodes),
        "corrected_sample_node": corrected_nodes[-1] if corrected_nodes else None,
    }
    row_report = {
        "case_id": case_id,
        "contract_pass": pass_value,
        "source": recompute["source"],
        "original_residual_top_displacement_m": recompute["original_residual_top_displacement_m"],
        "original_residual_drift_ratio_pct": recompute["original_residual_drift_ratio_pct"],
        "corrected_residual_top_displacement_m": None,
        "corrected_residual_drift_ratio_pct": None,
        "residual_reduction_ratio": None,
        "physical_metrics_status": "unavailable",
        "reason_code": unavailable_reason,
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
        corrected_top = _finite(recompute["residual_top_displacement_m"])
        corrected_drift = _finite(recompute["residual_drift_ratio_pct"])
        if math.isfinite(corrected_top):
            corrected_top_values.append(abs(corrected_top))
        if math.isfinite(corrected_drift):
            corrected_drift_values.append(abs(corrected_drift))

    pass_count = sum(1 for row in recompute_rows if bool(row.get("contract_pass", False)))
    case_count = len(recompute_rows)
    contract_pass = bool(case_count > 0 and pass_count == case_count)

    patched_summary = patched.setdefault("summary", {})
    if isinstance(patched_summary, dict):
        patched_summary["gnn_corrected_state_recompute_case_count"] = case_count
        patched_summary["gnn_corrected_state_recompute_pass_count"] = pass_count
        patched_summary["gnn_corrected_state_residual_top_displacement_m_max_abs"] = (
            max(corrected_top_values) if corrected_top_values else None
        )
        patched_summary["gnn_corrected_state_residual_drift_ratio_pct_max_abs"] = (
            max(corrected_drift_values) if corrected_drift_values else None
        )

    sidecar = {
        "schema_version": "ndtha-corrected-state-recompute.v1",
        "run_id": "pm-release-ndtha-corrected-state-recompute",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE",
        "physical_metrics_status": "unavailable",
        "checks": {
            "rows_present": case_count > 0,
            "all_rows_pass": pass_count == case_count and case_count > 0,
            "row_level_recompute_basis_declared": False,
            "heuristic_proposal_basis_declared": True,
            "full_fe_rerun_claimed": False,
        },
        "summary": {
            "case_count": case_count,
            "pass_count": pass_count,
            "recommended_residual_top_displacement_m": float(recommended_top_m),
            "recommended_residual_drift_ratio_pct": float(recommended_drift_pct),
            "min_reduction_ratio": float(min_reduction_ratio),
            "corrected_residual_top_displacement_m_max_abs": max(corrected_top_values) if corrected_top_values else None,
            "corrected_residual_drift_ratio_pct_max_abs": max(corrected_drift_values) if corrected_drift_values else None,
        },
        "limitations": [
            "The source report does not contain full global DOF state or a force residual evaluator.",
            "The fixed-coefficient heuristic contracts a mixed-unit synthetic row scalar; it does not recompute corrected displacement or drift.",
            "Physical metrics and corrected-state recompute approval require an actual solver evaluation; this diagnostic cannot supply release evidence.",
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
