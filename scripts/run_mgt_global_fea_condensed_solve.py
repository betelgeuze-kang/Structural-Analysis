#!/usr/bin/env python3
"""CLI: MGT NPZ condensed global-FEA proxy solve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_global_fea_condensed_solve import run_mgt_global_fea_condensed_solve  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/mgt_global_fea_condensed_solve.json",
    )
    args = parser.parse_args()
    payload = run_mgt_global_fea_condensed_solve(roundtrip_json=args.roundtrip_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"mgt-condensed-solve: {payload.get('native_solve_status')} -> {args.output_json}")
    return 0 if payload.get("status") == "ready" and not payload.get("blockers") else 1


if __name__ == "__main__":
    raise SystemExit(main())
