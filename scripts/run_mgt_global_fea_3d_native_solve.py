#!/usr/bin/env python3
"""CLI: MGT NPZ 3D beam mesh global solve + licensed-solver proxy crosscheck."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_global_fea_3d_native_solve import run_mgt_global_fea_3d_native_solve  # noqa: E402


def main() -> int:
    productization = REPO_ROOT / "implementation/phase1/release_evidence/productization"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--output-json", type=Path, default=productization / "mgt_global_fea_3d_native_solve.json")
    parser.add_argument("--commercial-crossval-json", type=Path, default=productization / "commercial_solver_cross_validation.json")
    args = parser.parse_args()
    payload = run_mgt_global_fea_3d_native_solve(
        roundtrip_json=args.roundtrip_json,
        commercial_crossval_json=args.commercial_crossval_json,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"mgt-3d-native: {payload.get('native_solve_status')} -> {args.output_json}")
    ok_statuses = {"mesh_3d_beam_global_wired", "mesh_3d_beam_global_wired_with_licensed_fingerprint_bridge"}
    return 0 if payload.get("native_solve_status") in ok_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main())
