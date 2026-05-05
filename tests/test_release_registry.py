from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_signed_release_registry import _mgt_export_provenance_from_gap


FIXTURE_PANEL_DIR = Path(__file__).resolve().parent / "fixtures" / "panel_zone_3d"
FIXTURE_FOUNDATION_DIR = Path(__file__).resolve().parent / "fixtures" / "foundation_realish"


def _env_without_pythonpath() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_panel_fixture_provenance(tmp_path: Path) -> dict:
    dataset_report = tmp_path / "panel_design_optimization_dataset_report.json"
    dataset_report.write_text((FIXTURE_PANEL_DIR / "design_optimization_dataset_report.json").read_text(encoding="utf-8"), encoding="utf-8")
    pbd = tmp_path / "pbd_review_package_report.json"
    _write_json(pbd, {"contract_pass": True})

    def _run_source(kind: str, fixture_name: str) -> Path:
        out = tmp_path / f"{kind}_source.json"
        proc = subprocess.run(
            [
                sys.executable,
                f"implementation/phase1/generate_panel_zone_{kind}_3d_source.py",
                "--design-optimization-dataset",
                str(dataset_report),
                "--source-input",
                str(FIXTURE_PANEL_DIR / fixture_name),
                "--out",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return out

    def _run_contract(kind: str, source_out: Path) -> Path:
        out = tmp_path / f"{kind}_contract.json"
        proc = subprocess.run(
            [
                sys.executable,
                "implementation/phase1/generate_panel_zone_3d_source_contract.py",
                "--source-kind",
                kind,
                "--source-artifact",
                str(source_out),
                "--out",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return out

    joint_source = _run_source("joint_geometry", "joint_geometry_source.json")
    anchorage_source = _run_source("rebar_anchorage", "rebar_anchorage_source.json")
    clash_source = _run_source("clash_verification", "clash_verification_source.json")
    joint_contract = _run_contract("joint_geometry", joint_source)
    anchorage_contract = _run_contract("rebar_anchorage", anchorage_source)
    clash_contract = _run_contract("clash_verification", clash_source)

    clash_artifact = tmp_path / "panel_zone_clash_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(dataset_report),
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

    clash_report = tmp_path / "panel_zone_clash_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(dataset_report),
            "--pbd-review-package",
            str(pbd),
            "--panel-zone-clash-artifact",
            str(clash_artifact),
            "--out",
            str(clash_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return _load_json(clash_report)


def test_panel_zone_clash_report_script_bootstraps_repo_root_without_pythonpath() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_env_without_pythonpath(),
    )

    assert proc.returncode == 0, proc.stderr
    assert "--panel-zone-clash-artifact" in proc.stdout


def _run_foundation_fixture_provenance(tmp_path: Path) -> dict:
    dataset_out = tmp_path / "foundation_design_optimization_dataset_report.json"
    npz_out = tmp_path / "foundation_design_optimization_dataset.npz"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(FIXTURE_FOUNDATION_DIR / "foundation_small_model.json"),
            "--code-check",
            str(FIXTURE_FOUNDATION_DIR / "foundation_small_code_check.json"),
            "--pbd-review",
            str(FIXTURE_FOUNDATION_DIR / "foundation_small_pbd.json"),
            "--ndtha-residual",
            str(FIXTURE_FOUNDATION_DIR / "foundation_small_ndtha.json"),
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
    foundation_rows = [row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert foundation_rows
    first = foundation_rows[0]
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"
    _write_json(
        changes,
        {
            "changes": [
                {
                    "group_id": str(first.get("group_id", "")),
                    "member_type": str(first.get("member_type", "")),
                    "semantic_group": str(first.get("semantic_group", "")),
                    "action_name": "mat_down",
                }
            ]
        },
    )
    _write_json(blocked, {"blocked_rows": []})

    artifact_out = tmp_path / "foundation_optimization_artifact.json"
    report_out = tmp_path / "foundation_optimization_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--design-optimization-npz",
            str(npz_out),
            "--midas-model",
            str(FIXTURE_FOUNDATION_DIR / "foundation_small_model.json"),
            "--cost-reduction-changes",
            str(changes),
            "--cost-reduction-blocked-actions",
            str(blocked),
            "--out",
            str(artifact_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    proc = subprocess.run(
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
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return _load_json(report_out)


def test_generate_signed_release_registry(tmp_path: Path) -> None:
    repro = tmp_path / "repro.json"
    lock_manifest = tmp_path / "version_lock_manifest.json"
    kds = tmp_path / "kds_summary.json"
    midas = tmp_path / "midas_conversion.json"
    solver = tmp_path / "solver_hip_e2e.json"
    committee_summary = tmp_path / "committee_summary.json"
    gap_report = tmp_path / "release_gap_report.json"
    parser_script = tmp_path / "parser.py"
    out = tmp_path / "release_registry.json"
    pub = tmp_path / "release_registry.pub.pem"
    sig = tmp_path / "release_registry.signature.b64"

    parser_script.write_text("print('parser placeholder')\n", encoding="utf-8")
    (tmp_path / "kds.pdf").write_text("pdf placeholder\n", encoding="utf-8")

    lock_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase3-version-lock-manifest",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "seed": 23,
                "replay_runs": 3,
                "input_hashes": {"input.json": "a" * 64},
                "model_hashes": {"model.bin": "b" * 64},
                "replay_digest": "c" * 64,
            }
        ),
        encoding="utf-8",
    )
    repro.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-repro",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "lock_manifest": str(lock_manifest),
                "checks": {
                    "case_count_pass": True,
                    "seed_locked": True,
                    "input_hashes_frozen": True,
                    "model_hashes_frozen": True,
                    "no_missing_model_artifacts": True,
                    "rust_backend_used_pass": True,
                    "replay_exact_match": True,
                    "lock_manifest_written": True,
                },
                "summary": {"case_count": 4, "replay_runs": 3, "seed": 23},
            }
        ),
        encoding="utf-8",
    )
    kds.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-kds",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "artifacts": {"kds_compliance_pdf": str(tmp_path / "kds.pdf")},
            }
        ),
        encoding="utf-8",
    )
    midas.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-midas",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "source_provenance": {
                    "path": "sample.mgt",
                    "sha256": "d" * 64,
                },
                "metrics": {
                    "element_rows_total": 100,
                    "element_rows_skipped": 0,
                    "unknown_row_total": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    solver.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-solver-hip",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
            }
        ),
        encoding="utf-8",
    )
    committee_summary.write_text(
        json.dumps(
            {
                "authority_catalog_diff_change_count": 2,
                "authority_catalog_routing_warning_active": True,
                "metrics": {
                    "pbd_resolved_ndtha_report": "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json",
                    "pbd_resolved_ndtha_response_npz": "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz",
                    "pbd_ndtha_response_fallback_used": True,
                    "pbd_ndtha_response_coverage_count": 7,
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
                },
            }
        ),
        encoding="utf-8",
    )
    gap_report.write_text(
        json.dumps(
            {
                "summary": {
                    "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                    "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                    "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                    "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                    "mgt_export_support_mode": "bounded_patch_subset",
                    "mgt_export_direct_patch_change_count": 7,
                    "mgt_export_direct_patch_action_family_label": "beam_section=1, slab_thickness=2, wall_thickness=5",
                    "mgt_export_instruction_sidecar_change_count": 12,
                    "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=3, detailing=4, rebar=5",
                    "mgt_export_rebar_payload_namespace_mode": "material_level_only",
                    "mgt_export_rebar_payload_material_level_namespace_present": True,
                    "mgt_export_rebar_payload_group_local_namespace_present": False,
                    "mgt_export_group_local_rebar_payload_row_count": 0,
                    "mgt_export_group_local_connection_detailing_payload_row_count": 3,
                    "mgt_export_group_local_connection_detailing_payload_available_count": 3,
                    "mgt_export_group_local_detailing_payload_row_count": 4,
                    "mgt_export_group_local_detailing_payload_available_count": 4,
                    "mgt_export_connection_detailing_payload_namespace_mode": "group_local",
                    "mgt_export_connection_detailing_payload_group_local_namespace_present": True,
                    "mgt_export_detailing_payload_namespace_mode": "group_local",
                    "mgt_export_detailing_payload_group_local_namespace_present": True,
                    "mgt_export_connection_detailing_structured_payload_mapped_change_count": 3,
                    "mgt_export_connection_detailing_direct_patch_eligible_change_count": 2,
                    "mgt_export_detailing_direct_patch_eligible_change_count": 1,
                    "mgt_export_detailing_structured_payload_mapped_change_count": 4,
                    "mgt_export_connection_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                    "mgt_export_detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
                    "mgt_export_rebar_direct_patch_eligible_change_count": 0,
                    "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=2, mixed_material_scope=4",
                    "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=5, direct_group_id=1",
                    "pbd_dynamic_hinge_refresh_ready": True,
                    "pbd_hinge_state_mode": "computed_member_local_hinge_refresh",
                    "pbd_hinge_refresh_reason": "dynamic hinge refresh attached",
                    "pbd_hinge_refresh_artifact_present": True,
                    "pbd_hinge_refresh_artifact_kind": "hinge_refresh_source_json",
                    "pbd_hinge_refresh_source_mode": "rebar_sensitive_member_local_refresh",
                    "pbd_hinge_refresh_overlap_member_count": 3,
                    "pbd_hinge_refresh_rebar_sensitive_member_count": 3,
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
                    "panel_zone_3d_clash_ready": True,
                    "panel_zone_constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
                    "panel_zone_constructability_reason": "3d panel-zone clash artifact attached",
                    "panel_zone_source_artifact_path": "implementation/phase1/panel_zone_clash_artifact.json",
                    "panel_zone_source_valid_row_counts": {"panel_zone_joint_geometry_3d": 1},
                    "panel_zone_source_overlap_member_counts": {"panel_zone_joint_geometry_3d": 1},
                    "panel_zone_source_candidate_scan_modes": {"panel_zone_joint_geometry_3d": "npz_full"},
                    "panel_zone_validated_source_row_count_total": 3,
                    "panel_zone_validated_source_overlap_member_count_min": 1,
                    "panel_zone_solver_verified_source_origin_class": "fixture_sample",
                    "panel_zone_solver_verified_release_refresh_source_allowed": False,
                    "foundation_optimization_ready": True,
                    "foundation_optimization_mode": "active_foundation_member_optimization",
                    "foundation_optimization_reason": "foundation optimization artifact attached",
                    "wind_tunnel_raw_mapping_ready": True,
                    "wind_tunnel_mapping_mode": "raw_hffb_node_pressure_mapping",
                    "wind_tunnel_mapping_reason": "raw wind tunnel mapping artifact attached",
                },
                "advanced_holdouts": [
                    {
                        "id": "pbd_dynamic_hinge_refresh",
                        "severity": "P0",
                        "title": "Dynamic plastic-hinge refresh",
                        "ready": True,
                        "mode": "computed_member_local_hinge_refresh",
                        "reason": "Dynamic hinge refresh attached.",
                        "evidence": "artifact_present=True, overlap_members=3, rebar_sensitive_members=3",
                    },
                    {
                        "id": "wind_tunnel_raw_mapping",
                        "severity": "P1",
                        "title": "Raw wind-tunnel data mapping",
                        "ready": False,
                        "mode": "semantic_pressure_binding_only",
                        "reason": "Raw wind mapping still waiting on raw traceable artifact.",
                        "evidence": "semantic_pressure_binding=True, bound_pressure_rows=7278, unbound_pressure_rows=0",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    external_readiness = tmp_path / "external_benchmark_submission_readiness.json"
    external_readiness.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "reason_code": "PASS_START_NOW_FULL",
                "summary": {
                    "submission_queue_count": 4,
                    "onepage_attestation_status": "ready_for_full_submission",
                },
                "submission_queue": [
                    {"queue_id": "hardest_external_10case", "status": "ready_for_full_submission"}
                ],
            }
        ),
        encoding="utf-8",
    )
    external_kickoff = tmp_path / "external_benchmark_kickoff_package.json"
    external_kickoff.write_text(
        json.dumps({"contract_pass": True, "reason_code": "PASS_START_NOW_FULL"}),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_signed_release_registry.py",
        "--repro-report",
        str(repro),
        "--lock-manifest",
        str(lock_manifest),
        "--kds-summary",
        str(kds),
        "--midas-conversion",
        str(midas),
        "--solver-hip-e2e",
        str(solver),
        "--committee-summary",
        str(committee_summary),
        "--gap-report",
        str(gap_report),
        "--external-benchmark-submission-readiness",
        str(external_readiness),
        "--external-benchmark-kickoff-package",
        str(external_kickoff),
        "--parser-script",
        str(parser_script),
        "--public-key-out",
        str(pub),
        "--signature-out",
        str(sig),
        "--out",
        str(out),
        "--generated-at",
        "2026-03-07T00:00:00+00:00",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["generated_at"] == "2026-03-07T00:00:00+00:00"
    assert report["registry_body"]["generated_at"] == "2026-03-07T00:00:00+00:00"
    assert report["project_registry_report"]["generated_at"] == "2026-03-07T00:00:00+00:00"
    assert report["reason_code"] == "PASS"
    assert report["checks"]["signature_verified_pass"] is True
    assert report["summary"]["signing_algorithm"] == "ed25519"
    assert report["summary"]["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert report["summary"]["measured_chain_comparable_reference_strict_design_opt_cost_smoke"] is True
    assert report["summary"]["authority_catalog_diff_change_count"] == 2
    assert report["summary"]["authority_catalog_routing_warning_active"] is True
    assert report["summary"]["external_benchmark_execution_mode"] == "limited"
    assert report["summary"]["external_benchmark_execution_ready_task_count"] == 10
    assert report["summary"]["external_benchmark_execution_blocked_task_count"] == 2
    assert report["summary"]["external_benchmark_execution_review_boundary_pending_count"] == 2
    assert report["summary"]["external_benchmark_execution_status_mode"] == "planned_only"
    assert report["summary"]["external_benchmark_execution_executable_task_count"] == 10
    assert report["summary"]["external_benchmark_execution_planned_task_count"] == 10
    assert report["summary"]["external_benchmark_execution_in_progress_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_completed_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_failed_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_finished_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_completion_ratio"] == 0.0
    assert report["summary"]["audit_review_decision_batch_template_item_count"] == 2
    assert report["summary"]["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert report["summary"]["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert report["summary"]["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert report["summary"]["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert report["summary"]["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert report["summary"]["external_benchmark_release_asset_count"] == 2
    assert report["summary"]["external_benchmark_submission_queue_count"] == 4
    assert report["summary"]["external_benchmark_onepage_attestation_status"] == "ready_for_full_submission"
    assert report["summary"]["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert report["summary"]["audit_review_decision_batch_runner_apply_live"] is False
    assert report["summary"]["audit_review_decision_batch_runner_live_applied"] is False
    assert report["summary"]["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert report["summary"]["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert report["summary"]["audit_review_decision_batch_runner_preview_pending_count"] == 0
    assert report["summary"]["audit_review_decision_batch_runner_preview_open_revision_count"] == 0
    assert report["summary"]["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert report["summary"]["mgt_export_rebar_payload_group_local_namespace_present"] is False
    assert report["summary"]["mgt_export_rebar_delivery_mode"] == "structured_sidecar_only"
    assert report["summary"]["mgt_export_delivery_boundary"] == (
        "direct_patch=beam_section=1, slab_thickness=2, wall_thickness=5 | "
        "sidecar=connection_detailing=3, detailing=4, rebar=5 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert report["summary"]["mgt_export_evidence_model"] == "direct_patch_plus_structured_sidecar"
    assert report["summary"]["mgt_export_rebar_direct_patch_ineligible_reason_label"] == "material_payload_missing=2, mixed_material_scope=4"
    assert report["summary"]["pbd_dynamic_hinge_refresh_ready"] is True
    assert report["summary"]["pbd_hinge_state_mode"] == "computed_member_local_hinge_refresh"
    assert report["summary"]["pbd_hinge_refresh_artifact_present"] is True
    assert report["summary"]["pbd_hinge_refresh_overlap_member_count"] == 3
    assert report["summary"]["pbd_hinge_refresh_rebar_sensitive_member_count"] == 3
    assert report["summary"]["pbd_hinge_benchmark_gate_pass"] is True
    assert report["summary"]["pbd_hinge_benchmark_fixture_regression_pass"] is True
    assert report["summary"]["pbd_hinge_benchmark_alignment_pass"] is True
    assert report["summary"]["pbd_hinge_benchmark_asset_count"] == 5
    assert report["summary"]["pbd_hinge_benchmark_train_count"] == 2
    assert report["summary"]["pbd_hinge_benchmark_val_count"] == 2
    assert report["summary"]["pbd_hinge_benchmark_holdout_count"] == 1
    assert report["summary"]["pbd_hinge_benchmark_rebar_sensitive_count"] == 1
    assert report["summary"]["pbd_hinge_benchmark_confinement_sensitive_count"] == 1
    assert report["summary"]["pbd_hinge_benchmark_fixture_count"] == 5
    assert report["summary"]["pbd_hinge_benchmark_fixture_min_point_count"] == 449
    assert report["summary"]["pbd_hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert report["summary"]["pbd_hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert report["summary"]["advanced_holdout_total_count"] == 2
    assert report["summary"]["advanced_holdout_closed_count"] == 1
    assert report["summary"]["advanced_holdout_open_count"] == 1
    assert report["summary"]["advanced_holdout_closure_summary_line"] == "closed=1/2 | open=1 | severities=P0:1, P1:1"
    assert report["summary"]["panel_zone_3d_clash_ready"] is True
    assert report["summary"]["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert report["summary"]["panel_zone_validated_source_row_count_total"] == 3
    assert report["summary"]["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert report["summary"]["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    assert report["summary"]["panel_zone_solver_verified_release_refresh_source_allowed"] is False
    assert report["summary"]["foundation_optimization_ready"] is True
    assert report["summary"]["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert report["summary"]["wind_tunnel_raw_mapping_ready"] is True
    assert report["summary"]["wind_tunnel_mapping_mode"] == "raw_hffb_node_pressure_mapping"
    assert report["registry_body"]["accelerated_coverage_provenance"]["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert report["registry_body"]["accelerated_coverage_provenance"]["authority_catalog_diff_change_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_mode"] == "limited"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_ready_task_count"] == 10
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_blocked_task_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_review_boundary_pending_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_status_mode"] == "planned_only"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_executable_task_count"] == 10
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_planned_task_count"] == 10
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_in_progress_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_completed_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_failed_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_finished_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_completion_ratio"] == 0.0
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_resolved_ndtha_report"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json"
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_resolved_ndtha_response_npz"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz"
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_ndtha_response_fallback_used"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_ndtha_response_coverage_count"] == 7
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_response_source_label"] == (
        "resolved_report=implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json | "
        "response_npz=implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.response.npz | "
        "fallback_used=True | coverage=7"
    )
    assert report["registry_body"]["package_provenance"]["pbd_response_source"]["resolved_ndtha_report"] == "implementation/phase1/experiments/by_test/nonlinear_ndtha_stress/latest/pbd7.json"
    assert report["registry_body"]["package_provenance"]["pbd_response_source"]["fallback_used"] is True
    assert len(report["registry_body"]["package_provenance"]["external_benchmark_release_assets"]) == 2
    assert {
        row["label"] for row in report["registry_body"]["package_provenance"]["external_benchmark_release_assets"]
    } == {"external_benchmark_submission_readiness", "external_benchmark_kickoff_package"}
    assert (
        report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_release_asset_count"]
        == 2
    )
    assert (
        report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_onepage_attestation_status"]
        == "ready_for_full_submission"
    )
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_template_item_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_apply_live"] is False
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_live_applied"] is False
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_pending_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_open_revision_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["mgt_export_rebar_payload_namespace_mode"] == "material_level_only"
    assert report["registry_body"]["accelerated_coverage_provenance"]["mgt_export_rebar_delivery_mode"] == "structured_sidecar_only"
    assert report["registry_body"]["accelerated_coverage_provenance"]["mgt_export_delivery_boundary"] == (
        "direct_patch=beam_section=1, slab_thickness=2, wall_thickness=5 | "
        "sidecar=connection_detailing=3, detailing=4, rebar=5 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_dynamic_hinge_refresh_ready"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_state_mode"] == "computed_member_local_hinge_refresh"
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_refresh_artifact_present"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_refresh_overlap_member_count"] == 3
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_refresh_rebar_sensitive_member_count"] == 3
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_gate_pass"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_fixture_regression_pass"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_alignment_pass"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_asset_count"] == 5
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_train_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_val_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_holdout_count"] == 1
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_rebar_sensitive_count"] == 1
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_confinement_sensitive_count"] == 1
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_fixture_count"] == 5
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_fixture_min_point_count"] == 449
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert report["registry_body"]["accelerated_coverage_provenance"]["pbd_hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert report["registry_body"]["accelerated_coverage_provenance"]["advanced_holdout_total_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["advanced_holdout_closed_count"] == 1
    assert report["registry_body"]["accelerated_coverage_provenance"]["advanced_holdout_open_count"] == 1
    assert report["registry_body"]["accelerated_coverage_provenance"]["advanced_holdout_closure_summary_line"] == (
        "closed=1/2 | open=1 | severities=P0:1, P1:1"
    )
    assert report["registry_body"]["accelerated_coverage_provenance"]["advanced_holdout_status_rows"] == [
        {
            "id": "pbd_dynamic_hinge_refresh",
            "title": "Dynamic plastic-hinge refresh",
            "severity": "P0",
            "closure_state": "closed",
            "ready": True,
            "mode": "computed_member_local_hinge_refresh",
            "reason_snippet": "Dynamic hinge refresh attached.",
            "evidence_snippet": "artifact_present=True, overlap_members=3, rebar_sensitive_members=3",
        },
        {
            "id": "wind_tunnel_raw_mapping",
            "title": "Raw wind-tunnel data mapping",
            "severity": "P1",
            "closure_state": "open",
            "ready": False,
            "mode": "semantic_pressure_binding_only",
            "reason_snippet": "Raw wind mapping still waiting on raw traceable artifact.",
            "evidence_snippet": "semantic_pressure_binding=True, bound_pressure_rows=7278, unbound_pressure_rows=0",
        },
    ]
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_3d_clash_ready"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_validated_source_row_count_total"] == 3
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_solver_verified_release_refresh_source_allowed"] is False
    assert report["registry_body"]["accelerated_coverage_provenance"]["foundation_optimization_ready"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert report["registry_body"]["accelerated_coverage_provenance"]["wind_tunnel_raw_mapping_ready"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["wind_tunnel_mapping_mode"] == "raw_hffb_node_pressure_mapping"
    assert report["checks"]["project_registry_package_pass"] is True
    assert report["checks"]["project_registry_signature_verified_pass"] is True
    assert report["summary"]["project_registry_artifact_count"] >= 8
    assert report["summary"]["project_registry_approval_count"] == 2
    assert Path(report["artifacts"]["project_registry_report"]).exists()
    assert Path(report["artifacts"]["project_package_zip"]).exists()
    assert Path(report["artifacts"]["project_registry_signature"]).exists()
    assert report["project_registry_report"]["contract_pass"] is True
    assert Path(report["signature"]["public_key_path"]).exists()
    assert Path(report["signature"]["signature_out"]).exists()


def test_mgt_export_provenance_preserves_audit_only_evidence_model() -> None:
    provenance = _mgt_export_provenance_from_gap(
        {
            "mgt_export_support_mode": "bounded_patch_subset",
            "mgt_export_direct_patch_change_count": 24,
            "mgt_export_direct_patch_action_family_label": "connection_detailing=6, detailing=5",
            "mgt_export_instruction_sidecar_change_count": 0,
            "mgt_export_instruction_sidecar_action_family_label": "",
            "mgt_export_instruction_sidecar_audit_only_change_count": 11,
            "mgt_export_instruction_sidecar_audit_only_action_family_label": "connection_detailing=6, detailing=5",
            "mgt_export_instruction_sidecar_manual_input_change_count": 0,
            "mgt_export_instruction_sidecar_manual_input_action_family_label": "",
            "mgt_export_audit_review_manifest_change_count": 11,
            "mgt_export_audit_review_manifest_action_family_label": "connection_detailing=6, detailing=5",
            "mgt_export_audit_review_packet_count": 2,
            "mgt_export_audit_review_packet_action_family_label": "connection_detailing=1, detailing=1",
            "mgt_export_audit_review_packet_followup_type_label": "connection_detailing_audit_after_material_patch=1, detailing_audit_after_material_patch=1",
            "mgt_export_audit_review_packet_file_count": 2,
            "mgt_export_audit_review_packet_file_action_family_label": "connection_detailing=1, detailing=1",
            "mgt_export_audit_review_queue_item_count": 2,
            "mgt_export_audit_review_queue_pending_count": 2,
            "mgt_export_audit_review_queue_acknowledged_count": 0,
            "mgt_export_audit_review_queue_status_label": "pending_review=2",
            "mgt_export_audit_review_queue_action_family_label": "connection_detailing=1, detailing=1",
            "mgt_export_audit_review_followup_item_count": 2,
            "mgt_export_audit_review_followup_open_item_count": 2,
            "mgt_export_audit_review_followup_closed_item_count": 0,
            "mgt_export_audit_review_followup_action_label": "wait_for_review=2",
            "mgt_export_audit_review_followup_owner_label": "licensed_engineer=2",
            "mgt_export_audit_review_followup_status_label": "pending_review=2",
            "mgt_export_audit_review_followup_mode": "queue_status_projected_followup_actions",
            "mgt_export_connection_detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
            "mgt_export_detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
            "mgt_export_evidence_model": "direct_patch_plus_audit_review_manifest",
        }
    )
    assert provenance["mgt_export_instruction_sidecar_change_count"] == 0
    assert provenance["mgt_export_audit_review_manifest_change_count"] == 11
    assert provenance["mgt_export_audit_review_packet_count"] == 2
    assert provenance["mgt_export_audit_review_packet_file_count"] == 2
    assert provenance["mgt_export_audit_review_packet_file_action_family_label"] == "connection_detailing=1, detailing=1"
    assert provenance["mgt_export_audit_review_queue_item_count"] == 2
    assert provenance["mgt_export_audit_review_queue_pending_count"] == 2
    assert provenance["mgt_export_audit_review_queue_acknowledged_count"] == 0
    assert provenance["mgt_export_audit_review_queue_status_label"] == "pending_review=2"
    assert provenance["mgt_export_audit_review_queue_action_family_label"] == "connection_detailing=1, detailing=1"
    assert provenance["mgt_export_audit_review_followup_item_count"] == 2
    assert provenance["mgt_export_audit_review_followup_open_item_count"] == 2
    assert provenance["mgt_export_audit_review_followup_closed_item_count"] == 0
    assert provenance["mgt_export_audit_review_followup_action_label"] == "wait_for_review=2"
    assert provenance["mgt_export_audit_review_followup_owner_label"] == "licensed_engineer=2"
    assert provenance["mgt_export_audit_review_followup_status_label"] == "pending_review=2"
    assert provenance["mgt_export_delivery_boundary"] == (
        "direct_patch=connection_detailing=6, detailing=5 | "
        "sidecar=n/a | "
        "connection_payload=direct_patch_metadata_plus_sidecar | "
        "detailing_payload=direct_patch_metadata_plus_sidecar"
    )
    assert provenance["mgt_export_evidence_model"] == "direct_patch_plus_audit_review_manifest"


def test_generate_signed_release_registry_with_fixture_derived_panel_and_foundation_provenance(tmp_path: Path) -> None:
    repro = tmp_path / "repro.json"
    lock_manifest = tmp_path / "version_lock_manifest.json"
    kds = tmp_path / "kds_summary.json"
    midas = tmp_path / "midas_conversion.json"
    solver = tmp_path / "solver_hip_e2e.json"
    committee_summary = tmp_path / "committee_summary.json"
    gap_report = tmp_path / "release_gap_report.json"
    parser_script = tmp_path / "parser.py"
    out = tmp_path / "release_registry.json"
    pub = tmp_path / "release_registry.pub.pem"
    sig = tmp_path / "release_registry.signature.b64"

    parser_script.write_text("print('parser placeholder')\n", encoding="utf-8")
    (tmp_path / "kds.pdf").write_text("pdf placeholder\n", encoding="utf-8")

    lock_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase3-version-lock-manifest",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "seed": 23,
                "replay_runs": 3,
                "input_hashes": {"input.json": "a" * 64},
                "model_hashes": {"model.bin": "b" * 64},
                "replay_digest": "c" * 64,
            }
        ),
        encoding="utf-8",
    )
    repro.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-repro",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "lock_manifest": str(lock_manifest),
                "checks": {
                    "case_count_pass": True,
                    "seed_locked": True,
                    "input_hashes_frozen": True,
                    "model_hashes_frozen": True,
                    "no_missing_model_artifacts": True,
                    "rust_backend_used_pass": True,
                    "replay_exact_match": True,
                    "lock_manifest_written": True,
                },
                "summary": {"case_count": 4, "replay_runs": 3, "seed": 23},
            }
        ),
        encoding="utf-8",
    )
    kds.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-kds",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "artifacts": {"kds_compliance_pdf": str(tmp_path / "kds.pdf")},
            }
        ),
        encoding="utf-8",
    )
    midas.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-midas",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "source_provenance": {
                    "path": "sample.mgt",
                    "sha256": "d" * 64,
                },
                "metrics": {
                    "element_rows_total": 100,
                    "element_rows_skipped": 0,
                    "unknown_row_total": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    solver.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-solver-hip",
                "generated_at": "2026-03-06T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
            }
        ),
        encoding="utf-8",
    )
    committee_summary.write_text(
        json.dumps(
            {
                "authority_catalog_diff_change_count": 2,
                "authority_catalog_routing_warning_active": True,
                "metrics": {
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
                },
            }
        ),
        encoding="utf-8",
    )

    panel_report = _run_panel_fixture_provenance(tmp_path)
    foundation_report = _run_foundation_fixture_provenance(tmp_path)
    gap_report.write_text(
        json.dumps(
            {
                "summary": {
                    "deployment_model": "engineer_in_the_loop_accelerated_coverage",
                    "measured_chain_rolling_selection_mode": "current_pipeline_comparable_full_chain_pass",
                    "measured_chain_comparable_reference_deployment_model": "engineer_in_the_loop_accelerated_coverage",
                    "measured_chain_comparable_reference_strict_design_opt_cost_smoke": True,
                    "mgt_export_support_mode": "bounded_patch_subset",
                    "mgt_export_direct_patch_change_count": 7,
                    "mgt_export_direct_patch_action_family_label": "beam_section=1, slab_thickness=2, wall_thickness=5",
                    "mgt_export_instruction_sidecar_change_count": 12,
                    "mgt_export_instruction_sidecar_action_family_label": "connection_detailing=3, detailing=4, rebar=5",
                    "mgt_export_rebar_payload_namespace_mode": "material_level_only",
                    "mgt_export_rebar_payload_material_level_namespace_present": True,
                    "mgt_export_rebar_payload_group_local_namespace_present": False,
                    "mgt_export_group_local_rebar_payload_row_count": 0,
                    "mgt_export_group_local_connection_detailing_payload_row_count": 3,
                    "mgt_export_group_local_connection_detailing_payload_available_count": 3,
                    "mgt_export_group_local_detailing_payload_row_count": 4,
                    "mgt_export_group_local_detailing_payload_available_count": 4,
                    "mgt_export_connection_detailing_payload_namespace_mode": "group_local",
                    "mgt_export_connection_detailing_payload_group_local_namespace_present": True,
                    "mgt_export_detailing_payload_namespace_mode": "group_local",
                    "mgt_export_detailing_payload_group_local_namespace_present": True,
                    "mgt_export_connection_detailing_structured_payload_mapped_change_count": 3,
                    "mgt_export_connection_detailing_direct_patch_eligible_change_count": 2,
                    "mgt_export_detailing_direct_patch_eligible_change_count": 1,
                    "mgt_export_detailing_structured_payload_mapped_change_count": 4,
                    "mgt_export_connection_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                    "mgt_export_detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
                    "mgt_export_rebar_direct_patch_eligible_change_count": 0,
                    "mgt_export_rebar_direct_patch_ineligible_reason_label": "material_payload_missing=2, mixed_material_scope=4",
                    "mgt_export_rebar_direct_patch_mapping_source_label": "alt_slab_wall_group_id=5, direct_group_id=1",
                    "pbd_dynamic_hinge_refresh_ready": True,
                    "pbd_hinge_state_mode": "computed_member_local_hinge_refresh",
                    "pbd_hinge_refresh_reason": "dynamic hinge refresh attached",
                    "panel_zone_3d_clash_ready": bool(panel_report["summary"]["constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"),
                    "panel_zone_constructability_mode": str(panel_report["summary"]["constructability_mode"]),
                    "panel_zone_constructability_reason": str(panel_report["reason"]),
                    "panel_zone_proxy_candidate_count": int(panel_report["summary"]["panel_zone_proxy_candidate_count"]),
                    "panel_zone_source_artifact_kind": str(panel_report["summary"]["panel_zone_source_artifact_kind"]),
                    "panel_zone_source_contract_mode": str(panel_report["summary"]["panel_zone_source_contract_mode"]),
                    "panel_zone_missing_required_sources": list(panel_report["summary"]["panel_zone_missing_required_sources"]),
                    "panel_zone_topology_capable_input": bool(panel_report["summary"]["panel_zone_topology_capable_input"]),
                    "panel_zone_true_3d_clash_verified": bool(panel_report["summary"]["panel_zone_true_3d_clash_verified"]),
                    "panel_zone_true_3d_anchorage_verified": bool(panel_report["summary"]["panel_zone_true_3d_anchorage_verified"]),
                    "foundation_optimization_ready": bool(foundation_report["summary"]["optimization_mode"] == "active_foundation_member_optimization"),
                    "foundation_member_type_present": bool(foundation_report["summary"]["foundation_member_type_count"] > 0),
                    "foundation_member_type_count": int(foundation_report["summary"]["foundation_member_type_count"]),
                    "foundation_optimization_mode": str(foundation_report["summary"]["optimization_mode"]),
                    "foundation_optimization_reason": str(foundation_report["reason"]),
                    "foundation_scope_source": str(foundation_report["summary"]["foundation_scope_source"]),
                    "foundation_artifact_scan_mode": str(foundation_report["summary"]["foundation_artifact_scan_mode"]),
                    "foundation_artifact_evidence_mode": str(foundation_report["summary"]["foundation_artifact_evidence_mode"]),
                    "upstream_foundation_label_count": int(foundation_report["summary"]["upstream_foundation_label_count"]),
                    "raw_source_foundation_label_count": int(foundation_report["summary"]["raw_source_foundation_label_count"]),
                    "upstream_foundation_provenance_mode": str(foundation_report["summary"]["upstream_foundation_provenance_mode"]),
                    "wind_tunnel_raw_mapping_ready": True,
                    "wind_tunnel_mapping_mode": "raw_hffb_node_pressure_mapping",
                    "wind_tunnel_mapping_reason": "raw wind tunnel mapping artifact attached",
                }
            }
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_signed_release_registry.py",
        "--repro-report",
        str(repro),
        "--lock-manifest",
        str(lock_manifest),
        "--kds-summary",
        str(kds),
        "--midas-conversion",
        str(midas),
        "--solver-hip-e2e",
        str(solver),
        "--committee-summary",
        str(committee_summary),
        "--gap-report",
        str(gap_report),
        "--parser-script",
        str(parser_script),
        "--public-key-out",
        str(pub),
        "--signature-out",
        str(sig),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["mgt_export_direct_patch_action_family_label"] == "beam_section=1, slab_thickness=2, wall_thickness=5"
    assert report["summary"]["external_benchmark_execution_mode"] == "limited"
    assert report["summary"]["external_benchmark_execution_ready_task_count"] == 10
    assert report["summary"]["external_benchmark_execution_blocked_task_count"] == 2
    assert report["summary"]["external_benchmark_execution_review_boundary_pending_count"] == 2
    assert report["summary"]["external_benchmark_execution_status_mode"] == "planned_only"
    assert report["summary"]["external_benchmark_execution_executable_task_count"] == 10
    assert report["summary"]["external_benchmark_execution_planned_task_count"] == 10
    assert report["summary"]["external_benchmark_execution_in_progress_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_completed_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_failed_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_finished_task_count"] == 0
    assert report["summary"]["external_benchmark_execution_completion_ratio"] == 0.0
    assert report["summary"]["audit_review_decision_batch_template_item_count"] == 2
    assert report["summary"]["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert report["summary"]["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert report["summary"]["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert report["summary"]["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert report["summary"]["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert report["summary"]["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert report["summary"]["audit_review_decision_batch_runner_apply_live"] is False
    assert report["summary"]["audit_review_decision_batch_runner_live_applied"] is False
    assert report["summary"]["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert report["summary"]["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert report["summary"]["audit_review_decision_batch_runner_preview_pending_count"] == 0
    assert report["summary"]["audit_review_decision_batch_runner_preview_open_revision_count"] == 0
    assert report["summary"]["mgt_export_group_local_connection_detailing_payload_available_count"] == 3
    assert report["summary"]["mgt_export_connection_detailing_direct_patch_eligible_change_count"] == 2
    assert report["summary"]["mgt_export_detailing_direct_patch_eligible_change_count"] == 1
    assert report["summary"]["mgt_export_connection_detailing_delivery_mode"] == "structured_group_local_payload_plus_sidecar"
    assert report["summary"]["mgt_export_detailing_delivery_mode"] == "direct_patch_metadata_plus_sidecar"
    assert report["summary"]["panel_zone_3d_clash_ready"] is True
    assert report["summary"]["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert report["summary"]["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert report["summary"]["panel_zone_proxy_candidate_count"] == 1
    assert report["summary"]["foundation_optimization_ready"] is True
    assert report["summary"]["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert report["summary"]["foundation_scope_source"] == "dataset_summary"
    assert report["summary"]["raw_source_foundation_label_count"] == 3
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_3d_clash_ready"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_mode"] == "limited"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_ready_task_count"] == 10
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_blocked_task_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_review_boundary_pending_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_status_mode"] == "planned_only"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_executable_task_count"] == 10
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_planned_task_count"] == 10
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_in_progress_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_completed_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_failed_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_finished_task_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_execution_completion_ratio"] == 0.0
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_template_item_count"] == 2
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_template_current_status_label"] == "pending_review=2"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_approve_all_reason_code"] == "PASS_START_NOW_FULL"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_approve_all_ready_full"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_reject_one_reason_code"] == "ERR_ARCHITECTURE_BLOCKERS"
    assert report["registry_body"]["accelerated_coverage_provenance"]["external_benchmark_submission_preview_reject_one_blocker_label"] == "audit_review_resolution_has_open_revisions"
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_reason_code"] == "PASS"
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_apply_live"] is False
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_live_applied"] is False
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_reason_code"] == "PASS_START_NOW_FULL"
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_ready_full"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_pending_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["audit_review_decision_batch_runner_preview_open_revision_count"] == 0
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert report["registry_body"]["accelerated_coverage_provenance"]["panel_zone_true_3d_clash_verified"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["foundation_optimization_ready"] is True
    assert report["registry_body"]["accelerated_coverage_provenance"]["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert report["registry_body"]["accelerated_coverage_provenance"]["foundation_scope_source"] == "dataset_summary"
    assert report["registry_body"]["accelerated_coverage_provenance"]["raw_source_foundation_label_count"] == 3
