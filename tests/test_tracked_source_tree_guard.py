from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

import pytest

from scripts import build_post_main_evidence_overlay as overlay
from scripts import check_generated_artifact_dag as dag
from scripts import verify_tracked_source_tree as guard


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.fixture()
def source_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "core.autocrlf", "false")
    (root / "source.txt").write_bytes(b"original\n")
    (root / "leaf.json").write_bytes(b'{"old":true}\n')
    (root / "공백 파일.txt").write_bytes(b"unicode source\n")
    (root / 'quote"name.txt').write_bytes(b"quoted source\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source fixture")
    return root, _git(root, "rev-parse", "HEAD")


def _check(repo: tuple[Path, str], **kwargs) -> dict[str, object]:
    root, sha = repo
    return guard.verify_tracked_source_tree(repo_root=root, source_sha=sha, **kwargs)


def test_complete_unchanged_source_and_named_generated_content(source_repo) -> None:
    root, _ = source_repo
    before = _git(root, "status", "--porcelain=v1")
    receipt = _check(source_repo)
    assert receipt["contract_pass"] is True
    assert receipt["tracked_path_count"] == 4
    assert _git(root, "status", "--porcelain=v1") == before
    (root / "leaf.json").write_bytes(b'{"fresh":true}\n')
    receipt = _check(source_repo, allowed_modified_paths={"leaf.json"})
    assert receipt["modified_generated_paths"] == ["leaf.json"]
    assert receipt["canonical_content_checked_count"] == 3


@pytest.mark.parametrize("mutation", ("modified", "deleted", "renamed", "symlink"))
def test_unlisted_source_changes_fail(source_repo, mutation: str) -> None:
    root, _ = source_repo
    source = root / "source.txt"
    if mutation == "modified":
        source.write_bytes(b"tampered\n")
    elif mutation == "deleted":
        source.unlink()
    elif mutation == "renamed":
        source.rename(root / "renamed.txt")
    else:
        source.unlink()
        source.symlink_to("leaf.json")
    with pytest.raises(guard.TrackedSourceTreeError):
        _check(source_repo, allowed_modified_paths={"leaf.json"})


@pytest.mark.parametrize("path", ("source.txt", "leaf.json"))
def test_staged_changes_fail_even_for_generated_leaves(source_repo, path: str) -> None:
    root, _ = source_repo
    (root / path).write_bytes(b"staged modification\n")
    _git(root, "add", path)
    with pytest.raises(guard.TrackedSourceTreeError, match="index_tree_mismatch"):
        _check(source_repo, allowed_modified_paths={"leaf.json"})


@pytest.mark.parametrize("flag", ("--assume-unchanged", "--skip-worktree"))
def test_index_visibility_flags_are_rejected_without_mutation(
    source_repo, flag: str
) -> None:
    root, _ = source_repo
    _git(root, "update-index", flag, "source.txt")
    (root / "source.txt").write_bytes(b"hidden!!\n")
    flags_before = _git(root, "ls-files", "-v")
    with pytest.raises(guard.TrackedSourceTreeError, match="index_flags"):
        _check(source_repo)
    assert _git(root, "ls-files", "-v") == flags_before


@pytest.mark.parametrize("path", ("source.txt", "leaf.json"))
def test_filemode_configuration_cannot_hide_executable_change(
    source_repo, path: str
) -> None:
    root, _ = source_repo
    _git(root, "config", "core.filemode", "false")
    (root / path).chmod(0o755)
    with pytest.raises(guard.TrackedSourceTreeError, match="mode_mismatch"):
        _check(source_repo, allowed_modified_paths={"leaf.json"})


@pytest.mark.parametrize("mutation", ("deleted", "symlink"))
def test_generated_exemption_allows_content_only(source_repo, mutation: str) -> None:
    root, _ = source_repo
    leaf = root / "leaf.json"
    leaf.unlink()
    if mutation == "symlink":
        leaf.symlink_to("source.txt")
    with pytest.raises(guard.TrackedSourceTreeError):
        _check(source_repo, allowed_modified_paths={"leaf.json"})


