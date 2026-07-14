from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile

import pytest

from structural_analysis.engine_v2.evidence import source_artifact_v1 as source_artifact
from structural_analysis.engine_v2.evidence.source_artifact_v1 import (
    SOURCE_ARTIFACT_MANIFEST_SCHEMA_VERSION_V1,
    SOURCE_ARTIFACT_SCHEMA_VERSION_V1,
    SourceArtifactV1Error,
    compile_source_artifact_identity_v1,
    validate_source_artifact_identity_v1,
)


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    return completed


def _write(path: Path, data: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o755 if executable else 0o644)


def _repository(
    tmp_path: Path,
    *,
    object_format: str = "sha1",
    extra_files: dict[str, tuple[bytes, bool]] | None = None,
) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    init_arguments = ["init", "--quiet", "--initial-branch=main"]
    if object_format == "sha256":
        init_arguments.append("--object-format=sha256")
    initialized = _git(repository, *init_arguments, check=False)
    if initialized.returncode != 0:
        if object_format == "sha256":
            pytest.skip("installed Git does not support SHA-256 repositories")
        raise AssertionError(initialized.stderr.decode("utf-8", errors="replace"))
    _git(repository, "config", "user.name", "Source Artifact Test")
    _git(repository, "config", "user.email", "source-artifact@example.invalid")
    _write(repository / ".gitignore", b"ignored.bin\n")
    _write(repository / "README.md", b"# source artifact\n")
    _write(repository / "build.py", b"print('build')\n")
    _write(repository / "requirements.lock", b"solver==1.0\n")
    _write(
        repository / "runner" / "main.py",
        b"#!/usr/bin/env python3\nprint('runner')\n",
        executable=True,
    )
    _write(repository / "runner" / "support.py", b"VALUE = 7\n")
    for relative, (data, executable) in (extra_files or {}).items():
        _write(repository / relative, data, executable=executable)
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "fixture")
    bundle = tmp_path / "source.tar"
    bundle.write_bytes(_git(repository, "archive", "--format=tar", "HEAD").stdout)
    bundle.chmod(0o644)
    return repository, bundle


def _compile(repository: Path, bundle: Path):
    return compile_source_artifact_identity_v1(
        repository,
        bundle,
        runner_source_paths=("runner/support.py", "runner/main.py"),
        build_recipe_path="build.py",
        dependency_lock_path="requirements.lock",
    )


def _assert_error(code: str, function, /, *args, **kwargs) -> SourceArtifactV1Error:
    with pytest.raises(SourceArtifactV1Error) as captured:
        function(*args, **kwargs)
    assert captured.value.code == code
    assert captured.value.path.startswith("/")
    return captured.value


def test_compiles_exact_clean_checkout_bundle_and_role_hashes(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path)

    first = _compile(repository, bundle)
    second = _compile(repository, bundle)

    assert first == second
    assert first.schema_version == SOURCE_ARTIFACT_SCHEMA_VERSION_V1
    assert (
        first.source_manifest.schema_version
        == SOURCE_ARTIFACT_MANIFEST_SCHEMA_VERSION_V1
    )
    assert first.object_format == "sha1"
    assert len(first.source_commit) == 40
    assert (
        first.source_commit
        == _git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    )
    assert first.source_tree_sha256.startswith("sha256:")
    assert (
        first.source_bundle_sha256
        == "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest()
    )
    assert first.source_bundle_byte_count == bundle.stat().st_size
    assert first.runner_source_paths == ("runner/main.py", "runner/support.py")
    assert (
        first.build_recipe_sha256
        == "sha256:"
        + hashlib.sha256((repository / "build.py").read_bytes()).hexdigest()
    )
    assert (
        first.dependency_lock_sha256
        == "sha256:"
        + hashlib.sha256((repository / "requirements.lock").read_bytes()).hexdigest()
    )
    assert first.identity_hash.startswith("sha256:")
    assert validate_source_artifact_identity_v1(first) is first
    assert first.to_dict()["identity_hash"] == first.identity_hash
    assert (
        first.source_manifest.to_dict()["source_tree_sha256"]
        == first.source_tree_sha256
    )

    paths = tuple(row.path for row in first.source_manifest.files)
    assert paths == tuple(sorted(paths, key=lambda value: value.encode("utf-8")))
    by_path = {row.path: row for row in first.source_manifest.files}
    assert by_path["runner/main.py"].git_mode == "100755"
    assert by_path["runner/support.py"].git_mode == "100644"
    assert (
        by_path["runner/main.py"].git_blob_oid
        == _git(repository, "rev-parse", "HEAD:runner/main.py").stdout.decode().strip()
    )
    with pytest.raises(FrozenInstanceError):
        first.source_commit = "0" * 40  # type: ignore[misc]


