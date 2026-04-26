from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_support_reports(tmp_path: Path) -> dict[str, Path]:
    gap = tmp_path / "release_gap_report.json"
    commercial = tmp_path / "commercial_readiness_report.json"
    tpu = tmp_path / "tpu_hffb_benchmark_gate_report.json"
    peer = tmp_path / "peer_spd_hinge_benchmark_gate_report.json"
    fixture = tmp_path / "peer_spd_hinge_fixture_regression_report.json"
    alignment = tmp_path / "peer_spd_hinge_refresh_alignment_report.json"
    _write(
        gap,
        {
            "summary": {
                "panel_zone_3d_clash_ready": True,
                "panel_zone_validation_boundary": "external_validation_only",
                "pbd_dynamic_hinge_refresh_ready": True,
                "foundation_optimization_ready": True,
                "wind_tunnel_raw_mapping_ready": True,
                "mgt_export_evidence_model": "direct_patch_plus_audit_review_manifest",
                "mgt_export_instruction_sidecar_change_count": 0,
                "mgt_export_audit_review_queue_pending_count": 2,
                "mgt_export_audit_review_followup_overdue_item_count": 0,
                "mgt_export_audit_review_resolution_open_revision_count": 0,
            }
        },
    )
    _write(
        commercial,
        {
            "contract_pass": True,
            "checks": {"real_source_pass": True, "gpu_strict_pass": True},
        },
    )
    for path in (tpu, peer, fixture, alignment):
        _write(path, {"contract_pass": True})
    return {
        "gap": gap,
        "commercial": commercial,
        "tpu": tpu,
        "peer": peer,
        "fixture": fixture,
        "alignment": alignment,
    }


def _build_queue_fixture(tmp_path: Path) -> tuple[Path, Path]:
    status_dir = tmp_path / "queue_status"
    manifest = tmp_path / "audit_review_queue.json"
    status_1 = status_dir / "01.connection.review_status.json"
    status_2 = status_dir / "02.detailing.review_status.json"
    _write(
        status_1,
        {
            "schema_version": "1.0",
            "packet_id": "connection|high",
            "action_family": "connection_detailing",
            "followup_type": "connection_detailing_audit_after_material_patch",
            "review_priority": "high",
            "review_owner": "licensed_engineer",
            "queue_status": "pending_review",
            "acknowledged": False,
            "resolution": "",
            "packet_file_path": str(tmp_path / "packet_01.json"),
            "change_count": 6,
            "row_count": 6,
        },
    )
    _write(
        status_2,
        {
            "schema_version": "1.0",
            "packet_id": "detail|medium",
            "action_family": "detailing",
            "followup_type": "detailing_audit_after_material_patch",
            "review_priority": "medium",
            "review_owner": "licensed_engineer",
            "queue_status": "pending_review",
            "acknowledged": False,
            "resolution": "",
            "packet_file_path": str(tmp_path / "packet_02.json"),
            "change_count": 5,
            "row_count": 5,
        },
    )
    _write(
        manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_status_directory": str(status_dir),
            "audit_review_queue_items": [
                {
                    "packet_id": "connection|high",
                    "action_family": "connection_detailing",
                    "followup_type": "connection_detailing_audit_after_material_patch",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "acknowledged": False,
                    "resolution": "",
                    "path": str(status_1),
                    "packet_file_path": str(tmp_path / "packet_01.json"),
                    "change_count": 6,
                    "row_count": 6,
                },
                {
                    "packet_id": "detail|medium",
                    "action_family": "detailing",
                    "followup_type": "detailing_audit_after_material_patch",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "acknowledged": False,
                    "resolution": "",
                    "path": str(status_2),
                    "packet_file_path": str(tmp_path / "packet_02.json"),
                    "change_count": 5,
                    "row_count": 5,
                },
            ],
        },
    )
    batch = tmp_path / "batch_updates.json"
    _write(
        batch,
        {
            "attestation": {
                "reviewer_name": "Kim PE",
                "reviewer_license_id": "PE-KR-001",
                "decision_basis": "review packet checked against latest patch artifacts",
                "review_session_id": "session-001",
                "attested_at_utc": "2026-03-22T00:00:00+00:00",
                "apply_live_acknowledged": True,
            },
            "updates": [
                {"packet_id": "connection|high", "set_status": "approved"},
                {"packet_id": "detail|medium", "set_status": "approved"},
            ],
        },
    )
    return manifest, batch


