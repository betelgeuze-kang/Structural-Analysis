"""Exact committed-source provenance helpers for additive G1 receipts."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any, Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def build_provenance(
    root: Path,
    paths: Iterable[Path],
    *,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    normalized = tuple(sorted({Path(path).as_posix() for path in paths}))
    return {
        "source_commit_sha": source_commit_sha or git_head(root),
        "input_checksums": {path: sha256_file(root / path) for path in normalized},
    }


def validate_provenance(
    payload: dict[str, Any],
    *,
    root: Path,
    expected_paths: Iterable[Path],
    require_commit_bound: bool,
) -> None:
    expected_names = tuple(sorted({Path(path).as_posix() for path in expected_paths}))
    checksums = payload.get("input_checksums")
    if not isinstance(checksums, dict) or tuple(sorted(checksums)) != expected_names:
        raise ValueError("g1_receipt_provenance_path_set_mismatch")
    current = {name: sha256_file(root / name) for name in expected_names}
    if checksums != current:
        raise ValueError("g1_receipt_provenance_current_bytes_mismatch")
    commit = payload.get("source_commit_sha")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("g1_receipt_provenance_commit_invalid")
    if not require_commit_bound:
        return
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise ValueError("g1_receipt_provenance_commit_not_ancestor")
    for name in expected_names:
        result = subprocess.run(
            ["git", "show", f"{commit}:{name}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ValueError(f"g1_receipt_provenance_path_not_committed:{name}")
        observed = "sha256:" + hashlib.sha256(result.stdout).hexdigest()
        if observed != checksums[name]:
            raise ValueError(f"g1_receipt_provenance_committed_bytes_mismatch:{name}")
