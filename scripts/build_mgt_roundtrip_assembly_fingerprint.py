#!/usr/bin/env python3
"""CLI: MGT roundtrip assembly fingerprint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_mgt_roundtrip_assembly_fingerprint import build_mgt_roundtrip_assembly_fingerprint  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    payload = build_mgt_roundtrip_assembly_fingerprint(roundtrip_json=args.roundtrip_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"mgt-fingerprint: {payload['status']} sha={payload.get('fingerprint_sha256', '')[:12]}")
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