def test_run_audit_review_decision_batch_preview_only(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    manifest, batch = _build_queue_fixture(tmp_path)
    preview_out = tmp_path / "preview.json"
    out = tmp_path / "run_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_audit_review_decision_batch.py",
            "--queue-manifest",
            str(manifest),
            "--batch-updates-json",
            str(batch),
            "--release-gap-report",
            str(reports["gap"]),
            "--commercial-readiness-report",
            str(reports["commercial"]),
            "--tpu-hffb-benchmark-report",
            str(reports["tpu"]),
            "--peer-spd-hinge-benchmark-report",
            str(reports["peer"]),
            "--peer-spd-hinge-fixture-regression-report",
            str(reports["fixture"]),
            "--peer-spd-hinge-alignment-report",
            str(reports["alignment"]),
            "--preview-out",
            str(preview_out),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["apply_live"] is False
    assert payload["live_applied"] is False
    assert payload["preview_reason_code"] == "PASS_START_NOW_FULL"
    assert payload["preview_ready_full"] is True
    refreshed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert refreshed_manifest["audit_review_queue_items"][0]["queue_status"] == "pending_review"
    assert preview_out.exists()


def test_run_audit_review_decision_batch_apply_live(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    manifest, batch = _build_queue_fixture(tmp_path)
    preview_out = tmp_path / "preview.json"
    out = tmp_path / "run_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_audit_review_decision_batch.py",
            "--queue-manifest",
            str(manifest),
            "--batch-updates-json",
            str(batch),
            "--release-gap-report",
            str(reports["gap"]),
            "--commercial-readiness-report",
            str(reports["commercial"]),
            "--tpu-hffb-benchmark-report",
            str(reports["tpu"]),
            "--peer-spd-hinge-benchmark-report",
            str(reports["peer"]),
            "--peer-spd-hinge-fixture-regression-report",
            str(reports["fixture"]),
            "--peer-spd-hinge-alignment-report",
            str(reports["alignment"]),
            "--preview-out",
            str(preview_out),
            "--out",
            str(out),
            "--apply-live",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["apply_live"] is True
    assert payload["live_applied"] is True
    assert payload["preview_reason_code"] == "PASS_START_NOW_FULL"
    assert payload["batch_attestation"]["reviewer_name"] == "Kim PE"
    refreshed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert refreshed_manifest["summary"]["audit_review_queue_pending_count"] == 0
    assert refreshed_manifest["summary"]["audit_review_queue_approved_count"] == 2
    status_file = Path(refreshed_manifest["audit_review_queue_items"][0]["path"])
    status_payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert status_payload["last_decision_attestation"]["reviewer_name"] == "Kim PE"
    assert status_payload["last_decision_attestation"]["reviewer_license_id"] == "PE-KR-001"
    queue_update_report = json.loads(out.with_name("run_report.queue_update.json").read_text(encoding="utf-8"))
    assert queue_update_report["reason_code"] == "PASS"
    assert queue_update_report["batch_attestation"]["reviewer_name"] == "Kim PE"


def test_run_audit_review_decision_batch_apply_live_requires_attestation(tmp_path: Path) -> None:
    reports = _write_support_reports(tmp_path)
    manifest, batch = _build_queue_fixture(tmp_path)
    preview_out = tmp_path / "preview.json"
    out = tmp_path / "run_report.json"
    payload = json.loads(batch.read_text(encoding="utf-8"))
    payload["attestation"] = {
        "reviewer_name": "",
        "reviewer_license_id": "",
        "decision_basis": "",
        "apply_live_acknowledged": False,
    }
    batch.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_audit_review_decision_batch.py",
            "--queue-manifest",
            str(manifest),
            "--batch-updates-json",
            str(batch),
            "--release-gap-report",
            str(reports["gap"]),
            "--commercial-readiness-report",
            str(reports["commercial"]),
            "--tpu-hffb-benchmark-report",
            str(reports["tpu"]),
            "--peer-spd-hinge-benchmark-report",
            str(reports["peer"]),
            "--peer-spd-hinge-fixture-regression-report",
            str(reports["fixture"]),
            "--peer-spd-hinge-alignment-report",
            str(reports["alignment"]),
            "--preview-out",
            str(preview_out),
            "--out",
            str(out),
            "--apply-live",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_MISSING_ATTESTATION"
    assert "reviewer_name" in report["batch_attestation_missing_fields"]
    assert "reviewer_license_id" in report["batch_attestation_missing_fields"]
    assert "decision_basis" in report["batch_attestation_missing_fields"]
    assert "apply_live_acknowledged" in report["batch_attestation_missing_fields"]
