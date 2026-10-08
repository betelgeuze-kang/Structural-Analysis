#!/usr/bin/env python3
"""Admit a canonical artifact only through one exact run attempt and archive."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.strict_json import StrictJSONError, strict_json_loads  # noqa: E402

SCHEMA_VERSION = "canonical-actions-artifact-identity.v1"
WORKFLOW_NAME = "P0 Canonical Verification Contract"
WORKFLOW_PATH = ".github/workflows/p0-canonical-contract.yml"
RECEIPT_PATH = "artifacts/manifests/canonical_verification_environment.current.v1.json"
CONTRACT_PATH = ".ci/canonical-project-wheel-contract.json"
WHEEL_PATH = ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl"
MEMBERS = frozenset({RECEIPT_PATH, CONTRACT_PATH, WHEEL_PATH})
MAX_ARCHIVE_BYTES = 200_000_000
MAX_MEMBER_BYTES = 100_000_000
MAX_METADATA_BYTES = 10_000_000
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SAFE_INTEGER = 9_007_199_254_740_991
API_IDENTITY_KEYS = (
    "id",
    "name",
    "digest",
    "size_in_bytes",
    "archive_download_url",
    "expired",
    "workflow_run",
    "created_at",
    "updated_at",
)


class CanonicalActionsArtifactError(ValueError):
    """An artifact or attempt contradicts the immutable canonical intake contract."""


def _require(condition: object, reason: str) -> None:
    if not condition:
        raise CanonicalActionsArtifactError(reason)


def _integer(value: Any, reason: str) -> int:
    _require(type(value) is int and 0 < value <= SAFE_INTEGER, reason)
    return value


def _object(raw: bytes, reason: str) -> dict[str, Any]:
    try:
        value = strict_json_loads(raw)
    except StrictJSONError as exc:
        raise CanonicalActionsArtifactError(reason) from exc
    _require(type(value) is dict, reason)
    return value


def _read_regular(
    path: Path, maximum: int, reason: str, expected_size: int | None = None
) -> bytes:
    metadata = path.lstat()
    _require(stat.S_ISREG(metadata.st_mode) and 0 < metadata.st_size <= maximum, reason)
    _require(expected_size is None or metadata.st_size == expected_size, reason)
    raw = path.read_bytes()
    _require(len(raw) == metadata.st_size, reason)
    return raw


def _timestamp(value: Any, reason: str) -> datetime:
    _require(type(value) is str and UTC_TIMESTAMP.fullmatch(value), reason)
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise CanonicalActionsArtifactError(reason) from exc


def artifact_name(source_sha: str, run_id: int, run_attempt: int) -> str:
    _require(
        type(source_sha) is str
        and SHA.fullmatch(source_sha)
        and source_sha != "0" * 40,
        "canonical_source_sha_invalid",
    )
    _integer(run_id, "canonical_run_id_invalid")
    _integer(run_attempt, "canonical_run_attempt_invalid")
    return f"canonical-verification-environment-{run_id}-{run_attempt}-{source_sha}"


def workflow_path_matches(path: Any) -> bool:
    if type(path) is not str:
        return False
    location, separator, ref = path.partition("@")
    return location == WORKFLOW_PATH and (
        not separator or bool(ref) and not any(character.isspace() for character in ref)
    )


def validate_run(
    run: dict[str, Any],
    *,
    repository: str,
    source_sha: str,
    run_id: int,
) -> str:
    _require(
        type(repository) is str and REPOSITORY.fullmatch(repository),
        "canonical_repository_invalid",
    )
    _integer(run_id, "canonical_run_id_invalid")
    _require(
        type(run) is dict and type(run.get("id")) is int and run.get("id") == run_id,
        "canonical_run_id_mismatch",
    )
    for key, expected in (
        ("name", WORKFLOW_NAME),
        ("head_branch", "main"),
        ("head_sha", source_sha),
        ("status", "completed"),
        ("conclusion", "success"),
    ):
        _require(run.get(key) == expected, "canonical_run_identity_invalid:" + key)
    _require(
        workflow_path_matches(run.get("path")), "canonical_run_identity_invalid:path"
    )
    _require(
        run.get("event") in {"push", "workflow_dispatch"}, "canonical_run_event_invalid"
    )
    _integer(run.get("run_number"), "canonical_run_number_invalid")
    attempt = _integer(run.get("run_attempt"), "canonical_run_attempt_invalid")
    for key in ("repository", "head_repository"):
        _require(
            type(run.get(key)) is dict and run[key].get("full_name") == repository,
            "canonical_run_repository_mismatch",
        )
        _integer(run[key].get("id"), "canonical_run_repository_id_invalid")
    started = _timestamp(run.get("run_started_at"), "canonical_run_started_at_invalid")
    updated = _timestamp(run.get("updated_at"), "canonical_run_updated_at_invalid")
    _require(started <= updated, "canonical_run_time_invalid")
    return artifact_name(source_sha, run_id, attempt)


def select_artifact(
    run: dict[str, Any],
    inventory: dict[str, Any],
    *,
    repository: str,
    source_sha: str,
    run_id: int,
) -> dict[str, Any]:
    expected_name = validate_run(
        run, repository=repository, source_sha=source_sha, run_id=run_id
    )
    rows = inventory.get("artifacts")
    _require(type(rows) is list, "canonical_artifact_inventory_invalid")
    _require(
        type(inventory.get("total_count")) is int
        and inventory["total_count"] == len(rows)
        and len(rows) <= 100,
        "canonical_artifact_inventory_incomplete",
    )
    matches = [
        row for row in rows if type(row) is dict and row.get("name") == expected_name
    ]
    _require(len(matches) == 1, "canonical_artifact_inventory_ambiguous")
    row = matches[0]
    _integer(row.get("id"), "canonical_artifact_id_invalid")
    return row


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _metadata(
    run: dict[str, Any],
    inventory: dict[str, Any],
    artifact: dict[str, Any],
    *,
    repository: str,
    source_sha: str,
    run_id: int,
    api_url: str,
) -> None:
    listed = select_artifact(
        run, inventory, repository=repository, source_sha=source_sha, run_id=run_id
    )
    for row in (listed, artifact):
        _require(type(row) is dict, "canonical_artifact_api_invalid")
        artifact_id = _integer(row.get("id"), "canonical_artifact_id_invalid")
        _require(
            type(row.get("digest")) is str and SHA256.fullmatch(row["digest"]),
            "canonical_artifact_digest_invalid",
        )
        size = _integer(row.get("size_in_bytes"), "canonical_artifact_size_invalid")
        _require(
            size <= MAX_ARCHIVE_BYTES and row.get("expired") is False,
            "canonical_artifact_unavailable",
        )
        _require(
            row.get("archive_download_url")
            == f"{api_url.rstrip('/')}/repos/{repository}/actions/artifacts/{artifact_id}/zip",
            "canonical_artifact_archive_url_invalid",
        )
        producer = row.get("workflow_run")
        _require(type(producer) is dict, "canonical_artifact_producer_run_mismatch")
        _integer(producer.get("id"), "canonical_artifact_producer_run_mismatch")
        _require(producer["id"] == run_id, "canonical_artifact_producer_run_mismatch")
        for key, run_key in (
            ("repository_id", "repository"),
            ("head_repository_id", "head_repository"),
        ):
            _integer(
                producer.get(key), "canonical_artifact_producer_repository_invalid"
            )
            _require(
                producer[key] == run[run_key]["id"],
                "canonical_artifact_producer_repository_invalid",
            )
        _require(
            producer.get("head_sha") == source_sha
            and producer.get("head_branch") == "main",
            "canonical_artifact_producer_source_mismatch",
        )
        created = _timestamp(
            row.get("created_at"), "canonical_artifact_created_at_invalid"
        )
        updated = _timestamp(
            row.get("updated_at"), "canonical_artifact_updated_at_invalid"
        )
        started = _timestamp(
            run.get("run_started_at"), "canonical_run_started_at_invalid"
        )
        completed = _timestamp(
            run.get("updated_at"), "canonical_run_updated_at_invalid"
        )
        _require(
            started <= created <= updated <= completed,
            "canonical_artifact_outside_attempt",
        )
    for key in API_IDENTITY_KEYS:
        _require(
            key in artifact and key in listed and artifact[key] == listed[key],
            "canonical_artifact_list_direct_mismatch:" + key,
        )


def _member_identity(files: dict[str, bytes], source_sha: str) -> None:
    receipt = _object(files[RECEIPT_PATH], "canonical_receipt_json_invalid")
    contract = _object(files[CONTRACT_PATH], "canonical_contract_json_invalid")
    _require(
        receipt.get("source_commit_sha") == source_sha
        and receipt.get("source_checkout_head_sha") == source_sha
        and contract.get("source_commit_sha") == source_sha,
        "canonical_archive_source_mismatch",
    )
    _require(
        receipt.get("project_wheel") == contract,
        "canonical_archive_wheel_contract_mismatch",
    )
    wheel = contract.get("wheel")
    _require(type(wheel) is dict, "canonical_archive_wheel_identity_invalid")
    _require(
        wheel.get("filename") == Path(WHEEL_PATH).name
        and type(wheel.get("byte_length")) is int
        and wheel["byte_length"] == len(files[WHEEL_PATH])
        and wheel.get("sha256") == _digest(files[WHEEL_PATH]),
        "canonical_archive_wheel_identity_invalid",
    )


def _identity(
    run: dict[str, Any],
    artifact: dict[str, Any],
    files: dict[str, bytes],
    repository: str,
    source_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "source_commit_sha": source_sha,
        "workflow_run": {
            key: run[key]
            for key in (
                "id",
                "run_number",
                "run_attempt",
                "name",
                "path",
                "event",
                "status",
                "conclusion",
                "head_branch",
                "head_sha",
                "run_started_at",
                "updated_at",
            )
        },
        "artifact": {key: artifact[key] for key in API_IDENTITY_KEYS},
        "archive_sha256": artifact["digest"],
        "archive_bytes": artifact["size_in_bytes"],
        "members": [
            {"path": path, "bytes": len(value), "sha256": _digest(value)}
            for path, value in sorted(files.items())
        ],
        "contract_pass": True,
        "claim_boundary": "Exact canonical run-attempt, immutable Actions artifact and archived byte identity only; no physical, release or freshness credit beyond this intake.",
    }


def _archive_members(raw: bytes) -> dict[str, bytes]:
    _require(0 < len(raw) <= MAX_ARCHIVE_BYTES, "canonical_archive_size_invalid")
    files: dict[str, bytes] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            rows = archive.infolist()
            _require(len(rows) == len(MEMBERS), "canonical_archive_member_set_invalid")
            for row in rows:
                _require(
                    row.filename in MEMBERS
                    and row.orig_filename == row.filename
                    and row.filename not in files,
                    "canonical_archive_member_set_invalid",
                )
                mode = (row.external_attr >> 16) & 0xFFFF
                _require(
                    not row.is_dir()
                    and not row.external_attr & 0x10
                    and stat.S_IFMT(mode) in {0, stat.S_IFREG}
                    and not row.flag_bits & 1
                    and row.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
                    "canonical_archive_member_type_invalid",
                )
                _require(
                    0 < row.file_size <= MAX_MEMBER_BYTES,
                    "canonical_archive_member_size_invalid",
                )
                total += row.file_size
                _require(
                    total <= MAX_ARCHIVE_BYTES, "canonical_archive_expansion_invalid"
                )
                value = archive.read(row)
                _require(
                    len(value) == row.file_size, "canonical_archive_member_size_changed"
                )
                files[row.filename] = value
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, CanonicalActionsArtifactError):
            raise
        raise CanonicalActionsArtifactError("canonical_archive_invalid") from exc
    _require(set(files) == MEMBERS, "canonical_archive_member_set_invalid")
    return files


def validate_artifact(
    *,
    run: dict[str, Any],
    inventory: dict[str, Any],
    artifact: dict[str, Any],
    archive: bytes,
    repository: str,
    source_sha: str,
    run_id: int,
    api_url: str = "https://api.github.com",
) -> tuple[dict[str, Any], dict[str, bytes]]:
    _metadata(
        run,
        inventory,
        artifact,
        repository=repository,
        source_sha=source_sha,
        run_id=run_id,
        api_url=api_url,
    )
    _require(
        len(archive) == artifact["size_in_bytes"]
        and _digest(archive) == artifact["digest"],
        "canonical_artifact_archive_digest_mismatch",
    )
    files = _archive_members(archive)
    _member_identity(files, source_sha)
    return _identity(run, artifact, files, repository, source_sha), files


def _safe_target(root: Path, relative: str) -> Path:
    root = root.absolute()
    _require(
        root.is_dir() and all(not path.is_symlink() for path in (root, *root.parents)),
        "canonical_materialize_root_unsafe",
    )
    target = root / relative
    for path in (*reversed(target.parents), target):
        if path == root or root in path.parents:
            _require(not path.is_symlink(), "canonical_materialize_target_unsafe")
            if path.exists():
                _require(
                    path.is_file() if path == target else path.is_dir(),
                    "canonical_materialize_target_unsafe",
                )
    return target


def validate_materialized(
    *,
    run: dict[str, Any],
    inventory: dict[str, Any],
    artifact: dict[str, Any],
    identity: dict[str, Any],
    materialize_root: Path,
    repository: str,
    source_sha: str,
    run_id: int,
    api_url: str = "https://api.github.com",
) -> None:
    """Replay sealed intake metadata and member bytes, without a new live API claim."""
    _metadata(
        run,
        inventory,
        artifact,
        repository=repository,
        source_sha=source_sha,
        run_id=run_id,
        api_url=api_url,
    )
    rows = identity.get("members")
    _require(
        type(rows) is list and len(rows) == len(MEMBERS),
        "canonical_materialized_member_identity_invalid",
    )
    expected_sizes = {}
    for row in rows:
        _require(
            type(row) is dict
            and type(row.get("path")) is str
            and row["path"] in MEMBERS
            and row["path"] not in expected_sizes,
            "canonical_materialized_member_identity_invalid",
        )
        size = _integer(row.get("bytes"), "canonical_materialized_member_size_invalid")
        _require(size <= MAX_MEMBER_BYTES, "canonical_materialized_member_size_invalid")
        expected_sizes[row["path"]] = size
    files = {
        relative: _read_regular(
            _safe_target(materialize_root, relative),
            MAX_MEMBER_BYTES,
            "canonical_materialized_member_size_invalid",
            expected_sizes[relative],
        )
        for relative in MEMBERS
    }
    _member_identity(files, source_sha)
    expected = _identity(run, artifact, files, repository, source_sha)
    _require(
        json.dumps(identity, sort_keys=True) == json.dumps(expected, sort_keys=True),
        "canonical_materialized_identity_mismatch",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "admit", "replay"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--materialize-root", type=Path)
    parser.add_argument("--identity-out", type=Path)
    args = parser.parse_args(argv)
    try:
        run = _object(
            _read_regular(args.run, MAX_METADATA_BYTES, "canonical_run_size_invalid"),
            "canonical_run_json_invalid",
        )
        inventory = _object(
            _read_regular(
                args.inventory, MAX_METADATA_BYTES, "canonical_inventory_size_invalid"
            ),
            "canonical_inventory_json_invalid",
        )
        if args.mode == "select":
            row = select_artifact(
                run,
                inventory,
                repository=args.repository,
                source_sha=args.source_sha,
                run_id=args.run_id,
            )
            print(row["id"])
            return 0
        _require(
            all(
                path is not None
                for path in (args.artifact, args.materialize_root, args.identity_out)
            ),
            "canonical_admit_arguments_missing",
        )
        artifact = _object(
            _read_regular(
                args.artifact, MAX_METADATA_BYTES, "canonical_artifact_size_invalid"
            ),
            "canonical_artifact_json_invalid",
        )
        if args.mode == "replay":
            validate_materialized(
                run=run,
                inventory=inventory,
                artifact=artifact,
                identity=_object(
                    _read_regular(
                        args.identity_out,
                        MAX_METADATA_BYTES,
                        "canonical_identity_size_invalid",
                    ),
                    "canonical_identity_json_invalid",
                ),
                materialize_root=args.materialize_root,
                repository=args.repository,
                source_sha=args.source_sha,
                run_id=args.run_id,
                api_url=args.api_url,
            )
            print(
                json.dumps(
                    {"artifact_id": artifact["id"], "contract_pass": True},
                    sort_keys=True,
                )
            )
            return 0
        _require(args.archive is not None, "canonical_admit_arguments_missing")
        _metadata(
            run,
            inventory,
            artifact,
            repository=args.repository,
            source_sha=args.source_sha,
            run_id=args.run_id,
            api_url=args.api_url,
        )
        archive = _read_regular(
            args.archive,
            MAX_ARCHIVE_BYTES,
            "canonical_archive_size_invalid",
            artifact["size_in_bytes"],
        )
        identity, files = validate_artifact(
            run=run,
            inventory=inventory,
            artifact=artifact,
            archive=archive,
            repository=args.repository,
            source_sha=args.source_sha,
            run_id=args.run_id,
            api_url=args.api_url,
        )
        # All byte/identity checks finish before materialized inputs are written.
        targets = {
            relative: _safe_target(args.materialize_root, relative)
            for relative in files
        }
        identity_relative = (
            args.identity_out.absolute()
            .relative_to(args.materialize_root.absolute())
            .as_posix()
        )
        identity_target = _safe_target(args.materialize_root, identity_relative)
        for relative, value in files.items():
            target = targets[relative]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        identity_target.parent.mkdir(parents=True, exist_ok=True)
        identity_target.write_text(
            json.dumps(identity, indent=2, sort_keys=True) + "\n"
        )
        print(
            json.dumps(
                {"artifact_id": identity["artifact"]["id"], "contract_pass": True},
                sort_keys=True,
            )
        )
    except (CanonicalActionsArtifactError, OSError, ValueError) as exc:
        print("canonical artifact verification failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
