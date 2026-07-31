#!/usr/bin/env python3
"""Verify that Git LFS attributes and committed pointer blobs agree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POINTER = re.compile(
    rb"\Aversion https://git-lfs.github.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\nsize ([1-9][0-9]*|0)\n\Z"
)


def _git(repo_root: Path, *args: str, input_text: str | None = None) -> bytes:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo_root,
        input=None if input_text is None else input_text.encode(),
    )


def build_report(*, repo_root: Path = ROOT, revision: str = "HEAD") -> dict[str, Any]:
    paths = _git(repo_root, "ls-tree", "-r", "--name-only", "-z", revision)
    tracked = [value.decode() for value in paths.split(b"\0") if value]
    candidates = [path for path in tracked if path.endswith(".npz")]
    violations: list[dict[str, str]] = []
    lfs_pointer_count = 0
    direct_blob_count = 0

    for path in candidates:
        attribute = _git(repo_root, "check-attr", "filter", "--", path).decode()
        uses_lfs = attribute.rstrip().endswith(": lfs")
        blob = _git(repo_root, "cat-file", "blob", f"{revision}:{path}")
        match = POINTER.fullmatch(blob)
        is_pointer = match is not None
        if is_pointer:
            lfs_pointer_count += 1
        else:
            direct_blob_count += 1
        if uses_lfs and not is_pointer:
            violations.append({"path": path, "reason": "lfs_attribute_without_pointer"})
        elif is_pointer and not uses_lfs:
            violations.append({"path": path, "reason": "pointer_without_lfs_attribute"})

    return {
        "schema_version": "git-lfs-integrity-report.v1",
        "revision": revision,
        "contract_pass": not violations,
        "lfs_pointer_count": lfs_pointer_count,
        "direct_blob_count": direct_blob_count,
        "pointer_violation_count": len(violations),
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = build_report(repo_root=args.repo_root.resolve(), revision=args.revision)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if args.json or args.out is None:
        print(text, end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
