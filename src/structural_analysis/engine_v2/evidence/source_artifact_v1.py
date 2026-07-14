"""Fail-closed source-artifact identity for reproducible Engine v2 builds.

The compiler accepts only a clean, top-level Git worktree.  It independently
matches the commit tree, index, same-file-descriptor worktree bytes, and an
exact ``git archive --format=tar HEAD`` bundle before returning release
binding hashes.  No path supplied by the caller is used as evidence by name
alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import hashlib
import io
import os
import re
import stat
import subprocess
import tarfile
from typing import Any, NoReturn
import unicodedata

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


SOURCE_ARTIFACT_SCHEMA_VERSION_V1 = "structural-analysis-source-artifact.v1"
SOURCE_ARTIFACT_MANIFEST_SCHEMA_VERSION_V1 = (
    "structural-analysis-source-artifact-manifest.v1"
)

_ZERO_HASH = "sha256:" + "0" * 64
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_MODE_RE = re.compile(r"^100(?:644|755)$")
_GIT_OBJECT_FORMATS = {"sha1": 40, "sha256": 64}
_READ_CHUNK_BYTES = 1024 * 1024


class SourceArtifactV1Error(ValueError):
    """Stable fail-closed source-artifact verification error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class SourceArtifactFileV1:
    """One canonical regular file from the exact committed source tree."""

    path: str
    git_mode: str
    byte_count: int
    git_blob_oid: str
    content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        _validate_file(self, object_format=None, path="/source_manifest/files")
        return _file_payload(self)


@dataclass(frozen=True, slots=True)
class SourceArtifactManifestV1:
    """Canonical, path-ordered manifest of every tracked source file."""

    schema_version: str
    object_format: str
    source_commit: str
    file_count: int
    files: tuple[SourceArtifactFileV1, ...]
    source_tree_sha256: str

    def to_dict(self) -> dict[str, Any]:
        _validate_manifest(self)
        return _manifest_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class SourceArtifactIdentityV1:
    """Release-ready identities derived from one verified source checkout."""

    schema_version: str
    object_format: str
    source_commit: str
    source_manifest: SourceArtifactManifestV1
    source_tree_sha256: str
    source_bundle_byte_count: int
    source_bundle_sha256: str
    runner_source_paths: tuple[str, ...]
    runner_source_sha256: str
    build_recipe_path: str
    build_recipe_sha256: str
    dependency_lock_path: str
    dependency_lock_sha256: str
    identity_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_source_artifact_identity_v1(self)
        return _identity_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class _GitEntry:
    path: str
    mode: str
    oid: str


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    evidence: SourceArtifactFileV1
    data: bytes


@dataclass(frozen=True, slots=True)
class _ReadSnapshot:
    data: bytes
    sha256: str
    device: int
    inode: int


