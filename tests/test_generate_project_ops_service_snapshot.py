from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.project_ops_api_service import build_project_ops_snapshot


SCRIPT = Path("implementation/phase1/generate_project_ops_service_snapshot.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _create_project_ops_fixture(tmp_path: Path) -> dict[str, Path]:
    release_root = tmp_path / "release"
    portfolio_root = release_root / "authoring" / "portfolio"
    sample_dir = portfolio_root / "sample_tower"
    steel_dir = portfolio_root / "steel_braced_frame"
    sample_dir.mkdir(parents=True, exist_ok=True)
    steel_dir.mkdir(parents=True, exist_ok=True)

    sample_registry = sample_dir / "native_authoring_project_registry.json"
    steel_registry = steel_dir / "native_authoring_project_registry.json"
    sample_batch = sample_dir / "native_authoring_batch_job_report.json"
    steel_batch = steel_dir / "native_authoring_batch_job_report.json"
    portfolio_json = portfolio_root / "native_authoring_ops_portfolio.json"
    registry_index_json = portfolio_root / "native_authoring_project_registry_index.json"
    portfolio_batch_json = portfolio_root / "native_authoring_ops_portfolio_batch.json"
    runtime_submission_json = portfolio_root / "native_authoring_runtime_submission_lane.json"
    runtime_writeback_depth_json = portfolio_root / "native_authoring_runtime_writeback_depth_report.json"
    multi_project_runtime_writeback_json = (
        portfolio_root / "native_authoring_multi_project_runtime_writeback_report.json"
    )
    solver_family_breadth_json = portfolio_root / "native_authoring_solver_family_breadth_report.json"
    local_runtime_scenario_depth_json = (
        portfolio_root / "native_authoring_local_runtime_scenario_depth_report.json"
    )
    release_registry_json = release_root / "release_registry.json"
    committee_summary_json = release_root / "committee_review" / "committee_summary.json"
    release_gap_report_json = release_root / "release_gap_report.json"
    latest_snapshot_json = (
        release_root / "phase3_nightly_hardening_20260419T120000Z" / "snapshot_manifest.json"
    )

    _write_json(
        sample_registry,
        {
            "generated_at": "2026-04-19T12:00:00+00:00",
            "contract_pass": True,
            "summary": {
                "project_id": "tower-a",
                "project_name": "Tower A",
                "project_family_id": "sample_tower",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "baseline",
                "approval_count": 2,
                "approved_count": 2,
                "pending_count": 0,
                "audit_event_count": 3,
                "artifact_count": 4,
                "package_sha256": "sha-tower-a",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
        },
    )
    _write_json(
        steel_registry,
        {
            "generated_at": "2026-04-19T12:10:00+00:00",
            "contract_pass": True,
            "summary": {
                "project_id": "frame-b",
                "project_name": "Frame B",
                "project_family_id": "steel_braced_frame",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "steel-alt",
                "approval_count": 1,
                "approved_count": 1,
                "pending_count": 0,
                "audit_event_count": 2,
                "artifact_count": 3,
                "package_sha256": "sha-frame-b",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
        },
    )
    _write_json(
        sample_batch,
        {
            "contract_pass": True,
            "summary": {
                "job_count": 3,
                "snapshot_count": 3,
                "completed_count": 3,
                "failed_count": 0,
                "planned_count": 0,
                "blocked_count": 0,
                "rerun_requested_count": 0,
            },
        },
    )
    _write_json(
        steel_batch,
        {
            "contract_pass": True,
            "summary": {
                "job_count": 2,
                "snapshot_count": 1,
                "completed_count": 2,
                "failed_count": 0,
                "planned_count": 0,
                "blocked_count": 0,
                "rerun_requested_count": 0,
            },
        },
    )
    _write_json(
        portfolio_json,
        {
            "generated_at": "2026-04-19T12:20:00+00:00",
            "contract_pass": True,
            "summary": {
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "family_count": 2,
                "complete_family_count": 2,
                "ready_family_count": 1,
                "family_track_count": 2,
                "runtime_ready_family_count": 1,
                "writeback_ready_family_count": 1,
                "full_lane_ready_family_count": 1,
                "narrowing_family_count": 1,
                "solver_combo_count": 24,
                "batch_snapshot_count": 4,
                "registry_project_count": 2,
                "registry_signature_verified_count": 2,
                "registry_reproducible_count": 2,
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "family_label": "Sample Tower",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "draft_label": "baseline",
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "commercialization_status": "ready",
                    "commercialization_score": 88,
                    "story_count": 5,
                    "member_count": 35,
                    "load_pattern_count": 4,
                    "solver_combo_count": 13,
                    "solver_mesh_request_count": 2,
                    "job_count": 3,
                    "snapshot_count": 3,
                    "workspace_ready": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "ops_ready": True,
                    "batch_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "summary_line": "Native authoring ops bundle: PASS | family=sample_tower",
                    "artifacts": {
                        "batch_job_report_json": str(sample_batch),
                        "project_registry_json": str(sample_registry),
                    },
                },
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "draft_label": "steel-alt",
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "commercialization_status": "narrowing",
                    "commercialization_score": 70,
                    "story_count": 7,
                    "member_count": 42,
                    "load_pattern_count": 6,
                    "solver_combo_count": 11,
                    "solver_mesh_request_count": 3,
                    "job_count": 2,
                    "snapshot_count": 1,
                    "workspace_ready": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "ops_ready": True,
                    "batch_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "summary_line": "Native authoring ops bundle: PASS | family=steel_braced_frame",
                    "artifacts": {
                        "batch_job_report_json": str(steel_batch),
                        "project_registry_json": str(steel_registry),
                    },
                },
            ],
            "artifacts": {
                "native_authoring_ops_portfolio_json": str(portfolio_json),
                "native_authoring_project_registry_index_json": str(registry_index_json),
                "native_authoring_ops_portfolio_batch_json": str(portfolio_batch_json),
            },
            "summary_line": "Native authoring ops portfolio: PASS | families=2 | ready=1",
        },
    )
    _write_json(
        registry_index_json,
        {
            "generated_at": "2026-04-19T12:21:00+00:00",
            "contract_pass": True,
            "summary": {
                "project_count": 2,
                "family_count": 2,
                "portfolio_count": 1,
                "signature_verified_count": 2,
                "package_reproducible_count": 2,
            },
            "project_rows": [
                {
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "registry_count": 1,
                    "all_contract_pass": True,
                    "any_contract_pass": True,
                    "latest_generated_at": "2026-04-19T12:00:00+00:00",
                    "latest_path": str(sample_registry),
                    "latest_reason_code": "PASS",
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 2,
                    "latest_approved_count": 2,
                    "latest_pending_count": 0,
                    "latest_audit_event_count": 3,
                    "latest_artifact_count": 4,
                    "latest_package_sha256": "sha-tower-a",
                    "latest_family_id": "sample_tower",
                    "latest_portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "latest_draft_label": "baseline",
                    "registry_paths": [str(sample_registry)],
                },
                {
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "registry_count": 1,
                    "all_contract_pass": True,
                    "any_contract_pass": True,
                    "latest_generated_at": "2026-04-19T12:10:00+00:00",
                    "latest_path": str(steel_registry),
                    "latest_reason_code": "PASS",
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 1,
                    "latest_approved_count": 1,
                    "latest_pending_count": 0,
                    "latest_audit_event_count": 2,
                    "latest_artifact_count": 3,
                    "latest_package_sha256": "sha-frame-b",
                    "latest_family_id": "steel_braced_frame",
                    "latest_portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "latest_draft_label": "steel-alt",
                    "registry_paths": [str(steel_registry)],
                },
            ],
            "family_rows": [
                {
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "family_id": "sample_tower",
                    "draft_labels": ["baseline"],
                    "project_ids": ["tower-a"],
                    "registry_count": 1,
                    "complete_registry_count": 1,
                    "signature_verified_count": 1,
                    "package_reproducible_count": 1,
                    "latest_generated_at": "2026-04-19T12:00:00+00:00",
                    "latest_path": str(sample_registry),
                    "latest_project_id": "tower-a",
                    "latest_project_name": "Tower A",
                },
                {
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "family_id": "steel_braced_frame",
                    "draft_labels": ["steel-alt"],
                    "project_ids": ["frame-b"],
                    "registry_count": 1,
                    "complete_registry_count": 1,
                    "signature_verified_count": 1,
                    "package_reproducible_count": 1,
                    "latest_generated_at": "2026-04-19T12:10:00+00:00",
                    "latest_path": str(steel_registry),
                    "latest_project_id": "frame-b",
                    "latest_project_name": "Frame B",
                },
            ],
            "rows": [],
        },
    )
    _write_json(
        portfolio_batch_json,
        {
            "contract_pass": True,
            "summary": {
                "job_count": 5,
                "snapshot_count": 4,
                "completed_count": 5,
                "failed_count": 0,
                "planned_count": 0,
                "blocked_count": 0,
                "rerun_requested_count": 0,
            },
        },
    )
    _write_json(
        runtime_submission_json,
        {
            "contract_pass": True,
            "summary": {
                "runtime_submission_ready": False,
                "submission_count": 2,
                "submission_ready_count": 1,
                "runtime_ready_count": 1,
                "ready_submission_count": 1,
                "writeback_ready_count": 1,
                "full_ready_count": 1,
                "queue_count": 1,
            },
            "submission_rows": [
                {
                    "submission_id": "tower-a-runtime-001",
                    "family_id": "sample_tower",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "submission_status": "released",
                    "runtime_ready": True,
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "contract_pass": True,
                    "submitted_at": "2026-04-19T12:22:00+00:00",
                },
                {
                    "submission_id": "frame-b-runtime-001",
                    "family_id": "steel_braced_frame",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "submission_status": "queued",
                    "runtime_ready": False,
                    "writeback_ready": False,
                    "registry_ready": True,
                    "signature_verified": True,
                    "contract_pass": False,
                    "submitted_at": "2026-04-19T12:23:00+00:00",
                },
            ],
            "artifacts": {
                "native_authoring_runtime_submission_lane_json": str(runtime_submission_json),
            },
            "summary_line": "Native authoring runtime submission lane: CHECK | submissions=2 | ready=1 | writeback_ready=1 | queue=1",
        },
    )
    _write_json(
        runtime_writeback_depth_json,
        {
            "contract_pass": True,
            "summary": {
                "runtime_writeback_depth_ready": True,
                "family_count": 2,
                "depth_ready_family_count": 2,
                "targeted_family_count": 0,
                "signature_verified_family_count": 2,
                "package_reproducible_family_count": 2,
                "snapshot_ready_family_count": 2,
                "queue_clear_family_count": 2,
                "family_status_label": "sample_tower:full, steel_braced_frame:full",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "runtime_writeback_depth_status": "full",
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
                {
                    "family_id": "steel_braced_frame",
                    "runtime_writeback_depth_status": "full",
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
            ],
            "artifacts": {
                "native_authoring_runtime_writeback_depth_report_json": str(runtime_writeback_depth_json),
            },
            "summary_line": "Native authoring runtime writeback depth: PASS | families=2 | full_depth=2 | targeted=0 | registry=2 | signature=2 | repro=2 | snapshot=2 | queue_clear=2",
        },
    )
    _write_json(
        multi_project_runtime_writeback_json,
        {
            "contract_pass": True,
            "summary": {
                "multi_project_runtime_writeback_ready": True,
                "project_count": 2,
                "family_count": 2,
                "project_family_count": 2,
                "full_depth_project_family_count": 2,
                "targeted_project_family_count": 0,
                "ready_project_count": 2,
                "signature_verified_project_count": 2,
                "package_reproducible_project_count": 2,
                "snapshot_ready_project_count": 2,
                "queue_clear_project_count": 2,
                "project_status_label": "tower-a:ready, frame-b:ready",
            },
            "project_rows": [
                {
                    "project_id": "tower-a",
                    "project_name": "Tower A",
                    "project_ready": True,
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
                {
                    "project_id": "frame-b",
                    "project_name": "Frame B",
                    "project_ready": True,
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                },
            ],
            "project_family_rows": [
                {
                    "project_id": "tower-a",
                    "family_id": "sample_tower",
                    "runtime_writeback_depth_status": "full",
                    "full_depth_ready": True,
                },
                {
                    "project_id": "frame-b",
                    "family_id": "steel_braced_frame",
                    "runtime_writeback_depth_status": "full",
                    "full_depth_ready": True,
                },
            ],
            "artifacts": {
                "native_authoring_multi_project_runtime_writeback_report_json": str(
                    multi_project_runtime_writeback_json
                ),
            },
            "summary_line": "Native authoring multi-project runtime/writeback: PASS | projects=2 | families=2 | project_families=2 | full_depth=2 | ready_projects=2 | signature=2 | repro=2 | snapshot=2 | queue_clear=2",
        },
    )
    _write_json(
        solver_family_breadth_json,
        {
            "contract_pass": True,
            "summary": {
                "solver_family_breadth_ready": True,
                "family_count": 2,
                "broad_ready_family_count": 2,
                "full_breadth_family_count": 1,
                "mesh_broad_family_count": 1,
                "member_multi_family_count": 2,
                "family_status_label": "sample_tower:broad, steel_braced_frame:broad",
            },
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "solver_family_breadth_status": "broad",
                    "broad_solver_family_ready": True,
                    "full_solver_family_ready": True,
                    "member_family_breadth_ready": True,
                    "mesh_breadth_status": "broad",
                },
                {
                    "family_id": "steel_braced_frame",
                    "solver_family_breadth_status": "broad",
                    "broad_solver_family_ready": True,
                    "full_solver_family_ready": False,
                    "member_family_breadth_ready": True,
                    "mesh_breadth_status": "narrow",
                },
            ],
            "artifacts": {
                "native_authoring_solver_family_breadth_report_json": str(solver_family_breadth_json),
            },
            "summary_line": "Native authoring solver family breadth: PASS | families=2 | broad_ready=2 | full_breadth=1 | solver_ready=2 | combo_broad=2 | mesh_coverage=2 | mesh_broad=1 | member_multi=2 | queue=0",
        },
    )
    _write_json(
        local_runtime_scenario_depth_json,
        {
            "contract_pass": True,
            "summary": {
                "local_runtime_scenario_depth_ready": True,
                "family_count": 2,
                "depth_ready_family_count": 2,
                "trace_ready_family_count": 2,
                "mesh_trace_ready_family_count": 2,
                "runtime_ready_family_count": 2,
                "omitted_library_family_count": 0,
                "family_status_label": "sample_tower:deep, steel_braced_frame:deep",
            },
            "family_rows": [
                {"family_id": "sample_tower", "local_runtime_scenario_depth_status": "deep", "runtime_ready": True, "trace_ready": True, "mesh_trace_ready": True, "omitted_library_combination_count": 0},
                {"family_id": "steel_braced_frame", "local_runtime_scenario_depth_status": "deep", "runtime_ready": True, "trace_ready": True, "mesh_trace_ready": True, "omitted_library_combination_count": 0},
            ],
            "artifacts": {
                "native_authoring_local_runtime_scenario_depth_report_json": str(local_runtime_scenario_depth_json),
            },
            "summary_line": "Native authoring local runtime scenario depth: PASS | families=2 | deep=2 | scenario_ready=2 | trace_ready=2 | mesh_ready=2 | runtime_ready=2 | omitted=0",
        },
    )
    _write_json(
        release_registry_json,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "artifact_count": 12,
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                "project_registry_artifact_count": 11,
                "project_registry_approval_count": 2,
                "project_registry_package_sha256": "sha-release-package",
                "project_registry_package_bytes": 123456,
                "signing_algorithm": "ed25519",
            },
            "checks": {
                "signature_verified_pass": True,
                "project_registry_signature_verified_pass": True,
            },
        },
    )
    _write_json(
        committee_summary_json,
        {
            "authority_catalog_diff_change_count": 0,
            "authority_catalog_routing_warning_active": False,
            "advanced_holdout_open_count": 1,
            "advanced_holdout_total_count": 4,
            "metrics": {
                "authority_catalog_diff_change_count": 0,
                "authority_catalog_routing_warning_active": False,
                "advanced_holdout_open_count": 1,
                "advanced_holdout_total_count": 4,
            },
        },
    )
    _write_json(
        release_gap_report_json,
        {
            "summary": {
                "release_candidate_pass": True,
                "commercial_grade": "Commercial",
                "deployment_model": "engineer_in_the_loop_accelerated_coverage",
            }
        },
    )
    _write_json(
        latest_snapshot_json,
        {
            "snapshot": "phase3_nightly_hardening_20260419T120000Z",
            "generated_at": "2026-04-19T12:30:00+00:00",
            "release_policy": {
                "policy_pass": True,
            },
            "files": [
                {"file": "release/release_registry.json", "present": True, "optional": False},
                {"file": "release/release_gap_report.json", "present": True, "optional": False},
            ],
            "optional_files": [
                {"file": "release/committee_review/committee_summary.json", "present": True, "optional": True}
            ],
        },
    )
    return {
        "release_root": release_root,
        "portfolio_batch_json": portfolio_batch_json,
    }


