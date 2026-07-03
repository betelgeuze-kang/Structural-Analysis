from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_structural_product_development_roadmap.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_structural_product_development_roadmap",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_minimal_inputs(repo_root: Path) -> None:
    productization = repo_root / "implementation/phase1/release_evidence/productization"
    release = repo_root / "implementation/phase1/release"

    _write_json(
        productization / "product_readiness_snapshot.json",
        {
            "status": "blocked",
            "blocker_count": 3,
            "evidence_fresh": True,
            "snapshot_source_state_consistent": True,
            "release_ready": False,
            "paid_pilot_ready": False,
            "limited_commercial_ready": False,
            "workstation_delivery_ready": False,
            "independent_product_ready": False,
            "assisted_service_pilot_ready": False,
            "ga_enterprise_ready": False,
            "components": {
                "external_benchmark_receipts": {
                    "ready": False,
                    "attached_count": 1,
                    "queue_count": 4,
                },
                "g1": {
                    "full_load_hip_newton_lane_observed_load_scale": 0.656,
                },
                "github_actions_ci_streak": {
                    "pr_consecutive_pass_count": 12,
                    "nightly_consecutive_pass_count": 4,
                },
                "human_ux_observation": {
                    "blocker_count": 1,
                },
                "license_status": {
                    "status": "blocked",
                },
                "solver_product": {
                    "ready": False,
                    "blocker_count": 1,
                    "blockers": ["solver_validation_blocked"],
                },
            },
        },
    )
    _write_json(
        productization / "pm_release_gate_report.json",
        {
            "paid_pilot_candidate": True,
            "limited_commercial_milestone_ready": False,
            "milestones": [{"ok": True}, {"ok": False}],
            "release_area_matrix": [
                {"area": "ci", "ok": True, "blockers": []},
                {"area": "ux", "ok": False, "blockers": ["human_observation_missing"]},
            ],
        },
    )
    _write_json(
        productization / "developer_preview_rc_status.json",
        {
            "status": "blocked",
            "final_gate_pass_count": 1,
            "final_gate_count": 2,
            "final_gates": [
                {"item": "small_model", "contract_pass": True, "blockers": []},
                {
                    "item": "medium_model",
                    "contract_pass": False,
                    "blockers": ["medium_model_missing"],
                },
            ],
        },
    )
    _write_json(
        productization / "structural_scope_contamination_audit.json",
        {
            "schema_version": "structural-scope-contamination-audit.v1",
            "status": "quarantined",
            "contract_pass": True,
            "blockers": [],
            "non_structural_path_count": 3,
            "quarantined_non_structural_path_count": 3,
            "unquarantined_non_structural_path_count": 0,
            "release_surface_text_leak_path_count": 0,
        },
    )
    _write_json(
        productization / "structural_scope_owner_review_packet.json",
        {
            "schema_version": "structural-scope-owner-review-packet.v1",
            "status": "ready_for_owner_review",
            "contract_pass": True,
            "evidence_closure_pass": False,
            "owner_review_required": True,
            "owner_decision_pending_count": 3,
        },
    )
    _write_json(
        productization / "structural_scope_owner_decision_application_plan.json",
        {
            "schema_version": "structural-scope-owner-decision-application-plan.v1",
            "status": "pending_owner_decisions",
            "contract_pass": True,
            "application_ready": False,
            "evidence_closure_pass": False,
            "owner_decision_recorded_count": 0,
            "owner_decision_pending_count": 3,
            "release_surface_owner_decision_required_count": 1,
            "release_surface_first_batch_template_paths": {
                "csv": (
                    "implementation/phase1/release_evidence/productization/"
                    "structural_scope_owner_decisions.release_surface_first.template.csv"
                ),
            },
            "release_surface_first_batch_decision_intake": {
                "schema_version": (
                    "structural-scope-release-surface-first-batch-decision-intake.v1"
                ),
                "status": "pending_owner_decisions",
                "expected_path_count": 1,
                "valid_cleanup_decision_count": 0,
                "pending_decision_count": 1,
            },
            "next_owner_review_batch": {
                "batch_id": "release_surface_first",
                "path_area": "release_surface",
                "path_count": 1,
                "paths": [
                    "implementation/phase1/release_evidence/surface/non_structural_scope_surface.json"
                ],
            },
        },
    )
    _write_json(
        productization / "structural_scope_release_surface_owner_handoff_check.json",
        {
            "schema_version": "structural-scope-release-surface-owner-handoff-check.v1",
            "status": "ready_for_owner_review",
            "contract_pass": True,
            "handoff_check_pass": True,
            "expected_release_surface_path_count": 1,
            "expected_release_surface_paths": [
                "implementation/phase1/release_evidence/surface/non_structural_scope_surface.json"
            ],
            "owner_decision_state": {
                "owner_decision_pending_count": 3,
                "owner_decision_recorded_count": 0,
                "release_surface_owner_decision_required_count": 1,
            },
            "blockers": [],
            "claim_boundary": (
                "Fixture verifies owner handoff consistency only."
            ),
        },
    )
    _write_json(
        productization / "release_evidence_freshness_report.json",
        {
            "contract_pass": True,
            "summary": {"pass_count": 10, "artifact_count": 10},
        },
    )
    _write_json(productization / "mgt_g1_direct_residual_terminal_gate_report.json", {"contract_pass": True})
    _write_json(
        productization / "g1_full_load_hip_newton_lane_report.json",
        {
            "contract_pass": False,
            "blockers": ["full_load_hip_newton_not_closed"],
            "lane_next_actions": [
                {"id": "generate_full_load_1p0_checkpoint_candidate"},
                {"id": "close_consistent_residual_jacobian_newton_gate"},
            ],
            "terminal_requirement_breakdown": {
                "schema_version": (
                    "g1-full-load-hip-newton-terminal-requirement-breakdown.v1"
                ),
                "ready_requirement_count": 1,
                "requirement_count": 4,
                "active_terminal_requirement_id": "full_load_checkpoint_1p0",
            },
        },
    )
    _write_json(
        productization / "g1_consistent_newton_full_load_checkpoint_candidate_runner.json",
        {
            "schema_version": (
                "g1-consistent-newton-full-load-checkpoint-candidate-runner.v1"
            ),
            "status": "ready_for_runner_implementation",
            "contract_pass": True,
            "evidence_closure_pass": False,
            "summary": {
                "next_action_ids": [
                    "generate_full_load_1p0_checkpoint_candidate",
                    "close_consistent_residual_jacobian_newton_gate",
                    "prove_production_rocm_hip_residual_jvp_worker",
                ]
            },
            "runner_contract": {
                "runner_id": "build_consistent_newton_full_load_checkpoint_candidate_runner",
                "preferred_candidate_generator": (
                    "consistent_residual_jacobian_newton_rocm_full_load_candidate"
                ),
            },
            "checkpoint_gap": {
                "required_load_scale": 1.0,
                "highest_observed_load_scale": 0.656,
            },
            "worker_path_repair_plan": {
                "schema_version": "g1-production-rocm-hip-worker-path-repair-plan.v1",
                "status": "blocked",
                "next_action_id": "repair_production_rocm_hip_residual_jvp_worker_path",
                "blocker_count": 3,
                "category_counts": {
                    "runtime_device_interface": 1,
                    "matrix_free_global_krylov": 1,
                    "current_tangent_residual_row_replay": 1,
                },
            },
        },
    )
    _write_json(
        productization / "g1_global_connectivity_load_path_audit.json",
        {
            "status": "ready",
            "summary": {
                "global_connectivity_classification": "element_graph_connects_dominant_modes_to_supports",
                "dominant_nodes_element_reachable_to_support_count": 8,
                "dominant_nodes_without_element_path_to_support_count": 0,
            },
            "decision_record": {
                "schema_version": "g1-global-connectivity-decision-record.v1",
                "row_only_correction_loop_stopped": True,
                "primary_next_lane": "consistent_residual_jacobian_newton_rocm_worker",
            },
        },
    )
    _write_json(
        productization / "g1_f2g_f2h_cause_narrowing_status.json",
        {
            "status": "ready",
            "contract_pass": True,
            "evidence_signals": {
                "support_or_link_row_gap_disfavored": True,
                "row_only_correction_loop_stopped_by_global_connectivity": True,
                "f2h_lightweight_0p1_0p2_0p4_ready": True,
            },
            "decision_record": {
                "schema_version": "g1-f2g-f2h-next-lane-decision.v1",
                "stop_row_only_support_or_elastic_link_correction_loop": True,
                "primary_next_lane": "consistent_residual_jacobian_newton_rocm_worker",
            },
        },
    )
    _write_json(
        productization / "g1_load_dependent_near_null_geometric_stiffness_comparison.json",
        {
            "status": "blocked",
            "contract_pass": False,
            "summary": {
                "near_null_packet_comparison_ready": False,
                "geometric_softening_signal": "active_secondary",
                "missing_near_null_packet_count": 2,
            },
        },
    )
    _write_json(
        repo_root / "implementation/phase1/customer_shadow_evidence_status.json",
        {"summary": {"completed_shadow_case_count": 1, "min_completed_shadow_cases": 3}},
    )
    _write_json(
        release / "external_benchmark_submission_readiness.json",
        {"summary": {"ready_to_start_full_submission_now": False}},
    )


