#!/usr/bin/env python3
"""Fail CI when generated artifacts or unsafe files are tracked in Git."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


FORBIDDEN_PREFIXES = (
    "implementation/phase1/release/",
    "implementation/phase1/experiments/",
    "tmp/",
    "node_modules/",
    "dist/",
)
FORBIDDEN_PATH_PARTS = {
    ".cache",
    "cache",
    "__pycache__",
}
ALLOWED_PATHS = {
    "implementation/phase1/release_artifacts_manifest.json",
}
FORBIDDEN_SUFFIXES = (
    ".pyc",
    ".pyo",
)
RAW_DATA_SUFFIXES = (
    ".zip",
    ".csv",
    ".jsonl",
)
MAX_GIT_BLOB_BYTES = 100 * 1024 * 1024
MAX_RAW_DATA_BYTES = 50 * 1024 * 1024


def _git_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [item for item in raw.decode("utf-8", "replace").split("\0") if item]


def _is_private_pem(path: str) -> bool:
    return path.endswith(".pem") and not path.endswith(".pub.pem")


def _is_raw_data_path(path: str) -> bool:
    return (
        path.startswith("implementation/phase1/open_data/")
        or path.startswith("implementation/phase1/workspace/")
        or path.startswith("implementation/phase1/spatiotemporal_data/")
    )


def check_tracked_files(files: list[str]) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path in ALLOWED_PATHS:
            continue
        path_parts = set(Path(path).parts)
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            errors.append(f"generated path is tracked: {path}")
        if path_parts & FORBIDDEN_PATH_PARTS:
            errors.append(f"cache path is tracked: {path}")
        if path.endswith(FORBIDDEN_SUFFIXES):
            errors.append(f"python cache artifact is tracked: {path}")
        if _is_private_pem(path):
            errors.append(f"private signing key is tracked: {path}")

        file_path = Path(path)
        if not file_path.is_file():
            continue
        size = file_path.stat().st_size
        if size > MAX_GIT_BLOB_BYTES:
            errors.append(f"file exceeds GitHub hard limit ({size} bytes): {path}")
        if size > MAX_RAW_DATA_BYTES and _is_raw_data_path(path) and path.endswith(RAW_DATA_SUFFIXES):
            errors.append(f"large raw data artifact must be externalized ({size} bytes): {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-ok", action="store_true", help="print a short success line")
    args = parser.parse_args()

    errors = check_tracked_files(_git_files())
    if errors:
        print("Repository hygiene check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.show_ok:
        print("Repository hygiene OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
