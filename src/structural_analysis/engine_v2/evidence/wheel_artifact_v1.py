"""Fail-closed identity and installed-root replay for Python wheel artifacts.

The inspector hashes and parses one already-open file descriptor.  It never
reopens a wheel by pathname while deriving its identity.  Archive members,
``RECORD``, core metadata, the filename, and wheel tags are mutually checked
before an immutable identity is returned.

``Requires-Dist`` values are canonicalized with :mod:`packaging` and retained
in their original ``METADATA`` order.  That makes the identity suitable as the
input to a separately policy-bound dependency-closure verifier.
"""

from __future__ import annotations

import base64
import csv
from configparser import ConfigParser, Error as ConfigParserError
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
import errno
import hashlib
import io
import os
from pathlib import PurePosixPath
import re
import stat
import struct
from typing import Any, BinaryIO, NoReturn
import unicodedata
from zipfile import BadZipFile, LargeZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from packaging.requirements import InvalidRequirement, Requirement
from packaging.tags import parse_tag
from packaging.utils import (
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)


WHEEL_ARTIFACT_SCHEMA_VERSION_V1 = "structural-analysis-wheel-artifact.v1"
INSTALLED_WHEEL_REPLAY_SCHEMA_VERSION_V1 = (
    "structural-analysis-installed-wheel-replay.v1"
)