def test_structural_product_development_roadmap_summarizes_blocked_stages(
    tmp_path: Path,
) -> None:
    _write_minimal_inputs(tmp_path)

    payload = module.build_structural_product_development_roadmap(repo_root=tmp_path)

    assert payload["schema_version"] == "structural-product-development-roadmap.v1"
    assert payload["surface_id"] == "structural_product_development_roadmap"
    assert payload["status"] == "blocked"
    assert payload["product_completion_claim"] is False
    assert payload["stage_count"] == 8
    assert payload["ready_stage_count"] == 1
    assert payload["primary_blocker"] == "release_surface_owner_decision_pending_count=1"
    assert payload["recommended_next_slice"] == [
        "close_structural_scope_owner_review_and_release_surface_cleanup",
        "land_ci_license_ux_release_area_evidence",
        "close_developer_preview_medium_large_and_parity_gates",
        "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path",
        "collect_customer_shadow_and_external_benchmark_terminal_receipts",
    ]
    details = {row["id"]: row for row in payload["recommended_next_slice_details"]}
    assert details[
        "close_structural_scope_owner_review_and_release_surface_cleanup"
    ]["current_position"]["owner_decisions_recorded"] == "0/3"
    assert details[
        "close_structural_scope_owner_review_and_release_surface_cleanup"
    ]["current_position"]["release_surface_cleanup_decisions"] == "0/1"
    assert details[
        "close_structural_scope_owner_review_and_release_surface_cleanup"
    ]["current_position"]["next_owner_review_batch"] == "release_surface_first"
    assert details[
        "close_structural_scope_owner_review_and_release_surface_cleanup"
    ]["current_position"]["release_surface_owner_handoff_check_pass"] is True
    assert details["land_ci_license_ux_release_area_evidence"]["current_position"][
        "pm_release_areas"
    ] == "1/2"
    assert details[
        "close_developer_preview_medium_large_and_parity_gates"
    ]["current_position"]["developer_preview_final_gates"] == "1/2"
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["recommended_g1_next_direction"]
        == "consistent_residual_jacobian_newton_rocm_worker"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["terminal_requirements"]
        == "1/4"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_terminal_requirement"]
        == "full_load_checkpoint_1p0"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["rocm_worker_path_repair_next_action"]
        == "repair_production_rocm_hip_residual_jvp_worker_path"
    )
    assert details[
        "collect_customer_shadow_and_external_benchmark_terminal_receipts"
    ]["current_position"]["completed_shadow_case_count"] == 1

    stages = {row["stage_id"]: row for row in payload["roadmap_stages"]}
    assert stages["evidence_freshness_and_snapshot_integrity"]["status"] == "ready"
    assert stages["structural_scope_cleanup"]["status"] == "partial"
    assert stages["structural_scope_cleanup"]["blockers"] == [
        "release_surface_owner_decision_pending_count=1",
        "owner_decision_pending_count=3",
        "structural_scope_cleanup_evidence_closure_not_passed",
    ]
    assert stages["structural_scope_cleanup"]["summary"][
        "unquarantined_non_structural_path_count"
    ] == 0
    assert stages["structural_scope_cleanup"]["summary"][
        "next_owner_review_batch"
    ] == {
        "batch_id": "release_surface_first",
        "path_area": "release_surface",
        "path_count": 1,
        "priority": 0,
        "review_goal": "",
    }
    assert stages["structural_scope_cleanup"]["summary"][
        "release_surface_owner_handoff_check_pass"
    ] is True
    assert stages["pm_release_gate"]["blockers"] == ["ux::human_observation_missing"]
    assert stages["g1_solver_closure"]["blockers"] == [
        "full_load_hip_newton_not_closed"
    ]
    assert (
        stages["g1_solver_closure"]["summary"]["f2g_f2h_cause_narrowing_status"]
        == "ready"
    )
    assert (
        stages["g1_solver_closure"]["summary"]["global_connectivity_load_path_audit_status"]
        == "ready"
    )
    assert (
        stages["g1_solver_closure"]["summary"]["global_connectivity_classification"]
        == "element_graph_connects_dominant_modes_to_supports"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "dominant_nodes_element_reachable_to_support_count"
        ]
        == 8
    )
    assert (
        stages["g1_solver_closure"]["summary"]["recommended_g1_next_direction"]
        == "consistent_residual_jacobian_newton_rocm_worker"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "full_load_hip_newton_terminal_ready_requirements"
        ]
        == "1/4"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "full_load_hip_newton_active_terminal_requirement"
        ]
        == "full_load_checkpoint_1p0"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "consistent_newton_full_load_runner_contract_status"
        ]
        == "ready_for_runner_implementation"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "consistent_newton_full_load_runner_contract_pass"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"]["rocm_worker_path_repair_status"]
        == "blocked"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "rocm_worker_path_repair_blocker_count"
        ]
        == 3
    )
    assert stages["g1_solver_closure"]["summary"][
        "rocm_worker_path_repair_category_counts"
    ] == {
        "runtime_device_interface": 1,
        "matrix_free_global_krylov": 1,
        "current_tangent_residual_row_replay": 1,
    }
    assert (
        stages["g1_solver_closure"]["summary"][
            "load_dependent_near_null_geometric_stiffness_comparison_status"
        ]
        == "blocked"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "load_dependent_geometric_softening_signal"
        ]
        == "active_secondary"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "load_dependent_near_null_missing_packet_count"
        ]
        == 2
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "consistent_newton_full_load_runner_evidence_closure_pass"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"]["row_only_correction_loop_stopped"]
        is True
    )
    assert stages["g1_solver_closure"]["next_actions"][:2] == [
        "generate_full_load_1p0_checkpoint_candidate",
        "close_consistent_residual_jacobian_newton_gate",
    ]
    assert (
        "implementation/phase1/release_evidence/productization/g1_global_connectivity_load_path_audit.json"
        in stages["g1_solver_closure"]["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/g1_consistent_newton_full_load_checkpoint_candidate_runner.json"
        in stages["g1_solver_closure"]["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/g1_f2g_f2h_cause_narrowing_status.json"
        in stages["g1_solver_closure"]["evidence_artifacts"]
    )
    assert (
        "implementation/phase1/release_evidence/productization/g1_load_dependent_near_null_geometric_stiffness_comparison.json"
        in stages["g1_solver_closure"]["evidence_artifacts"]
    )
    assert stages["paid_pilot_readiness"]["blockers"] == [
        "customer_shadow_below_required:1/3",
        "external_benchmark_receipts_pending:1/4",
        "product_snapshot_paid_pilot_ready_false",
    ]


def test_write_structural_product_development_roadmap_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    _write_minimal_inputs(tmp_path)
    out_json = tmp_path / "roadmap.json"
    out_md = tmp_path / "roadmap.md"

    payload = module.write_structural_product_development_roadmap(
        repo_root=tmp_path,
        out_json=out_json,
        out_md=out_md,
    )

    assert json.loads(out_json.read_text(encoding="utf-8"))["summary_line"] == payload[
        "summary_line"
    ]
    assert "# Structural Product Development Roadmap" in out_md.read_text(
        encoding="utf-8"
    )


def test_structural_product_development_roadmap_check_detects_stale_json(
    tmp_path: Path,
) -> None:
    _write_minimal_inputs(tmp_path)
    out_json = tmp_path / "roadmap.json"
    out_md = tmp_path / "roadmap.md"

    module.write_structural_product_development_roadmap(
        repo_root=tmp_path,
        out_json=out_json,
        out_md=out_md,
    )

    ok, message, _generated = module.check_structural_product_development_roadmap(
        repo_root=tmp_path,
        out_json=out_json,
        out_md=out_md,
    )
    assert ok is True
    assert message == "structural_product_development_roadmap_consistent"

    stale_payload = json.loads(out_json.read_text(encoding="utf-8"))
    stale_payload["roadmap_stages"][0]["summary"]["snapshot_blocker_count"] = 999
    _write_json(out_json, stale_payload)

    ok, message, _generated = module.check_structural_product_development_roadmap(
        repo_root=tmp_path,
        out_json=out_json,
        out_md=out_md,
    )
    assert ok is False
    assert message.startswith("roadmap_semantic_mismatch:")
    assert "roadmap_stages" in message
