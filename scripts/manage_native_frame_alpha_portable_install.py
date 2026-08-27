#!/usr/bin/env python3
"""Manage a verified local Frame Alpha workstation installation.

The tool deliberately has no network client.  It accepts only a local workstation
ZIP, delegates the complete archive smoke to the distribution verifier, stages a
content-bound immutable version, and atomically replaces ``current.json`` as the
single activation commit point.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import errno
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
from typing import Any, Iterator, Sequence
import uuid
import zipfile

if os.name == "nt":  # pragma: no cover - exercised by the Windows clean runner
    import msvcrt
else:
    import fcntl


ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_SCRIPT = ROOT / "scripts" / "build_native_frame_alpha_distribution.py"
STATE_SCHEMA_VERSION = "structural-frame-alpha-portable-install-state.v1"
VERSION_SCHEMA_VERSION = "structural-frame-alpha-retained-version.v1"
WORKSTATION_MANIFEST_SCHEMA = "structural-frame-alpha-workstation-distribution.v2"
PLATFORMS = ("linux-x86_64-gnu", "windows-x86_64-msvc")
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_HISTORY_ROWS = 256
DESCRIPTOR_NAME = ".structural-retained-version.json"
CURRENT_NAME = "current.json"
LOCK_NAME = ".structural-portable-install.lock"
LOCK_TIMEOUT_SECONDS = 15.0
LOCK_POLL_SECONDS = 0.05
AUTHORITY = {
    "local_archive_verification": "required_before_installation_mutation",
    "immutable_version_storage": "content_bound_no_overwrite_verified_on_use",
    "current_activation": "atomic_local_pointer",
    "downgrade": "rejected_unless_explicitly_allowed",
    "rollback": "explicit_retained_verified_version_only",
    "network_auto_update": "not_implemented",
    "os_code_signing": "not_established",
    "engineering_design": "not_authoritative",
    "commercial_use": "not_authoritative",
    "release_readiness": "not_authoritative",
}
GATES = {
    "all_retained_archives_verified_before_installation_mutation": True,
    "active_payload_hash_verified": True,
    "version_overwrite_forbidden": True,
    "current_pointer_atomic_replace": True,
}
CLAIM_BOUNDARY = (
    "verified_local_source_bound_workstation_zip_install_update_and_explicit_"
    "retained_version_rollback_not_network_auto_update_os_code_signing_or_"
    "release_authority"
)


class PortableInstallError(RuntimeError):
    """Raised when an install-state operation must fail closed."""


def _try_acquire_file_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":  # pragma: no cover - exercised by the Windows clean runner
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_file_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":  # pragma: no cover - exercised by the Windows clean runner
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def _installation_lock(
    root: Path,
    *,
    create_root: bool,
    timeout_seconds: float | None = None,
) -> Iterator[None]:
    """Serialize all state reads and mutations for one installation root."""

    timeout = LOCK_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise PortableInstallError("installation_lock_timeout_invalid")
    if root.is_symlink():
        raise PortableInstallError("install_root_symlink_forbidden")
    if root.exists() and not root.is_dir():
        raise PortableInstallError("install_root_not_directory")
    if not root.exists():
        if not create_root:
            raise PortableInstallError("installation_missing")
        root.mkdir(parents=True, exist_ok=False)
    if root.is_symlink() or not root.is_dir():
        raise PortableInstallError("install_root_invalid")

    lock_path = root / LOCK_NAME
    if lock_path.is_symlink():
        raise PortableInstallError("installation_lock_symlink_forbidden")
    flags = os.O_RDWR | os.O_CREAT
    for optional_flag in ("O_BINARY", "O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= int(getattr(os, optional_flag, 0))
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise PortableInstallError("installation_lock_open_failed") from error

    acquired = False
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise PortableInstallError("installation_lock_not_private_regular_file")
        if opened.st_size == 0:
            os.write(descriptor, b"\x00")
            os.fsync(descriptor)

        deadline = time.monotonic() + float(timeout)
        busy_errors = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        while True:
            try:
                _try_acquire_file_lock(descriptor)
                acquired = True
                break
            except OSError as error:
                if error.errno not in busy_errors:
                    raise PortableInstallError("installation_lock_acquire_failed") from error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PortableInstallError("installation_lock_timeout") from error
                time.sleep(min(LOCK_POLL_SECONDS, remaining))

        observed = os.stat(lock_path, follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_dev != opened.st_dev
            or observed.st_ino != opened.st_ino
        ):
            raise PortableInstallError("installation_lock_identity_changed")
        yield
    finally:
        if acquired:
            try:
                _release_file_lock(descriptor)
            except OSError:
                # Closing the descriptor releases either platform's process lock.
                pass
        os.close(descriptor)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_object(value: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise PortableInstallError(f"{label}_duplicate_key:{key}")
            result[key] = item
        return result

    try:
        payload = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                PortableInstallError(f"{label}_nonfinite:{token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortableInstallError(f"{label}_invalid_json") from error
    if not isinstance(payload, dict):
        raise PortableInstallError(f"{label}_must_be_object")
    return payload


def _load_distribution_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_native_frame_alpha_distribution_portable_install",
        DISTRIBUTION_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise PortableInstallError("distribution_verifier_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git_sha(value: object, label: str) -> str:
    text = str(value)
    if re.fullmatch(r"[0-9a-f]{40}", text) is None:
        raise PortableInstallError(f"{label}_invalid")
    return text


def _sha256(value: object, label: str) -> str:
    text = str(value)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", text) is None:
        raise PortableInstallError(f"{label}_invalid")
    return text


def _semantic_version(value: object, label: str) -> tuple[int, int, int]:
    text = str(value)
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", text)
    if match is None:
        raise PortableInstallError(f"{label}_invalid")
    return tuple(int(item) for item in match.groups())


def _version_key(package_version: str, platform_tag: str, source_commit: str) -> str:
    _semantic_version(package_version, "package_version")
    if platform_tag not in PLATFORMS:
        raise PortableInstallError("platform_tag_invalid")
    _git_sha(source_commit, "source_commit")
    return f"v{package_version}--{platform_tag}--{source_commit}"


def _safe_relative_path(value: object, label: str) -> str:
    text = str(value)
    pure = PurePosixPath(text)
    if (
        not text
        or "\\" in text
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise PortableInstallError(f"{label}_unsafe")
    return pure.as_posix()


def _manifest_hash(manifest: dict[str, Any]) -> str:
    body = deepcopy(manifest)
    body.pop("schema_version", None)
    body.pop("manifest_hash", None)
    return _sha256_bytes(_canonical_bytes(body))


def _file_stats(root: Path) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise PortableInstallError("retained_version_root_invalid")
    digest = hashlib.sha256()
    count = 0
    byte_length = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PortableInstallError("retained_version_symlink_forbidden")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PortableInstallError("retained_version_entry_invalid")
        relative = path.relative_to(root).as_posix()
        if relative == DESCRIPTOR_NAME:
            continue
        content = path.read_bytes()
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        count += 1
        byte_length += len(content)
    if count < 2 or byte_length < 1:
        raise PortableInstallError("retained_version_payload_empty")
    return {
        "tree_sha256": "sha256:" + digest.hexdigest(),
        "file_count": count,
        "byte_length": byte_length,
    }


def _descriptor_hash(descriptor: dict[str, Any]) -> str:
    body = deepcopy(descriptor)
    body.pop("descriptor_hash", None)
    body.pop("schema_version", None)
    return _sha256_bytes(_canonical_bytes(body))


def _descriptor_bytes(descriptor: dict[str, Any]) -> bytes:
    return _canonical_bytes(descriptor) + b"\n"


def _state_hash(state: dict[str, Any]) -> str:
    body = deepcopy(state)
    body.pop("state_hash", None)
    body.pop("schema_version", None)
    return _sha256_bytes(_canonical_bytes(body))


def _state_bytes(state: dict[str, Any]) -> bytes:
    return _canonical_bytes(state) + b"\n"


def _validate_source(source: object, label: str) -> dict[str, str]:
    if not isinstance(source, dict) or set(source) != {
        "commit_sha",
        "tree_sha",
        "binding_profile",
    }:
        raise PortableInstallError(f"{label}_invalid")
    if source.get("binding_profile") != "verified_clean_git_checkout.v1":
        raise PortableInstallError(f"{label}_binding_profile_invalid")
    return {
        "commit_sha": _git_sha(source.get("commit_sha"), f"{label}_commit"),
        "tree_sha": _git_sha(source.get("tree_sha"), f"{label}_tree"),
        "binding_profile": "verified_clean_git_checkout.v1",
    }


def _summary_from_descriptor(
    descriptor: dict[str, Any], *, descriptor_file_sha256: str
) -> dict[str, Any]:
    return {
        "version_key": descriptor["version_key"],
        "relative_path": f"versions/{descriptor['version_key']}",
        "package": descriptor["package"],
        "source": descriptor["source"],
        "payload": descriptor["payload"],
        "descriptor_hash": descriptor["descriptor_hash"],
        "descriptor_file_sha256": descriptor_file_sha256,
    }


def _validate_version_summary(summary: object, label: str) -> dict[str, Any]:
    if not isinstance(summary, dict) or set(summary) != {
        "version_key",
        "relative_path",
        "package",
        "source",
        "payload",
        "descriptor_hash",
        "descriptor_file_sha256",
    }:
        raise PortableInstallError(f"{label}_fields_invalid")
    package = summary.get("package")
    if not isinstance(package, dict) or set(package) != {
        "package_id",
        "package_version",
        "platform_tag",
        "manifest_hash",
        "archive_sha256",
        "archive_byte_length",
    }:
        raise PortableInstallError(f"{label}_package_invalid")
    platform_tag = str(package.get("platform_tag"))
    if platform_tag not in PLATFORMS:
        raise PortableInstallError(f"{label}_platform_invalid")
    package_version = str(package.get("package_version"))
    _semantic_version(package_version, f"{label}_package_version")
    expected_id = f"structural-frame-alpha-workstation-{package_version}-{platform_tag}"
    if package.get("package_id") != expected_id:
        raise PortableInstallError(f"{label}_package_id_invalid")
    _sha256(package.get("manifest_hash"), f"{label}_manifest_hash")
    _sha256(package.get("archive_sha256"), f"{label}_archive_hash")
    if not isinstance(package.get("archive_byte_length"), int) or not (
        1 <= int(package["archive_byte_length"]) <= MAX_ARCHIVE_BYTES
    ):
        raise PortableInstallError(f"{label}_archive_length_invalid")
    source = _validate_source(summary.get("source"), f"{label}_source")
    expected_key = _version_key(package_version, platform_tag, source["commit_sha"])
    if summary.get("version_key") != expected_key:
        raise PortableInstallError(f"{label}_version_key_invalid")
    if summary.get("relative_path") != f"versions/{expected_key}":
        raise PortableInstallError(f"{label}_relative_path_invalid")
    payload = summary.get("payload")
    if not isinstance(payload, dict) or set(payload) != {
        "tree_sha256",
        "file_count",
        "byte_length",
    }:
        raise PortableInstallError(f"{label}_payload_invalid")
    _sha256(payload.get("tree_sha256"), f"{label}_payload_hash")
    if not isinstance(payload.get("file_count"), int) or int(payload["file_count"]) < 2:
        raise PortableInstallError(f"{label}_file_count_invalid")
    if (
        not isinstance(payload.get("byte_length"), int)
        or int(payload["byte_length"]) < 1
    ):
        raise PortableInstallError(f"{label}_byte_length_invalid")
    _sha256(summary.get("descriptor_hash"), f"{label}_descriptor_hash")
    _sha256(summary.get("descriptor_file_sha256"), f"{label}_descriptor_file_hash")
    return summary


def _build_descriptor(
    *,
    package: dict[str, Any],
    source: dict[str, str],
    payload: dict[str, object],
) -> tuple[dict[str, Any], dict[str, Any]]:
    key = _version_key(
        str(package["package_version"]),
        str(package["platform_tag"]),
        source["commit_sha"],
    )
    body: dict[str, Any] = {
        "schema_version": VERSION_SCHEMA_VERSION,
        "version_key": key,
        "package": package,
        "source": source,
        "payload": payload,
        "verification": {
            "archive_verified_before_installation_mutation": True,
            "manifest_and_file_hashes_verified": True,
            "immutable_storage_profile": (
                "content_bound_no_overwrite_verified_on_use.v1"
            ),
        },
        "authority": AUTHORITY,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    descriptor = {
        "schema_version": body.pop("schema_version"),
        "descriptor_hash": _descriptor_hash(body),
        **body,
    }
    encoded = _descriptor_bytes(descriptor)
    return descriptor, _summary_from_descriptor(
        descriptor, descriptor_file_sha256=_sha256_bytes(encoded)
    )


def _validate_descriptor(descriptor: dict[str, Any]) -> None:
    if set(descriptor) != {
        "schema_version",
        "descriptor_hash",
        "version_key",
        "package",
        "source",
        "payload",
        "verification",
        "authority",
        "claim_boundary",
    }:
        raise PortableInstallError("retained_descriptor_fields_invalid")
    if (
        descriptor.get("schema_version") != VERSION_SCHEMA_VERSION
        or descriptor.get("descriptor_hash") != _descriptor_hash(descriptor)
        or descriptor.get("authority") != AUTHORITY
        or descriptor.get("claim_boundary") != CLAIM_BOUNDARY
        or descriptor.get("verification")
        != {
            "archive_verified_before_installation_mutation": True,
            "manifest_and_file_hashes_verified": True,
            "immutable_storage_profile": (
                "content_bound_no_overwrite_verified_on_use.v1"
            ),
        }
    ):
        raise PortableInstallError("retained_descriptor_contract_invalid")
    encoded = _descriptor_bytes(descriptor)
    _validate_version_summary(
        _summary_from_descriptor(
            descriptor, descriptor_file_sha256=_sha256_bytes(encoded)
        ),
        "retained_descriptor",
    )


def _verify_version_directory(version_root: Path, summary: dict[str, Any]) -> None:
    if version_root.is_symlink() or not version_root.is_dir():
        raise PortableInstallError("retained_version_missing")
    descriptor_path = version_root / DESCRIPTOR_NAME
    if descriptor_path.is_symlink() or not descriptor_path.is_file():
        raise PortableInstallError("retained_descriptor_missing")
    descriptor_bytes = descriptor_path.read_bytes()
    if _sha256_bytes(descriptor_bytes) != summary["descriptor_file_sha256"]:
        raise PortableInstallError("retained_descriptor_file_hash_mismatch")
    descriptor = _load_object(descriptor_bytes, "retained_descriptor")
    _validate_descriptor(descriptor)
    expected = _summary_from_descriptor(
        descriptor, descriptor_file_sha256=_sha256_bytes(descriptor_bytes)
    )
    if expected != summary:
        raise PortableInstallError("retained_descriptor_summary_mismatch")
    if _file_stats(version_root) != summary["payload"]:
        raise PortableInstallError("retained_payload_hash_mismatch")


def _verify_retained_version(root: Path, summary: dict[str, Any]) -> None:
    _validate_version_summary(summary, "retained_summary")
    _verify_version_directory(
        root / Path(str(summary["relative_path"])),
        summary,
    )


def _validate_transition(row: object, expected_revision: int) -> None:
    if not isinstance(row, dict) or set(row) != {
        "revision",
        "operation",
        "from_version_key",
        "to_version_key",
        "package_version",
        "source_commit_sha",
        "archive_sha256",
        "payload_tree_sha256",
        "downgrade_policy",
    }:
        raise PortableInstallError("install_history_row_invalid")
    if row.get("revision") != expected_revision:
        raise PortableInstallError("install_history_revision_invalid")
    if row.get("operation") not in {"install", "update", "rollback"}:
        raise PortableInstallError("install_history_operation_invalid")
    if (
        row.get("from_version_key") is not None
        and re.fullmatch(
            r"v[0-9]+\.[0-9]+\.[0-9]+--(?:linux-x86_64-gnu|windows-x86_64-msvc)--[0-9a-f]{40}",
            str(row.get("from_version_key")),
        )
        is None
    ):
        raise PortableInstallError("install_history_from_version_invalid")
    if (
        re.fullmatch(
            r"v[0-9]+\.[0-9]+\.[0-9]+--(?:linux-x86_64-gnu|windows-x86_64-msvc)--[0-9a-f]{40}",
            str(row.get("to_version_key")),
        )
        is None
    ):
        raise PortableInstallError("install_history_to_version_invalid")
    _semantic_version(row.get("package_version"), "install_history_package_version")
    _git_sha(row.get("source_commit_sha"), "install_history_source_commit")
    _sha256(row.get("archive_sha256"), "install_history_archive_hash")
    _sha256(row.get("payload_tree_sha256"), "install_history_payload_hash")
    if row.get("downgrade_policy") not in {
        "not_applicable",
        "monotonic_or_same_version_source_update",
        "explicit_allow_downgrade",
        "explicit_retained_version_rollback",
    }:
        raise PortableInstallError("install_history_downgrade_policy_invalid")


def _validate_state(
    state: dict[str, Any], root: Path, *, verify_payloads: bool
) -> None:
    if set(state) != {
        "schema_version",
        "status",
        "state_hash",
        "installation_profile",
        "revision",
        "active_version_key",
        "active_version",
        "known_versions",
        "history",
        "gates",
        "authority",
        "claim_boundary",
    }:
        raise PortableInstallError("install_state_fields_invalid")
    if (
        state.get("schema_version") != STATE_SCHEMA_VERSION
        or state.get("status") != "pass"
        or state.get("installation_profile")
        != "source_bound_portable_workstation_local.v1"
        or state.get("authority") != AUTHORITY
        or state.get("gates") != GATES
        or state.get("claim_boundary") != CLAIM_BOUNDARY
        or state.get("state_hash") != _state_hash(state)
    ):
        raise PortableInstallError("install_state_contract_invalid")
    known = state.get("known_versions")
    history = state.get("history")
    if (
        not isinstance(known, list)
        or not known
        or len(known) > MAX_HISTORY_ROWS
        or not isinstance(history, list)
        or not history
        or len(history) > MAX_HISTORY_ROWS
        or state.get("revision") != len(history)
    ):
        raise PortableInstallError("install_state_cardinality_invalid")
    keys: list[str] = []
    summaries_by_key: dict[str, dict[str, Any]] = {}
    for index, summary in enumerate(known):
        validated = _validate_version_summary(summary, f"known_version_{index}")
        keys.append(str(validated["version_key"]))
        summaries_by_key[str(validated["version_key"])] = validated
        if verify_payloads:
            _verify_retained_version(root, validated)
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise PortableInstallError("known_version_order_invalid")
    if state.get("active_version_key") not in keys:
        raise PortableInstallError("active_version_key_unknown")
    active = next(
        row for row in known if row["version_key"] == state["active_version_key"]
    )
    if state.get("active_version") != active:
        raise PortableInstallError("active_version_summary_mismatch")
    if len({row["package"]["platform_tag"] for row in known}) != 1:
        raise PortableInstallError("known_version_platform_mismatch")
    previous_key: str | None = None
    transitioned_keys: set[str] = set()
    for revision, row in enumerate(history, start=1):
        _validate_transition(row, revision)
        operation = str(row["operation"])
        if revision == 1:
            if (
                operation != "install"
                or row["from_version_key"] is not None
                or row["downgrade_policy"] != "not_applicable"
            ):
                raise PortableInstallError("install_history_initial_transition_invalid")
        elif operation == "install" or row["from_version_key"] != previous_key:
            raise PortableInstallError("install_history_lineage_invalid")
        target = summaries_by_key.get(str(row["to_version_key"]))
        if target is None or (
            row["package_version"] != target["package"]["package_version"]
            or row["source_commit_sha"] != target["source"]["commit_sha"]
            or row["archive_sha256"] != target["package"]["archive_sha256"]
            or row["payload_tree_sha256"] != target["payload"]["tree_sha256"]
        ):
            raise PortableInstallError("install_history_target_binding_invalid")
        policy = str(row["downgrade_policy"])
        if operation == "rollback" and policy != "explicit_retained_version_rollback":
            raise PortableInstallError("install_history_rollback_policy_invalid")
        if operation == "update" and policy not in {
            "monotonic_or_same_version_source_update",
            "explicit_allow_downgrade",
        }:
            raise PortableInstallError("install_history_update_policy_invalid")
        previous_key = str(row["to_version_key"])
        transitioned_keys.add(previous_key)
    if transitioned_keys != set(keys):
        raise PortableInstallError("known_version_history_mismatch")
    if history[-1]["to_version_key"] != state["active_version_key"]:
        raise PortableInstallError("install_history_active_mismatch")


def _load_state(
    root: Path, *, verify_payloads: bool = True
) -> tuple[dict[str, Any] | None, bytes | None]:
    if root.is_symlink():
        raise PortableInstallError("install_root_symlink_forbidden")
    current = root / CURRENT_NAME
    if current.is_symlink():
        raise PortableInstallError("current_pointer_symlink_forbidden")
    if not current.exists():
        return None, None
    if not current.is_file():
        raise PortableInstallError("current_pointer_not_regular")
    encoded = current.read_bytes()
    state = _load_object(encoded, "install_state")
    _validate_state(state, root, verify_payloads=verify_payloads)
    if encoded != _state_bytes(state):
        raise PortableInstallError("install_state_not_canonical")
    return state, encoded


def _verified_archive_to_staging(
    *,
    archive_path: Path,
    expected_source_commit: str,
    expected_platform_tag: str,
    staging_parent: Path,
) -> tuple[Path, dict[str, Any]]:
    expected_source_commit = _git_sha(expected_source_commit, "expected_source_commit")
    if expected_platform_tag not in PLATFORMS:
        raise PortableInstallError("expected_platform_tag_invalid")
    if archive_path.is_symlink() or not archive_path.is_file():
        raise PortableInstallError("archive_must_be_regular_file")
    archive_bytes = archive_path.read_bytes()
    if not 0 < len(archive_bytes) <= MAX_ARCHIVE_BYTES:
        raise PortableInstallError("archive_size_invalid")

    # The distribution verifier executes the packaged CLI.  Give it a private
    # snapshot of the captured bytes so a concurrent replacement of the caller's
    # path cannot change which binary is verified or executed.
    verification_archive = staging_parent / f".verification-{uuid.uuid4().hex}.zip"
    with verification_archive.open("xb") as stream:
        stream.write(archive_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    verification_archive.chmod(0o400)

    distribution = _load_distribution_module()
    try:
        smoke = distribution.verify_workstation_distribution(
            archive_path=verification_archive
        )
    except Exception as error:
        raise PortableInstallError(
            f"archive_verification_failed:{type(error).__name__}:{error}"
        ) from error
    if (
        verification_archive.read_bytes() != archive_bytes
        or archive_path.read_bytes() != archive_bytes
    ):
        raise PortableInstallError("archive_changed_during_verification")
    source = _validate_source(smoke.get("source"), "verified_smoke_source")
    if (
        smoke.get("status") != "pass"
        or smoke.get("platform_tag") != expected_platform_tag
        or source["commit_sha"] != expected_source_commit
    ):
        raise PortableInstallError("archive_source_or_platform_mismatch")

    # Extract the exact byte sequence that passed the verifier.  Reopening the
    # path here would leave a swap window between verification and extraction.
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r")
    except zipfile.BadZipFile as error:
        raise PortableInstallError("archive_invalid") from error
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise PortableInstallError("archive_duplicate_path")
        manifest_names = [name for name in names if name.endswith("/manifest.json")]
        if len(manifest_names) != 1:
            raise PortableInstallError("archive_manifest_count_invalid")
        manifest_name = manifest_names[0]
        manifest = _load_object(archive.read(manifest_name), "workstation_manifest")
        root_parts = PurePosixPath(manifest_name).parts
        if (
            len(root_parts) != 2
            or root_parts[1] != "manifest.json"
            or _safe_relative_path(root_parts[0], "archive_root") != root_parts[0]
        ):
            raise PortableInstallError("archive_manifest_path_invalid")
        archive_root = root_parts[0]
        package_version = str(manifest.get("package_version"))
        _semantic_version(package_version, "manifest_package_version")
        package_id = str(manifest.get("package_id"))
        if (
            manifest.get("schema_version") != WORKSTATION_MANIFEST_SCHEMA
            or package_id
            != f"structural-frame-alpha-workstation-{package_version}-{expected_platform_tag}"
            or archive_root != package_id
            or manifest.get("platform_tag") != expected_platform_tag
            or _validate_source(manifest.get("source"), "manifest_source") != source
            or manifest.get("manifest_hash") != _manifest_hash(manifest)
            or smoke.get("manifest_hash") != manifest.get("manifest_hash")
        ):
            raise PortableInstallError("archive_manifest_binding_invalid")
        rows = manifest.get("files")
        if not isinstance(rows, list) or not rows:
            raise PortableInstallError("archive_manifest_files_invalid")
        indexed: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise PortableInstallError("archive_manifest_file_row_invalid")
            relative = _safe_relative_path(row.get("path"), "manifest_file_path")
            if relative == DESCRIPTOR_NAME or relative in indexed:
                raise PortableInstallError("archive_manifest_file_inventory_invalid")
            if (
                not isinstance(row.get("byte_length"), int)
                or int(row["byte_length"]) < 1
                or not isinstance(row.get("executable"), bool)
            ):
                raise PortableInstallError("archive_manifest_file_metadata_invalid")
            _sha256(row.get("sha256"), "manifest_file_hash")
            indexed[relative] = row
        expected_names = {f"{archive_root}/{path}" for path in indexed} | {
            manifest_name
        }
        if set(names) != expected_names:
            raise PortableInstallError("archive_inventory_invalid")
        package_root = staging_parent / archive_root
        package_root.mkdir(parents=True)
        for info in infos:
            parts = PurePosixPath(info.filename).parts
            if (
                not parts
                or parts[0] != archive_root
                or any(part in {"", ".", ".."} for part in parts)
                or info.is_dir()
            ):
                raise PortableInstallError("archive_path_invalid")
            relative = PurePosixPath(*parts[1:]).as_posix()
            content = archive.read(info)
            if relative != "manifest.json":
                row = indexed.get(relative)
                if row is None or (
                    len(content) != row["byte_length"]
                    or _sha256_bytes(content) != row["sha256"]
                ):
                    raise PortableInstallError(
                        f"archive_file_binding_invalid:{relative}"
                    )
                executable = bool(row["executable"])
            else:
                executable = False
            target = package_root.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise PortableInstallError("archive_extraction_overwrite_forbidden")
            target.write_bytes(content)
            target.chmod(0o555 if executable else 0o444)

    payload = _file_stats(package_root)
    package = {
        "package_id": package_id,
        "package_version": package_version,
        "platform_tag": expected_platform_tag,
        "manifest_hash": str(manifest["manifest_hash"]),
        "archive_sha256": _sha256_bytes(archive_bytes),
        "archive_byte_length": len(archive_bytes),
    }
    descriptor, summary = _build_descriptor(
        package=package,
        source=source,
        payload=payload,
    )
    descriptor_path = package_root / DESCRIPTOR_NAME
    descriptor_path.write_bytes(_descriptor_bytes(descriptor))
    descriptor_path.chmod(0o444)
    return package_root, summary


def _make_transition(
    *,
    revision: int,
    operation: str,
    previous_key: str | None,
    target: dict[str, Any],
    downgrade_policy: str,
) -> dict[str, Any]:
    return {
        "revision": revision,
        "operation": operation,
        "from_version_key": previous_key,
        "to_version_key": target["version_key"],
        "package_version": target["package"]["package_version"],
        "source_commit_sha": target["source"]["commit_sha"],
        "archive_sha256": target["package"]["archive_sha256"],
        "payload_tree_sha256": target["payload"]["tree_sha256"],
        "downgrade_policy": downgrade_policy,
    }


def _build_state(
    *,
    previous: dict[str, Any] | None,
    target: dict[str, Any],
    operation: str,
    downgrade_policy: str,
) -> dict[str, Any]:
    if previous is None:
        known = [target]
        history: list[dict[str, Any]] = []
        previous_key = None
    else:
        known = list(previous["known_versions"])
        if target["version_key"] not in {row["version_key"] for row in known}:
            known.append(target)
        known.sort(key=lambda row: str(row["version_key"]))
        history = list(previous["history"])
        previous_key = str(previous["active_version_key"])
    if len(history) >= MAX_HISTORY_ROWS or len(known) > MAX_HISTORY_ROWS:
        raise PortableInstallError("install_state_history_limit_reached")
    history.append(
        _make_transition(
            revision=len(history) + 1,
            operation=operation,
            previous_key=previous_key,
            target=target,
            downgrade_policy=downgrade_policy,
        )
    )
    body: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "status": "pass",
        "installation_profile": "source_bound_portable_workstation_local.v1",
        "revision": len(history),
        "active_version_key": target["version_key"],
        "active_version": target,
        "known_versions": known,
        "history": history,
        "gates": GATES,
        "authority": AUTHORITY,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    state = {
        "schema_version": body.pop("schema_version"),
        "state_hash": _state_hash(body),
        **body,
    }
    return state


def _remove_version_tree(path: Path) -> None:
    if not path.exists():
        return
    directories = [path]
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            child.chmod(0o600)
        elif child.is_dir() and not child.is_symlink():
            directories.append(child)
    for directory in directories:
        directory.chmod(0o700)
    shutil.rmtree(path)


def _make_tree_read_only(path: Path) -> None:
    for child in path.rglob("*"):
        if child.is_dir() and not child.is_symlink():
            child.chmod(0o555)
    path.chmod(0o555)


def _retain_prepared_version(
    *, root: Path, prepared_root: Path, summary: dict[str, Any]
) -> bool:
    versions = root / "versions"
    if versions.is_symlink() or (versions.exists() and not versions.is_dir()):
        raise PortableInstallError("versions_root_invalid")
    versions.mkdir(parents=True, exist_ok=True)
    target = versions / str(summary["version_key"])
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_dir():
            raise PortableInstallError("retained_version_target_collision")
        _verify_retained_version(root, summary)
        return False
    staging = versions / f".staging-{uuid.uuid4().hex}"
    if staging.exists() or staging.is_symlink():
        raise PortableInstallError("retained_version_staging_collision")
    try:
        shutil.copytree(prepared_root, staging, symlinks=False)
        _verify_version_directory(staging, summary)
        _make_tree_read_only(staging)
        staging.rename(target)
    except Exception:
        _remove_version_tree(staging)
        raise
    return True


def _atomic_activate(
    *, root: Path, state: dict[str, Any], expected_previous: bytes | None
) -> None:
    encoded = _state_bytes(state)
    current = root / CURRENT_NAME
    observed = (
        current.read_bytes() if current.is_file() and not current.is_symlink() else None
    )
    if observed != expected_previous:
        raise PortableInstallError("current_pointer_changed_during_operation")
    temporary = root / f".{CURRENT_NAME}.partial-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, current)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_archive(
    *,
    operation: str,
    archive_path: Path,
    install_root: Path,
    expected_source_commit: str,
    expected_platform_tag: str,
    allow_downgrade: bool = False,
) -> dict[str, Any]:
    if operation not in {"install", "update"}:
        raise PortableInstallError("archive_operation_invalid")
    # The complete archive smoke, source binding, manifest binding, and extraction
    # all finish in an external temporary directory before install_root is mutated.
    with tempfile.TemporaryDirectory(prefix="frame-alpha-portable-install-") as text:
        prepared_root, target = _verified_archive_to_staging(
            archive_path=archive_path,
            expected_source_commit=expected_source_commit,
            expected_platform_tag=expected_platform_tag,
            staging_parent=Path(text),
        )
        with _installation_lock(
            install_root,
            create_root=operation == "install",
        ):
            previous, previous_bytes = _load_state(install_root)
            if operation == "install" and previous is not None:
                raise PortableInstallError("installation_already_initialized_use_update")
            if operation == "update" and previous is None:
                raise PortableInstallError("installation_missing_use_install")
            if previous is not None:
                active = previous["active_version"]
                if active["package"]["platform_tag"] != expected_platform_tag:
                    raise PortableInstallError("update_platform_mismatch")
                if active["version_key"] == target["version_key"]:
                    raise PortableInstallError("target_version_already_active")
                if target["version_key"] in {
                    row["version_key"] for row in previous["known_versions"]
                }:
                    raise PortableInstallError(
                        "target_previously_retained_use_rollback"
                    )
                target_version = _semantic_version(
                    target["package"]["package_version"], "target_package_version"
                )
                active_version = _semantic_version(
                    active["package"]["package_version"], "active_package_version"
                )
                downgrade = target_version < active_version
                if downgrade and not allow_downgrade:
                    raise PortableInstallError("downgrade_requires_explicit_allow")
                downgrade_policy = (
                    "explicit_allow_downgrade"
                    if downgrade
                    else "monotonic_or_same_version_source_update"
                )
            else:
                downgrade_policy = "not_applicable"

            state = _build_state(
                previous=previous,
                target=target,
                operation=operation,
                downgrade_policy=downgrade_policy,
            )
            created = _retain_prepared_version(
                root=install_root,
                prepared_root=prepared_root,
                summary=target,
            )
            try:
                _validate_state(state, install_root, verify_payloads=True)
                _atomic_activate(
                    root=install_root,
                    state=state,
                    expected_previous=previous_bytes,
                )
            except Exception:
                if created:
                    _remove_version_tree(
                        install_root / "versions" / str(target["version_key"])
                    )
                raise
    return state


def rollback(*, install_root: Path, target_version_key: str) -> dict[str, Any]:
    with _installation_lock(install_root, create_root=False):
        previous, previous_bytes = _load_state(install_root)
        if previous is None:
            raise PortableInstallError("installation_missing")
        if target_version_key == previous["active_version_key"]:
            raise PortableInstallError("rollback_target_already_active")
        candidates = {
            str(row["version_key"]): row for row in previous["known_versions"]
        }
        target = candidates.get(target_version_key)
        if target is None:
            raise PortableInstallError("rollback_target_not_previously_verified")
        _verify_retained_version(install_root, target)
        state = _build_state(
            previous=previous,
            target=target,
            operation="rollback",
            downgrade_policy="explicit_retained_version_rollback",
        )
        _validate_state(state, install_root, verify_payloads=True)
        _atomic_activate(
            root=install_root,
            state=state,
            expected_previous=previous_bytes,
        )
    return state


def verify_installation(*, install_root: Path) -> dict[str, Any]:
    with _installation_lock(install_root, create_root=False):
        state, _encoded = _load_state(install_root)
        if state is None:
            raise PortableInstallError("installation_missing")
    return state


def _print_state(state: dict[str, Any]) -> None:
    print(_canonical_bytes(state).decode("utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for name in ("install", "update"):
        command = subparsers.add_parser(name)
        command.add_argument("--archive", type=Path, required=True)
        command.add_argument("--install-root", type=Path, required=True)
        command.add_argument("--expected-source-commit", required=True)
        command.add_argument("--platform-tag", choices=PLATFORMS, required=True)
        if name == "update":
            command.add_argument("--allow-downgrade", action="store_true")
    rollback_command = subparsers.add_parser("rollback")
    rollback_command.add_argument("--install-root", type=Path, required=True)
    rollback_command.add_argument("--to-version", required=True)
    verify_command = subparsers.add_parser("verify")
    verify_command.add_argument("--install-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.operation in {"install", "update"}:
            state = apply_archive(
                operation=arguments.operation,
                archive_path=arguments.archive,
                install_root=arguments.install_root,
                expected_source_commit=arguments.expected_source_commit,
                expected_platform_tag=arguments.platform_tag,
                allow_downgrade=bool(getattr(arguments, "allow_downgrade", False)),
            )
        elif arguments.operation == "rollback":
            state = rollback(
                install_root=arguments.install_root,
                target_version_key=arguments.to_version,
            )
        else:
            state = verify_installation(install_root=arguments.install_root)
    except (OSError, PortableInstallError, shutil.Error, zipfile.BadZipFile) as error:
        print(f"Frame Alpha portable installation failed: {error}", file=sys.stderr)
        return 1
    _print_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
