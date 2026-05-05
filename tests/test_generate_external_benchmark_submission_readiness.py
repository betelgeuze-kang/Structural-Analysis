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
    submission_updates: dict | None = None,
) -> dict:
    gap = tmp_path / "release_gap_report.json"
    commercial = tmp_path / "commercial_readiness_report.json"
    tpu = tmp_path / "tpu_hffb_benchmark_gate_report.json"
    peer = tmp_path / "peer_spd_hinge_benchmark_gate_report.json"
    fixture = tmp_path / "peer_spd_hinge_fixture_regression_report.json"
    alignment = tmp_path / "peer_spd_hinge_refresh_alignment_report.json"
    out = tmp_path / "external_benchmark_submission_readiness.json"
    updates = tmp_path / "external_benchmark_submission_updates.json"

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
                "commercial_scope_summary_line": "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%",
                "commercial_reliability_breadth_summary_line": "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | evidence_rows=1 | evidence_present=True",
                "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
                "hardest_external_10case_kickoff_summary_line": "Hardest external 10-case kickoff: PASS | cases=10 | coverage=100% | dry_run=ready",
                "korean_source_ingest_summary_line": "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | seed=4 | topo=1 | native=1 | p0=3",
                "korean_structural_preview_queue_summary_line": "KR preview queue: PASS | cand=4 | pend=1 | state=open",
                "midas_kds_row_provenance_export_row_count": 144,
                "midas_kds_row_provenance_export_exact_row_count": 144,
                "midas_kds_row_provenance_preview_rows": [
                    {
                        "combination_name": "gLCB1",
                        "member_id": "C-TST-003",
                        "clause_label": "KDS-MOMENT-Y-001",
                        "baseline_focus_member_id": "27441",
                        "bridge_row_provenance_mode_label": "exact row-level provenance",
                        "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                        "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column",
                    }
                ],
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
    _write(
        tpu,
        {
            "contract_pass": True,
            "summary_line": "TPU/HFFB benchmark gate: PASS | assets=2 | ready=2 | raw_mapping=eligible",
        },
    )
    _write(
        peer,
        {
            "contract_pass": True,
            "summary_line": "PEER/SPD hinge benchmark gate: PASS | assets=2 | ready=2 | split=train:1,holdout:1",
        },
    )
    _write(
        fixture,
        {
            "contract_pass": True,
            "summary_line": "PEER/SPD hinge fixture regression: PASS | fixtures=2 | min_points=449",
        },
    )
    _write(
        alignment,
        {
            "contract_pass": True,
            "summary_line": "PEER/SPD hinge alignment: PASS | refresh_columns=2 | rebar_sensitive_columns=0",
        },
    )
    if submission_updates is not None:
        _write(updates, submission_updates)

    cmd = [
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
    ]
    if submission_updates is not None:
        cmd.extend(["--submission-updates", str(updates)])
    proc = subprocess.run(
        cmd,
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
    assert payload["summary"]["commercial_scope_summary_line"].startswith("Commercial scope: grade=Commercial")
    assert "engineer_in_loop_accelerated_coverage_ready=True" in payload["summary"]["commercial_scope_summary_line"]
    assert "full_commercial_replacement_ready=False" in payload["summary"]["commercial_scope_summary_line"]
    assert payload["summary"]["commercial_reliability_breadth_summary_line"].startswith("Commercial reliability breadth: PASS")
    assert payload["summary"]["midas_kds_row_provenance_exact_row_coverage_label"] == "144/144"
    assert payload["summary"]["midas_kds_row_provenance_preview_rows_present"] is True
    assert payload["summary"]["submission_queue_count"] == 4
    assert payload["summary"]["submission_queue_review_pending_count"] == 4
    assert payload["summary"]["submission_queue_ready_count"] == 0
    assert payload["summary"]["onepage_attestation_status"] == "draft_ready_final_review_pending"
    assert {row["queue_id"] for row in payload["submission_queue"]} == {
        "hardest_external_10case",
        "tpu_hffb",
        "peer_spd_hinge",
        "korean_public_structures",
    }
    assert all(
        row["status"] == "ready_for_benchmark_start_final_review_pending"
        for row in payload["submission_queue"]
    )
    assert [row["work_item_id"] for row in payload["submission_queue"]] == ["EB-001", "EB-002", "EB-003", "EB-004"]
    assert [row["submission_id"] for row in payload["submission_queue"]] == [
        "p1-hardest-external-10case",
        "p1-tpu-hffb",
        "p1-peer-spd-hinge",
        "p1-korean-public-structures",
    ]
    assert all("receipt_url" in row for row in payload["submission_queue"])
    assert all(row["closure_evidence_status"] == "pending" for row in payload["submission_queue"])
    assert all(row["status_lifecycle"]["current_status"] == row["status"] for row in payload["submission_queue"])
    assert all(row["submission_receipt"] == "pending" for row in payload["submission_queue"])
    assert all(
        row["submission_receipt_status"] == "not_due_review_boundary_pending"
        for row in payload["submission_queue"]
    )
    assert all(
        row["status_lifecycle"]["submission_receipt_status"] == row["submission_receipt_status"]
        for row in payload["submission_queue"]
    )
    assert payload["submission_queue"][0]["closure_evidence_required"] == "hardest_external_10case_submission_receipt"
    assert all("dry_run_evidence" in row for row in payload["submission_queue"])
    assert all("onepage_attestation_status" in row for row in payload["submission_queue"])
    assert payload["submission_queue"][0]["dry_run_evidence"] == "Hardest external 10-case kickoff: PASS | cases=10 | coverage=100% | dry_run=ready"
    assert payload["submission_queue"][1]["dry_run_evidence"] == (
        "TPU/HFFB benchmark gate: PASS | assets=2 | ready=2 | raw_mapping=eligible"
    )
    assert payload["submission_queue"][2]["dry_run_evidence"] == (
        "PEER/SPD hinge benchmark gate: PASS | assets=2 | ready=2 | split=train:1,holdout:1 | "
        "PEER/SPD hinge fixture regression: PASS | fixtures=2 | min_points=449 | "
        "PEER/SPD hinge alignment: PASS | refresh_columns=2 | rebar_sensitive_columns=0"
    )
    assert payload["submission_queue"][3]["dry_run_evidence"] == (
        "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | seed=4 | topo=1 | native=1 | p0=3 | "
        "KR preview queue: PASS | cand=4 | pend=1 | state=open"
    )
    assert all(
        row["commercial_scope_summary_line"].startswith("Commercial scope: grade=Commercial")
        for row in payload["submission_queue"]
    )
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
    assert payload["summary"]["commercial_scope_summary_line"].startswith("Commercial scope: grade=Commercial")
    assert payload["summary"]["submission_queue_ready_count"] == 4
    assert payload["summary"]["onepage_attestation_status"] == "ready_for_full_submission"
    assert all(row["status"] == "ready_for_full_submission" for row in payload["submission_queue"])
    assert all(row["submission_receipt"] == "pending" for row in payload["submission_queue"])
    assert all(
        row["submission_receipt_status"] == "pending_external_submission_receipt"
        for row in payload["submission_queue"]
    )


def test_external_benchmark_submission_readiness_merges_submission_update_sidecar(tmp_path: Path) -> None:
    payload = _run(
        tmp_path,
        pending=0,
        overdue=0,
        submission_updates={
            "updates": {
                "hardest_external_10case": {
                    "submission_id": "ext-bench-2026-05-hardest",
                    "receipt_url": "https://bench.example/receipts/EB-001",
                    "submitted_at_utc": "2026-05-05T01:02:03Z",
                    "last_checked_at_utc": "2026-05-05T02:03:04Z",
                    "closure_evidence_path": "release_evidence/productization/EB-001.receipt.json",
                    "closure_evidence_status": "attached",
                }
            }
        },
    )

    row = payload["submission_queue"][0]
    assert row["queue_id"] == "hardest_external_10case"
    assert row["submission_id"] == "ext-bench-2026-05-hardest"
    assert row["receipt_url"] == "https://bench.example/receipts/EB-001"
    assert row["submission_receipt"] == "https://bench.example/receipts/EB-001"
    assert row["submitted_at_utc"] == "2026-05-05T01:02:03Z"
    assert row["last_checked_at_utc"] == "2026-05-05T02:03:04Z"
    assert row["closure_evidence_status"] == "attached"
    assert row["closure_evidence_path"].endswith("EB-001.receipt.json")
    assert row["submission_status"] == "submitted_receipt_attached"
    assert row["submission_lifecycle_status"] == "submitted_receipt_attached"
    assert row["submission_lifecycle"] == "submitted_receipt_attached"
    assert row["lifecycle"] == "submitted_receipt_attached"
    assert row["receipt_status"] == "attached"
    assert row["status_lifecycle"]["submitted"] is True
    assert row["status_lifecycle"]["receipt_verified"] is True
    assert payload["summary"]["submission_receipt_pending_count"] == 3
    assert payload["summary"]["submission_receipt_attached_count"] == 1
    assert payload["summary"]["submission_last_checked_count"] == 1
    assert payload["summary"]["closure_evidence_attached_count"] == 1
    assert payload["artifacts"]["external_benchmark_submission_updates_present"] is True


def test_external_benchmark_submission_readiness_accepts_operational_queue_sidecar(tmp_path: Path) -> None:
    payload = _run(
        tmp_path,
        pending=0,
        overdue=0,
        submission_updates={
            "queues": {
                "external_benchmark_submission_work_items": [
                    {
                        "queue_id": "tpu_hffb",
                        "submitted_at_utc": "2026-05-05T03:04:05Z",
                        "last_checked_at_utc": "2026-05-05T04:05:06Z",
                    },
                    {
                        "queue_id": "peer_spd_hinge",
                        "submission_receipt": "https://bench.example/receipts/EB-003",
                        "last_checked_at_utc": "2026-05-05T04:05:06Z",
                        "closure_evidence_path": "release_evidence/productization/EB-003.receipt.json",
                    },
                ]
            }
        },
    )

    tpu_row = next(row for row in payload["submission_queue"] if row["queue_id"] == "tpu_hffb")
    assert tpu_row["submission_lifecycle_status"] == "submitted_pending_receipt"
    assert tpu_row["receipt_status"] == "pending_external_submission_receipt"
    assert tpu_row["submission_owner_action"] == "attach_external_submission_receipt"
    assert tpu_row["status_lifecycle"]["submitted"] is True
    assert tpu_row["status_lifecycle"]["receipt_verified"] is False

    peer_row = next(row for row in payload["submission_queue"] if row["queue_id"] == "peer_spd_hinge")
    assert peer_row["receipt_url"] == "https://bench.example/receipts/EB-003"
    assert peer_row["submission_receipt_status"] == "attached"
    assert peer_row["closure_evidence_status"] == "attached"
    assert payload["summary"]["submission_receipt_pending_count"] == 3
    assert payload["summary"]["submission_receipt_attached_count"] == 1
    assert payload["summary"]["submission_last_checked_count"] == 2
    assert payload["summary"]["closure_evidence_attached_count"] == 1


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
    assert payload["summary"]["submission_queue_blocked_count"] == 4
    assert payload["summary"]["onepage_attestation_status"] == "blocked"
    assert all(row["status"] == "blocked" for row in payload["submission_queue"])
    assert all(row["submission_receipt_status"] == "blocked" for row in payload["submission_queue"])
