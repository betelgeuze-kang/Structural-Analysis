from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_git_lfs_integrity.py"
SPEC = importlib.util.spec_from_file_location("check_git_lfs_integrity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_current_repository_has_no_lfs_pointer_attribute_violation() -> None:
    report = module.build_report(repo_root=ROOT)
    assert report["pointer_violation_count"] == 0
    assert report["lfs_pointer_count"] > 0


def test_checker_rejects_direct_blob_declared_as_lfs(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitattributes").write_text("*.npz filter=lfs\n", encoding="utf-8")
    (tmp_path / "bad.npz").write_bytes(b"not-a-pointer")
    _git(tmp_path, "add", ".gitattributes")
    _git(
        tmp_path,
        "-c",
        "filter.lfs.clean=cat",
        "-c",
        "filter.lfs.required=false",
        "add",
        "bad.npz",
    )
    _git(tmp_path, "commit", "-m", "fixture")

    report = module.build_report(repo_root=tmp_path)
    assert report["contract_pass"] is False
    assert report["violations"] == [
        {"path": "bad.npz", "reason": "lfs_attribute_without_pointer"}
    ]
