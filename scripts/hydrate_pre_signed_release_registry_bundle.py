#!/usr/bin/env python3
"""Hydrate an externally signed, exact-main release-registry artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any
import unicodedata
import zipfile


EXPECTED_FILES = frozenset(
    {
        "project_package.zip",
        "project_registry.json",
        "release_registry.json",
        "signing/project_registry.signature.b64",
        "signing/release_registry.signature.b64",
        "signing/release_registry_ed25519.pub.pem",
    }
)
ALLOWED_DIRECTORIES = frozenset({"signing"})
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate artifact metadata key: {key}")
        result[key] = value
    return result


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("pre-signed artifact metadata is invalid") from error
    if not isinstance(payload, dict):
        raise ValueError("pre-signed artifact metadata root must be an object")
    return payload


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("pre-signed artifact archive exceeds size limit")
            digest.update(chunk)
    return digest.hexdigest(), size


def _validate_identity(
    metadata: dict[str, Any],
    *,
    archive_sha256: str,
    archive_size: int,
    expected_artifact_id: int,
    expected_artifact_digest: str,
    expected_repository: str,
    expected_source_sha: str,
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", expected_repository):
        raise ValueError("expected repository is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha):
        raise ValueError("expected source SHA is invalid")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_artifact_digest):
        raise ValueError("expected artifact digest is invalid")
    workflow_run = metadata.get("workflow_run")
    expected_name = f"technical-release-registry-{expected_source_sha}"
    expected_url = (
        f"https://api.github.com/repos/{expected_repository}/actions/artifacts/"
        f"{expected_artifact_id}/zip"
    )
    if not (
        type(metadata.get("id")) is int
        and metadata["id"] == expected_artifact_id
        and metadata.get("name") == expected_name
        and metadata.get("expired") is False
        and metadata.get("digest") == expected_artifact_digest
        and type(metadata.get("size_in_bytes")) is int
        and metadata["size_in_bytes"] == archive_size
        and metadata.get("archive_download_url") == expected_url
        and expected_artifact_digest == f"sha256:{archive_sha256}"
        and isinstance(workflow_run, dict)
        and type(workflow_run.get("id")) is int
        and workflow_run["id"] > 0
        and type(workflow_run.get("repository_id")) is int
        and workflow_run["repository_id"] > 0
        and workflow_run.get("head_repository_id")
        == workflow_run.get("repository_id")
        and workflow_run.get("head_branch") == "main"
        and workflow_run.get("head_sha") == expected_source_sha
    ):
        raise ValueError("pre-signed artifact identity is invalid")


def _validated_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if not infos or len(infos) > len(EXPECTED_FILES) + len(ALLOWED_DIRECTORIES):
        raise ValueError("pre-signed artifact member count is invalid")
    files: dict[str, zipfile.ZipInfo] = {}
    folded: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        name = info.filename
        trimmed = name[:-1] if info.is_dir() and name.endswith("/") else name
        relative = PurePosixPath(trimmed)
        if (
            not trimmed
            or "\\" in name
            or relative.is_absolute()
            or "." in relative.parts
            or ".." in relative.parts
            or relative.as_posix() != trimmed
            or unicodedata.normalize("NFC", name) != name
            or any(unicodedata.category(character) in {"Cc", "Cf"} for character in name)
            or info.flag_bits & 1
        ):
            raise ValueError("pre-signed artifact member path is invalid")
        folded_name = trimmed.casefold()
        if folded_name in folded:
            raise ValueError("pre-signed artifact member names collide")
        folded.add(folded_name)
        mode = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
        if info.is_dir():
            if trimmed not in ALLOWED_DIRECTORIES or mode not in (0, stat.S_IFDIR):
                raise ValueError("pre-signed artifact directory is invalid")
            continue
        if (
            trimmed not in EXPECTED_FILES
            or mode not in (0, stat.S_IFREG)
            or info.file_size <= 0
            or info.compress_size <= 0
            or info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO
        ):
            raise ValueError("pre-signed artifact file metadata is invalid")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("pre-signed artifact uncompressed size exceeds limit")
        files[trimmed] = info
    if set(files) != EXPECTED_FILES:
        raise ValueError("pre-signed artifact file set is incomplete")
    return files


def hydrate_bundle(
    *,
    metadata_path: Path,
    archive_path: Path,
    out_dir: Path,
    expected_artifact_id: int,
    expected_artifact_digest: str,
    expected_repository: str,
    expected_source_sha: str,
) -> dict[str, Any]:
    if expected_artifact_id <= 0:
        raise ValueError("expected artifact ID is invalid")
    if out_dir.exists() or out_dir.is_symlink():
        raise ValueError("pre-signed registry output directory must be fresh")
    metadata = _load_metadata(metadata_path)
    archive_sha256, archive_size = _sha256_file(archive_path)
    _validate_identity(
        metadata,
        archive_sha256=archive_sha256,
        archive_size=archive_size,
        expected_artifact_id=expected_artifact_id,
        expected_artifact_digest=expected_artifact_digest,
        expected_repository=expected_repository,
        expected_source_sha=expected_source_sha,
    )
    out_parent = out_dir.parent.resolve(strict=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=out_parent))
    file_rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _validated_members(archive)
            for name in sorted(members):
                destination = temporary.joinpath(*PurePosixPath(name).parts)
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with archive.open(members[name]) as source, destination.open("xb") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(chunk)
                        digest.update(chunk)
                        target.write(chunk)
                if size != members[name].file_size:
                    raise ValueError("pre-signed artifact member size changed during extraction")
                os.chmod(destination, 0o600)
                file_rows.append(
                    {"path": name, "sha256": digest.hexdigest(), "bytes": size}
                )
        final_archive_sha256, final_archive_size = _sha256_file(archive_path)
        if (final_archive_sha256, final_archive_size) != (
            archive_sha256,
            archive_size,
        ):
            raise ValueError("pre-signed artifact archive changed during hydration")
        os.replace(temporary, out_dir)
    except (OSError, ValueError, zipfile.BadZipFile):
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "schema_version": "pre-signed-release-registry-hydration.v1",
        "source_commit_sha": expected_source_sha,
        "artifact": {
            "id": expected_artifact_id,
            "name": metadata["name"],
            "digest": expected_artifact_digest,
            "size_in_bytes": archive_size,
            "workflow_run_id": metadata["workflow_run"]["id"],
        },
        "files": file_rows,
        "technical_integrity_pass": True,
        "authority": {
            "legal_authority": False,
            "commercial_use_authority": False,
            "redistribution_authority": False,
            "release_authority": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-artifact-id", type=int, required=True)
    parser.add_argument("--expected-artifact-digest", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        result = hydrate_bundle(
            metadata_path=args.metadata,
            archive_path=args.archive,
            out_dir=args.out_dir,
            expected_artifact_id=args.expected_artifact_id,
            expected_artifact_digest=args.expected_artifact_digest,
            expected_repository=args.expected_repository,
            expected_source_sha=args.expected_source_sha,
        )
        if args.receipt is not None:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(
                json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"pre-signed release registry hydration failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
