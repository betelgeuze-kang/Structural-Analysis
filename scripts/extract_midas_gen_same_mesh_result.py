#!/usr/bin/env python3
"""CLI: extract model-derived same-mesh KPIs from optimized MGT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from extract_midas_gen_same_mesh_result import extract_midas_gen_same_mesh_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mgt-path",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--seismic-cs", type=float, default=None)
    parser.add_argument("--assumed-drift-pct", type=float, default=None)
    parser.add_argument(
        "--condensed-solve-json",
        type=Path,
        default=None,
        help="Optional condensed story solve JSON for NDTHA drift bridge.",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    payload = extract_midas_gen_same_mesh_result(
        mgt_path=args.mgt_path,
        roundtrip_json=args.roundtrip_json,
        condensed_solve_json=args.condensed_solve_json,
        seismic_coefficient=args.seismic_cs,
        assumed_elastic_drift_pct=args.assumed_drift_pct,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    d = payload["derivation"]
    print(
        f"midas-extract: W={d['seismic_weight_kN']:.0f}kN H={d['building_height_m']:.2f}m "
        f"V={payload['metrics']['base_shear_kN']:.0f}kN blockers={payload['blockers']}"
    )
    return 0 if not payload["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
