#!/usr/bin/env python3
"""Validate nonlinear Lennard-Jones mapping kernel for plastic hinge behavior."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from nonlinear_lj_hinge_kernel import LJMappingConfig, simulate_lj_plastic_hinge

SCHEMA_VERSION = "1.0"
RUN_ID = "phase1-nonlinear-lj-mapping"

REASON_CODES = {
    "PASS": "nonlinear LJ mapping contract satisfied",
    "ERR_LJ_YIELD": "yield detection/strain mapping failed",
    "ERR_LJ_SOFTENING": "post-yield softening condition failed",
    "ERR_LJ_DISSIPATION": "energy dissipation condition failed",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--elastic-modulus-pa", type=float, default=210e9)
    p.add_argument("--yield-stress-pa", type=float, default=355e6)
    p.add_argument("--area-m2", type=float, default=0.015)
    p.add_argument("--gauge-length-m", type=float, default=6.0)
    p.add_argument("--damage-beta", type=float, default=1.2)
    p.add_argument("--strain-max-factor", type=float, default=8.0)
    p.add_argument("--points", type=int, default=240)
    p.add_argument("--out", default="implementation/phase1/nonlinear_lj_mapping_report.json")
    args = p.parse_args()

    cfg = LJMappingConfig(
        elastic_modulus_pa=float(args.elastic_modulus_pa),
        yield_stress_pa=float(args.yield_stress_pa),
        area_m2=float(args.area_m2),
        gauge_length_m=float(args.gauge_length_m),
        damage_beta=float(args.damage_beta),
        strain_max_factor=float(args.strain_max_factor),
        points=int(args.points),
    )

    result = simulate_lj_plastic_hinge(cfg)
    checks = result["checks"]

    if not checks["yield_detected"] or not checks["yield_strain_pass"]:
        reason_code = "ERR_LJ_YIELD"
    elif not checks["post_yield_softening_pass"]:
        reason_code = "ERR_LJ_SOFTENING"
    elif not checks["energy_dissipation_pass"]:
        reason_code = "ERR_LJ_DISSIPATION"
    else:
        reason_code = "PASS"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
        **result,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote nonlinear LJ mapping report: {out}")
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
