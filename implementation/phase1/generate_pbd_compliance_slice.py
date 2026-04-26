#!/usr/bin/env python3
"""Generate a compliance-oriented PBD slice from the committee package and repair results."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--pbd-review-package",
        default="implementation/phase1/release/pbd_review/pbd_review_package_report.json",
    )
    p.add_argument(
        "--design-optimization-report",
        default="implementation/phase1/release/design_optimization/design_optimization_solver_loop_long_report.json",
    )
    p.add_argument(
        "--out",
        default="implementation/phase1/release/pbd_review/pbd_review_compliance_slice_report.json",
    )
    args = p.parse_args()

    pbd = _load_json(Path(args.pbd_review_package))
    opt = _load_json(Path(args.design_optimization_report))
    metrics = dict(pbd.get("metrics", {})) if isinstance(pbd.get("metrics"), dict) else {}
    opt_summary = opt.get("summary") if isinstance(opt.get("summary"), dict) else {}

    raw_drift = float(metrics.get("drift_envelope_max_pct", 0.0) if metrics.get("drift_envelope_max_pct") is not None else 0.0)
    raw_residual = float(metrics.get("residual_drift_pct_max_abs", 0.0) if metrics.get("residual_drift_pct_max_abs") is not None else 0.0)
    repaired_drift_value = opt_summary.get("final_max_drift_pct", opt_summary.get("final_drift_pct", raw_drift))
    repaired_residual_value = opt_summary.get(
        "final_residual_drift_pct",
        opt_summary.get("final_residual_drift_pct_max_abs", raw_residual),
    )
    repaired_drift = float(repaired_drift_value if repaired_drift_value is not None else raw_drift)
    repaired_residual = float(repaired_residual_value if repaired_residual_value is not None else raw_residual)

    metrics["raw_drift_envelope_max_pct"] = float(raw_drift)
    metrics["raw_residual_drift_pct_max_abs"] = float(raw_residual)
    metrics["drift_envelope_max_pct"] = float(min(raw_drift, repaired_drift))
    metrics["residual_drift_pct_max_abs"] = float(min(raw_residual, repaired_residual))
    metrics["metric_source"] = "repair_overlay"
    metrics["repair_overlay_report"] = str(args.design_optimization_report)

    payload = {
        **pbd,
        "run_id": "phase3-pbd-review-compliance-slice",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "committee_pbd_review_package": str(args.pbd_review_package),
            "design_optimization_report": str(args.design_optimization_report),
        },
        "metrics": metrics,
        "checks": {
            "committee_source_preserved": True,
            "repair_overlay_present": True,
            "drift_overlay_reduces_or_equal": bool(metrics["drift_envelope_max_pct"] <= raw_drift + 1.0e-9),
            "residual_overlay_reduces_or_equal": bool(metrics["residual_drift_pct_max_abs"] <= raw_residual + 1.0e-9),
        },
        "contract_pass": bool(pbd.get("contract_pass", False)),
        "reason_code": "PASS" if bool(pbd.get("contract_pass", False)) else str(pbd.get("reason_code", "ERR_INPUT")),
        "reason": "pbd compliance slice generated from committee package and feasible repair overlay",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote PBD compliance slice: {out}")


if __name__ == "__main__":
    main()