def test_explicit_content_hash_bypasses_restored_mtime_and_untrusted_stat_config(
    source_repo,
) -> None:
    root, _ = source_repo
    _git(root, "config", "core.trustctime", "false")
    _git(root, "config", "core.checkstat", "minimal")
    _git(root, "update-index", "--refresh")
    source = root / "source.txt"
    original_stat = source.stat()
    source.write_bytes(b"tampered\n")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert source.stat().st_size == original_stat.st_size
    with pytest.raises(guard.TrackedSourceTreeError, match="content_mismatch"):
        _check(source_repo)


def test_full_crlf_checkout_preserves_source_attributes_semantics(source_repo) -> None:
    root, _ = source_repo
    (root / ".gitattributes").write_bytes(b"*.txt text\n")
    _git(root, "add", ".gitattributes")
    _git(root, "commit", "-qm", "source attributes")
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "config", "core.autocrlf", "true")
    for path in root.iterdir():
        if path.is_file():
            path.unlink()
    _git(root, "checkout-index", "--all", "--force")
    assert (root / ".gitattributes").read_bytes() == b"*.txt text\r\n"
    assert (root / "source.txt").read_bytes() == b"original\r\n"
    assert _check((root, sha))["contract_pass"] is True


def test_attribute_directive_tamper_is_rejected_before_filter_use(source_repo) -> None:
    root, _ = source_repo
    (root / ".gitattributes").write_bytes(b"*.txt text\n")
    _git(root, "add", ".gitattributes")
    _git(root, "commit", "-qm", "source attributes")
    sha = _git(root, "rev-parse", "HEAD")
    (root / ".gitattributes").write_bytes(b"*.txt filter=unsafe\n")
    with pytest.raises(guard.TrackedSourceTreeError, match="attributes_mismatch"):
        _check((root, sha))


def test_ignored_ancestor_attributes_cannot_mask_tracked_source_tamper(
    source_repo, monkeypatch
) -> None:
    root, _ = source_repo
    (root / "sub").mkdir()
    (root / "sub/source.txt").write_bytes(b"$Id$\n")
    (root / ".gitignore").write_bytes(b"sub/.gitattributes\n")
    _git(root, "add", ".gitignore", "sub/source.txt")
    _git(root, "commit", "-qm", "source with ignored runtime attribute location")
    sha = _git(root, "rev-parse", "HEAD")
    (root / "sub/.gitattributes").write_bytes(b"source.txt ident\n")
    (root / "sub/source.txt").write_bytes(b"$Id: unrelated tracked content changed$\n")
    _git(root, "check-ignore", "sub/.gitattributes")

    def forbid_hashing(*_args, **_kwargs):
        raise AssertionError("unexpected attribute metadata must fail before hashing")

    monkeypatch.setattr(guard, "_canonical_hashes", forbid_hashing)
    with pytest.raises(guard.TrackedSourceTreeError, match="uncommitted_attributes"):
        _check((root, sha))


def test_git_info_attribute_override_is_rejected_from_metadata(
    source_repo, monkeypatch
) -> None:
    root, _ = source_repo
    (root / ".git/info/attributes").write_bytes(b"source.txt ident\n")

    def forbid_hashing(*_args, **_kwargs):
        raise AssertionError("Git info attribute metadata must fail before hashing")

    monkeypatch.setattr(guard, "_canonical_hashes", forbid_hashing)
    with pytest.raises(
        guard.TrackedSourceTreeError, match="git_info_attributes_forbidden"
    ):
        _check(source_repo)


def test_custom_clean_filters_are_rejected_before_execution(source_repo) -> None:
    root, _ = source_repo
    (root / ".gitattributes").write_bytes(b"*.txt filter=unsafe\n")
    _git(root, "add", ".gitattributes")
    _git(root, "commit", "-qm", "declared unsupported filter")
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "config", "filter.unsafe.clean", "touch clean-filter-was-run; cat")
    with pytest.raises(guard.TrackedSourceTreeError, match="filter_unsupported"):
        _check((root, sha))
    assert not (root / "clean-filter-was-run").exists()


