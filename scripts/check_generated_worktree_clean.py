#!/usr/bin/env python3
"""Fail when tracked generated artifacts are dirty in the worktree."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


GENERATED_PREFIXES = (
    "implementation/phase1/open_data/",
    "implementation/phase1/stress/",
)
GENERATED_FILES = {
    "implementation/phase1/panel_zone_solver_verified_export_bundle.json",
    "implementation/phase1/panel_zone_solver_verified_inbox_status.json",
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Guard against tracked generated artifact drift reported by "
            "`git diff --name-only`."
        )
    )
    parser.add_argument(
        "--diff-name-only-file",
        type=Path,
        help="Read newline-delimited paths from a git diff --name-only fixture.",
    )
    parser.add_argument(
        "--show-ok",
        action="store_true",
        help="Print an OK message when no generated artifact drift is detected.",
    )
    return parser.parse_args(argv)


def _git_diff_name_only() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return _split_name_only(proc.stdout)


def _read_name_only_file(path: Path) -> list[str]:
    return _split_name_only(path.read_text(encoding="utf-8"))


def _split_name_only(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_generated_artifact(path: str) -> bool:
    return path in GENERATED_FILES or any(
        path.startswith(prefix) for prefix in GENERATED_PREFIXES
    )


def _dirty_generated_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if _is_generated_artifact(path)]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    paths = (
        _read_name_only_file(args.diff_name_only_file)
        if args.diff_name_only_file
        else _git_diff_name_only()
    )
    dirty_generated = _dirty_generated_paths(paths)

    if dirty_generated:
        print(
            "ERROR: tracked generated artifact drift detected:",
            file=sys.stderr,
        )
        for path in dirty_generated:
            print(f"  - {path}", file=sys.stderr)
        return 1

    if args.show_ok:
        print("OK: no tracked generated artifact drift detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
