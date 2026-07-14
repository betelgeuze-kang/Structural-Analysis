"""Canonical runtime dependency-wheel closure verification.

The v1 lock contains only dependency wheels; the release root wheel is supplied
as a separately inspected :class:`WheelArtifactIdentityV1`.  Verification is
deliberately stricter than an installer: every dependency wheel must be the
only regular entry in a dedicated wheelhouse, its bytes and metadata are
re-inspected, and the active ``Requires-Dist`` graph must equal the lock.

This contract does not inspect build-system dependencies, execute an install,
or claim that another environment can reproduce the artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

from packaging.markers import UndefinedEnvironmentName
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)

from .wheel_artifact_v1 import (
    WheelArtifactV1Error,
    WheelArtifactIdentityV1,
    inspect_wheel_artifact_v1,
    validate_wheel_artifact_identity_v1,
)


DEPENDENCY_LOCK_SCHEMA_VERSION_V1 = "structural-analysis-dependency-lock.v1"
DEPENDENCY_LOCK_RECEIPT_SCHEMA_VERSION_V1 = (
    "structural-analysis-dependency-lock-receipt.v1"
)

_STATUS = "runtime_dependency_artifact_closure_verified"
_ZERO_HASH = "sha256:" + "0" * 64
_LOCK_MAX_BYTES = 8 * 1024 * 1024
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANONICAL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SAFE_WHEEL_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]*\.whl$")

# ``Marker.evaluate`` fills omitted values from the current interpreter.  An
# exact set prevents a partial lock from silently depending on verifier-host
# state.  ``extra`` is derived from dependency edges and is not caller input.
_TARGET_ENVIRONMENT_KEYS = (
    "implementation_name",
    "implementation_version",
    "os_name",
    "platform_machine",
    "platform_python_implementation",
    "platform_release",
    "platform_system",
    "platform_version",
    "python_full_version",
    "python_version",
    "sys_platform",
)


class DependencyLockV1Error(ValueError):
    """Stable fail-closed dependency-lock error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class DependencyLockArtifactV1:
    """One re-inspected dependency wheel bound into the receipt."""

    name: str
    version: str
    filename: str
    byte_count: int
    sha256: str
    direct: bool
    requires_dist: tuple[str, ...]
    wheel_identity_hash: str

    def to_dict(self) -> dict[str, Any]:
        _validate_receipt_artifact(self, path="/artifacts")
        return _receipt_artifact_payload(self)


@dataclass(frozen=True, slots=True)
class DependencyLockClaimsV1:
    """Narrow claims made by a successful v1 closure verification."""

    canonical_lock_bytes_verified: Literal[True] = True
    dependency_wheel_bytes_verified: Literal[True] = True
    dependency_wheel_record_integrity_verified: Literal[True] = True
    dependency_wheel_metadata_verified: Literal[True] = True
    target_marker_environment_bound: Literal[True] = True
    runtime_requires_dist_closure_verified: Literal[True] = True
    exact_dependency_artifact_set_verified: Literal[True] = True
    direct_dependency_flags_verified: Literal[True] = True
    build_dependencies_verified: Literal[False] = False
    installation_executed: Literal[False] = False
    source_build_reproducibility_proven: Literal[False] = False
    environment_reproducibility_proven: Literal[False] = False
    commercial_ready: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class DependencyLockReceiptV1:
    """Immutable receipt for one root wheel and exact runtime wheel closure."""

    schema_version: str
    status: Literal["runtime_dependency_artifact_closure_verified"]
    lock_hash: str
    lock_bytes_sha256: str
    target_environment: tuple[tuple[str, str], ...]
    target_environment_hash: str
    root_distribution_name: str
    root_distribution_version: str
    root_filename: str
    root_byte_count: int
    root_sha256: str
    root_requires_dist: tuple[str, ...]
    root_wheel_identity_hash: str
    artifact_count: int
    artifacts: tuple[DependencyLockArtifactV1, ...]
    artifact_aggregate_hash: str
    direct_dependency_names: tuple[str, ...]
    transitive_dependency_names: tuple[str, ...]
    root_requirements_matched: Literal[True]
    transitive_closure_matched: Literal[True]
    claims: DependencyLockClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_dependency_lock_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class _LockRow:
    name: str
    version: str
    filename: str
    byte_count: int
    sha256: str
    direct: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "filename": self.filename,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "direct": self.direct,
        }


