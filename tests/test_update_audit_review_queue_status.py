from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_queue_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    status_dir = tmp_path / "queue_status"
    manifest = tmp_path / "audit_review_queue.json"
    export_report = tmp_path / "custom.export_report.json"
    status_1 = status_dir / "01.connection.review_status.json"
    status_2 = status_dir / "02.detailing.review_status.json"

    _write(
        status_1,
        {
            "schema_version": "1.0",
            "packet_id": "connection_detailing|connection_detailing_audit_after_material_patch|high",
            "action_family": "connection_detailing",
            "followup_type": "connection_detailing_audit_after_material_patch",
            "review_priority": "high",
            "review_owner": "licensed_engineer",
            "queue_status": "pending_review",
            "acknowledged": False,
            "resolution": "",
            "change_count": 6,
            "row_count": 6,
            "packet_file_path": str(tmp_path / "packet_01.json"),
        },
    )
    _write(
        status_2,
        {
            "schema_version": "1.0",
            "packet_id": "detailing|detailing_audit_after_material_patch|medium",
            "action_family": "detailing",
            "followup_type": "detailing_audit_after_material_patch",
            "review_priority": "medium",
            "review_owner": "licensed_engineer",
            "queue_status": "pending_review",
            "acknowledged": False,
            "resolution": "",
            "change_count": 5,
            "row_count": 5,
            "packet_file_path": str(tmp_path / "packet_02.json"),
        },
    )
    _write(
        manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_items": [
                {
                    "packet_id": "connection_detailing|connection_detailing_audit_after_material_patch|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "queue_status": "pending_review",
                    "acknowledged": False,
                    "path": str(status_1),
                    "packet_file_path": str(tmp_path / "packet_01.json"),
                    "change_count": 6,
                    "row_count": 6,
                },
                {
                    "packet_id": "detailing|detailing_audit_after_material_patch|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "queue_status": "pending_review",
                    "acknowledged": False,
                    "path": str(status_2),
                    "packet_file_path": str(tmp_path / "packet_02.json"),
                    "change_count": 5,
                    "row_count": 5,
                },
            ],
            "audit_review_queue_status_directory": str(status_dir),
            "summary": {
                "audit_review_queue_item_count": 2,
                "audit_review_queue_pending_count": 2,
                "audit_review_queue_acknowledged_count": 0,
                "audit_review_queue_status_counts": {"pending_review": 2},
                "audit_review_queue_action_family_counts": {"connection_detailing": 1, "detailing": 1},
                "audit_review_queue_status_mode": "generated_pending_review_queue",
            },
        },
    )
    _write(
        export_report,
        {
            "contract_pass": True,
            "summary": {
                "support_mode": "test",
                "audit_review_queue_item_count": 2,
                "audit_review_queue_pending_count": 2,
                "audit_review_queue_acknowledged_count": 0,
                "audit_review_queue_status_counts": {"pending_review": 2},
                "audit_review_queue_action_family_counts": {"connection_detailing": 1, "detailing": 1},
            },
        },
    )
    return manifest, export_report, status_1, status_2, status_dir


