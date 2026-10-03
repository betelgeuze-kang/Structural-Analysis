#!/usr/bin/env python3
"""Verify complete canonical Git source while permitting named generated leaves."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Iterable
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
TRUSTED_GIT = Path("/usr/bin/git")
SHA = re.compile(r"[0-9a-f]{40}")
PRODUCER_GENERATED_MARKDOWN_FILES = tuple(
    "implementation/phase1/release_evidence/productization/" + name + ".md"
    for name in (
        "developer_preview_readiness",
        "developer_preview_rc_status",
        "release_evidence_freshness_report",
        "pm_release_gate_report",
        "pm_release_blocker_action_register",
        "pm_release_blocker_closure_board",
    )
)
CANONICAL_RECEIPT = (
    "artifacts/manifests/canonical_verification_environment.current.v1.json"
)


class TrackedSourceTreeError(ValueError):
    """A source checkout differs from its committed canonical content contract."""


def _require(condition: object, reason: str) -> None:
    if not condition:
        raise TrackedSourceTreeError(reason)


def _safe_path(value: str) -> str:
    path = PurePosixPath(value)
    _require(
        0 < len(value) <= 2048
        and "\\" not in value
        and ":" not in value
        and unicodedata.normalize("NFC", value) == value
        and not any(unicodedata.category(c) in {"Cc", "Cf"} for c in value)
        and not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", "..", ".git"} for part in path.parts),
        "tracked_source_path_unsafe",
    )
    name = path.name
    environment = (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
        or ".env." in name
    ) and name != ".env.example"
    credentials = name in {
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".git-credentials",
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
    } or any(part in {".ssh", ".aws", ".docker"} for part in path.parts)
    _require(not environment and not credentials, "tracked_source_protected_path")
    return value


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    _require(
        TRUSTED_GIT.is_file()
        and not TRUSTED_GIT.is_symlink()
        and TRUSTED_GIT.resolve() == TRUSTED_GIT,
        "tracked_source_trusted_git_unavailable",
    )
    result = subprocess.run(
        [
            str(TRUSTED_GIT),
            "-c",
            f"safe.directory={root}",
            "-c",
            "core.filemode=true",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.ignorestat=false",
            "-c",
            "core.trustctime=true",
            "-c",
            "core.checkstat=default",
            "-c",
            "core.attributesfile=" + os.devnull,
            "-c",
            "filter.lfs.clean=",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.required=false",
            *args,
        ],
        cwd=root,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        },
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, "tracked_source_git_failed:" + args[0])
    return result.stdout


def _quoted_paths(paths: Iterable[str]) -> bytes:
    quoted = ['"' + path.replace('"', '\\"') + '"' for path in paths]
    return ("\n".join(quoted) + "\n").encode("utf-8")


def _canonical_hashes(root: Path, paths: list[str]) -> list[str]:
    if not paths:
        return []
    hashes = (
        _git(
            root,
            "hash-object",
            "--stdin-paths",
            input_bytes=_quoted_paths(paths),
        )
        .decode("ascii", errors="strict")
        .splitlines()
    )
    _require(len(hashes) == len(paths), "tracked_source_hash_count_mismatch")
    return hashes


def _filters(root: Path, paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    expected = set(paths)
    rows = _rows(
        _git(
            root,
            "check-attr",
            "--cached",
            "-z",
            "filter",
            "--stdin",
            input_bytes=b"\0".join(path.encode("utf-8") for path in paths) + b"\0",
        )
    )
    _require(len(rows) == 3 * len(paths), "tracked_source_filter_inventory_invalid")
    result: dict[str, str] = {}
    for path, attribute, value in zip(rows[::3], rows[1::3], rows[2::3]):
        _require(
            path in expected and attribute == "filter",
            "tracked_source_filter_inventory_invalid",
        )
        _require(
            value in {"unspecified", "unset", "lfs"},
            "tracked_source_filter_unsupported:" + path,
        )
        result[path] = value
    _require(set(result) == expected, "tracked_source_filter_inventory_invalid")
    return result


def _matches_lfs_pointer(root: Path, path: str, source_blob: str) -> bool:
    size = _git(root, "cat-file", "-s", source_blob).strip()
    if not size.isdigit() or int(size) > 1024:
        return False
    raw = _git(root, "cat-file", "blob", source_blob)
    pointer = re.fullmatch(
        rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n",
        raw,
    )
    if pointer is None:
        return False
    expected_bytes = int(pointer[2])
    digest = hashlib.sha256()
    observed_bytes = 0
    with (root / path).open("rb") as handle:
        while chunk := handle.read(1_048_576):
            observed_bytes += len(chunk)
            if observed_bytes > expected_bytes:
                return False
            digest.update(chunk)
    return (
        observed_bytes == expected_bytes and digest.hexdigest().encode() == pointer[1]
    )


def _verify_attribute_ancestry(root: Path, source: dict[str, tuple[str, str]]) -> None:
    """Do not let uncommitted attribute files change canonical source hashing."""
    candidates: set[str] = {".gitattributes"}
    for path in source:
        for parent in PurePosixPath(path).parents:
            candidates.add((parent / ".gitattributes").as_posix())
    info_path = Path(
        _git(root, "rev-parse", "--git-path", "info/attributes").decode().strip()
    )
    if not info_path.is_absolute():
        info_path = root / info_path
    try:
        os.lstat(info_path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise TrackedSourceTreeError(
            "tracked_source_attributes_inventory_failed"
        ) from exc
    else:
        raise TrackedSourceTreeError("tracked_source_git_info_attributes_forbidden")
    for path in sorted(candidates):
        if path in source:
            continue
        try:
            os.lstat(root / path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise TrackedSourceTreeError(
                "tracked_source_attributes_inventory_failed:" + path
            ) from exc
        raise TrackedSourceTreeError("tracked_source_uncommitted_attributes:" + path)


def _rows(raw: bytes) -> list[str]:
    try:
        return [row.decode("utf-8", errors="strict") for row in raw.split(b"\0") if row]
    except UnicodeError as exc:
        raise TrackedSourceTreeError("tracked_source_path_encoding_invalid") from exc


def _tree(root: Path, source_sha: str) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for row in _rows(_git(root, "ls-tree", "-rz", source_sha)):
        header, path = row.split("\t", 1)
        mode, kind, blob = header.split()
        _safe_path(path)
        _require(
            mode in {"100644", "100755"} and kind == "blob" and SHA.fullmatch(blob),
            "tracked_source_tree_entry_unsupported:" + path,
        )
        _require(path not in result, "tracked_source_tree_duplicate")
        result[path] = (mode, blob)
    _require(result, "tracked_source_tree_empty")
    return result


def _index(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for row in _rows(_git(root, "ls-files", "--stage", "-z")):
        header, path = row.split("\t", 1)
        mode, blob, stage = header.split()
        _safe_path(path)
        _require(stage == "0" and path not in result, "tracked_source_index_unmerged")
        result[path] = (mode, blob)
    for row in _rows(_git(root, "ls-files", "-v", "-z")):
        _safe_path(row[2:])
        _require(row[:2] == "H ", "tracked_source_index_flags:" + row[2:])
    return result


def _regular_mode(root: Path, path: str, expected_mode: str | None) -> None:
    current = root
    try:
        for part in PurePosixPath(path).parts[:-1]:
            current /= part
            metadata = os.lstat(current)
            _require(
                stat.S_ISDIR(metadata.st_mode), "tracked_source_parent_unsafe:" + path
            )
        metadata = os.lstat(root / path)
    except OSError as exc:
        raise TrackedSourceTreeError("tracked_source_file_missing:" + path) from exc
    _require(stat.S_ISREG(metadata.st_mode), "tracked_source_file_unsafe:" + path)
    if expected_mode is not None:
        executable = bool(metadata.st_mode & stat.S_IXUSR)
        _require(
            executable == (expected_mode == "100755"),
            "tracked_source_mode_mismatch:" + path,
        )


def source_profile_paths(profile: str) -> tuple[frozenset[str], frozenset[str]]:
    """Use exact producer and consumer paths; never accept a directory prefix."""
    if profile == "pristine":
        return frozenset(), frozenset()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import build_post_main_evidence_overlay as overlay

    if profile == "producer":
        return frozenset(
            (
                *overlay.RELEASE_FILES,
                *(p for p, _ in overlay.EXTERNAL_RECEIPTS),
                *PRODUCER_GENERATED_MARKDOWN_FILES,
            )
        ), frozenset()
    if profile == "consumer":
        return frozenset(overlay.RELEASE_FILES), frozenset({CANONICAL_RECEIPT})
    raise TrackedSourceTreeError("tracked_source_profile_invalid")


def verify_tracked_source_tree(
    *,
    repo_root: Path,
    source_sha: str,
    allowed_modified_paths: Iterable[str] = (),
    allowed_untracked_paths: Iterable[str] = (),
) -> dict[str, object]:
    """Verify index, modes and every non-output canonical Git content hash.

    Git text representation and source-bound LFS v1 pointers are the checkout
    contract. Custom filters are rejected; LFS clean/process are disabled.
    This helper bypasses the index stat cache but does not authenticate hostile
    local Git configuration. Artifact raw bytes are sealed separately.
    Generated exemptions permit regular-file content changes only.
    """
    root = Path(os.path.abspath(repo_root))
    _require(root.is_dir() and not root.is_symlink(), "tracked_source_root_unsafe")
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        _require(stat.S_ISDIR(os.lstat(current).st_mode), "tracked_source_root_unsafe")
    _require(
        SHA.fullmatch(source_sha) and source_sha != "0" * 40,
        "tracked_source_sha_invalid",
    )
    allowed_modified = frozenset(_safe_path(p) for p in allowed_modified_paths)
    allowed_untracked = frozenset(_safe_path(p) for p in allowed_untracked_paths)
    _require(
        _git(root, "rev-parse", "--verify", "HEAD^{commit}").strip().decode()
        == source_sha,
        "tracked_source_head_mismatch",
    )
    source = _tree(root, source_sha)
    _require(_index(root) == source, "tracked_source_index_tree_mismatch")
    untracked = set(
        _rows(_git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    )
    for path in untracked:
        _safe_path(path)
    _require(untracked <= allowed_untracked, "tracked_source_untracked_path")
    for path, (mode, _) in source.items():
        _regular_mode(root, path, mode)
    for path in untracked:
        _regular_mode(root, path, "100644")

    _verify_attribute_ancestry(root, source)

    # Explicitly hash every non-output path. A same-size edit with restored
    # mtime must not be accepted solely because Git's stat cache looks clean.
    paths = sorted(source)
    checked = sorted(set(source) - allowed_modified)
    attributes = [
        path for path in paths if PurePosixPath(path).name == ".gitattributes"
    ]
    _require(
        not allowed_modified.intersection(attributes),
        "tracked_source_attributes_exemption_forbidden",
    )
    for path in attributes:
        committed = _git(root, "cat-file", "blob", source[path][1])
        working = (root / path).read_bytes()
        _require(
            working.replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n"),
            "tracked_source_attributes_mismatch:" + path,
        )
    filters = _filters(root, paths)
    hashes = _canonical_hashes(root, paths)
    modified: list[str] = []
    for path, observed in zip(paths, hashes):
        matches = observed == source[path][1]
        if not matches and filters[path] == "lfs":
            matches = _matches_lfs_pointer(root, path, source[path][1])
        if not matches and path in allowed_modified:
            modified.append(path)
        else:
            _require(matches, "tracked_source_content_mismatch:" + path)
    # No diff or textconv command is needed: explicit content hashes decide
    # changes, including source-bound hydrated LFS bytes without git-lfs.
    for path, (mode, _) in source.items():
        _regular_mode(root, path, mode)
    _require(_index(root) == source, "tracked_source_index_changed_during_check")
    _require(
        _git(root, "rev-parse", "--verify", "HEAD^{commit}").strip().decode()
        == source_sha,
        "tracked_source_head_changed_during_check",
    )
    return {
        "source_commit_sha": source_sha,
        "source_tree_sha": _git(root, "rev-parse", source_sha + "^{tree}")
        .strip()
        .decode(),
        "tracked_path_count": len(source),
        "canonical_content_checked_count": len(checked),
        "modified_generated_paths": sorted(modified),
        "allowed_untracked_paths_present": sorted(untracked),
        "contract_pass": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--profile", choices=("pristine", "producer", "consumer"), required=True
    )
    args = parser.parse_args(argv)
    try:
        modified, untracked = source_profile_paths(args.profile)
        receipt = verify_tracked_source_tree(
            repo_root=args.repo_root,
            source_sha=args.source_sha,
            allowed_modified_paths=modified,
            allowed_untracked_paths=untracked,
        )
    except TrackedSourceTreeError as exc:
        print("tracked source verification failed: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