@dataclass(frozen=True, slots=True)
class _WheelView:
    source: Any
    distribution_name: str
    distribution_version: str
    requires_dist: tuple[str, ...]
    filename: str
    byte_count: int
    sha256: str
    identity_hash: str


class _DuplicateJsonKey(ValueError):
    pass


def verify_dependency_artifact_lock_v1(
    raw_lock: bytes,
    *,
    artifact_root: str | os.PathLike[str],
    root_wheel_identity: WheelArtifactIdentityV1,
) -> DependencyLockReceiptV1:
    """Verify canonical lock bytes and the exact active runtime wheel closure.

    ``artifact_root`` is a dedicated dependency wheelhouse.  The root wheel is
    intentionally not stored in it and is supplied as an already-inspected
    identity.  Every regular or symbolic-link entry not named by the lock is a
    failure; symbolic links are never accepted as artifacts.
    """

    manifest = _parse_canonical_lock(raw_lock)
    target_environment = _validate_target_environment(
        manifest["target_environment"], path="/target_environment"
    )
    rows = _validate_lock_rows(manifest["artifacts"])

    root = _validate_root_wheel_identity(root_wheel_identity)
    if root.distribution_name in {row.name for row in rows}:
        _fail("dependency_lock_root_present_in_artifacts", "/artifacts")

    root_path = _validate_artifact_root(artifact_root)
    expected_filenames = {row.filename for row in rows}
    _validate_wheelhouse_entries(root_path, expected_filenames)

    inspected: list[tuple[_LockRow, _WheelView]] = []
    by_name: dict[str, _WheelView] = {}
    for index, row in enumerate(rows):
        wheel_path = _safe_artifact_path(root_path, row.filename, index=index)
        identity = _inspect_dependency_wheel(wheel_path, index=index)
        _match_lock_row(row, identity, index=index)
        inspected.append((row, identity))
        by_name[row.name] = identity

    # Detect additions, removals, and replacements that occurred while wheel
    # inspection was in progress.
    _validate_wheelhouse_entries(root_path, expected_filenames)

    direct_names, reachable_names = _verify_runtime_closure(
        root=root,
        dependencies=by_name,
        target_environment=target_environment,
    )
    locked_names = set(by_name)
    if reachable_names != locked_names:
        missing = sorted(reachable_names - locked_names)
        extra = sorted(locked_names - reachable_names)
        if missing:
            _fail(
                "dependency_lock_dependency_missing",
                "/artifacts",
                ",".join(missing),
            )
        _fail(
            "dependency_lock_dependency_extra",
            "/artifacts",
            ",".join(extra),
        )

    for index, row in enumerate(rows):
        expected_direct = row.name in direct_names
        if row.direct is not expected_direct:
            _fail(
                "dependency_lock_direct_flag_mismatch",
                f"/artifacts/{index}/direct",
            )

    receipt_artifacts = tuple(
        DependencyLockArtifactV1(
            name=row.name,
            version=row.version,
            filename=row.filename,
            byte_count=row.byte_count,
            sha256=row.sha256,
            direct=row.direct,
            requires_dist=identity.requires_dist,
            wheel_identity_hash=identity.identity_hash,
        )
        for row, identity in inspected
    )
    artifact_aggregate_hash = canonical_hash(
        [_receipt_artifact_payload(artifact) for artifact in receipt_artifacts]
    )
    environment_items = tuple(sorted(target_environment.items()))
    draft = DependencyLockReceiptV1(
        schema_version=DEPENDENCY_LOCK_RECEIPT_SCHEMA_VERSION_V1,
        status=_STATUS,
        lock_hash=manifest["lock_hash"],
        lock_bytes_sha256=sha256_prefixed(raw_lock),
        target_environment=environment_items,
        target_environment_hash=canonical_hash(dict(environment_items)),
        root_distribution_name=root.distribution_name,
        root_distribution_version=root.distribution_version,
        root_filename=root.filename,
        root_byte_count=root.byte_count,
        root_sha256=root.sha256,
        root_requires_dist=root.requires_dist,
        root_wheel_identity_hash=root.identity_hash,
        artifact_count=len(receipt_artifacts),
        artifacts=receipt_artifacts,
        artifact_aggregate_hash=artifact_aggregate_hash,
        direct_dependency_names=tuple(sorted(direct_names)),
        transitive_dependency_names=tuple(sorted(reachable_names - direct_names)),
        root_requirements_matched=True,
        transitive_closure_matched=True,
        claims=DependencyLockClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_dependency_lock_receipt_v1(receipt)


def validate_dependency_lock_v1(
    raw_lock: bytes,
    *,
    artifact_root: str | os.PathLike[str],
    root_wheel_identity: WheelArtifactIdentityV1,
) -> DependencyLockReceiptV1:
    """Compatibility spelling for the full artifact-backed validator."""

    return verify_dependency_artifact_lock_v1(
        raw_lock,
        artifact_root=artifact_root,
        root_wheel_identity=root_wheel_identity,
    )


def validate_dependency_lock_receipt_v1(
    receipt: DependencyLockReceiptV1,
) -> DependencyLockReceiptV1:
    """Validate the immutable receipt shape and every derived receipt hash."""

    if type(receipt) is not DependencyLockReceiptV1:
        _fail("dependency_lock_receipt_type_invalid", "/receipt")
    if (
        receipt.schema_version != DEPENDENCY_LOCK_RECEIPT_SCHEMA_VERSION_V1
        or receipt.status != _STATUS
    ):
        _fail("dependency_lock_receipt_semantics_invalid", "/receipt")
    for path, value in (
        ("/lock_hash", receipt.lock_hash),
        ("/lock_bytes_sha256", receipt.lock_bytes_sha256),
        ("/target_environment_hash", receipt.target_environment_hash),
        ("/root_sha256", receipt.root_sha256),
        ("/root_wheel_identity_hash", receipt.root_wheel_identity_hash),
        ("/artifact_aggregate_hash", receipt.artifact_aggregate_hash),
        ("/receipt_hash", receipt.receipt_hash),
    ):
        _validate_sha256(value, path)

    if type(receipt.target_environment) is not tuple:
        _fail("dependency_lock_receipt_environment_invalid", "/target_environment")
    try:
        environment = dict(receipt.target_environment)
    except (TypeError, ValueError) as exc:
        _fail(
            "dependency_lock_receipt_environment_invalid",
            "/target_environment",
            type(exc).__name__,
        )
    if tuple(sorted(environment.items())) != receipt.target_environment:
        _fail("dependency_lock_receipt_environment_invalid", "/target_environment")
    _validate_target_environment(environment, path="/target_environment")
    if receipt.target_environment_hash != canonical_hash(environment):
        _fail(
            "dependency_lock_receipt_environment_hash_mismatch",
            "/target_environment_hash",
        )

    _validate_canonical_name(receipt.root_distribution_name, "/root/name")
    _validate_canonical_version(receipt.root_distribution_version, "/root/version")
    _validate_safe_filename(receipt.root_filename, "/root/filename")
    if type(receipt.root_byte_count) is not int or receipt.root_byte_count <= 0:
        _fail("dependency_lock_receipt_root_invalid", "/root/byte_count")
    if type(receipt.root_requires_dist) is not tuple or any(
        type(value) is not str for value in receipt.root_requires_dist
    ):
        _fail("dependency_lock_receipt_root_invalid", "/root/requires_dist")
    _parse_requirements(
        receipt.root_requires_dist,
        owner=receipt.root_distribution_name,
    )

    if (
        type(receipt.artifacts) is not tuple
        or type(receipt.artifact_count) is not int
        or receipt.artifact_count != len(receipt.artifacts)
    ):
        _fail("dependency_lock_receipt_artifact_count_invalid", "/artifact_count")
    for index, artifact in enumerate(receipt.artifacts):
        _validate_receipt_artifact(artifact, path=f"/artifacts/{index}")
    names = tuple(artifact.name for artifact in receipt.artifacts)
    if names != tuple(sorted(names)) or len(set(names)) != len(names):
        _fail("dependency_lock_receipt_artifact_order_invalid", "/artifacts")
    if receipt.root_distribution_name in set(names):
        _fail("dependency_lock_receipt_root_present", "/artifacts")
    expected_aggregate = canonical_hash(
        [_receipt_artifact_payload(artifact) for artifact in receipt.artifacts]
    )
    if receipt.artifact_aggregate_hash != expected_aggregate:
        _fail(
            "dependency_lock_receipt_artifact_aggregate_mismatch",
            "/artifact_aggregate_hash",
        )

    if (
        type(receipt.direct_dependency_names) is not tuple
        or type(receipt.transitive_dependency_names) is not tuple
        or receipt.direct_dependency_names
        != tuple(sorted(receipt.direct_dependency_names))
        or receipt.transitive_dependency_names
        != tuple(sorted(receipt.transitive_dependency_names))
        or len(set(receipt.direct_dependency_names))
        != len(receipt.direct_dependency_names)
        or len(set(receipt.transitive_dependency_names))
        != len(receipt.transitive_dependency_names)
        or set(receipt.direct_dependency_names)
        & set(receipt.transitive_dependency_names)
        or set(receipt.direct_dependency_names)
        | set(receipt.transitive_dependency_names)
        != set(names)
    ):
        _fail("dependency_lock_receipt_dependency_sets_invalid", "/dependencies")
    direct_from_rows = {
        artifact.name for artifact in receipt.artifacts if artifact.direct
    }
    if direct_from_rows != set(receipt.direct_dependency_names):
        _fail("dependency_lock_receipt_direct_flags_invalid", "/artifacts")
    if (
        receipt.root_requirements_matched is not True
        or receipt.transitive_closure_matched is not True
        or type(receipt.claims) is not DependencyLockClaimsV1
        or receipt.claims != DependencyLockClaimsV1()
    ):
        _fail("dependency_lock_receipt_claims_invalid", "/claims")
    if receipt.receipt_hash != canonical_hash(
        _receipt_payload(receipt, include_hash=False)
    ):
        _fail("dependency_lock_receipt_hash_mismatch", "/receipt_hash")
    return receipt


def _parse_canonical_lock(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _LOCK_MAX_BYTES:
        _fail("dependency_lock_bytes_invalid", "/lock")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("dependency_lock_json_bom_forbidden", "/lock")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJsonKey(key)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
        _reject_nonfinite(payload, path="/lock")
        canonical = canonical_json_bytes(payload)
    except _DuplicateJsonKey as exc:
        _fail("dependency_lock_json_duplicate_key", "/lock", str(exc))
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        _fail("dependency_lock_json_invalid", "/lock", type(exc).__name__)
    if type(payload) is not dict:
        _fail("dependency_lock_json_root_invalid", "/lock")
    if raw != canonical:
        _fail("dependency_lock_json_not_canonical", "/lock")
    expected_keys = {
        "schema_version",
        "target_environment",
        "artifacts",
        "lock_hash",
    }
    if set(payload) != expected_keys:
        _fail("dependency_lock_fields_invalid", "/lock")
    if payload["schema_version"] != DEPENDENCY_LOCK_SCHEMA_VERSION_V1:
        _fail("dependency_lock_schema_version_invalid", "/schema_version")
    _validate_sha256(payload["lock_hash"], "/lock_hash")
    hash_payload = dict(payload)
    del hash_payload["lock_hash"]
    if payload["lock_hash"] != canonical_hash(hash_payload):
        _fail("dependency_lock_hash_mismatch", "/lock_hash")
    return payload


def _validate_target_environment(
    value: Any,
    *,
    path: str,
) -> dict[str, str]:
    if type(value) is not dict or tuple(sorted(value)) != _TARGET_ENVIRONMENT_KEYS:
        _fail("dependency_lock_target_environment_fields_invalid", path)
    result: dict[str, str] = {}
    for key in _TARGET_ENVIRONMENT_KEYS:
        item = value[key]
        if type(item) is not str or "\x00" in item:
            _fail("dependency_lock_target_environment_value_invalid", f"{path}/{key}")
        result[key] = item
    for version_key in (
        "implementation_version",
        "python_full_version",
        "python_version",
    ):
        try:
            parsed = Version(result[version_key])
        except InvalidVersion as exc:
            _fail(
                "dependency_lock_target_environment_version_invalid",
                f"{path}/{version_key}",
                type(exc).__name__,
            )
        if str(parsed) != result[version_key]:
            _fail(
                "dependency_lock_target_environment_version_alias",
                f"{path}/{version_key}",
            )
    return result


def _validate_lock_rows(value: Any) -> tuple[_LockRow, ...]:
    if type(value) is not list:
        _fail("dependency_lock_artifacts_invalid", "/artifacts")
    rows: list[_LockRow] = []
    for index, item in enumerate(value):
        path = f"/artifacts/{index}"
        if type(item) is not dict or set(item) != {
            "name",
            "version",
            "filename",
            "byte_count",
            "sha256",
            "direct",
        }:
            _fail("dependency_lock_artifact_fields_invalid", path)
        _validate_canonical_name(item["name"], f"{path}/name")
        _validate_canonical_version(item["version"], f"{path}/version")
        _validate_safe_filename(item["filename"], f"{path}/filename")
        if type(item["byte_count"]) is not int or item["byte_count"] <= 0:
            _fail("dependency_lock_artifact_byte_count_invalid", f"{path}/byte_count")
        _validate_sha256(item["sha256"], f"{path}/sha256")
        if type(item["direct"]) is not bool:
            _fail("dependency_lock_artifact_direct_invalid", f"{path}/direct")
        rows.append(_LockRow(**item))
    names = [row.name for row in rows]
    filenames = [row.filename for row in rows]
    if names != sorted(names):
        _fail("dependency_lock_artifact_order_invalid", "/artifacts")
    if len(set(names)) != len(names):
        _fail("dependency_lock_artifact_name_duplicate", "/artifacts")
    if len(set(filenames)) != len(filenames):
        _fail("dependency_lock_artifact_filename_duplicate", "/artifacts")
    return tuple(rows)


def _validate_root_wheel_identity(identity: Any) -> _WheelView:
    if type(identity) is not WheelArtifactIdentityV1:
        _fail("dependency_lock_root_wheel_identity_type_invalid", "/root")
    try:
        validate_wheel_artifact_identity_v1(identity)
    except Exception as exc:
        _fail(
            "dependency_lock_root_wheel_identity_invalid",
            "/root",
            type(exc).__name__,
        )
    return _wheel_view(identity, path="/root")


def _validate_artifact_root(value: str | os.PathLike[str]) -> Path:
    if isinstance(value, bytes):
        _fail("dependency_lock_artifact_root_invalid", "/artifact_root")
    try:
        path = Path(value)
        resolved = path.resolve(strict=True)
    except (TypeError, ValueError, OSError) as exc:
        _fail(
            "dependency_lock_artifact_root_invalid",
            "/artifact_root",
            type(exc).__name__,
        )
    if not resolved.is_dir():
        _fail("dependency_lock_artifact_root_not_directory", "/artifact_root")
    return resolved


def _validate_wheelhouse_entries(root: Path, expected: set[str]) -> None:
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        _fail(
            "dependency_lock_artifact_root_read_failed",
            "/artifact_root",
            type(exc).__name__,
        )
    regular_names: set[str] = set()
    for entry in entries:
        try:
            if entry.is_symlink():
                _fail(
                    "dependency_lock_wheelhouse_symlink_forbidden",
                    f"/artifacts/{entry.name}",
                )
            if entry.is_file():
                regular_names.add(entry.name)
            else:
                _fail(
                    "dependency_lock_wheelhouse_entry_invalid",
                    f"/artifacts/{entry.name}",
                )
        except OSError as exc:
            _fail(
                "dependency_lock_wheelhouse_entry_read_failed",
                f"/artifacts/{entry.name}",
                type(exc).__name__,
            )
    if regular_names != expected:
        missing = sorted(expected - regular_names)
        extra = sorted(regular_names - expected)
        if missing:
            _fail(
                "dependency_lock_wheelhouse_artifact_missing",
                "/artifacts",
                ",".join(missing),
            )
        _fail(
            "dependency_lock_wheelhouse_artifact_extra", "/artifacts", ",".join(extra)
        )


def _safe_artifact_path(root: Path, filename: str, *, index: int) -> Path:
    candidate = root / filename
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        _fail(
            "dependency_lock_artifact_path_invalid",
            f"/artifacts/{index}/filename",
            type(exc).__name__,
        )
    if resolved.parent != root or resolved.name != filename or candidate.is_symlink():
        _fail("dependency_lock_artifact_path_escape", f"/artifacts/{index}/filename")
    if not resolved.is_file():
        _fail("dependency_lock_artifact_not_regular", f"/artifacts/{index}/filename")
    return resolved


def _inspect_dependency_wheel(path: Path, *, index: int) -> _WheelView:
    try:
        identity = inspect_wheel_artifact_v1(path)
        validate_wheel_artifact_identity_v1(identity)
    except WheelArtifactV1Error as exc:
        # A dependency lock already pins the expected path, bytes, RECORD, and
        # metadata identity.  If those bytes no longer form a valid wheel, the
        # stable lock-level meaning is artifact drift rather than a first-time
        # inspection failure.  Preserve the lower-level code only as bounded
        # diagnostic context.
        _fail(
            "dependency_lock_artifact_identity_mismatch",
            f"/artifacts/{index}",
            exc.code,
        )
    except Exception as exc:
        _fail(
            "dependency_lock_wheel_inspection_failed",
            f"/artifacts/{index}",
            type(exc).__name__,
        )
    return _wheel_view(identity, path=f"/artifacts/{index}")


def _wheel_view(identity: Any, *, path: str) -> _WheelView:
    """Extract the fixed public wheel-identity contract without aliases."""

    if type(identity) is not WheelArtifactIdentityV1:
        _fail("dependency_lock_wheel_identity_type_invalid", path)
    expected_attributes = (
        "distribution_name",
        "canonical_distribution_name",
        "distribution_version",
        "canonical_distribution_version",
        "requires_dist",
        "wheel_filename",
        "byte_count",
        "sha256",
        "identity_hash",
    )
    if any(not hasattr(identity, name) for name in expected_attributes):
        _fail("dependency_lock_wheel_identity_shape_invalid", path)
    requires_dist = identity.requires_dist
    if type(requires_dist) is not tuple or any(
        type(value) is not str for value in requires_dist
    ):
        _fail("dependency_lock_wheel_requires_dist_invalid", f"{path}/requires_dist")
    view = _WheelView(
        source=identity,
        distribution_name=identity.canonical_distribution_name,
        distribution_version=identity.canonical_distribution_version,
        requires_dist=requires_dist,
        filename=identity.wheel_filename,
        byte_count=identity.byte_count,
        sha256=identity.sha256,
        identity_hash=identity.identity_hash,
    )
    _validate_canonical_name(view.distribution_name, f"{path}/distribution_name")
    _validate_canonical_version(
        view.distribution_version, f"{path}/distribution_version"
    )
    _validate_safe_filename(view.filename, f"{path}/filename")
    if type(view.byte_count) is not int or view.byte_count <= 0:
        _fail("dependency_lock_wheel_byte_count_invalid", f"{path}/byte_count")
    _validate_sha256(view.sha256, f"{path}/sha256")
    _validate_sha256(view.identity_hash, f"{path}/identity_hash")
    return view


def _match_lock_row(row: _LockRow, identity: _WheelView, *, index: int) -> None:
    expected = (
        row.name,
        row.version,
        row.filename,
        row.byte_count,
        row.sha256,
    )
    actual = (
        identity.distribution_name,
        identity.distribution_version,
        identity.filename,
        identity.byte_count,
        identity.sha256,
    )
    if actual != expected:
        _fail("dependency_lock_artifact_identity_mismatch", f"/artifacts/{index}")


def _verify_runtime_closure(
    *,
    root: _WheelView,
    dependencies: Mapping[str, _WheelView],
    target_environment: Mapping[str, str],
) -> tuple[set[str], set[str]]:
    available = {root.distribution_name: root, **dependencies}
    requirements = {
        name: _parse_requirements(identity.requires_dist, owner=name)
        for name, identity in available.items()
    }
    activated_extras: dict[str, set[str]] = {root.distribution_name: set()}
    reachable: set[str] = set()
    direct: set[str] = set()

    changed = True
    while changed:
        changed = False
        owners = (root.distribution_name, *sorted(reachable))
        for owner_name in owners:
            owner_extras = activated_extras.setdefault(owner_name, set())
            marker_extras = ("", *sorted(owner_extras))
            for requirement_index, requirement in enumerate(requirements[owner_name]):
                if not _requirement_is_active(
                    requirement,
                    environment=target_environment,
                    extras=marker_extras,
                    path=f"/requires_dist/{owner_name}/{requirement_index}",
                ):
                    continue
                if requirement.url is not None:
                    _fail(
                        "dependency_lock_active_direct_url_unsupported",
                        f"/requires_dist/{owner_name}/{requirement_index}",
                    )
                target_name = canonicalize_name(requirement.name)
                target = available.get(target_name)
                if target is None:
                    _fail(
                        "dependency_lock_dependency_missing",
                        f"/requires_dist/{owner_name}/{requirement_index}",
                        target_name,
                    )
                try:
                    satisfies = requirement.specifier.contains(
                        Version(target.distribution_version),
                        prereleases=None,
                    )
                except (InvalidVersion, InvalidSpecifier) as exc:
                    _fail(
                        "dependency_lock_requirement_version_invalid",
                        f"/requires_dist/{owner_name}/{requirement_index}",
                        type(exc).__name__,
                    )
                if not satisfies:
                    _fail(
                        "dependency_lock_requirement_version_mismatch",
                        f"/requires_dist/{owner_name}/{requirement_index}",
                        f"{target_name}=={target.distribution_version}",
                    )
                if owner_name == root.distribution_name and target_name != owner_name:
                    direct.add(target_name)
                if (
                    target_name != root.distribution_name
                    and target_name not in reachable
                ):
                    reachable.add(target_name)
                    changed = True
                requested_extras = {
                    canonicalize_name(extra) for extra in requirement.extras
                }
                target_extras = activated_extras.setdefault(target_name, set())
                if not requested_extras.issubset(target_extras):
                    target_extras.update(requested_extras)
                    changed = True
    return direct, reachable


def _parse_requirements(
    values: Sequence[str], *, owner: str
) -> tuple[Requirement, ...]:
    result: list[Requirement] = []
    for index, value in enumerate(values):
        try:
            requirement = Requirement(value)
        except InvalidRequirement as exc:
            _fail(
                "dependency_lock_requires_dist_invalid",
                f"/requires_dist/{owner}/{index}",
                type(exc).__name__,
            )
        if value != _canonical_requirement_text(requirement):
            _fail(
                "dependency_lock_requires_dist_noncanonical",
                f"/requires_dist/{owner}/{index}",
            )
        result.append(requirement)
    return tuple(result)


def _canonical_requirement_text(requirement: Requirement) -> str:
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


def _requirement_is_active(
    requirement: Requirement,
    *,
    environment: Mapping[str, str],
    extras: Sequence[str],
    path: str,
) -> bool:
    if requirement.marker is None:
        return True
    for extra in extras:
        marker_environment = dict(environment)
        marker_environment["extra"] = extra
        try:
            if requirement.marker.evaluate(environment=marker_environment):
                return True
        except (UndefinedEnvironmentName, KeyError, ValueError) as exc:
            _fail("dependency_lock_marker_evaluation_failed", path, type(exc).__name__)
    return False


def _validate_receipt_artifact(
    artifact: DependencyLockArtifactV1,
    *,
    path: str,
) -> None:
    if type(artifact) is not DependencyLockArtifactV1:
        _fail("dependency_lock_receipt_artifact_type_invalid", path)
    _validate_canonical_name(artifact.name, f"{path}/name")
    _validate_canonical_version(artifact.version, f"{path}/version")
    _validate_safe_filename(artifact.filename, f"{path}/filename")
    if type(artifact.byte_count) is not int or artifact.byte_count <= 0:
        _fail("dependency_lock_receipt_artifact_invalid", f"{path}/byte_count")
    _validate_sha256(artifact.sha256, f"{path}/sha256")
    _validate_sha256(artifact.wheel_identity_hash, f"{path}/wheel_identity_hash")
    if type(artifact.direct) is not bool:
        _fail("dependency_lock_receipt_artifact_invalid", f"{path}/direct")
    if type(artifact.requires_dist) is not tuple or any(
        type(value) is not str for value in artifact.requires_dist
    ):
        _fail("dependency_lock_receipt_artifact_invalid", f"{path}/requires_dist")
    _parse_requirements(artifact.requires_dist, owner=artifact.name)


def _receipt_artifact_payload(artifact: DependencyLockArtifactV1) -> dict[str, Any]:
    return {
        "name": artifact.name,
        "version": artifact.version,
        "filename": artifact.filename,
        "byte_count": artifact.byte_count,
        "sha256": artifact.sha256,
        "direct": artifact.direct,
        "requires_dist": list(artifact.requires_dist),
        "wheel_identity_hash": artifact.wheel_identity_hash,
    }


def _receipt_payload(
    receipt: DependencyLockReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "status": receipt.status,
        "lock_hash": receipt.lock_hash,
        "lock_bytes_sha256": receipt.lock_bytes_sha256,
        "target_environment": dict(receipt.target_environment),
        "target_environment_hash": receipt.target_environment_hash,
        "root": {
            "distribution_name": receipt.root_distribution_name,
            "distribution_version": receipt.root_distribution_version,
            "filename": receipt.root_filename,
            "byte_count": receipt.root_byte_count,
            "sha256": receipt.root_sha256,
            "requires_dist": list(receipt.root_requires_dist),
            "wheel_identity_hash": receipt.root_wheel_identity_hash,
        },
        "artifact_count": receipt.artifact_count,
        "artifacts": [
            _receipt_artifact_payload(artifact) for artifact in receipt.artifacts
        ],
        "artifact_aggregate_hash": receipt.artifact_aggregate_hash,
        "direct_dependency_names": list(receipt.direct_dependency_names),
        "transitive_dependency_names": list(receipt.transitive_dependency_names),
        "root_requirements_matched": receipt.root_requirements_matched,
        "transitive_closure_matched": receipt.transitive_closure_matched,
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _validate_canonical_name(value: Any, path: str) -> None:
    if (
        type(value) is not str
        or not _CANONICAL_NAME_RE.fullmatch(value)
        or canonicalize_name(value) != value
    ):
        _fail("dependency_lock_distribution_name_alias", path)


def _validate_canonical_version(value: Any, path: str) -> None:
    if type(value) is not str:
        _fail("dependency_lock_distribution_version_invalid", path)
    try:
        canonical = str(Version(value))
    except InvalidVersion as exc:
        _fail(
            "dependency_lock_distribution_version_invalid",
            path,
            type(exc).__name__,
        )
    if canonical != value:
        _fail("dependency_lock_distribution_version_alias", path)


def _validate_safe_filename(value: Any, path: str) -> None:
    if (
        type(value) is not str
        or not _SAFE_WHEEL_FILENAME_RE.fullmatch(value)
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or Path(value).name != value
    ):
        _fail("dependency_lock_artifact_filename_unsafe", path)


def _validate_sha256(value: Any, path: str) -> None:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        _fail("dependency_lock_sha256_invalid", path)


def _reject_nonfinite(value: Any, *, path: str) -> None:
    if type(value) is float and not math.isfinite(value):
        _fail("dependency_lock_json_nonfinite", path)
    if type(value) is dict:
        for key, item in value.items():
            _reject_nonfinite(item, path=f"{path}/{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_nonfinite(item, path=f"{path}/{index}")


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise DependencyLockV1Error(code, path, message)


__all__ = [
    "DEPENDENCY_LOCK_RECEIPT_SCHEMA_VERSION_V1",
    "DEPENDENCY_LOCK_SCHEMA_VERSION_V1",
    "DependencyLockArtifactV1",
    "DependencyLockClaimsV1",
    "DependencyLockReceiptV1",
    "DependencyLockV1Error",
    "validate_dependency_lock_receipt_v1",
    "validate_dependency_lock_v1",
    "verify_dependency_artifact_lock_v1",
]
