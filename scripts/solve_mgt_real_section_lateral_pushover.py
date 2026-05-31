#!/usr/bin/env python3
"""CLI: cantilever / fixed-guided beam FE lateral pushover (real MGT sections)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from solve_mgt_real_section_lateral_pushover import solve_real_section_lateral_pushover  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-npz",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz",
    )
    parser.add_argument(
        "--mgt-path",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    parser.add_argument("--n-stories", type=int, default=12)
    parser.add_argument(
        "--boundary",
        choices=("cantilever", "fixed_guided", "both"),
        default="both",
        help="Lateral BC: cantilever, fixed-guided (top rotation fixed), or both in one JSON",
    )
    parser.add_argument("--wind-params-json", type=Path, default=None)
    parser.add_argument("--basic-wind-speed-mps", type=float, default=None)
    parser.add_argument("--exposure", type=str, default=None)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    payload = solve_real_section_lateral_pushover(
        roundtrip_npz=args.roundtrip_npz,
        mgt_path=args.mgt_path,
        n_stories=args.n_stories,
        boundary=args.boundary,
        wind_params_json=args.wind_params_json,
        basic_wind_speed_mps=args.basic_wind_speed_mps,
        exposure=args.exposure,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.boundary == "both" or payload.get("schema") == "wind_native_lateral_dual.v1":
        print(
            "mgt-native-lateral: "
            f"fixed_guided={payload.get('fixed_guided_drift_pct', 0):.6f}% "
            f"cantilever={payload.get('cantilever_drift_pct', 0):.6f}% "
            f"V={payload.get('base_shear_kn', 0):.0f}kN "
            f"n_stories={payload.get('n_stories')} "
            f"blockers={payload.get('blockers')}"
        )
    else:
        print(
            "mgt-native-lateral: "
            f"boundary={payload.get('boundary')} "
            f"max_drift={payload.get('max_story_drift_ratio_pct', 0):.6f}% "
            f"top_disp={payload.get('top_displacement_m', 0):.4f}m "
            f"V={payload.get('base_shear_kn', 0):.0f}kN "
            f"coverage={payload.get('real_section_coverage_pct', 0):.1f}% "
            f"n_stories={payload.get('n_stories')} "
            f"blockers={payload.get('blockers')}"
        )
    return 0 if payload.get("status") == "ready" and not payload.get("blockers") else 1


if __name__ == "__main__":
    raise SystemExit(main())
