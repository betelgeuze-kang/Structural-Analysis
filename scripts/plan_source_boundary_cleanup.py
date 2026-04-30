#!/usr/bin/env python3
"""Plan source-boundary cleanup candidates without mutating Git state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


GENERATED_BOUNDARY_PREFIXES = (
    "implementation/phase1/stress/",
    "implementation/phase1/workspace/",
    "implementation/phase1/output/",
)
BUILD_OUTPUT_PREFIXES = (
    "implementation/phase1/rust_hip_md3bead_hook/target/",
    "node_modules/",
    "dist/",
)
BUILD_OUTPUT_PARTS = {
    "__pycache__",
}
BUILD_OUTPUT_SUFFIXES = (
    ".pyc",
)
BUCKETS = (
    "build_output",
    "generated_boundary",
    "large_file",
    "private_secret",
)
DEFAULT_LARGE_FILE_THRESHOLD_MIB = 25.0
BYTES_PER_MIB = 1024 * 1024


def _git_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [item for item in raw.decode("utf-8", "replace").split("\0") if item]


def _read_tracked_files(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _path_size(path: str) -> int | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return file_path.stat().st_size


def _is_private_pem(path: str) -> bool:
    return path.endswith(".pem") and not path.endswith(".pub.pem")


def _is_build_output(path: str) -> bool:
    return (
        any(path.startswith(prefix) for prefix in BUILD_OUTPUT_PREFIXES)
        or bool(set(Path(path).parts) & BUILD_OUTPUT_PARTS)
        or path.endswith(BUILD_OUTPUT_SUFFIXES)
    )


def classify_path(path: str, *, size_bytes: int | None, large_file_threshold_bytes: int) -> list[str]:
    buckets: list[str] = []
    if _is_build_output(path):
        buckets.append("build_output")
    if any(path.startswith(prefix) for prefix in GENERATED_BOUNDARY_PREFIXES):
        buckets.append("generated_boundary")
    if size_bytes is not None and size_bytes >= large_file_threshold_bytes:
        buckets.append("large_file")
    if _is_private_pem(path):
        buckets.append("private_secret")
    return buckets


def recommended_action(buckets: list[str]) -> str:
    if "private_secret" in buckets:
        return "manual_review"
    if "build_output" in buckets or "generated_boundary" in buckets:
        return "remove_from_git"
    if "large_file" in buckets:
        return "externalize_or_allowlist"
    return "manual_review"


def build_plan(files: list[str], *, large_file_threshold_mib: float = DEFAULT_LARGE_FILE_THRESHOLD_MIB) -> dict[str, object]:
    large_file_threshold_bytes = int(large_file_threshold_mib * BYTES_PER_MIB)
    records: list[dict[str, int | str | list[str] | None]] = []
    counts_by_bucket = dict.fromkeys(BUCKETS, 0)
    total_candidate_bytes = 0

    for path in sorted(files):
        size_bytes = _path_size(path)
        buckets = classify_path(
            path,
            size_bytes=size_bytes,
            large_file_threshold_bytes=large_file_threshold_bytes,
        )
        if not buckets:
            continue
        for bucket in buckets:
            counts_by_bucket[bucket] += 1
        if size_bytes is not None:
            total_candidate_bytes += size_bytes
        records.append(
            {
                "path": path,
                "bytes": size_bytes,
                "buckets": buckets,
                "recommended_action": recommended_action(buckets),
            }
        )

    return {
        "counts_by_bucket": {
            bucket: count
            for bucket, count in counts_by_bucket.items()
            if count
        },
        "large_file_threshold_bytes": large_file_threshold_bytes,
        "records": records,
        "total_candidate_bytes": total_candidate_bytes,
        "total_candidate_files": len(records),
        "total_tracked_files": len(files),
    }


def _write_pathspec(path: Path, records: list[dict[str, object]]) -> None:
    paths = [
        str(record["path"])
        for record in records
        if record["recommended_action"] == "remove_from_git"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{item}\n" for item in paths), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print JSON diagnostics (default)")
    parser.add_argument(
        "--tracked-files",
        type=Path,
        help="read newline-separated tracked paths from a fixture instead of running git ls-files",
    )
    parser.add_argument(
        "--large-file-threshold-mib",
        type=float,
        default=DEFAULT_LARGE_FILE_THRESHOLD_MIB,
        help="classify tracked files at or above this size as large_file",
    )
    parser.add_argument(
        "--write-pathspec",
        type=Path,
        help="write remove_from_git paths for git rm --cached --pathspec-from-file",
    )
    args = parser.parse_args(argv)

    files = _read_tracked_files(args.tracked_files) if args.tracked_files else _git_files()
    plan = build_plan(files, large_file_threshold_mib=args.large_file_threshold_mib)
    if args.write_pathspec:
        _write_pathspec(args.write_pathspec, plan["records"])
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
