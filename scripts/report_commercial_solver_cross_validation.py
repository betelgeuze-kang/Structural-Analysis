#!/usr/bin/env python3
"""CLI: commercial HF/LF benchmark cross-validation report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from report_commercial_solver_cross_validation import (  # noqa: E402
    build_cross_validation_report,
    load_cases_payload,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/commercial_benchmark_cases.from_csv.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit 4 when any case metric exceeds tolerance.",
    )
    args = parser.parse_args()
    if not args.cases_json.is_file():
        print(f"crossval: missing cases json: {args.cases_json}", file=sys.stderr)
        return 2

    payload = load_cases_payload(args.cases_json)
    report = build_cross_validation_report(payload)
    write_report(args.output_json, report)
    print(
        f"crossval: {report['status']} "
        f"({report['cases_passed']}/{report['case_count']} cases, "
        f"{report['metric_failures']} metric failures)"
    )
    if args.fail_on_mismatch and report.get("status") != "pass":
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
