from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_committee_review_package import (
    _panel_zone_external_validation_surface,
    _write_html,
    _write_markdown,
    _write_csv,
)


FOUNDATION_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "foundation_realish"
PANEL_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _committee_artifacts(tmp_path: Path) -> dict:
    artifacts: dict[str, str] = {}
    for name in [
        "drift_envelope.png",
        "core_hysteresis.png",
        "hinge_proxy_3d.png",
        "authority_sac_kpi.png",
        "authority_nheri_waveform.png",
        "release_gap_smoke_history.png",
    ]:
        path = tmp_path / name
        path.write_bytes(b"")
        artifacts[path.stem if name != "release_gap_smoke_history.png" else "smoke_history_png"] = str(path)
    return {
        "drift_envelope_png": str(tmp_path / "drift_envelope.png"),
        "core_hysteresis_png": str(tmp_path / "core_hysteresis.png"),
        "hinge_proxy_3d_png": str(tmp_path / "hinge_proxy_3d.png"),
        "authority_sac_kpi_png": str(tmp_path / "authority_sac_kpi.png"),
        "authority_nheri_waveform_png": str(tmp_path / "authority_nheri_waveform.png"),
        "smoke_history_png": str(tmp_path / "release_gap_smoke_history.png"),
    }


def _run_foundation_realish_fixture(tmp_path: Path) -> dict:
    dataset_out = tmp_path / "foundation_dataset_report.json"
    npz_out = tmp_path / "foundation_dataset.npz"
    artifact_out = tmp_path / "foundation_optimization_artifact.json"
    report_out = tmp_path / "foundation_optimization_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(FOUNDATION_FIXTURE_DIR / "foundation_small_model.json"),
            "--code-check",
            str(FOUNDATION_FIXTURE_DIR / "foundation_small_code_check.json"),
            "--pbd-review",
            str(FOUNDATION_FIXTURE_DIR / "foundation_small_pbd.json"),
            "--ndtha-residual",
            str(FOUNDATION_FIXTURE_DIR / "foundation_small_ndtha.json"),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(dataset_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    dataset = _load_json(dataset_out)
    first = next(row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation")
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": str(first.get("group_id", "")),
                    "member_type": "foundation",
                    "semantic_group": str(first.get("semantic_group", "")),
                    "action_name": "mat_down",
                }
            ]
        },
    )
    _write_json(blocked, {"blocked_rows": []})

    for cmd in [
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--design-optimization-npz",
            str(npz_out),
            "--midas-model",
            str(FOUNDATION_FIXTURE_DIR / "foundation_small_model.json"),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact_out),
        ],
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--foundation-optimization-artifact",
            str(artifact_out),
            "--out",
            str(report_out),
        ],
    ]:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    return {
        "dataset": dataset,
        "report": _load_json(report_out),
    }