# These bounds are part of the verifier contract, not caller-selectable knobs.
WHEEL_ARTIFACT_MAX_ARCHIVE_BYTES_V1 = 512 * 1024 * 1024
WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1 = 65_535
WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1 = 256 * 1024 * 1024
WHEEL_ARTIFACT_MAX_UNCOMPRESSED_BYTES_V1 = 1024 * 1024 * 1024
WHEEL_ARTIFACT_MAX_COMPRESSION_RATIO_V1 = 1000
WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1 = 2 * 1024 * 1024
WHEEL_ARTIFACT_MAX_RECORD_BYTES_V1 = 16 * 1024 * 1024
WHEEL_ARTIFACT_MAX_PATH_BYTES_V1 = 4096
WHEEL_ARTIFACT_MAX_EXTRA_FILES_V1 = 65_536

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECORD_HASH_RE = re.compile(r"^sha256=([A-Za-z0-9_-]{43})$")
_SIZE_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_WHEEL_FILENAME_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.]+)-"
    r"(?P<version>[A-Za-z0-9_.+!]+)"
    r"(?:-(?P<build>[0-9][A-Za-z0-9_.]*))?-"
    r"(?P<python>[A-Za-z0-9_.]+)-"
    r"(?P<abi>[A-Za-z0-9_.]+)-"
    r"(?P<platform>[A-Za-z0-9_.]+)\.whl$"
)
_TAG_RE = re.compile(r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CHUNK_BYTES = 1024 * 1024
_MAX_CENTRAL_DIRECTORY_BYTES = 128 * 1024 * 1024

WHEEL_ARTIFACT_STABLE_ERROR_CODES_V1 = frozenset(
    {
        "installed_record_extra_limit_exceeded",
        "installed_record_hash_mismatch",
        "installed_record_invalid",
        "installed_record_member_mismatch",
        "installed_record_missing",
        "installed_record_path_escape",
        "installed_root_invalid",
        "installed_root_mutated",
        "installed_root_open_failed",
        "installed_root_path_replaced",
        "installed_root_symlink_forbidden",
        "installed_scripts_root_missing",
        "installed_wheel_file_hash_mismatch",
        "installed_wheel_file_missing",
        "installed_wheel_file_not_regular",
        "installed_wheel_file_size_mismatch",
        "installed_wheel_file_symlink_forbidden",
        "installed_wheel_replay_hash_mismatch",
        "installed_wheel_replay_semantics_invalid",
        "installed_wheel_replay_type_invalid",
        "wheel_archive_absolute_path",
        "wheel_archive_backslash_forbidden",
        "wheel_archive_casefold_collision",
        "wheel_archive_compression_ratio_exceeded",
        "wheel_archive_compression_unsupported",
        "wheel_archive_encrypted_member",
        "wheel_archive_invalid",
        "wheel_archive_local_header_mismatch",
        "wheel_archive_member_count_exceeded",
        "wheel_archive_member_duplicate",
        "wheel_archive_member_name_invalid",
        "wheel_archive_member_read_failed",
        "wheel_archive_member_size_mismatch",
        "wheel_archive_member_too_large",
        "wheel_archive_nfc_invalid",
        "wheel_archive_non_regular_member",
        "wheel_archive_nul_forbidden",
        "wheel_archive_path_traversal",
        "wheel_archive_path_prefix_collision",
        "wheel_archive_symlink_forbidden",
        "wheel_archive_uncompressed_limit_exceeded",
        "wheel_artifact_argument_invalid",
        "wheel_artifact_hash_mismatch",
        "wheel_artifact_mutated",
        "wheel_artifact_not_regular",
        "wheel_artifact_open_failed",
        "wheel_artifact_path_replaced",
        "wheel_artifact_secure_open_unsupported",
        "wheel_artifact_symlink_forbidden",
        "wheel_artifact_too_large",
        "wheel_dist_info_invalid",
        "wheel_filename_invalid",
        "wheel_identity_hash_mismatch",
        "wheel_identity_schema_invalid",
        "wheel_identity_semantics_invalid",
        "wheel_identity_type_invalid",
        "wheel_metadata_dependency_invalid",
        "wheel_metadata_duplicate",
        "wheel_metadata_invalid",
        "wheel_metadata_missing",
        "wheel_metadata_name_mismatch",
        "wheel_metadata_version_mismatch",
        "wheel_record_duplicate",
        "wheel_record_hash_invalid",
        "wheel_record_hash_mismatch",
        "wheel_record_invalid",
        "wheel_record_member_set_mismatch",
        "wheel_record_row_invalid",
        "wheel_record_self_invalid",
        "wheel_record_size_invalid",
        "wheel_record_size_mismatch",
        "wheel_tag_mismatch",
    }
)


class WheelArtifactV1Error(RuntimeError):
    """A stable, bounded, fail-closed wheel verifier error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        if code not in WHEEL_ARTIFACT_STABLE_ERROR_CODES_V1:
            raise ValueError(f"Unknown wheel-artifact error code: {code}")
        if type(path) is not str or not path.startswith("/"):
            raise ValueError("Wheel-artifact error paths must be JSON pointers.")
        self.code = code
        self.path = path
        self.message = _bounded_message(message or code)
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class WheelArtifactMemberIdentityV1:
    path: str
    byte_count: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class WheelArtifactIdentityV1:
    schema_version: str
    wheel_filename: str
    distribution_name: str
    canonical_distribution_name: str
    distribution_version: str
    canonical_distribution_version: str
    build_tag: str | None
    wheel_tags: tuple[str, ...]
    requires_dist: tuple[str, ...]
    console_scripts: tuple[str, ...]
    gui_scripts: tuple[str, ...]
    byte_count: int
    sha256: str
    dist_info_directory: str
    metadata_path: str
    wheel_metadata_path: str
    record_path: str
    metadata_sha256: str
    wheel_metadata_sha256: str
    record_sha256: str
    member_count: int
    uncompressed_byte_count: int
    members: tuple[WheelArtifactMemberIdentityV1, ...]
    member_manifest_sha256: str
    identity_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_wheel_artifact_identity_v1(self)
        return _identity_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class InstalledWheelReplayV1:
    schema_version: str
    wheel_identity: WheelArtifactIdentityV1
    installed_record_sha256: str
    verified_wheel_member_count: int
    extra_files: tuple[WheelArtifactMemberIdentityV1, ...]
    extra_file_count: int
    extra_byte_count: int
    extra_manifest_sha256: str
    script_files: tuple[InstalledWheelScriptIdentityV1, ...]
    script_file_count: int
    script_byte_count: int
    script_manifest_sha256: str
    replay_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_installed_wheel_replay_v1(self)
        return _installed_replay_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class _RecordRow:
    path: str
    hash_field: str
    size_field: str


@dataclass(frozen=True, slots=True)
class InstalledWheelScriptIdentityV1:
    entry_point_name: str
    record_path: str
    installed_basename: str
    byte_count: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_point_name": self.entry_point_name,
            "record_path": self.record_path,
            "installed_basename": self.installed_basename,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class _StatSnapshot:
    device: int
    inode: int
    mode_type: int
    size: int
    mtime_ns: int
    ctime_ns: int


def inspect_wheel_artifact_v1(
    wheel_path: str | os.PathLike[str],
) -> WheelArtifactIdentityV1:
    """Inspect one wheel through a same-open-FD, fail-closed pipeline."""

    path = _filesystem_path(wheel_path, error_path="/wheel_path")
    filename = os.path.basename(path)
    fd = _secure_open_file(path, purpose="wheel")
    try:
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = -1
            start_fd = _stat_snapshot(os.fstat(stream.fileno()))
            start_path = _lstat_path(path, purpose="wheel")
            _validate_opened_wheel(start_fd, start_path)
            filename_fields = _parse_filename(filename)
            first_sha256, first_size = _hash_stream(stream)
            if first_size != start_fd.size:
                _fail(
                    "wheel_artifact_mutated",
                    "/wheel_path",
                    "size changed during initial hashing",
                )
            stream.seek(0)
            identity = _inspect_open_wheel(
                stream,
                filename=filename,
                filename_fields=filename_fields,
                byte_count=first_size,
                archive_sha256=first_sha256,
            )
            stream.seek(0)
            second_sha256, second_size = _hash_stream(stream)
            if (second_sha256, second_size) != (first_sha256, first_size):
                _fail(
                    "wheel_artifact_hash_mismatch",
                    "/sha256",
                    "wheel bytes changed while the archive was parsed",
                )
            end_fd = _stat_snapshot(os.fstat(stream.fileno()))
            end_path = _lstat_path(path, purpose="wheel")
            _require_same_inode(start_fd, start_path, end_path, purpose="wheel")
            if end_fd != start_fd:
                _fail(
                    "wheel_artifact_mutated",
                    "/wheel_path",
                    "open wheel stat changed during inspection",
                )
            return identity
    finally:
        if fd >= 0:
            os.close(fd)


def validate_wheel_artifact_identity_v1(identity: WheelArtifactIdentityV1) -> None:
    """Structurally validate an immutable wheel identity without filesystem I/O."""

    if type(identity) is not WheelArtifactIdentityV1:
        _fail("wheel_identity_type_invalid", "/", type(identity).__name__)
    if identity.schema_version != WHEEL_ARTIFACT_SCHEMA_VERSION_V1:
        _fail("wheel_identity_schema_invalid", "/schema_version")
    try:
        filename_fields = _parse_filename(identity.wheel_filename)
    except WheelArtifactV1Error as exc:
        _fail("wheel_identity_semantics_invalid", "/wheel_filename", exc.code)
    string_fields = (
        "distribution_name",
        "canonical_distribution_name",
        "distribution_version",
        "canonical_distribution_version",
        "dist_info_directory",
        "metadata_path",
        "wheel_metadata_path",
        "record_path",
    )
    for field in string_fields:
        value = getattr(identity, field)
        if type(value) is not str or not value:
            _fail("wheel_identity_semantics_invalid", f"/{field}")
    if identity.build_tag is not None and (
        type(identity.build_tag) is not str or not identity.build_tag
    ):
        _fail("wheel_identity_semantics_invalid", "/build_tag")
    if identity.build_tag != filename_fields["build_tag"]:
        _fail("wheel_identity_semantics_invalid", "/build_tag")
    if (
        identity.canonical_distribution_name
        != canonicalize_name(identity.distribution_name)
        or identity.canonical_distribution_name != filename_fields["name"]
    ):
        _fail("wheel_identity_semantics_invalid", "/canonical_distribution_name")
    try:
        canonical_version = str(Version(identity.distribution_version))
    except InvalidVersion:
        _fail("wheel_identity_semantics_invalid", "/distribution_version")
    if (
        identity.canonical_distribution_version != canonical_version
        or identity.canonical_distribution_version != filename_fields["version"]
    ):
        _fail(
            "wheel_identity_semantics_invalid",
            "/canonical_distribution_version",
        )
    if type(identity.wheel_tags) is not tuple or not identity.wheel_tags:
        _fail("wheel_identity_semantics_invalid", "/wheel_tags")
    if identity.wheel_tags != tuple(sorted(set(identity.wheel_tags))):
        _fail("wheel_identity_semantics_invalid", "/wheel_tags")
    if identity.wheel_tags != filename_fields["tags"]:
        _fail("wheel_identity_semantics_invalid", "/wheel_tags")
    for index, tag in enumerate(identity.wheel_tags):
        if type(tag) is not str or not _TAG_RE.fullmatch(tag):
            _fail("wheel_identity_semantics_invalid", f"/wheel_tags/{index}")
        if tuple(sorted(str(item) for item in parse_tag(tag))) != (tag,):
            _fail("wheel_identity_semantics_invalid", f"/wheel_tags/{index}")
    if type(identity.requires_dist) is not tuple:
        _fail("wheel_identity_semantics_invalid", "/requires_dist")
    canonical_requirements: list[str] = []
    for index, value in enumerate(identity.requires_dist):
        if type(value) is not str:
            _fail("wheel_identity_semantics_invalid", f"/requires_dist/{index}")
        try:
            canonical = _canonical_requirement(Requirement(value))
        except InvalidRequirement:
            _fail("wheel_identity_semantics_invalid", f"/requires_dist/{index}")
        if value != canonical:
            _fail("wheel_identity_semantics_invalid", f"/requires_dist/{index}")
        canonical_requirements.append(value)
    if len(set(canonical_requirements)) != len(canonical_requirements):
        _fail("wheel_identity_semantics_invalid", "/requires_dist")
    script_names: set[str] = set()
    for field in ("console_scripts", "gui_scripts"):
        values = getattr(identity, field)
        if type(values) is not tuple or values != tuple(sorted(values)):
            _fail("wheel_identity_semantics_invalid", f"/{field}")
        for index, value in enumerate(values):
            if type(value) is not str or not _SCRIPT_NAME_RE.fullmatch(value):
                _fail("wheel_identity_semantics_invalid", f"/{field}/{index}")
            folded = value.casefold()
            if folded in script_names:
                _fail("wheel_identity_semantics_invalid", f"/{field}/{index}")
            script_names.add(folded)
    integer_fields = (
        "byte_count",
        "member_count",
        "uncompressed_byte_count",
    )
    for field in integer_fields:
        value = getattr(identity, field)
        if type(value) is not int or value < 0:
            _fail("wheel_identity_semantics_invalid", f"/{field}")
    if not 0 < identity.byte_count <= WHEEL_ARTIFACT_MAX_ARCHIVE_BYTES_V1:
        _fail("wheel_identity_semantics_invalid", "/byte_count")
    for field in (
        "sha256",
        "metadata_sha256",
        "wheel_metadata_sha256",
        "record_sha256",
        "member_manifest_sha256",
        "identity_hash",
    ):
        if type(getattr(identity, field)) is not str or not _HASH_RE.fullmatch(
            getattr(identity, field)
        ):
            _fail("wheel_identity_semantics_invalid", f"/{field}")
    if type(identity.members) is not tuple or not identity.members:
        _fail("wheel_identity_semantics_invalid", "/members")
    if identity.member_count != len(identity.members):
        _fail("wheel_identity_semantics_invalid", "/member_count")
    if identity.member_count > WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1:
        _fail("wheel_identity_semantics_invalid", "/member_count")
    previous_path = ""
    casefold_paths: set[str] = set()
    for index, member in enumerate(identity.members):
        if type(member) is not WheelArtifactMemberIdentityV1:
            _fail("wheel_identity_semantics_invalid", f"/members/{index}")
        _validate_member_path(member.path, f"/members/{index}/path", installed=False)
        if member.path <= previous_path:
            _fail("wheel_identity_semantics_invalid", f"/members/{index}/path")
        previous_path = member.path
        folded = member.path.casefold()
        if folded in casefold_paths:
            _fail("wheel_identity_semantics_invalid", f"/members/{index}/path")
        casefold_paths.add(folded)
        if (
            type(member.byte_count) is not int
            or member.byte_count < 0
            or member.byte_count > WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1
            or type(member.sha256) is not str
            or not _HASH_RE.fullmatch(member.sha256)
        ):
            _fail("wheel_identity_semantics_invalid", f"/members/{index}")
    if (
        identity.uncompressed_byte_count
        != sum(member.byte_count for member in identity.members)
        or identity.uncompressed_byte_count > WHEEL_ARTIFACT_MAX_UNCOMPRESSED_BYTES_V1
    ):
        _fail("wheel_identity_semantics_invalid", "/uncompressed_byte_count")
    expected_dist_info = filename_fields["dist_info_directory"]
    expected_paths = (
        f"{expected_dist_info}/METADATA",
        f"{expected_dist_info}/WHEEL",
        f"{expected_dist_info}/RECORD",
    )
    if (
        identity.dist_info_directory != expected_dist_info
        or (
            identity.metadata_path,
            identity.wheel_metadata_path,
            identity.record_path,
        )
        != expected_paths
    ):
        _fail("wheel_identity_semantics_invalid", "/dist_info_directory")
    member_by_path = {member.path: member for member in identity.members}
    if not all(path in member_by_path for path in expected_paths):
        _fail("wheel_identity_semantics_invalid", "/members")
    if member_by_path[identity.metadata_path].sha256 != identity.metadata_sha256:
        _fail("wheel_identity_semantics_invalid", "/metadata_sha256")
    if (
        member_by_path[identity.metadata_path].byte_count
        > WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1
        or member_by_path[identity.wheel_metadata_path].byte_count
        > WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1
        or member_by_path[identity.record_path].byte_count
        > WHEEL_ARTIFACT_MAX_RECORD_BYTES_V1
    ):
        _fail("wheel_identity_semantics_invalid", "/members")
    if (
        member_by_path[identity.wheel_metadata_path].sha256
        != identity.wheel_metadata_sha256
    ):
        _fail("wheel_identity_semantics_invalid", "/wheel_metadata_sha256")
    if member_by_path[identity.record_path].sha256 != identity.record_sha256:
        _fail("wheel_identity_semantics_invalid", "/record_sha256")
    manifest_hash = canonical_hash([member.to_dict() for member in identity.members])
    if identity.member_manifest_sha256 != manifest_hash:
        _fail("wheel_identity_hash_mismatch", "/member_manifest_sha256")
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        _fail("wheel_identity_hash_mismatch", "/identity_hash")


def replay_installed_wheel_artifact_v1(
    *,
    wheel_path: str | os.PathLike[str],
    installed_root: str | os.PathLike[str],
    installed_scripts_root: str | os.PathLike[str] | None = None,
) -> InstalledWheelReplayV1:
    """Replay wheel files and explicitly authorized installer-created scripts.

    ``installed_scripts_root`` is required when the wheel declares console or
    GUI entry points.  Only the exact ``RECORD`` path derived from that root and
    an entry-point basename is allowed outside ``installed_root``.
    """

    identity = inspect_wheel_artifact_v1(wheel_path)
    root_path = _filesystem_path(installed_root, error_path="/installed_root")
    root_fd = _secure_open_root(root_path)
    scripts_fd = -1
    try:
        start_fd = _stat_snapshot(os.fstat(root_fd))
        start_path = _lstat_path(root_path, purpose="installed_root")
        _validate_opened_root(start_fd, start_path)
        declared_scripts = identity.console_scripts + identity.gui_scripts
        authorized_scripts: dict[str, tuple[str, str]] = {}
        scripts_path = ""
        scripts_start_fd: _StatSnapshot | None = None
        scripts_start_path: _StatSnapshot | None = None
        if declared_scripts:
            if installed_scripts_root is None:
                _fail("installed_scripts_root_missing", "/installed_scripts_root")
            scripts_path = _filesystem_path(
                installed_scripts_root,
                error_path="/installed_scripts_root",
            )
            scripts_fd = _secure_open_root(scripts_path)
            scripts_start_fd = _stat_snapshot(os.fstat(scripts_fd))
            scripts_start_path = _lstat_path(
                scripts_path,
                purpose="installed_root",
            )
            _validate_opened_root(scripts_start_fd, scripts_start_path)
            authorized_scripts = _authorized_script_record_paths(
                installed_root=root_path,
                scripts_root=scripts_path,
                entry_point_names=declared_scripts,
            )
        try:
            installed_record = _read_root_file(
                root_fd,
                identity.record_path,
                byte_limit=WHEEL_ARTIFACT_MAX_RECORD_BYTES_V1,
            )
        except WheelArtifactV1Error as exc:
            if exc.code == "installed_wheel_file_missing":
                _fail("installed_record_missing", "/installed_record", exc.message)
            raise
        installed_rows = _parse_record(
            installed_record,
            record_path=identity.record_path,
            installed=True,
            allowed_external_paths=frozenset(authorized_scripts),
            max_rows=(
                identity.member_count
                + WHEEL_ARTIFACT_MAX_EXTRA_FILES_V1
                + len(authorized_scripts)
            ),
        )
        installed_by_path = {row.path: row for row in installed_rows}
        expected_by_path = {member.path: member for member in identity.members}
        missing = sorted(set(expected_by_path) - set(installed_by_path))
        if missing:
            _fail(
                "installed_record_member_mismatch",
                "/installed_record",
                f"missing wheel row {missing[0]}",
            )
        verified_count = 0
        for member in identity.members:
            row = installed_by_path[member.path]
            if member.path == identity.record_path:
                if row.hash_field or row.size_field:
                    _fail(
                        "installed_record_member_mismatch",
                        "/installed_record",
                        "RECORD self row must remain empty",
                    )
                continue
            expected_hash = _record_hash_from_prefixed(member.sha256)
            if row.hash_field != expected_hash or row.size_field != str(
                member.byte_count
            ):
                _fail(
                    "installed_record_member_mismatch",
                    "/installed_record",
                    f"wheel row changed: {member.path}",
                )
            data = _read_root_file(
                root_fd,
                member.path,
                byte_limit=member.byte_count,
            )
            actual_hash = sha256_prefixed(data)
            if len(data) != member.byte_count:
                _fail(
                    "installed_wheel_file_size_mismatch",
                    f"/installed/{member.path}",
                )
            if actual_hash != member.sha256:
                _fail(
                    "installed_wheel_file_hash_mismatch",
                    f"/installed/{member.path}",
                )
            verified_count += 1
        all_extra_paths = set(installed_by_path) - set(expected_by_path)
        script_paths = sorted(all_extra_paths & set(authorized_scripts))
        represented_entry_points = {
            authorized_scripts[path][0].casefold() for path in script_paths
        }
        if represented_entry_points != {name.casefold() for name in declared_scripts}:
            _fail(
                "installed_record_member_mismatch",
                "/installed_record",
                "declared entry-point scripts are missing",
            )
        script_files: list[InstalledWheelScriptIdentityV1] = []
        for path in script_paths:
            row = installed_by_path[path]
            entry_point_name, basename = authorized_scripts[path]
            data = _read_root_file(
                scripts_fd,
                basename,
                byte_limit=WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1,
            )
            digest = sha256_prefixed(data)
            _verify_installed_extra_row(row, digest=digest, byte_count=len(data))
            script_files.append(
                InstalledWheelScriptIdentityV1(
                    entry_point_name=entry_point_name,
                    record_path=path,
                    installed_basename=basename,
                    byte_count=len(data),
                    sha256=digest,
                )
            )
        script_tuple = tuple(script_files)
        extra_paths = sorted(all_extra_paths - set(script_paths))
        if len(extra_paths) > WHEEL_ARTIFACT_MAX_EXTRA_FILES_V1:
            _fail(
                "installed_record_extra_limit_exceeded",
                "/installed_record",
            )
        extras: list[WheelArtifactMemberIdentityV1] = []
        for path in extra_paths:
            row = installed_by_path[path]
            data = _read_root_file(
                root_fd,
                path,
                byte_limit=WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1,
            )
            digest = sha256_prefixed(data)
            _verify_installed_extra_row(row, digest=digest, byte_count=len(data))
            extras.append(
                WheelArtifactMemberIdentityV1(
                    path=path,
                    byte_count=len(data),
                    sha256=digest,
                )
            )
        extra_tuple = tuple(extras)
        replay = InstalledWheelReplayV1(
            schema_version=INSTALLED_WHEEL_REPLAY_SCHEMA_VERSION_V1,
            wheel_identity=identity,
            installed_record_sha256=sha256_prefixed(installed_record),
            verified_wheel_member_count=verified_count,
            extra_files=extra_tuple,
            extra_file_count=len(extra_tuple),
            extra_byte_count=sum(item.byte_count for item in extra_tuple),
            extra_manifest_sha256=canonical_hash(
                [item.to_dict() for item in extra_tuple]
            ),
            script_files=script_tuple,
            script_file_count=len(script_tuple),
            script_byte_count=sum(item.byte_count for item in script_tuple),
            script_manifest_sha256=canonical_hash(
                [item.to_dict() for item in script_tuple]
            ),
            replay_hash="",
        )
        replay = InstalledWheelReplayV1(
            **{
                **_installed_replay_constructor_payload(replay),
                "replay_hash": canonical_hash(
                    _installed_replay_payload(replay, include_hash=False)
                ),
            }
        )
        validate_installed_wheel_replay_v1(replay)
        end_fd = _stat_snapshot(os.fstat(root_fd))
        end_path = _lstat_path(root_path, purpose="installed_root")
        if end_fd != start_fd:
            _fail("installed_root_mutated", "/installed_root")
        _require_same_inode(
            start_fd,
            start_path,
            end_path,
            purpose="installed_root",
        )
        if (
            scripts_fd >= 0
            and scripts_start_fd is not None
            and scripts_start_path is not None
        ):
            scripts_end_fd = _stat_snapshot(os.fstat(scripts_fd))
            scripts_end_path = _lstat_path(
                scripts_path,
                purpose="installed_root",
            )
            if scripts_end_fd != scripts_start_fd:
                _fail("installed_root_mutated", "/installed_scripts_root")
            _require_same_inode(
                scripts_start_fd,
                scripts_start_path,
                scripts_end_path,
                purpose="installed_root",
            )
        return replay
    finally:
        if scripts_fd >= 0:
            os.close(scripts_fd)
        os.close(root_fd)


def validate_installed_wheel_replay_v1(replay: InstalledWheelReplayV1) -> None:
    """Structurally validate an installed-wheel replay receipt."""

    if type(replay) is not InstalledWheelReplayV1:
        _fail("installed_wheel_replay_type_invalid", "/", type(replay).__name__)
    if replay.schema_version != INSTALLED_WHEEL_REPLAY_SCHEMA_VERSION_V1:
        _fail("installed_wheel_replay_semantics_invalid", "/schema_version")
    validate_wheel_artifact_identity_v1(replay.wheel_identity)
    if type(replay.installed_record_sha256) is not str or not _HASH_RE.fullmatch(
        replay.installed_record_sha256
    ):
        _fail(
            "installed_wheel_replay_semantics_invalid",
            "/installed_record_sha256",
        )
    expected_verified = replay.wheel_identity.member_count - 1
    if (
        type(replay.verified_wheel_member_count) is not int
        or replay.verified_wheel_member_count != expected_verified
    ):
        _fail(
            "installed_wheel_replay_semantics_invalid",
            "/verified_wheel_member_count",
        )
    if type(replay.extra_files) is not tuple:
        _fail("installed_wheel_replay_semantics_invalid", "/extra_files")
    if (
        type(replay.extra_file_count) is not int
        or replay.extra_file_count != len(replay.extra_files)
        or replay.extra_file_count > WHEEL_ARTIFACT_MAX_EXTRA_FILES_V1
    ):
        _fail("installed_wheel_replay_semantics_invalid", "/extra_file_count")
    expected_paths = {item.path.casefold() for item in replay.wheel_identity.members}
    previous_path = ""
    for index, item in enumerate(replay.extra_files):
        if type(item) is not WheelArtifactMemberIdentityV1:
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/extra_files/{index}",
            )
        _validate_member_path(
            item.path,
            f"/extra_files/{index}/path",
            installed=True,
        )
        if item.path <= previous_path or item.path.casefold() in expected_paths:
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/extra_files/{index}/path",
            )
        previous_path = item.path
        expected_paths.add(item.path.casefold())
        if (
            type(item.byte_count) is not int
            or not 0 <= item.byte_count <= WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1
            or type(item.sha256) is not str
            or not _HASH_RE.fullmatch(item.sha256)
        ):
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/extra_files/{index}",
            )
    if type(replay.extra_byte_count) is not int or replay.extra_byte_count != sum(
        item.byte_count for item in replay.extra_files
    ):
        _fail("installed_wheel_replay_semantics_invalid", "/extra_byte_count")
    manifest_hash = canonical_hash([item.to_dict() for item in replay.extra_files])
    if replay.extra_manifest_sha256 != manifest_hash:
        _fail("installed_wheel_replay_hash_mismatch", "/extra_manifest_sha256")
    if type(replay.script_files) is not tuple:
        _fail("installed_wheel_replay_semantics_invalid", "/script_files")
    if type(replay.script_file_count) is not int or replay.script_file_count != len(
        replay.script_files
    ):
        _fail("installed_wheel_replay_semantics_invalid", "/script_file_count")
    declared_scripts = {
        name.casefold()
        for name in (
            replay.wheel_identity.console_scripts + replay.wheel_identity.gui_scripts
        )
    }
    represented_scripts: set[str] = set()
    previous_script_path = ""
    for index, item in enumerate(replay.script_files):
        if type(item) is not InstalledWheelScriptIdentityV1:
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/script_files/{index}",
            )
        if (
            type(item.entry_point_name) is not str
            or item.entry_point_name.casefold() not in declared_scripts
            or type(item.installed_basename) is not str
            or not _SCRIPT_NAME_RE.fullmatch(item.installed_basename)
        ):
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/script_files/{index}",
            )
        allowed_basenames = {
            item.entry_point_name,
            f"{item.entry_point_name}.exe",
            f"{item.entry_point_name}-script.py",
            f"{item.entry_point_name}.exe.manifest",
        }
        if item.installed_basename not in allowed_basenames:
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/script_files/{index}/installed_basename",
            )
        _validate_external_record_path(
            item.record_path,
            f"/script_files/{index}/record_path",
        )
        if (
            item.record_path <= previous_script_path
            or item.record_path.casefold() in expected_paths
        ):
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/script_files/{index}/record_path",
            )
        previous_script_path = item.record_path
        expected_paths.add(item.record_path.casefold())
        represented_scripts.add(item.entry_point_name.casefold())
        if (
            type(item.byte_count) is not int
            or not 0 <= item.byte_count <= WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1
            or type(item.sha256) is not str
            or not _HASH_RE.fullmatch(item.sha256)
        ):
            _fail(
                "installed_wheel_replay_semantics_invalid",
                f"/script_files/{index}",
            )
    if represented_scripts != declared_scripts:
        _fail("installed_wheel_replay_semantics_invalid", "/script_files")
    if type(replay.script_byte_count) is not int or replay.script_byte_count != sum(
        item.byte_count for item in replay.script_files
    ):
        _fail("installed_wheel_replay_semantics_invalid", "/script_byte_count")
    script_manifest_hash = canonical_hash(
        [item.to_dict() for item in replay.script_files]
    )
    if replay.script_manifest_sha256 != script_manifest_hash:
        _fail("installed_wheel_replay_hash_mismatch", "/script_manifest_sha256")
    if type(replay.replay_hash) is not str or not _HASH_RE.fullmatch(
        replay.replay_hash
    ):
        _fail("installed_wheel_replay_semantics_invalid", "/replay_hash")
    if replay.replay_hash != canonical_hash(
        _installed_replay_payload(replay, include_hash=False)
    ):
        _fail("installed_wheel_replay_hash_mismatch", "/replay_hash")


def _inspect_open_wheel(
    stream: BinaryIO,
    *,
    filename: str,
    filename_fields: dict[str, Any],
    byte_count: int,
    archive_sha256: str,
) -> WheelArtifactIdentityV1:
    _preflight_zip_directory(stream, byte_count=byte_count)
    try:
        archive = ZipFile(stream, mode="r", allowZip64=True)
    except (BadZipFile, LargeZipFile, OSError, ValueError) as exc:
        _fail("wheel_archive_invalid", "/archive", type(exc).__name__)
    try:
        with archive:
            infos = archive.infolist()
            _validate_archive_infos(infos)
            _validate_local_headers(archive, infos)
            paths = tuple(info.filename for info in infos)
            dist_info, required_paths = _locate_dist_info(paths, filename_fields)
            entry_points_path = f"{dist_info}/entry_points.txt"
            capture_paths = set(required_paths)
            if entry_points_path in paths:
                capture_paths.add(entry_points_path)
            members: list[WheelArtifactMemberIdentityV1] = []
            selected_bytes: dict[str, bytes] = {}
            for index, info in enumerate(infos):
                capture = info.filename in capture_paths
                if (
                    info.filename == required_paths[2]
                    and info.file_size > WHEEL_ARTIFACT_MAX_RECORD_BYTES_V1
                ):
                    _fail("wheel_record_invalid", "/RECORD")
                if (
                    capture
                    and info.filename != required_paths[2]
                    and info.file_size > WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1
                ):
                    _fail("wheel_metadata_invalid", f"/archive/{info.filename}")
                data, digest, actual_size = _read_archive_member(
                    archive,
                    info,
                    index=index,
                    capture=capture,
                )
                members.append(
                    WheelArtifactMemberIdentityV1(
                        path=info.filename,
                        byte_count=actual_size,
                        sha256=digest,
                    )
                )
                if capture:
                    selected_bytes[info.filename] = data
    except WheelArtifactV1Error:
        raise
    except (BadZipFile, LargeZipFile, OSError, RuntimeError, EOFError) as exc:
        _fail("wheel_archive_member_read_failed", "/archive", type(exc).__name__)
    metadata_path, wheel_metadata_path, record_path = required_paths
    metadata = selected_bytes[metadata_path]
    wheel_metadata = selected_bytes[wheel_metadata_path]
    record = selected_bytes[record_path]
    name, canonical_name, version, canonical_version, requirements = _parse_metadata(
        metadata
    )
    if canonical_name != filename_fields["name"]:
        _fail("wheel_metadata_name_mismatch", "/METADATA/Name")
    if canonical_version != filename_fields["version"]:
        _fail("wheel_metadata_version_mismatch", "/METADATA/Version")
    wheel_tags = _parse_wheel_metadata(wheel_metadata)
    if wheel_tags != filename_fields["tags"]:
        _fail("wheel_tag_mismatch", "/WHEEL/Tag")
    console_scripts, gui_scripts = _parse_entry_points(
        selected_bytes.get(entry_points_path)
    )
    member_tuple = tuple(sorted(members, key=lambda item: item.path))
    record_rows = _parse_record(
        record,
        record_path=record_path,
        installed=False,
        max_rows=WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1,
    )
    _verify_wheel_record(record_rows, member_tuple, record_path=record_path)
    member_by_path = {member.path: member for member in member_tuple}
    identity = WheelArtifactIdentityV1(
        schema_version=WHEEL_ARTIFACT_SCHEMA_VERSION_V1,
        wheel_filename=filename,
        distribution_name=name,
        canonical_distribution_name=canonical_name,
        distribution_version=version,
        canonical_distribution_version=canonical_version,
        build_tag=filename_fields["build_tag"],
        wheel_tags=wheel_tags,
        requires_dist=requirements,
        console_scripts=console_scripts,
        gui_scripts=gui_scripts,
        byte_count=byte_count,
        sha256=archive_sha256,
        dist_info_directory=dist_info,
        metadata_path=metadata_path,
        wheel_metadata_path=wheel_metadata_path,
        record_path=record_path,
        metadata_sha256=member_by_path[metadata_path].sha256,
        wheel_metadata_sha256=member_by_path[wheel_metadata_path].sha256,
        record_sha256=member_by_path[record_path].sha256,
        member_count=len(member_tuple),
        uncompressed_byte_count=sum(item.byte_count for item in member_tuple),
        members=member_tuple,
        member_manifest_sha256=canonical_hash(
            [item.to_dict() for item in member_tuple]
        ),
        identity_hash="",
    )
    identity = WheelArtifactIdentityV1(
        **{
            **_identity_constructor_payload(identity),
            "identity_hash": canonical_hash(
                _identity_payload(identity, include_hash=False)
            ),
        }
    )
    validate_wheel_artifact_identity_v1(identity)
    return identity


def _preflight_zip_directory(stream: BinaryIO, *, byte_count: int) -> None:
    eocd_struct = struct.Struct("<4s4H2LH")
    tail_size = min(byte_count, eocd_struct.size + 65_535)
    try:
        stream.seek(byte_count - tail_size)
        tail = stream.read(tail_size)
    except (OSError, ValueError) as exc:
        _fail("wheel_archive_invalid", "/archive/eocd", type(exc).__name__)
    search_end = len(tail)
    fields: tuple[Any, ...] | None = None
    eocd_in_tail = -1
    while True:
        candidate = tail.rfind(b"PK\x05\x06", 0, search_end)
        if candidate < 0:
            break
        if candidate + eocd_struct.size <= len(tail):
            unpacked = eocd_struct.unpack_from(tail, candidate)
            comment_length = unpacked[-1]
            if candidate + eocd_struct.size + comment_length == len(tail):
                fields = unpacked
                eocd_in_tail = candidate
                break
        search_end = candidate
    if fields is None:
        _fail("wheel_archive_invalid", "/archive/eocd")
    (
        _signature,
        disk_number,
        central_disk,
        entries_on_disk,
        total_entries,
        central_size,
        central_offset,
        _comment_length,
    ) = fields
    if (
        disk_number != 0
        or central_disk != 0
        or entries_on_disk != total_entries
        or total_entries in (0, 0xFFFF)
        or central_size == 0xFFFFFFFF
        or central_offset == 0xFFFFFFFF
    ):
        _fail("wheel_archive_invalid", "/archive/eocd")
    if total_entries > WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1:
        _fail("wheel_archive_member_count_exceeded", "/archive/eocd/entry_count")
    if central_size > _MAX_CENTRAL_DIRECTORY_BYTES:
        _fail("wheel_archive_invalid", "/archive/eocd/central_directory_size")
    eocd_offset = byte_count - tail_size + eocd_in_tail
    if central_offset + central_size != eocd_offset:
        _fail("wheel_archive_invalid", "/archive/eocd/central_directory_offset")


def _validate_archive_infos(infos: list[Any]) -> None:
    if not infos or len(infos) > WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1:
        _fail("wheel_archive_member_count_exceeded", "/archive/members")
    seen: set[str] = set()
    casefold_seen: set[str] = set()
    uncompressed_total = 0
    for index, info in enumerate(infos):
        path = f"/archive/members/{index}"
        original = getattr(info, "orig_filename", info.filename)
        if "\x00" in original or original != info.filename:
            _fail("wheel_archive_nul_forbidden", f"{path}/name")
        mode = info.external_attr >> 16
        mode_type = stat.S_IFMT(mode)
        if mode_type == stat.S_IFLNK:
            _fail("wheel_archive_symlink_forbidden", path)
        if (
            info.is_dir()
            or info.external_attr & 0x10
            or mode_type not in (0, stat.S_IFREG)
        ):
            _fail("wheel_archive_non_regular_member", path)
        _validate_member_path(info.filename, f"{path}/name", installed=False)
        if info.filename in seen:
            _fail("wheel_archive_member_duplicate", f"{path}/name")
        seen.add(info.filename)
        folded = info.filename.casefold()
        if folded in casefold_seen:
            _fail("wheel_archive_casefold_collision", f"{path}/name")
        casefold_seen.add(folded)
        if info.flag_bits & 0x41:
            _fail("wheel_archive_encrypted_member", path)
        if info.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
            _fail("wheel_archive_compression_unsupported", path)
        if (
            type(info.file_size) is not int
            or info.file_size < 0
            or info.file_size > WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1
        ):
            _fail("wheel_archive_member_too_large", f"{path}/file_size")
        if type(info.compress_size) is not int or info.compress_size < 0:
            _fail("wheel_archive_invalid", f"{path}/compress_size")
        uncompressed_total += info.file_size
        if uncompressed_total > WHEEL_ARTIFACT_MAX_UNCOMPRESSED_BYTES_V1:
            _fail(
                "wheel_archive_uncompressed_limit_exceeded",
                "/archive/uncompressed_byte_count",
            )
        if info.file_size and (
            info.compress_size == 0
            or info.file_size
            > info.compress_size * WHEEL_ARTIFACT_MAX_COMPRESSION_RATIO_V1
        ):
            _fail("wheel_archive_compression_ratio_exceeded", path)
    for name in seen:
        components = name.split("/")
        for stop in range(1, len(components)):
            if "/".join(components[:stop]) in seen:
                _fail(
                    "wheel_archive_path_prefix_collision",
                    "/archive/members",
                )


def _validate_local_headers(archive: ZipFile, infos: list[Any]) -> None:
    stream = archive.fp
    if stream is None:
        _fail("wheel_archive_invalid", "/archive")
    header_struct = struct.Struct("<4s5H3L2H")
    for index, info in enumerate(infos):
        path = f"/archive/members/{index}/local_header"
        try:
            stream.seek(info.header_offset)
            header = stream.read(header_struct.size)
            if len(header) != header_struct.size:
                _fail("wheel_archive_local_header_mismatch", path)
            fields = header_struct.unpack(header)
            signature = fields[0]
            flags = fields[2]
            compression = fields[3]
            crc = fields[6]
            compressed_size = fields[7]
            uncompressed_size = fields[8]
            filename_length = fields[9]
            extra_length = fields[10]
            if signature != b"PK\x03\x04":
                _fail("wheel_archive_local_header_mismatch", path)
            if flags & 0x41:
                _fail("wheel_archive_encrypted_member", path)
            if flags != info.flag_bits or compression != info.compress_type:
                _fail("wheel_archive_local_header_mismatch", path)
            if not 0 < filename_length <= WHEEL_ARTIFACT_MAX_PATH_BYTES_V1:
                _fail("wheel_archive_local_header_mismatch", path)
            filename_bytes = stream.read(filename_length)
            extra = stream.read(extra_length)
            if len(filename_bytes) != filename_length or len(extra) != extra_length:
                _fail("wheel_archive_local_header_mismatch", path)
            try:
                filename = filename_bytes.decode(
                    "utf-8" if flags & 0x800 else "cp437",
                    errors="strict",
                )
            except UnicodeDecodeError as exc:
                _fail(
                    "wheel_archive_local_header_mismatch",
                    path,
                    type(exc).__name__,
                )
            if filename != info.orig_filename:
                _fail("wheel_archive_local_header_mismatch", path)
            if not flags & 0x8 and (
                crc != info.CRC
                or compressed_size != info.compress_size
                or uncompressed_size != info.file_size
            ):
                _fail("wheel_archive_local_header_mismatch", path)
        except WheelArtifactV1Error:
            raise
        except (OSError, ValueError, struct.error) as exc:
            _fail(
                "wheel_archive_local_header_mismatch",
                path,
                type(exc).__name__,
            )


def _read_archive_member(
    archive: ZipFile,
    info: Any,
    *,
    index: int,
    capture: bool,
) -> tuple[bytes, str, int]:
    digest = hashlib.sha256()
    size = 0
    captured = io.BytesIO() if capture else None
    try:
        with archive.open(info, mode="r") as member:
            while True:
                chunk = member.read(_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > info.file_size or size > WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1:
                    _fail(
                        "wheel_archive_member_size_mismatch",
                        f"/archive/members/{index}/file_size",
                    )
                digest.update(chunk)
                if captured is not None:
                    captured.write(chunk)
    except WheelArtifactV1Error:
        raise
    except (BadZipFile, OSError, RuntimeError, EOFError, NotImplementedError) as exc:
        _fail(
            "wheel_archive_member_read_failed",
            f"/archive/members/{index}",
            type(exc).__name__,
        )
    if size != info.file_size:
        _fail(
            "wheel_archive_member_size_mismatch",
            f"/archive/members/{index}/file_size",
        )
    return (
        b"" if captured is None else captured.getvalue(),
        f"sha256:{digest.hexdigest()}",
        size,
    )


def _locate_dist_info(
    paths: tuple[str, ...],
    filename_fields: dict[str, Any],
) -> tuple[str, tuple[str, str, str]]:
    dist_info_roots: set[str] = set()
    for path in paths:
        first = path.split("/", 1)[0]
        if first.endswith(".dist-info"):
            dist_info_roots.add(first)
        if any(part.endswith(".dist-info") for part in path.split("/")[1:]):
            _fail("wheel_dist_info_invalid", "/archive/dist_info")
    expected = filename_fields["dist_info_directory"]
    if dist_info_roots != {expected}:
        _fail(
            "wheel_dist_info_invalid",
            "/archive/dist_info",
            f"expected exactly {expected}",
        )
    required = (
        f"{expected}/METADATA",
        f"{expected}/WHEEL",
        f"{expected}/RECORD",
    )
    path_set = set(paths)
    for path in required:
        if path not in path_set:
            _fail("wheel_metadata_missing", f"/archive/{path}")
    return expected, required


def _parse_filename(filename: str) -> dict[str, Any]:
    if (
        type(filename) is not str
        or not filename
        or filename != os.path.basename(filename)
        or unicodedata.normalize("NFC", filename) != filename
        or not filename.isascii()
    ):
        _fail("wheel_filename_invalid", "/wheel_filename")
    match = _WHEEL_FILENAME_RE.fullmatch(filename)
    if match is None:
        _fail("wheel_filename_invalid", "/wheel_filename")
    try:
        name, version, build, tags = parse_wheel_filename(filename)
    except (InvalidWheelFilename, InvalidVersion, ValueError) as exc:
        _fail("wheel_filename_invalid", "/wheel_filename", type(exc).__name__)
    expanded_tags = tuple(sorted(str(tag) for tag in tags))
    if not expanded_tags or any(not _TAG_RE.fullmatch(tag) for tag in expanded_tags):
        _fail("wheel_filename_invalid", "/wheel_filename")
    build_text = match.group("build")
    if bool(build) != bool(build_text):
        _fail("wheel_filename_invalid", "/wheel_filename")
    return {
        "name": str(name),
        "version": str(version),
        "build_tag": build_text,
        "tags": expanded_tags,
        "dist_info_directory": (
            f"{match.group('name')}-{match.group('version')}.dist-info"
        ),
    }


def _parse_metadata(
    data: bytes,
) -> tuple[str, str, str, str, tuple[str, ...]]:
    message = _parse_email_metadata(
        data,
        path="/METADATA",
        byte_limit=WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1,
    )
    names = message.get_all("Name", [])
    versions = message.get_all("Version", [])
    if len(names) != 1:
        _fail(
            "wheel_metadata_missing" if not names else "wheel_metadata_duplicate",
            "/METADATA/Name",
        )
    if len(versions) != 1:
        _fail(
            "wheel_metadata_missing" if not versions else "wheel_metadata_duplicate",
            "/METADATA/Version",
        )
    name = str(names[0])
    version = str(versions[0])
    if name != name.strip() or not _NAME_RE.fullmatch(name):
        _fail("wheel_metadata_invalid", "/METADATA/Name")
    if version != version.strip() or not version or not version.isascii():
        _fail("wheel_metadata_invalid", "/METADATA/Version")
    try:
        canonical_version = str(Version(version))
    except InvalidVersion as exc:
        _fail("wheel_metadata_invalid", "/METADATA/Version", type(exc).__name__)
    canonical_name = canonicalize_name(name)
    requirements: list[str] = []
    seen: set[str] = set()
    for index, raw_requirement in enumerate(message.get_all("Requires-Dist", [])):
        value = str(raw_requirement)
        if value != value.strip() or "\x00" in value:
            _fail(
                "wheel_metadata_dependency_invalid", f"/METADATA/Requires-Dist/{index}"
            )
        try:
            requirement = _canonical_requirement(Requirement(value))
        except InvalidRequirement as exc:
            _fail(
                "wheel_metadata_dependency_invalid",
                f"/METADATA/Requires-Dist/{index}",
                type(exc).__name__,
            )
        if requirement in seen:
            _fail(
                "wheel_metadata_dependency_invalid",
                f"/METADATA/Requires-Dist/{index}",
                "duplicate canonical requirement",
            )
        seen.add(requirement)
        requirements.append(requirement)
    return name, canonical_name, version, canonical_version, tuple(requirements)


def _canonical_requirement(requirement: Requirement) -> str:
    result = canonicalize_name(requirement.name)
    if requirement.extras:
        extras = sorted(canonicalize_name(extra) for extra in requirement.extras)
        result += f"[{','.join(extras)}]"
    if requirement.url is not None:
        result += f"@ {requirement.url}"
    else:
        result += str(requirement.specifier)
    if requirement.marker is not None:
        result += f"; {requirement.marker}"
    return result


def _parse_wheel_metadata(data: bytes) -> tuple[str, ...]:
    message = _parse_email_metadata(
        data,
        path="/WHEEL",
        byte_limit=WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1,
    )
    versions = message.get_all("Wheel-Version", [])
    tags = message.get_all("Tag", [])
    if len(versions) != 1 or str(versions[0]).strip() != "1.0":
        _fail("wheel_metadata_invalid", "/WHEEL/Wheel-Version")
    if not tags:
        _fail("wheel_metadata_missing", "/WHEEL/Tag")
    expanded: set[str] = set()
    for index, raw_tag in enumerate(tags):
        value = str(raw_tag)
        if value != value.strip() or not _TAG_RE.fullmatch(value):
            _fail("wheel_metadata_invalid", f"/WHEEL/Tag/{index}")
        parsed = tuple(sorted(str(tag) for tag in parse_tag(value)))
        if not parsed or any(tag in expanded for tag in parsed):
            _fail("wheel_metadata_duplicate", f"/WHEEL/Tag/{index}")
        expanded.update(parsed)
    return tuple(sorted(expanded))


def _parse_entry_points(data: bytes | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if data is None:
        return (), ()
    if (
        type(data) is not bytes
        or not data
        or len(data) > WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1
    ):
        _fail("wheel_metadata_invalid", "/entry_points.txt")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail("wheel_metadata_invalid", "/entry_points.txt", type(exc).__name__)
    if text.startswith("\ufeff") or "\x00" in text:
        _fail("wheel_metadata_invalid", "/entry_points.txt")
    parser = ConfigParser(
        interpolation=None,
        delimiters=("=",),
        strict=True,
        empty_lines_in_values=False,
    )
    parser.optionxform = str
    try:
        parser.read_string(text)
    except ConfigParserError as exc:
        _fail("wheel_metadata_invalid", "/entry_points.txt", type(exc).__name__)
    if parser.defaults():
        _fail("wheel_metadata_invalid", "/entry_points.txt/DEFAULT")
    result: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for section in ("console_scripts", "gui_scripts"):
        names: list[str] = []
        if parser.has_section(section):
            for index, (name, target) in enumerate(parser.items(section, raw=True)):
                if (
                    name != name.strip()
                    or not _SCRIPT_NAME_RE.fullmatch(name)
                    or not target.strip()
                ):
                    _fail(
                        "wheel_metadata_invalid",
                        f"/entry_points.txt/{section}/{index}",
                    )
                folded = name.casefold()
                if folded in seen:
                    _fail(
                        "wheel_metadata_duplicate",
                        f"/entry_points.txt/{section}/{index}",
                    )
                seen.add(folded)
                names.append(name)
        result.append(tuple(sorted(names)))
    return result[0], result[1]


def _parse_email_metadata(data: bytes, *, path: str, byte_limit: int) -> Any:
    if type(data) is not bytes or not data or len(data) > byte_limit:
        _fail("wheel_metadata_invalid", path)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail("wheel_metadata_invalid", path, type(exc).__name__)
    if text.startswith("\ufeff") or "\x00" in text:
        _fail("wheel_metadata_invalid", path)
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except (ValueError, TypeError) as exc:
        _fail("wheel_metadata_invalid", path, type(exc).__name__)
    if message.defects:
        _fail("wheel_metadata_invalid", path, type(message.defects[0]).__name__)
    return message


def _parse_record(
    data: bytes,
    *,
    record_path: str,
    installed: bool,
    allowed_external_paths: frozenset[str] = frozenset(),
    max_rows: int,
) -> tuple[_RecordRow, ...]:
    error_code = "installed_record_invalid" if installed else "wheel_record_invalid"
    if (
        type(data) is not bytes
        or not data
        or len(data) > WHEEL_ARTIFACT_MAX_RECORD_BYTES_V1
    ):
        _fail(error_code, "/installed_record" if installed else "/RECORD")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail(
            error_code,
            "/installed_record" if installed else "/RECORD",
            type(exc).__name__,
        )
    if text.startswith("\ufeff") or "\x00" in text:
        _fail(error_code, "/installed_record" if installed else "/RECORD")
    if type(max_rows) is not int or max_rows <= 0:
        _fail(error_code, "/installed_record" if installed else "/RECORD")
    rows: list[_RecordRow] = []
    seen: set[str] = set()
    folded_seen: set[str] = set()
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        for index, fields in enumerate(reader):
            if index >= max_rows:
                _fail(
                    "installed_record_extra_limit_exceeded"
                    if installed
                    else "wheel_record_invalid",
                    "/installed_record" if installed else "/RECORD",
                )
            path = f"/installed_record/{index}" if installed else f"/RECORD/{index}"
            if len(fields) != 3 or any(type(field) is not str for field in fields):
                _fail(
                    "installed_record_invalid"
                    if installed
                    else "wheel_record_row_invalid",
                    path,
                )
            member_path, hash_field, size_field = fields
            if installed and member_path in allowed_external_paths:
                _validate_external_record_path(member_path, f"{path}/0")
            else:
                _validate_member_path(member_path, f"{path}/0", installed=installed)
            if member_path in seen:
                _fail(
                    "installed_record_invalid"
                    if installed
                    else "wheel_record_duplicate",
                    path,
                )
            seen.add(member_path)
            folded = member_path.casefold()
            if folded in folded_seen:
                _fail(
                    "installed_record_invalid"
                    if installed
                    else "wheel_record_duplicate",
                    path,
                )
            folded_seen.add(folded)
            if member_path == record_path:
                if hash_field or size_field:
                    _fail(
                        "installed_record_invalid"
                        if installed
                        else "wheel_record_self_invalid",
                        path,
                    )
            else:
                if hash_field:
                    match = _RECORD_HASH_RE.fullmatch(hash_field)
                    if match is None:
                        _fail(
                            "installed_record_invalid"
                            if installed
                            else "wheel_record_hash_invalid",
                            path,
                        )
                    try:
                        digest = base64.b64decode(
                            match.group(1) + "=",
                            altchars=b"-_",
                            validate=True,
                        )
                    except (ValueError, TypeError) as exc:
                        _fail(
                            "installed_record_invalid"
                            if installed
                            else "wheel_record_hash_invalid",
                            path,
                            type(exc).__name__,
                        )
                    if (
                        len(digest) != 32
                        or _record_hash_from_digest(digest) != hash_field
                    ):
                        _fail(
                            "installed_record_invalid"
                            if installed
                            else "wheel_record_hash_invalid",
                            path,
                        )
                if size_field and _SIZE_RE.fullmatch(size_field) is None:
                    _fail(
                        "installed_record_invalid"
                        if installed
                        else "wheel_record_size_invalid",
                        path,
                    )
                if not installed and (not hash_field or not size_field):
                    _fail("wheel_record_row_invalid", path)
                if installed and bool(hash_field) != bool(size_field):
                    _fail("installed_record_invalid", path)
            rows.append(_RecordRow(member_path, hash_field, size_field))
    except (csv.Error, UnicodeError) as exc:
        _fail(
            error_code,
            "/installed_record" if installed else "/RECORD",
            type(exc).__name__,
        )
    if not rows:
        _fail(error_code, "/installed_record" if installed else "/RECORD")
    if record_path not in seen:
        _fail(
            "installed_record_invalid" if installed else "wheel_record_self_invalid",
            "/installed_record" if installed else "/RECORD",
        )
    return tuple(rows)


def _authorized_script_record_paths(
    *,
    installed_root: str,
    scripts_root: str,
    entry_point_names: tuple[str, ...],
) -> dict[str, tuple[str, str]]:
    installed_absolute = os.path.abspath(installed_root)
    scripts_absolute = os.path.abspath(scripts_root)
    result: dict[str, tuple[str, str]] = {}
    for entry_point_name in entry_point_names:
        basenames = (entry_point_name,)
        if os.name == "nt":  # pragma: no cover - exercised on Windows runners
            basenames = (
                f"{entry_point_name}.exe",
                f"{entry_point_name}-script.py",
                f"{entry_point_name}.exe.manifest",
            )
        for basename in basenames:
            try:
                record_path = os.path.relpath(
                    os.path.join(scripts_absolute, basename),
                    start=installed_absolute,
                ).replace(os.sep, "/")
            except ValueError as exc:
                _fail(
                    "wheel_artifact_argument_invalid",
                    "/installed_scripts_root",
                    type(exc).__name__,
                )
            _validate_external_record_path(
                record_path,
                "/installed_scripts_root",
            )
            if record_path in result:
                _fail(
                    "wheel_artifact_argument_invalid",
                    "/installed_scripts_root",
                    "script RECORD path collision",
                )
            result[record_path] = (entry_point_name, basename)
    return result


def _validate_external_record_path(path: str, pointer: str) -> None:
    if (
        type(path) is not str
        or not path
        or "\x00" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or "\\" in path
        or path.startswith("/")
        or _DRIVE_RE.match(path)
        or unicodedata.normalize("NFC", path) != path
    ):
        _fail("installed_record_path_escape", pointer)
    try:
        encoded = path.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        _fail("installed_record_path_escape", pointer, type(exc).__name__)
    if len(encoded) > WHEEL_ARTIFACT_MAX_PATH_BYTES_V1:
        _fail("installed_record_path_escape", pointer)
    parts = path.split("/")
    seen_normal = False
    for part in parts:
        if part in ("", "."):
            _fail("installed_record_path_escape", pointer)
        if part == "..":
            if seen_normal:
                _fail("installed_record_path_escape", pointer)
        else:
            seen_normal = True
    if not seen_normal:
        _fail("installed_record_path_escape", pointer)


def _verify_installed_extra_row(
    row: _RecordRow,
    *,
    digest: str,
    byte_count: int,
) -> None:
    if row.hash_field:
        if row.hash_field != _record_hash_from_prefixed(digest):
            _fail(
                "installed_record_hash_mismatch",
                f"/installed_record/{row.path}",
            )
        if row.size_field != str(byte_count):
            _fail(
                "installed_record_member_mismatch",
                f"/installed_record/{row.path}",
            )
    elif row.size_field:
        _fail(
            "installed_record_invalid",
            f"/installed_record/{row.path}",
            "extra hash and size must both be empty or both be present",
        )


def _verify_wheel_record(
    rows: tuple[_RecordRow, ...],
    members: tuple[WheelArtifactMemberIdentityV1, ...],
    *,
    record_path: str,
) -> None:
    row_by_path = {row.path: row for row in rows}
    member_by_path = {member.path: member for member in members}
    if set(row_by_path) != set(member_by_path):
        _fail("wheel_record_member_set_mismatch", "/RECORD")
    for path, member in member_by_path.items():
        row = row_by_path[path]
        if path == record_path:
            continue
        if row.hash_field != _record_hash_from_prefixed(member.sha256):
            _fail("wheel_record_hash_mismatch", f"/RECORD/{path}")
        if row.size_field != str(member.byte_count):
            _fail("wheel_record_size_mismatch", f"/RECORD/{path}")


def _validate_member_path(path: str, pointer: str, *, installed: bool) -> None:
    escape_code = (
        "installed_record_path_escape" if installed else "wheel_archive_path_traversal"
    )
    if type(path) is not str or not path:
        _fail(
            "installed_record_invalid"
            if installed
            else "wheel_archive_member_name_invalid",
            pointer,
        )
    if "\x00" in path:
        _fail(
            "installed_record_path_escape"
            if installed
            else "wheel_archive_nul_forbidden",
            pointer,
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        _fail(
            "installed_record_path_escape"
            if installed
            else "wheel_archive_member_name_invalid",
            pointer,
        )
    if "\\" in path:
        _fail(
            "installed_record_path_escape"
            if installed
            else "wheel_archive_backslash_forbidden",
            pointer,
        )
    if path.startswith("/") or path.startswith("//") or _DRIVE_RE.match(path):
        _fail(
            "installed_record_path_escape"
            if installed
            else "wheel_archive_absolute_path",
            pointer,
        )
    if unicodedata.normalize("NFC", path) != path:
        _fail(
            "installed_record_path_escape"
            if installed
            else "wheel_archive_nfc_invalid",
            pointer,
        )
    try:
        encoded = path.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        _fail(
            "installed_record_invalid"
            if installed
            else "wheel_archive_member_name_invalid",
            pointer,
            type(exc).__name__,
        )
    if len(encoded) > WHEEL_ARTIFACT_MAX_PATH_BYTES_V1:
        _fail(
            "installed_record_invalid"
            if installed
            else "wheel_archive_member_name_invalid",
            pointer,
        )
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        _fail(escape_code, pointer)
    pure = PurePosixPath(path)
    if pure.is_absolute() or str(pure) != path:
        _fail(escape_code, pointer)


def _record_hash_from_digest(digest: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _record_hash_from_prefixed(value: str) -> str:
    return _record_hash_from_digest(bytes.fromhex(value.removeprefix("sha256:")))


def _filesystem_path(value: Any, *, error_path: str) -> str:
    try:
        path = os.fspath(value)
    except TypeError as exc:
        _fail("wheel_artifact_argument_invalid", error_path, type(exc).__name__)
    if type(path) is not str or not path or "\x00" in path:
        _fail("wheel_artifact_argument_invalid", error_path)
    return path


def _secure_flags(*, directory: bool = False) -> int:
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_CLOEXEC")
        or not hasattr(os, "O_NONBLOCK")
    ):
        _fail("wheel_artifact_secure_open_unsupported", "/platform")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    flags |= getattr(os, "O_BINARY", 0)
    if directory:
        if not hasattr(os, "O_DIRECTORY"):
            _fail("wheel_artifact_secure_open_unsupported", "/platform")
        flags |= os.O_DIRECTORY
    else:
        flags |= os.O_NONBLOCK
    return flags


def _secure_open_file(path: str, *, purpose: str) -> int:
    try:
        return os.open(path, _secure_flags())
    except OSError as exc:
        if exc.errno == errno.ELOOP or _path_is_symlink(path):
            _fail(
                "wheel_artifact_symlink_forbidden"
                if purpose == "wheel"
                else "installed_wheel_file_symlink_forbidden",
                "/wheel_path" if purpose == "wheel" else f"/installed/{path}",
            )
        _fail(
            "wheel_artifact_open_failed"
            if purpose == "wheel"
            else "installed_wheel_file_missing",
            "/wheel_path" if purpose == "wheel" else f"/installed/{path}",
            type(exc).__name__,
        )


def _secure_open_root(path: str) -> int:
    try:
        return os.open(path, _secure_flags(directory=True))
    except OSError as exc:
        if exc.errno == errno.ELOOP or _path_is_symlink(path):
            _fail("installed_root_symlink_forbidden", "/installed_root")
        _fail("installed_root_open_failed", "/installed_root", type(exc).__name__)


def _path_is_symlink(path: str) -> bool:
    try:
        return stat.S_ISLNK(os.stat(path, follow_symlinks=False).st_mode)
    except OSError:
        return False


def _dir_entry_is_symlink(directory_fd: int, name: str) -> bool:
    try:
        return stat.S_ISLNK(
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode
        )
    except OSError:
        return False


def _lstat_path(path: str, *, purpose: str) -> _StatSnapshot:
    try:
        result = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        _fail(
            "wheel_artifact_path_replaced"
            if purpose == "wheel"
            else "installed_root_path_replaced",
            "/wheel_path" if purpose == "wheel" else "/installed_root",
            type(exc).__name__,
        )
    return _stat_snapshot(result)


def _stat_snapshot(value: os.stat_result) -> _StatSnapshot:
    return _StatSnapshot(
        device=value.st_dev,
        inode=value.st_ino,
        mode_type=stat.S_IFMT(value.st_mode),
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _validate_opened_wheel(fd_stat: _StatSnapshot, path_stat: _StatSnapshot) -> None:
    if fd_stat.mode_type != stat.S_IFREG:
        _fail("wheel_artifact_not_regular", "/wheel_path")
    if path_stat.mode_type == stat.S_IFLNK:
        _fail("wheel_artifact_symlink_forbidden", "/wheel_path")
    if (fd_stat.device, fd_stat.inode) != (path_stat.device, path_stat.inode):
        _fail("wheel_artifact_path_replaced", "/wheel_path")
    if not 0 < fd_stat.size <= WHEEL_ARTIFACT_MAX_ARCHIVE_BYTES_V1:
        _fail("wheel_artifact_too_large", "/byte_count")


def _validate_opened_root(fd_stat: _StatSnapshot, path_stat: _StatSnapshot) -> None:
    if fd_stat.mode_type != stat.S_IFDIR:
        _fail("installed_root_invalid", "/installed_root")
    if path_stat.mode_type == stat.S_IFLNK:
        _fail("installed_root_symlink_forbidden", "/installed_root")
    if (fd_stat.device, fd_stat.inode) != (path_stat.device, path_stat.inode):
        _fail("installed_root_path_replaced", "/installed_root")


def _require_same_inode(
    start_fd: _StatSnapshot,
    start_path: _StatSnapshot,
    end_path: _StatSnapshot,
    *,
    purpose: str,
) -> None:
    expected = (start_fd.device, start_fd.inode)
    if (start_path.device, start_path.inode) != expected or (
        end_path.device,
        end_path.inode,
    ) != expected:
        _fail(
            "wheel_artifact_path_replaced"
            if purpose == "wheel"
            else "installed_root_path_replaced",
            "/wheel_path" if purpose == "wheel" else "/installed_root",
        )


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    while True:
        chunk = stream.read(_CHUNK_BYTES)
        if not chunk:
            break
        count += len(chunk)
        if count > WHEEL_ARTIFACT_MAX_ARCHIVE_BYTES_V1:
            _fail("wheel_artifact_too_large", "/byte_count")
        digest.update(chunk)
    return f"sha256:{digest.hexdigest()}", count


def _read_root_file(root_fd: int, path: str, *, byte_limit: int) -> bytes:
    _validate_member_path(path, f"/installed/{path}", installed=True)
    components = path.split("/")
    directory_fd = os.dup(root_fd)
    try:
        for component in components[:-1]:
            try:
                next_fd = os.open(
                    component,
                    _secure_flags(directory=True),
                    dir_fd=directory_fd,
                )
            except OSError as exc:
                if exc.errno == errno.ELOOP or _dir_entry_is_symlink(
                    directory_fd,
                    component,
                ):
                    _fail(
                        "installed_wheel_file_symlink_forbidden",
                        f"/installed/{path}",
                    )
                _fail(
                    "installed_wheel_file_missing",
                    f"/installed/{path}",
                    type(exc).__name__,
                )
            os.close(directory_fd)
            directory_fd = next_fd
        name = components[-1]
        try:
            file_fd = os.open(name, _secure_flags(), dir_fd=directory_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP or _dir_entry_is_symlink(
                directory_fd,
                name,
            ):
                _fail(
                    "installed_wheel_file_symlink_forbidden",
                    f"/installed/{path}",
                )
            _fail(
                "installed_wheel_file_missing",
                f"/installed/{path}",
                type(exc).__name__,
            )
        try:
            start_fd = _stat_snapshot(os.fstat(file_fd))
            try:
                start_path = _stat_snapshot(
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                )
            except OSError as exc:
                _fail(
                    "installed_wheel_file_missing",
                    f"/installed/{path}",
                    type(exc).__name__,
                )
            if start_fd.mode_type != stat.S_IFREG:
                _fail(
                    "installed_wheel_file_not_regular",
                    f"/installed/{path}",
                )
            if start_path.mode_type == stat.S_IFLNK:
                _fail(
                    "installed_wheel_file_symlink_forbidden",
                    f"/installed/{path}",
                )
            if (start_fd.device, start_fd.inode) != (
                start_path.device,
                start_path.inode,
            ):
                _fail("installed_wheel_file_missing", f"/installed/{path}")
            if start_fd.size > byte_limit:
                _fail(
                    "installed_wheel_file_size_mismatch",
                    f"/installed/{path}",
                )
            chunks: list[bytes] = []
            count = 0
            while True:
                chunk = os.read(file_fd, min(_CHUNK_BYTES, byte_limit + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > byte_limit:
                    _fail(
                        "installed_wheel_file_size_mismatch",
                        f"/installed/{path}",
                    )
            end_fd = _stat_snapshot(os.fstat(file_fd))
            end_path = _stat_snapshot(
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            )
            if end_fd != start_fd or (
                end_path.device,
                end_path.inode,
            ) != (start_fd.device, start_fd.inode):
                _fail("installed_wheel_file_missing", f"/installed/{path}")
            return b"".join(chunks)
        except OSError as exc:
            _fail(
                "installed_wheel_file_missing",
                f"/installed/{path}",
                type(exc).__name__,
            )
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


def _identity_payload(
    identity: WheelArtifactIdentityV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "wheel_filename": identity.wheel_filename,
        "distribution_name": identity.distribution_name,
        "canonical_distribution_name": identity.canonical_distribution_name,
        "distribution_version": identity.distribution_version,
        "canonical_distribution_version": identity.canonical_distribution_version,
        "build_tag": identity.build_tag,
        "wheel_tags": list(identity.wheel_tags),
        "requires_dist": list(identity.requires_dist),
        "console_scripts": list(identity.console_scripts),
        "gui_scripts": list(identity.gui_scripts),
        "byte_count": identity.byte_count,
        "sha256": identity.sha256,
        "dist_info_directory": identity.dist_info_directory,
        "metadata_path": identity.metadata_path,
        "wheel_metadata_path": identity.wheel_metadata_path,
        "record_path": identity.record_path,
        "metadata_sha256": identity.metadata_sha256,
        "wheel_metadata_sha256": identity.wheel_metadata_sha256,
        "record_sha256": identity.record_sha256,
        "member_count": identity.member_count,
        "uncompressed_byte_count": identity.uncompressed_byte_count,
        "members": [member.to_dict() for member in identity.members],
        "member_manifest_sha256": identity.member_manifest_sha256,
    }
    if include_hash:
        payload["identity_hash"] = identity.identity_hash
    return payload


def _identity_constructor_payload(identity: WheelArtifactIdentityV1) -> dict[str, Any]:
    return {
        name: getattr(identity, name)
        for name in identity.__dataclass_fields__
        if name != "identity_hash"
    }


def _installed_replay_payload(
    replay: InstalledWheelReplayV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": replay.schema_version,
        "wheel_identity": _identity_payload(replay.wheel_identity, include_hash=True),
        "installed_record_sha256": replay.installed_record_sha256,
        "verified_wheel_member_count": replay.verified_wheel_member_count,
        "extra_files": [item.to_dict() for item in replay.extra_files],
        "extra_file_count": replay.extra_file_count,
        "extra_byte_count": replay.extra_byte_count,
        "extra_manifest_sha256": replay.extra_manifest_sha256,
        "script_files": [item.to_dict() for item in replay.script_files],
        "script_file_count": replay.script_file_count,
        "script_byte_count": replay.script_byte_count,
        "script_manifest_sha256": replay.script_manifest_sha256,
    }
    if include_hash:
        payload["replay_hash"] = replay.replay_hash
    return payload


def _installed_replay_constructor_payload(
    replay: InstalledWheelReplayV1,
) -> dict[str, Any]:
    return {
        name: getattr(replay, name)
        for name in replay.__dataclass_fields__
        if name != "replay_hash"
    }


def _bounded_message(value: str) -> str:
    text = " ".join(str(value).split())
    return text[:240]


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise WheelArtifactV1Error(code, path, message)


__all__ = [
    "INSTALLED_WHEEL_REPLAY_SCHEMA_VERSION_V1",
    "WHEEL_ARTIFACT_MAX_ARCHIVE_BYTES_V1",
    "WHEEL_ARTIFACT_MAX_COMPRESSION_RATIO_V1",
    "WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1",
    "WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1",
    "WHEEL_ARTIFACT_MAX_METADATA_BYTES_V1",
    "WHEEL_ARTIFACT_MAX_RECORD_BYTES_V1",
    "WHEEL_ARTIFACT_MAX_UNCOMPRESSED_BYTES_V1",
    "WHEEL_ARTIFACT_SCHEMA_VERSION_V1",
    "WHEEL_ARTIFACT_STABLE_ERROR_CODES_V1",
    "InstalledWheelReplayV1",
    "InstalledWheelScriptIdentityV1",
    "WheelArtifactIdentityV1",
    "WheelArtifactMemberIdentityV1",
    "WheelArtifactV1Error",
    "inspect_wheel_artifact_v1",
    "replay_installed_wheel_artifact_v1",
    "validate_installed_wheel_replay_v1",
    "validate_wheel_artifact_identity_v1",
]
