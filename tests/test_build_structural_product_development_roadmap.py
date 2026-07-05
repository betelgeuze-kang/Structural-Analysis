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
            "true_newton_full_load_checkpoint_candidate": {
                "present": True,
                "status": "candidate_created",
                "checkpoint_written": True,
                "checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_true_newton_full_load_checkpoint_candidate.npz"
                ),
                "checkpoint_direct_residual_inf_n": 464.56223807569995,
                "true_newton_residual_gate_passed": False,
            },
            "true_newton_from_active_set_ls_trust_candidate": {
                "present": True,
                "status": "review",
                "true_final_residual_n": 0.42740724991695345,
                "true_residual_gate_passed": False,
                "true_stop_reason": "line_search_no_descent",
                "max_jvp_minus_unregularized_tangent_action_relative_inf": (
                    4.088178091005261
                ),
                "dominant_jvp_gap_component": "frame",
            },
            "true_newton_from_active_set_service_tangent_ls_trust_candidate": {
                "present": True,
                "status": "review",
                "true_final_residual_n": 0.42740724991695345,
                "true_residual_gate_passed": False,
                "true_stop_reason": "line_search_no_descent",
                "max_jvp_minus_unregularized_tangent_action_relative_inf": (
                    4.088231545444302
                ),
                "dominant_jvp_gap_component": "frame",
            },
            "true_newton_frame_tangent_source_comparison": {
                "present": True,
                "both_line_search_no_descent": True,
                "both_dominant_gap_component_frame": True,
                "service_minus_force_max_jvp_gap_relative_inf": (
                    5.3454439040478974e-05
                ),
            },
            "frame_tangent_fd_epsilon_sweep": {
                "present": True,
                "status": "ready",
                "default_eps_gap_relative_inf": 4.088178091005261,
                "best_eps": 0.001,
                "best_eps_gap_relative_inf": 0.003379869645939948,
                "default_eps_artifact_likely": True,
            },
            "true_newton_from_active_set_mu_sweep": {
                "present": True,
                "status": "ready",
                "evaluated_mu_count": 11,
                "factorable_mu_count": 11,
                "descent_observed": False,
                "best_mu": 0.03,
                "best_improvement_inf_n": -2.9530156098189764e-10,
            },
            "active_set_load_parameter_probe": {
                "present": True,
                "status": "ready",
                "actual_replay_descent_observed": False,
                "best_actual_replay_load_scale": 0.995,
                "best_actual_replay_residual_inf_n": 66.12257730630517,
                "best_actual_replay_improvement_inf_n": -65.69517005638822,
                "restored_full_load_descent_observed": False,
                "best_restored_full_load_residual_inf_n": 0.42811959570077285,
            },
            "active_set_load_parameter_tiny_trust_probe": {
                "present": True,
                "status": "ready",
                "actual_replay_descent_observed": True,
                "best_actual_replay_load_scale": 0.99999,
                "best_actual_replay_residual_inf_n": 0.4274029760383601,
                "best_actual_replay_improvement_inf_n": (
                    4.273878593363811e-06
                ),
                "restored_full_load_descent_observed": False,
                "best_restored_full_load_residual_inf_n": (
                    0.42740796265036174
                ),
            },
            "active_frontier_residual_ownership_probe": {
                "present": True,
                "status": "ready",
                "top_residual_inf_n": 0.42740724991695345,
                "top_row_node_id": 2276,
                "top_row_dof_label": "UZ",
                "top_row_dominant_internal_component": "shell_bending_drilling",
                "top_row_balance_driver": "external_load_balance",
                "top_row_inferred_external_load_n": 0.569876333333335,
            },
            "active_frontier_shell_load_neighborhood_probe": {
                "present": True,
                "status": "ready",
                "top_row_required_reference_shell_load_scale_for_zero_row_residual": (
                    0.25000000014572954
                ),
                "top_row_surface_component_free_pressure_resultant": True,
                "top_incident_element_id": 25880,
            },
            "active_frontier_shell_policy_replay_probe": {
                "present": True,
                "status": "ready",
                "best_policy": "attached_components_only",
                "best_residual_inf_n": 0.3818403374023447,
                "best_improvement_inf_n": 0.04556691251460876,
                "structural_or_attached_policy_descent_observed": True,
                "best_residual_gate_passed": False,
            },
            "active_frontier_shell_policy_linearized_active_set_probe": {
                "present": True,
                "status": "ready",
                "shell_pressure_load_path_policy": "structural_components_only",
                "best_linear_active_residual_after_inf_n": 7.245315458703772e-13,
                "linearized_active_descent_observed": True,
                "direct_replay_required_for_candidate": True,
            },
            "active_frontier_structural_policy_active_set_ls_trust_candidate": {
                "present": True,
                "status": "candidate_created",
                "final_residual_n": 0.07205501101467937,
                "total_reduction_n": 0.048877269735777995,
                "residual_gate_passed": False,
                "checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.npz"
                ),
            },
            "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep": {
                "present": True,
                "status": "review",
                "final_residual_n": 0.07205501101467937,
                "stop_reason": "no_candidate_descent",
            },
            "active_frontier_structural_policy_residual_ownership_probe": {
                "present": True,
                "status": "ready",
                "top_row_dof_label": "RX",
                "top_row_dominant_internal_component": "shell_bending_drilling",
                "top_row_balance_driver": "shell_bending_drilling_internal_force",
                "top_row_load_derivative_n_per_load": 0.0,
            },
            "active_frontier_structural_policy_linearized_active_set_after_two_step_probe": {
                "present": True,
                "status": "ready",
                "best_linear_active_residual_after_inf_n": 3.396605913197348e-13,
                "linearized_active_descent_observed": True,
            },
            "active_frontier_structural_policy_shell_rotation_row_candidate": {
                "present": True,
                "status": "ready",
                "fd_consistent": True,
                "selected_rotation_row_count": 4,
                "best_direct_residual_inf_n": 0.04728610099315822,
                "best_improvement_inf_n": 0.006755157257430255,
                "checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
                ),
                "checkpoint_best_alpha": 0.125,
            },
            "active_frontier_structural_policy_shell_rotation_row_no_descent_probe": {
                "present": True,
                "status": "ready",
                "base_residual_inf_n": 0.04728610099315822,
                "best_improvement_inf_n": -0.0016700968262350901,
                "direct_descent_observed": False,
            },
            "active_frontier_structural_policy_shell_rotation_candidate_residual_ownership_probe": {
                "present": True,
                "status": "ready",
                "top_residual_inf_n": 0.04728610099315822,
                "top_row_dof_label": "RX",
                "top_row_dominant_internal_component": "shell_bending_drilling",
                "top_row_balance_driver": "shell_bending_drilling_internal_force",
            },
            "sparse_direct_scaled_lsmr_frontier_probe": {
                "present": True,
                "status": "ready",
                "jvp_parity_pass": True,
                "assembled_tangent_parity_pass": True,
                "direction_status": "ready",
                "line_search_status": "ready",
                "line_search_residual_after_n": 0.04728606850215522,
                "line_search_residual_reduction_ratio": 6.871152900485691e-07,
                "output_checkpoint_written": True,
                "output_checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
                ),
                "output_checkpoint_direct_residual_inf_n": 0.04728606850215522,
                "output_checkpoint_residual_gate_passed": False,
            },
            "sparse_direct_scaled_lsmr_second_probe": {
                "present": True,
                "status": "ready",
                "line_search_status": "ready",
                "line_search_residual_after_n": 0.047285916814733264,
                "line_search_residual_reduction_ratio": 3.2078670687026466e-06,
                "output_checkpoint_written": True,
                "output_checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
                ),
                "output_checkpoint_direct_residual_inf_n": 0.047285916814733264,
                "output_checkpoint_residual_gate_passed": False,
            },
            "sparse_direct_scaled_lsmr_chain": {
                "present": True,
                "step_count": 3,
                "ready_step_count": 3,
                "checkpoint_written_step_count": 3,
                "all_steps_ready": True,
                "all_output_checkpoints_written": True,
                "monotonic_residual_descent": True,
                "initial_residual_n": 0.04728610099315822,
                "final_residual_n": 0.047285863685509466,
                "total_reduction_n": 2.3730764875384835e-07,
                "total_reduction_ratio": 5.018549716928113e-06,
                "latest_checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz"
                ),
                "latest_checkpoint_residual_gate_passed": False,
                "promotes_g1_closure": False,
            },
            "sparse_direct_scaled_lsmr_chain_probe": {
                "present": True,
                "status": "ready",
                "step_count": 3,
                "monotonic_residual_descent": True,
                "final_residual_n": 0.047285863685509466,
                "latest_checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_mgt_sparse_direct_scaled_lsmr_chain_step_03_candidate.npz"
                ),
                "promotes_g1_closure": False,
            },
            "sparse_direct_scaled_lsmr_long_chain_probe": {
                "present": True,
                "status": "ready",
                "step_count": 10,
                "monotonic_residual_descent": True,
                "final_residual_n": 0.04728560329011722,
                "final_residual_over_gate": 94.57120658023443,
                "estimated_steps_to_gate_at_last_reduction": 2008386,
                "gate_convergence_assessment": "stalled_for_gate",
                "recommended_next_action": (
                    "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
                ),
                "latest_checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_mgt_sparse_direct_scaled_lsmr_long_chain_step_10_candidate.npz"
                ),
                "promotes_g1_closure": False,
            },
            "shell_hotspot_tangent_fd_jvp": {
                "present": True,
                "status": "ready",
                "fd_consistent": True,
                "max_relative_inf_error": 7.82988821999408e-14,
                "evaluated_row_count": 8,
            },
            "shell_hotspot_diagonal_sweep": {
                "present": True,
                "status": "ready",
                "descent_observed": False,
                "best_direct_residual_inf_n": 0.4278508811240626,
                "best_improvement_inf_n": -2.0477105863392353e-05,
            },
            "global_tangent_scaled_sweep": {
                "present": True,
                "status": "ready",
                "descent_observed": False,
                "best_direct_residual_inf_n": 0.42783040426657654,
                "best_improvement_inf_n": -2.483773187123006e-10,
                "linear_relative_residual_inf": 0.4278305011820284,
            },
            "residual_norm_gradient_tiny_sweep": {
                "present": True,
                "status": "ready",
                "inf_descent_observed": False,
                "l2_descent_observed": True,
                "best_l2_direct_residual_l2_n": 1.2159739821333575,
                "best_l2_improvement_l2_n": 0.16379561248899166,
            },
            "active_set_ls_sweep": {
                "present": True,
                "status": "ready",
                "full_inf_descent_observed": True,
                "active_inf_descent_observed": True,
                "best_full_direct_residual_inf_n": 0.4274072503950392,
                "best_full_improvement_inf_n": 0.000423153623160033,
            },
            "active_set_ls_trust_candidate": {
                "present": True,
                "status": "candidate_created",
                "checkpoint_written": True,
                "final_residual_n": 0.42740724991695345,
                "residual_gate_passed": False,
                "checkpoint_path": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
                ),
            },
            "active_set_ls_trust_schedule_candidate": {
                "present": True,
                "status": "candidate_created",
                "final_residual_n": 0.4274072499174437,
                "residual_gate_passed": False,
                "active_row_count_schedule": [8, 16, 32],
            },
            "active_set_ls_trust_tangent_fd_jvp": {
                "present": True,
                "status": "ready",
                "base_residual_inf_n": 0.42740724991695345,
                "fd_consistent": True,
                "max_relative_inf_error": 5.0e-14,
                "evaluated_row_count": 2,
                "consistent_residual_jacobian_newton_gate_passed": False,
            },
            "active_set_minimax_trust_candidate": {
                "present": True,
                "status": "review",
                "final_residual_n": 0.42740724991695345,
                "residual_gate_passed": False,
                "steps_taken": 0,
                "best_linear_active_inf_improvement_n": 1.1784706543949142e-10,
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
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_residual_ownership_top_row_balance_driver"
        ]
        == "external_load_balance"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_load_neighborhood_top_free_pressure_resultant"
        ]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_load_neighborhood_top_required_shell_load_scale"
        ]
        == 0.25000000014572954
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_frontier_shell_policy_replay_best_policy"]
        == "attached_components_only"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_policy_replay_best_residual_inf_n"
        ]
        == 0.3818403374023447
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_policy_replay_descent_observed"
        ]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_policy_replay_best_residual_gate_passed"
        ]
        is False
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_policy_linearized_active_set_policy"
        ]
        == "structural_components_only"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_policy_linearized_active_set_best_after_inf_n"
        ]
        == 7.245315458703772e-13
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_shell_policy_linearized_active_set_direct_replay_required"
        ]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_active_set_ls_trust_final_residual_n"
        ]
        == 0.07205501101467937
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_active_set_ls_trust_total_reduction_n"
        ]
        == 0.048877269735777995
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_active_set_ls_trust_residual_gate_passed"
        ]
        is False
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_stop_reason"
        ]
        == "no_candidate_descent"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_residual_ownership_top_row_dof_label"
        ]
        == "RX"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_residual_ownership_top_row_balance_driver"
        ]
        == "shell_bending_drilling_internal_force"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_linearized_after_two_step_best_after_inf_n"
        ]
        == 3.396605913197348e-13
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_shell_rotation_candidate_best_residual_inf_n"
        ]
        == 0.04728610099315822
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_shell_rotation_candidate_best_improvement_inf_n"
        ]
        == 0.006755157257430255
    )
    assert details[
        "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
    ]["current_position"][
        "active_frontier_structural_policy_shell_rotation_candidate_checkpoint_path"
    ].endswith(
        "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_shell_rotation_no_descent_best_improvement_inf_n"
        ]
        == -0.0016700968262350901
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_shell_rotation_no_descent_observed"
        ]
        is False
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_dof_label"
        ]
        == "RX"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_balance_driver"
        ]
        == "shell_bending_drilling_internal_force"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_frontier_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_frontier_jvp_parity_pass"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_frontier_tangent_parity_pass"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_frontier_direction_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_frontier_line_search_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_frontier_line_search_residual_after_n"
        ]
        == 0.04728606850215522
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_frontier_line_search_reduction_ratio"
        ]
        == 6.871152900485691e-07
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_written"
        ]
        is True
    )
    assert details[
        "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
    ]["current_position"][
        "sparse_direct_scaled_lsmr_frontier_output_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_n"
        ]
        == 0.04728606850215522
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_gate_passed"
        ]
        is False
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_second_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_second_line_search_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_second_line_search_residual_after_n"
        ]
        == 0.047285916814733264
    )
    assert details[
        "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
    ]["current_position"][
        "sparse_direct_scaled_lsmr_second_output_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_second_output_checkpoint_residual_n"
        ]
        == 0.047285916814733264
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_chain_step_count"]
        == 3
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_chain_monotonic_residual_descent"
        ]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_chain_final_residual_n"]
        == 0.047285863685509466
    )
    assert details[
        "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
    ]["current_position"][
        "sparse_direct_scaled_lsmr_chain_latest_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_chain_probe_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_chain_probe_final_residual_n"
        ]
        == 0.047285863685509466
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["sparse_direct_scaled_lsmr_long_chain_probe_status"]
        == "ready"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_long_chain_probe_step_count"
        ]
        == 10
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_long_chain_probe_final_residual_over_gate"
        ]
        == 94.57120658023443
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_long_chain_probe_estimated_steps_to_gate_at_last_reduction"
        ]
        == 2008386
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_long_chain_probe_gate_convergence_assessment"
        ]
        == "stalled_for_gate"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "sparse_direct_scaled_lsmr_long_chain_probe_recommended_next_action"
        ]
        == "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["shell_hotspot_tangent_fd_jvp_fd_consistent"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["shell_hotspot_diagonal_sweep_descent_observed"]
        is False
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["global_tangent_scaled_sweep_descent_observed"]
        is False
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["residual_norm_gradient_tiny_sweep_l2_descent_observed"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_set_ls_sweep_full_inf_descent_observed"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_set_ls_trust_candidate_checkpoint_written"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_set_ls_trust_schedule_candidate_final_residual_n"]
        == 0.4274072499174437
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_set_ls_trust_schedule_candidate_active_row_count_schedule"
        ]
        == [8, 16, 32]
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_set_ls_trust_tangent_fd_jvp_fd_consistent"]
        is True
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"][
            "active_set_ls_trust_tangent_fd_jvp_evaluated_row_count"
        ]
        == 2
    )
    assert (
        details[
            "continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path"
        ]["current_position"]["active_set_minimax_trust_candidate_steps_taken"]
        == 0
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
        stages["g1_solver_closure"]["summary"][
            "true_newton_full_load_checkpoint_candidate_written"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_full_load_checkpoint_candidate_residual_n"
        ]
        == 464.56223807569995
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_from_active_set_stop_reason"
        ]
        == "line_search_no_descent"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_from_active_set_max_jvp_gap_relative_inf"
        ]
        == 4.088178091005261
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_from_active_set_dominant_gap_component"
        ]
        == "frame"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_from_active_set_service_tangent_max_jvp_gap_relative_inf"
        ]
        == 4.088231545444302
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_frame_tangent_source_comparison_both_line_search_no_descent"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_frame_tangent_source_comparison_both_dominant_gap_component_frame"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "frame_tangent_fd_epsilon_sweep_default_eps_artifact_likely"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "frame_tangent_fd_epsilon_sweep_best_gap_relative_inf"
        ]
        == 0.003379869645939948
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_from_active_set_mu_sweep_evaluated_mu_count"
        ]
        == 11
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "true_newton_from_active_set_mu_sweep_descent_observed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_load_parameter_probe_descent_observed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_load_parameter_tiny_trust_descent_observed"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_load_parameter_tiny_trust_best_load_scale"
        ]
        == 0.99999
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_load_parameter_tiny_trust_restored_full_load_descent_observed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_residual_ownership_present"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_residual_ownership_top_row_balance_driver"
        ]
        == "external_load_balance"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_residual_ownership_top_row_dominant_internal_component"
        ]
        == "shell_bending_drilling"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_residual_ownership_top_row_inferred_external_load_n"
        ]
        == 0.569876333333335
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_load_neighborhood_top_free_pressure_resultant"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_load_neighborhood_top_incident_element_id"
        ]
        == 25880
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_policy_replay_best_policy"
        ]
        == "attached_components_only"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_policy_replay_best_residual_inf_n"
        ]
        == 0.3818403374023447
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_policy_replay_descent_observed"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_policy_linearized_active_set_policy"
        ]
        == "structural_components_only"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_policy_linearized_active_set_best_after_inf_n"
        ]
        == 7.245315458703772e-13
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_shell_policy_linearized_active_set_descent_observed"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_structural_policy_active_set_ls_trust_final_residual_n"
        ]
        == 0.07205501101467937
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_stop_reason"
        ]
        == "no_candidate_descent"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_structural_policy_residual_ownership_top_row_dof_label"
        ]
        == "RX"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_structural_policy_residual_ownership_top_row_component"
        ]
        == "shell_bending_drilling"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_frontier_structural_policy_linearized_after_two_step_descent_observed"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_frontier_status"
        ]
        == "ready"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_frontier_line_search_residual_after_n"
        ]
        == 0.04728606850215522
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_frontier_line_search_reduction_ratio"
        ]
        == 6.871152900485691e-07
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_written"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_n"
        ]
        == 0.04728606850215522
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_second_line_search_residual_after_n"
        ]
        == 0.047285916814733264
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_second_output_checkpoint_written"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_second_output_checkpoint_residual_n"
        ]
        == 0.047285916814733264
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_chain_step_count"
        ]
        == 3
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_chain_monotonic_residual_descent"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_chain_final_residual_n"
        ]
        == 0.047285863685509466
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_chain_probe_status"
        ]
        == "ready"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_long_chain_probe_final_residual_n"
        ]
        == 0.04728560329011722
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_long_chain_probe_gate_convergence_assessment"
        ]
        == "stalled_for_gate"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "sparse_direct_scaled_lsmr_long_chain_probe_recommended_next_action"
        ]
        == "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "shell_hotspot_tangent_fd_jvp_fd_consistent"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "shell_hotspot_tangent_fd_jvp_max_relative_inf_error"
        ]
        == 7.82988821999408e-14
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "shell_hotspot_diagonal_sweep_descent_observed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "shell_hotspot_diagonal_sweep_best_improvement_n"
        ]
        == -2.0477105863392353e-05
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "global_tangent_scaled_sweep_descent_observed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "global_tangent_scaled_sweep_best_improvement_n"
        ]
        == -2.483773187123006e-10
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "global_tangent_scaled_sweep_linear_relative_residual"
        ]
        == 0.4278305011820284
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "residual_norm_gradient_tiny_sweep_inf_descent_observed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "residual_norm_gradient_tiny_sweep_l2_descent_observed"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "residual_norm_gradient_tiny_sweep_best_l2_improvement_n"
        ]
        == 0.16379561248899166
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_sweep_full_inf_descent_observed"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_sweep_best_full_residual_n"
        ]
        == 0.4274072503950392
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_sweep_best_full_improvement_n"
        ]
        == 0.000423153623160033
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_trust_candidate_final_residual_n"
        ]
        == 0.42740724991695345
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_trust_candidate_residual_gate_passed"
        ]
        is False
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_trust_schedule_candidate_final_residual_n"
        ]
        == 0.4274072499174437
    )
    assert stages["g1_solver_closure"]["summary"][
        "active_set_ls_trust_schedule_candidate_active_row_count_schedule"
    ] == [8, 16, 32]
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_trust_tangent_fd_jvp_fd_consistent"
        ]
        is True
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_ls_trust_tangent_fd_jvp_max_relative_inf_error"
        ]
        == 5.0e-14
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_minimax_trust_candidate_final_residual_n"
        ]
        == 0.42740724991695345
    )
    assert (
        stages["g1_solver_closure"]["summary"][
            "active_set_minimax_trust_candidate_best_linear_active_inf_improvement_n"
        ]
        == 1.1784706543949142e-10
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
        "implementation/phase1/release_evidence/productization/g1_true_newton_full_load_checkpoint_candidate_status.json"
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