def compile_source_artifact_identity_v1(
    repository_root: str | os.PathLike[str],
    source_bundle_path: str | os.PathLike[str],
    *,
    runner_source_paths: Sequence[str],
    build_recipe_path: str,
    dependency_lock_path: str,
) -> SourceArtifactIdentityV1:
    """Compile and verify a source identity from one clean Git checkout.

    ``source_bundle_path`` must already contain the exact raw output of
    ``git archive --format=tar HEAD``.  Runner files are hashed as a canonical
    ordered aggregate; the build recipe and dependency lock use their exact
    raw-byte SHA-256 identities.
    """

    root_path = _path_argument(repository_root, "/repository_root")
    bundle_path = _path_argument(source_bundle_path, "/source_bundle_path")
    runner_paths = _normalize_role_paths(
        runner_source_paths,
        path="/runner_source_paths",
        require_nonempty=True,
    )
    _validate_safe_source_path(build_recipe_path, "/build_recipe_path")
    _validate_safe_source_path(dependency_lock_path, "/dependency_lock_path")
    role_paths = (*runner_paths, build_recipe_path, dependency_lock_path)
    if len(set(role_paths)) != len(role_paths):
        _fail("source_artifact_role_path_not_distinct", "/source_roles")

    root_descriptor = _open_repository_root(root_path)
    try:
        _validate_top_level_worktree(root_path)
        object_format = _read_object_format(root_path)
        source_commit = _read_head(root_path, object_format)
        _require_clean_worktree(root_path)

        tree_raw = _git(
            root_path,
            "ls-tree",
            "-rz",
            "--full-tree",
            "HEAD",
            path="/git/ls_tree",
        )
        index_raw = _git(
            root_path,
            "ls-files",
            "--stage",
            "-z",
            path="/git/ls_files",
        )
        tree_entries = _parse_tree(tree_raw, object_format=object_format)
        index_entries = _parse_index(index_raw, object_format=object_format)
        _validate_tree_index_match(tree_entries, index_entries)

        snapshots = _snapshot_worktree(
            root_descriptor,
            tree_entries,
            object_format=object_format,
        )
        manifest = _compile_manifest(
            object_format=object_format,
            source_commit=source_commit,
            snapshots=snapshots,
        )
        selected = _select_role_files(
            manifest,
            runner_paths=runner_paths,
            build_recipe_path=build_recipe_path,
            dependency_lock_path=dependency_lock_path,
        )

        expected_bundle = _git(
            root_path,
            "archive",
            "--format=tar",
            "HEAD",
            path="/source_bundle",
        )
        bundle_snapshot = _read_external_regular(bundle_path)
        if bundle_snapshot.data != expected_bundle:
            _fail("source_artifact_bundle_bytes_mismatch", "/source_bundle")
        _validate_tar_bundle(bundle_snapshot.data, snapshots)

        _postflight_repository(
            root_path,
            object_format=object_format,
            source_commit=source_commit,
            tree_raw=tree_raw,
            index_raw=index_raw,
        )

        runner_rows = tuple(selected[path] for path in runner_paths)
        runner_source_sha256 = canonical_hash(
            {
                "schema_version": "structural-analysis-runner-source-set.v1",
                "file_count": len(runner_rows),
                "files": [_file_payload(row) for row in runner_rows],
            }
        )
        build_row = selected[build_recipe_path]
        dependency_row = selected[dependency_lock_path]
        draft = SourceArtifactIdentityV1(
            schema_version=SOURCE_ARTIFACT_SCHEMA_VERSION_V1,
            object_format=object_format,
            source_commit=source_commit,
            source_manifest=manifest,
            source_tree_sha256=manifest.source_tree_sha256,
            source_bundle_byte_count=len(bundle_snapshot.data),
            source_bundle_sha256=bundle_snapshot.sha256,
            runner_source_paths=runner_paths,
            runner_source_sha256=runner_source_sha256,
            build_recipe_path=build_recipe_path,
            build_recipe_sha256=build_row.content_sha256,
            dependency_lock_path=dependency_lock_path,
            dependency_lock_sha256=dependency_row.content_sha256,
            identity_hash=_ZERO_HASH,
        )
        result = replace(
            draft,
            identity_hash=canonical_hash(_identity_payload(draft, include_hash=False)),
        )
        return validate_source_artifact_identity_v1(result)
    finally:
        os.close(root_descriptor)


