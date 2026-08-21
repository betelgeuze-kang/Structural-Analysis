#!/usr/bin/env python3
"""Run one deterministic, file-isolated shard of the repository test suite."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def discover_test_files(repo_root: Path, test_root: Path) -> tuple[str, ...]:
    """Return repository-relative test module paths in stable lexical order."""
    resolved_repo = repo_root.resolve()
    resolved_tests = (
        test_root.resolve()
        if test_root.is_absolute()
        else (resolved_repo / test_root).resolve()
    )
    try:
        resolved_tests.relative_to(resolved_repo)
    except ValueError as exc:
        raise ValueError("test root must be inside the repository root") from exc
    if not resolved_tests.is_dir():
        raise ValueError(f"test root is not a directory: {resolved_tests}")

    files: list[str] = []
    for path in resolved_tests.rglob("test_*.py"):
        if not path.is_file() or path.is_symlink():
            continue
        files.append(path.resolve().relative_to(resolved_repo).as_posix())
    if not files:
        raise ValueError(f"no test modules found below {resolved_tests}")
    return tuple(sorted(files))


def shard_index_for_path(relative_path: str, shard_count: int) -> int:
    """Assign a module to a stable shard without relying on Python hash state."""
    if shard_count < 1:
        raise ValueError("shard count must be positive")
    digest = hashlib.sha256(relative_path.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % shard_count


def select_shard(
    test_files: Sequence[str],
    *,
    shard_index: int,
    shard_count: int,
) -> tuple[str, ...]:
    """Select exactly one deterministic shard from a complete module list."""
    if shard_count < 1:
        raise ValueError("shard count must be positive")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard index must be in [0, shard count)")
    selected = tuple(
        path
        for path in test_files
        if shard_index_for_path(path, shard_count) == shard_index
    )
    if not selected:
        raise ValueError(f"shard {shard_index}/{shard_count} contains no test modules")
    return selected


def manifest_sha256(paths: Sequence[str]) -> str:
    """Hash an ordered path manifest with an unambiguous trailing newline."""
    payload = "".join(f"{path}\n" for path in paths).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--test-root", type=Path, default=Path("tests"))
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="print the selected module paths without invoking pytest",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="pytest arguments following an optional -- separator",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        files = discover_test_files(args.repo_root, args.test_root)
        selected = select_shard(
            files,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
    except ValueError as exc:
        print(f"pytest shard configuration error: {exc}", file=sys.stderr)
        return 2

    print(
        "pytest_shard_v1 "
        f"index={args.shard_index} "
        f"count={args.shard_count} "
        f"module_count={len(selected)} "
        f"suite_manifest_sha256={manifest_sha256(files)} "
        f"shard_manifest_sha256={manifest_sha256(selected)}",
        flush=True,
    )
    if args.list_only:
        print("\n".join(selected))
        return 0

    pytest_args = list(args.pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args.pop(0)
    command = [sys.executable, "-m", "pytest", *pytest_args, *selected]
    return subprocess.run(command, cwd=args.repo_root.resolve(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
