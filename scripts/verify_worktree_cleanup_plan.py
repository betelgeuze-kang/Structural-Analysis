#!/usr/bin/env python3
"""Verify a generated worktree cleanup pathspec plan against current drift."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from report_worktree_drift import (
    CATEGORIES,
    CATEGORY_PATHSPEC_FILENAMES,
    classify_status,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Non-destructively verify that report_worktree_drift.py "
            "--write-pathspec-dir output still matches current worktree drift."
        )
    )
    parser.add_argument(
        "--pathspec-dir",
        type=Path,
        required=True,
        help="Directory containing category pathspec files to verify.",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        help="Read git status --porcelain=v1 output from a fixture file.",
    )
    parser.add_argument(
        "--allow-source",
        action="store_true",
        help="Allow matched source_changes instead of failing on them.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the text summary.",
    )
    return parser.parse_args(argv)


def _split_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _git_status_porcelain() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return _split_lines(proc.stdout)


def _read_status_file(path: Path) -> list[str]:
    return _split_lines(path.read_text(encoding="utf-8"))


def _read_plan(pathspec_dir: Path) -> tuple[dict[str, list[str]], list[str]]:
    plan: dict[str, list[str]] = {}
    missing_files: list[str] = []
    for category in CATEGORIES:
        filename = CATEGORY_PATHSPEC_FILENAMES[category]
        path = pathspec_dir / filename
        if not path.is_file():
            missing_files.append(filename)
            plan[category] = []
            continue
        plan[category] = _split_lines(path.read_text(encoding="utf-8"))
    return plan, missing_files


def _category_mismatches(
    plan: dict[str, list[str]],
    current: dict[str, list[str]],
) -> dict[str, dict[str, object]]:
    mismatches: dict[str, dict[str, object]] = {}
    for category in CATEGORIES:
        planned_paths = plan[category]
        current_paths = current[category]
        if planned_paths == current_paths:
            continue

        details: dict[str, object] = {
            "missing_from_plan": [
                path for path in current_paths if path not in planned_paths
            ],
            "stale_in_plan": [
                path for path in planned_paths if path not in current_paths
            ],
        }
        if not details["missing_from_plan"] and not details["stale_in_plan"]:
            details["order_mismatch"] = True
        mismatches[category] = details
    return mismatches


def _counts(report: dict[str, list[str]]) -> dict[str, int]:
    return {category: len(report[category]) for category in CATEGORIES}


def _blocking_reasons(
    current: dict[str, list[str]],
    *,
    allow_source: bool,
) -> list[str]:
    reasons: list[str] = []
    if current["source_changes"] and not allow_source:
        reasons.append("source_changes")
    if current["other_changes"]:
        reasons.append("other_changes")
    return reasons


def _build_result(
    *,
    plan: dict[str, list[str]],
    current: dict[str, list[str]],
    missing_files: list[str],
    allow_source: bool,
) -> dict[str, object]:
    mismatches = _category_mismatches(plan, current)
    blocking_reasons = _blocking_reasons(current, allow_source=allow_source)
    return {
        "ok": not missing_files and not mismatches and not blocking_reasons,
        "missing_category_files": missing_files,
        "mismatches": mismatches,
        "blocking_reasons": blocking_reasons,
        "requires_separate_approval": (
            ["asset_deletions"] if current["asset_deletions"] else []
        ),
        "counts": _counts(current),
        "plan": plan,
        "current": current,
    }


def _print_text_result(result: dict[str, object], *, allow_source: bool) -> None:
    ok = result["ok"]
    print(
        "cleanup plan matches current worktree drift"
        if ok
        else "cleanup plan verification failed"
    )

    for filename in result["missing_category_files"]:
        print(f"missing category file: {filename}")

    mismatches = result["mismatches"]
    for category in CATEGORIES:
        if category not in mismatches:
            continue
        details = mismatches[category]
        print(f"mismatched category: {category}")
        for path in details["missing_from_plan"]:
            print(f"  missing from plan: {path}")
        for path in details["stale_in_plan"]:
            print(f"  stale in plan: {path}")
        if details.get("order_mismatch"):
            print("  order differs from current worktree report")

    counts = result["counts"]
    for category in CATEGORIES:
        suffix = ""
        if category == "asset_deletions" and counts[category]:
            suffix = " (requires separate approval)"
        elif category == "source_changes" and counts[category]:
            suffix = (
                " (allowed by --allow-source)"
                if allow_source
                else " (blocked; rerun with --allow-source to permit)"
            )
        elif category == "other_changes" and counts[category]:
            suffix = " (blocked)"
        print(f"{category}: {counts[category]}{suffix}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    lines = _read_status_file(args.status_file) if args.status_file else _git_status_porcelain()
    current = classify_status(lines)
    plan, missing_files = _read_plan(args.pathspec_dir)
    result = _build_result(
        plan=plan,
        current=current,
        missing_files=missing_files,
        allow_source=args.allow_source,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_text_result(result, allow_source=args.allow_source)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