def validate_source_artifact_identity_v1(
    identity: SourceArtifactIdentityV1,
) -> SourceArtifactIdentityV1:
    """Validate the complete immutable source identity and all derived hashes."""

    if type(identity) is not SourceArtifactIdentityV1:
        _fail("source_artifact_identity_type_invalid", "/source_artifact")
    if identity.schema_version != SOURCE_ARTIFACT_SCHEMA_VERSION_V1:
        _fail("source_artifact_schema_version_invalid", "/schema_version")
    manifest = _validate_manifest(identity.source_manifest)
    if (
        identity.object_format != manifest.object_format
        or identity.source_commit != manifest.source_commit
        or identity.source_tree_sha256 != manifest.source_tree_sha256
    ):
        _fail("source_artifact_manifest_binding_mismatch", "/source_manifest")
    if (
        type(identity.source_bundle_byte_count) is not int
        or identity.source_bundle_byte_count <= 0
    ):
        _fail("source_artifact_bundle_size_invalid", "/source_bundle_byte_count")
    _require_sha256(identity.source_bundle_sha256, "/source_bundle_sha256")

    runner_paths = _normalize_role_paths(
        identity.runner_source_paths,
        path="/runner_source_paths",
        require_nonempty=True,
    )
    if runner_paths != identity.runner_source_paths:
        _fail("source_artifact_runner_paths_noncanonical", "/runner_source_paths")
    _validate_safe_source_path(identity.build_recipe_path, "/build_recipe_path")
    _validate_safe_source_path(identity.dependency_lock_path, "/dependency_lock_path")
    role_paths = (
        *runner_paths,
        identity.build_recipe_path,
        identity.dependency_lock_path,
    )
    if len(set(role_paths)) != len(role_paths):
        _fail("source_artifact_role_path_not_distinct", "/source_roles")

    by_path = {row.path: row for row in manifest.files}
    try:
        runner_rows = tuple(by_path[path] for path in runner_paths)
        build_row = by_path[identity.build_recipe_path]
        dependency_row = by_path[identity.dependency_lock_path]
    except KeyError as exc:
        _fail("source_artifact_role_path_untracked", "/source_roles", str(exc))
    expected_runner_hash = canonical_hash(
        {
            "schema_version": "structural-analysis-runner-source-set.v1",
            "file_count": len(runner_rows),
            "files": [_file_payload(row) for row in runner_rows],
        }
    )
    if identity.runner_source_sha256 != expected_runner_hash:
        _fail("source_artifact_runner_hash_mismatch", "/runner_source_sha256")
    if identity.build_recipe_sha256 != build_row.content_sha256:
        _fail("source_artifact_build_recipe_hash_mismatch", "/build_recipe_sha256")
    if identity.dependency_lock_sha256 != dependency_row.content_sha256:
        _fail(
            "source_artifact_dependency_lock_hash_mismatch",
            "/dependency_lock_sha256",
        )
    for field_name in (
        "runner_source_sha256",
        "build_recipe_sha256",
        "dependency_lock_sha256",
        "identity_hash",
    ):
        _require_sha256(getattr(identity, field_name), f"/{field_name}")
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        _fail("source_artifact_identity_hash_mismatch", "/identity_hash")
    return identity


def _compile_manifest(
    *,
    object_format: str,
    source_commit: str,
    snapshots: dict[str, _FileSnapshot],
) -> SourceArtifactManifestV1:
    files = tuple(
        snapshots[path].evidence
        for path in sorted(snapshots, key=lambda value: value.encode("utf-8"))
    )
    draft = SourceArtifactManifestV1(
        schema_version=SOURCE_ARTIFACT_MANIFEST_SCHEMA_VERSION_V1,
        object_format=object_format,
        source_commit=source_commit,
        file_count=len(files),
        files=files,
        source_tree_sha256=_ZERO_HASH,
    )
    result = replace(
        draft,
        source_tree_sha256=canonical_hash(
            _manifest_payload(draft, include_hash=False, include_commit=False)
        ),
    )
    return _validate_manifest(result)


def _validate_manifest(
    manifest: SourceArtifactManifestV1,
) -> SourceArtifactManifestV1:
    if type(manifest) is not SourceArtifactManifestV1:
        _fail("source_artifact_manifest_type_invalid", "/source_manifest")
    if manifest.schema_version != SOURCE_ARTIFACT_MANIFEST_SCHEMA_VERSION_V1:
        _fail(
            "source_artifact_manifest_schema_invalid",
            "/source_manifest/schema_version",
        )
    _validate_object_format(manifest.object_format)
    _validate_oid(
        manifest.source_commit,
        object_format=manifest.object_format,
        path="/source_manifest/source_commit",
    )
    if type(manifest.files) is not tuple or not manifest.files:
        _fail("source_artifact_manifest_files_invalid", "/source_manifest/files")
    if type(manifest.file_count) is not int or manifest.file_count != len(
        manifest.files
    ):
        _fail(
            "source_artifact_manifest_file_count_invalid",
            "/source_manifest/file_count",
        )
    paths: list[str] = []
    for index, row in enumerate(manifest.files):
        _validate_file(
            row,
            object_format=manifest.object_format,
            path=f"/source_manifest/files/{index}",
        )
        paths.append(row.path)
    expected_order = sorted(paths, key=lambda value: value.encode("utf-8"))
    if paths != expected_order:
        _fail("source_artifact_manifest_order_invalid", "/source_manifest/files")
    _validate_path_namespace(paths, path="/source_manifest/files")
    _require_sha256(manifest.source_tree_sha256, "/source_tree_sha256")
    expected_hash = canonical_hash(
        _manifest_payload(manifest, include_hash=False, include_commit=False)
    )
    if manifest.source_tree_sha256 != expected_hash:
        _fail("source_artifact_tree_hash_mismatch", "/source_tree_sha256")
    return manifest


