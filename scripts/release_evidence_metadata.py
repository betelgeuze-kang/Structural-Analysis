#!/usr/bin/env python3
"""Small helpers for release-evidence provenance metadata."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

PRODUCT_IDENTITY_MANIFEST = Path("artifacts/manifests/product_identity.json")
PRODUCT_SOURCE_REVISION_PATHS = (
    ".github/workflows",
    "benchmarks",
    "canonical",
    "native",
    "pyproject.toml",
    "scripts",
    "src",
)


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


def product_source_revision(repo_root: Path = Path(".")) -> str:
    """Return the newest commit affecting executable or contract source.

    Generated-evidence-only commits deliberately do not invalidate a package
    whose complete source/control byte closure is unchanged. This avoids an
    impossible self-referential requirement for a committed package manifest
    to embed the hash of the commit that contains that manifest.
    """

    try:
        value = subprocess.check_output(
            [
                "git",
                "log",
                "-1",
                "--format=%H",
                "HEAD",
                "--",
                *PRODUCT_SOURCE_REVISION_PATHS,
            ],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else ""


def engine_version(repo_root: Path = Path(".")) -> str:
    identity_manifest = repo_root / PRODUCT_IDENTITY_MANIFEST
    if identity_manifest.exists():
        try:
            identity = json.loads(identity_manifest.read_text(encoding="utf-8"))
        except Exception:
            identity = {}
        if isinstance(identity, dict):
            name = str(identity.get("distribution_name", "")).strip()
            version = str(identity.get("version", "")).strip()
            if name and version:
                return f"{name}@{version}"

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
    return "structural-analysis@unversioned"


CANONICAL_REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ENGINE_VERSION = engine_version(CANONICAL_REPO_ROOT)


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


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def resolve_input_path(path: Path, *, repo_root: Path = Path(".")) -> Path:
    """Resolve a declared input against its repository, never the caller CWD."""

    root = repo_root.resolve()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _resolved_input(
    path: Path, *, repo_root: Path
) -> tuple[str | None, Path]:
    """Resolve an input exactly once, relative to ``repo_root`` when needed.

    ``Path.resolve()`` on a relative path uses the process working directory.
    Evidence builders can be invoked from any directory, so resolving a
    repository-relative declaration before joining it to ``repo_root`` would
    make provenance depend on the caller's current directory.  Returning the
    resolved path even for external inputs also prevents callers from resolving
    the same declaration a second, potentially different, way.
    """

    root = repo_root.resolve()
    resolved = resolve_input_path(path, repo_root=root)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        relative = None
    return relative, resolved


def _git_object(repo_root: Path, source_commit_sha: str, relative_path: str) -> bytes | None:
    try:
        return subprocess.check_output(
            ["git", "show", f"{source_commit_sha}:{relative_path}"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


def _git_object_type(
    repo_root: Path, source_commit_sha: str, relative_path: str
) -> str:
    try:
        return subprocess.check_output(
            ["git", "cat-file", "-t", f"{source_commit_sha}:{relative_path}"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _git_directory_sha256(
    repo_root: Path, source_commit_sha: str, relative_path: str
) -> tuple[str | None, str]:
    try:
        listing = subprocess.check_output(
            ["git", "ls-tree", "-r", "-z", source_commit_sha, "--", relative_path],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None, f"input_source_tree_unreadable:{relative_path}"
    rows: list[tuple[str, bytes]] = []
    prefix = f"{relative_path.rstrip('/')}/"
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_name = entry.split(b"\t", 1)
            mode, object_type, object_id_raw = metadata.split()
        except ValueError:
            return None, f"input_source_tree_entry_malformed:{relative_path}"
        object_id = object_id_raw.decode("ascii")
        name = raw_name.decode("utf-8", errors="surrogateescape")
        child = Path(name)
        if _checksum_ignored(child):
            continue
        if mode == b"160000" or object_type == b"commit":
            return None, f"input_gitlink_not_commit_bound:{name}"
        if object_type != b"blob":
            return None, f"input_source_tree_entry_not_blob:{name}"
        try:
            payload = subprocess.check_output(
                ["git", "cat-file", "blob", object_id],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return None, f"input_source_blob_unreadable:{name}"
        nested_name = name[len(prefix) :] if name.startswith(prefix) else name
        rows.append((nested_name, payload))
    digest = hashlib.sha256()
    for nested_name, payload in sorted(rows):
        digest.update(nested_name.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(_sha256_bytes(payload).encode("utf-8"))
        digest.update(b"\0")
    return f"dir-sha256:{digest.hexdigest()}", ""


def _git_path_checksum(
    repo_root: Path, source_commit_sha: str, relative_path: str
) -> tuple[str, bool, str]:
    object_type = _git_object_type(repo_root, source_commit_sha, relative_path)
    if object_type == "tree":
        checksum, blocker = _git_directory_sha256(
            repo_root, source_commit_sha, relative_path
        )
        return (checksum or "missing"), True, blocker
    if object_type == "blob":
        payload = _git_object(repo_root, source_commit_sha, relative_path)
        if payload is not None:
            return _sha256_bytes(payload), True, ""
        return "missing", True, f"input_source_blob_unreadable:{relative_path}"
    if object_type:
        return (
            "missing",
            True,
            f"input_source_object_type_unsupported:{relative_path}:{object_type}",
        )
    return "missing", False, ""


def commit_bound_input_metadata(
    paths: Iterable[Path],
    *,
    repo_root: Path = Path("."),
    source_commit_sha: str | None = None,
    additional_blockers: Iterable[str] = (),
) -> dict[str, Any]:
    """Bind input hashes to one commit and disclose workspace divergence.

    Repository-local input checksums are computed from ``source_commit_sha``
    rather than from mutable workspace bytes.  A tracked input that differs in
    the workspace, or an untracked workspace input that is absent from the
    declared commit, makes the provenance contract fail closed.  Missing inputs
    that are absent from both the commit and workspace remain a reproducible
    ``missing`` observation.

    Absolute inputs outside ``repo_root`` cannot be reproduced from a git
    commit.  They retain their workspace checksum for diagnostic callers but
    are explicitly marked unbound and fail the provenance contract.
    """

    root = repo_root.resolve()
    source_sha = source_commit_sha or git_head(root)
    source_resolved = False
    if source_sha:
        try:
            resolved_sha = subprocess.check_output(
                ["git", "rev-parse", "--verify", f"{source_sha}^{{commit}}"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            source_resolved = bool(resolved_sha)
            source_sha = resolved_sha or source_sha
        except Exception:
            source_resolved = False

    checksums: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    blockers = [str(item) for item in additional_blockers if str(item)]
    for raw_path in paths:
        path = Path(raw_path)
        relative, resolved = _resolved_input(path, repo_root=root)
        if relative is None:
            key = path.as_posix()
            workspace_checksum = (
                directory_sha256(resolved)
                if resolved.is_dir()
                else file_sha256(resolved)
                if resolved.is_file()
                else "missing"
            )
            checksums[key] = workspace_checksum
            blocker = f"external_input_not_commit_bound:{key}"
            blockers.append(blocker)
            rows.append(
                {
                    "path": key,
                    "source_state": "external_unbound",
                    "source_checksum": workspace_checksum,
                    "workspace_checksum": workspace_checksum,
                    "workspace_matches_source": False,
                    "blocker": blocker,
                }
            )
            continue

        key = relative
        source_checksum, source_present, source_blocker = (
            _git_path_checksum(root, source_sha, key)
            if source_resolved
            else ("missing", False, "")
        )
        workspace_checksum = (
            directory_sha256(resolved)
            if resolved.is_dir()
            else file_sha256(resolved)
            if resolved.is_file()
            else "missing"
        )
        checksums[key] = source_checksum
        workspace_matches_source = bool(
            source_resolved
            and not source_blocker
            and workspace_checksum == source_checksum
        )
        blocker = ""
        if not source_resolved:
            blocker = "source_commit_unresolved"
        elif source_blocker:
            blocker = source_blocker
        elif not source_present and workspace_checksum != "missing":
            blocker = f"input_untracked_at_source_commit:{key}"
        elif source_present and workspace_checksum == "missing":
            blocker = f"input_missing_from_workspace:{key}"
        elif not workspace_matches_source:
            blocker = f"input_differs_from_source_commit:{key}"
        if blocker:
            blockers.append(blocker)
        rows.append(
            {
                "path": key,
                "source_state": "tracked" if source_present else "missing",
                "source_checksum": source_checksum,
                "workspace_checksum": workspace_checksum,
                "workspace_matches_source": workspace_matches_source,
                "blocker": blocker,
            }
        )

    blockers = list(dict.fromkeys(blockers))
    return {
        "source_commit_sha": source_sha,
        "input_checksums": dict(sorted(checksums.items())),
        "source_input_provenance": {
            "schema_version": "source-input-provenance.v1",
            "contract_pass": not blockers,
            "reason_code": "PASS" if not blockers else "ERR_SOURCE_INPUT_NOT_REPRODUCIBLE",
            "source_commit_resolved": source_resolved,
            "input_count": len(rows),
            "workspace_match_count": sum(
                1 for row in rows if row["workspace_matches_source"] is True
            ),
            "blocker_count": len(blockers),
            "blockers": blockers,
            "inputs": rows,
            "claim_boundary": (
                "input_checksums records bytes from source_commit_sha for repository-local inputs. "
                "Dirty, untracked, missing-workspace, external, or cyclic inputs fail this provenance "
                "contract and cannot support a release-ready claim."
            ),
        },
    }


def commit_bound_release_evidence_metadata(
    *,
    input_paths: Iterable[Path],
    reused_evidence: bool,
    reuse_policy: str,
    repo_root: Path = Path("."),
    source_commit_sha: str | None = None,
    additional_blockers: Iterable[str] = (),
) -> dict[str, Any]:
    metadata = commit_bound_input_metadata(
        input_paths,
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        additional_blockers=additional_blockers,
    )
    return {
        "generated_at": now_utc_iso(),
        **metadata,
        "engine_version": engine_version(repo_root),
        "reused_evidence": bool(reused_evidence),
        "reuse_policy": reuse_policy,
    }


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