def test_update_audit_review_queue_status_by_packet_id(tmp_path: Path) -> None:
    manifest, export_report, status_1, _status_2, _status_dir = _build_queue_fixture(tmp_path)
    followup_manifest = tmp_path / "audit_review_followup_manifest.json"
    resolution_manifest = tmp_path / "audit_review_resolution_manifest.json"
    resolution_dir = tmp_path / "audit_review_resolution_files"
    out = tmp_path / "update_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_audit_review_queue_status.py",
            "--queue-manifest",
            str(manifest),
            "--mgt-export-report",
            str(export_report),
            "--audit-review-followup-manifest",
            str(followup_manifest),
            "--audit-review-resolution-manifest",
            str(resolution_manifest),
            "--audit-review-resolution-dir",
            str(resolution_dir),
            "--packet-id",
            "connection_detailing|connection_detailing_audit_after_material_patch|high",
            "--set-status",
            "approved",
            "--note",
            "review complete",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    updated_status = json.loads(status_1.read_text(encoding="utf-8"))
    assert updated_status["queue_status"] == "approved"
    assert updated_status["acknowledged"] is True
    assert updated_status["resolution"] == "approved"
    assert updated_status["status_history"][-1]["to_status"] == "approved"

    refreshed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    summary = refreshed_manifest["summary"]
    assert summary["audit_review_queue_item_count"] == 2
    assert summary["audit_review_queue_pending_count"] == 1
    assert summary["audit_review_queue_acknowledged_count"] == 1
    assert summary["audit_review_queue_approved_count"] == 1
    assert summary["audit_review_queue_status_counts"] == {"approved": 1, "pending_review": 1}
    assert summary["audit_review_queue_status_mode"] == "refreshed_from_status_files"

    patched_export_report = json.loads(export_report.read_text(encoding="utf-8"))
    assert patched_export_report["summary"]["audit_review_queue_pending_count"] == 1
    assert patched_export_report["summary"]["audit_review_queue_acknowledged_count"] == 1
    assert patched_export_report["summary"]["audit_review_queue_sync_source"] == "queue_manifest_override"
    assert patched_export_report["summary"]["audit_review_followup_action_counts"] == {
        "close_packet": 1,
        "wait_for_review": 1,
    }

    followup_payload = json.loads(followup_manifest.read_text(encoding="utf-8"))
    assert followup_payload["summary"]["audit_review_followup_open_item_count"] == 1
    assert followup_payload["summary"]["audit_review_followup_closed_item_count"] == 1
    resolution_payload = json.loads(resolution_manifest.read_text(encoding="utf-8"))
    assert resolution_payload["summary"]["audit_review_resolution_action_counts"] == {
        "await_review_decision": 1,
        "close_packet": 1,
    }

    update_report = json.loads(out.read_text(encoding="utf-8"))
    assert update_report["reason_code"] == "PASS"
    assert update_report["current_status"] == "approved"
    assert update_report["export_report_patched"] is True
    assert update_report["followup_summary"]["audit_review_followup_action_counts"] == {
        "close_packet": 1,
        "wait_for_review": 1,
    }
    assert update_report["resolution_summary"]["audit_review_resolution_status_counts"] == {
        "closed_packet": 1,
        "pending_review": 1,
    }


def test_update_audit_review_queue_status_by_status_file(tmp_path: Path) -> None:
    manifest, export_report, _status_1, status_2, _status_dir = _build_queue_fixture(tmp_path)
    followup_manifest = tmp_path / "audit_review_followup_manifest.json"
    resolution_manifest = tmp_path / "audit_review_resolution_manifest.json"
    resolution_dir = tmp_path / "audit_review_resolution_files"
    out = tmp_path / "update_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_audit_review_queue_status.py",
            "--queue-manifest",
            str(manifest),
            "--mgt-export-report",
            str(export_report),
            "--audit-review-followup-manifest",
            str(followup_manifest),
            "--audit-review-resolution-manifest",
            str(resolution_manifest),
            "--audit-review-resolution-dir",
            str(resolution_dir),
            "--status-file",
            str(status_2),
            "--set-status",
            "rejected",
            "--resolution",
            "needs panel anchorage clarification",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    updated_status = json.loads(status_2.read_text(encoding="utf-8"))
    assert updated_status["queue_status"] == "rejected"
    assert updated_status["acknowledged"] is True
    assert updated_status["resolution"] == "needs panel anchorage clarification"

    refreshed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    summary = refreshed_manifest["summary"]
    assert summary["audit_review_queue_pending_count"] == 1
    assert summary["audit_review_queue_acknowledged_count"] == 1
    assert summary["audit_review_queue_rejected_count"] == 1
    assert summary["audit_review_queue_status_counts"] == {"pending_review": 1, "rejected": 1}

    followup_payload = json.loads(followup_manifest.read_text(encoding="utf-8"))
    assert followup_payload["summary"]["audit_review_followup_action_counts"] == {
        "reopen_revision_cycle": 1,
        "wait_for_review": 1,
    }
    resolution_payload = json.loads(resolution_manifest.read_text(encoding="utf-8"))
    assert resolution_payload["summary"]["audit_review_resolution_status_counts"] == {
        "pending_review": 1,
        "revision_package_open": 1,
    }


