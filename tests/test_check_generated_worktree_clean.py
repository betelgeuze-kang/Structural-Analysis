"""Contract tests for the generated artifact worktree guard."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "check_generated_worktree_clean.py"


def _write_diff_fixture(tmp_path: Path, paths: list[str]) -> Path:
    fixture = tmp_path / "diff-name-only.txt"
    fixture.write_text("\n".join(paths) + "\n", encoding="utf-8")
    return fixture


def _run_guard(diff_fixture: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--diff-name-only-file",
            str(diff_fixture),
            *args,
        ],
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
    )


def test_clean_diff_name_only_list_passes_with_ok_output(tmp_path: Path) -> None:
    diff_fixture = _write_diff_fixture(tmp_path, [])

    proc = _run_guard(diff_fixture, "--show-ok")

    assert proc.returncode == 0
    assert proc.stdout.strip() == "OK: no tracked generated artifact drift detected."
    assert proc.stderr == ""


def test_generated_dirty_paths_fail_and_are_reported(tmp_path: Path) -> None:
    diff_fixture = _write_diff_fixture(
        tmp_path,
        [
            "implementation/phase1/open_data/generated_case.json",
            "implementation/phase1/stress/report.json",
            "implementation/phase1/panel_zone_solver_verified_export_bundle.json",
            "implementation/phase1/panel_zone_solver_verified_inbox_status.json",
            "implementation/phase1/solver_source.py",
        ],
    )

    proc = _run_guard(diff_fixture)

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "tracked generated artifact drift detected" in proc.stderr
    assert "implementation/phase1/open_data/generated_case.json" in proc.stderr
    assert "implementation/phase1/stress/report.json" in proc.stderr
    assert "implementation/phase1/panel_zone_solver_verified_export_bundle.json" in proc.stderr
    assert "implementation/phase1/panel_zone_solver_verified_inbox_status.json" in proc.stderr
    assert "implementation/phase1/solver_source.py" not in proc.stderr


def test_unrelated_source_dirty_paths_pass(tmp_path: Path) -> None:
    diff_fixture = _write_diff_fixture(
        tmp_path,
        [
            "implementation/phase1/open_dataset_reader.py",
            "implementation/phase1/stress_solver.py",
            "implementation/phase1/solver_source.py",
            "tests/test_solver_source.py",
        ],
    )

    proc = _run_guard(diff_fixture)

    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""