def _validate_file(
    row: SourceArtifactFileV1,
    *,
    object_format: str | None,
    path: str,
) -> None:
    if type(row) is not SourceArtifactFileV1:
        _fail("source_artifact_file_type_invalid", path)
    _validate_safe_source_path(row.path, f"{path}/path")
    if type(row.git_mode) is not str or _GIT_MODE_RE.fullmatch(row.git_mode) is None:
        _fail("source_artifact_file_mode_invalid", f"{path}/git_mode")
    if type(row.byte_count) is not int or row.byte_count < 0:
        _fail("source_artifact_file_size_invalid", f"{path}/byte_count")
    if object_format is None:
        if type(row.git_blob_oid) is not str or not any(
            re.fullmatch(rf"[0-9a-f]{{{length}}}", row.git_blob_oid)
            for length in _GIT_OBJECT_FORMATS.values()
        ):
            _fail("source_artifact_git_oid_invalid", f"{path}/git_blob_oid")
    else:
        _validate_oid(
            row.git_blob_oid,
            object_format=object_format,
            path=f"{path}/git_blob_oid",
        )
    _require_sha256(row.content_sha256, f"{path}/content_sha256")


def _snapshot_worktree(
    root_descriptor: int,
    entries: tuple[_GitEntry, ...],
    *,
    object_format: str,
) -> dict[str, _FileSnapshot]:
    snapshots: dict[str, _FileSnapshot] = {}
    inode_paths: dict[tuple[int, int], str] = {}
    for index, entry in enumerate(entries):
        expected_permissions = 0o755 if entry.mode == "100755" else 0o644
        read = _read_regular_at(
            root_descriptor,
            entry.path,
            expected_permissions=expected_permissions,
            path=f"/source_manifest/files/{index}",
        )
        inode_key = (read.device, read.inode)
        if inode_key in inode_paths:
            _fail(
                "source_artifact_worktree_hardlink_alias",
                f"/source_manifest/files/{index}",
            )
        inode_paths[inode_key] = entry.path
        blob_hasher = hashlib.new(object_format)
        blob_hasher.update(f"blob {len(read.data)}\0".encode("ascii"))
        blob_hasher.update(read.data)
        if blob_hasher.hexdigest() != entry.oid:
            _fail(
                "source_artifact_worktree_blob_mismatch",
                f"/source_manifest/files/{index}",
            )
        evidence = SourceArtifactFileV1(
            path=entry.path,
            git_mode=entry.mode,
            byte_count=len(read.data),
            git_blob_oid=entry.oid,
            content_sha256=read.sha256,
        )
        snapshots[entry.path] = _FileSnapshot(evidence=evidence, data=read.data)
    return snapshots


def _select_role_files(
    manifest: SourceArtifactManifestV1,
    *,
    runner_paths: tuple[str, ...],
    build_recipe_path: str,
    dependency_lock_path: str,
) -> dict[str, SourceArtifactFileV1]:
    by_path = {row.path: row for row in manifest.files}
    selected: dict[str, SourceArtifactFileV1] = {}
    for role_path in (*runner_paths, build_recipe_path, dependency_lock_path):
        try:
            selected[role_path] = by_path[role_path]
        except KeyError:
            _fail("source_artifact_role_path_untracked", "/source_roles", role_path)
    return selected