def test_lfs_pointer_hydration_is_source_bound_without_filter_execution(
    source_repo,
) -> None:
    root, _ = source_repo
    payload = b"fixed source-bound LFS bytes\x00\x01"
    digest = hashlib.sha256(payload).hexdigest()
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{digest}\nsize {len(payload)}\n"
    ).encode()
    (root / ".gitattributes").write_bytes(b"asset.bin filter=lfs -text\n")
    (root / "asset.bin").write_bytes(pointer)
    _git(root, "add", ".gitattributes", "asset.bin")
    _git(root, "commit", "-qm", "source-bound LFS pointer")
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "config", "filter.lfs.clean", "touch lfs-clean-was-run; cat")
    _git(root, "config", "filter.lfs.process", "touch lfs-process-was-run; cat")
    _git(root, "config", "filter.lfs.required", "true")
    assert _check((root, sha))["contract_pass"] is True
    (root / "asset.bin").write_bytes(payload)
    assert _check((root, sha))["contract_pass"] is True
    (root / "asset.bin").write_bytes(b"x" + payload[1:])
    with pytest.raises(guard.TrackedSourceTreeError, match="content_mismatch"):
        _check((root, sha))
    assert not (root / "lfs-clean-was-run").exists()
    assert not (root / "lfs-process-was-run").exists()


def test_external_diff_and_textconv_do_not_execute(source_repo) -> None:
    root, _ = source_repo
    _git(root, "config", "diff.external", "touch external-diff-was-run")
    (root / ".gitattributes").write_bytes(b"leaf.json diff=sentinel\n")
    _git(root, "add", ".gitattributes")
    _git(root, "commit", "-qm", "diff driver metadata")
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "config", "diff.sentinel.textconv", "touch textconv-was-run")
    (root / "leaf.json").write_bytes(b'{"fresh":true}\n')
    assert (
        _check((root, sha), allowed_modified_paths={"leaf.json"})["contract_pass"]
        is True
    )
    assert not (root / "external-diff-was-run").exists()
    assert not (root / "textconv-was-run").exists()


def test_only_named_untracked_receipts_are_admitted(source_repo) -> None:
    root, _ = source_repo
    receipt = "canonical-receipt.json"
    (root / receipt).write_bytes(b"{}\n")
    with pytest.raises(guard.TrackedSourceTreeError, match="untracked_path"):
        _check(source_repo)
    assert (
        _check(source_repo, allowed_untracked_paths={receipt})["contract_pass"] is True
    )
    (root / receipt).chmod(0o755)
    with pytest.raises(guard.TrackedSourceTreeError, match="mode_mismatch"):
        _check(source_repo, allowed_untracked_paths={receipt})


@pytest.mark.parametrize(
    "path", ("private.env.production", ".netrc", ".git-credentials")
)
def test_protected_name_gate_precedes_any_content_command(
    source_repo, monkeypatch, path: str
) -> None:
    # Inject only tree metadata: no environment or credential payload is created/read.
    original_git = guard._git
    calls: list[tuple[str, ...]] = []

    def metadata_only(root, *args, **kwargs):
        calls.append(args)
        if args[0] == "ls-tree":
            return f"100644 blob {'a' * 40}\t{path}\0".encode()
        return original_git(root, *args, **kwargs)

    monkeypatch.setattr(guard, "_git", metadata_only)
    with pytest.raises(guard.TrackedSourceTreeError, match="protected_path"):
        _check(source_repo)
    assert not any(
        args[0] in {"hash-object", "cat-file", "diff-files"} for args in calls
    )


