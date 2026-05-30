#!/usr/bin/env python3
"""CLI: proxy vs solver divergence gate on optimization changes.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_proxy_solver_divergence_gate import analyze_changes, load_json, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--max-governing-dcr-after", type=float, default=1.35)
    parser.add_argument(
        "--fail-on-divergence",
        action="store_true",
        help="Exit 5 when any divergence row is recorded.",
    )
    args = parser.parse_args()
    if not args.changes_json.is_file():
        print(f"proxy-gate: missing {args.changes_json}", file=sys.stderr)
        return 2

    payload = load_json(args.changes_json)
    report = analyze_changes(payload, max_governing_dcr_after=args.max_governing_dcr_after)
    write_json(args.output_json, report)
    print(
        f"proxy-gate: {report['status']} "
        f"({report['divergence_count']} divergences / {report['change_count']} changes)"
    )
    if args.fail_on_divergence and report.get("divergence_count", 0) > 0:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