def test_build_project_ops_snapshot_falls_back_to_family_batch_reports(tmp_path: Path) -> None:
    fixture = _create_project_ops_fixture(tmp_path)
    fixture["portfolio_batch_json"].unlink()

    payload = build_project_ops_snapshot(
        release_root=fixture["release_root"],
        generated_at="2026-04-19T13:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["batch_job_count"] == 5
    assert payload["summary"]["batch_snapshot_count"] == 4
    assert payload["summary"]["submission_count"] == 2
    assert payload["summary"]["ready_submission_count"] == 1
    assert payload["summary"]["runtime_ready_family_count"] == 1
    assert payload["summary"]["writeback_ready_family_count"] == 1
    assert payload["summary"]["runtime_writeback_depth_ready"] is True
    assert payload["summary"]["runtime_writeback_depth_family_count"] == 2
    assert payload["summary"]["runtime_writeback_depth_full_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_ready"] is True
    assert payload["summary"]["multi_project_runtime_writeback_project_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_project_family_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_ready_project_count"] == 2
    assert payload["summary"]["solver_family_breadth_ready"] is True
    assert payload["summary"]["solver_family_breadth_family_count"] == 2
    assert payload["summary"]["solver_family_breadth_broad_ready_count"] == 2
    assert payload["summary"]["local_runtime_scenario_depth_ready"] is True
    assert payload["summary"]["local_runtime_scenario_depth_family_count"] == 2
    assert payload["summary"]["local_runtime_scenario_depth_ready_count"] == 2
    assert payload["summary"]["full_ready_family_count"] == 1
    assert payload["summary"]["ready_family_label"] == "1/2 ready families"
    assert payload["summary"]["runtime_ready_family_label"] == "1/2 runtime-ready families"
    assert payload["summary"]["queued_submission_count"] == 1
    assert payload["summary"]["family_runtime_writeback_alignment_pass"] is True
    assert payload["summary"]["family_runtime_writeback_alignment_count"] == 1
    assert payload["summary"]["family_runtime_writeback_alignment_label"] == "PASS 1/1 ready families aligned"
    assert "runtime_ready_families=1" in payload["summary"]["family_runtime_writeback_alignment_evidence"]
    assert payload["batch"]["primary_summary"]["completed_count"] == 5
    assert payload["runtime_submissions"]["summary"]["queue_count"] == 1
    assert payload["runtime_submissions"]["summary"]["runtime_ready_count"] == 1
    assert payload["runtime_submissions"]["summary"]["full_ready_count"] == 1
    assert payload["artifacts"]["portfolio_batch_json"] == ""
    assert payload["artifacts"]["runtime_submission_json"].endswith("native_authoring_runtime_submission_lane.json")
    assert payload["artifacts"]["native_authoring_runtime_writeback_depth_report_json"].endswith(
        "native_authoring_runtime_writeback_depth_report.json"
    )
    assert payload["artifacts"]["native_authoring_multi_project_runtime_writeback_report_json"].endswith(
        "native_authoring_multi_project_runtime_writeback_report.json"
    )
    assert payload["artifacts"]["native_authoring_solver_family_breadth_report_json"].endswith(
        "native_authoring_solver_family_breadth_report.json"
    )
    assert payload["artifacts"]["native_authoring_local_runtime_scenario_depth_report_json"].endswith(
        "native_authoring_local_runtime_scenario_depth_report.json"
    )


def test_generate_project_ops_service_snapshot_cli_writes_release_summary(tmp_path: Path) -> None:
    fixture = _create_project_ops_fixture(tmp_path)
    out = fixture["release_root"] / "project_ops_service_snapshot.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--release-root",
            str(fixture["release_root"]),
            "--out",
            str(out),
            "--generated-at",
            "2026-04-19T13:15:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["batch_job_count"] == 5
    assert payload["summary"]["submission_count"] == 2
    assert payload["summary"]["ready_submission_count"] == 1
    assert payload["summary"]["runtime_ready_family_count"] == 1
    assert payload["summary"]["runtime_writeback_depth_ready"] is True
    assert payload["summary"]["runtime_writeback_depth_family_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_ready"] is True
    assert payload["summary"]["multi_project_runtime_writeback_project_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_project_family_count"] == 2
    assert payload["summary"]["multi_project_runtime_writeback_ready_project_count"] == 2
    assert payload["summary"]["solver_family_breadth_ready"] is True
    assert payload["summary"]["solver_family_breadth_family_count"] == 2
    assert payload["summary"]["local_runtime_scenario_depth_ready"] is True
    assert payload["summary"]["local_runtime_scenario_depth_family_count"] == 2
    assert payload["summary"]["local_runtime_scenario_depth_ready_count"] == 2
    assert payload["summary"]["family_runtime_writeback_alignment_pass"] is True
    assert payload["summary"]["queued_submission_count"] == 1
    assert payload["artifacts"]["project_ops_service_snapshot_json"] == str(out)
    assert payload["artifacts"]["runtime_submission_json"].endswith("native_authoring_runtime_submission_lane.json")
    assert payload["artifacts"]["native_authoring_runtime_writeback_depth_report_json"].endswith(
        "native_authoring_runtime_writeback_depth_report.json"
    )
    assert payload["artifacts"]["native_authoring_multi_project_runtime_writeback_report_json"].endswith(
        "native_authoring_multi_project_runtime_writeback_report.json"
    )
    assert payload["artifacts"]["native_authoring_solver_family_breadth_report_json"].endswith(
        "native_authoring_solver_family_breadth_report.json"
    )
    assert payload["artifacts"]["native_authoring_local_runtime_scenario_depth_report_json"].endswith(
        "native_authoring_local_runtime_scenario_depth_report.json"
    )
    assert payload["release_governance"]["release_registry"]["signing_algorithm"] == "ed25519"
    assert payload["release_governance"]["latest_release_snapshot"]["release_policy_pass"] is True
    assert payload["projects"][0]["project_id"] == "tower-a"
    assert payload["submissions"][0]["family_id"] == "sample_tower"
    assert payload["runtime_submissions"]["summary"]["writeback_ready_count"] == 1
    assert payload["runtime_submissions"]["summary"]["full_ready_count"] == 1
    assert "Project ops service snapshot: PASS" in proc.stdout
