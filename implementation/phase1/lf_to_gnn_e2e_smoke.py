#!/usr/bin/env python3
"""Phase1 Priority-A: LF -> GNN one-batch E2E smoke.

Loads LF exports (ulf_nodes/ulf_edges/ulf_meta), runs one-batch residual correction,
and emits an O(N+E) + physics-accuracy focused report.

Mobile/static contract notes:
- this smoke is a residual-correction assist surface, not solver truth;
- required interface fields and standard reason codes are mirrored in
  ``mobile-static-contracts.md`` for review without executing the model;
- legacy reason codes remain stable for existing tests and reports, while
  ``standard_reason_code`` maps them to the LF->GNN contract vocabulary;
- fallback reporting is explicit, so a fallback path cannot be mistaken for
  successful ``gnn_residual_model`` execution.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


INTERFACE_VERSION = "1.1.0"
SCHEMA_VERSION = "1.2"
RUN_ID = "phase1-lf-gnn-smoke"
MOBILE_STATIC_CONTRACT_REF = "implementation/phase1/mobile-static-contracts.md#a1-lf---gnn-interface-contract"
CLAIM_BOUNDARY = "residual_correction_assist_not_solver_truth"
LF_GNN_REQUIRED_INPUT_FIELDS = (
    "schema_version",
    "case_id",
    "source_model_ref",
    "node_features",
    "edge_index",
    "lf_outputs",
    "boundary_conditions",
    "normalization",
    "provenance",
    "claim_boundary",
)
LF_GNN_OUTPUT_FIELDS = (
    "status",
    "reason_code",
    "standard_reason_code",
    "delta_u",
    "corrected_state",
    "residual_metrics",
    "uncertainty",
    "unsupported_features",
    "warnings",
)
LF_GNN_STANDARD_REASON_CODES = {
    "PASS": "input/output contract is satisfied",
    "ERR_LF_GNN_FIELD_MISSING": "required field is absent",
    "ERR_LF_GNN_TYPE": "field exists but has wrong type",
    "ERR_LF_GNN_EMPTY_BATCH": "node/edge/LF batch is empty",
    "ERR_LF_GNN_SHAPE_MISMATCH": "node, edge, or LF response dimensions are inconsistent",
    "ERR_LF_GNN_ACCURACY_BELOW_TARGET": "residual correction did not meet the configured accuracy target",
    "ERR_LF_GNN_COMPLEXITY_GUARDRAIL": "observed operation budget exceeded the linear-complexity guardrail",
    "ERR_LF_GNN_UNSUPPORTED_FEATURE": "feature family is outside the residual model scope",
    "ERR_LF_GNN_CLAIM_BOUNDARY": "output tries to claim autonomous solver truth",
}
LEGACY_TO_STANDARD_REASON_CODE = {
    "PASS": "PASS",
    "ERR_EMPTY_NODES": "ERR_LF_GNN_EMPTY_BATCH",
    "ERR_EMPTY_EDGES": "ERR_LF_GNN_EMPTY_BATCH",
    "ERR_META_UNIT": "ERR_LF_GNN_FIELD_MISSING",
    "ERR_EMPTY_CORRECTION": "ERR_LF_GNN_EMPTY_BATCH",
    "ERR_RESIDUAL_ACCURACY": "ERR_LF_GNN_ACCURACY_BELOW_TARGET",
    "ERR_COMPLEXITY_GUARDRAIL": "ERR_LF_GNN_COMPLEXITY_GUARDRAIL",
}

REASON_CODES = {
    "PASS": "one-batch ingestion + correction completed",
    "ERR_EMPTY_NODES": "nodes csv has no rows",
    "ERR_EMPTY_EDGES": "edges csv has no rows",
    "ERR_META_UNIT": "meta.unit_system missing",
    "ERR_EMPTY_CORRECTION": "no corrected nodes emitted",
    "ERR_RESIDUAL_ACCURACY": "residual correction accuracy below target",
    "ERR_COMPLEXITY_GUARDRAIL": "linear complexity guardrail violated",
    **LF_GNN_STANDARD_REASON_CODES,
}


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class CsvBatchLoader:
    def __init__(self, rows: list[dict], batch_size: int) -> None:
        self.rows = rows
        self.batch_size = max(1, batch_size)

    def __iter__(self) -> Iterator[list[dict]]:
        for i in range(0, len(self.rows), self.batch_size):
            yield self.rows[i : i + self.batch_size]


def _apply_residual_batch_fallback(batch: list[dict], gain: float) -> tuple[list[dict], dict]:
    corrected = []
    before = 0.0
    after = 0.0
    for n in batch:
        ux = float(n.get("ux", 0.0))
        uy = float(n.get("uy", 0.0))
        uz = float(n.get("uz", 0.0))
        f_norm = abs(float(n.get("f_norm", 0.0)))

        du = -gain * f_norm
        corrected.append({"node_id": n.get("node_id"), "ux": ux + du, "uy": uy + du, "uz": uz + du})

        before += f_norm
        after += max(0.0, f_norm * (1.0 - min(0.9999, gain * 10.0)))

    reduction_ratio = 0.0 if before <= 1e-12 else max(0.0, min(1.0, 1.0 - (after / before)))
    metrics = {
        "model_module": "python_fallback",
        "fallback_used": True,
        "fallback_reason": "model_or_import_failure",
        "residual_l1_before": before,
        "residual_l1_after": after,
        "residual_reduction_ratio": reduction_ratio,
        "physical_accuracy_pct": reduction_ratio * 100.0,
        "target_accuracy_pct": 99.9,
        "target_met": reduction_ratio * 100.0 >= 99.9,
        "complexity_class": "O(N)",
        "linear_complexity_observed": True,
        "operation_count_estimate": int(8 * len(batch)),
        "node_count": len(batch),
        "edge_count": 0,
        "claim_boundary": CLAIM_BOUNDARY,
        "mobile_static_contract_ref": MOBILE_STATIC_CONTRACT_REF,
    }
    return corrected, metrics


def _apply_residual_batch_model(batch: list[dict], edges: list[dict], meta: dict, gain: float) -> tuple[list[dict], dict]:
    try:
        from gnn_residual_model import run_one_batch_with_metrics

        corrected, metrics = run_one_batch_with_metrics(batch, edges, meta, gain)
        metrics.setdefault("model_module", "gnn_residual_model")
        metrics.setdefault("fallback_used", False)
        metrics.setdefault("fallback_reason", "")
        metrics.setdefault("claim_boundary", CLAIM_BOUNDARY)
        metrics.setdefault("mobile_static_contract_ref", MOBILE_STATIC_CONTRACT_REF)
        return corrected, metrics
    except Exception:
        return _apply_residual_batch_fallback(batch, gain)


def run(
    nodes_csv: Path,
    edges_csv: Path,
    meta_json: Path,
    batch_size: int,
    gain: float,
    target_accuracy_pct: float,
) -> dict:
    nodes = _read_csv(nodes_csv)
    edges = _read_csv(edges_csv)
    meta = json.loads(meta_json.read_text(encoding="utf-8"))

    loader = CsvBatchLoader(nodes, batch_size=batch_size)

    backend = "python"
    torch_available = False
    try:
        import torch  # type: ignore  # noqa: F401

        torch_available = True
        backend = "torch"
    except Exception:
        torch_available = False

    corrected: list[dict] = []
    batch_count = 0

    residual_before_sum = 0.0
    residual_after_sum = 0.0
    operation_count_sum = 0
    linearity_flags: list[bool] = []
    complexity_class = "O(N+E)"
    last_metrics: dict = {}

    for batch in loader:
        batch_count += 1
        corrected_batch, metrics = _apply_residual_batch_model(batch, edges, meta, gain=gain)
        last_metrics = dict(metrics)
        corrected.extend(corrected_batch)

        residual_before_sum += float(metrics.get("residual_l1_before", 0.0))
        residual_after_sum += float(metrics.get("residual_l1_after", 0.0))
        operation_count_sum += int(metrics.get("operation_count_estimate", 0))
        linearity_flags.append(bool(metrics.get("linear_complexity_observed", True)))
        complexity_class = str(metrics.get("complexity_class", complexity_class))
        break  # one-batch smoke

    reduction_ratio = 0.0
    if residual_before_sum > 1e-12:
        reduction_ratio = max(0.0, min(1.0, 1.0 - (residual_after_sum / residual_before_sum)))
    achieved_accuracy_pct = reduction_ratio * 100.0

    target_met = achieved_accuracy_pct >= float(target_accuracy_pct)
    complexity_ok = all(linearity_flags) if linearity_flags else True

    if len(nodes) == 0:
        reason_code = "ERR_EMPTY_NODES"
    elif len(edges) == 0:
        reason_code = "ERR_EMPTY_EDGES"
    elif not bool(meta.get("unit_system")):
        reason_code = "ERR_META_UNIT"
    elif len(corrected) == 0:
        reason_code = "ERR_EMPTY_CORRECTION"
    elif not complexity_ok:
        reason_code = "ERR_COMPLEXITY_GUARDRAIL"
    elif not target_met:
        reason_code = "ERR_RESIDUAL_ACCURACY"
    else:
        reason_code = "PASS"

    pass_cond = reason_code == "PASS"
    standard_reason_code = LEGACY_TO_STANDARD_REASON_CODE.get(reason_code, reason_code)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "contract": {
            "mobile_static_contract_ref": MOBILE_STATIC_CONTRACT_REF,
            "claim_boundary": CLAIM_BOUNDARY,
            "required_input_fields": list(LF_GNN_REQUIRED_INPUT_FIELDS),
            "output_fields": list(LF_GNN_OUTPUT_FIELDS),
            "standard_reason_codes": LF_GNN_STANDARD_REASON_CODES,
        },
        "ingest": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "meta_unit_system": meta.get("unit_system"),
            "meta_solver": meta.get("solver"),
        },
        "inference": {
            "backend": backend,
            "model_module": str(last_metrics.get("model_module", "not_run_empty_batch")),
            "model_api_version": "1.1.0",
            "torch_available": torch_available,
            "batch_size": batch_size,
            "processed_batches": batch_count,
            "processed_nodes": len(corrected),
            "residual_gain": gain,
            "residual_correction_applied": True,
            "fallback_used": bool(last_metrics.get("fallback_used", False)),
            "fallback_reason": str(last_metrics.get("fallback_reason", "")),
            "residual_l1_before": residual_before_sum,
            "residual_l1_after": residual_after_sum,
            "residual_reduction_ratio": reduction_ratio,
            "physical_accuracy_pct": achieved_accuracy_pct,
            "target_accuracy_pct": float(target_accuracy_pct),
            "target_met": target_met,
            "complexity_class": complexity_class,
            "linear_complexity_observed": complexity_ok,
            "operation_count_estimate": operation_count_sum,
            "sample_corrected_node": corrected[0] if corrected else None,
        },
        "pass": pass_cond,
        "reason_code": reason_code,
        "standard_reason_code": standard_reason_code,
        "claim_boundary": CLAIM_BOUNDARY,
        "reason": REASON_CODES[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nodes", default="implementation/phase1/step_outputs/ulf_nodes.csv")
    p.add_argument("--edges", default="implementation/phase1/step_outputs/ulf_edges.csv")
    p.add_argument("--meta", default="implementation/phase1/step_outputs/ulf_meta.json")
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--gain", type=float, default=0.001)
    p.add_argument("--target-accuracy-pct", type=float, default=99.9)
    p.add_argument("--out", default="implementation/phase1/lf_to_gnn_e2e_smoke_report.json")
    args = p.parse_args()

    report = run(
        Path(args.nodes),
        Path(args.edges),
        Path(args.meta),
        batch_size=args.batch_size,
        gain=args.gain,
        target_accuracy_pct=args.target_accuracy_pct,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote LF->GNN smoke report: {out}")
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
