#!/usr/bin/env python3
"""CLI: build MIDAS Gen same-mesh result proxy JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_midas_gen_same_mesh_result_proxy import build_midas_gen_same_mesh_result_proxy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, required=True)
    parser.add_argument(
        "--commercial-crossval-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release_evidence/productization/commercial_solver_cross_validation.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    payload = build_midas_gen_same_mesh_result_proxy(
        roundtrip_json=args.roundtrip_json,
        commercial_crossval_json=args.commercial_crossval_json,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"midas-proxy: blockers={payload.get('blockers')}")
    return 0 if not payload.get("blockers") else 1


if __name__ == "__main__":
    raise SystemExit(main())
