from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from release_evidence_metadata import (  # noqa: E402
    commit_bound_input_metadata,
    directory_sha256,
)


def test_directory_sha256_ignores_python_cache_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    baseline = directory_sha256(source_dir)

    cache_dir = source_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "module.cpython-310.pyc").write_bytes(b"cache")
    (source_dir / ".pytest_cache").mkdir()
    (source_dir / ".pytest_cache" / "README.md").write_text("cache\n", encoding="utf-8")

    assert directory_sha256(source_dir) == baseline


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def test_commit_bound_inputs_reject_transient_dirty_tree_hashes(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    receipt = tmp_path / "receipt.json"
    committed_bytes = b'{"status":"blocked"}\n'
    receipt.write_bytes(committed_bytes)
    _git(tmp_path, "add", "receipt.json")
    _git(tmp_path, "commit", "-m", "source receipt")
    source_commit = _git(tmp_path, "rev-parse", "HEAD")

    receipt.write_text('{"status":"ready"}\n', encoding="utf-8")
    metadata = commit_bound_input_metadata(
        [Path("receipt.json")],
        repo_root=tmp_path,
    )

    assert metadata["source_commit_sha"] == source_commit
    assert metadata["input_checksums"]["receipt.json"] == (
        f"sha256:{hashlib.sha256(committed_bytes).hexdigest()}"
    )
    provenance = metadata["source_input_provenance"]
    assert provenance["contract_pass"] is False
    assert provenance["reason_code"] == "ERR_SOURCE_INPUT_NOT_REPRODUCIBLE"
    assert provenance["blockers"] == [
        "input_differs_from_source_commit:receipt.json"
    ]


def test_commit_bound_inputs_record_untracked_workspace_input_as_missing(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "source")
    untracked = tmp_path / "license_status.json"
    untracked.write_text('{"status":"active"}\n', encoding="utf-8")

    metadata = commit_bound_input_metadata(
        [Path("license_status.json")],
        repo_root=tmp_path,
    )

    assert metadata["input_checksums"]["license_status.json"] == "missing"
    provenance = metadata["source_input_provenance"]
    assert provenance["contract_pass"] is False
    assert provenance["blockers"] == [
        "input_untracked_at_source_commit:license_status.json"
    ]


def test_commit_bound_directory_checksum_matches_clean_workspace(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    source_dir = tmp_path / "workflows"
    source_dir.mkdir()
    (source_dir / "a.yml").write_text("name: a\n", encoding="utf-8")
    nested = source_dir / "nested"
    nested.mkdir()
    (nested / "b.yml").write_text("name: b\n", encoding="utf-8")
    _git(tmp_path, "add", "workflows")
    _git(tmp_path, "commit", "-m", "source directory")

    metadata = commit_bound_input_metadata(
        [Path("workflows")],
        repo_root=tmp_path,
    )

    committed_checksum = directory_sha256(source_dir)
    assert metadata["input_checksums"]["workflows"] == committed_checksum
    assert metadata["source_input_provenance"]["contract_pass"] is True

    (nested / "b.yml").write_text("name: dirty\n", encoding="utf-8")
    dirty_metadata = commit_bound_input_metadata(
        [Path("workflows")],
        repo_root=tmp_path,
    )
    assert dirty_metadata["input_checksums"]["workflows"] == committed_checksum
    assert dirty_metadata["source_input_provenance"]["contract_pass"] is False
    assert dirty_metadata["source_input_provenance"]["blockers"] == [
        "input_differs_from_source_commit:workflows"
    ]


def test_commit_bound_external_relative_input_resolves_from_repo_root_once(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "provenance-test@example.invalid")
    _git(repo, "config", "user.name", "Provenance Test")
    tracked = repo / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "source")
    external = tmp_path / "external.txt"
    external.write_bytes(b"external evidence\n")
    alternate_cwd = tmp_path / "alternate-cwd"
    alternate_cwd.mkdir()
    monkeypatch.chdir(alternate_cwd)

    metadata = commit_bound_input_metadata(
        [Path("../external.txt")],
        repo_root=repo,
    )

    expected = f"sha256:{hashlib.sha256(external.read_bytes()).hexdigest()}"
    assert metadata["input_checksums"]["../external.txt"] == expected
    provenance = metadata["source_input_provenance"]
    assert provenance["contract_pass"] is False
    assert provenance["inputs"][0]["workspace_checksum"] == expected
    assert provenance["blockers"] == [
        "external_input_not_commit_bound:../external.txt"
    ]


def test_commit_bound_external_directory_is_hashed_but_fails_closed(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "provenance-test@example.invalid")
    _git(repo, "config", "user.name", "Provenance Test")
    tracked = repo / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "source")
    external = tmp_path / "external-dir"
    external.mkdir()
    (external / "receipt.json").write_text("{}\n", encoding="utf-8")

    metadata = commit_bound_input_metadata(
        [external],
        repo_root=repo,
    )

    assert metadata["input_checksums"][external.as_posix()].startswith(
        "dir-sha256:"
    )
    assert metadata["source_input_provenance"]["blockers"] == [
        f"external_input_not_commit_bound:{external.as_posix()}"
    ]


