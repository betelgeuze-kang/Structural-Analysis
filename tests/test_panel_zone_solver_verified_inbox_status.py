from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_drop(inbox: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / "drop_package"),
            "--inbox-dir",
            str(inbox),
            "--clean",
            "--out",
            str(inbox / "stage_report.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_panel_zone_solver_verified_inbox_status_marks_pending_raw_triplet(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    _stage_drop(inbox)
    out = tmp_path / "inbox_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_inbox_status.py",
            "--inbox-dir",
            str(inbox),
            "--archive-dir",
            str(tmp_path / "archive"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = _load_json(out)
    summary = payload["summary"]
    assert payload["contract_pass"] is True
    assert summary["panel_zone_solver_verified_inbox_status_mode"] == "pending_raw_triplet"
    assert summary["panel_zone_solver_verified_pending_input"] is True
    assert summary["panel_zone_solver_verified_input_mode_detected"] == "raw_triplet"
    assert summary["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    assert summary["panel_zone_solver_verified_release_refresh_source_allowed"] is False
    assert summary["panel_zone_solver_verified_latest_consume_contract_pass"] is False
    assert summary["panel_zone_solver_verified_recommended_action"] == "consume_pending_input"


def test_panel_zone_solver_verified_inbox_status_marks_empty_after_successful_consume(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    _stage_drop(inbox)
    pbd = tmp_path / "pbd_review_package_report.json"
    pbd.write_text(json.dumps({"contract_pass": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_dir = tmp_path / "archive"
    consume_report = inbox / "consume_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox),
            "--handoff-report-out",
            str(tmp_path / "handoff_report.json"),
            "--design-optimization-dataset",
            str(FIXTURE_DIR / "design_optimization_dataset_report.json"),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-solver-export-bundle",
            str(tmp_path / "panel_zone_solver_verified_export_bundle.json"),
            "--panel-zone-joint-geometry-source-output",
            str(tmp_path / "panel_zone_joint_geometry_3d.json"),
            "--panel-zone-rebar-anchorage-source-output",
            str(tmp_path / "panel_zone_rebar_anchorage_3d.json"),
            "--panel-zone-clash-verification-source-output",
            str(tmp_path / "panel_zone_clash_verification_3d.json"),
            "--panel-zone-joint-geometry-contract",
            str(tmp_path / "panel_zone_joint_geometry_3d_contract.json"),
            "--panel-zone-rebar-anchorage-contract",
            str(tmp_path / "panel_zone_rebar_anchorage_3d_contract.json"),
            "--panel-zone-clash-verification-contract",
            str(tmp_path / "panel_zone_clash_verification_3d_contract.json"),
            "--panel-zone-clash-artifact",
            str(tmp_path / "panel_zone_clash_artifact.json"),
            "--panel-zone-clash-report",
            str(tmp_path / "panel_zone_clash_report.json"),
            "--inbox-status-report",
            str(tmp_path / "panel_zone_solver_verified_inbox_status.consume.json"),
            "--archive-dir",
            str(archive_dir),
            "--archive-on-success",
            "--clean-inbox-on-success",
            "--out",
            str(consume_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    out = tmp_path / "inbox_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_inbox_status.py",
            "--inbox-dir",
            str(inbox),
            "--archive-dir",
            str(archive_dir),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = _load_json(out)
    summary = payload["summary"]
    assert summary["panel_zone_solver_verified_inbox_status_mode"] == "empty_after_successful_consume"
    assert summary["panel_zone_solver_verified_pending_input"] is False
    assert summary["panel_zone_solver_verified_latest_consume_contract_pass"] is True
    assert summary["panel_zone_solver_verified_latest_consume_reason_code"] == "PASS"
    assert summary["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    assert summary["panel_zone_solver_verified_release_refresh_source_allowed"] is False
    assert summary["panel_zone_solver_verified_latest_archive_dir"].startswith(str(archive_dir))
    assert summary["panel_zone_solver_verified_recommended_action"] == "local_closeout_closed"


def test_panel_zone_solver_verified_inbox_status_requires_exact_trusted_origin_for_release_refresh(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/stage_panel_zone_solver_verified_drop.py",
            "--source-drop-dir",
            str(FIXTURE_DIR / "trusted_drop_package"),
            "--source-origin-class",
            "partner_external_solver_source",
            "--inbox-dir",
            str(inbox),
            "--clean",
            "--out",
            str(inbox / "stage_report.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    out = tmp_path / "inbox_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_inbox_status.py",
            "--inbox-dir",
            str(inbox),
            "--archive-dir",
            str(tmp_path / "archive"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = _load_json(out)
    summary = payload["summary"]
    assert summary["panel_zone_solver_verified_source_origin_class"] == "partner_external_solver_source"
    assert summary["panel_zone_solver_verified_release_refresh_source_allowed"] is False
