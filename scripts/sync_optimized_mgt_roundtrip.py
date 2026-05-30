#!/usr/bin/env python3
"""Sync or re-parse optimized MGT into roundtrip JSON (+ NPZ)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from sync_mgt_roundtrip_provenance import (  # noqa: E402
    refresh_optimized_roundtrip_from_mgt,
    sync_roundtrip_source_from_mgt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mgt",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--npz-out", type=Path, default=None)
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Update sha256/size in roundtrip JSON without re-parsing MGT.",
    )
    parser.add_argument(
        "--parse",
        action="store_true",
        help="Re-parse MGT into roundtrip JSON and NPZ (slow).",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    if not args.mgt.is_file():
        print(f"sync-mgt: missing {args.mgt}", file=sys.stderr)
        return 2

    if args.sync_only:
        result = sync_roundtrip_source_from_mgt(roundtrip_json=args.roundtrip_json, mgt_path=args.mgt)
        payload = {"status": result.get("status"), "sync": result}
    elif args.parse:
        payload = refresh_optimized_roundtrip_from_mgt(
            mgt_path=args.mgt,
            roundtrip_json=args.roundtrip_json,
            npz_out=args.npz_out,
            parse_refresh=True,
            sync_provenance_only=False,
        )
    else:
        payload = refresh_optimized_roundtrip_from_mgt(
            mgt_path=args.mgt,
            roundtrip_json=args.roundtrip_json,
            npz_out=args.npz_out,
            parse_refresh=False,
            sync_provenance_only=True,
        )

    print(
        f"sync-mgt: {payload.get('status')} "
        f"sha={payload.get('sha256') or (payload.get('sync') or {}).get('sha256')}"
    )
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if payload.get("status") in {"ready", "synced"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
