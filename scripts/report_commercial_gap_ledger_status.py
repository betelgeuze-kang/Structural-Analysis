#!/usr/bin/env python3
"""Write the commercial solver and AI-engine gap-ledger status matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.commercial_gap_ledger_status import (  # noqa: E402
    PRODUCTIZATION,
    build_commercial_gap_ledger_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--productization-dir",
        type=Path,
        default=PRODUCTIZATION,
        help="Directory containing productization evidence JSON inputs.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--fail-open",
        action="store_true",
        help="Exit non-zero when any ledger requirement remains open, partial, external-blocked, or undocumented.",
    )
    args = parser.parse_args()

    output_json = args.output_json or (args.productization_dir / "commercial_gap_ledger_status.json")
    payload = build_commercial_gap_ledger_status(productization_dir=args.productization_dir)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = payload["summary"]
    print(
        "commercial-gap-ledger: "
        f"status={payload['status']} "
        f"closed={summary['closed_count']}/{summary['total_count']} "
        f"partial={summary['partial_count']} open={summary['open_count']} "
        f"external_blocked={summary['external_blocked_count']} -> {output_json}"
    )
    if args.fail_open and not payload.get("full_gap_ledger_ready"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
