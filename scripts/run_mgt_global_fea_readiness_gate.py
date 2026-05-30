#!/usr/bin/env python3
"""CLI: MGT global FEA readiness preflight."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_global_fea_readiness_gate import (  # noqa: E402
    build_mgt_global_fea_readiness_gate,
    write_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--mgt",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    payload = build_mgt_global_fea_readiness_gate(
        roundtrip_json=args.roundtrip_json,
        mgt_path=args.mgt,
    )
    write_gate(args.output_json, payload)
    print(f"global-fea-readiness: {payload['status']} -> {args.output_json}")
    if args.fail_on_blocked and payload.get("status") != "ready":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