def test_supports_exact_sha256_git_object_ids_when_available(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path, object_format="sha256")

    identity = _compile(repository, bundle)

    assert identity.object_format == "sha256"
    assert len(identity.source_commit) == 64
    assert all(len(row.git_blob_oid) == 64 for row in identity.source_manifest.files)


@pytest.mark.parametrize("dirty_kind", ["staged", "unstaged", "untracked", "ignored"])
def test_rejects_every_real_porcelain_dirty_class(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    repository, bundle = _repository(tmp_path)
    if dirty_kind == "staged":
        _write(repository / "README.md", b"staged\n")
        _git(repository, "add", "README.md")
    elif dirty_kind == "unstaged":
        _write(repository / "README.md", b"unstaged\n")
    elif dirty_kind == "untracked":
        _write(repository / "new.py", b"untracked\n")
    else:
        _write(repository / "ignored.bin", b"ignored\n")

    _assert_error("source_artifact_worktree_not_clean", _compile, repository, bundle)


@pytest.mark.parametrize(
    "porcelain_record",
    [
        b"1 M. N... 100644 100644 100644 " + b"0" * 40 + b" " + b"0" * 40 + b" x\0",
        b"2 R. N... 100644 100644 100644 "
        + b"0" * 40
        + b" "
        + b"0" * 40
        + b" R100 x\0y\0",
        b"u UU N... 100644 100644 100644 100644 " + b"0" * 122 + b" x\0",
        b"1 .M S.M. 160000 160000 160000 " + b"0" * 40 + b" " + b"0" * 40 + b" sub\0",
        b"? untracked\0",
        b"! ignored\0",
    ],
)
def test_any_porcelain_v2_record_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    porcelain_record: bytes,
) -> None:
    monkeypatch.setattr(
        source_artifact, "_git", lambda *args, **kwargs: porcelain_record
    )

    _assert_error(
        "source_artifact_worktree_not_clean",
        source_artifact._require_clean_worktree,
        "/unused",
    )


def test_rejects_tree_index_disagreement_even_if_status_was_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, bundle = _repository(tmp_path)
    original_git = source_artifact._git

    def disagreeing_index(root: str, *arguments: str, path: str) -> bytes:
        raw = original_git(root, *arguments, path=path)
        if arguments[:2] == ("ls-files", "--stage"):
            records = raw[:-1].split(b"\0")
            metadata, filename = records[0].split(b"\t", 1)
            mode, oid, stage = metadata.split(b" ")
            replacement = (b"1" if oid[:1] != b"1" else b"2") + oid[1:]
            records[0] = b" ".join((mode, replacement, stage)) + b"\t" + filename
            return b"\0".join(records) + b"\0"
        return raw

    monkeypatch.setattr(source_artifact, "_git", disagreeing_index)

    _assert_error("source_artifact_tree_index_mismatch", _compile, repository, bundle)


def test_rejects_assume_unchanged_worktree_bytes_by_git_blob_oid(
    tmp_path: Path,
) -> None:
    repository, bundle = _repository(tmp_path)
    _git(repository, "update-index", "--assume-unchanged", "runner/support.py")
    _write(repository / "runner" / "support.py", b"VALUE = 999\n")

    _assert_error(
        "source_artifact_worktree_blob_mismatch", _compile, repository, bundle
    )