def _validate_tar_bundle(
    bundle: bytes,
    snapshots: dict[str, _FileSnapshot],
) -> None:
    expected_files = set(snapshots)
    expected_directories = {
        "/".join(parts[:index])
        for path in expected_files
        for parts in (path.split("/"),)
        for index in range(1, len(parts))
    }
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    folded_members: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:") as archive:
            for index, member in enumerate(archive):
                raw_name = member.name
                if member.isdir() and raw_name.endswith("/"):
                    raw_name = raw_name[:-1]
                _validate_safe_source_path(raw_name, f"/source_bundle/members/{index}")
                folded = raw_name.casefold()
                prior = folded_members.get(folded)
                if prior is not None:
                    _fail(
                        "source_artifact_tar_member_duplicate",
                        f"/source_bundle/members/{index}",
                    )
                folded_members[folded] = raw_name
                if member.isdir():
                    if raw_name not in expected_directories or member.size != 0:
                        _fail(
                            "source_artifact_tar_directory_mismatch",
                            f"/source_bundle/members/{index}",
                        )
                    if member.mode not in {0o755, 0o775}:
                        _fail(
                            "source_artifact_tar_mode_mismatch",
                            f"/source_bundle/members/{index}/mode",
                        )
                    actual_directories.add(raw_name)
                    continue
                if not member.isfile() or raw_name not in expected_files:
                    _fail(
                        "source_artifact_tar_member_type_invalid",
                        f"/source_bundle/members/{index}",
                    )
                snapshot = snapshots[raw_name]
                expected_modes = (
                    {0o755, 0o775}
                    if snapshot.evidence.git_mode == "100755"
                    else {0o644, 0o664}
                )
                if member.mode not in expected_modes:
                    _fail(
                        "source_artifact_tar_mode_mismatch",
                        f"/source_bundle/members/{index}/mode",
                    )
                if member.size != len(snapshot.data):
                    _fail(
                        "source_artifact_tar_size_mismatch",
                        f"/source_bundle/members/{index}/size",
                    )
                extracted = archive.extractfile(member)
                if extracted is None or extracted.read() != snapshot.data:
                    _fail(
                        "source_artifact_tar_bytes_mismatch",
                        f"/source_bundle/members/{index}",
                    )
                actual_files.add(raw_name)
    except SourceArtifactV1Error:
        raise
    except (tarfile.TarError, OSError, UnicodeError) as exc:
        _fail("source_artifact_tar_invalid", "/source_bundle", type(exc).__name__)
    if actual_files != expected_files or actual_directories != expected_directories:
        _fail("source_artifact_tar_manifest_mismatch", "/source_bundle/members")


def _postflight_repository(
    root_path: str,
    *,
    object_format: str,
    source_commit: str,
    tree_raw: bytes,
    index_raw: bytes,
) -> None:
    if _read_object_format(root_path) != object_format:
        _fail("source_artifact_repository_changed", "/git/object_format")
    if _read_head(root_path, object_format) != source_commit:
        _fail("source_artifact_repository_changed", "/git/HEAD")
    _require_clean_worktree(root_path)
    if (
        _git(
            root_path,
            "ls-tree",
            "-rz",
            "--full-tree",
            "HEAD",
            path="/git/ls_tree",
        )
        != tree_raw
    ):
        _fail("source_artifact_repository_changed", "/git/ls_tree")
    if (
        _git(
            root_path,
            "ls-files",
            "--stage",
            "-z",
            path="/git/ls_files",
        )
        != index_raw
    ):
        _fail("source_artifact_repository_changed", "/git/ls_files")


def _require_clean_worktree(root_path: str) -> None:
    status = _git(
        root_path,
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--ignored=matching",
        "--ignore-submodules=none",
        path="/git/status",
    )
    if status:
        _fail("source_artifact_worktree_not_clean", "/git/status")


def _parse_tree(raw: bytes, *, object_format: str) -> tuple[_GitEntry, ...]:
    entries: list[_GitEntry] = []
    for index, record in enumerate(_z_records(raw, "/git/ls_tree")):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode_raw, kind_raw, oid_raw = metadata.split(b" ")
            mode = mode_raw.decode("ascii", errors="strict")
            kind = kind_raw.decode("ascii", errors="strict")
            oid = oid_raw.decode("ascii", errors="strict")
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeError) as exc:
            _fail(
                "source_artifact_tree_record_invalid",
                f"/git/ls_tree/{index}",
                type(exc).__name__,
            )
        _validate_safe_source_path(path, f"/git/ls_tree/{index}/path")
        if kind != "blob" or _GIT_MODE_RE.fullmatch(mode) is None:
            _fail(
                "source_artifact_tree_entry_not_regular",
                f"/git/ls_tree/{index}",
            )
        _validate_oid(
            oid, object_format=object_format, path=f"/git/ls_tree/{index}/oid"
        )
        entries.append(_GitEntry(path=path, mode=mode, oid=oid))
    if not entries:
        _fail("source_artifact_tree_empty", "/git/ls_tree")
    _validate_entry_uniqueness(entries, path="/git/ls_tree")
    return tuple(entries)


