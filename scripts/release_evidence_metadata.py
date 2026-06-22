#!/usr/bin/env python3
"""Small helpers for release-evidence provenance metadata."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head(repo_root: Path = Path(".")) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def engine_version(repo_root: Path = Path(".")) -> str:
    package_json = repo_root / "package.json"
    if package_json.exists():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            name = str(payload.get("name", "structural-analysis-workbench") or "structural-analysis-workbench")
            version = str(payload.get("version", "unversioned") or "unversioned")
            return f"{name}@{version}"
    return "structural-analysis-workbench@unversioned"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _checksum_ignored(path: Path) -> bool:
    ignored_dirs = {"__pycache__", ".pytest_cache"}
    return bool(ignored_dirs.intersection(path.parts)) or path.suffix in {".pyc", ".pyo"}


def directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(
        item for item in path.rglob("*") if item.is_file() and not _checksum_ignored(item)
    ):
        relative = child.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(child).encode("utf-8"))
        digest.update(b"\0")
    return f"dir-sha256:{digest.hexdigest()}"


def input_checksums(paths: Iterable[Path], *, repo_root: Path = Path(".")) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        key = str(raw_path)
        if not path.exists():
            checksums[key] = "missing"
            continue
        checksums[key] = directory_sha256(path) if path.is_dir() else file_sha256(path)
    return dict(sorted(checksums.items()))


def release_evidence_metadata(
    *,
    input_paths: Iterable[Path],
    reused_evidence: bool,
    reuse_policy: str,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    return {
        "generated_at": now_utc_iso(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "input_checksums": input_checksums(input_paths, repo_root=repo_root),
        "reused_evidence": bool(reused_evidence),
        "reuse_policy": reuse_policy,
    }