def test_commit_bound_missing_external_input_still_fails_closed(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "provenance-test@example.invalid")
    _git(repo, "config", "user.name", "Provenance Test")
    tracked = repo / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "source")
    missing_external = tmp_path / "missing-external.json"

    metadata = commit_bound_input_metadata(
        [missing_external],
        repo_root=repo,
    )

    assert metadata["input_checksums"][missing_external.as_posix()] == "missing"
    assert metadata["source_input_provenance"]["blockers"] == [
        f"external_input_not_commit_bound:{missing_external.as_posix()}"
    ]


def test_commit_bound_repo_relative_input_is_independent_of_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "provenance-test@example.invalid")
    _git(repo, "config", "user.name", "Provenance Test")
    receipt = repo / "evidence" / "receipt.json"
    receipt.parent.mkdir()
    receipt.write_text('{"status":"ready"}\n', encoding="utf-8")
    _git(repo, "add", "evidence/receipt.json")
    _git(repo, "commit", "-m", "source")
    alternate_cwd = tmp_path / "alternate-cwd"
    alternate_cwd.mkdir()
    monkeypatch.chdir(alternate_cwd)

    metadata = commit_bound_input_metadata(
        [Path("evidence/receipt.json")],
        repo_root=repo,
    )

    assert metadata["source_input_provenance"]["contract_pass"] is True
    assert metadata["source_input_provenance"]["workspace_match_count"] == 1


def test_commit_bound_input_fails_closed_when_tracked_workspace_file_deleted(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"status":"blocked"}\n', encoding="utf-8")
    _git(tmp_path, "add", "receipt.json")
    _git(tmp_path, "commit", "-m", "source")
    receipt.unlink()

    metadata = commit_bound_input_metadata(
        [Path("receipt.json")],
        repo_root=tmp_path,
    )

    assert metadata["input_checksums"]["receipt.json"].startswith("sha256:")
    assert metadata["source_input_provenance"]["blockers"] == [
        "input_missing_from_workspace:receipt.json"
    ]


def test_commit_bound_input_records_missing_from_source_and_workspace_reproducibly(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "source")

    metadata = commit_bound_input_metadata(
        [Path("intentionally-missing.json")],
        repo_root=tmp_path,
    )

    assert metadata["input_checksums"]["intentionally-missing.json"] == "missing"
    provenance = metadata["source_input_provenance"]
    assert provenance["contract_pass"] is True
    assert provenance["inputs"][0]["source_state"] == "missing"
    assert provenance["inputs"][0]["workspace_matches_source"] is True


def test_commit_bound_input_fails_closed_for_unresolved_source_commit(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "source")

    metadata = commit_bound_input_metadata(
        [Path("tracked.txt")],
        repo_root=tmp_path,
        source_commit_sha="0" * 40,
    )

    provenance = metadata["source_input_provenance"]
    assert provenance["contract_pass"] is False
    assert provenance["source_commit_resolved"] is False
    assert provenance["blockers"] == ["source_commit_unresolved"]


def test_commit_bound_directory_with_gitlink_fails_closed_without_exception(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "provenance-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Provenance Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "base")
    commit_sha = _git(tmp_path, "rev-parse", "HEAD")
    _git(
        tmp_path,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit_sha},vendor/subrepo",
    )
    _git(tmp_path, "commit", "-m", "gitlink")

    metadata = commit_bound_input_metadata(
        [Path("vendor")],
        repo_root=tmp_path,
    )

    provenance = metadata["source_input_provenance"]
    assert provenance["contract_pass"] is False
    assert provenance["inputs"][0]["source_state"] == "tracked"
    assert provenance["inputs"][0]["workspace_matches_source"] is False
    assert provenance["blockers"] == [
        "input_gitlink_not_commit_bound:vendor/subrepo"
    ]