def _run_panel_zone_fixture(tmp_path: Path) -> dict:
    dataset = tmp_path / "panel_design_optimization_dataset_report.json"
    _write_json(dataset, _load_json(PANEL_FIXTURE_DIR / "design_optimization_dataset_report.json"))

    def _run_source(source_kind: str, source_fixture: str, out_name: str) -> Path:
        out = tmp_path / out_name
        proc = subprocess.run(
            [
                sys.executable,
                f"implementation/phase1/generate_panel_zone_{source_kind}_3d_source.py",
                "--design-optimization-dataset",
                str(dataset),
                "--source-input",
                str(PANEL_FIXTURE_DIR / source_fixture),
                "--out",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return out

    def _run_contract(source_kind: str, source_artifact: Path, out_name: str) -> Path:
        out = tmp_path / out_name
        proc = subprocess.run(
            [
                sys.executable,
                "implementation/phase1/generate_panel_zone_3d_source_contract.py",
                "--source-kind",
                source_kind,
                "--source-artifact",
                str(source_artifact),
                "--out",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return out

    joint = _run_source("joint_geometry", "joint_geometry_source.json", "panel_zone_joint_geometry_3d.json")
    anchorage = _run_source("rebar_anchorage", "rebar_anchorage_source.json", "panel_zone_rebar_anchorage_3d.json")
    clash = _run_source("clash_verification", "clash_verification_source.json", "panel_zone_clash_verification_3d.json")

    joint_contract = _run_contract("joint_geometry", joint, "panel_zone_joint_geometry_3d_contract.json")
    anchorage_contract = _run_contract("rebar_anchorage", anchorage, "panel_zone_rebar_anchorage_3d_contract.json")
    clash_contract = _run_contract("clash_verification", clash, "panel_zone_clash_verification_3d_contract.json")

    clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--panel-zone-joint-geometry-artifact",
            str(joint_contract),
            "--panel-zone-rebar-anchorage-artifact",
            str(anchorage_contract),
            "--panel-zone-clash-verification-artifact",
            str(clash_contract),
            "--out",
            str(clash_artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})
    report_out = tmp_path / "panel_zone_clash_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash_artifact),
            "--out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    return _load_json(report_out)


def test_committee_boundary_only_solver_verified_does_not_close_panel_zone_external_validation() -> None:
    surface = _panel_zone_external_validation_surface(
        {
            "panel_zone_validation_boundary": "solver_verified",
            "panel_zone_external_validation_status_label": "solver_verified",
            "panel_zone_external_validation_source_count": 3,
            "panel_zone_external_validation_validated_source_count": 3,
            "panel_zone_external_validation_exact_source_count": 3,
            "panel_zone_external_validation_fallback_source_count": 0,
            "panel_zone_external_validation_candidate_member_count": 3,
            "panel_zone_external_validation_validated_member_count": 3,
            "panel_zone_external_validation_exact_member_count": 3,
            "panel_zone_external_validation_validated_row_count_total": 9,
            "panel_zone_external_validation_exact_validated_row_count": 9,
        }
    )

    assert surface["artifact_closed"] is False
    assert surface["closure_mode"] == "open_exact_validated"
    assert surface["status_label"] == "validated_exact_gap"


def test_committee_markdown_and_html_surface_fixture_panel_and_foundation_provenance(tmp_path: Path) -> None:
    foundation = _run_foundation_realish_fixture(tmp_path)
    panel = _run_panel_zone_fixture(tmp_path)
    foundation_report = foundation["report"]
    foundation_summary = foundation_report["summary"]
    panel_summary = panel["summary"]
    irregular_gate_report = tmp_path / "irregular_structure_gate_report.json"
    irregular_top5_manifest = tmp_path / "irregular_top5_execution_manifest.json"
    irregular_top5_rows = [
        {
            "family_id": f"IRR-{idx:02d}",
            "priority": idx,
            "execution_mode": "ready_local_now" if idx <= 3 else "remote_source_hunt_needed",
            "source_record_count": 1,
            "local_ready_source_count": 1 if idx <= 3 else 0,
            "remote_candidate_source_count": 0 if idx <= 3 else 1,
            "authority_fit": "high",
            "ai_learning_fit": "high",
        }
        for idx in range(1, 6)
    ]
    _write_json(
        irregular_gate_report,
        {
            "summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
            "summary": {
                "irregular_structure_track_pass": True,
                "irregular_structure_track_summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
                "irregular_structure_family_count": 5,
                "irregular_structure_source_record_count": 5,
                "irregular_structure_local_ready_count": 3,
                "irregular_structure_remote_candidate_count": 2,
                "irregular_structure_native_roundtrip_candidate_count": 4,
                "irregular_structure_solver_benchmark_candidate_count": 3,
                "irregular_structure_ai_learning_candidate_count": 5,
                "irregular_structure_top5_count": 5,
                "top5_family_ids": [row["family_id"] for row in irregular_top5_rows],
            },
        },
    )
    _write_json(
        irregular_top5_manifest,
        {"summary": {"top5_count": 5}, "top5_families": irregular_top5_rows},
    )

    metrics = {
        "accelerated_coverage_target_pct_label": "95-99%",
        "residual_holdout_target_pct_label": "1-5%",
        "estimated_time_saved_pct_label": "90-96%",
        "measured_chain_total_minutes": 5.24,
        "estimated_time_saved_basis": "empirical_smoke_runtime_reduction x coverage target",
        "time_saving_focus": "Automate repetitive heavy-lift analysis and packaging.",
        "pbd_dynamic_hinge_refresh_ready": False,
        "pbd_hinge_state_mode": "proxy_only_hinge_visualization",
        "pbd_hinge_refresh_reason": "PBD review still publishes hinge proxy artifacts.",
        "pbd_hinge_refresh_artifact_present": True,
        "pbd_hinge_refresh_artifact_kind": "hinge_refresh_source_json",
        "pbd_hinge_refresh_source_mode": "proxy_only_dataset_heuristic",
        "pbd_hinge_refresh_overlap_member_count": 0,
        "pbd_hinge_refresh_rebar_sensitive_member_count": 0,
        "pbd_hinge_benchmark_gate_pass": True,
        "pbd_hinge_benchmark_fixture_regression_pass": True,
        "pbd_hinge_benchmark_alignment_pass": True,
        "pbd_hinge_benchmark_asset_count": 5,
        "pbd_hinge_benchmark_train_count": 2,
        "pbd_hinge_benchmark_val_count": 2,
        "pbd_hinge_benchmark_holdout_count": 1,
        "pbd_hinge_benchmark_rebar_sensitive_count": 1,
        "pbd_hinge_benchmark_confinement_sensitive_count": 1,
        "pbd_hinge_benchmark_fixture_count": 5,
        "pbd_hinge_benchmark_fixture_min_point_count": 449,
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": 0.03662513089005235,
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": 5,
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": 5,
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": 0.0127,
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": 0.0603,
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": 0.064,
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": 0.074,
        "panel_zone_3d_clash_ready": bool(panel["contract_pass"]),
        "panel_zone_constructability_mode": str(panel_summary["constructability_mode"]),
        "panel_zone_constructability_reason": str(panel["reason"]),
        "panel_zone_proxy_candidate_count": int(panel_summary["panel_zone_proxy_candidate_count"]),
        "panel_zone_source_artifact_kind": str(panel_summary["panel_zone_source_artifact_kind"]),
        "panel_zone_source_contract_mode": str(panel_summary["panel_zone_source_contract_mode"]),
        "panel_zone_internal_engine_complete": False,
        "panel_zone_external_validation_pending": False,
        "panel_zone_validation_boundary": str(
            panel_summary.get("panel_zone_validation_boundary", "solver_verified")
        ),
        "panel_zone_status_label": "release_ready",
        "panel_zone_advisory_only": False,
        "panel_zone_release_blocking": False,
        "panel_zone_external_validation_advisory_only": False,
        "panel_zone_external_validation_release_blocking": False,
        "panel_zone_external_validation_status_label": str(
            panel_summary.get("panel_zone_external_validation_status_label", "")
        ),
        "panel_zone_external_validation_artifact_closed": bool(
            panel_summary.get("panel_zone_external_validation_artifact_closed", False)
        ),
        "panel_zone_external_validation_closure_mode": str(
            panel_summary.get("panel_zone_external_validation_closure_mode", "")
        ),
        "panel_zone_external_validation_required_evidence": str(
            panel_summary.get("panel_zone_external_validation_required_evidence", "")
        ),
        "panel_zone_external_validation_summary_line": str(
            panel_summary.get("panel_zone_external_validation_summary_line", "")
        ),
        "panel_zone_external_validation_local_closure_state": str(
            panel_summary.get("panel_zone_external_validation_local_closure_state", "")
        ),
        "panel_zone_external_validation_local_closure_label": str(
            panel_summary.get("panel_zone_external_validation_local_closure_label", "")
        ),
        "panel_zone_external_validation_source_count": int(
            panel_summary.get("panel_zone_external_validation_source_count", 0)
        ),
        "panel_zone_external_validation_validated_source_count": int(
            panel_summary.get("panel_zone_external_validation_validated_source_count", 0)
        ),
        "panel_zone_external_validation_exact_source_count": int(
            panel_summary.get("panel_zone_external_validation_exact_source_count", 0)
        ),
        "panel_zone_external_validation_fallback_source_count": int(
            panel_summary.get("panel_zone_external_validation_fallback_source_count", 0)
        ),
        "panel_zone_external_validation_validated_member_count": int(
            panel_summary.get("panel_zone_external_validation_validated_member_count", 0)
        ),
        "panel_zone_external_validation_exact_member_count": int(
            panel_summary.get("panel_zone_external_validation_exact_member_count", 0)
        ),
        "panel_zone_external_validation_fallback_member_count": int(
            panel_summary.get("panel_zone_external_validation_fallback_member_count", 0)
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            panel_summary.get("panel_zone_external_validation_exact_validated_row_count", 0)
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            panel_summary.get("panel_zone_external_validation_fallback_validated_row_count", 0)
        ),
        "panel_zone_external_validation_provenance_summary_label": str(
            panel_summary.get("panel_zone_external_validation_provenance_summary_label", "")
        ),
        "panel_zone_external_validation_closing_summary_label": (
            f"{panel_summary.get('panel_zone_external_validation_summary_line', '')} | "
            f"local_closure_state={panel_summary.get('panel_zone_external_validation_local_closure_state', '')} | "
            f"local_closure_label={panel_summary.get('panel_zone_external_validation_local_closure_label', '')} | "
            "inbox=pending_raw_triplet | pending_input=True | latest_consume_present=True | "
            "latest_consume_pass=False | latest_consume_reason=ERR_HANDOFF_FAILED | next=consume_pending_input"
        ),
        "panel_zone_instruction_sidecar_present": True,
        "panel_zone_instruction_sidecar_change_count": 17,
        "panel_zone_instruction_sidecar_candidate_overlap_mode": "section_signature",
        "panel_zone_instruction_sidecar_overlap_row_count": 4,
        "panel_zone_instruction_sidecar_overlap_member_count": 11,
        "panel_zone_instruction_sidecar_overlap_group_count": 3,
        "panel_zone_instruction_sidecar_evidence_model": "direct_patch_plus_structured_sidecar",
        "panel_zone_instruction_sidecar_rebar_delivery_mode": "structured_sidecar_only",
        "panel_zone_member_mapping_sidecar_present": True,
        "panel_zone_member_mapping_sidecar_mode": "explicit_member_id_map",
        "panel_zone_member_mapping_sidecar_row_count": 1,
        "panel_zone_member_mapping_sidecar_applied_row_count": 1,
        "panel_zone_member_mapping_sidecar_unmapped_source_member_count": 0,
        "panel_zone_source_valid_row_counts": dict(panel_summary["panel_zone_source_valid_row_counts"]),
        "panel_zone_source_overlap_member_counts": dict(panel_summary["panel_zone_source_overlap_member_counts"]),
        "panel_zone_source_candidate_scan_modes": dict(panel_summary["panel_zone_source_candidate_scan_modes"]),
        "panel_zone_source_bundle_modes": dict(panel_summary.get("panel_zone_source_bundle_modes", {}) or {}),
        "panel_zone_source_upstream_verification_tiers": dict(
            panel_summary.get("panel_zone_source_upstream_verification_tiers", {}) or {}
        ),
        "panel_zone_validated_source_row_count_total": int(panel_summary["panel_zone_validated_source_row_count_total"]),
        "panel_zone_validated_source_overlap_member_count_min": int(
            panel_summary["panel_zone_validated_source_overlap_member_count_min"]
        ),
        "panel_zone_topology_capable_input": bool(panel_summary["panel_zone_topology_capable_input"]),
        "panel_zone_true_3d_clash_verified": bool(panel_summary["panel_zone_true_3d_clash_verified"]),
        "panel_zone_true_3d_anchorage_verified": bool(panel_summary["panel_zone_true_3d_anchorage_verified"]),
        "panel_zone_true_3d_bridge_complete": bool(
            panel_summary.get("panel_zone_true_3d_bridge_complete", False)
        ),
        "panel_zone_solver_verified_bridge_complete": bool(
            panel_summary.get("panel_zone_solver_verified_bridge_complete", False)
        ),
        "panel_zone_missing_required_sources": list(panel_summary["panel_zone_missing_required_sources"]),
        "panel_zone_solver_verified_inbox_status_mode": "pending_raw_triplet",
        "panel_zone_solver_verified_inbox_has_input": True,
        "panel_zone_solver_verified_pending_input": True,
        "panel_zone_solver_verified_input_mode_detected": "raw_triplet",
        "panel_zone_solver_verified_latest_consume_report_present": True,
        "panel_zone_solver_verified_latest_consume_contract_pass": False,
        "panel_zone_solver_verified_latest_consume_reason_code": "ERR_HANDOFF_FAILED",
        "panel_zone_solver_verified_source_origin_class": "fixture_sample",
        "panel_zone_solver_verified_release_refresh_source_allowed": False,
        "panel_zone_solver_verified_recommended_action": "consume_pending_input",
        "foundation_optimization_ready": bool(foundation_report["contract_pass"]),
        "foundation_optimization_mode": str(foundation_summary["optimization_mode"]),
        "foundation_optimization_reason": str(foundation_report["reason"]),
        "foundation_scope_source": str(foundation_summary["foundation_scope_source"]),
        "foundation_artifact_scan_mode": str(foundation_summary["foundation_artifact_scan_mode"]),
        "upstream_foundation_label_count": int(foundation_summary["upstream_foundation_label_count"]),
        "raw_source_foundation_label_count": int(foundation_summary["raw_source_foundation_label_count"]),
        "upstream_foundation_provenance_mode": str(foundation_summary["upstream_foundation_provenance_mode"]),
        "external_benchmark_execution_mode": "limited",
        "external_benchmark_execution_ready_task_count": 10,
        "external_benchmark_execution_blocked_task_count": 2,
        "external_benchmark_execution_review_boundary_pending_count": 2,
        "external_benchmark_submission_queue_count": 4,
        "external_benchmark_submission_queue_ready_count": 0,
        "external_benchmark_submission_queue_review_pending_count": 4,
        "external_benchmark_submission_queue_blocked_count": 0,
        "external_benchmark_submission_onepage_attestation_status": "draft_ready_final_review_pending",
        "external_benchmark_execution_review_boundary_resolution_label": "approve_all=PASS_START_NOW_FULL/ready_full=yes; reject_one=ERR_ARCHITECTURE_BLOCKERS/open_revision=1",
        "external_benchmark_execution_review_boundary_owner_label": "licensed_engineer=2",
        "external_benchmark_execution_review_boundary_assignee_label": "unassigned=2",
        "external_benchmark_execution_review_boundary_assignment_status_label": "unassigned=2",
        "external_benchmark_execution_review_boundary_priority_label": "high=1, medium=1",
        "external_benchmark_execution_review_boundary_family_label": "connection_detailing=1, detailing=1",
        "external_benchmark_execution_review_boundary_change_count_total": 11,
        "external_benchmark_execution_review_boundary_followup_action_label": "wait_for_review=2",
        "external_benchmark_execution_review_boundary_sla_state_label": "within_sla=2",
        "external_benchmark_execution_review_boundary_age_bucket_label": "lt_24h=2",
        "external_benchmark_execution_review_boundary_overdue_count": 0,
        "external_benchmark_execution_review_boundary_oldest_open_age_hours": 5.5,
        "external_benchmark_execution_status_mode": "planned_only",
        "external_benchmark_execution_executable_task_count": 10,
        "external_benchmark_execution_planned_task_count": 10,
        "external_benchmark_execution_in_progress_task_count": 0,
        "external_benchmark_execution_completed_task_count": 0,
        "external_benchmark_execution_failed_task_count": 0,
        "external_benchmark_execution_finished_task_count": 0,
        "external_benchmark_execution_completion_ratio": 0.0,
        "audit_review_decision_batch_template_item_count": 2,
        "audit_review_decision_batch_template_current_status_label": "pending_review=2",
        "audit_review_decision_batch_template_review_owner_label": "licensed_engineer=2",
        "audit_review_decision_batch_template_review_priority_label": "high=1, medium=1",
        "audit_review_decision_batch_attested_example_count": 2,
        "audit_review_decision_batch_attested_example_preview_label": "approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS",
        "external_benchmark_submission_preview_approve_all_reason_code": "PASS_START_NOW_FULL",
        "external_benchmark_submission_preview_approve_all_ready_full": True,
        "external_benchmark_submission_preview_approve_all_pending_count": 0,
        "external_benchmark_submission_preview_approve_all_open_revision_count": 0,
        "external_benchmark_submission_preview_reject_one_reason_code": "ERR_ARCHITECTURE_BLOCKERS",
        "external_benchmark_submission_preview_reject_one_ready_full": False,
        "external_benchmark_submission_preview_reject_one_pending_count": 0,
        "external_benchmark_submission_preview_reject_one_open_revision_count": 1,
        "external_benchmark_submission_preview_reject_one_blocker_label": "audit_review_resolution_has_open_revisions",
        "audit_review_decision_batch_runner_reason_code": "PASS",
        "audit_review_decision_batch_runner_apply_live": False,
        "audit_review_decision_batch_runner_live_applied": False,
        "audit_review_decision_batch_runner_preview_reason_code": "PASS_START_NOW_FULL",
        "audit_review_decision_batch_runner_preview_ready_full": True,
        "audit_review_decision_batch_runner_preview_pending_count": 0,
        "audit_review_decision_batch_runner_preview_open_revision_count": 0,
        "audit_review_decision_batch_runner_live_preview_reason_code": "PASS_START_NOW_FULL",
        "midas_kds_geometry_bridge_summary_line": "MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0",
        "midas_kds_geometry_bridge_load_crosswalk_summary_line": "load_crosswalk=12/12 PASS",
        "midas_kds_geometry_bridge_load_crosswalk_count": 12,
        "midas_kds_geometry_bridge_load_crosswalk_expected": 12,
        "midas_kds_geometry_bridge_load_crosswalk_status": "PASS",
        "midas_kds_geometry_bridge_load_crosswalk_pass": True,
        "midas_kds_geometry_bridge_semantic_crosswalk_summary_line": "semantic_crosswalk=12/12 PASS",
        "midas_kds_geometry_bridge_semantic_crosswalk_count": 12,
        "midas_kds_geometry_bridge_semantic_crosswalk_expected": 12,
        "midas_kds_geometry_bridge_semantic_crosswalk_status": "PASS",
        "midas_kds_geometry_bridge_semantic_crosswalk_pass": True,
        "midas_kds_geometry_bridge_full_member_crosswalk_summary_line": "full_member_crosswalk=242/242 PASS",
        "midas_kds_geometry_bridge_full_member_crosswalk_count": 242,
        "midas_kds_geometry_bridge_full_member_crosswalk_expected": 242,
        "midas_kds_geometry_bridge_full_member_crosswalk_status": "PASS",
        "midas_kds_geometry_bridge_full_member_crosswalk_pass": True,
        "midas_kds_geometry_bridge_full_section_crosswalk_summary_line": "full_section_crosswalk=200/200 PASS",
        "midas_kds_geometry_bridge_full_section_crosswalk_count": 200,
        "midas_kds_geometry_bridge_full_section_crosswalk_expected": 200,
        "midas_kds_geometry_bridge_full_section_crosswalk_status": "PASS",
        "midas_kds_geometry_bridge_full_section_crosswalk_pass": True,
        "midas_kds_geometry_bridge_full_load_crosswalk_summary_line": "full_load_crosswalk=51/51 PASS",
        "midas_kds_geometry_bridge_full_load_crosswalk_count": 51,
        "midas_kds_geometry_bridge_full_load_crosswalk_expected": 51,
        "midas_kds_geometry_bridge_full_load_crosswalk_status": "PASS",
        "midas_kds_geometry_bridge_full_load_crosswalk_pass": True,
        "midas_kds_geometry_bridge_full_crosswalk_depth": 12,
        "element_material_breadth_summary_line": "Element/material breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=2,cases=14) | panel_cyclic=yes(sections=2,pinch=0.18,crush=1.00) | contact=full_structural_contact | support=15(contact=6,foundation=4,device=5) | materials=2(rc_composite,steel_elastic_plastic) | links=6(bearing_bilinear,compression_only_penalty,coulomb_friction,kelvin_voigt_pounding,normal_gap_unilateral,uplift_seat_unilateral) | capabilities=12(contact_bearing_friction_impact,contact_gap_uplift_unilateral,dissipative_device_response,foundation_soil_link_nonlinear,interface_transfer_finite,rc_bond_slip,rc_cracking,rc_creep_shrinkage,shell_surface_transfer,slab_wall_interaction,soil_boundary_nonlinear,wall_compression_damage) | groups=4(rc=5,shell_interface=2,foundation_soil=2,device_contact=3)",
        "support_search_summary_line": "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21 | support_families=2 | proxy_families=2",
        "general_fe_contact_matrix_summary_line": "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21",
        "support_search_count": 9,
        "surface_interaction_benchmark_summary_line": "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=4,shell-wall=4,footing-soil=4",
        "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
        "commercial_scope_summary_line": "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%",
        "commercial_reliability_breadth_summary_line": "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | evidence_rows=1 | evidence_present=True",
        "midas_kds_row_provenance_exact_row_coverage_label": "144/144",
        "midas_kds_row_provenance_preview_rows_present": True,
        "midas_kds_row_provenance_preview_row_count": 1,
        "ndtha_step_series_depth": 2400,
        "korean_source_ingest_summary_line": (
            "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | "
            "seed=4 | topo=1 | native=1 | p0=3"
        ),
        "korean_structural_preview_queue_summary_line": "KR preview queue: PASS | cand=4 | pend=1 | state=open",
        "midas_kds_row_provenance_preview_rows": [
            {
                "combination_name": "ULS1",
                "member_id": "C-TST-003",
                "clause_label": "KDS-MOMENT-Y-001",
                "baseline_focus_member_id": "502101",
                "bridge_row_provenance_mode_label": "exact row-level provenance",
                "clause_provenance_summary_label": "rows=1 | members=1 | rules=1 | hazards=1",
                "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=502101 | member_types=column",
            }
        ],
        "midas_kds_row_provenance_hazard_filter_rows": [
            {
                "hazard_type": "gravity",
                "row_count": 24,
                "member_count": 4,
                "clause_count": 1,
                "combination_count": 3,
                "top_clause_label": "KDS-MOMENT-Y-001",
                "top_dcr_label": "1.216",
            }
        ],
        "midas_kds_row_provenance_rule_family_filter_rows": [
            {
                "rule_family": "moment",
                "row_count": 24,
                "member_count": 4,
                "hazard_count": 1,
                "combination_count": 3,
                "top_clause_label": "KDS-MOMENT-Y-001",
                "top_dcr_label": "1.216",
            }
        ],
        "irregular_structure_summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
        "irregular_structure_top5_family_ids": [row["family_id"] for row in irregular_top5_rows],
        "irregular_structure_track_pass": True,
        "irregular_structure_family_count": 5,
        "irregular_structure_source_record_count": 5,
        "irregular_structure_local_ready_count": 3,
        "irregular_structure_remote_candidate_count": 2,
        "irregular_structure_native_roundtrip_candidate_count": 4,
        "irregular_structure_solver_benchmark_candidate_count": 3,
        "irregular_structure_ai_learning_candidate_count": 5,
        "irregular_structure_top5_count": 5,
    }
    artifacts = _committee_artifacts(tmp_path)
    artifacts.update(
        {
            "irregular_structure_gate_report": str(irregular_gate_report),
            "irregular_top5_execution_manifest": str(irregular_top5_manifest),
            "irregular_structure_source_catalog": "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
            "irregular_priority_manifest": "implementation/phase1/open_data/irregular/priority_irregular_structure_families.json",
            "irregular_structure_collection_report": "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
            "irregular_structure_triage_report": "implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
        }
    )

    cards = [
        {
            "label": "Coverage Model",
            "value": "engineer_in_the_loop_accelerated_coverage",
            "status": "INFO",
            "note": "95-99%",
        }
    ]
    rows = [
        {
            "section": "release",
            "item": "coverage",
            "criterion": "accelerated coverage path",
            "value": "PASS",
            "status": "PASS",
            "evidence": "release_gap_report.json",
        }
    ]
    holdout_buckets = [
        {
            "id": "licensed_engineer_review_required",
            "label": "Licensed Engineer Review",
            "owner": "기술사",
            "work_item_id": "RH-001",
            "due_date": "assignment_plus_3_business_days",
            "sla_label": "72h",
            "closure_evidence_required": "signed_engineer_review_packet",
            "closure_evidence_status": "pending",
            "queue_status": "pending_review",
            "status": "open",
            "relative_share_pct": 50,
            "absolute_project_pct_range": [0.5, 2.5],
            "scope": "final judgment",
        },
        {
            "id": "legacy_tool_cross_validation_required",
            "label": "Legacy Tool Cross-Validation",
            "owner": "기존툴+기술사",
            "work_item_id": "RH-002",
            "due_date": "assignment_plus_5_business_days",
            "sla_label": "120h",
            "closure_evidence_required": "legacy_tool_cross_validation_packet",
            "closure_evidence_status": "pending",
            "queue_status": "pending_cross_validation",
            "status": "open",
            "relative_share_pct": 30,
            "absolute_project_pct_range": [0.3, 1.5],
            "scope": "cross-check",
        },
        {
            "id": "legal_authority_signoff_required",
            "label": "Legal Sign-Off",
            "owner": "기술사/기존 승인 workflow",
            "work_item_id": "RH-003",
            "due_date": "assignment_plus_7_business_days",
            "sla_label": "168h",
            "closure_evidence_required": "authority_signoff_packet",
            "closure_evidence_status": "pending",
            "queue_status": "pending_signoff",
            "status": "open",
            "relative_share_pct": 20,
            "absolute_project_pct_range": [0.2, 1.0],
            "scope": "formal sign-off",
        },
    ]
    holdout_detail_rows = [
        {
            "bucket_label": "Licensed Engineer Review",
            "work_item_id": "RH-001",
            "detail_axis": "review_story_zone",
            "detail_value": "S02/perimeter",
            "owner": "기술사",
            "due_date": "assignment_plus_3_business_days",
            "sla_label": "72h",
            "closure_evidence_required": "signed_engineer_review_packet",
            "closure_evidence_status": "pending",
            "status": "open",
            "why": "Top story-zone review pockets remain under engineer review.",
        },
        {
            "bucket_label": "Legacy Tool Cross-Validation",
            "work_item_id": "RH-002",
            "detail_axis": "submodel_family",
            "detail_value": "SCBF16B_shell_beam_mix",
            "owner": "기존툴+기술사",
            "due_date": "assignment_plus_5_business_days",
            "sla_label": "120h",
            "closure_evidence_required": "legacy_tool_cross_validation_packet",
            "closure_evidence_status": "pending",
            "status": "open",
            "why": "Authority submodel families remain outside the accelerated envelope.",
        },
        {
            "bucket_label": "Legal Sign-Off",
            "work_item_id": "RH-003",
            "detail_axis": "authority_catalog_track",
            "detail_value": "sac (1)",
            "owner": "기술사/기존 승인 workflow",
            "due_date": "assignment_plus_7_business_days",
            "sla_label": "168h",
            "closure_evidence_required": "authority_signoff_packet",
            "closure_evidence_status": "pending",
            "status": "open",
            "why": "Formal authority-facing responsibility stays outside automated scope.",
        },
    ]
    md = tmp_path / "committee_review_report.md"
    html = tmp_path / "committee_review_report.html"
    _write_markdown(
        md,
        cards,
        rows,
        artifacts,
        metrics,
        [],
        [],
        [],
        [],
        {},
        [],
        [],
        [],
        [],
        [],
        holdout_buckets,
        holdout_detail_rows,
        [],
        {"baseline_seeded": False, "change_count": 0, "added_count": 0, "removed_count": 0, "unchanged_count": 0, "diff_rows": []},
    )
    _write_html(
        html,
        cards,
        rows,
        artifacts,
        metrics,
        [],
        [],
        [],
        {},
        [],
        [],
        [],
        [],
        [],
        holdout_buckets,
        holdout_detail_rows,
        [],
        {"baseline_seeded": False, "change_count": 0, "added_count": 0, "removed_count": 0, "unchanged_count": 0, "diff_rows": []},
    )

    markdown = md.read_text(encoding="utf-8")
    html_text = html.read_text(encoding="utf-8")
    assert "panel_zone_3d_clash_ready" in markdown
    assert "pbd_hinge_refresh_artifact_present" in markdown
    assert "pbd_hinge_refresh_overlap_member_count" in markdown
    assert "pbd_hinge_benchmark_gate_pass" in markdown
    assert "pbd_hinge_benchmark_fixture_regression_pass" in markdown
    assert "pbd_hinge_benchmark_alignment_pass" in markdown
    assert "pbd_hinge_benchmark_asset_count" in markdown
    assert "pbd_hinge_benchmark_fixture_count" in markdown
    assert "train=2, val=2, holdout=1" in markdown
    assert "panel_zone_3d_clash_and_anchorage_verified" in markdown
    assert "panel_zone_external_validation_advisory_only" in markdown
    assert "panel_zone_external_validation_release_blocking" in markdown
    assert "panel_zone_external_validation_status_label" in markdown
    assert "`panel_zone_external_validation_status_label`: `verified`" in markdown
    assert "panel_zone_external_validation_artifact_closed" in markdown
    assert "`panel_zone_external_validation_artifact_closed`: `True`" in markdown
    assert "panel_zone_external_validation_closure_mode" in markdown
    assert "`panel_zone_external_validation_closure_mode`: `closed_exact_validated`" in markdown
    assert "panel_zone_external_validation_required_evidence" in markdown
    assert "`panel_zone_external_validation_required_evidence`: `none`" in markdown
    assert "panel_zone_external_validation_provenance_summary_label" in markdown
    assert "panel_zone_external_validation_closing_summary_label" in markdown
    assert "panel_zone_external_validation_local_closure_state" in markdown
    assert "`panel_zone_external_validation_local_closure_state`: `closed_with_solver_verified_artifact`" in markdown
    assert "panel_zone_status_label" in markdown
    assert "`panel_zone_status_label`: `release_ready`" in markdown
    assert "panel_zone_advisory_only" in markdown
    assert "`panel_zone_advisory_only`: `False`" in markdown
    assert "panel_zone_release_blocking" in markdown
    assert "`panel_zone_release_blocking`: `False`" in markdown
    assert "panel_zone_instruction_sidecar_candidate_overlap_mode" in markdown
    assert "section_signature" in markdown
    assert "panel_zone_instruction_sidecar_evidence_model" in markdown
    assert "direct_patch_plus_structured_sidecar" in markdown
    assert "panel_zone_member_mapping_sidecar_present" in markdown
    assert "`panel_zone_member_mapping_sidecar_mode`: `explicit_member_id_map`" in markdown
    assert "panel_zone_validated_source_row_count_total" in markdown
    assert "panel_zone_validated_source_overlap_member_count_min" in markdown
    assert "panel_zone_solver_verified_inbox_status_mode" in markdown
    assert "panel_zone_solver_verified_source_origin_class" in markdown
    assert "panel_zone_solver_verified_release_refresh_source_allowed" in markdown
    assert "consume_pending_input" in markdown
    assert "foundation_optimization_ready" in markdown
    assert "active_foundation_member_optimization" in markdown
    assert "foundation_scope_source" in markdown
    assert "dataset_summary" in markdown
    assert "raw_source_foundation_label_count" in markdown
    assert "`3`" in markdown
    assert "external_benchmark_execution_mode" in markdown
    assert "external_benchmark_execution_status_mode" in markdown
    assert "completion_ratio=0.000" in markdown
    assert "`limited`" in markdown
    assert "audit_review_decision_batch_template" in markdown
    assert "pending_review=2" in markdown
    assert "attested_examples=2" in markdown
    assert "approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS" in markdown
    assert "external_benchmark_submission_preview_approve_all" in markdown
    assert "PASS_START_NOW_FULL" in markdown
    assert "external_benchmark_submission_preview_reject_one" in markdown
    assert "audit_review_resolution_has_open_revisions" in markdown
    assert "audit_review_decision_batch_runner" in markdown
    assert "reason=PASS" in markdown
    assert "surface_interaction_benchmark" in markdown
    assert "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3" in markdown
    assert "`midas_kds_geometry_bridge_summary_line`: `MIDAS kds-geometry-bridge: ok | mapped_review_ids=0/12 | rows=1056 | strategies=unmapped:12 | source=kds_codecheck_bridge_metadata | registry=none 0/0`" in markdown
    assert "`midas_kds_geometry_bridge_full_member_crosswalk_summary_line`: `full_member_crosswalk=242/242 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_section_crosswalk_summary_line`: `full_section_crosswalk=200/200 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_load_crosswalk_summary_line`: `full_load_crosswalk=51/51 PASS`" in markdown
    assert "`midas_kds_geometry_bridge_full_crosswalk_depth`: `12`" in markdown
    assert "`element_material_breadth_summary_line`: `Element/material breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=2,cases=14) | panel_cyclic=yes(sections=2,pinch=0.18,crush=1.00) | contact=full_structural_contact" in markdown
    assert (
        "`support_search_summary_line`: `Support search: PASS | support_search=9 | node_surface_proxy=5 | "
        "support_depth=21 | support_families=2 | proxy_families=2`"
    ) in markdown
    assert (
        "`general_fe_contact_matrix_summary_line`: `General FE contact matrix: PASS | ready=10/10 | direct=6/6 | "
        "foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | "
        "support_search=9 | node_surface_proxy=5 | support_depth=21`"
    ) in markdown
    assert (
        "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | "
        "full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%"
    ) in markdown
    assert "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | evidence_rows=1 | evidence_present=True" in markdown
    assert "| Work Item | Category | Due Date | SLA | Closure Evidence | Owner | Queue Status | Status | Relative Share | Absolute Project % | Scope |" in markdown
    assert "| Category | Work Item | Axis | Detail | Owner | Queue Status | Status | SLA | Due | Closure Evidence | Why |" in markdown
    assert "RH-001" in markdown
    assert "pending_review" in markdown
    assert "midas_kds_row_provenance_exact_row_coverage_label" in markdown
    assert "`ndtha_step_series_depth`: `2400`" in markdown
    assert "constitutive_interaction_families" in markdown
    assert "material and steel/composite constitutive gates are surfaced explicitly" in markdown
    assert "Appendix: Irregular Structure Track" in markdown
    assert "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3" in markdown
    assert "irregular_top5_execution_manifest.json" in markdown
    assert "IRR-01" in markdown
    assert "Appendix: MIDAS KDS Row Provenance Export" in markdown
    assert "row-provenance sync" in markdown
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in markdown
    assert "viewer_row_url" in markdown
    assert "viewer_slice_url" in markdown
    assert "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144" in markdown
    assert "KR ingest" in markdown
    assert "seed=4 | topo=1 | native=1 | p0=3" in markdown
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in markdown
    assert "Panel-zone 3D clash and anchorage" in html_text
    assert "External benchmark execution mode" in html_text
    assert "ready=10 | blocked=2 | review_boundary_pending=2" in html_text
    assert "External benchmark execution status" in html_text
    assert "planned=10 | in_progress=0 | completed=0 | failed=0 | finished=0 | completion_ratio=0.000" in html_text
    assert "PBD response source" in html_text
    assert "fallback_used=False | coverage=0" in html_text
    assert "Audit review decision batch template" in html_text
    assert "items=2 | status=pending_review=2 | owner=licensed_engineer=2 | priority=high=1, medium=1 | attested_examples=2 | example_preview=approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS" in html_text
    assert "Approve-all readiness preview" in html_text
    assert "reason=PASS_START_NOW_FULL | ready_full=True | pending=0 | open_revision=0" in html_text
    assert "Reject-one readiness preview" in html_text
    assert "reason=ERR_ARCHITECTURE_BLOCKERS | ready_full=False | pending=0 | open_revision=1 | blocker=audit_review_resolution_has_open_revisions" in html_text
    assert "Audit review decision batch runner" in html_text
    assert "reason=PASS | apply_live=False | live_applied=False | preview_reason=PASS_START_NOW_FULL | preview_ready_full=True | preview_pending=0 | preview_open_revision=0" in html_text
    assert "Surface interaction benchmark" in html_text
    assert "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=35/35 | source_families=3/3" in html_text
    assert "Element/material breadth" in html_text
    assert "Element/material breadth: PASS | shell=yes(elems=5,cases=31) | wall=yes(rows=2,cases=14) | panel_cyclic=yes(sections=2,pinch=0.18,crush=1.00) | contact=full_structural_contact" in html_text
    assert "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21" in html_text
    assert "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21" in html_text
    assert (
        "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | "
        "full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%"
    ) in html_text
    assert "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | evidence_rows=1 | evidence_present=True" in html_text
    assert "<th>Work Item</th>" in html_text
    assert "RH-001" in html_text
    assert "pending_review" in html_text
    assert "MIDAS KDS geometry full-crosswalk depth" in html_text
    assert "12 (min(load/semantic crosswalk))" in html_text
    assert "NDTHA step-series depth" in html_text
    assert "2400 (max completed steps)" in html_text
    assert "Constitutive/interaction families" in html_text
    assert "material and steel/composite constitutive gates are surfaced explicitly" in html_text
    assert "Appendix: Irregular Structure Track" in html_text
    assert "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3" in html_text
    assert "irregular_top5_execution_manifest.json" in html_text
    assert "IRR-01" in html_text
    assert "Appendix: MIDAS KDS Row Provenance Export" in html_text
    assert "row-provenance sync" in html_text
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in html_text
    assert "viewer_row_url" in html_text
    assert "viewer_slice_url" in html_text
    assert "KDS-MOMENT-Y-001" in html_text
    assert "KR ingest" in html_text
    assert "KR preview queue" in html_text
    assert (
        "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | "
        "seed=4 | topo=1 | native=1 | p0=3"
    ) in html_text
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in html_text
    assert "PBD hinge evidence" in html_text
    assert "PBD hinge benchmark" in html_text
    assert "assets=5" in html_text
    assert "alignment=True" in html_text
    assert "refresh-columns=5" in html_text
    assert "artifact=True" in html_text
    assert "Panel-zone source coverage" in html_text
    assert "validated_sources=3/3 | exact_sources=3/3 | fallback_sources=0/3" in html_text
    assert "latest_consume_reason=ERR_HANDOFF_FAILED" in html_text
    assert "panel_zone_3d_clash_and_anchorage_verified" in html_text
    assert "artifact_closed=True" in html_text
    assert "closure_mode=closed_exact_validated" in html_text
    assert "advisory_only=False" in html_text
    assert "release_blocking=False" in html_text
    assert "status=verified" in html_text
    assert "required_evidence=none" in html_text
    assert "local_closeout=closed_with_solver_verified_artifact" in html_text
    assert "Panel-zone source coverage" in html_text
    assert "origin=fixture_sample" in html_text
    assert "validated rows=3" in html_text
    assert "min overlap=1" in html_text
    assert "Panel-zone sidecar overlap" in html_text
    assert "section_signature" in html_text
    assert "direct_patch_plus_structured_sidecar" in html_text
    assert "structured_sidecar_only" in html_text
    assert "Panel-zone solver inbox" in html_text
    assert "pending_raw_triplet" in html_text
    assert "consume_pending_input" in html_text
    assert "Foundation / mat / pile optimization" in html_text
    assert "Foundation scope provenance" in html_text
    assert "dataset_summary" in html_text
    assert "upstream labels=5 | raw labels=3 | dataset_scope_only" in html_text


def test_committee_csv_surfaces_fixture_panel_and_foundation_provenance(tmp_path: Path) -> None:
    foundation = _run_foundation_realish_fixture(tmp_path)
    panel = _run_panel_zone_fixture(tmp_path)
    foundation_report = foundation["report"]
    foundation_summary = foundation_report["summary"]
    panel_summary = panel["summary"]
    cards = [
        {"label": "Coverage Model", "value": "engineer_in_the_loop_accelerated_coverage", "status": "INFO", "note": "95-99%"}
    ]
    rows = [
        {
            "section": "release",
            "item": "coverage",
            "criterion": "fixture-derived committee coverage",
            "value": "PASS",
            "status": "PASS",
            "evidence": "release_gap_report.json",
        }
    ]
    metrics = {
        "pbd_dynamic_hinge_refresh_ready": False,
        "pbd_hinge_state_mode": "proxy_only_hinge_visualization",
        "pbd_hinge_refresh_reason": "fixture does not attach hinge refresh rows",
        "pbd_hinge_refresh_artifact_present": True,
        "pbd_hinge_refresh_artifact_kind": "hinge_refresh_source_json",
        "pbd_hinge_refresh_source_mode": "proxy_only_dataset_heuristic",
        "pbd_hinge_refresh_overlap_member_count": 0,
        "pbd_hinge_refresh_rebar_sensitive_member_count": 0,
        "pbd_hinge_benchmark_gate_pass": True,
        "pbd_hinge_benchmark_fixture_regression_pass": True,
        "pbd_hinge_benchmark_alignment_pass": True,
        "pbd_hinge_benchmark_asset_count": 5,
        "pbd_hinge_benchmark_train_count": 2,
        "pbd_hinge_benchmark_val_count": 2,
        "pbd_hinge_benchmark_holdout_count": 1,
        "pbd_hinge_benchmark_rebar_sensitive_count": 1,
        "pbd_hinge_benchmark_confinement_sensitive_count": 1,
        "pbd_hinge_benchmark_fixture_count": 5,
        "pbd_hinge_benchmark_fixture_min_point_count": 449,
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": 0.03662513089005235,
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": 5,
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": 5,
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": 0.0127,
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": 0.0603,
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": 0.064,
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": 0.074,
        "panel_zone_3d_clash_ready": bool(panel["contract_pass"]),
        "panel_zone_constructability_mode": str(panel_summary["constructability_mode"]),
        "panel_zone_constructability_reason": str(panel["reason"]),
        "panel_zone_proxy_candidate_count": int(panel_summary["panel_zone_proxy_candidate_count"]),
        "panel_zone_source_artifact_kind": str(panel_summary["panel_zone_source_artifact_kind"]),
        "panel_zone_source_contract_mode": str(panel_summary["panel_zone_source_contract_mode"]),
        "panel_zone_internal_engine_complete": False,
        "panel_zone_external_validation_pending": False,
        "panel_zone_validation_boundary": str(
            panel_summary.get("panel_zone_validation_boundary", "solver_verified")
        ),
        "panel_zone_status_label": "release_ready",
        "panel_zone_advisory_only": False,
        "panel_zone_release_blocking": False,
        "panel_zone_external_validation_advisory_only": False,
        "panel_zone_external_validation_release_blocking": False,
        "panel_zone_external_validation_status_label": str(
            panel_summary.get("panel_zone_external_validation_status_label", "")
        ),
        "panel_zone_external_validation_artifact_closed": bool(
            panel_summary.get("panel_zone_external_validation_artifact_closed", False)
        ),
        "panel_zone_external_validation_closure_mode": str(
            panel_summary.get("panel_zone_external_validation_closure_mode", "")
        ),
        "panel_zone_external_validation_required_evidence": str(
            panel_summary.get("panel_zone_external_validation_required_evidence", "")
        ),
        "panel_zone_external_validation_summary_line": str(
            panel_summary.get("panel_zone_external_validation_summary_line", "")
        ),
        "panel_zone_external_validation_local_closure_state": str(
            panel_summary.get("panel_zone_external_validation_local_closure_state", "")
        ),
        "panel_zone_external_validation_local_closure_label": str(
            panel_summary.get("panel_zone_external_validation_local_closure_label", "")
        ),
        "panel_zone_external_validation_source_count": int(
            panel_summary.get("panel_zone_external_validation_source_count", 0)
        ),
        "panel_zone_external_validation_validated_source_count": int(
            panel_summary.get("panel_zone_external_validation_validated_source_count", 0)
        ),
        "panel_zone_external_validation_exact_source_count": int(
            panel_summary.get("panel_zone_external_validation_exact_source_count", 0)
        ),
        "panel_zone_external_validation_fallback_source_count": int(
            panel_summary.get("panel_zone_external_validation_fallback_source_count", 0)
        ),
        "panel_zone_external_validation_validated_member_count": int(
            panel_summary.get("panel_zone_external_validation_validated_member_count", 0)
        ),
        "panel_zone_external_validation_exact_member_count": int(
            panel_summary.get("panel_zone_external_validation_exact_member_count", 0)
        ),
        "panel_zone_external_validation_fallback_member_count": int(
            panel_summary.get("panel_zone_external_validation_fallback_member_count", 0)
        ),
        "panel_zone_external_validation_exact_validated_row_count": int(
            panel_summary.get("panel_zone_external_validation_exact_validated_row_count", 0)
        ),
        "panel_zone_external_validation_fallback_validated_row_count": int(
            panel_summary.get("panel_zone_external_validation_fallback_validated_row_count", 0)
        ),
        "panel_zone_external_validation_provenance_summary_label": str(
            panel_summary.get("panel_zone_external_validation_provenance_summary_label", "")
        ),
        "panel_zone_external_validation_closing_summary_label": (
            f"{panel_summary.get('panel_zone_external_validation_summary_line', '')} | "
            f"local_closure_state={panel_summary.get('panel_zone_external_validation_local_closure_state', '')} | "
            f"local_closure_label={panel_summary.get('panel_zone_external_validation_local_closure_label', '')} | "
            "inbox=pending_raw_triplet | pending_input=True | latest_consume_present=True | "
            "latest_consume_pass=False | latest_consume_reason=ERR_HANDOFF_FAILED | next=consume_pending_input"
        ),
        "panel_zone_instruction_sidecar_present": True,
        "panel_zone_instruction_sidecar_change_count": 17,
        "panel_zone_instruction_sidecar_candidate_overlap_mode": "section_signature",
        "panel_zone_instruction_sidecar_overlap_row_count": 4,
        "panel_zone_instruction_sidecar_overlap_member_count": 11,
        "panel_zone_instruction_sidecar_overlap_group_count": 3,
        "panel_zone_instruction_sidecar_evidence_model": "direct_patch_plus_structured_sidecar",
        "panel_zone_instruction_sidecar_rebar_delivery_mode": "structured_sidecar_only",
        "panel_zone_member_mapping_sidecar_present": True,
        "panel_zone_member_mapping_sidecar_mode": "explicit_member_id_map",
        "panel_zone_member_mapping_sidecar_row_count": 1,
        "panel_zone_member_mapping_sidecar_applied_row_count": 1,
        "panel_zone_member_mapping_sidecar_unmapped_source_member_count": 0,
        "panel_zone_source_valid_row_counts": dict(panel_summary["panel_zone_source_valid_row_counts"]),
        "panel_zone_source_overlap_member_counts": dict(panel_summary["panel_zone_source_overlap_member_counts"]),
        "panel_zone_source_candidate_scan_modes": dict(panel_summary["panel_zone_source_candidate_scan_modes"]),
        "panel_zone_source_bundle_modes": dict(panel_summary.get("panel_zone_source_bundle_modes", {}) or {}),
        "panel_zone_source_upstream_verification_tiers": dict(
            panel_summary.get("panel_zone_source_upstream_verification_tiers", {}) or {}
        ),
        "panel_zone_validated_source_row_count_total": int(panel_summary["panel_zone_validated_source_row_count_total"]),
        "panel_zone_validated_source_overlap_member_count_min": int(
            panel_summary["panel_zone_validated_source_overlap_member_count_min"]
        ),
        "panel_zone_topology_capable_input": bool(panel_summary["panel_zone_topology_capable_input"]),
        "panel_zone_true_3d_clash_verified": bool(panel_summary["panel_zone_true_3d_clash_verified"]),
        "panel_zone_true_3d_anchorage_verified": bool(panel_summary["panel_zone_true_3d_anchorage_verified"]),
        "panel_zone_true_3d_bridge_complete": bool(
            panel_summary.get("panel_zone_true_3d_bridge_complete", False)
        ),
        "panel_zone_solver_verified_bridge_complete": bool(
            panel_summary.get("panel_zone_solver_verified_bridge_complete", False)
        ),
        "panel_zone_missing_required_sources": list(panel_summary["panel_zone_missing_required_sources"]),
        "panel_zone_solver_verified_inbox_status_mode": "pending_raw_triplet",
        "panel_zone_solver_verified_inbox_has_input": True,
        "panel_zone_solver_verified_pending_input": True,
        "panel_zone_solver_verified_input_mode_detected": "raw_triplet",
        "panel_zone_solver_verified_latest_consume_report_present": True,
        "panel_zone_solver_verified_latest_consume_contract_pass": False,
        "panel_zone_solver_verified_latest_consume_reason_code": "ERR_HANDOFF_FAILED",
        "panel_zone_solver_verified_source_origin_class": "fixture_sample",
        "panel_zone_solver_verified_release_refresh_source_allowed": False,
        "panel_zone_solver_verified_recommended_action": "consume_pending_input",
        "foundation_optimization_ready": bool(foundation_report["contract_pass"]),
        "foundation_optimization_mode": str(foundation_summary["optimization_mode"]),
        "foundation_optimization_reason": str(foundation_report["reason"]),
        "foundation_scope_source": str(foundation_summary["foundation_scope_source"]),
        "foundation_artifact_scan_mode": str(foundation_summary["foundation_artifact_scan_mode"]),
        "upstream_foundation_label_count": int(foundation_summary["upstream_foundation_label_count"]),
        "raw_source_foundation_label_count": int(foundation_summary["raw_source_foundation_label_count"]),
        "upstream_foundation_provenance_mode": str(foundation_summary["upstream_foundation_provenance_mode"]),
        "external_benchmark_execution_mode": "limited",
        "external_benchmark_execution_ready_task_count": 10,
        "external_benchmark_execution_blocked_task_count": 2,
        "external_benchmark_execution_review_boundary_pending_count": 2,
        "external_benchmark_execution_status_mode": "planned_only",
        "external_benchmark_execution_executable_task_count": 10,
        "external_benchmark_execution_planned_task_count": 10,
        "external_benchmark_execution_in_progress_task_count": 0,
        "external_benchmark_execution_completed_task_count": 0,
        "external_benchmark_execution_failed_task_count": 0,
        "external_benchmark_execution_finished_task_count": 0,
        "external_benchmark_execution_completion_ratio": 0.0,
        "audit_review_decision_batch_template_item_count": 2,
        "audit_review_decision_batch_template_current_status_label": "pending_review=2",
        "audit_review_decision_batch_template_review_owner_label": "licensed_engineer=2",
        "audit_review_decision_batch_template_review_priority_label": "high=1, medium=1",
        "audit_review_decision_batch_attested_example_count": 2,
        "audit_review_decision_batch_attested_example_preview_label": "approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS",
        "external_benchmark_submission_preview_approve_all_reason_code": "PASS_START_NOW_FULL",
        "external_benchmark_submission_preview_approve_all_ready_full": True,
        "external_benchmark_submission_preview_approve_all_pending_count": 0,
        "external_benchmark_submission_preview_approve_all_open_revision_count": 0,
        "external_benchmark_submission_preview_reject_one_reason_code": "ERR_ARCHITECTURE_BLOCKERS",
        "external_benchmark_submission_preview_reject_one_ready_full": False,
        "external_benchmark_submission_preview_reject_one_pending_count": 0,
        "external_benchmark_submission_preview_reject_one_open_revision_count": 1,
        "external_benchmark_submission_preview_reject_one_blocker_label": "audit_review_resolution_has_open_revisions",
        "audit_review_decision_batch_runner_reason_code": "PASS",
        "audit_review_decision_batch_runner_apply_live": False,
        "audit_review_decision_batch_runner_live_applied": False,
        "audit_review_decision_batch_runner_preview_reason_code": "PASS_START_NOW_FULL",
        "audit_review_decision_batch_runner_preview_ready_full": True,
        "audit_review_decision_batch_runner_preview_pending_count": 0,
        "audit_review_decision_batch_runner_preview_open_revision_count": 0,
        "audit_review_decision_batch_runner_live_preview_reason_code": "PASS_START_NOW_FULL",
        "wind_tunnel_raw_mapping_ready": False,
        "wind_tunnel_mapping_mode": "semantic_pressure_binding_only",
        "wind_tunnel_mapping_reason": "fixture does not attach a wind raw mapping artifact",
    }
    csv_path = tmp_path / "committee_review_report.csv"
    _write_csv(csv_path, cards, rows, metrics, [], [], [], [], [])
    text = csv_path.read_text(encoding="utf-8")
    assert "Coverage Model" in text
    assert "advanced_holdout_provenance,pbd_hinge_refresh_ready,False,FAIL" in text
    assert "artifact_present=True | overlap=0 | rebar_sensitive=0" in text
    assert "advanced_holdout_provenance,pbd_hinge_benchmark_gate,True,PASS" in text
    assert "assets=5 | split=train:2/val:2/holdout:1 | rebar_sensitive=1 | confinement_sensitive=1" in text
    assert "advanced_holdout_provenance,pbd_hinge_benchmark_fixture_regression,True,PASS" in text
    assert "fixtures=5 | min_point_count=449" in text
    assert "advanced_holdout_provenance,pbd_hinge_benchmark_alignment,True,PASS" in text
    assert "refresh_columns=5 | rebar_sensitive_columns=5" in text
    assert "advanced_holdout_provenance,panel_zone_3d_clash_ready,True,PASS" in text
    assert "advanced_holdout_provenance,panel_zone_external_validation_status_label,verified,INFO" in text
    assert "artifact_closed=True | closure_mode=closed_exact_validated | advisory_only=False | release_blocking=False | boundary=solver_verified | pending=False" in text
    assert "advanced_holdout_provenance,panel_zone_external_validation_local_closure_state,closed_with_solver_verified_artifact,INFO" in text
    assert "required_evidence=none" in text
    assert "advanced_holdout_provenance,panel_zone_external_validation_provenance_summary_label," in text
    assert "validated_source_ratio=" in text
    assert "advanced_holdout_provenance,panel_zone_external_validation_closing_summary_label," in text
    assert "advanced_holdout_provenance,panel_zone_status_label,release_ready,INFO" in text
    assert "advanced_holdout_provenance,panel_zone_source_contract_mode,true_3d_clash_and_anchorage_verified,INFO" in text
    assert "validated_rows=3" in text
    assert "min_overlap=1" in text
    assert "advanced_holdout_provenance,panel_zone_instruction_sidecar_candidate_overlap_mode,section_signature,INFO" in text
    assert "overlap_members=11" in text
    assert "evidence=direct_patch_plus_structured_sidecar" in text
    assert "mapping_present=True" in text
    assert "mapping_mode=explicit_member_id_map" in text
    assert "advanced_holdout_provenance,panel_zone_source_bundle_modes," in text
    assert "advanced_holdout_provenance,panel_zone_solver_verified_inbox_status_mode,pending_raw_triplet,INFO" in text
    assert "origin=fixture_sample" in text
    assert "latest_consume_reason=ERR_HANDOFF_FAILED" in text
    assert "advanced_holdout_provenance,foundation_optimization_ready,True,PASS" in text
    assert "advanced_holdout_provenance,foundation_scope_source,dataset_summary,INFO" in text
    assert "raw_source_labels=3" in text
    assert "advanced_holdout_provenance,external_benchmark_execution_mode,limited,PASS" in text
    assert "ready=10 | blocked=2 | review_boundary_pending=2" in text
    assert "advanced_holdout_provenance,external_benchmark_execution_review_boundary" in text
    assert "advanced_holdout_provenance,external_benchmark_execution_status_mode,planned_only,PASS" in text
    assert "planned=10 | in_progress=0 | completed=0 | failed=0 | finished=0 | completion_ratio=0.000" in text
    assert "advanced_holdout_provenance,audit_review_decision_batch_template,2,PASS" in text
    assert "status=pending_review=2 | owner=licensed_engineer=2 | priority=high=1, medium=1 | attested_examples=2 | example_preview=approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS" in text
    assert "advanced_holdout_provenance,external_benchmark_submission_preview_approve_all,PASS_START_NOW_FULL,PASS" in text
    assert "ready_full=True | pending=0 | open_revision=0" in text
    assert "advanced_holdout_provenance,external_benchmark_submission_preview_reject_one,ERR_ARCHITECTURE_BLOCKERS,FAIL" in text
    assert "ready_full=False | pending=0 | open_revision=1 | blocker=audit_review_resolution_has_open_revisions" in text
    assert "advanced_holdout_provenance,audit_review_decision_batch_runner,PASS,PASS" in text
    assert "apply_live=False | live_applied=False | preview_reason=PASS_START_NOW_FULL | preview_ready_full=True | preview_pending=0 | preview_open_revision=0" in text
    assert "advanced_holdout_provenance,wind_tunnel_raw_mapping_ready,False,FAIL" in text
    assert "advanced_holdout_provenance,irregular_structure_track," in text
    assert "families=0 | sources=0 | local_ready=0 | remote_candidates=0 | top5=0 | top5_family_ids=n/a | gate=n/a | manifest=n/a" in text


def test_committee_markdown_and_html_include_row_provenance_appendix(tmp_path: Path) -> None:
    report_md = tmp_path / "committee_review_report.md"
    report_html = tmp_path / "committee_review_report.html"
    irregular_gate_report = tmp_path / "irregular_structure_gate_report.json"
    irregular_top5_manifest = tmp_path / "irregular_top5_execution_manifest.json"
    irregular_top5_rows = [
        {
            "family_id": f"IRR-{idx:02d}",
            "priority": idx,
            "execution_mode": "ready_local_now" if idx <= 3 else "remote_source_hunt_needed",
            "source_record_count": 1,
            "local_ready_source_count": 1 if idx <= 3 else 0,
            "remote_candidate_source_count": 0 if idx <= 3 else 1,
            "authority_fit": "high",
            "ai_learning_fit": "high",
        }
        for idx in range(1, 6)
    ]
    _write_json(
        irregular_gate_report,
        {
            "summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
            "summary": {
                "irregular_structure_track_pass": True,
                "irregular_structure_track_summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
                "irregular_structure_top5_family_ids": [row["family_id"] for row in irregular_top5_rows],
            },
        },
    )
    _write_json(
        irregular_top5_manifest,
        {"summary": {"top5_count": 5}, "top5_families": irregular_top5_rows},
    )
    artifacts = {
        **_committee_artifacts(tmp_path),
        "midas_kds_row_provenance_export_json": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json",
        "midas_kds_row_provenance_export_csv": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
        "midas_kds_row_provenance_export_report": "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
        "irregular_structure_gate_report": str(irregular_gate_report),
        "irregular_top5_execution_manifest": str(irregular_top5_manifest),
        "irregular_structure_source_catalog": "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
        "irregular_priority_manifest": "implementation/phase1/open_data/irregular/priority_irregular_structure_families.json",
        "irregular_structure_collection_report": "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
        "irregular_structure_triage_report": "implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
    }
    metrics = defaultdict(
        lambda: 0,
        {
        "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
        "korean_source_ingest_summary_line": (
            "KR ingest: PASS | src=4 | cls=4 | got=0 | fp=0 | meta=4 | rej=0 | dup=0 | "
            "seed=4 | topo=1 | native=1 | p0=3"
        ),
        "korean_structural_preview_queue_summary_line": "KR preview queue: PASS | cand=4 | pend=1 | state=open",
        "midas_kds_row_provenance_preview_rows": [
            {
                "combination_name": "ULS1",
                "member_id": "C-TST-003",
                "clause_label": "KDS-MOMENT-Y-001",
                "baseline_focus_member_id": "502101",
                "bridge_row_provenance_mode_label": "exact row-level provenance",
                "clause_provenance_summary_label": "rows=24 | members=4 | rules=1 | hazards=1",
                "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=502101 | member_types=column",
            }
        ],
        "midas_kds_row_provenance_hazard_filter_rows": [
            {
                "hazard_type": "gravity",
                "row_count": 24,
                "member_count": 4,
                "clause_count": 1,
                "combination_count": 3,
                "top_clause_label": "KDS-MOMENT-Y-001",
                "top_dcr_label": "1.216",
            }
        ],
        "midas_kds_row_provenance_rule_family_filter_rows": [
            {
                "rule_family": "moment",
                "row_count": 24,
                "member_count": 4,
                "hazard_count": 1,
                "combination_count": 3,
                "top_clause_label": "KDS-MOMENT-Y-001",
                "top_dcr_label": "1.216",
            }
        ],
        "irregular_structure_summary_line": "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3 | remote_candidates=2 | native_roundtrip_candidates=4 | solver_candidates=3 | ai_candidates=5 | top5=5 | gate=irregular_structure_gate_report.json | manifest=irregular_top5_execution_manifest.json",
        "irregular_structure_top5_family_ids": [row["family_id"] for row in irregular_top5_rows],
        "irregular_structure_track_pass": True,
        "irregular_structure_family_count": 5,
        "irregular_structure_source_record_count": 5,
        "irregular_structure_local_ready_count": 3,
        "irregular_structure_remote_candidate_count": 2,
        "irregular_structure_native_roundtrip_candidate_count": 4,
        "irregular_structure_solver_benchmark_candidate_count": 3,
        "irregular_structure_ai_learning_candidate_count": 5,
        "irregular_structure_top5_count": 5,
        "irregular_structure_gate_report": str(irregular_gate_report),
        "irregular_top5_execution_manifest": str(irregular_top5_manifest),
        },
    )

    _write_markdown(
        report_md,
        [],
        [],
        artifacts,
        metrics,
        [],
        [],
        [],
        [],
        {},
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        {},
    )
    _write_html(
        report_html,
        [],
        [],
        artifacts,
        metrics,
        [],
        [],
        [],
        {},
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        {},
    )

    markdown = report_md.read_text(encoding="utf-8")
    html_text = report_html.read_text(encoding="utf-8")
    assert "## Appendix: MIDAS KDS Row Provenance Export" in markdown
    assert "## Appendix: Irregular Structure Track" in markdown
    assert "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3" in markdown
    assert "irregular_top5_execution_manifest.json" in markdown
    assert "IRR-01" in markdown
    assert "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144" in markdown
    assert "seed=4 | topo=1 | native=1 | p0=3" in markdown
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in markdown
    assert "row-provenance sync" in markdown
    assert "explicit viewer_row_url and viewer_slice_url reverse-sync links" in markdown
    assert "midas_kds_row_provenance_table.csv" in markdown
    assert "MIDAS KDS Row Provenance Export" in html_text
    assert "Appendix: Irregular Structure Track" in html_text
    assert "Irregular structure track: PASS | families=5 | sources=5 | local_ready=3" in html_text
    assert "irregular_top5_execution_manifest.json" in html_text
    assert "IRR-01" in html_text
    assert "KR ingest" in html_text
    assert "KR preview queue" in html_text
    assert "seed=4 | topo=1 | native=1 | p0=3" in html_text
    assert "KR preview queue: PASS | cand=4 | pend=1 | state=open" in html_text
    assert "KDS-MOMENT-Y-001" in html_text
    assert "exact row-level provenance" in html_text
