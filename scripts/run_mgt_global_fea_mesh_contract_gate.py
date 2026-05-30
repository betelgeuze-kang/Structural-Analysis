#!/usr/bin/env python3
"""CLI: MGT global FEA mesh contract gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_global_fea_mesh_contract_gate import build_mgt_global_fea_mesh_contract_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    payload = build_mgt_global_fea_mesh_contract_gate(roundtrip_json=args.roundtrip_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"mgt-mesh-contract: {payload['status']} -> {args.output_json}")
    if args.fail_on_blocked and payload.get("status") != "ready":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