def test_rejects_worktree_mode_hidden_by_core_filemode(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path)
    _git(repository, "config", "core.fileMode", "false")
    (repository / "runner" / "main.py").chmod(0o644)

    _assert_error(
        "source_artifact_worktree_mode_mismatch", _compile, repository, bundle
    )


def test_openat_nofollow_rejects_file_swap_after_git_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, bundle = _repository(tmp_path)
    original_git = source_artifact._git
    swapped = False

    def swap_after_index(root: str, *arguments: str, path: str) -> bytes:
        nonlocal swapped
        raw = original_git(root, *arguments, path=path)
        if not swapped and arguments[:2] == ("ls-files", "--stage"):
            target = repository / "runner" / "main.py"
            target.unlink()
            target.symlink_to("../build.py")
            swapped = True
        return raw

    monkeypatch.setattr(source_artifact, "_git", swap_after_index)

    _assert_error("source_artifact_open_failed", _compile, repository, bundle)


def test_rejects_tracked_symlink_and_non_regular_git_modes(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path)
    (repository / "alias.py").symlink_to("build.py")
    _git(repository, "add", "alias.py")
    _git(repository, "commit", "--quiet", "-m", "add symlink")
    bundle.write_bytes(_git(repository, "archive", "--format=tar", "HEAD").stdout)

    _assert_error(
        "source_artifact_tree_entry_not_regular", _compile, repository, bundle
    )


def test_rejects_distinct_tracked_paths_that_alias_one_hardlink_inode(
    tmp_path: Path,
) -> None:
    repository, bundle = _repository(tmp_path)
    os.link(repository / "build.py", repository / "build-alias.py")
    _git(repository, "add", "build-alias.py")
    _git(repository, "commit", "--quiet", "-m", "add hardlink alias")
    bundle.write_bytes(_git(repository, "archive", "--format=tar", "HEAD").stdout)

    _assert_error(
        "source_artifact_worktree_hardlink_alias",
        _compile,
        repository,
        bundle,
    )


@pytest.mark.parametrize(
    "extra_files, expected_code",
    [
        ({"e\u0301.py": (b"non-nfc\n", False)}, "source_artifact_path_not_nfc"),
        (
            {"Case.py": (b"upper\n", False), "case.py": (b"lower\n", False)},
            "source_artifact_path_casefold_collision",
        ),
        ({"bad\\name.py": (b"backslash\n", False)}, "source_artifact_path_unsafe"),
    ],
)
def test_rejects_unsafe_noncanonical_or_casefold_colliding_git_paths(
    tmp_path: Path,
    extra_files: dict[str, tuple[bytes, bool]],
    expected_code: str,
) -> None:
    repository, bundle = _repository(tmp_path, extra_files=extra_files)

    _assert_error(expected_code, _compile, repository, bundle)


def test_rejects_bundle_raw_byte_difference_and_bundle_symlink(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path)
    original = bundle.read_bytes()
    bundle.write_bytes(original + b"tamper")

    _assert_error("source_artifact_bundle_bytes_mismatch", _compile, repository, bundle)

    bundle.write_bytes(original)
    alias = tmp_path / "source-alias.tar"
    alias.symlink_to(bundle.name)
    _assert_error("source_artifact_bundle_open_failed", _compile, repository, alias)


def test_rejects_git_archive_member_set_changed_by_export_ignore(
    tmp_path: Path,
) -> None:
    repository, _ = _repository(tmp_path)
    _write(repository / ".gitattributes", b"README.md export-ignore\n")
    _git(repository, "add", ".gitattributes")
    _git(repository, "commit", "--quiet", "-m", "export rule")
    bundle = tmp_path / "export-ignore.tar"
    bundle.write_bytes(_git(repository, "archive", "--format=tar", "HEAD").stdout)

    _assert_error("source_artifact_tar_manifest_mismatch", _compile, repository, bundle)


