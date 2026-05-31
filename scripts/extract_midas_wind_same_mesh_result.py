#!/usr/bin/env python3
"""CLI: extract wind-load model-derived same-mesh KPIs from optimized MGT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from extract_midas_wind_same_mesh_result import extract_midas_wind_same_mesh_result  # noqa: E402


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
    parser.add_argument("--wind-params-json", type=Path, default=None)
    parser.add_argument("--basic-wind-speed-mps", type=float, default=None, help="Override site basic wind speed (m/s)")
    parser.add_argument("--exposure", type=str, default=None, help="Override terrain exposure (A/B/C/D)")
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    payload = extract_midas_wind_same_mesh_result(
        mgt_path=args.mgt_path,
        roundtrip_json=args.roundtrip_json,
        wind_params_json=args.wind_params_json,
        basic_wind_speed_mps=args.basic_wind_speed_mps,
        exposure=args.exposure,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    d = payload.get("derivation", {})
    m = payload.get("metrics", {})
    asm = payload.get("assumptions", {})
    wd = payload.get("wind_directional", {})
    torsion = wd.get("accidental_torsion", {})
    print(
        f"midas-wind-extract: V={m.get('base_shear_kN', 0):.0f}kN drift={m.get('drift_ratio_pct', 0):.4f}% "
        f"({asm.get('lateral_stiffness_basis')},conf={payload.get('confidence',{}).get('drift_ratio_pct')}) "
        f"gov_dir={wd.get('governing_direction')} torsion_amp={torsion.get('governing_amplification', 0):.4f} "
        f"Vw={asm.get('resolved_basic_wind_speed_mps')}m/s exp={asm.get('resolved_exposure')} "
        f"plan={d.get('plan_dim_x_m', 0):.1f}x{d.get('plan_dim_y_m', 0):.1f}m blockers={payload.get('blockers')}"
    )
    return 0 if not payload.get("blockers") else 1


if __name__ == "__main__":
    raise SystemExit(main())
