from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_external_benchmark_kickoff_package_limited_start(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    wind_registry = tmp_path / "wind_registry.json"
    tpu_gate = tmp_path / "tpu_gate.json"
    hinge_registry = tmp_path / "hinge_registry.json"
    hinge_gate = tmp_path / "hinge_gate.json"
    hinge_fixture_reg = tmp_path / "hinge_fixture_regression.json"
    hinge_alignment = tmp_path / "hinge_alignment.json"
    audit_queue = tmp_path / "audit_queue.json"
    frame_report = tmp_path / "frame.json"
    wind_system = tmp_path / "wind_system.json"
    ssi_report = tmp_path / "ssi.json"
    out_dir = tmp_path / "out"

    _write_json(
        readiness,
        {
            "contract_pass": True,
            "reason_code": "PASS_START_NOW_LIMITED",
            "summary": {
                "recommended_start_mode": "start_now_limited_external_benchmark",
                "recommended_submission_scope": "component_and_system_performance_benchmark_with_review_boundary",
                "ready_to_start_now": True,
                "ready_to_start_full_submission_now": False,
                "caution_label": "audit_review_queue_pending=2",
                "blocker_label": "none",
                "next_actions": ["close pending audit-review packets before final external submission package"],
                "panel_zone_validation_boundary": "external_validation_only",
                "commercial_scope_summary_line": "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%",
                "commercial_reliability_breadth_summary_line": "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | evidence_rows=1 | evidence_present=True",
                "midas_kds_row_provenance_exact_row_coverage_label": "144/144",
                "submission_queue_count": 4,
                "submission_queue_ready_count": 0,
                "submission_queue_review_pending_count": 4,
                "submission_queue_blocked_count": 0,
                "onepage_attestation_status": "draft_ready_final_review_pending",
                "onepage_attestation_required_count": 4,
                "onepage_attestation_ready_count": 0,
            },
            "submission_queue": [
                {
                    "queue_id": "hardest_external_10case",
                    "submission_scope": "hardest_external_benchmark_program",
                    "owner": "benchmark_program_owner",
                    "status": "ready_for_benchmark_start_final_review_pending",
                    "onepage_attestation": "hardest external 10-case one-page attestation",
                    "onepage_attestation_status": "draft_ready_final_review_pending",
                    "dry_run_evidence": "Hardest external 10-case kickoff: PASS | cases=10 | coverage=100% | dry_run=ready",
                },
                {
                    "queue_id": "tpu_hffb",
                    "submission_scope": "component_wind_benchmark_submission",
                    "owner": "wind_benchmark_owner",
                    "status": "ready_for_benchmark_start_final_review_pending",
                    "onepage_attestation": "TPU/HFFB component benchmark one-page attestation",
                    "onepage_attestation_status": "draft_ready_final_review_pending",
                    "dry_run_evidence": "TPU/HFFB benchmark gate: PASS | assets=2 | ready=2 | raw_mapping=eligible",
                },
                {
                    "queue_id": "peer_spd_hinge",
                    "submission_scope": "component_hinge_benchmark_submission",
                    "owner": "pbd_benchmark_owner",
                    "status": "ready_for_benchmark_start_final_review_pending",
                    "onepage_attestation": "PEER/SPD hinge component one-page attestation",
                    "onepage_attestation_status": "draft_ready_final_review_pending",
                    "dry_run_evidence": (
                        "PEER/SPD hinge benchmark gate: PASS | assets=2 | ready=2 | split=train:1,holdout:1 | "
                        "PEER/SPD hinge fixture regression: PASS | fixtures=2 | min_points=449 | "
                        "PEER/SPD hinge alignment: PASS | refresh_columns=2 | rebar_sensitive_columns=0"
                    ),
                },
                {
                    "queue_id": "korean_public_structures",
                    "submission_scope": "korean_public_structure_release_review",
                    "owner": "korean_source_owner",
                    "status": "ready_for_benchmark_start_final_review_pending",
                    "onepage_attestation": "Korean public structures provenance one-page attestation",
                    "onepage_attestation_status": "draft_ready_final_review_pending",
                    "dry_run_evidence": (
                        "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | seed=4 | topo=1 | native=1 | p0=3 | "
                        "KR preview queue: PASS | cand=4 | pend=1 | state=open"
                    ),
                },
            ],
        },
    )
    _write_json(
        wind_registry,
        {
            "benchmark_ready_assets": [
                {
                    "benchmark_seed_id": "tpu_hffb_isolated_highrise_seed_01",
                    "case_role": "baseline_isolated_highrise",
                    "holdout_split": "val",
                    "signal_column_count": 200,
                    "source_manifest_path": "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json",
                    "source_origin_class": "official_external_benchmark",
                    "raw_hffb_mapping_eligible": True,
                },
                {
                    "benchmark_seed_id": "tpu_hffb_interference_highrise_seed_01",
                    "case_role": "neighbor_interference_highrise",
                    "holdout_split": "holdout",
                    "signal_column_count": 252,
                    "source_manifest_path": "implementation/phase1/open_data/wind/tpu/case_917_materialized/tpu_hffb_interference_highrise_seed_01.source_manifest.json",
                    "source_origin_class": "official_external_benchmark",
                    "raw_hffb_mapping_eligible": True,
                },
            ]
        },
    )
    _write_json(tpu_gate, {"contract_pass": True})
    _write_json(
        hinge_registry,
        {
            "rows": [
                {
                    "seed_id": "peer_spd_rc_column_rectangular_seed_01",
                    "holdout_split": "train",
                    "fixture_path": "implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_rectangular_seed_01.hinge_fixture.json",
                    "specimen_id": "121",
                    "point_count": 1169,
                    "benchmark_ready": True,
                    "rebar_sensitive_expected": False,
                    "confinement_sensitive_expected": False,
                },
                {
                    "seed_id": "peer_spd_rc_column_holdout_seed_01",
                    "holdout_split": "holdout",
                    "fixture_path": "implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_holdout_seed_01.hinge_fixture.json",
                    "specimen_id": "299",
                    "point_count": 449,
                    "benchmark_ready": True,
                    "rebar_sensitive_expected": False,
                    "confinement_sensitive_expected": False,
                },
            ]
        },
    )
    _write_json(hinge_gate, {"contract_pass": True})
    _write_json(hinge_fixture_reg, {"contract_pass": True})
    _write_json(hinge_alignment, {"contract_pass": True})
    _write_json(
        audit_queue,
        {
            "audit_review_queue_items": [
                {
                    "packet_id": "connection_detailing|connection_detailing_audit_after_material_patch|high",
                    "action_family": "connection_detailing",
                    "review_priority": "high",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "change_count": 6,
                },
                {
                    "packet_id": "detailing|detailing_audit_after_material_patch|medium",
                    "action_family": "detailing",
                    "review_priority": "medium",
                    "review_owner": "licensed_engineer",
                    "queue_status": "pending_review",
                    "change_count": 5,
                },
            ]
        },
    )
    for report in [frame_report, wind_system, ssi_report]:
        _write_json(report, {"contract_pass": True, "reason_code": "PASS", "summary": {"case_count": 2}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_kickoff_package.py",
            "--readiness-report",
            str(readiness),
            "--wind-registry",
            str(wind_registry),
            "--tpu-gate-report",
            str(tpu_gate),
            "--hinge-registry",
            str(hinge_registry),
            "--hinge-gate-report",
            str(hinge_gate),
            "--hinge-fixture-regression-report",
            str(hinge_fixture_reg),
            "--hinge-alignment-report",
            str(hinge_alignment),
            "--audit-review-queue-manifest",
            str(audit_queue),
            "--frame-report",
            str(frame_report),
            "--wind-system-report",
            str(wind_system),
            "--ssi-report",
            str(ssi_report),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    package = json.loads((out_dir / "external_benchmark_kickoff_package.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "external_benchmark_kickoff_package.md").read_text(encoding="utf-8")

    assert package["reason_code"] == "PASS_START_NOW_LIMITED"
    assert package["summary"]["recommended_start_mode"] == "start_now_limited_external_benchmark"
    assert package["summary"]["wind_component_asset_count"] == 2
    assert package["summary"]["hinge_component_asset_count"] == 2
    assert package["summary"]["pending_packet_count"] == 2
    assert package["summary"]["submission_queue_count"] == 4
    assert package["summary"]["submission_queue_review_pending_count"] == 4
    assert package["summary"]["onepage_attestation_status"] == "draft_ready_final_review_pending"
    assert package["summary"]["commercial_scope_summary_line"].startswith("Commercial scope: grade=Commercial")
    assert package["summary"]["commercial_reliability_breadth_summary_line"].startswith("Commercial reliability breadth: PASS")
    assert package["review_boundary"]["pending_packet_label"] == "connection_detailing=1, detailing=1"
    assert package["review_boundary"]["pending_packets"][0]["queue_status"] == "pending_review"
    assert package["benchmark_contracts"]["tpu_hffb_benchmark_gate_pass"] is True
    assert package["benchmark_contracts"]["peer_spd_hinge_benchmark_gate_pass"] is True
    assert package["submission_queue"][0]["queue_id"] == "hardest_external_10case"
    assert package["submission_queue"][0]["onepage_attestation_status"] == "draft_ready_final_review_pending"
    assert package["submission_queue"][0]["dry_run_evidence"].startswith("Hardest external 10-case kickoff: PASS")
    assert package["submission_queue"][1]["dry_run_evidence"] == "TPU/HFFB benchmark gate: PASS | assets=2 | ready=2 | raw_mapping=eligible"
    assert package["submission_queue"][2]["dry_run_evidence"].startswith("PEER/SPD hinge benchmark gate: PASS")
    assert package["submission_queue"][3]["dry_run_evidence"].startswith("KR ingest: PASS")
    assert "start_now_limited_external_benchmark" in markdown
    assert "component_and_system_performance_benchmark_with_review_boundary" in markdown
    assert "connection_detailing|connection_detailing_audit_after_material_patch|high" in markdown
    assert "Commercial scope" in markdown
    assert "Commercial reliability breadth" in markdown
    assert "hardest_external_10case" in markdown
    assert "onepage_attestation_status" in markdown
    assert "onepage_status=`draft_ready_final_review_pending`" in markdown
    assert "dry_run_evidence=`Hardest external 10-case kickoff: PASS" in markdown
    assert "dry_run_evidence=`KR ingest: PASS" in markdown
    assert "queue_status=pending_review" in markdown


def test_generate_external_benchmark_kickoff_package_full_start_ready_without_review_boundary_packets(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    wind_registry = tmp_path / "wind_registry.json"
    tpu_gate = tmp_path / "tpu_gate.json"
    hinge_registry = tmp_path / "hinge_registry.json"
    hinge_gate = tmp_path / "hinge_gate.json"
    hinge_fixture_reg = tmp_path / "hinge_fixture_regression.json"
    hinge_alignment = tmp_path / "hinge_alignment.json"
    audit_queue = tmp_path / "audit_queue.json"
    frame_report = tmp_path / "frame.json"
    wind_system = tmp_path / "wind_system.json"
    ssi_report = tmp_path / "ssi.json"
    out_dir = tmp_path / "out"

    _write_json(
        readiness,
        {
            "contract_pass": True,
            "reason_code": "PASS_START_NOW_FULL",
            "summary": {
                "recommended_start_mode": "start_now_full_external_benchmark",
                "recommended_submission_scope": "component_and_system_performance_benchmark_full_submission",
                "ready_to_start_now": True,
                "ready_to_start_full_submission_now": True,
                "caution_label": "none",
                "blocker_label": "none",
                "next_actions": ["open external benchmark launch window"],
                "panel_zone_validation_boundary": "external_validation_only",
                "commercial_scope_summary_line": "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%",
                "commercial_reliability_breadth_summary_line": "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | evidence_rows=1 | evidence_present=True",
                "midas_kds_row_provenance_exact_row_coverage_label": "144/144",
                "submission_queue_count": 4,
                "submission_queue_ready_count": 4,
                "submission_queue_review_pending_count": 0,
                "submission_queue_blocked_count": 0,
                "onepage_attestation_status": "ready_for_full_submission",
                "onepage_attestation_required_count": 4,
                "onepage_attestation_ready_count": 4,
            },
            "submission_queue": [
                {
                    "queue_id": "hardest_external_10case",
                    "submission_scope": "hardest_external_benchmark_program",
                    "owner": "benchmark_program_owner",
                    "status": "ready_for_full_submission",
                    "onepage_attestation": "hardest external 10-case one-page attestation",
                }
            ],
        },
    )
    _write_json(
        wind_registry,
        {
            "benchmark_ready_assets": [
                {
                    "benchmark_seed_id": "tpu_hffb_isolated_highrise_seed_01",
                    "case_role": "baseline_isolated_highrise",
                    "holdout_split": "val",
                    "signal_column_count": 200,
                    "source_manifest_path": "implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json",
                    "source_origin_class": "official_external_benchmark",
                    "raw_hffb_mapping_eligible": True,
                }
            ]
        },
    )
    _write_json(tpu_gate, {"contract_pass": True})
    _write_json(
        hinge_registry,
        {
            "rows": [
                {
                    "seed_id": "peer_spd_rc_column_rectangular_seed_01",
                    "holdout_split": "train",
                    "fixture_path": "implementation/phase1/open_data/pbd_hinge/peer_spd_rc_column_rectangular_seed_01.hinge_fixture.json",
                    "specimen_id": "121",
                    "point_count": 1169,
                    "benchmark_ready": True,
                    "rebar_sensitive_expected": False,
                    "confinement_sensitive_expected": False,
                }
            ]
        },
    )
    _write_json(hinge_gate, {"contract_pass": True})
    _write_json(hinge_fixture_reg, {"contract_pass": True})
    _write_json(hinge_alignment, {"contract_pass": True})
    _write_json(audit_queue, {"audit_review_queue_items": []})
    for report in [frame_report, wind_system, ssi_report]:
        _write_json(report, {"contract_pass": True, "reason_code": "PASS", "summary": {"case_count": 1}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_external_benchmark_kickoff_package.py",
            "--readiness-report",
            str(readiness),
            "--wind-registry",
            str(wind_registry),
            "--tpu-gate-report",
            str(tpu_gate),
            "--hinge-registry",
            str(hinge_registry),
            "--hinge-gate-report",
            str(hinge_gate),
            "--hinge-fixture-regression-report",
            str(hinge_fixture_reg),
            "--hinge-alignment-report",
            str(hinge_alignment),
            "--audit-review-queue-manifest",
            str(audit_queue),
            "--frame-report",
            str(frame_report),
            "--wind-system-report",
            str(wind_system),
            "--ssi-report",
            str(ssi_report),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    package = json.loads((out_dir / "external_benchmark_kickoff_package.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "external_benchmark_kickoff_package.md").read_text(encoding="utf-8")

    assert package["summary"]["ready_to_start_now"] is True
    assert package["summary"]["ready_to_start_full_submission_now"] is True
    assert package["summary"]["commercial_scope_summary_line"].startswith("Commercial scope: grade=Commercial")
    assert package["summary"]["pending_packet_count"] == 0
    assert package["summary"]["submission_queue_count"] == 4
    assert package["summary"]["onepage_attestation_status"] == "ready_for_full_submission"
    assert package["review_boundary"]["pending_packet_count"] == 0
    assert package["review_boundary"]["pending_packet_label"] == "none"
    assert any("start TPU raw HFFB benchmark execution" in action for action in package["next_actions"])
    assert any("start PEER hinge benchmark execution" in action for action in package["next_actions"])
    assert not any("close pending audit-review packets" in action for action in package["next_actions"])
    assert "start_now_full_external_benchmark" in markdown
    assert "component_and_system_performance_benchmark_full_submission" in markdown
    assert "Commercial scope" in markdown
    assert "Commercial reliability breadth" in markdown
    assert "ready_for_full_submission" in markdown
