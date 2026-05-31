#!/usr/bin/env python3
"""CLI: CSV one-row summary → midas-gen-same-mesh-result.v1 JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from convert_midas_gen_table_export_to_result import convert_midas_gen_table_export_to_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--roundtrip-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--kind", default="midas_gen_live_export")
    parser.add_argument("--load-case", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    payload = convert_midas_gen_table_export_to_result(
        csv_path=args.csv,
        roundtrip_json=args.roundtrip_json,
        output_json=args.output_json,
        kind=args.kind,
        load_case=args.load_case,
        run_id=args.run_id,
        note=args.note,
    )
    print(f"midas-convert: kind={payload['source']['kind']} metrics={payload['metrics']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
