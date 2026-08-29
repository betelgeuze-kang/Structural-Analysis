from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from scripts import hydrate_pre_signed_release_registry_bundle as hydrate


SOURCE_SHA = "a" * 40
REPOSITORY = "example/structural"
ARTIFACT_ID = 1234


def _archive(tmp_path: Path, *, extra: str | None = None) -> tuple[Path, bytes]:
    path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(hydrate.EXPECTED_FILES):
            member = zipfile.ZipInfo(name)
            member.create_system = 3
            member.external_attr = (stat.S_IFREG | 0o600) << 16
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, f"signed:{name}\n".encode())
        if extra is not None:
            archive.writestr(extra, b"extra\n")
    return path, path.read_bytes()


def _metadata(tmp_path: Path, archive_bytes: bytes, **updates: object) -> Path:
    payload: dict[str, object] = {
        "id": ARTIFACT_ID,
        "name": f"technical-release-registry-{SOURCE_SHA}",
        "expired": False,
        "digest": "sha256:" + hashlib.sha256(archive_bytes).hexdigest(),
        "size_in_bytes": len(archive_bytes),
        "archive_download_url": (
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/"
            f"{ARTIFACT_ID}/zip"
        ),
        "workflow_run": {
            "id": 5678,
            "repository_id": 10,
            "head_repository_id": 10,
            "head_branch": "main",
            "head_sha": SOURCE_SHA,
        },
    }
    payload.update(updates)
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _hydrate(tmp_path: Path, metadata_path: Path, archive_path: Path) -> dict:
    return hydrate.hydrate_bundle(
        metadata_path=metadata_path,
        archive_path=archive_path,
        out_dir=tmp_path / "hydrated",
        expected_artifact_id=ARTIFACT_ID,
        expected_artifact_digest=(
            "sha256:" + hashlib.sha256(archive_path.read_bytes()).hexdigest()
        ),
        expected_repository=REPOSITORY,
        expected_source_sha=SOURCE_SHA,
    )


def test_hydrates_exact_main_pre_signed_registry_bundle(tmp_path: Path) -> None:
    archive_path, archive_bytes = _archive(tmp_path)
    metadata_path = _metadata(tmp_path, archive_bytes)

    receipt = _hydrate(tmp_path, metadata_path, archive_path)

    assert receipt["technical_integrity_pass"] is True
    assert receipt["authority"] == {
        "legal_authority": False,
        "commercial_use_authority": False,
        "redistribution_authority": False,
        "release_authority": False,
    }
    assert {
        path.relative_to(tmp_path / "hydrated").as_posix()
        for path in (tmp_path / "hydrated").rglob("*")
        if path.is_file()
    } == hydrate.EXPECTED_FILES


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ARTIFACT_ID + 1),
        ("name", "untrusted"),
        ("expired", True),
        ("digest", "sha256:" + "0" * 64),
        ("size_in_bytes", 1),
        ("archive_download_url", "https://example.invalid/archive.zip"),
    ],
)
def test_rejects_artifact_metadata_identity_drift(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    archive_path, archive_bytes = _archive(tmp_path)
    metadata_path = _metadata(tmp_path, archive_bytes, **{field: value})

    with pytest.raises(ValueError, match="artifact identity is invalid"):
        _hydrate(tmp_path, metadata_path, archive_path)


@pytest.mark.parametrize(
    "workflow_run",
    [
        {"id": 1, "repository_id": 10, "head_repository_id": 11, "head_branch": "main", "head_sha": SOURCE_SHA},
        {"id": 1, "repository_id": 10, "head_repository_id": 10, "head_branch": "feature", "head_sha": SOURCE_SHA},
        {"id": 1, "repository_id": 10, "head_repository_id": 10, "head_branch": "main", "head_sha": "b" * 40},
    ],
)
def test_rejects_non_main_or_cross_repository_producer(
    tmp_path: Path,
    workflow_run: dict[str, object],
) -> None:
    archive_path, archive_bytes = _archive(tmp_path)
    metadata_path = _metadata(tmp_path, archive_bytes, workflow_run=workflow_run)

    with pytest.raises(ValueError, match="artifact identity is invalid"):
        _hydrate(tmp_path, metadata_path, archive_path)


@pytest.mark.parametrize("extra", ["extra.txt", "../escape.txt", "PROJECT_REGISTRY.JSON"])
def test_rejects_extra_traversal_or_casefold_archive_members(
    tmp_path: Path,
    extra: str,
) -> None:
    archive_path, archive_bytes = _archive(tmp_path, extra=extra)
    metadata_path = _metadata(tmp_path, archive_bytes)

    with pytest.raises(ValueError):
        _hydrate(tmp_path, metadata_path, archive_path)