def _parse_index(raw: bytes, *, object_format: str) -> tuple[_GitEntry, ...]:
    entries: list[_GitEntry] = []
    for index, record in enumerate(_z_records(raw, "/git/ls_files")):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode_raw, oid_raw, stage_raw = metadata.split(b" ")
            mode = mode_raw.decode("ascii", errors="strict")
            oid = oid_raw.decode("ascii", errors="strict")
            stage = stage_raw.decode("ascii", errors="strict")
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeError) as exc:
            _fail(
                "source_artifact_index_record_invalid",
                f"/git/ls_files/{index}",
                type(exc).__name__,
            )
        _validate_safe_source_path(path, f"/git/ls_files/{index}/path")
        if stage != "0" or _GIT_MODE_RE.fullmatch(mode) is None:
            _fail(
                "source_artifact_index_entry_not_regular",
                f"/git/ls_files/{index}",
            )
        _validate_oid(
            oid, object_format=object_format, path=f"/git/ls_files/{index}/oid"
        )
        entries.append(_GitEntry(path=path, mode=mode, oid=oid))
    if not entries:
        _fail("source_artifact_index_empty", "/git/ls_files")
    _validate_entry_uniqueness(entries, path="/git/ls_files")
    return tuple(entries)


def _validate_tree_index_match(
    tree_entries: tuple[_GitEntry, ...],
    index_entries: tuple[_GitEntry, ...],
) -> None:
    tree = {entry.path: (entry.mode, entry.oid) for entry in tree_entries}
    index = {entry.path: (entry.mode, entry.oid) for entry in index_entries}
    if tree != index:
        _fail("source_artifact_tree_index_mismatch", "/git/ls_files")


def _validate_entry_uniqueness(entries: Sequence[_GitEntry], *, path: str) -> None:
    paths = [entry.path for entry in entries]
    if len(paths) != len(set(paths)):
        _fail("source_artifact_path_duplicate", path)
    _validate_path_namespace(paths, path=path)


def _validate_path_namespace(paths: Sequence[str], *, path: str) -> None:
    folded_files: dict[str, str] = {}
    folded_directories: dict[str, str] = {}
    for source_path in paths:
        _validate_safe_source_path(source_path, path)
        parts = source_path.split("/")
        folded_path = source_path.casefold()
        prior = folded_files.get(folded_path)
        if prior is not None and prior != source_path:
            _fail("source_artifact_path_casefold_collision", path)
        if folded_path in folded_directories:
            _fail("source_artifact_path_namespace_collision", path)
        folded_files[folded_path] = source_path
        for index in range(1, len(parts)):
            directory = "/".join(parts[:index])
            folded_directory = directory.casefold()
            if folded_directory in folded_files:
                _fail("source_artifact_path_namespace_collision", path)
            prior_directory = folded_directories.get(folded_directory)
            if prior_directory is not None and prior_directory != directory:
                _fail("source_artifact_path_casefold_collision", path)
            folded_directories[folded_directory] = directory


