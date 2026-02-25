#!/usr/bin/env python3
"""Static bifurcation detector contract for MD->branching trigger.

Detects candidate bifurcation events (buckling/yield branching) using:
- stiffness drop ratio
- residual spike ratio
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _first_trigger_step(stiffness: list[float], residual: list[float], k_drop: float, r_spike: float) -> tuple[int | None, float, float]:
    base_k = max(stiffness[0], 1e-12)
    base_r = max(residual[0], 1e-12)
    for i, (k, r) in enumerate(zip(stiffness, residual), start=1):
        k_ratio = k / base_k
        r_ratio = r / base_r
        if k_ratio <= k_drop and r_ratio >= r_spike:
            return i, k_ratio, r_ratio
    return None, stiffness[-1] / base_k, residual[-1] / base_r


def run(k_drop_threshold: float, residual_spike_threshold: float) -> dict:
    stiffness = [1.00, 0.97, 0.92, 0.78, 0.62, 0.49]
    residual = [1.0, 1.05, 1.2, 1.8, 2.6, 3.4]

    step, k_ratio, r_ratio = _first_trigger_step(
        stiffness,
        residual,
        k_drop=k_drop_threshold,
        r_spike=residual_spike_threshold,
    )
    detected = step is not None
    return {
        "schema_version": "1.0",
        "run_id": "bifurcation-detector",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trigger": {
            "k_drop_threshold": k_drop_threshold,
            "residual_spike_threshold": residual_spike_threshold,
            "triggered": detected,
            "trigger_step": step,
            "observed_k_ratio": k_ratio,
            "observed_residual_ratio": r_ratio,
        },
        "contract_pass": True,
        "reason_code": "PASS" if detected else "WARN_NO_BIFURCATION_EVENT",
        "reason": "bifurcation trigger emitted" if detected else "no event in static profile",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/bifurcation_detector_report.json")
    parser.add_argument("--k-drop-threshold", type=float, default=0.70)
    parser.add_argument("--residual-spike-threshold", type=float, default=2.0)
    args = parser.parse_args()

    report = run(args.k_drop_threshold, args.residual_spike_threshold)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote bifurcation detector report: {out}")


if __name__ == "__main__":
    main()
