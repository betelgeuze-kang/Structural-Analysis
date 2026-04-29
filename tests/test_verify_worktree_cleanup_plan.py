"""Contract tests for cleanup-plan verification before worktree drift cleanup."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "verify_worktree_cleanup_plan.py"


def _write_status_fixture(tmp_path: Path, lines: list[str]) -> Path:
    fixture = tmp_path / "status.txt"
    fixture.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return fixture


def _write_pathspecs(
    pathspec_dir: Path,
    *,
    generated_drift: list[str] | None = None,
    asset_deletions: list[str] | None = None,
    source_changes: list[str] | None = None,
    other_changes: list[str] | None = None,
) -> None:
    pathspec_dir.mkdir()
    categories = {
        "generated_drift.txt": generated_drift or [],
        "asset_deletions.txt": asset_deletions or [],
        "source_changes.txt": source_changes or [],
        "other_changes.txt": other_changes or [],
    }
    for filename, paths in categories.items():
        pathspec_dir.joinpath(filename).write_text(
            "\n".join(paths) + ("\n" if paths else ""),
            encoding="utf-8",
        )


def _run_verify(
    pathspec_dir: Path,
    status_fixture: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--pathspec-dir",
            str(pathspec_dir),
            "--status-file",
            str(status_fixture),
            *args,
        ],
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
    )


def test_matching_plan_passes_and_flags_asset_deletions_for_approval(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(
        tmp_path,
        [
            " M implementation/phase1/open_data/generated_case.json",
            " D Code_Generated_Image.png",
        ],
    )
    pathspec_dir = tmp_path / "pathspecs"
    _write_pathspecs(
        pathspec_dir,
        generated_drift=["implementation/phase1/open_data/generated_case.json"],
        asset_deletions=["Code_Generated_Image.png"],
    )

    proc = _run_verify(pathspec_dir, status_fixture)

    assert proc.returncode == 0
    assert "cleanup plan matches current worktree drift" in proc.stdout
    assert "asset_deletions: 1 (requires separate approval)" in proc.stdout
    assert proc.stderr == ""


def test_stale_mismatched_pathspec_fails_with_json_details(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(
        tmp_path,
        [" M implementation/phase1/open_data/current_case.json"],
    )
    pathspec_dir = tmp_path / "pathspecs"
    _write_pathspecs(
        pathspec_dir,
        generated_drift=["implementation/phase1/open_data/stale_case.json"],
    )

    proc = _run_verify(pathspec_dir, status_fixture, "--json")

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["mismatches"] == {
        "generated_drift": {
            "missing_from_plan": ["implementation/phase1/open_data/current_case.json"],
            "stale_in_plan": ["implementation/phase1/open_data/stale_case.json"],
        }
    }
    assert proc.stderr == ""


def test_source_changes_fail_by_default_and_pass_with_allow_source(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(
        tmp_path,
        [" M scripts/report_worktree_drift.py"],
    )
    pathspec_dir = tmp_path / "pathspecs"
    _write_pathspecs(
        pathspec_dir,
        source_changes=["scripts/report_worktree_drift.py"],
    )

    blocked = _run_verify(pathspec_dir, status_fixture)
    allowed = _run_verify(pathspec_dir, status_fixture, "--allow-source")

    assert blocked.returncode == 1
    assert "source_changes: 1 (blocked; rerun with --allow-source to permit)" in blocked.stdout
    assert allowed.returncode == 0
    assert "source_changes: 1 (allowed by --allow-source)" in allowed.stdout
    assert blocked.stderr == ""
    assert allowed.stderr == ""


def test_missing_category_file_fails(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(tmp_path, [])
    pathspec_dir = tmp_path / "pathspecs"
    _write_pathspecs(pathspec_dir)
    pathspec_dir.joinpath("other_changes.txt").unlink()

    proc = _run_verify(pathspec_dir, status_fixture)

    assert proc.returncode == 1
    assert "missing category file: other_changes.txt" in proc.stdout
    assert proc.stderr == ""
