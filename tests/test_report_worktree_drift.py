"""Contract tests for the worktree drift triage report."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "report_worktree_drift.py"


def _write_status_fixture(tmp_path: Path, lines: list[str]) -> Path:
    fixture = tmp_path / "status.txt"
    fixture.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return fixture


def _run_report(status_fixture: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--status-file",
            str(status_fixture),
            *args,
        ],
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
    )


def test_clean_status_reports_zero_counts(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(tmp_path, [])

    proc = _run_report(status_fixture)

    assert proc.returncode == 0
    assert "generated_drift: 0" in proc.stdout
    assert "asset_deletions: 0" in proc.stdout
    assert "source_changes: 0" in proc.stdout
    assert "other_changes: 0" in proc.stdout
    assert proc.stderr == ""


def test_mixed_generated_and_asset_deletions_are_classified(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(
        tmp_path,
        [
            " M implementation/phase1/open_data/generated_case.json",
            " M implementation/phase1/stress/report.json",
            " M implementation/phase1/panel_zone_solver_verified_export_bundle.json",
            " D Code_Generated_Image.png",
            ' D "\\354\\212\\244\\355\\201\\254\\353\\246\\260\\354\\203\\267 2026-03-03 22-13-22.png"',
            " M scripts/report_worktree_drift.py",
        ],
    )

    proc = _run_report(status_fixture, "--json", "--fail-on-generated")

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["counts"] == {
        "generated_drift": 3,
        "asset_deletions": 2,
        "source_changes": 1,
        "other_changes": 0,
    }
    assert payload["generated_drift"] == [
        "implementation/phase1/open_data/generated_case.json",
        "implementation/phase1/stress/report.json",
        "implementation/phase1/panel_zone_solver_verified_export_bundle.json",
    ]
    assert payload["asset_deletions"] == [
        "Code_Generated_Image.png",
        "스크린샷 2026-03-03 22-13-22.png",
    ]
    assert payload["source_changes"] == ["scripts/report_worktree_drift.py"]
    assert proc.stderr == ""


def test_source_only_status_reports_source_changes_without_failure(tmp_path: Path) -> None:
    status_fixture = _write_status_fixture(
        tmp_path,
        [
            " M scripts/check_generated_worktree_clean.py",
            "?? tests/test_report_worktree_drift.py",
        ],
    )

    proc = _run_report(status_fixture)

    assert proc.returncode == 0
    assert "source_changes: 2" in proc.stdout
    assert "scripts/check_generated_worktree_clean.py" in proc.stdout
    assert "tests/test_report_worktree_drift.py" in proc.stdout
    assert "generated_drift: 0" in proc.stdout
    assert "asset_deletions: 0" in proc.stdout
    assert proc.stderr == ""