def _validate_safe_source_path(value: str, path: str) -> None:
    if type(value) is not str or not value:
        _fail("source_artifact_path_invalid", path)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        _fail("source_artifact_path_utf8_invalid", path, type(exc).__name__)
    if unicodedata.normalize("NFC", value) != value:
        _fail("source_artifact_path_not_nfc", path)
    if (
        value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or "//" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail("source_artifact_path_unsafe", path)


def _normalize_role_paths(
    values: Sequence[str],
    *,
    path: str,
    require_nonempty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("source_artifact_runner_paths_type_invalid", path)
    normalized = tuple(values)
    if require_nonempty and not normalized:
        _fail("source_artifact_runner_paths_empty", path)
    for index, value in enumerate(normalized):
        _validate_safe_source_path(value, f"{path}/{index}")
    if len(normalized) != len(set(normalized)):
        _fail("source_artifact_runner_path_duplicate", path)
    _validate_path_namespace(normalized, path=path)
    expected = tuple(sorted(normalized, key=lambda value: value.encode("utf-8")))
    return expected


def _read_regular_at(
    root_descriptor: int,
    source_path: str,
    *,
    expected_permissions: int,
    path: str,
) -> _ReadSnapshot:
    descriptors: list[int] = []
    current = root_descriptor
    flags_directory = _open_flags(directory=True)
    flags_file = _open_flags(directory=False)
    try:
        parts = source_path.split("/")
        for component in parts[:-1]:
            descriptor = os.open(component, flags_directory, dir_fd=current)
            descriptors.append(descriptor)
            current = descriptor
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                _fail("source_artifact_parent_not_directory", path)
        descriptor = os.open(parts[-1], flags_file, dir_fd=current)
        descriptors.append(descriptor)
        return _read_stable_fd(
            descriptor,
            expected_permissions=expected_permissions,
            path=path,
        )
    except SourceArtifactV1Error:
        raise
    except OSError as exc:
        _fail("source_artifact_open_failed", path, type(exc).__name__)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_external_regular(path_value: str) -> _ReadSnapshot:
    absolute = os.path.abspath(path_value)
    parts = [part for part in absolute.split(os.sep) if part]
    if not parts:
        _fail("source_artifact_bundle_path_invalid", "/source_bundle_path")
    descriptors: list[int] = []
    try:
        current = os.open(os.sep, _open_flags(directory=True))
        descriptors.append(current)
        for component in parts[:-1]:
            descriptor = os.open(
                component,
                _open_flags(directory=True),
                dir_fd=current,
            )
            descriptors.append(descriptor)
            current = descriptor
        descriptor = os.open(
            parts[-1],
            _open_flags(directory=False),
            dir_fd=current,
        )
        descriptors.append(descriptor)
        return _read_stable_fd(
            descriptor,
            expected_permissions=None,
            path="/source_bundle",
        )
    except SourceArtifactV1Error:
        raise
    except OSError as exc:
        _fail(
            "source_artifact_bundle_open_failed", "/source_bundle", type(exc).__name__
        )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_stable_fd(
    descriptor: int,
    *,
    expected_permissions: int | None,
    path: str,
) -> _ReadSnapshot:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        _fail("source_artifact_not_regular", path)
    if (
        expected_permissions is not None
        and stat.S_IMODE(before.st_mode) != expected_permissions
    ):
        _fail("source_artifact_worktree_mode_mismatch", path)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, _READ_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
        chunks.append(chunk)
    data = b"".join(chunks)
    after = os.fstat(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or len(data) != before.st_size:
        _fail("source_artifact_file_changed_during_read", path)
    return _ReadSnapshot(
        data=data,
        sha256=f"sha256:{digest.hexdigest()}",
        device=int(before.st_dev),
        inode=int(before.st_ino),
    )


def _open_repository_root(root_path: str) -> int:
    try:
        descriptor = os.open(root_path, _open_flags(directory=True))
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            _fail("source_artifact_repository_not_directory", "/repository_root")
        return descriptor
    except SourceArtifactV1Error:
        raise
    except OSError as exc:
        _fail(
            "source_artifact_repository_open_failed",
            "/repository_root",
            type(exc).__name__,
        )


def _open_flags(*, directory: bool) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        _fail("source_artifact_secure_open_unsupported", "/platform")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= os.O_DIRECTORY
    else:
        flags |= getattr(os, "O_NONBLOCK", 0)
    return flags


def _validate_top_level_worktree(root_path: str) -> None:
    if (
        _git(
            root_path,
            "rev-parse",
            "--is-inside-work-tree",
            path="/git/worktree",
        )
        != b"true\n"
    ):
        _fail("source_artifact_not_worktree", "/repository_root")
    if (
        _git(
            root_path,
            "rev-parse",
            "--is-bare-repository",
            path="/git/worktree",
        )
        != b"false\n"
    ):
        _fail("source_artifact_bare_repository", "/repository_root")
    if (
        _git(
            root_path,
            "rev-parse",
            "--show-prefix",
            path="/git/worktree",
        )
        != b"\n"
    ):
        _fail("source_artifact_repository_root_not_top_level", "/repository_root")


def _read_object_format(root_path: str) -> str:
    value = _git_line(
        root_path,
        "rev-parse",
        "--show-object-format",
        path="/git/object_format",
    )
    _validate_object_format(value)
    return value


def _validate_object_format(value: str) -> None:
    if type(value) is not str or value not in _GIT_OBJECT_FORMATS:
        _fail("source_artifact_object_format_invalid", "/object_format")


def _read_head(root_path: str, object_format: str) -> str:
    value = _git_line(
        root_path,
        "rev-parse",
        "--verify",
        "HEAD^{commit}",
        path="/git/HEAD",
    )
    _validate_oid(value, object_format=object_format, path="/git/HEAD")
    return value


def _validate_oid(value: str, *, object_format: str, path: str) -> None:
    length = _GIT_OBJECT_FORMATS.get(object_format)
    if (
        length is None
        or type(value) is not str
        or re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None
    ):
        _fail("source_artifact_git_oid_invalid", path)


def _require_sha256(value: str, path: str) -> None:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail("source_artifact_sha256_invalid", path)


def _git_line(root_path: str, *arguments: str, path: str) -> str:
    raw = _git(root_path, *arguments, path=path)
    if not raw.endswith(b"\n") or b"\n" in raw[:-1] or b"\r" in raw:
        _fail("source_artifact_git_line_invalid", path)
    try:
        return raw[:-1].decode("ascii", errors="strict")
    except UnicodeError as exc:
        _fail("source_artifact_git_line_invalid", path, type(exc).__name__)


def _git(root_path: str, *arguments: str, path: str) -> bytes:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
        }
    )
    try:
        completed = subprocess.run(
            ("git", "--no-pager", *arguments),
            cwd=root_path,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _fail("source_artifact_git_command_failed", path, type(exc).__name__)
    if completed.returncode != 0:
        _fail(
            "source_artifact_git_command_failed",
            path,
            f"exit_{completed.returncode}",
        )
    return completed.stdout


def _z_records(raw: bytes, path: str) -> tuple[bytes, ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\0"):
        _fail("source_artifact_git_z_stream_invalid", path)
    records = tuple(raw[:-1].split(b"\0"))
    if any(not record for record in records):
        _fail("source_artifact_git_z_stream_invalid", path)
    return records


def _path_argument(value: str | os.PathLike[str], path: str) -> str:
    try:
        result = os.fspath(value)
    except TypeError as exc:
        _fail("source_artifact_path_argument_invalid", path, type(exc).__name__)
    if type(result) is not str or not result or "\0" in result:
        _fail("source_artifact_path_argument_invalid", path)
    return result


def _file_payload(row: SourceArtifactFileV1) -> dict[str, Any]:
    return {
        "path": row.path,
        "git_mode": row.git_mode,
        "byte_count": row.byte_count,
        "git_blob_oid": row.git_blob_oid,
        "content_sha256": row.content_sha256,
    }


def _manifest_payload(
    manifest: SourceArtifactManifestV1,
    *,
    include_hash: bool,
    include_commit: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": manifest.schema_version,
        "object_format": manifest.object_format,
        "file_count": manifest.file_count,
        "files": [_file_payload(row) for row in manifest.files],
    }
    if include_commit:
        payload["source_commit"] = manifest.source_commit
    if include_hash:
        payload["source_tree_sha256"] = manifest.source_tree_sha256
    return payload


def _identity_payload(
    identity: SourceArtifactIdentityV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "object_format": identity.object_format,
        "source_commit": identity.source_commit,
        "source_manifest": _manifest_payload(
            identity.source_manifest,
            include_hash=True,
        ),
        "source_tree_sha256": identity.source_tree_sha256,
        "source_bundle_byte_count": identity.source_bundle_byte_count,
        "source_bundle_sha256": identity.source_bundle_sha256,
        "runner_source_paths": list(identity.runner_source_paths),
        "runner_source_sha256": identity.runner_source_sha256,
        "build_recipe_path": identity.build_recipe_path,
        "build_recipe_sha256": identity.build_recipe_sha256,
        "dependency_lock_path": identity.dependency_lock_path,
        "dependency_lock_sha256": identity.dependency_lock_sha256,
    }
    if include_hash:
        payload["identity_hash"] = identity.identity_hash
    return payload


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise SourceArtifactV1Error(code, path, message)


__all__ = [
    "SOURCE_ARTIFACT_MANIFEST_SCHEMA_VERSION_V1",
    "SOURCE_ARTIFACT_SCHEMA_VERSION_V1",
    "SourceArtifactFileV1",
    "SourceArtifactIdentityV1",
    "SourceArtifactManifestV1",
    "SourceArtifactV1Error",
    "compile_source_artifact_identity_v1",
    "validate_source_artifact_identity_v1",
]
