#!/usr/bin/env python3
"""Fail CI when generated artifacts or unsafe files are tracked in Git."""

from __future__ import annotations

import argparse
import json
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
STRICT_SOURCE_BOUNDARY_PREFIXES = (
    "implementation/phase1/stress/",
    "implementation/phase1/workspace/",
    "implementation/phase1/output/",
    "implementation/phase1/rust_hip_md3bead_hook/target/",
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


def _path_size(path: str) -> int | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return file_path.stat().st_size


def _git_blob_size(path: str) -> int | None:
    result = subprocess.run(
        ["git", "cat-file", "-s", f":{path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


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


def check_tracked_files(files: list[str], *, strict_source_boundary: bool = False) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path in ALLOWED_PATHS:
            continue
        path_parts = set(Path(path).parts)
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            errors.append(f"generated path is tracked: {path}")
        if strict_source_boundary and any(path.startswith(prefix) for prefix in STRICT_SOURCE_BOUNDARY_PREFIXES):
            errors.append(f"source-boundary candidate is tracked: {path}")
        if path_parts & FORBIDDEN_PATH_PARTS:
            errors.append(f"cache path is tracked: {path}")
        if path.endswith(FORBIDDEN_SUFFIXES):
            errors.append(f"python cache artifact is tracked: {path}")
        if _is_private_pem(path):
            errors.append(f"private signing key is tracked: {path}")

        worktree_size = _path_size(path)
        blob_size = _git_blob_size(path)
        github_size = blob_size if blob_size is not None else worktree_size
        if github_size is not None and github_size > MAX_GIT_BLOB_BYTES:
            errors.append(f"file exceeds GitHub hard limit ({github_size} bytes): {path}")
        if (
            worktree_size is not None
            and worktree_size > MAX_RAW_DATA_BYTES
            and _is_raw_data_path(path)
            and path.endswith(RAW_DATA_SUFFIXES)
        ):
            errors.append(f"large raw data artifact must be externalized ({worktree_size} bytes): {path}")
    return errors


def build_inventory(files: list[str], *, warn_large_files_mb: float | None = None) -> dict[str, object]:
    risky_prefix_counts = {
        prefix: sum(1 for path in files if path.startswith(prefix))
        for prefix in STRICT_SOURCE_BOUNDARY_PREFIXES
    }
    inventory: dict[str, object] = {
        "total_files": len(files),
        "risky_prefix_counts": {
            prefix: count
            for prefix, count in risky_prefix_counts.items()
            if count
        },
        "large_files": [],
    }
    if warn_large_files_mb is None:
        return inventory

    threshold_bytes = int(warn_large_files_mb * 1024 * 1024)
    large_files: list[dict[str, int | str]] = []
    for path in files:
        size = _path_size(path)
        if size is not None and size > threshold_bytes:
            large_files.append({"path": path, "size_bytes": size})
    inventory["large_files"] = sorted(large_files, key=lambda item: (-int(item["size_bytes"]), str(item["path"])))
    return inventory


def _print_inventory(inventory: dict[str, object]) -> None:
    risky_prefix_counts = inventory["risky_prefix_counts"]
    large_files = inventory["large_files"]
    if risky_prefix_counts:
        print("Tracked risky prefix counts:")
        for prefix, count in risky_prefix_counts.items():
            print(f"- {prefix}: {count}")
    if large_files:
        print("Tracked files above advisory threshold:")
        for item in large_files:
            print(f"- {item['size_bytes']} bytes: {item['path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-ok", action="store_true", help="print a short success line")
    parser.add_argument(
        "--strict-source-boundary",
        action="store_true",
        help="fail on tracked generated/workspace/build-output source-boundary candidates",
    )
    parser.add_argument("--json", action="store_true", help="print deterministic JSON diagnostics")
    parser.add_argument(
        "--warn-large-files-mb",
        type=float,
        help="include tracked files above this advisory size threshold in inventory output",
    )
    args = parser.parse_args(argv)

    files = _git_files()
    errors = check_tracked_files(files, strict_source_boundary=args.strict_source_boundary)
    inventory = build_inventory(files, warn_large_files_mb=args.warn_large_files_mb)
    if args.json:
        print(json.dumps({"errors": errors, "inventory": inventory, "ok": not errors}, indent=2, sort_keys=True))
        return 1 if errors else 0
    if args.warn_large_files_mb is not None:
        _print_inventory(inventory)
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
