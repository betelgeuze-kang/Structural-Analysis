#!/usr/bin/env python3
"""CLI: validate midas-gen-same-mesh-result.v1 JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from validate_midas_gen_same_mesh_result import validate_midas_gen_same_mesh_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", type=Path, required=True)
    parser.add_argument("--roundtrip-json", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()
    roundtrip = args.roundtrip_json
    if roundtrip is None and args.result_json.parent.name == "midas":
        candidate = args.result_json.parent / "midas_generator_33.optimized.roundtrip.json"
        if candidate.is_file():
            roundtrip = candidate
    payload = validate_midas_gen_same_mesh_result(result_json=args.result_json, roundtrip_json=roundtrip)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"midas-validate: {payload['status']} live_ready={payload.get('live_export_ready')} "
        f"failed={payload.get('failed_checks')}"
    )
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
