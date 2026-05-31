#!/usr/bin/env python3
"""CLI: MIDAS same-mesh vs native solve comparison receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_midas_gen_same_mesh_native_comparison import run_midas_gen_same_mesh_native_comparison  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", type=Path, required=True)
    parser.add_argument("--roundtrip-json", type=Path, required=True)
    parser.add_argument(
        "--native-3d-solve-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/mgt_global_fea_3d_native_solve.json",
    )
    parser.add_argument(
        "--native-condensed-solve-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/mgt_global_fea_condensed_solve.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    payload = run_midas_gen_same_mesh_native_comparison(
        result_json=args.result_json,
        roundtrip_json=args.roundtrip_json,
        native_3d_solve_json=args.native_3d_solve_json,
        native_condensed_solve_json=args.native_condensed_solve_json,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"midas-native-compare: {payload.get('comparison_status')} status={payload.get('status')}")
    return 0 if payload.get("status") in {"ready", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
