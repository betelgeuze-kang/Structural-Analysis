from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_repo_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_repo_hygiene", SCRIPT_PATH)
assert SPEC is not None
check_repo_hygiene = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_repo_hygiene)


def test_default_mode_allows_tracked_source_boundary_candidates() -> None:
    files = [
        "implementation/phase1/stress/solver_cache.json",
        "implementation/phase1/workspace/public_input.csv",
        "implementation/phase1/output/report.json",
        "implementation/phase1/rust_hip_md3bead_hook/target/debug/build.log",
    ]

    assert check_repo_hygiene.check_tracked_files(files) == []


def test_strict_source_boundary_reports_generated_prefixes() -> None:
    files = [
        "implementation/phase1/stress/solver_cache.json",
        "implementation/phase1/workspace/public_input.csv",
        "implementation/phase1/output/report.json",
        "implementation/phase1/rust_hip_md3bead_hook/target/debug/build.log",
        "implementation/phase1/src/keep.py",
    ]

    errors = check_repo_hygiene.check_tracked_files(files, strict_source_boundary=True)

    assert errors == [
        "source-boundary candidate is tracked: implementation/phase1/stress/solver_cache.json",
        "source-boundary candidate is tracked: implementation/phase1/workspace/public_input.csv",
        "source-boundary candidate is tracked: implementation/phase1/output/report.json",
        "source-boundary candidate is tracked: implementation/phase1/rust_hip_md3bead_hook/target/debug/build.log",
    ]


def test_private_pem_is_blocked_but_public_pem_is_allowed() -> None:
    errors = check_repo_hygiene.check_tracked_files(["keys/signing.pem", "keys/signing.pub.pem"])

    assert errors == ["private signing key is tracked: keys/signing.pem"]


def test_inventory_reports_large_files_above_threshold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    small_file = tmp_path / "implementation" / "phase1" / "workspace" / "small.csv"
    large_file = tmp_path / "implementation" / "phase1" / "workspace" / "large.csv"
    large_source_file = tmp_path / "implementation" / "phase1" / "src" / "large.py"
    small_file.parent.mkdir(parents=True)
    large_source_file.parent.mkdir(parents=True)
    small_file.write_bytes(b"x" * 512)
    large_file.write_bytes(b"x" * 2048)
    large_source_file.write_bytes(b"x" * 3072)

    inventory = check_repo_hygiene.build_inventory(
        [
            "implementation/phase1/workspace/small.csv",
            "implementation/phase1/workspace/large.csv",
            "implementation/phase1/src/large.py",
        ],
        warn_large_files_mb=0.001,
    )

    assert inventory == {
        "total_files": 3,
        "risky_prefix_counts": {
            "implementation/phase1/workspace/": 2,
        },
        "large_files": [
            {
                "path": "implementation/phase1/src/large.py",
                "size_bytes": 3072,
            },
            {
                "path": "implementation/phase1/workspace/large.csv",
                "size_bytes": 2048,
            },
        ],
    }


def test_github_hard_limit_uses_git_blob_size_for_lfs_smudged_files(tmp_path: Path, monkeypatch) -> None:
    path = "implementation/phase1/release_evidence/productization/frontier_checkpoint.npz"
    file_path = tmp_path / path
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"x" * (check_repo_hygiene.MAX_GIT_BLOB_BYTES + 1))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(check_repo_hygiene, "_git_blob_size", lambda checked: 132 if checked == path else None)

    assert check_repo_hygiene.check_tracked_files([path]) == []


def test_github_hard_limit_falls_back_to_worktree_size(monkeypatch) -> None:
    path = "implementation/phase1/src/large.bin"
    monkeypatch.setattr(check_repo_hygiene, "_git_blob_size", lambda checked: None)
    monkeypatch.setattr(check_repo_hygiene, "_path_size", lambda checked: check_repo_hygiene.MAX_GIT_BLOB_BYTES + 1)

    assert check_repo_hygiene.check_tracked_files([path]) == [
        f"file exceeds GitHub hard limit ({check_repo_hygiene.MAX_GIT_BLOB_BYTES + 1} bytes): {path}"
    ]


def test_allowed_release_manifest_is_not_blocked() -> None:
    assert check_repo_hygiene.check_tracked_files(["implementation/phase1/release_artifacts_manifest.json"]) == []


def test_release_directory_remains_blocked() -> None:
    errors = check_repo_hygiene.check_tracked_files(["implementation/phase1/release/bundle.zip"])

    assert errors == ["generated path is tracked: implementation/phase1/release/bundle.zip"]
