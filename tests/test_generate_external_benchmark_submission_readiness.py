from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(
    tmp_path: Path,
    *,
    pending: int,
    overdue: int,
    open_revision: int = 0,
    wind_ready: bool = True,
    commercial_pass: bool = True,
) -> dict:
    gap = tmp_path / "release_gap_report.json"
    commercial = tmp_path / "commercial_readiness_report.json"
    tpu = tmp_path / "tpu_hffb_benchmark_gate_report.json"
    peer = tmp_path / "peer_spd_hinge_benchmark_gate_report.json"
    fixture = tmp_path / "peer_spd_hinge_fixture_regression_report.json"
    alignment = tmp_path / "peer_spd_hinge_refresh_alignment_report.json"
    out = tmp_path / "external_benchmark_submission_readiness.json"

    _write(
        gap,
        {
            "summary": {
                "panel_zone_3d_clash_ready": True,
                "panel_zone_validation_boundary": "external_validation_only",
                "pbd_dynamic_hinge_refresh_ready": True,
                "foundation_optimization_ready": True,
                "wind_tunnel_raw_mapping_ready": wind_ready,
                "mgt_export_evidence_model": "direct_patch_plus_zero_touch_verification_manifest",
                "mgt_export_instruction_sidecar_change_count": 0,
                "mgt_export_audit_review_queue_pending_count": pending,
                "mgt_export_audit_review_followup_overdue_item_count": overdue,
                "mgt_export_audit_review_resolution_open_revision_count": open_revision,
            }
        },
    )
    _write(
        commercial,
        {
            "contract_pass": commercial_pass,
            "checks": {
                "real_source_pass": commercial_pass,
                "gpu_strict_pass": commercial_pass,
            },
        },
    )
    for path in (tpu, peer, fixture, alignment):
        _write(path, {"contract_pass": True})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_submission_readiness.py",
            "--release-gap-report",
            str(gap),
            "--commercial-readiness-report",
            str(commercial),
            "--tpu-hffb-benchmark-report",
            str(tpu),
            "--peer-spd-hinge-benchmark-report",
            str(peer),
            "--peer-spd-hinge-fixture-regression-report",
            str(fixture),
            "--peer-spd-hinge-alignment-report",
            str(alignment),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_external_benchmark_submission_readiness_allows_limited_start_with_clean_pending_queue(tmp_path: Path) -> None:
    payload = _run(tmp_path, pending=2, overdue=0)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_START_NOW_LIMITED"
    assert payload["summary"]["recommended_start_mode"] == "start_now_limited_external_benchmark"
    assert payload["summary"]["recommended_submission_scope"] == "component_and_system_performance_benchmark_with_review_boundary"
    assert payload["summary"]["mgt_export_audit_only_boundary_ready"] is True
    assert payload["summary"]["blocker_label"] == "none"
    assert payload["summary"]["audit_review_queue_pending_count"] == 2
    assert payload["summary"]["audit_review_queue_overdue_item_count"] == 0
    assert payload["summary"]["audit_review_resolution_open_revision_count"] == 0
    assert payload["checks"]["panel_zone_validation_advisory_only"] is True
    assert payload["summary"]["panel_zone_validation_advisory_only"] is True
    assert payload["summary"]["panel_zone_validation_advisory_label"] == "panel_zone_external_validation_only_boundary"
    assert "panel_zone_external_validation_only_boundary" in payload["summary"]["cautions"]
    assert "audit_review_queue_pending=2" in payload["summary"]["cautions"]


def test_external_benchmark_submission_readiness_allows_full_start_when_queue_closed(tmp_path: Path) -> None:
    payload = _run(tmp_path, pending=0, overdue=0)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_START_NOW_FULL"
    assert payload["summary"]["recommended_start_mode"] == "start_now_full_external_submission"
    assert payload["summary"]["ready_to_start_full_submission_now"] is True


def test_external_benchmark_submission_readiness_blocks_on_open_revision_cycle(tmp_path: Path) -> None:
    payload = _run(tmp_path, pending=0, overdue=0, open_revision=1)
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    blockers = set(payload["summary"]["blockers"])
    assert "audit_review_resolution_has_open_revisions" in blockers
    assert payload["summary"]["audit_review_resolution_open_revision_count"] == 1
    assert payload["checks"]["audit_review_resolution_clear"] is False


def test_external_benchmark_submission_readiness_blocks_on_architecture_gaps(tmp_path: Path) -> None:
    payload = _run(tmp_path, pending=0, overdue=1, wind_ready=False, commercial_pass=False)
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    blockers = set(payload["summary"]["blockers"])
    assert "core_holdouts_not_closed" in blockers
    assert "commercial_readiness_not_green" in blockers
    assert "audit_review_queue_has_overdue_items" in blockers
    assert payload["summary"]["recommended_start_mode"] == "wait_for_blockers"