def test_update_audit_review_queue_status_supports_batch_updates(tmp_path: Path) -> None:
    manifest, export_report, _status_1, _status_2, _status_dir = _build_queue_fixture(tmp_path)
    followup_manifest = tmp_path / "audit_review_followup_manifest.json"
    resolution_manifest = tmp_path / "audit_review_resolution_manifest.json"
    resolution_dir = tmp_path / "audit_review_resolution_files"
    batch = tmp_path / "updates.json"
    out = tmp_path / "update_report.json"
    _write(
        batch,
        {
            "attestation": {
                "reviewer_name": "Kim PE",
                "reviewer_license_id": "PE-KR-001",
                "decision_basis": "batch review completed",
                "review_session_id": "session-002",
                "attested_at_utc": "2026-03-22T00:00:00+00:00",
                "apply_live_acknowledged": True,
            },
            "updates": [
                {
                    "packet_id": "connection_detailing|connection_detailing_audit_after_material_patch|high",
                    "set_status": "approved",
                    "note": "approved in batch",
                },
                {
                    "packet_id": "detailing|detailing_audit_after_material_patch|medium",
                    "set_status": "acknowledged",
                    "note": "review scheduled",
                },
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_audit_review_queue_status.py",
            "--queue-manifest",
            str(manifest),
            "--mgt-export-report",
            str(export_report),
            "--audit-review-followup-manifest",
            str(followup_manifest),
            "--audit-review-resolution-manifest",
            str(resolution_manifest),
            "--audit-review-resolution-dir",
            str(resolution_dir),
            "--batch-updates-json",
            str(batch),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    refreshed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    summary = refreshed_manifest["summary"]
    assert summary["audit_review_queue_item_count"] == 2
    assert summary["audit_review_queue_pending_count"] == 0
    assert summary["audit_review_queue_acknowledged_count"] == 2
    assert summary["audit_review_queue_approved_count"] == 1
    assert summary["audit_review_queue_status_counts"] == {"acknowledged": 1, "approved": 1}

    followup_payload = json.loads(followup_manifest.read_text(encoding="utf-8"))
    assert followup_payload["summary"]["audit_review_followup_action_counts"] == {
        "close_packet": 1,
        "review_in_progress": 1,
    }
    resolution_payload = json.loads(resolution_manifest.read_text(encoding="utf-8"))
    assert resolution_payload["summary"]["audit_review_resolution_action_counts"] == {
        "close_packet": 1,
        "continue_review": 1,
    }

    update_report = json.loads(out.read_text(encoding="utf-8"))
    assert update_report["batch_update_count"] == 2
    assert len(update_report["updates"]) == 2
    assert update_report["reason_code"] == "PASS"
    assert update_report["batch_attestation"]["reviewer_name"] == "Kim PE"


def test_update_audit_review_queue_status_supports_release_refresh_dry_run(tmp_path: Path) -> None:
    manifest, export_report, status_1, _status_2, _status_dir = _build_queue_fixture(tmp_path)
    followup_manifest = tmp_path / "audit_review_followup_manifest.json"
    resolution_manifest = tmp_path / "audit_review_resolution_manifest.json"
    resolution_dir = tmp_path / "audit_review_resolution_files"
    out = tmp_path / "update_report.json"
    before_status = json.loads(status_1.read_text(encoding="utf-8"))
    before_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    before_export_report = json.loads(export_report.read_text(encoding="utf-8"))

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/update_audit_review_queue_status.py",
            "--queue-manifest",
            str(manifest),
            "--mgt-export-report",
            str(export_report),
            "--audit-review-followup-manifest",
            str(followup_manifest),
            "--audit-review-resolution-manifest",
            str(resolution_manifest),
            "--audit-review-resolution-dir",
            str(resolution_dir),
            "--packet-id",
            "connection_detailing|connection_detailing_audit_after_material_patch|high",
            "--set-status",
            "approved",
            "--refresh-release-surfaces",
            "--dry-run",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    update_report = json.loads(out.read_text(encoding="utf-8"))
    assert update_report["refresh_release_surfaces"] is True
    assert update_report["release_surface_refresh_pass"] is True
    assert update_report["dry_run"] is True
    steps = {str(step["step"]): str(step["command"]) for step in update_report["steps"]}
    assert "release_gap_report" in steps
    assert "external_benchmark_submission_readiness" in steps
    assert "release_registry" in steps
    assert "committee_review_package" in steps
    assert "external_validation_submission" in steps
    assert "freeze_release_snapshot" in steps
    assert "promote_release_candidate" in steps
    assert str(manifest) in steps["release_gap_report"]
    assert str(export_report) in steps["release_gap_report"]
    assert str(followup_manifest) in steps["release_gap_report"]
    assert "generate_external_benchmark_submission_readiness.py" in steps["external_benchmark_submission_readiness"]
    assert update_report["state_write_skipped"] is True
    assert json.loads(status_1.read_text(encoding="utf-8")) == before_status
    assert json.loads(manifest.read_text(encoding="utf-8")) == before_manifest
    assert json.loads(export_report.read_text(encoding="utf-8")) == before_export_report
    assert not followup_manifest.exists()
    assert not resolution_manifest.exists()