def test_tar_parser_rejects_non_regular_member_even_when_raw_archive_authority_is_spoofed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, valid_bundle = _repository(tmp_path)
    malicious = io.BytesIO()
    with tarfile.open(
        fileobj=io.BytesIO(valid_bundle.read_bytes()), mode="r:"
    ) as source:
        with tarfile.open(fileobj=malicious, mode="w:") as target:
            for member in source:
                extracted = source.extractfile(member) if member.isfile() else None
                target.addfile(member, extracted)
            link = tarfile.TarInfo("runner-link")
            link.type = tarfile.SYMTYPE
            link.linkname = "runner/main.py"
            link.mode = 0o777
            target.addfile(link)
    malicious_bundle = tmp_path / "malicious.tar"
    malicious_bundle.write_bytes(malicious.getvalue())
    original_git = source_artifact._git

    def spoof_archive(root: str, *arguments: str, path: str) -> bytes:
        if arguments[:2] == ("archive", "--format=tar"):
            return malicious.getvalue()
        return original_git(root, *arguments, path=path)

    monkeypatch.setattr(source_artifact, "_git", spoof_archive)

    _assert_error(
        "source_artifact_tar_member_type_invalid",
        _compile,
        repository,
        malicious_bundle,
    )


@pytest.mark.parametrize(
    "runner_paths, build_path, lock_path, expected_code",
    [
        (
            ("runner/main.py", "runner/main.py"),
            "build.py",
            "requirements.lock",
            "source_artifact_runner_path_duplicate",
        ),
        (
            ("runner/main.py",),
            "runner/main.py",
            "requirements.lock",
            "source_artifact_role_path_not_distinct",
        ),
        (
            ("runner/main.py",),
            "build.py",
            "build.py",
            "source_artifact_role_path_not_distinct",
        ),
        (
            ("missing.py",),
            "build.py",
            "requirements.lock",
            "source_artifact_role_path_untracked",
        ),
    ],
)
def test_role_files_must_be_tracked_regular_and_mutually_distinct(
    tmp_path: Path,
    runner_paths: tuple[str, ...],
    build_path: str,
    lock_path: str,
    expected_code: str,
) -> None:
    repository, bundle = _repository(tmp_path)

    _assert_error(
        expected_code,
        compile_source_artifact_identity_v1,
        repository,
        bundle,
        runner_source_paths=runner_paths,
        build_recipe_path=build_path,
        dependency_lock_path=lock_path,
    )


def test_validator_rejects_hash_and_manifest_tampering(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path)
    identity = _compile(repository, bundle)

    _assert_error(
        "source_artifact_runner_hash_mismatch",
        validate_source_artifact_identity_v1,
        replace(identity, runner_source_sha256="sha256:" + "0" * 64),
    )
    _assert_error(
        "source_artifact_identity_hash_mismatch",
        validate_source_artifact_identity_v1,
        replace(identity, source_bundle_sha256="sha256:" + "0" * 64),
    )
    altered_manifest = replace(
        identity.source_manifest,
        source_tree_sha256="sha256:" + "0" * 64,
    )
    _assert_error(
        "source_artifact_tree_hash_mismatch",
        validate_source_artifact_identity_v1,
        replace(identity, source_manifest=altered_manifest),
    )
    first = identity.source_manifest.files[0]
    invalid_mode = replace(first, git_mode=None)  # type: ignore[arg-type]
    _assert_error(
        "source_artifact_file_mode_invalid",
        validate_source_artifact_identity_v1,
        replace(
            identity,
            source_manifest=replace(
                identity.source_manifest,
                files=(invalid_mode, *identity.source_manifest.files[1:]),
            ),
        ),
    )
    invalid_oid = replace(first, git_blob_oid=None)  # type: ignore[arg-type]
    _assert_error(
        "source_artifact_git_oid_invalid",
        validate_source_artifact_identity_v1,
        replace(
            identity,
            source_manifest=replace(
                identity.source_manifest,
                files=(invalid_oid, *identity.source_manifest.files[1:]),
            ),
        ),
    )


def test_rejects_repository_and_bundle_parent_symlinks(tmp_path: Path) -> None:
    repository, bundle = _repository(tmp_path)
    repository_alias = tmp_path / "repository-alias"
    repository_alias.symlink_to(repository.name, target_is_directory=True)

    _assert_error(
        "source_artifact_repository_open_failed",
        _compile,
        repository_alias,
        bundle,
    )
