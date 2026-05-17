#!/usr/bin/env python3
"""Report tracked source-boundary footprint without mutating repository state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from plan_source_boundary_cleanup import (  # noqa: E402
    BYTES_PER_MIB,
    DEFAULT_ALLOWLIST_MANIFEST,
    DEFAULT_LARGE_FILE_THRESHOLD_MIB,
    _git_files,
    _read_allowlist,
    _read_tracked_files,
    build_plan,
)


SCHEMA_VERSION = "source-boundary-footprint-report.v1"
DEFAULT_RESTORE_RUNBOOK = Path("docs/source-boundary-restore-runbook.md")


def _format_mib(size_bytes: int | float) -> float:
    return round(float(size_bytes) / BYTES_PER_MIB, 3)


def _sum_allowlisted_bytes_by_classification(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        classification = str(row.get("classification", "") or "")
        totals[classification] = totals.get(classification, 0) + int(row.get("bytes") or 0)
    return totals


def build_footprint_report(
    *,
    files: list[str],
    allowlist_manifest: Path = DEFAULT_ALLOWLIST_MANIFEST,
    restore_runbook: Path = DEFAULT_RESTORE_RUNBOOK,
    large_file_threshold_mib: float = DEFAULT_LARGE_FILE_THRESHOLD_MIB,
) -> dict[str, Any]:
    plan = build_plan(
        files,
        large_file_threshold_mib=large_file_threshold_mib,
        allowlist=_read_allowlist(allowlist_manifest),
    )
    allowlisted_records = [
        row for row in plan.get("allowlisted_records", []) if isinstance(row, dict)
    ]
    allowlisted_bytes_by_classification = _sum_allowlisted_bytes_by_classification(allowlisted_records)
    candidate_files = int(plan.get("total_candidate_files", 0) or 0)
    restore_runbook_present = restore_runbook.exists()
    contract_pass = bool(plan.get("contract_pass")) and restore_runbook_present
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_SOURCE_BOUNDARY_FOOTPRINT_CONTRACT",
        "non_destructive_policy": True,
        "cleanup_policy": "report_only_no_git_rm_cached_no_history_rewrite",
        "large_file_threshold_mib": float(large_file_threshold_mib),
        "total_tracked_files": int(plan.get("total_tracked_files", 0) or 0),
        "candidate_files": candidate_files,
        "candidate_bytes": int(plan.get("total_candidate_bytes", 0) or 0),
        "candidate_mib": _format_mib(int(plan.get("total_candidate_bytes", 0) or 0)),
        "allowlisted_files": int(plan.get("total_allowlisted_files", 0) or 0),
        "allowlisted_bytes": int(plan.get("total_allowlisted_bytes", 0) or 0),
        "allowlisted_mib": _format_mib(int(plan.get("total_allowlisted_bytes", 0) or 0)),
        "allowlisted_counts_by_classification": plan.get("allowlisted_counts_by_classification", {}),
        "allowlisted_mib_by_classification": {
            classification: _format_mib(size)
            for classification, size in sorted(allowlisted_bytes_by_classification.items())
        },
        "allowlist_manifest": str(allowlist_manifest),
        "restore_runbook": str(restore_runbook),
        "restore_runbook_present": restore_runbook_present,
        "next_action": (
            "keep non-destructive source-boundary gate active"
            if contract_pass
            else "resolve cleanup candidates or add the restore runbook"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON diagnostics")
    parser.add_argument("--check", action="store_true", help="fail when footprint contract is not closed")
    parser.add_argument("--tracked-files", type=Path, help="read tracked file fixture instead of git ls-files")
    parser.add_argument(
        "--allowlist-manifest",
        type=Path,
        default=DEFAULT_ALLOWLIST_MANIFEST,
        help="source-boundary allowlist manifest",
    )
    parser.add_argument(
        "--restore-runbook",
        type=Path,
        default=DEFAULT_RESTORE_RUNBOOK,
        help="restore runbook required by the non-destructive footprint contract",
    )
    parser.add_argument(
        "--large-file-threshold-mib",
        type=float,
        default=10.0,
        help="large file threshold used by PR source-boundary gate",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    files = _read_tracked_files(args.tracked_files) if args.tracked_files else _git_files()
    payload = build_footprint_report(
        files=files,
        allowlist_manifest=args.allowlist_manifest,
        restore_runbook=args.restore_runbook,
        large_file_threshold_mib=args.large_file_threshold_mib,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.check and not bool(payload["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