def test_producer_and_consumer_profiles_keep_exact_distinct_paths() -> None:
    producer, producer_untracked = guard.source_profile_paths("producer")
    consumer, consumer_untracked = guard.source_profile_paths("consumer")
    assert len(producer) == 22 and producer_untracked == frozenset()
    assert consumer == frozenset(overlay.RELEASE_FILES) and len(consumer) == 14
    assert consumer_untracked == {guard.CANONICAL_RECEIPT}
    assert set(guard.PRODUCER_GENERATED_MARKDOWN_FILES).isdisjoint(consumer)
    assert {path for path, _ in overlay.EXTERNAL_RECEIPTS}.isdisjoint(consumer)


def test_overlay_rejects_unlisted_source_drift_before_copy_or_seal(
    source_repo, tmp_path
) -> None:
    root, sha = source_repo
    (root / "source.txt").write_bytes(b"tampered\n")
    output = tmp_path / "overlay"
    with pytest.raises(
        overlay.OverlayContractError, match="overlay_tracked_source_invalid"
    ):
        overlay.build_overlay(
            repo_root=root,
            out_dir=output,
            repository="owner/repository",
            source_sha=sha,
            workflow_run_id=101,
            workflow_run_attempt=1,
            event="workflow_dispatch",
        )
    assert not output.exists()


def test_overlay_rechecks_source_after_leaf_replay_before_writing_seal(
    source_repo, tmp_path, monkeypatch
) -> None:
    root, sha = source_repo
    monkeypatch.setattr(overlay, "RELEASE_FILES", ("leaf.json",))
    monkeypatch.setattr(overlay, "EXTERNAL_RECEIPTS", ())
    monkeypatch.setattr(overlay, "_source_authority_policy", lambda *_: None)
    monkeypatch.setattr(overlay, "_technical_contracts", lambda *_: {})
    monkeypatch.setattr(overlay, "_validate_schema", lambda *_: None)
    monkeypatch.setattr(
        overlay,
        "_source_file_identity",
        lambda *_: {
            "path": ".github/workflows/nightly-full-quality.yml",
            "blob_sha": "a" * 40,
            "sha256": "sha256:" + "a" * 64,
        },
    )

    def mutate_during_replay(**_):
        (root / "source.txt").write_bytes(b"tampered\n")
        return []

    monkeypatch.setattr(dag, "validate_post_main_overlay_outputs", mutate_during_replay)
    output = tmp_path / "overlay"
    with pytest.raises(
        overlay.OverlayContractError, match="overlay_tracked_source_invalid"
    ):
        overlay.build_overlay(
            repo_root=root,
            out_dir=output,
            repository="owner/repository",
            source_sha=sha,
            workflow_run_id=101,
            workflow_run_attempt=1,
            event="workflow_dispatch",
        )
    assert (output / "release-files/leaf.json").is_file()
    assert not (output / overlay.MANIFEST_NAME).exists()


def test_workflow_admission_runs_pristine_and_exact_consumer_profiles() -> None:
    import yaml

    nightly = yaml.safe_load(
        (overlay.ROOT / ".github/workflows/nightly-full-quality.yml").read_text()
    )
    product = yaml.safe_load(
        (overlay.ROOT / ".github/workflows/product-state-current.yml").read_text()
    )
    nightly_step = next(
        step
        for step in nightly["jobs"]["build_post_main_overlay"]["steps"]
        if step.get("name") == "Verify pristine exact-main producer source"
    )
    product_step = next(
        step
        for step in product["jobs"]["build-current-state"]["steps"]
        if step.get("name")
        == "Verify pristine exact-source checkout before unprivileged build"
    )
    consumer_step = next(
        step
        for step in product["jobs"]["build-current-state"]["steps"]
        if step.get("name") == "Materialize exact current-source product-state inputs"
    )
    for step in (nightly_step, product_step):
        assert "scripts/verify_tracked_source_tree.py" in step["run"]
        assert "--profile pristine" in step["run"]
    assert '--source-sha "$GITHUB_SHA"' in nightly_step["run"]
    assert '--source-sha "$PRODUCT_STATE_SHA"' in product_step["run"]
    assert (
        '--source-sha "$PRODUCT_STATE_SHA" --profile consumer' in consumer_step["run"]
    )
