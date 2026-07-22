from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_large_git_blobs.py"
SPEC = importlib.util.spec_from_file_location("check_large_git_blobs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_current_head_has_no_unapproved_blob_above_25_mib() -> None:
    report = audit.build_report(ROOT, scope="current")

    assert report["threshold_bytes"] == 25 * 1024 * 1024
    assert report["contract_pass"] is True
    assert report["oversized_blob_count"] == 0
    assert report["unapproved_oversized_blob_count"] == 0
    assert report["history_rewrite_authorized"] is False
    assert report["p0_required_scope"] == "all_history"


def test_history_scope_reports_removed_unapproved_blob_without_authorizing_rewrite(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    large = repo / "large.bin"
    large.write_bytes(b"0123456789")
    _git(repo, "add", "large.bin")
    _git(repo, "commit", "-m", "add large blob")
    large.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-m", "remove large blob")
    policy = repo / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": "structural-analysis-large-blob-policy.v1",
                "threshold_bytes": 4,
                "p0_required_scope": "all_history",
                "history_rewrite_authorized": False,
                "approved_blobs": [],
                "claim_boundary": "test",
            }
        ),
        encoding="utf-8",
    )

    current = audit.build_report(repo, policy_path=policy, scope="current")
    history = audit.build_report(repo, policy_path=policy, scope="history")

    assert current["contract_pass"] is True
    assert current["oversized_blob_count"] == 0
    assert history["contract_pass"] is False
    assert history["repository_is_shallow"] is False
    assert history["unapproved_oversized_blob_count"] == 1
    assert history["blocker_count"] == 2
    assert history["blockers"][-1] == "history_rewrite_not_authorized"
