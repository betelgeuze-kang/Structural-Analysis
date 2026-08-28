#!/usr/bin/env python3
"""Verify a signed, source-bound rights-holder license decision."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ID = "betelgeuze-kang/structural-analysis"
DECISION_SCHEMA = ROOT / "canonical/rights-holder-license-decision.v1.schema.json"
TRUST_ROOT_SCHEMA = ROOT / "canonical/rights-holder-license-trust-root.v1.schema.json"
DEFAULT_TRUST_ROOT = Path("canonical/rights-holder-license-trust-root.v1.json")
REPLAY_POLICY = "exact_subject_and_source_commit_until_expiry"
TRUSTED_GIT = Path("/usr/bin/git")
TRUSTED_OPENSSL = Path("/usr/bin/openssl")
MAX_AUTHORITY_FILE_BYTES = 2 * 1024 * 1024
MAX_DECISION_VALIDITY_SECONDS = 90 * 24 * 60 * 60
LICENSE_POLICY_DIRECTORY = Path("canonical/license-policies")
REQUIRED_FIRST_PARTY_COVERAGE = [
    ".betelgeuze/**",
    ".coveragerc",
    ".cursor/**",
    ".gitattributes",
    ".github/**",
    ".gitignore",
    ".ignore",
    ".kiro/**",
    ".phase1_missing_artifact",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "DESIGN.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "apps/**",
    "artifacts/**",
    "benchmarks/**",
    "canonical/**",
    "ci/**",
    "commercial_gap_analysis.md",
    "deployment/**",
    "docs/**",
    "examples/**",
    "implementation/**",
    "index.html",
    "native/**",
    "opencode.json",
    "package-lock.json",
    "package.json",
    "prototype/**",
    "pyproject.toml",
    "pytest.ini",
    "requirements.txt",
    "schemas/**",
    "scripts/**",
    "setup.cfg",
    "src/**",
    "structural_viewer.html",
    "tests/**",
    "tsconfig.json",
    "verification/**",
    "vite.config.ts",
]
RIGHTS_HOLDER_DECISION_DIRECTORY = Path(
    "implementation/phase1/release/license_decisions"
)
CANONICAL_LICENSE_STATUS = Path(
    "implementation/phase1/release/support_bundle/license_status.json"
)
_LFS_POINTER = re.compile(
    rb"version https://git-lfs.github.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\n"
    rb"size ([0-9]+)\n"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_ALLOWED_TIERS = {"paid-pilot", "limited-commercial"}
_ALLOWED_APPROVER_ROLES = {
    "product_owner",
    "legal_counsel",
    "product_and_legal",
    "delegated_product_owner",
}


def canonical_decision_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the exact bytes covered by the detached decision signature."""

    signed = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(
        signed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _load_object_bytes(payload: bytes) -> dict[str, Any]:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_json_key")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise ValueError("non_finite_json_number")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _read_repository_file(
    path: Path,
    *,
    repo_root: Path,
) -> tuple[Path | None, bytes, str]:
    root = repo_root.resolve()
    candidate = path if path.is_absolute() else root / path
    if not candidate.is_absolute():
        candidate = candidate.absolute()
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return None, b"", "outside_repository_or_missing"
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None, b"", "outside_repository_or_missing"
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return None, b"", "nofollow_unsupported"
    if candidate.is_symlink():
        return None, b"", "symlink_not_allowed"

    descriptors: list[int] = []
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(directory_fd)
        root_metadata = os.fstat(directory_fd)
        # Group-writable worktrees are common on managed build hosts.  Reject
        # world-write and special permission bits while still requiring the
        # invoking/root owner; the same boundary is applied to authority files.
        if root_metadata.st_mode & 0o7002 or root_metadata.st_uid not in {
            0,
            os.geteuid(),
        }:
            return None, b"", "unsafe_owner_or_permissions"
        for part in relative.parts[:-1]:
            directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            descriptors.append(directory_fd)
            directory_metadata = os.fstat(directory_fd)
            if directory_metadata.st_mode & 0o7002 or directory_metadata.st_uid not in {
                0,
                os.geteuid(),
            }:
                return None, b"", "unsafe_owner_or_permissions"
        file_fd = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        descriptors.append(file_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            return None, b"", "not_regular_file"
        if metadata.st_mode & 0o7002 or metadata.st_uid not in {0, os.geteuid()}:
            return None, b"", "unsafe_owner_or_permissions"
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(file_fd, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_AUTHORITY_FILE_BYTES:
                return None, b"", "file_too_large"
            chunks.append(chunk)
        return root / relative, b"".join(chunks), "ok"
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, OSError) and error.errno in {errno.ELOOP, errno.ENOTDIR}:
            return None, b"", "symlink_not_allowed"
        return None, b"", "outside_repository_or_missing"
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _trusted_git_run(
    arguments: list[str],
    *,
    repo_root: Path,
) -> subprocess.CompletedProcess[bytes] | None:
    try:
        metadata = TRUSTED_GIT.stat()
    except OSError:
        return None
    if (
        TRUSTED_GIT.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
    ):
        return None
    try:
        return subprocess.run(
            [
                str(TRUSTED_GIT),
                "--no-replace-objects",
                f"--work-tree={repo_root.resolve()}",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "core.ignoreStat=false",
                "-c",
                "core.trustctime=true",
                "-c",
                "core.checkStat=default",
                "-c",
                "core.fileMode=true",
                "-c",
                "core.hooksPath=/nonexistent",
                *arguments,
            ],
            cwd=repo_root,
            env={
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "HOME": "/nonexistent",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _trusted_openssl_run(
    arguments: list[str],
    *,
    input_bytes: bytes = b"",
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[bytes] | None:
    try:
        metadata = TRUSTED_OPENSSL.stat()
    except OSError:
        return None
    if (
        TRUSTED_OPENSSL.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
    ):
        return None
    try:
        return subprocess.run(
            [str(TRUSTED_OPENSSL), *arguments],
            input=input_bytes,
            env={
                "HOME": "/nonexistent",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
            pass_fds=pass_fds,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _trusted_openssl_signature_inspection(
    *,
    public_key_bytes: bytes,
    signature_bytes: bytes,
    signed_bytes: bytes,
) -> tuple[bool, int, int]:
    """Verify key strength and PKCS#1-v1.5/SHA-256 with root-owned OpenSSL."""

    if not hasattr(os, "memfd_create") or not Path("/proc/self/fd").is_dir():
        return False, 0, 0
    descriptors: list[int] = []
    try:
        public_key_fd = os.memfd_create("rights-holder-public-key", os.MFD_CLOEXEC)
        signature_fd = os.memfd_create("rights-holder-signature", os.MFD_CLOEXEC)
        descriptors.extend([public_key_fd, signature_fd])
        for descriptor, payload in (
            (public_key_fd, public_key_bytes),
            (signature_fd, signature_bytes),
        ):
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    return False, 0, 0
                view = view[written:]
            os.lseek(descriptor, 0, os.SEEK_SET)
        key_path = f"/proc/self/fd/{public_key_fd}"
        signature_path = f"/proc/self/fd/{signature_fd}"
        key_inspection = _trusted_openssl_run(
            ["pkey", "-pubin", "-in", key_path, "-text", "-noout"],
            pass_fds=(public_key_fd,),
        )
        if key_inspection is None or key_inspection.returncode != 0:
            return False, 0, 0
        bits_match = re.search(
            rb"^Public-Key: \(([0-9]+) bit\)$",
            key_inspection.stdout,
            re.MULTILINE,
        )
        exponent_match = re.search(
            rb"^Exponent: ([0-9]+)(?: |$)",
            key_inspection.stdout,
            re.MULTILINE,
        )
        if bits_match is None or exponent_match is None:
            return False, 0, 0
        public_key_bits = int(bits_match.group(1))
        public_key_exponent = int(exponent_match.group(1))
        if public_key_bits < 2048 or public_key_exponent != 65537:
            return False, public_key_bits, public_key_exponent
        verification = _trusted_openssl_run(
            [
                "dgst",
                "-sha256",
                "-verify",
                key_path,
                "-signature",
                signature_path,
            ],
            input_bytes=signed_bytes,
            pass_fds=(public_key_fd, signature_fd),
        )
        signature_verified = bool(
            verification is not None
            and verification.returncode == 0
            and verification.stdout == b"Verified OK\n"
            and verification.stderr == b""
        )
        return signature_verified, public_key_bits, public_key_exponent
    except (OSError, UnicodeError, ValueError):
        return False, 0, 0
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def source_commit_head(repo_root: Path) -> str:
    completed = _trusted_git_run(["rev-parse", "HEAD"], repo_root=repo_root)
    if completed is None or completed.returncode != 0:
        return ""
    try:
        value = completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        return ""
    return (
        value
        if len(value) == 40 and all(c in "0123456789abcdef" for c in value)
        else ""
    )


def _tracked_file_matches_source_commit(
    path: Path | None,
    observed_bytes: bytes,
    *,
    repo_root: Path,
    source_commit_sha: str,
) -> bool:
    """Return true only for an exact regular-file blob tracked at the source commit."""

    if path is None:
        return False
    try:
        relative = path.relative_to(repo_root.resolve()).as_posix()
        tracked = _trusted_git_run(
            ["show", f"{source_commit_sha}:{relative}"],
            repo_root=repo_root,
        )
    except ValueError:
        return False
    return bool(
        tracked is not None
        and tracked.returncode == 0
        and tracked.stdout == observed_bytes
    )


def _coverage_pattern_matches_path(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(f"{prefix}/")
    return path == pattern


def _source_tree_coverage_pass(
    *,
    repo_root: Path,
    source_commit_sha: str,
    coverage: list[str],
) -> bool:
    """Require every source-commit path to be inside the signed path inventory."""

    tracked = _trusted_git_run(
        ["ls-tree", "-r", "--name-only", "-z", source_commit_sha],
        repo_root=repo_root,
    )
    if tracked is None or tracked.returncode != 0:
        return False
    try:
        paths = [
            raw.decode("utf-8")
            for raw in tracked.stdout.split(b"\0")
            if raw
        ]
    except UnicodeDecodeError:
        return False
    return bool(
        paths
        and all(
            any(
                _coverage_pattern_matches_path(pattern, path)
                for pattern in coverage
            )
            for path in paths
        )
    )


def _worktree_matches_source_commit(
    *,
    repo_root: Path,
    source_commit_sha: str,
    decision_path: Path | None,
    allowed_untracked_paths: list[Path] | None = None,
) -> bool:
    """Cryptographically compare the checked-out tree with the subject commit.

    Git status/index stat hints are insufficient here: assume-unchanged,
    skip-worktree, sparse checkouts, and a local core.worktree redirect can all
    hide modified source.  This routine pins Git to ``repo_root``, requires a
    plain index matching the commit tree, hashes every tracked worktree entry,
    and rejects every extra file except the explicitly supplied authority
    records.  Strict Git-LFS pointers are compared to the expanded worktree
    object's SHA-256 and size.
    """

    if source_commit_head(repo_root) != source_commit_sha:
        return False

    expected_tree = _trusted_git_run(
        ["rev-parse", f"{source_commit_sha}^{{tree}}"],
        repo_root=repo_root,
    )
    index_tree = _trusted_git_run(["write-tree"], repo_root=repo_root)
    if (
        expected_tree is None
        or expected_tree.returncode != 0
        or index_tree is None
        or index_tree.returncode != 0
        or expected_tree.stdout.strip() != index_tree.stdout.strip()
    ):
        return False

    index_entries = _trusted_git_run(["ls-files", "-v", "-z"], repo_root=repo_root)
    if index_entries is None or index_entries.returncode != 0:
        return False
    if any(
        entry and not entry.startswith(b"H ")
        for entry in index_entries.stdout.split(b"\0")
    ):
        return False

    tree = _trusted_git_run(
        ["ls-tree", "-r", "-z", "--full-tree", source_commit_sha],
        repo_root=repo_root,
    )
    if tree is None or tree.returncode != 0:
        return False
    observed_metadata: list[tuple[Path, str, tuple[int, ...]]] = []
    for raw_entry in tree.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode_raw, object_type, object_id = metadata.split()
            relative = Path(raw_path.decode("utf-8"))
            mode = mode_raw.decode("ascii")
            expected_object_id = object_id.decode("ascii")
        except (UnicodeDecodeError, ValueError):
            return False
        if object_type != b"blob" or mode not in {"100644", "100755", "120000"}:
            return False
        observed = _hash_worktree_entry(
            relative,
            repo_root=repo_root,
            expected_mode=mode,
        )
        if observed is None:
            return False
        (
            observed_object_id,
            observed_sha256,
            observed_size,
            metadata_signature,
        ) = observed
        observed_metadata.append((relative, mode, metadata_signature))
        if observed_object_id == expected_object_id:
            continue
        committed_size = _trusted_git_run(
            ["cat-file", "-s", expected_object_id],
            repo_root=repo_root,
        )
        if committed_size is None or committed_size.returncode != 0:
            return False
        try:
            committed_size_value = int(committed_size.stdout.strip())
        except ValueError:
            return False
        if committed_size_value > 1024:
            return False
        committed_blob = _trusted_git_run(
            ["cat-file", "blob", expected_object_id],
            repo_root=repo_root,
        )
        if committed_blob is None or committed_blob.returncode != 0:
            return False
        pointer = _LFS_POINTER.fullmatch(committed_blob.stdout)
        if (
            pointer is None
            or observed_sha256 != pointer.group(1).decode("ascii")
            or observed_size != int(pointer.group(2))
        ):
            return False

    for relative, mode, metadata_signature in observed_metadata:
        if (
            _worktree_entry_metadata_signature(
                relative,
                repo_root=repo_root,
                expected_mode=mode,
            )
            != metadata_signature
        ):
            return False

    allowed_paths: set[str] = {CANONICAL_LICENSE_STATUS.as_posix()}
    for path in [decision_path, *(allowed_untracked_paths or [])]:
        if path is None:
            continue
        try:
            relative_path = path.relative_to(repo_root)
        except ValueError:
            return False
        if path != decision_path:
            temporary_status = bool(
                relative_path.parent == CANONICAL_LICENSE_STATUS.parent
                and relative_path.name.startswith(f".{CANONICAL_LICENSE_STATUS.name}.")
                and relative_path.name.endswith(".tmp")
            )
            if relative_path != CANONICAL_LICENSE_STATUS and not temporary_status:
                return False
        allowed_paths.add(relative_path.as_posix())
    untracked = _trusted_git_run(
        ["ls-files", "--others", "-z", "--"],
        repo_root=repo_root,
    )
    if untracked is None or untracked.returncode != 0:
        return False
    observed_untracked: set[str] = set()
    for raw_path in untracked.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            observed_untracked.add(raw_path.decode("utf-8"))
        except UnicodeDecodeError:
            return False
    return observed_untracked.issubset(allowed_paths)


def _hash_worktree_entry(
    relative: Path,
    *,
    repo_root: Path,
    expected_mode: str,
) -> tuple[str, str, int, tuple[int, ...]] | None:
    """Return Git blob SHA-1, content SHA-256, and size without following links."""

    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return None
    descriptors: list[int] = []
    try:
        directory_fd = os.open(repo_root, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(directory_fd)
        for part in relative.parts[:-1]:
            directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            descriptors.append(directory_fd)
        name = relative.parts[-1]
        if expected_mode == "120000":
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISLNK(metadata.st_mode):
                return None
            payload = os.fsencode(os.readlink(name, dir_fd=directory_fd))
            git_digest = hashlib.sha1(usedforsecurity=False)
            git_digest.update(f"blob {len(payload)}\0".encode("ascii"))
            git_digest.update(payload)
            return (
                git_digest.hexdigest(),
                hashlib.sha256(payload).hexdigest(),
                len(payload),
                _stat_signature(metadata),
            )

        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            return None
        if before.st_mode & 0o7002 or before.st_uid not in {0, os.geteuid()}:
            return None
        executable = bool(before.st_mode & 0o111)
        if executable != (expected_mode == "100755"):
            return None
        git_digest = hashlib.sha1(usedforsecurity=False)
        git_digest.update(f"blob {before.st_size}\0".encode("ascii"))
        content_digest = hashlib.sha256()
        observed_size = 0
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            git_digest.update(chunk)
            content_digest.update(chunk)
            observed_size += len(chunk)
        after = os.fstat(file_fd)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            return None
        if observed_size != before.st_size:
            return None
        return (
            git_digest.hexdigest(),
            content_digest.hexdigest(),
            observed_size,
            _stat_signature(after),
        )
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _stat_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _worktree_entry_metadata_signature(
    relative: Path,
    *,
    repo_root: Path,
    expected_mode: str,
) -> tuple[int, ...] | None:
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    descriptors: list[int] = []
    try:
        directory_fd = os.open(repo_root, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(directory_fd)
        for part in relative.parts[:-1]:
            directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            descriptors.append(directory_fd)
        metadata = os.stat(
            relative.parts[-1],
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if expected_mode == "120000":
            if not stat.S_ISLNK(metadata.st_mode):
                return None
        elif not stat.S_ISREG(metadata.st_mode) or bool(metadata.st_mode & 0o111) != (
            expected_mode == "100755"
        ):
            return None
        return _stat_signature(metadata)
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _exact_keys(value: Any, expected: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def _valid_string_list(value: Any, *, allowed: set[str] | None = None) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
        and (allowed is None or set(value).issubset(allowed))
    )


def _decision_shape_valid(payload: Mapping[str, Any]) -> bool:
    top_keys = {
        "schema_version",
        "decision_id",
        "rights_holder_id",
        "signer_id",
        "issued_at_utc",
        "expires_at_utc",
        "replay_policy",
        "nonce",
        "subject",
        "grants",
        "signature",
        "claim_boundary",
    }
    if not _exact_keys(payload, top_keys):
        return False
    subject = payload.get("subject")
    policy = subject.get("license_policy") if isinstance(subject, dict) else None
    grants = payload.get("grants")
    signature = payload.get("signature")
    return bool(
        payload.get("schema_version") == "rights-holder-license-decision.v1"
        and isinstance(payload.get("decision_id"), str)
        and len(payload["decision_id"]) >= 8
        and isinstance(payload.get("rights_holder_id"), str)
        and len(payload["rights_holder_id"]) >= 3
        and isinstance(payload.get("signer_id"), str)
        and len(payload["signer_id"]) >= 3
        and isinstance(payload.get("issued_at_utc"), str)
        and isinstance(payload.get("expires_at_utc"), str)
        and payload.get("replay_policy") == REPLAY_POLICY
        and isinstance(payload.get("nonce"), str)
        and _NONCE.fullmatch(payload["nonce"])
        and _exact_keys(
            subject,
            {
                "repository_id",
                "source_commit_sha",
                "repository_license_sha256",
                "license_id",
                "license_policy",
                "tier",
                "approver_role",
                "product_scope",
            },
        )
        and subject.get("repository_id") == REPOSITORY_ID
        and isinstance(subject.get("source_commit_sha"), str)
        and _SOURCE_SHA.fullmatch(subject["source_commit_sha"])
        and isinstance(subject.get("repository_license_sha256"), str)
        and _SHA256.fullmatch(subject["repository_license_sha256"])
        and isinstance(subject.get("license_id"), str)
        and len(subject["license_id"]) >= 3
        and subject.get("tier") in _ALLOWED_TIERS
        and subject.get("approver_role") in _ALLOWED_APPROVER_ROLES
        and subject.get("product_scope")
        == [
            "review-assist",
            "specified-structure-families",
            "specified-workflows",
            "engine-and-reviewer-evidence-package",
        ]
        and _exact_keys(
            policy,
            {
                "document_path",
                "document_sha256",
                "version",
                "covered_first_party_paths",
            },
        )
        and isinstance(policy.get("document_path"), str)
        and isinstance(policy.get("document_sha256"), str)
        and _SHA256.fullmatch(policy["document_sha256"])
        and isinstance(policy.get("version"), str)
        and len(policy["version"]) >= 3
        and policy.get("covered_first_party_paths") == REQUIRED_FIRST_PARTY_COVERAGE
        and grants
        == {
            "repository_use_approved": True,
            "commercial_use_approved": True,
            "redistribution_approved": True,
            "third_party_material_redistribution_approved": False,
            "release_authority_granted": False,
        }
        and _exact_keys(
            signature,
            {"algorithm", "signed_payload_sha256", "value_base64"},
        )
        and signature.get("algorithm") == "rsa-sha256"
        and isinstance(signature.get("signed_payload_sha256"), str)
        and _SHA256.fullmatch(signature["signed_payload_sha256"])
        and isinstance(signature.get("value_base64"), str)
        and len(signature["value_base64"]) >= 64
        and isinstance(payload.get("claim_boundary"), str)
        and len(payload["claim_boundary"]) >= 80
    )


def _trust_root_shape_valid(payload: Mapping[str, Any]) -> bool:
    top_keys = {
        "schema_version",
        "repository_id",
        "approved_signers",
        "revoked_signer_ids",
        "revoked_decision_ids",
        "claim_boundary",
    }
    if not _exact_keys(payload, top_keys):
        return False
    signers = payload.get("approved_signers")
    if not isinstance(signers, list):
        return False
    signer_keys = {
        "signer_id",
        "rights_holder_id",
        "algorithm",
        "public_key_path",
        "public_key_sha256",
        "allowed_repository_license_sha256",
        "allowed_license_ids",
        "allowed_license_policy",
        "allowed_tiers",
        "allowed_approver_roles",
        "allowed_product_scope",
    }
    for signer in signers:
        policy = (
            signer.get("allowed_license_policy")
            if isinstance(signer, dict)
            else None
        )
        if not (
            _exact_keys(signer, signer_keys)
            and isinstance(signer.get("signer_id"), str)
            and len(signer["signer_id"]) >= 3
            and isinstance(signer.get("rights_holder_id"), str)
            and len(signer["rights_holder_id"]) >= 3
            and signer.get("algorithm") == "rsa-sha256"
            and isinstance(signer.get("public_key_path"), str)
            and isinstance(signer.get("public_key_sha256"), str)
            and _SHA256.fullmatch(signer["public_key_sha256"])
            and isinstance(signer.get("allowed_repository_license_sha256"), str)
            and _SHA256.fullmatch(signer["allowed_repository_license_sha256"])
            and _valid_string_list(signer.get("allowed_license_ids"))
            and _valid_string_list(
                signer.get("allowed_tiers"), allowed=_ALLOWED_TIERS
            )
            and _valid_string_list(
                signer.get("allowed_approver_roles"),
                allowed=_ALLOWED_APPROVER_ROLES,
            )
            and signer.get("allowed_product_scope")
            == [
                "review-assist",
                "specified-structure-families",
                "specified-workflows",
                "engine-and-reviewer-evidence-package",
            ]
            and _exact_keys(
                policy,
                {
                    "document_path",
                    "document_sha256",
                    "version",
                    "covered_first_party_paths",
                },
            )
            and isinstance(policy.get("document_path"), str)
            and isinstance(policy.get("document_sha256"), str)
            and _SHA256.fullmatch(policy["document_sha256"])
            and isinstance(policy.get("version"), str)
            and len(policy["version"]) >= 3
            and policy.get("covered_first_party_paths")
            == REQUIRED_FIRST_PARTY_COVERAGE
        ):
            return False
    revoked_signers = payload.get("revoked_signer_ids")
    revoked_decisions = payload.get("revoked_decision_ids")
    return bool(
        payload.get("schema_version") == "rights-holder-license-trust-root.v1"
        and payload.get("repository_id") == REPOSITORY_ID
        and isinstance(revoked_signers, list)
        and all(isinstance(item, str) and len(item) >= 3 for item in revoked_signers)
        and len(revoked_signers) == len(set(revoked_signers))
        and isinstance(revoked_decisions, list)
        and all(isinstance(item, str) and len(item) >= 8 for item in revoked_decisions)
        and len(revoked_decisions) == len(set(revoked_decisions))
        and isinstance(payload.get("claim_boundary"), str)
        and len(payload["claim_boundary"]) >= 80
    )


def inspect_rights_holder_license_decision(
    *,
    decision_path: Path,
    trust_root_path: Path = DEFAULT_TRUST_ROOT,
    repo_root: Path = ROOT,
    expected_source_commit_sha: str,
    expected_decision_id: str,
    expected_license_id: str,
    expected_tier: str,
    expected_approver_role: str,
    expected_product_scope: list[str],
    expected_rights_holder_id: str,
    expected_approved_at_utc: str,
    expected_expires_at_utc: str,
    allowed_untracked_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Inspect a decision against repository trust and its exact license subject."""

    now = datetime.now(timezone.utc)
    repo_root = repo_root.resolve()
    blockers: list[str] = []

    decision_file, decision_bytes, decision_path_status = _read_repository_file(
        decision_path,
        repo_root=repo_root,
    )
    if decision_file is None:
        blockers.append(f"rights_holder_decision_{decision_path_status}")
    decision_path_bounded = False
    if decision_file is not None:
        try:
            decision_relative = decision_file.relative_to(repo_root)
            decision_path_bounded = bool(
                decision_relative.parent == RIGHTS_HOLDER_DECISION_DIRECTORY
                and decision_relative.suffix == ".json"
            )
        except ValueError:
            decision_path_bounded = False
    if not decision_path_bounded:
        blockers.append("rights_holder_decision_path_not_canonical")
    trust_file, trust_bytes, trust_path_status = _read_repository_file(
        trust_root_path,
        repo_root=repo_root,
    )
    if trust_file is None:
        blockers.append(f"rights_holder_trust_root_{trust_path_status}")
    canonical_trust_root_pass = bool(
        trust_file is not None and trust_file == repo_root / DEFAULT_TRUST_ROOT
    )
    if not canonical_trust_root_pass:
        blockers.append("rights_holder_trust_root_not_canonical")

    decision = _load_object_bytes(decision_bytes)
    trust_root = _load_object_bytes(trust_bytes)
    # Keep the runtime verifier stdlib-only so the official command can run with
    # ``python -I -B``.  The checked-in JSON Schemas remain the documentation and
    # producer contract; these exact-shape checks are the fail-closed consumer
    # boundary and cannot be replaced through ambient site-packages/PYTHONPATH.
    if not _decision_shape_valid(decision):
        blockers.append("rights_holder_decision_schema_invalid:$")
    if not _trust_root_shape_valid(trust_root):
        blockers.append("rights_holder_trust_root_schema_invalid:$")

    subject = decision.get("subject")
    subject = subject if isinstance(subject, dict) else {}
    grants = decision.get("grants")
    grants = grants if isinstance(grants, dict) else {}
    signature = decision.get("signature")
    signature = signature if isinstance(signature, dict) else {}
    decision_id = str(decision.get("decision_id") or "")
    signer_id = str(decision.get("signer_id") or "")
    rights_holder_id = str(decision.get("rights_holder_id") or "")
    license_policy = subject.get("license_policy")
    license_policy = license_policy if isinstance(license_policy, dict) else {}

    license_policy_file: Path | None = None
    license_policy_bytes = b""
    license_policy_sha256 = ""
    policy_path_value = str(license_policy.get("document_path") or "")
    policy_path = Path(policy_path_value)
    policy_path_bounded = bool(
        policy_path_value
        and not policy_path.is_absolute()
        and ".." not in policy_path.parts
        and policy_path.parts[:2] == LICENSE_POLICY_DIRECTORY.parts
        and len(policy_path.parts) > len(LICENSE_POLICY_DIRECTORY.parts)
    )
    if not policy_path_bounded:
        blockers.append("rights_holder_license_policy_path_not_bounded")
    else:
        (
            license_policy_file,
            license_policy_bytes,
            license_policy_path_status,
        ) = _read_repository_file(policy_path, repo_root=repo_root)
        if license_policy_file is None:
            blockers.append(
                f"rights_holder_license_policy_{license_policy_path_status}"
            )
        else:
            license_policy_sha256 = sha256_bytes(license_policy_bytes)
            if license_policy_sha256 != license_policy.get("document_sha256"):
                blockers.append("rights_holder_license_policy_hash_mismatch")
    covered_first_party_paths = license_policy.get("covered_first_party_paths")
    coverage_paths_valid = bool(
        isinstance(covered_first_party_paths, list)
        and covered_first_party_paths == REQUIRED_FIRST_PARTY_COVERAGE
        and all(
            isinstance(item, str)
            and item.strip() == item
            and item
            and not Path(item).is_absolute()
            and ".." not in Path(item).parts
            for item in covered_first_party_paths
        )
    )
    if not coverage_paths_valid:
        blockers.append("rights_holder_license_policy_coverage_invalid")
    source_tree_coverage_pass = bool(
        coverage_paths_valid
        and _source_tree_coverage_pass(
            repo_root=repo_root,
            source_commit_sha=expected_source_commit_sha,
            coverage=covered_first_party_paths,
        )
    )
    if not source_tree_coverage_pass:
        blockers.append("rights_holder_license_policy_source_tree_not_covered")

    (
        repository_license,
        repository_license_bytes,
        repository_license_status,
    ) = _read_repository_file(
        repo_root / "LICENSE",
        repo_root=repo_root,
    )
    if repository_license is None:
        blockers.append(f"repository_license_{repository_license_status}")
    repository_license_sha256 = (
        sha256_bytes(repository_license_bytes) if repository_license else ""
    )
    expected_subject = {
        "repository_id": REPOSITORY_ID,
        "source_commit_sha": expected_source_commit_sha,
        "repository_license_sha256": repository_license_sha256,
        "license_id": expected_license_id,
        "license_policy": license_policy,
        "tier": expected_tier,
        "approver_role": expected_approver_role,
        "product_scope": expected_product_scope,
    }
    subject_binding_pass = bool(subject == expected_subject)
    if not subject_binding_pass:
        blockers.append("rights_holder_decision_subject_binding_mismatch")
    if rights_holder_id != expected_rights_holder_id:
        blockers.append("rights_holder_decision_rights_holder_mismatch")
    decision_id_binding_pass = bool(decision_id == expected_decision_id)
    if not decision_id_binding_pass:
        blockers.append("rights_holder_decision_id_binding_mismatch")
    if decision.get("replay_policy") != REPLAY_POLICY:
        blockers.append("rights_holder_decision_replay_policy_invalid")

    issued_at = _parse_utc(decision.get("issued_at_utc"))
    expires_at = _parse_utc(decision.get("expires_at_utc"))
    expected_issued_at = _parse_utc(expected_approved_at_utc)
    expected_expiry = _parse_utc(expected_expires_at_utc)
    timeline_pass = bool(
        issued_at is not None
        and expires_at is not None
        and expected_issued_at is not None
        and expected_expiry is not None
        and issued_at == expected_issued_at
        and expires_at == expected_expiry
        and issued_at <= now < expires_at
        and (expires_at - issued_at).total_seconds() <= MAX_DECISION_VALIDITY_SECONDS
    )
    if not timeline_pass:
        blockers.append("rights_holder_decision_timeline_invalid_or_expired")

    required_grants = {
        "repository_use_approved": True,
        "commercial_use_approved": True,
        "redistribution_approved": True,
        "third_party_material_redistribution_approved": False,
        "release_authority_granted": False,
    }
    grants_pass = grants == required_grants
    if not grants_pass:
        blockers.append("rights_holder_decision_grants_invalid")

    approved_signers = trust_root.get("approved_signers")
    approved_signers = approved_signers if isinstance(approved_signers, list) else []
    signer_rows = [
        row
        for row in approved_signers
        if isinstance(row, dict) and row.get("signer_id") == signer_id
    ]
    signer = signer_rows[0] if len(signer_rows) == 1 else {}
    if len(signer_rows) != 1:
        blockers.append("rights_holder_decision_signer_not_uniquely_approved")
    if signer.get("rights_holder_id") != rights_holder_id:
        blockers.append("rights_holder_decision_signer_rights_holder_mismatch")
    if signer_id in set(trust_root.get("revoked_signer_ids") or []):
        blockers.append("rights_holder_decision_signer_revoked")
    if decision_id in set(trust_root.get("revoked_decision_ids") or []):
        blockers.append("rights_holder_decision_revoked")

    public_key_file: Path | None = None
    public_key_bytes = b""
    public_key_sha256 = ""
    if signer:
        (
            public_key_file,
            public_key_bytes,
            public_key_status,
        ) = _read_repository_file(
            Path(str(signer.get("public_key_path") or "")),
            repo_root=repo_root,
        )
        if public_key_file is None:
            blockers.append(f"rights_holder_public_key_{public_key_status}")
        else:
            public_key_sha256 = sha256_bytes(public_key_bytes)
            if public_key_sha256 != signer.get("public_key_sha256"):
                blockers.append("rights_holder_public_key_hash_mismatch")
    if signer.get("algorithm") != "rsa-sha256":
        blockers.append("rights_holder_signer_algorithm_invalid")
    signer_policy_pass = bool(
        signer
        and signer.get("allowed_repository_license_sha256") == repository_license_sha256
        and expected_license_id in set(signer.get("allowed_license_ids") or [])
        and signer.get("allowed_license_policy") == license_policy
        and expected_tier in set(signer.get("allowed_tiers") or [])
        and expected_approver_role in set(signer.get("allowed_approver_roles") or [])
        and signer.get("allowed_product_scope") == expected_product_scope
    )
    if not signer_policy_pass:
        blockers.append("rights_holder_signer_policy_not_authorized")

    repository_license_source_binding_pass = _tracked_file_matches_source_commit(
        repository_license,
        repository_license_bytes,
        repo_root=repo_root,
        source_commit_sha=expected_source_commit_sha,
    )
    if not repository_license_source_binding_pass:
        blockers.append("repository_license_not_exact_source_blob")
    trust_root_source_binding_pass = _tracked_file_matches_source_commit(
        trust_file,
        trust_bytes,
        repo_root=repo_root,
        source_commit_sha=expected_source_commit_sha,
    )
    if not trust_root_source_binding_pass:
        blockers.append("rights_holder_trust_root_not_exact_source_blob")
    public_key_source_binding_pass = _tracked_file_matches_source_commit(
        public_key_file,
        public_key_bytes,
        repo_root=repo_root,
        source_commit_sha=expected_source_commit_sha,
    )
    if not public_key_source_binding_pass:
        blockers.append("rights_holder_public_key_not_exact_source_blob")
    license_policy_source_binding_pass = _tracked_file_matches_source_commit(
        license_policy_file,
        license_policy_bytes,
        repo_root=repo_root,
        source_commit_sha=expected_source_commit_sha,
    )
    if not license_policy_source_binding_pass:
        blockers.append("rights_holder_license_policy_not_exact_source_blob")
    source_worktree_binding_pass = _worktree_matches_source_commit(
        repo_root=repo_root,
        source_commit_sha=expected_source_commit_sha,
        decision_path=decision_file,
        allowed_untracked_paths=allowed_untracked_paths,
    )
    if not source_worktree_binding_pass:
        blockers.append("repository_worktree_not_exact_source_commit")

    signed_bytes = b""
    signed_payload_sha256 = ""
    try:
        signed_bytes = canonical_decision_bytes(decision)
        signed_payload_sha256 = sha256_bytes(signed_bytes)
    except (TypeError, UnicodeError, ValueError):
        blockers.append("rights_holder_decision_canonical_payload_invalid")
    if signature.get("algorithm") != "rsa-sha256":
        blockers.append("rights_holder_decision_signature_algorithm_invalid")
    if signature.get("signed_payload_sha256") != signed_payload_sha256:
        blockers.append("rights_holder_decision_signed_payload_hash_mismatch")

    signature_bytes = b""
    try:
        signature_bytes = base64.b64decode(
            str(signature.get("value_base64") or ""),
            validate=True,
        )
    except (ValueError, binascii.Error):
        blockers.append("rights_holder_decision_signature_base64_invalid")
    if not signature_bytes or len(signature_bytes) > 16 * 1024:
        blockers.append("rights_holder_decision_signature_size_invalid")

    signature_verified = False
    public_key_bits = 0
    public_key_exponent = 0
    if public_key_file is not None and signature_bytes and signed_bytes:
        (
            signature_verified,
            public_key_bits,
            public_key_exponent,
        ) = _trusted_openssl_signature_inspection(
            public_key_bytes=public_key_bytes,
            signature_bytes=signature_bytes,
            signed_bytes=signed_bytes,
        )
    if public_key_bits and public_key_bits < 2048:
        blockers.append("rights_holder_public_key_too_small")
    elif public_key_exponent and public_key_exponent != 65537:
        blockers.append("rights_holder_public_key_exponent_not_allowed")
    elif public_key_file is not None and not public_key_bits:
        blockers.append("rights_holder_public_key_not_rsa")
    if not signature_verified:
        blockers.append("rights_holder_decision_signature_not_verified")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "rights-holder-license-decision-inspection.v1",
        "contract_pass": not blockers,
        "decision_id": decision_id,
        "signer_id": signer_id,
        "rights_holder_id": rights_holder_id,
        "decision_sha256": (sha256_bytes(decision_bytes) if decision_file else ""),
        "trust_root_sha256": (sha256_bytes(trust_bytes) if trust_file else ""),
        "canonical_trust_root_pass": canonical_trust_root_pass,
        "repository_license_sha256": repository_license_sha256,
        "license_policy_path": (
            license_policy_file.relative_to(repo_root).as_posix()
            if license_policy_file is not None
            else ""
        ),
        "license_policy_sha256": license_policy_sha256,
        "license_policy_version": str(license_policy.get("version") or ""),
        "covered_first_party_paths": (
            covered_first_party_paths if coverage_paths_valid else []
        ),
        "source_tree_coverage_pass": source_tree_coverage_pass,
        "public_key_sha256": public_key_sha256,
        "public_key_path": (
            public_key_file.relative_to(repo_root).as_posix()
            if public_key_file is not None
            else ""
        ),
        "public_key_bits": public_key_bits,
        "public_key_exponent": public_key_exponent,
        "signature_verified": signature_verified,
        "decision_id_binding_pass": decision_id_binding_pass,
        "subject_binding_pass": subject_binding_pass,
        "repository_license_source_binding_pass": (
            repository_license_source_binding_pass
        ),
        "trust_root_source_binding_pass": trust_root_source_binding_pass,
        "public_key_source_binding_pass": public_key_source_binding_pass,
        "license_policy_source_binding_pass": (license_policy_source_binding_pass),
        "source_worktree_binding_pass": source_worktree_binding_pass,
        "timeline_and_expiry_pass": timeline_pass,
        "replay_scope_pass": decision.get("replay_policy") == REPLAY_POLICY,
        "grants_contract_pass": grants_pass,
        "signer_policy_authorized_pass": signer_policy_pass,
        "commercial_use_approved": bool(
            not blockers and grants.get("commercial_use_approved") is True
        ),
        "redistribution_approved": bool(
            not blockers and grants.get("redistribution_approved") is True
        ),
        "third_party_material_redistribution_approved": False,
        "release_authority": False,
        "blockers": blockers,
        "claim_boundary": (
            "This inspection verifies one approved repository trust-root signer, the "
            "RSA-SHA256 signature through root-owned /usr/bin/openssl with a sanitized "
            "environment, exact repository/source/license-policy subject, "
            "canonical trust root, signer policy constraints, exact tracked license-policy "
            "artifact, exact required first-party product-path inventory, and complete "
            "source-tree path coverage, "
            "cryptographically matched clean source worktree, "
            "minimum 2048-bit key, maximum 90-day validity, revocation, and bounded replay "
            "policy. It cannot grant third-party "
            "material rights or overall product release authority."
        ),
    }
