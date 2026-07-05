from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from copy import deepcopy


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_consistent_newton_full_load_checkpoint_candidate_runner", SCRIPT_PATH
)
assert SPEC is not None
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _g1_lane_payload(*, action_id: str | None = runner.RUNNER_ID) -> dict:
    actions = []
    if action_id is not None:
        actions.append(
            {
                "id": action_id,
                "reason": "row_only_largest_rows_operator_exhausted",
                "preferred_candidate_generator": runner.PREFERRED_GENERATOR,
                "required_load_scale": 1.0,
                "highest_observed_load_scale": 0.656,
                "highest_observed_gap_to_required_load_scale": 0.344,
                "workspace_candidate_count": 357,
                "workspace_full_load_candidate_count": 0,
                "workspace_scan_root": "implementation/phase1/release_evidence/productization",
                "cause_narrowing_primary_next_lane": runner.PRIMARY_NEXT_LANE,
                "cause_narrowing_row_only_correction_loop_stopped": True,
                "cause_narrowing_support_or_link_gap_disfavored": True,
                "cause_narrowing_support_or_link_row_gap_disfavored": True,
                "suppressed_retry_action_ids": runner.DISALLOWED_RETRY_ACTION_IDS,
                "rerun_command": (
                    "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                    "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
                ),
            }
        )
    return {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "status": "blocked",
        "contract_pass": False,
        "blockers": [
            "checkpoint_load_scale_below_required_full_load",
            "checkpoint_resolution_no_full_load_candidate",
            "hip_consistency_proof_gate_not_passed",
        ],
        "checkpoint_resolution_gate": {
            "mode": "auto_select",
            "passed": False,
            "required_load_scale": 1.0,
            "highest_observed_load_scale": 0.656,
            "highest_observed_gap_to_required_load_scale": 0.344,
            "full_load_candidate_count": 0,
        },
        "lane_next_actions": actions,
    }


def _cause_narrowing_payload() -> dict:
    return {
        "schema_version": "g1-f2g-f2h-cause-narrowing-status.v1",
        "status": "ready",
        "contract_pass": True,
        "evidence_signals": {
            "support_or_link_row_gap_disfavored": True,
            "row_only_correction_loop_stopped_by_global_connectivity": True,
            "global_connectivity_primary_next_lane": runner.PRIMARY_NEXT_LANE,
        },
        "decision_record": {
            "schema_version": "g1-f2g-f2h-next-lane-decision.v1",
            "primary_next_lane": runner.PRIMARY_NEXT_LANE,
            "stop_row_only_support_or_elastic_link_correction_loop": True,
            "required_next_receipts": [
                "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
                "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
            ],
        },
    }


def _hip_probe_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "partial",
        "source_commit_sha": "fixture-hip-proof",
        "rocm_hip_required": True,
        "execution_mode": "hip_required_direct_probe_no_cpu_fallback",
        "consistent_residual_jacobian_newton_gate_passed": False,
        "cpu_diagnostic_assembler_used": False,
        "production_hip_residual_jacobian_path": True,
        "load_scale": 1.0,
        "hip_direct_probe": {
            "executed": True,
            "status": "partial",
            "direct_residual_newton_ready": False,
            "direct_residual_summary": {
                "base_direct_residual_inf_n": 5.584111205195331,
                "base_direct_relative_residual_inf": 0.0004222127955919827,
                "final_direct_residual_inf_n": 5.571832446441612,
                "final_direct_relative_residual_inf": 0.0004212844027163208,
                "output_final_checkpoint": {
                    "written": True,
                    "path": (
                        "implementation/phase1/release_evidence/productization/"
                        "mgt_residual_jacobian_step15_material_active_set_ls_rows32_child_direct_candidate.npz"
                    ),
                    "load_scale": 1.0,
                    "direct_residual_inf_n": 5.571832446441612,
                },
            },
            "gate_assessment": {
                "direct_residual_gate_passed": False,
                "relative_increment_gate_passed": True,
                "full_load_closure_passed": True,
                "consistent_residual_jacobian_newton_passed": False,
                "material_newton_breadth_passed": False,
                "fallback_zero_passed": True,
            },
            "matrix_free_global_krylov": {
                "hip_krylov_solver_used": True,
                "jvp_rows_retained": True,
                "jvp_row_count": 3,
                "accepted_state_refresh_cpu_used": False,
                "accepted_state_tangent_refresh_hip_used": True,
            },
            "current_tangent_residual_row_correction": {
                "attempted": True,
                "promoted_to_final_state": False,
                "batch_replay_backend": "hip_full_residual",
                "accepted_state_refresh_cpu_used": False,
                "accepted_state_tangent_refresh_hip_used": True,
            },
        },
        "live_g1_assembly_contract": {
            "uses_assembly_result_contract": True,
            "assembly_result_schema": "g1-assembly-result.v1",
            "residual_formula": "F_internal_minus_F_external",
            "residual_source": "physical_direct_residual",
            "tangent_definition": "dR_du_consistent",
            "required_fields_present": True,
            "required_fields": [
                "residual_free",
                "tangent_free",
                "internal_forces",
                "external_forces",
                "material_state_next",
                "metrics",
            ],
            "fixed_point_residual_promoted_to_physical": False,
            "regularized_fixed_point_substitute": False,
        },
        "blockers": [
            "consistent_residual_jacobian::consistent_residual_jacobian_newton_not_proven",
            "production_rocm_hip_residual_jvp_worker::consistent_residual_jacobian_newton_gate_not_passed",
        ],
        "production_rocm_hip_residual_jvp_worker": {
            "schema_version": "production-rocm-hip-residual-jvp-worker-contract.v1",
            "worker_id": runner.PRIMARY_NEXT_LANE,
            "ready": False,
            "status": "blocked",
            "blockers": ["consistent_residual_jacobian_newton_gate_not_passed"],
            "residual_jvp_worker_path_ready": True,
            "residual_jvp_worker_path_blockers": [],
            "g1_closure_gate_ready": False,
            "g1_closure_gate_blockers": [
                "consistent_residual_jacobian_newton_gate_not_passed"
            ],
            "terminal_gate_partition": {
                "checkpoint_gate": {
                    "load_scale": 0.656,
                    "full_load_candidate": False,
                    "gap_to_full_load": 0.344,
                },
                "direct_residual_gate": {
                    "passed": False,
                    "relative_increment_gate_passed": True,
                },
            },
        },
    }


def _assembly_contract_seed_payload() -> dict:
    return {
        "schema_version": "g1-assembly-contract-seed-report.v1",
        "status": "ready",
        "contract_pass": True,
        "promotes_g1_closure": False,
        "g1_closure_claim": False,
        "phase_covered": "phase1_phase2_cpu_seed_contract_and_newton_parity",
        "residual_formula": "F_internal_minus_F_external",
        "fixed_point_residual_promoted_to_physical": False,
        "regularized_fixed_point_substitute": False,
        "cpu_seed_consistent_newton_gate_passed": True,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "case_count": 2,
    }


def _true_newton_load_sweep_payload() -> dict:
    return {
        "schema_version": "g1-true-newton-load-sweep-status.v1",
        "status": "partial",
        "contract_pass": True,
        "evidence_closure_pass": False,
        "promotes_g1_closure": False,
        "required_load_scale": 1.0,
        "max_attempted_load_scale": 1.0,
        "max_newton_steps": 4,
        "residual_gate_n": 5.0e-4,
        "full_load_attempted": True,
        "full_load_true_newton_residual_descent_observed": True,
        "full_load_true_newton_residual_gate_passed": False,
        "full_load_true_newton_final_residual_n": 716.2398790963002,
        "full_load_true_newton_total_reduction_ratio": 0.95,
        "rows": [
            {
                "load_scale": 0.75,
                "status": "ready",
                "uses_real_mgt_model": True,
                "true_newton_steps": 4,
                "true_newton_initial_residual_n": 15000.0,
                "true_newton_final_residual_n": 537.1799036113136,
                "true_newton_total_reduction_ratio": 0.96,
                "true_newton_residual_descent_observed": True,
                "true_newton_residual_gate_passed": False,
            },
            {
                "load_scale": 1.0,
                "status": "ready",
                "uses_real_mgt_model": True,
                "true_newton_steps": 4,
                "true_newton_initial_residual_n": 20000.0,
                "true_newton_final_residual_n": 716.2398790963002,
                "true_newton_total_reduction_ratio": 0.95,
                "true_newton_residual_descent_observed": True,
                "true_newton_residual_gate_passed": False,
            },
        ],
        "blockers": [
            "full_load_true_newton_residual_gate_not_passed",
            "full_load_checkpoint_not_created_by_true_newton_sweep",
            "production_rocm_hip_not_executed_by_true_newton_sweep",
        ],
        "claim_boundary": "non-promoting fixture",
    }


def _true_newton_checkpoint_candidate_payload() -> dict:
    return {
        "schema_version": "g1-true-newton-full-load-checkpoint-candidate-status.v1",
        "status": "candidate_created",
        "contract_pass": True,
        "evidence_closure_pass": False,
        "promotes_g1_closure": False,
        "required_load_scale": 1.0,
        "max_newton_steps": 12,
        "residual_gate_n": 5.0e-4,
        "true_newton_candidate": {
            "status": "ready",
            "reason_code": "max_steps",
            "steps": 12,
            "initial_residual_n": 22323.093943383923,
            "final_residual_n": 464.56223807569995,
            "total_reduction_ratio": 0.9791882547360113,
            "monotonic_residual_decrease": True,
            "residual_gate_passed": False,
            "stop_reason": "max_steps",
        },
        "checkpoint_candidate": {
            "written": True,
            "path": "implementation/phase1/release_evidence/productization/"
            "g1_true_newton_full_load_checkpoint_candidate.npz",
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "dof_count": 78282,
            "free_dof_count": 39141,
            "direct_residual_inf_n": 464.56223807569995,
            "residual_gate_passed": False,
            "promotes_g1_closure": False,
        },
        "checkpoint_written": True,
        "checkpoint_schema_pass": True,
        "checkpoint_load_scale_pass": True,
        "full_load_true_newton_residual_descent_observed": True,
        "full_load_true_newton_residual_gate_passed": False,
        "blockers": [
            "full_load_true_newton_checkpoint_residual_gate_not_passed",
            "production_rocm_hip_not_executed_by_true_newton_checkpoint_candidate",
        ],
        "claim_boundary": "checkpoint candidate fixture; not a G1 closure",
    }


def _adaptive_all_components_frontier_payload() -> dict:
    return {
        "schema_version": "g1-adaptive-regularization-reference-newton.v1",
        "status": "review",
        "reason_code": "no_candidate_descent",
        "promotes_g1_closure": False,
        "frame_tangent_source": "force_based_residual_tangent",
        "shell_pressure_load_path_policy": "all_components",
        "summary": {
            "initial_residual_n": 0.5698763332807477,
            "final_residual_n": 0.4278304040181992,
            "total_reduction_ratio": 0.24925746336016033,
            "residual_gate_passed": False,
            "stop_reason": "no_candidate_descent",
            "steps_taken": 38,
        },
        "output_final_checkpoint": {
            "written": True,
            "path": "implementation/phase1/release_evidence/productization/"
            "g1_adaptive_fixed_signed_all_components_from_structural_60step_diagnostic.npz",
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "direct_residual_inf_n": 0.4278304040181992,
            "residual_gate_passed": False,
            "frame_tangent_source": "force_based_residual_tangent",
            "shell_pressure_load_path_policy": "all_components",
            "promotes_g1_closure": False,
            "claim_boundary": "adaptive all-components fixture; not a G1 closure",
        },
    }


def _shell_hotspot_tangent_fd_jvp_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "ready",
        "base_residual_inf_n": 0.4278304040181992,
        "residual_hotspot_tangent_fd_jvp_component_filter": (
            "shell_bending_drilling"
        ),
        "residual_hotspot_tangent_fd_jvp_rows": [
            {
                "evaluated": True,
                "dominant_component": "shell_bending_drilling",
                "global_dof": 46694,
                "free_row": 33806,
                "dof": "uz",
                "relative_inf_error": 7.82988821999408e-14,
                "selected_row_relative_error": 3.61610487797195e-14,
                "action_cosine": 1.0,
            }
        ],
    }


def _active_set_ls_trust_tangent_fd_jvp_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "ready",
        "residual_jacobian_consistency_ready": True,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "checkpoint": {
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
            )
        },
        "load_scale": 1.0,
        "base_residual_inf_n": 0.42740724991695345,
        "base_relative_residual_inf": 0.42740724991695345,
        "relative_error_threshold": 0.25,
        "cosine_threshold": 0.8,
        "direction_rows": [
            {
                "direction": "top_residual_sign",
                "evaluated": True,
                "relative_inf_error": 5.0e-14,
                "relative_l2_error": 4.0e-14,
                "action_cosine": 1.0,
            },
            {
                "direction": "deterministic_free_sample",
                "evaluated": True,
                "relative_inf_error": 7.0e-15,
                "relative_l2_error": 8.0e-15,
                "action_cosine": 0.9999999999999998,
            },
        ],
    }


def _true_newton_from_active_set_payload() -> dict:
    return {
        "schema_version": "g1-true-newton-reference-candidate.v1",
        "status": "review",
        "reason_code": "line_search_no_descent",
        "promotes_g1_closure": False,
        "initial_checkpoint_npz": (
            "implementation/phase1/release_evidence/productization/"
            "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
        ),
        "frame_tangent_source": "force_based_residual_tangent",
        "regularization": {"mode": "relative_diagonal_shift", "mu": 0.03},
        "true_newton_candidate": {
            "steps": 1,
            "initial_residual_n": 0.42740724991695345,
            "final_residual_n": 0.42740724991695345,
            "residual_gate_passed": False,
            "stop_reason": "line_search_no_descent",
        },
        "modified_newton_baseline": {
            "final_residual_n": 0.42740724991695345,
            "residual_gate_passed": False,
            "stop_reason": "line_search_no_descent",
        },
        "true_newton_faster_than_modified": False,
        "summary": {
            "initial_residual_n": 0.42740724991695345,
            "final_residual_n": 0.42740724991695345,
            "residual_gate_passed": False,
            "stop_reason": "line_search_no_descent",
            "directional_residual_jvp_contract": {
                "direction_solve_contracts": {
                    "max_regularized_linear_solve_relative_inf": (
                        3.197442310920451e-14
                    ),
                    "max_unregularized_tangent_plus_residual_relative_inf": (
                        0.4278578064844439
                    ),
                    "max_regularization_action_vs_residual_inf": (
                        0.4278578064844431
                    ),
                    "max_jvp_minus_unregularized_tangent_action_relative_inf": (
                        4.088178091005261
                    ),
                    "dominant_jvp_gap_row_set": {
                        "dominant_jvp_minus_unregularized_tangent_action_rows": [
                            {
                                "global_dof": 74216,
                                "node_id": 12385,
                                "dof_label": "UZ",
                                "value": 4.088178091005261,
                            }
                        ],
                        "dominant_jvp_gap_component_breakdown": {
                            "rows": [
                                {
                                    "dominant_component_tangent_gap": "frame",
                                }
                            ]
                        },
                    },
                }
            },
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_true_newton_from_active_set_ls_trust_mu_0p03_candidate.npz"
            ),
            "direct_residual_inf_n": 0.42740724991695345,
            "residual_gate_passed": False,
        },
    }


def _true_newton_from_active_set_service_tangent_payload() -> dict:
    payload = deepcopy(_true_newton_from_active_set_payload())
    payload["frame_tangent_source"] = "service_material_plus_geometric_delta"
    payload["true_newton_candidate"]["stop_reason"] = "line_search_no_descent"
    payload["modified_newton_baseline"]["stop_reason"] = "line_search_no_descent"
    contracts = payload["summary"]["directional_residual_jvp_contract"][
        "direction_solve_contracts"
    ]
    contracts["max_unregularized_tangent_plus_residual_relative_inf"] = (
        0.4278579302525935
    )
    contracts["max_regularization_action_vs_residual_inf"] = 0.42785793025259444
    contracts["max_jvp_minus_unregularized_tangent_action_relative_inf"] = (
        4.088231545444302
    )
    dominant_gap = contracts["dominant_jvp_gap_row_set"]
    dominant_gap["dominant_jvp_minus_unregularized_tangent_action_rows"][0] = {
        "global_dof": 8516,
        "node_id": 1420,
        "dof_label": "UZ",
        "value": -4.088231545444302,
    }
    payload["output_final_checkpoint"]["path"] = (
        "implementation/phase1/release_evidence/productization/"
        "g1_true_newton_from_active_set_ls_trust_service_tangent_mu_0p03_candidate.npz"
    )
    return payload


def _frame_tangent_fd_epsilon_sweep_payload() -> dict:
    return {
        "schema_version": "g1-frame-tangent-fd-epsilon-sweep-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "frame_tangent_source": "force_based_residual_tangent",
        "summary": {
            "residual_inf_n": 0.42740724991695345,
            "direction_inf_m": 4.881411123457379e-09,
            "frame_force_inf_n": 239015.45965449896,
            "frame_tangent_action_inf_n": 0.38190455418218505,
            "default_jvp_eps": 1.0e-6,
            "default_eps_row": {
                "eps": 1.0e-6,
                "max_frame_jvp_minus_tangent_action_inf_n": (
                    4.088178091005261
                ),
                "max_frame_jvp_minus_tangent_action_relative_inf": (
                    4.088178091005261
                ),
            },
            "best_eps_row": {
                "eps": 1.0e-3,
                "max_frame_jvp_minus_tangent_action_inf_n": (
                    0.003379869645939948
                ),
                "max_frame_jvp_minus_tangent_action_relative_inf": (
                    0.003379869645939948
                ),
            },
            "fd_step_sensitivity_observed": True,
            "default_eps_artifact_likely": True,
            "default_to_best_gap_ratio": 1209.566751948103,
        },
    }


def _true_newton_from_active_set_mu_sweep_payload() -> dict:
    return {
        "schema_version": "g1-true-newton-mu-sweep-from-active-set-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "frame_tangent_source": "force_based_residual_tangent",
        "regularization_mode": "relative_diagonal_shift",
        "summary": {
            "initial_residual_inf_n": 0.42740724991695345,
            "evaluated_mu_count": 11,
            "factorable_mu_count": 11,
            "descent_observed": False,
            "best_mu": 0.03,
            "best_effective_shift": 87557238.6929269,
            "best_direction_sign": "forward",
            "best_residual_inf_n": 0.427407250212255,
            "best_improvement_inf_n": -2.9530156098189764e-10,
            "best_reduction_ratio": -6.909139486653485e-10,
            "best_direction_inf_m": 4.881411123457379e-09,
            "best_unregularized_tangent_plus_residual_relative_inf": (
                0.4278578064844439
            ),
            "best_regularization_action_vs_residual_inf": 0.4278578064844431,
        },
    }


def _active_set_load_parameter_payload(*, tiny_trust: bool = False) -> dict:
    if tiny_trust:
        load_trust = 1.0e-5
        best_load = 0.99999
        best_residual = 0.4274029760383601
        best_improvement = 4.273878593363811e-06
        descent = True
        linear_delta = -1.0e-5
        restored_residual = 0.42740796265036174
        restored_improvement = -7.127334082923653e-07
    else:
        load_trust = 0.02
        best_load = 0.995
        best_residual = 66.12257730630517
        best_improvement = -65.69517005638822
        descent = False
        linear_delta = -0.02
        restored_residual = 0.42811959570077285
        restored_improvement = -0.0007123457838194014
    return {
        "schema_version": "g1-active-set-load-parameter-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "load_trust_radius": load_trust,
        "displacement_trust_radius_m": 1.0e-8,
        "summary": {
            "initial_residual_inf_n": 0.42740724991695345,
            "load_derivative_inf_n_per_load": 13225.821821352838,
            "best_linear_active_row_count": 8,
            "best_linear_delta_load_scale": linear_delta,
            "best_linear_active_improvement_inf_n": (
                4.274190345765483e-06 if tiny_trust else 0.008548145117847072
            ),
            "actual_replay_attempted": True,
            "actual_replay_descent_observed": descent,
            "best_actual_replay_load_scale": best_load,
            "best_actual_replay_residual_inf_n": best_residual,
            "best_actual_replay_improvement_inf_n": best_improvement,
            "best_actual_replay_residual_gate_passed": False,
            "restored_full_load_replay_attempted": True,
            "restored_full_load_descent_observed": False,
            "best_restored_full_load_residual_inf_n": restored_residual,
            "best_restored_full_load_improvement_inf_n": restored_improvement,
            "best_restored_full_load_residual_gate_passed": False,
        },
    }


def _active_frontier_residual_ownership_payload() -> dict:
    return {
        "schema_version": "g1-active-frontier-residual-ownership-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "frame_tangent_source": "force_based_residual_tangent",
        "shell_pressure_load_path_policy": "all_components",
        "summary": {
            "top_residual_inf_n": 0.42740724991695345,
            "residual_gate_passed": False,
            "top_row_global_dof": 13652,
            "top_row_node_id": 2276,
            "top_row_node_index": 2275,
            "top_row_dof_label": "UZ",
            "top_row_residual_n": -0.42740724991695345,
            "top_row_internal_sum_n": 0.14246908341638154,
            "top_row_inferred_external_load_n": 0.569876333333335,
            "top_row_dominant_internal_component": "shell_bending_drilling",
            "top_row_balance_driver": "external_load_balance",
            "top_row_load_derivative_n_per_load": -0.5698763333333301,
            "dominant_internal_component_counts": {
                "frame": 5,
                "shell_bending_drilling": 11,
            },
            "balance_driver_counts": {
                "component_external_cancellation": 2,
                "external_load_balance": 9,
                "frame_internal_force": 2,
                "shell_bending_drilling_internal_force": 3,
            },
            "load_derivative_inf_n_per_load": 13225.821821352838,
        },
        "claim_boundary": "fixture residual ownership; not a G1 closure",
    }


def _active_frontier_shell_load_neighborhood_payload() -> dict:
    return {
        "schema_version": "g1-active-frontier-shell-load-neighborhood-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "frame_tangent_source": "force_based_residual_tangent",
        "shell_pressure_load_path_policy": "all_components",
        "summary": {
            "top_residual_inf_n": 0.42740724991695345,
            "shell_helper_row_count": 11,
            "surface_load_diagnostics_evaluated": True,
            "internal_element_diagnostics_evaluated": True,
            "external_minus_reference_shell_load_inf_n": 1.1102230246251565e-16,
            "component_minus_reconstructed_shell_inf_n": 4.967946054534877e-10,
            "component_minus_reconstructed_bending_inf_n": 4.967946054534877e-10,
            "top_row_node_id": 2276,
            "top_row_dof": "uz",
            "top_row_external_load_n": 0.569876333333335,
            "top_row_reference_shell_load_reconstructed_n": 0.5698763333333349,
            "top_row_required_reference_shell_load_scale_for_zero_row_residual": (
                0.25000000014572954
            ),
            "top_row_shell_internal_to_reference_load_scale": (
                0.2500000001903663
            ),
            "top_row_incident_surface_element_count": 1,
            "top_row_surface_component_element_count": 1,
            "top_row_surface_component_frame_connected_node_count": 0,
            "top_row_surface_component_restrained_translation_dof_count": 0,
            "top_row_surface_component_free_pressure_resultant": True,
            "top_incident_element": {
                "elem_id": 25880,
                "target_dof_reference_shell_load_n": 0.5698763333333349,
                "target_dof_bending_internal_force_n": 0.14246908344181897,
            },
        },
        "claim_boundary": "fixture shell load neighborhood; not a G1 closure",
    }


def _active_frontier_shell_policy_replay_payload() -> dict:
    return {
        "schema_version": "g1-active-frontier-shell-policy-replay-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "frame_tangent_source": "force_based_residual_tangent",
        "summary": {
            "anchor_global_dof": 13652,
            "anchor_reduced_index": 11024,
            "baseline_policy": "all_components",
            "baseline_residual_inf_n": 0.42740724991695345,
            "best_policy": "attached_components_only",
            "best_residual_inf_n": 0.3818403374023447,
            "best_improvement_inf_n": 0.04556691251460876,
            "best_reduction_ratio": 0.10661239958719126,
            "best_residual_gate_passed": False,
            "structural_or_attached_policy_descent_observed": True,
            "best_policy_pressure_filter_enabled": True,
            "best_policy_pressure_suppressed_surface_element_count": 2,
            "ready_policy_count": 3,
        },
        "claim_boundary": "fixture shell policy replay; not a G1 closure",
    }


def _active_frontier_shell_policy_linearized_active_set_payload() -> dict:
    return {
        "schema_version": (
            "g1-active-frontier-shell-policy-linearized-active-set-probe.v1"
        ),
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "frame_tangent_source": "force_based_residual_tangent",
        "shell_pressure_load_path_policy": "structural_components_only",
        "summary": {
            "base_residual_inf_n": 0.3818403374023447,
            "base_relative_residual_inf": 2.8870821228351682e-05,
            "base_residual_gate_passed": False,
            "evaluated_active_row_count_schedule": [8, 16, 32],
            "best_active_row_count": 8,
            "best_linear_active_residual_before_inf_n": 0.3818403374023447,
            "best_linear_active_residual_after_inf_n": 7.245315458703772e-13,
            "best_linear_active_improvement_inf_n": 0.38184033740162016,
            "best_linear_active_reduction_ratio": 0.9999999999981025,
            "linearized_active_descent_observed": True,
            "direct_replay_attempted": False,
            "direct_replay_required_for_candidate": True,
        },
        "claim_boundary": "fixture linearized active-set probe; not a G1 closure",
    }


def _shell_hotspot_diagonal_sweep_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "ready",
        "base_residual_inf_n": 0.4278304040181992,
        "residual_hotspot_diagonal_newton_sweep": {
            "enabled": True,
            "evaluated": True,
            "component_filter": "shell_bending_drilling",
            "selected_hotspot_row_count": 8,
            "base_direct_residual_inf_n": 0.4278304040181992,
            "correction_inf_m": 2.1677838459098335e-10,
            "best_candidate": {
                "alpha": 0.03125,
                "free_dof_set_stable": True,
                "direct_residual_inf_n": 0.4278508811240626,
                "improvement_inf_n": -2.0477105863392353e-05,
                "relative_increment": 1.2638244230809586e-10,
                "residual_gate_passed": False,
                "relative_increment_gate_passed": True,
            },
            "best_gate_eligible_candidate": {
                "alpha": 0.03125,
                "direct_residual_inf_n": 0.4278508811240626,
            },
        },
    }


def _global_tangent_scaled_sweep_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "ready",
        "base_residual_inf_n": 0.4278304040181992,
        "residual_global_tangent_newton_sweep": {
            "enabled": True,
            "evaluated": True,
            "solver": "scipy_lsmr_limited_cpu_diagnostic",
            "scaling": {
                "mode": "row_col_inf",
                "row_scale_min": 3.7978767960241835e-15,
                "row_scale_max": 1.0,
                "col_scale_min": 3.7978767960241835e-15,
                "col_scale_max": 1.0,
            },
            "descent_observed": False,
            "base_direct_residual_inf_n": 0.4278304040181992,
            "direction_inf_m": 0.00035488155989295137,
            "linear_residual_inf_n": 0.4278305011820284,
            "linear_relative_residual_inf": 0.4278305011820284,
            "solver_stats": {
                "iteration_count": 128,
                "condition_estimate": 231288.68661634796,
            },
            "best_candidate": {
                "alpha": 0.00390625,
                "free_dof_set_stable": True,
                "direct_residual_inf_n": 0.42783040426657654,
                "improvement_inf_n": -2.483773187123006e-10,
                "relative_increment": 2.5862125480131654e-05,
                "residual_gate_passed": False,
                "relative_increment_gate_passed": True,
            },
            "best_gate_eligible_candidate": {
                "alpha": 0.00390625,
                "direct_residual_inf_n": 0.42783040426657654,
            },
        },
    }


def _residual_norm_gradient_tiny_sweep_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "ready",
        "base_residual_inf_n": 0.4278304040181992,
        "residual_norm_gradient_sweep": {
            "enabled": True,
            "evaluated": True,
            "direction": "negative_residual_norm_gradient",
            "base_direct_residual_inf_n": 0.4278304040181992,
            "base_direct_residual_l2_n": 1.3797695946223492,
            "trust_radius_m": 1.0e-15,
            "gradient_inf": 117956710584802.14,
            "gradient_l2": 205241130799474.28,
            "inf_descent_observed": False,
            "l2_descent_observed": True,
            "best_inf_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 0.4278304040181992,
                "direct_residual_l2_n": 1.2159739821333575,
                "improvement_inf_n": 0.0,
                "improvement_l2_n": 0.16379561248899166,
                "relative_improvement_l2": 0.11871229307225273,
                "residual_gate_passed": False,
                "relative_increment_gate_passed": True,
            },
            "best_l2_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 0.4278304040181992,
                "direct_residual_l2_n": 1.2159739821333575,
                "improvement_inf_n": 0.0,
                "improvement_l2_n": 0.16379561248899166,
                "relative_improvement_l2": 0.11871229307225273,
                "residual_gate_passed": False,
                "relative_increment_gate_passed": True,
            },
            "best_gate_eligible_inf_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 0.4278304040181992,
            },
        },
    }


def _active_set_ls_sweep_payload() -> dict:
    return {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "status": "ready",
        "base_residual_inf_n": 0.4278304040181992,
        "residual_active_set_least_squares_sweep": {
            "enabled": True,
            "evaluated": True,
            "direction": "active_set_global_least_squares",
            "selected_hotspot_row_count": 8,
            "base_direct_residual_inf_n": 0.4278304040181992,
            "base_active_residual_inf_n": 0.4278304040181992,
            "full_inf_descent_observed": True,
            "active_inf_descent_observed": True,
            "direction_inf_m": 3.160709424631079e-13,
            "active_linear_residual_inf_n": 0.42740724992626605,
            "solver_stats": {
                "iteration_count": 3,
                "condition_estimate": 2.0365056657192695,
            },
            "best_full_inf_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 0.4274072503950392,
                "active_residual_inf_n": 0.4274072503950392,
                "improvement_inf_n": 0.000423153623160033,
                "active_improvement_inf_n": 0.000423153623160033,
                "relative_increment": 5.896649554093333e-12,
                "residual_gate_passed": False,
                "relative_increment_gate_passed": True,
            },
            "best_active_inf_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 0.4274072503950392,
                "active_residual_inf_n": 0.4274072503950392,
                "improvement_inf_n": 0.000423153623160033,
                "active_improvement_inf_n": 0.000423153623160033,
            },
            "best_gate_eligible_full_inf_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 0.4274072503950392,
            },
        },
    }


def _active_set_ls_trust_candidate_payload() -> dict:
    return {
        "schema_version": "g1-active-set-ls-trust-candidate.v1",
        "status": "candidate_created",
        "promotes_g1_closure": False,
        "summary": {
            "initial_residual_n": 0.4278304040181992,
            "final_residual_n": 0.42740724991695345,
            "total_reduction_n": 0.0004231541012457707,
            "total_reduction_ratio": 0.0009890697277974904,
            "residual_gate_passed": False,
            "steps_taken": 5,
            "stop_reason": "no_candidate_descent",
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
            ),
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "direct_residual_inf_n": 0.42740724991695345,
            "residual_gate_passed": False,
            "claim_boundary": "active-set candidate fixture",
        },
    }


def _active_frontier_structural_policy_active_set_payload() -> dict:
    payload = deepcopy(_active_set_ls_trust_candidate_payload())
    payload["shell_pressure_load_path_policy"] = "structural_components_only"
    payload["summary"] = {
        "initial_residual_n": 0.12093228075045737,
        "final_residual_n": 0.07205501101467937,
        "total_reduction_n": 0.048877269735777995,
        "total_reduction_ratio": 0.4041714960477451,
        "residual_gate_passed": False,
        "steps_taken": 1,
        "stop_reason": "max_steps",
        "active_row_count_schedule": [8],
    }
    payload["output_final_checkpoint"] = {
        "written": True,
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.npz"
        ),
        "schema": "mgt-direct-residual-newton-state.v1",
        "load_scale": 1.0,
        "direct_residual_inf_n": 0.07205501101467937,
        "residual_gate_passed": False,
        "shell_pressure_load_path_policy": "structural_components_only",
        "claim_boundary": "structural policy active-set fixture",
    }
    payload["runtime_metrics"] = {"total_seconds": 41.4}
    return payload


def _active_frontier_structural_policy_alpha_sweep_payload() -> dict:
    payload = _active_frontier_structural_policy_active_set_payload()
    payload["status"] = "review"
    payload["summary"] = {
        "initial_residual_n": 0.07205501101467937,
        "final_residual_n": 0.07205501101467937,
        "total_reduction_n": 0.0,
        "total_reduction_ratio": 0.0,
        "residual_gate_passed": False,
        "steps_taken": 0,
        "stop_reason": "no_candidate_descent",
        "active_row_count_schedule": [8],
    }
    payload["output_final_checkpoint"]["path"] = (
        "implementation/phase1/release_evidence/productization/"
        "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_alpha_sweep_candidate.npz"
    )
    payload["output_final_checkpoint"]["direct_residual_inf_n"] = (
        0.07205501101467937
    )
    return payload


def _active_frontier_structural_policy_direct_material_replay_payload() -> dict:
    return {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "status": "partial",
        "promotes_g1_closure": False,
        "source_commit_sha": "fixture",
        "base_direct_residual": {
            "load_scale": 1.0,
            "direct_residual_inf_n": 44.08048153349253,
            "fixed_point_receipt_residual_inf_n": 0.07205064005823536,
            "residual_component_breakdown": {
                "component_inf_n": {
                    "frame": 239015.45965449896,
                    "shell_bending_drilling": 239103.9000580624,
                    "shell_membrane": 72233.54910141167,
                },
                "top_row_dominant_component_counts": {
                    "shell_bending_drilling": 14,
                    "shell_membrane": 10,
                },
                "top_rows": [
                    {
                        "global_dof": 13610,
                        "node_index": 2268,
                        "dof": "uz",
                        "residual_n": 44.08048153349253,
                        "external_load_n": 24.332456500000006,
                        "internal_sum_n": 68.41293803349254,
                        "dominant_component": "shell_bending_drilling",
                        "component_values_n": {
                            "shell_bending_drilling": 72301.96203944516,
                            "shell_membrane": -72233.54910141167,
                        },
                    }
                ],
            },
        },
        "final_direct_residual": {
            "direct_residual_inf_n": 44.08048153349253,
            "residual_gate_passed": False,
        },
        "live_g1_assembly_contract": {
            "contract_pass": True,
            "load_scale": 1.0,
            "residual_inf_norm": 44.08048153349253,
        },
        "gate_assessment": {
            "direct_residual_gate_passed": False,
            "consistent_residual_jacobian_newton_passed": False,
            "consistent_residual_jacobian_newton_blockers": [
                "consistent_residual_jacobian_newton_not_proven",
                "state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency",
            ],
            "material_newton_breadth_blockers": [
                "material_newton_breadth_not_proven",
                "state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency",
            ],
        },
        "residual_contract": {
            "consistent_residual_jacobian_newton_gate_passed": False,
            "residual_component_breakdown_included": True,
        },
        "claim_boundary": "state-updated material direct replay fixture",
    }


def _active_frontier_structural_policy_current_component_row_correction_payload() -> dict:
    return {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "status": "partial",
        "promotes_g1_closure": False,
        "source_commit_sha": "fixture",
        "base_direct_residual": {
            "load_scale": 1.0,
            "direct_residual_inf_n": 44.08048153349253,
        },
        "final_direct_residual": {
            "direct_residual_inf_n": 44.08014382294667,
            "residual_gate_passed": False,
            "residual_component_breakdown": {
                "top_rows": [
                    {
                        "global_dof": 13610,
                        "dof": "uz",
                        "residual_n": 44.08014382294667,
                        "dominant_component": "shell_bending_drilling",
                    }
                ]
            },
        },
        "current_tangent_residual_row_correction": {
            "enabled": True,
            "attempted": True,
            "accepted": True,
            "promoted_to_final_state": True,
            "stop_reason": "max_promotions_exhausted",
            "best_gate_eligible_candidate": {
                "target_mode": "current_component_rows",
                "target_row_count": 1,
                "support_column_count": 4,
                "alpha": 1.0,
                "direct_residual_inf_n": 44.08014382294667,
                "improvement_inf_n": 0.0003377105458639562,
                "relative_improvement": 7.661226332279568e-06,
                "relative_increment": 4.78930206438536e-09,
                "residual_gate_passed": False,
                "relative_increment_gate_passed": True,
                "residual_only_assembly": True,
                "batch_alpha_replay": True,
                "residual_batch_backend": "cpu_physical_internal_force_batch",
            },
            "passes": [{"accepted_state_refresh_cpu_used": True}],
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_active_frontier_structural_policy_active_set_current_component_row_correction_candidate.npz"
            ),
            "direct_residual_inf_n": 44.08014382294667,
        },
        "claim_boundary": "current-component row correction fixture",
    }


def _active_frontier_structural_policy_current_component_row_correction_step2_payload() -> dict:
    payload = _active_frontier_structural_policy_current_component_row_correction_payload()
    payload["source_commit_sha"] = "fixture-step2"
    payload["base_direct_residual"]["direct_residual_inf_n"] = 44.08014382294667
    payload["final_direct_residual"]["direct_residual_inf_n"] = 43.816671401648165
    payload["final_direct_residual"]["direct_relative_residual_inf"] = (
        0.0033129639876822666
    )
    payload["final_direct_residual"]["residual_component_breakdown"]["top_rows"][0][
        "residual_n"
    ] = 43.816671401648165
    row = payload["current_tangent_residual_row_correction"]
    row["best_gate_eligible_candidate"]["direct_residual_inf_n"] = 43.816671401648165
    row["best_gate_eligible_candidate"]["improvement_inf_n"] = 0.263472421298502
    row["best_gate_eligible_candidate"]["relative_improvement"] = 0.005977122541994679
    row["passes"] = [
        {
            "previous_direct_residual_inf_n": 44.08014382294667,
            "residual_descent": True,
            "accepted_improvement_inf_n": 0.263472421298502,
            "accepted_relative_improvement": 0.005977122541994679,
            "accepted_state_refresh_cpu_used": True,
        }
    ]
    payload["output_final_checkpoint"]["path"] = (
        "implementation/phase1/release_evidence/productization/"
        "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step2_candidate.npz"
    )
    payload["output_final_checkpoint"]["direct_residual_inf_n"] = 43.816671401648165
    return payload


def _active_frontier_structural_policy_current_component_row_correction_step3_payload() -> dict:
    payload = _active_frontier_structural_policy_current_component_row_correction_step2_payload()
    payload["source_commit_sha"] = "fixture-step3"
    payload["base_direct_residual"]["direct_residual_inf_n"] = 43.816671401648165
    payload["final_direct_residual"]["direct_residual_inf_n"] = 43.816671401648165
    payload["final_direct_residual"]["residual_component_breakdown"]["top_rows"][0][
        "residual_n"
    ] = 43.816671401648165
    row = payload["current_tangent_residual_row_correction"]
    row["accepted"] = False
    row["promoted_to_final_state"] = False
    row["stop_reason"] = "no_residual_descent"
    row["best_gate_eligible_candidate"] = None
    row["best_candidate"] = {
        "target_mode": "current_component_rows",
        "target_row_count": 1,
        "support_column_count": 4,
        "alpha": 0.03125,
        "direct_residual_inf_n": 43.883829113147186,
        "improvement_inf_n": -0.06715771149902139,
        "relative_improvement": -0.0015326977004578046,
        "relative_increment": 3.333726916654414e-10,
        "residual_gate_passed": False,
        "relative_increment_gate_passed": True,
        "residual_only_assembly": True,
        "batch_alpha_replay": True,
        "residual_batch_backend": "cpu_physical_internal_force_batch",
    }
    row["passes"] = [
        {
            "previous_direct_residual_inf_n": 43.816671401648165,
            "residual_descent": False,
            "accepted_state_refresh_cpu_used": False,
        }
    ]
    payload["output_final_checkpoint"] = {
        "written": False,
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step3_candidate.npz"
        ),
        "reason": "no_residual_descent",
        "direct_residual_inf_n": 43.816671401648165,
    }
    return payload


def _active_frontier_structural_policy_residual_ownership_payload() -> dict:
    payload = _active_frontier_residual_ownership_payload()
    payload["checkpoint_npz"] = (
        "implementation/phase1/release_evidence/productization/"
        "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.npz"
    )
    payload["shell_pressure_load_path_policy"] = "structural_components_only"
    payload["summary"] = {
        "top_residual_inf_n": 0.07205501101467937,
        "residual_gate_passed": False,
        "top_row_global_dof": 13641,
        "top_row_node_id": 2274,
        "top_row_node_index": 2273,
        "top_row_dof_label": "RX",
        "top_row_residual_n": -0.07205501101467937,
        "top_row_internal_sum_n": -0.07205501101467937,
        "top_row_inferred_external_load_n": 0.0,
        "top_row_dominant_internal_component": "shell_bending_drilling",
        "top_row_balance_driver": "shell_bending_drilling_internal_force",
        "top_row_load_derivative_n_per_load": 0.0,
        "dominant_internal_component_counts": {
            "frame": 11,
            "shell_bending_drilling": 13,
        },
        "balance_driver_counts": {
            "component_external_cancellation": 1,
            "external_load_balance": 2,
            "frame_internal_force": 9,
            "shell_bending_drilling_internal_force": 12,
        },
        "load_derivative_inf_n_per_load": 13225.821821352838,
    }
    payload["claim_boundary"] = "structural policy residual ownership fixture"
    return payload


def _active_frontier_structural_policy_linearized_after_two_step_payload() -> dict:
    payload = _active_frontier_shell_policy_linearized_active_set_payload()
    payload["checkpoint_npz"] = (
        "implementation/phase1/release_evidence/productization/"
        "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.npz"
    )
    payload["summary"] = {
        "base_residual_inf_n": 0.07205501101467937,
        "base_relative_residual_inf": 5.4480554772287545e-06,
        "base_residual_gate_passed": False,
        "evaluated_active_row_count_schedule": [8, 16, 32],
        "best_active_row_count": 8,
        "best_linear_active_residual_before_inf_n": 0.07205501101467937,
        "best_linear_active_residual_after_inf_n": 3.396605913197348e-13,
        "best_linear_active_improvement_inf_n": 0.07205501101433971,
        "best_linear_active_reduction_ratio": 0.9999999999952861,
        "linearized_active_descent_observed": True,
        "direct_replay_attempted": False,
        "direct_replay_required_for_candidate": True,
    }
    payload["claim_boundary"] = "linearized after two-step fixture"
    return payload


def _active_frontier_structural_policy_shell_rotation_candidate_payload() -> dict:
    return {
        "schema_version": "g1-active-frontier-shell-rotation-row-probe.v1",
        "status": "ready",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "shell_pressure_load_path_policy": "structural_components_only",
        "summary": {
            "base_residual_inf_n": 0.054041258250588475,
            "base_relative_residual_inf": 4.086041607133633e-06,
            "base_residual_gate_passed": False,
            "selected_rotation_row_count": 4,
            "evaluated_jvp_row_count": 4,
            "fd_consistent": True,
            "max_selected_row_relative_error": 7.427605682003617e-14,
            "max_relative_inf_error": 5.184120475416087e-13,
            "min_action_cosine": 0.9999999999999999,
            "correction_inf_rad": 3.342097668570392e-10,
            "best_direct_residual_inf_n": 0.04728610099315822,
            "best_improvement_inf_n": 0.006755157257430255,
            "direct_descent_observed": True,
            "best_residual_gate_passed": False,
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
            ),
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "direct_residual_inf_n": 0.04728610099315822,
            "residual_gate_passed": False,
            "shell_pressure_load_path_policy": "structural_components_only",
            "best_alpha": 0.125,
            "accepted_iteration_count": 1,
            "claim_boundary": "shell rotation row fixture",
        },
        "claim_boundary": "fixture shell rotation row candidate; not a G1 closure",
    }


def _active_frontier_structural_policy_shell_rotation_no_descent_payload() -> dict:
    payload = _active_frontier_structural_policy_shell_rotation_candidate_payload()
    payload["summary"] = {
        **payload["summary"],
        "base_residual_inf_n": 0.04728610099315822,
        "base_relative_residual_inf": 3.575286408048494e-06,
        "max_selected_row_relative_error": 1.0560838848108246e-13,
        "correction_inf_rad": 2.9243354614767377e-10,
        "best_direct_residual_inf_n": 0.04895619781939331,
        "best_improvement_inf_n": -0.0016700968262350901,
        "direct_descent_observed": False,
    }
    payload["output_final_checkpoint"] = {
        **payload["output_final_checkpoint"],
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_active_frontier_structural_policy_shell_rotation_row_third_candidate.npz"
        ),
        "direct_residual_inf_n": 0.04728610099315822,
        "best_alpha": 0.0,
        "accepted_iteration_count": 0,
    }
    payload["claim_boundary"] = "fixture shell rotation no-descent probe"
    return payload


def _active_frontier_structural_policy_shell_rotation_ownership_payload() -> dict:
    payload = _active_frontier_residual_ownership_payload()
    payload["checkpoint_npz"] = (
        "implementation/phase1/release_evidence/productization/"
        "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
    )
    payload["shell_pressure_load_path_policy"] = "structural_components_only"
    payload["summary"] = {
        "top_residual_inf_n": 0.04728610099315822,
        "residual_gate_passed": False,
        "top_row_global_dof": 46695,
        "top_row_node_id": 7783,
        "top_row_node_index": 7782,
        "top_row_dof_label": "RX",
        "top_row_residual_n": -0.04728610099315822,
        "top_row_internal_sum_n": -0.04728610099315822,
        "top_row_inferred_external_load_n": 0.0,
        "top_row_dominant_internal_component": "shell_bending_drilling",
        "top_row_balance_driver": "shell_bending_drilling_internal_force",
        "top_row_load_derivative_n_per_load": 0.0,
        "dominant_internal_component_counts": {
            "frame": 6,
            "shell_bending_drilling": 18,
        },
        "balance_driver_counts": {
            "external_load_balance": 2,
            "frame_internal_force": 5,
            "shell_bending_drilling_internal_force": 17,
        },
        "load_derivative_inf_n_per_load": 13225.821821352838,
    }
    payload["claim_boundary"] = "fixture shell rotation ownership"
    return payload


def _sparse_direct_scaled_lsmr_frontier_payload() -> dict:
    return {
        "schema_version": "g1-mgt-sparse-direct-physical-line-search-smoke.v1",
        "status": "ready",
        "reason_code": "PASS",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "resource_usage": {
            "checkpoint": {
                "checkpoint_applied": True,
                "checkpoint_npz": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
                ),
                "checkpoint_direct_residual_inf_n": 0.04728610099315822,
                "checkpoint_residual_gate_passed": False,
                "checkpoint_promotes_g1_closure": False,
            }
        },
        "jvp_parity": {"pass": True},
        "assembled_tangent_parity": {
            "pass": True,
            "max_relative_error": 7.863775071614314e-12,
        },
        "direction_solve_comparison": {
            "scaled_lsmr": {
                "status": "ready",
                "reason_code": "PASS",
                "iterations": 27,
                "residual_norm_before": 0.04728610099315822,
                "residual_norm_after_linear_solve": 0.04728606860212275,
                "condition_estimate": 241507.49735932404,
            }
        },
        "line_search_preview": {
            "status": "ready",
            "accepted_alpha": 1.0,
            "residual_before_n": 0.04728610099315822,
            "residual_after_n": 0.04728606850215522,
            "residual_reduction_ratio": 6.871152900485691e-07,
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
            ),
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "dof_count": 78282,
            "direct_residual_inf_n": 0.04728606850215522,
            "direct_relative_residual_inf": 3.575283951414537e-06,
            "accepted_alpha": 1.0,
            "residual_gate_passed": False,
            "promotes_g1_closure": False,
            "claim_boundary": "Loadable sparse-direct line-search checkpoint candidate only.",
        },
        "claim_boundary": "non_promoting_sparse_direct_real_mgt_smoke_only",
    }


def _sparse_direct_scaled_lsmr_second_payload() -> dict:
    payload = _sparse_direct_scaled_lsmr_frontier_payload()
    payload["resource_usage"] = {
        **payload["resource_usage"],
        "checkpoint": {
            **payload["resource_usage"]["checkpoint"],
            "checkpoint_npz": (
                "implementation/phase1/release_evidence/productization/"
                "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
            ),
            "checkpoint_direct_residual_inf_n": 0.04728606850215522,
        },
    }
    payload["direction_solve_comparison"] = {
        "scaled_lsmr": {
            **payload["direction_solve_comparison"]["scaled_lsmr"],
            "residual_norm_before": 0.04728606850215522,
            "residual_norm_after_linear_solve": 0.04728591691470079,
        }
    }
    payload["line_search_preview"] = {
        "status": "ready",
        "accepted_alpha": 1.0,
        "residual_before_n": 0.04728606850215522,
        "residual_after_n": 0.047285916814733264,
        "residual_reduction_ratio": 3.2078670687026466e-06,
    }
    payload["output_final_checkpoint"] = {
        **payload["output_final_checkpoint"],
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
        ),
        "direct_residual_inf_n": 0.047285916814733264,
        "direct_relative_residual_inf": 3.575272482378888e-06,
    }
    payload["claim_boundary"] = "non_promoting_sparse_direct_second_step_fixture"
    return payload


def _sparse_direct_scaled_lsmr_third_payload() -> dict:
    payload = _sparse_direct_scaled_lsmr_second_payload()
    payload["resource_usage"] = {
        **payload["resource_usage"],
        "checkpoint": {
            **payload["resource_usage"]["checkpoint"],
            "checkpoint_npz": (
                "implementation/phase1/release_evidence/productization/"
                "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
            ),
            "checkpoint_direct_residual_inf_n": 0.047285916814733264,
        },
    }
    payload["direction_solve_comparison"] = {
        "scaled_lsmr": {
            **payload["direction_solve_comparison"]["scaled_lsmr"],
            "residual_norm_before": 0.047285916814733264,
            "residual_norm_after_linear_solve": 0.047285863785477,
        }
    }
    payload["line_search_preview"] = {
        "status": "ready",
        "accepted_alpha": 1.0,
        "residual_before_n": 0.047285916814733264,
        "residual_after_n": 0.047285863685509466,
        "residual_reduction_ratio": 1.123573938649602e-06,
    }
    payload["output_final_checkpoint"] = {
        **payload["output_final_checkpoint"],
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz"
        ),
        "direct_residual_inf_n": 0.047285863685509466,
        "direct_relative_residual_inf": 3.575268465295903e-06,
    }
    payload["claim_boundary"] = "non_promoting_sparse_direct_third_step_fixture"
    return payload


def _sparse_direct_scaled_lsmr_chain_payload() -> dict:
    return {
        "schema_version": "g1-mgt-sparse-direct-scaled-lsmr-chain-probe.v1",
        "status": "ready",
        "reason_code": "PASS",
        "promotes_g1_closure": False,
        "is_smoke_only": True,
        "initial_checkpoint_npz": (
            "implementation/phase1/release_evidence/productization/"
            "g1_active_frontier_structural_policy_shell_rotation_row_second_candidate.npz"
        ),
        "max_steps": 3,
        "step_count": 3,
        "ready_step_count": 3,
        "checkpoint_written_step_count": 3,
        "monotonic_residual_descent": True,
        "initial_residual_n": 0.04728610099315822,
        "final_residual_n": 0.047285863685509466,
        "total_reduction_n": 2.3730764875384835e-07,
        "total_reduction_ratio": 5.018549716928113e-06,
        "latest_checkpoint_path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_mgt_sparse_direct_scaled_lsmr_chain_step_03_candidate.npz"
        ),
        "latest_checkpoint_residual_gate_passed": False,
        "claim_boundary": "non-promoting chain fixture",
    }


def _sparse_direct_scaled_lsmr_long_chain_payload() -> dict:
    payload = _sparse_direct_scaled_lsmr_chain_payload()
    payload.update(
        {
            "step_count": 10,
            "ready_step_count": 10,
            "checkpoint_written_step_count": 10,
            "final_residual_n": 0.04728560329011722,
            "final_residual_gate_passed": False,
            "final_residual_gate_gap_n": 0.04678560329011722,
            "final_residual_over_gate": 94.57120658023443,
            "total_reduction_n": 4.977030410024952e-07,
            "total_reduction_ratio": 1.0525355877290609e-05,
            "last_step_reduction_n": 2.3295130602285496e-08,
            "last_step_reduction_ratio": 4.926471802226919e-07,
            "mean_step_reduction_n": 4.977030410024952e-08,
            "max_step_reduction_n": 1.5168742195648122e-07,
            "estimated_steps_to_gate_at_last_reduction": 2008386,
            "gate_convergence_assessment": "stalled_for_gate",
            "recommended_next_action": (
                "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
            ),
            "latest_checkpoint_path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_mgt_sparse_direct_scaled_lsmr_long_chain_step_10_candidate.npz"
            ),
        }
    )
    return payload


def _sparse_direct_scaled_lsmr_from_incomplete_preview_payload() -> dict:
    payload = _sparse_direct_scaled_lsmr_frontier_payload()
    payload["status"] = "ready"
    payload["jvp_eps"] = 0.001
    payload["direction_solve_comparison"]["scaled_lsmr"].update(
        {
            "iterations": 512,
            "residual_norm_before": 0.0033228596775920494,
            "residual_norm_after_linear_solve": 0.003322712022860205,
            "condition_estimate": 321056.7105073829,
        }
    )
    payload["line_search_preview"].update(
        {
            "residual_before_n": 0.0033228596775920494,
            "residual_after_n": 0.0033227123724053342,
            "residual_reduction_ratio": 4.433084782619419e-05,
            "beats_d_residual_reduction_baseline": False,
        }
    )
    payload["output_final_checkpoint"].update(
        {
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_candidate.npz"
            ),
            "direct_residual_inf_n": 0.0033227123724053342,
            "residual_before_n": 0.0033228596775920494,
            "direction_solver": "scaled_lsmr",
            "direction_status": "ready",
            "incomplete_gmres_direction_preview": False,
            "residual_gate_passed": False,
        }
    )
    payload["resource_usage"]["checkpoint"] = {
        "checkpoint_applied": True,
        "checkpoint_npz": (
            "implementation/phase1/release_evidence/productization/"
            "g1_mgt_sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_mu_1e_4_incomplete_preview_candidate.npz"
        ),
        "checkpoint_direct_residual_inf_n": 0.0033228596775920494,
        "checkpoint_promotes_g1_closure": False,
    }
    payload["claim_boundary"] = (
        "non_promoting_scaled_lsmr_from_incomplete_preview_fixture"
    )
    return payload


def _sparse_direct_scaled_lsmr_from_incomplete_preview_chain_payload() -> dict:
    return {
        "schema_version": "g1-mgt-sparse-direct-scaled-lsmr-chain-probe.v1",
        "status": "ready",
        "reason_code": "PASS",
        "promotes_g1_closure": False,
        "is_smoke_only": True,
        "initial_checkpoint_npz": (
            "implementation/phase1/release_evidence/productization/"
            "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_candidate.npz"
        ),
        "max_steps": 10,
        "jvp_eps": 0.001,
        "step_count": 10,
        "ready_step_count": 10,
        "checkpoint_written_step_count": 10,
        "monotonic_residual_descent": True,
        "initial_residual_n": 0.0033227123724053342,
        "final_residual_n": 0.003321678662540961,
        "residual_gate_n": 5.0e-4,
        "final_residual_gate_passed": False,
        "final_residual_gate_gap_n": 0.002821678662540961,
        "final_residual_over_gate": 6.643357325081922,
        "gate_convergence_assessment": "stalled_for_gate",
        "recommended_next_action": (
            "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
        ),
        "total_reduction_n": 1.0337098643731224e-06,
        "total_reduction_ratio": 0.00031110422706399134,
        "last_step_reduction_n": 1.018051989376545e-07,
        "estimated_steps_to_gate_at_last_reduction": 27717,
        "latest_checkpoint_path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_chain_step_10_candidate.npz"
        ),
        "latest_checkpoint_residual_gate_passed": False,
        "claim_boundary": "non-promoting chain fixture",
    }


def _sparse_direct_shifted_splu_payload(
    *,
    from_gate_step2: bool = False,
) -> dict:
    before = 3.694505585372099e-05 if from_gate_step2 else 0.003321678662540961
    after = 3.42023849952966e-05 if from_gate_step2 else 3.694505585372099e-05
    input_checkpoint = (
        "g1_mgt_sparse_direct_shifted_splu_mu_1e_4_from_incomplete_preview_chain_candidate.npz"
        if from_gate_step2
        else "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_chain_step_10_candidate.npz"
    )
    output_checkpoint = (
        "g1_mgt_sparse_direct_shifted_splu_mu_1e_4_from_gate_candidate_step2_candidate.npz"
        if from_gate_step2
        else "g1_mgt_sparse_direct_shifted_splu_mu_1e_4_from_incomplete_preview_chain_candidate.npz"
    )
    return {
        "schema_version": "g1-mgt-sparse-direct-physical-line-search-smoke.v1",
        "status": "ready",
        "reason_code": "PASS",
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "jvp_eps": 0.001,
        "jvp_parity": {"pass": True},
        "assembled_tangent_parity": {"pass": True},
        "direction_solve_comparison": {
            "shifted_sparse_direct_splu": {
                "status": "ready",
                "reason_code": "PASS",
                "residual_norm_before": before,
                "residual_norm_after_linear_solve": after,
                "residual_norm_after_shifted_linear_solve": 8.0e-16,
                "shifted_operator": {
                    "mode": "shifted_ilu",
                    "shift_mode": "relative_diagonal_shift",
                    "shift_mu": 1.0e-4,
                    "effective_shift": 292168.1153689314,
                },
                "preconditioned": True,
            }
        },
        "line_search_preview": {
            "attempted": True,
            "status": "ready",
            "accepted_alpha": 1.0,
            "residual_before_n": before,
            "residual_after_n": after,
            "residual_reduction_ratio": (before - after) / before,
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                f"{output_checkpoint}"
            ),
            "direct_residual_inf_n": after,
            "direct_relative_residual_inf": 2.6e-09,
            "residual_gate_passed": True,
            "direction_solver": "shifted_sparse_direct_splu",
            "direction_status": "ready",
            "promotes_g1_closure": False,
        },
        "resource_usage": {
            "checkpoint": {
                "checkpoint_applied": True,
                "checkpoint_npz": (
                    "implementation/phase1/release_evidence/productization/"
                    f"{input_checkpoint}"
                ),
                "checkpoint_direct_residual_inf_n": before,
                "checkpoint_residual_gate_passed": from_gate_step2,
                "checkpoint_promotes_g1_closure": False,
            }
        },
        "claim_boundary": "non-promoting shifted SPLU fixture",
    }


def _sparse_direct_adaptive_jvp_eps_probe_payload(
    *,
    solver: str,
    incomplete_preview: bool = False,
) -> dict:
    reason = (
        "ERR_ILU_FACTOR_FAILED"
        if solver == "gmres_ilu"
        else "ERR_ILU_GMRES_NOT_CONVERGED"
        if solver == "gmres_shifted_ilu"
        else "ERR_DIRECTION_SOLVE_BLOCKED"
    )
    direction = {
        "status": "blocked",
        "reason_code": reason,
    }
    if solver in {"gmres_matrix_free", "gmres_shifted_ilu"}:
        direction.update(
            {
                "iterations": 32,
                "residual_norm_before": 0.04728560329011722,
                "residual_norm_after": (
                    0.0001237155747730867
                    if solver == "gmres_shifted_ilu"
                    else 0.05179151634140644
                ),
                "preconditioned": solver == "gmres_shifted_ilu",
            }
        )
    if solver == "gmres_shifted_ilu":
        direction["preconditioner"] = {
            "mode": "shifted_ilu",
            "shift_mode": "relative_diagonal_shift",
            "shift_mu": 1.0e-4,
            "effective_shift": 292168.1153689314,
        }
    status = "blocked"
    line_search = {
        "attempted": True,
        "status": "blocked",
        "reason_code": reason,
        "accepted_alpha": None,
    }
    if incomplete_preview:
        status = "review"
        direction.update(
            {
                "status": "preview",
                "preview_reason_code": "PREVIEW_INCOMPLETE_GMRES_DIRECTION",
                "incomplete_direction_preview": True,
                "incomplete_gmres_relative_tolerance": 3.0e-3,
                "residual_norm_after_ratio": 0.002616347601912557,
            }
        )
        line_search = {
            "attempted": True,
            "status": "ready",
            "reason_code": "ok",
            "accepted_alpha": 1.0,
            "residual_before_n": 0.04728560329011722,
            "residual_after_n": 0.0033228596775920494,
            "residual_reduction_ratio": 0.9297278781195855,
            "incomplete_gmres_direction_preview": True,
        }
    output_checkpoint = None
    if incomplete_preview:
        output_checkpoint = {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_mgt_sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_mu_1e_4_incomplete_preview_candidate.npz"
            ),
            "direct_residual_inf_n": 0.0033228596775920494,
            "residual_gate_passed": False,
            "direction_solver": "gmres_shifted_ilu",
            "direction_status": "preview",
            "incomplete_gmres_direction_preview": True,
            "preview_reason_code": "PREVIEW_INCOMPLETE_GMRES_DIRECTION",
            "promotes_g1_closure": False,
        }
    return {
        "schema_version": "g1-mgt-sparse-direct-physical-line-search-smoke.v1",
        "status": status,
        "reason_code": (
            "PREVIEW_INCOMPLETE_GMRES_DIRECTION" if incomplete_preview else reason
        ),
        "promotes_g1_closure": False,
        "load_scale": 1.0,
        "jvp_eps": 0.001,
        "jvp_parity": {
            "pass": True,
            "finite_difference_eps": 0.001,
            "reference_finite_difference_eps": 0.01,
            "max_absolute_error_n": 0.001708984375,
            "max_relative_error": 1.3296559216720257e-15,
        },
        "assembled_tangent_parity": {
            "pass": True,
            "max_absolute_error": 0.006011962890625,
            "max_relative_error": 2.683381287585585e-15,
        },
        "direction_solve_comparison": {
            "gmres_matrix_free_none": {
                "status": "blocked",
                "reason_code": "gmres_not_converged_maxiter",
                "iterations": 32,
                "residual_norm_after": 0.05179151634140644,
            },
            solver: direction,
        },
        "line_search_preview": line_search,
        "output_final_checkpoint": output_checkpoint,
        "resource_usage": {
            "checkpoint": {
                "checkpoint_applied": True,
                "checkpoint_npz": (
                    "implementation/phase1/release_evidence/productization/"
                    "g1_mgt_sparse_direct_scaled_lsmr_long_chain_step_10_candidate.npz"
                ),
                "checkpoint_direct_residual_inf_n": 0.04728560329011722,
            }
        },
        "claim_boundary": "non-promoting adaptive JVP fixture",
    }


def _active_set_ls_trust_schedule_candidate_payload() -> dict:
    payload = _active_set_ls_trust_candidate_payload()
    payload["summary"] = {
        **payload["summary"],
        "final_residual_n": 0.4274072499174437,
        "total_reduction_n": 0.0004231541007554962,
        "active_row_count_schedule": [8, 16, 32],
        "steps_taken": 4,
        "stop_reason": "max_steps",
    }
    payload["output_final_checkpoint"] = {
        **payload["output_final_checkpoint"],
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_schedule_from_frontier_candidate.npz"
        ),
        "direct_residual_inf_n": 0.4274072499174437,
    }
    return payload


def _active_set_minimax_trust_candidate_payload() -> dict:
    return {
        "schema_version": "g1-active-set-minimax-trust-candidate.v1",
        "status": "review",
        "promotes_g1_closure": False,
        "summary": {
            "initial_residual_n": 0.42740724991695345,
            "final_residual_n": 0.42740724991695345,
            "total_reduction_n": 0.0,
            "total_reduction_ratio": 0.0,
            "residual_gate_passed": False,
            "active_row_count_schedule": [8, 16, 32],
            "support_strongest_per_row": 32,
            "steps_taken": 0,
            "stop_reason": "no_candidate_descent",
        },
        "history": [
            {
                "iteration": 0,
                "accepted": False,
                "direction_attempts": [
                    {
                        "active_row_count": 8,
                        "direction_status": "ready",
                        "direction": {
                            "support_column_count": 24,
                            "active_linear_improvement_inf_n": (
                                1.1784706543949142e-10
                            ),
                        },
                    },
                    {
                        "active_row_count": 16,
                        "direction_status": "ready",
                        "direction": {
                            "support_column_count": 143,
                            "active_linear_improvement_inf_n": (
                                6.970424237806583e-12
                            ),
                        },
                    },
                ],
            }
        ],
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "g1_adaptive_fixed_signed_all_components_from_structural_active_set_minimax_trust_candidate.npz"
            ),
            "load_scale": 1.0,
            "direct_residual_inf_n": 0.42740724991695345,
            "residual_gate_passed": False,
        },
    }


def _hip_required_full_load_residual_jvp_frontier_payload() -> dict:
    return {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "status": "partial",
        "source_commit_sha": "fixture-step14",
        "base_direct_residual": {
            "load_scale": 1.0,
            "direct_residual_inf_n": 5.602810437066918,
        },
        "final_direct_residual": {
            "direct_residual_inf_n": 5.584111205301272,
            "direct_relative_residual_inf": 0.0004222127955999929,
            "residual_gate_passed": False,
        },
        "gate_assessment": {
            "direct_residual_gate_passed": False,
            "relative_increment_gate_passed": True,
            "full_load_closure_passed": True,
            "material_newton_breadth_passed": False,
            "consistent_residual_jacobian_newton_passed": False,
            "hip_residual_engine_gate_passed": True,
        },
        "residual_contract": {
            "consistent_residual_jacobian_newton_gate_passed": False,
            "hip_residual_engine_contract_passed": True,
            "hip_residual_engine_required_lane_count": 2,
            "hip_residual_engine_passed_lane_count": 2,
            "hip_residual_engine_backends": [
                "hip_full_residual",
                "hip_full_residual_resident",
            ],
            "hip_residual_engine_rows": [
                {"component": "matrix_free_global_krylov", "passed": True},
                {
                    "component": "current_tangent_residual_row_correction",
                    "passed": True,
                },
            ],
        },
        "matrix_free_global_krylov": {
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "hip_krylov_solver_used": True,
            "accepted_state_refresh_backend": "hip_full_residual_resident",
            "accepted_state_refresh_hip_used": True,
            "accepted_state_refresh_cpu_used": False,
            "best_gate_eligible_candidate": {
                "direct_residual_inf_n": 5.601030296954047,
                "improvement_inf_n": 0.0017801401659198746,
                "residual_batch_backend": "hip_full_residual_resident",
            },
        },
        "current_tangent_residual_row_correction": {
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "accepted_state_refresh_backend": "hip_full_residual",
            "accepted_state_refresh_hip_used": True,
            "accepted_state_refresh_cpu_used": False,
            "best_gate_eligible_candidate": {
                "direct_residual_inf_n": 5.584111205301272,
                "improvement_inf_n": 0.01691909165277483,
                "residual_batch_backend": "hip_full_residual",
            },
        },
        "output_final_checkpoint": {
            "written": True,
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "mgt_residual_jacobian_step14_material_active_set_ls_rows32_child_direct_candidate.npz"
            ),
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "direct_residual_inf_n": 5.584111205301272,
        },
    }


def _hip_required_consistency_no_descent_payload() -> dict:
    payload = deepcopy(_hip_probe_payload())
    payload["source_commit_sha"] = "fixture-step16-consistency-no-descent"
    payload["blockers"] = [
        "consistent_residual_jacobian::consistent_residual_jacobian_newton_not_proven",
        "global_krylov_accepted_state_tangent_refresh_hip_not_proven",
    ]
    direct_summary = payload["hip_direct_probe"]["direct_residual_summary"]
    direct_summary["base_direct_residual_inf_n"] = 5.571832446349628
    direct_summary["final_direct_residual_inf_n"] = 5.571832446349628
    direct_summary["output_final_checkpoint"] = {
        "written": False,
        "reason": "no_residual_descent",
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "mgt_residual_jacobian_step16_material_active_set_ls_rows32_child_direct_candidate.npz"
        ),
        "load_scale": 1.0,
    }
    payload["production_rocm_hip_residual_jvp_worker"][
        "residual_jvp_worker_path_ready"
    ] = True
    return payload


def _hip_required_scaled_global_krylov_no_descent_payload() -> dict:
    return {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "status": "partial",
        "source_commit_sha": "fixture-step16-scaled-global-krylov",
        "base_direct_residual": {
            "load_scale": 1.0,
            "direct_residual_inf_n": 5.571832446349628,
        },
        "final_direct_residual": {
            "direct_residual_inf_n": 5.571832446349628,
            "direct_relative_residual_inf": 0.00042128440270930455,
            "residual_gate_passed": False,
        },
        "gate_assessment": {
            "direct_residual_gate_passed": False,
            "relative_increment_gate_passed": True,
            "full_load_closure_passed": True,
            "material_newton_breadth_passed": False,
            "consistent_residual_jacobian_newton_passed": False,
            "fallback_zero_passed": True,
            "hip_residual_engine_gate_passed": True,
        },
        "matrix_free_global_krylov": {
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": False,
            "scaling_mode": "residual_diagonal_displacement",
            "hip_krylov_solver_used": True,
            "jvp_rows": [
                {"row": 101, "backend": "hip_full_residual_resident"},
                {"row": 102, "backend": "hip_full_residual_resident"},
                {"row": 103, "backend": "hip_full_residual_resident"},
                {"row": 104, "backend": "hip_full_residual_resident"},
            ],
            "trial_rows": [
                {"alpha": 1.0, "direct_residual_inf_n": 5.572699041492692},
                {"alpha": 0.5, "direct_residual_inf_n": 5.5732},
            ],
            "best_candidate": {
                "alpha": 1.0,
                "direct_residual_inf_n": 5.572699041492692,
                "improvement_inf_n": -0.0008665950510797771,
                "residual_batch_backend": "hip_full_residual_resident",
            },
        },
        "current_tangent_residual_row_correction": {
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": False,
            "target_row_counts": [16, 32],
            "support_column_counts": [2],
            "trial_rows": [
                {
                    "target_row_count": 16,
                    "support_column_count": 2,
                    "direct_residual_inf_n": 5.58261631268956,
                }
            ],
            "best_candidate": {
                "direct_residual_inf_n": 5.58261631268956,
                "improvement_inf_n": -0.010783866339932224,
                "residual_batch_backend": "hip_full_residual",
            },
        },
        "output_final_checkpoint": {
            "written": False,
            "reason": "no_residual_descent",
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "mgt_residual_jacobian_step16_scaled_global_krylov_candidate.npz"
            ),
            "load_scale": 1.0,
        },
    }


def _current_frontier_operator_mismatch_audit_payload() -> dict:
    return {
        "schema_version": "g1-current-frontier-operator-mismatch-audit.v1",
        "status": "ready",
        "audit_complete": True,
        "is_audit_only": True,
        "promotes_g1_closure": False,
        "frontier_probe": {
            "path": (
                "implementation/phase1/release_evidence/productization/"
                "mgt_residual_jacobian_step16_scaled_global_krylov_direct_probe.json"
            ),
            "status": "partial",
            "source_commit_sha": "fixture-step16-scaled-global-krylov",
            "load_scale": 1.0,
            "base_direct_residual_inf_n": 5.571832446349628,
            "final_direct_residual_inf_n": 5.571832446349628,
            "output_checkpoint_written": False,
            "output_checkpoint_reason": "no_residual_descent",
            "output_checkpoint_path": (
                "implementation/phase1/release_evidence/productization/"
                "mgt_residual_jacobian_step16_scaled_global_krylov_candidate.npz"
            ),
            "full_load_no_descent": True,
        },
        "current_operator_mismatch": {
            "normalization_lambda": 515.4003370345272,
            "frame_tangent_ratio_min": 4.7619047619047615e-06,
            "service_material_scale_min": 0.02746524828006217,
            "mismatch_reasons": [
                "frame_service_material_tangent_reduced_below_elastic",
                "assembled_service_material_tangent_reduced_below_elastic",
                "lambda_damping_available_to_corrector_but_excluded_from_physical_residual",
                "state_dependent_shell_material_tangent_refresh_is_host_side_not_production_residency",
            ],
        },
        "shell_material_state": {
            "shell_material_tangent_elastic_passive_at_checkpoint": True,
            "shell_material_tangent_is_stall_driver": False,
        },
        "current_frontier_no_descent": {
            "global_and_row_operator_family_no_descent": True,
            "scaled_global_krylov": {
                "attempted": True,
                "promoted_to_final_state": False,
                "best_direct_residual_inf_n": 5.572699041492692,
                "best_improvement_inf_n": -0.0008665950510797771,
                "trial_count": 16,
                "all_trial_candidates_no_descent": True,
            },
            "current_tangent_residual_row_correction": {
                "attempted": True,
                "promoted_to_final_state": False,
                "best_direct_residual_inf_n": 5.58261631268956,
                "best_improvement_inf_n": -0.010783866339932224,
                "trial_count": 24,
                "all_trial_candidates_no_descent": True,
            },
        },
        "operator_mismatch_summary": {
            "stall_driver": (
                "current_full_load_scaled_global_krylov_and_row_correction_"
                "operator_family_no_descent"
            ),
            "next_required_operator": (
                "physical_consistent_frame_shell_material_geometric_with_state_"
                "updated_material_tangent_and_full_residual_globalization"
            ),
            "disfavored_retries": [
                "repeat_scaled_global_krylov_with_residual_diagonal_displacement",
                "repeat_largest_rows_current_tangent_residual_row_correction",
            ],
        },
        "terminal_criteria": {
            "frontier_probe_present": True,
            "full_load_checkpoint_input": True,
            "live_g1_assembly_contract_passed": True,
            "physical_residual_contract_preserved": True,
            "hip_residual_engine_contract_passed": True,
            "current_scaled_global_krylov_no_descent": True,
            "current_row_correction_no_descent": True,
            "shell_material_tangent_elastic_passive_evidence_present": True,
            "current_operator_mismatch_named": True,
        },
        "claim_boundary": (
            "This is a non-promoting current-frontier operator mismatch audit."
        ),
    }


def _global_connectivity_payload() -> dict:
    return {
        "schema_version": "g1-global-connectivity-load-path-audit.v1",
        "status": "ready",
        "decision_record": {
            "primary_next_lane": runner.PRIMARY_NEXT_LANE,
            "row_only_correction_loop_stopped": True,
        },
    }


def _write_inputs(tmp_path: Path, *, action_id: str | None = runner.RUNNER_ID) -> dict[str, Path]:
    paths = {
        "g1_lane": tmp_path / "g1_full_load_hip_newton_lane_report.json",
        "cause": tmp_path / "g1_f2g_f2h_cause_narrowing_status.json",
        "hip": tmp_path / "mgt_residual_jacobian_consistency_hip_required_probe.json",
        "global": tmp_path / "g1_global_connectivity_load_path_audit.json",
        "assembly": tmp_path / "g1_assembly_contract_seed_report.json",
        "sweep": tmp_path / "g1_true_newton_load_sweep_status.json",
        "checkpoint_candidate": (
            tmp_path / "g1_true_newton_full_load_checkpoint_candidate_status.json"
        ),
        "true_newton_from_active": (
            tmp_path / runner.DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_LS_TRUST_CANDIDATE
        ),
        "true_newton_from_active_service_tangent": (
            tmp_path
            / runner.DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_SERVICE_TANGENT_LS_TRUST_CANDIDATE
        ),
        "adaptive": tmp_path / runner.DEFAULT_ADAPTIVE_ALL_COMPONENTS_FRONTIER,
        "shell_jvp": tmp_path / runner.DEFAULT_SHELL_HOTSPOT_TANGENT_FD_JVP_PROBE,
        "shell_diag": tmp_path / runner.DEFAULT_SHELL_HOTSPOT_DIAGONAL_SWEEP_PROBE,
        "global_tangent": tmp_path / runner.DEFAULT_GLOBAL_TANGENT_SCALED_SWEEP_PROBE,
        "residual_gradient": (
            tmp_path / runner.DEFAULT_RESIDUAL_NORM_GRADIENT_TINY_SWEEP_PROBE
        ),
        "active_set": tmp_path / runner.DEFAULT_ACTIVE_SET_LS_SWEEP_PROBE,
        "active_set_candidate": tmp_path / runner.DEFAULT_ACTIVE_SET_LS_TRUST_CANDIDATE,
        "active_set_schedule": (
            tmp_path / runner.DEFAULT_ACTIVE_SET_LS_TRUST_SCHEDULE_CANDIDATE
        ),
        "active_set_tangent_jvp": (
            tmp_path / runner.DEFAULT_ACTIVE_SET_LS_TRUST_TANGENT_FD_JVP_PROBE
        ),
        "active_set_minimax": (
            tmp_path / runner.DEFAULT_ACTIVE_SET_MINIMAX_TRUST_CANDIDATE
        ),
        "frame_eps_sweep": (
            tmp_path / runner.DEFAULT_FRAME_TANGENT_FD_EPSILON_SWEEP_PROBE
        ),
        "mu_sweep": (
            tmp_path / runner.DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_MU_SWEEP_PROBE
        ),
        "load_parameter": (
            tmp_path / runner.DEFAULT_ACTIVE_SET_LOAD_PARAMETER_PROBE
        ),
        "load_parameter_tiny": (
            tmp_path / runner.DEFAULT_ACTIVE_SET_LOAD_PARAMETER_TINY_TRUST_PROBE
        ),
        "residual_ownership": (
            tmp_path / runner.DEFAULT_ACTIVE_FRONTIER_RESIDUAL_OWNERSHIP_PROBE
        ),
        "shell_neighborhood": (
            tmp_path / runner.DEFAULT_ACTIVE_FRONTIER_SHELL_LOAD_NEIGHBORHOOD_PROBE
        ),
        "shell_policy": (
            tmp_path / runner.DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_REPLAY_PROBE
        ),
        "shell_policy_linearized": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_LINEARIZED_ACTIVE_SET_PROBE
        ),
        "structural_policy_active_set": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_CANDIDATE
        ),
        "structural_policy_alpha_sweep": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_ALPHA_SWEEP
        ),
        "structural_policy_direct_replay": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_DIRECT_MATERIAL_REPLAY_PROBE
        ),
        "structural_policy_component_row": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_PROBE
        ),
        "structural_policy_component_row_step2": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP2_PROBE
        ),
        "structural_policy_component_row_step3": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP3_PROBE
        ),
        "structural_policy_ownership": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_RESIDUAL_OWNERSHIP_PROBE
        ),
        "structural_policy_linearized_after": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_LINEARIZED_ACTIVE_SET_AFTER_TWO_STEP_PROBE
        ),
        "structural_policy_shell_rotation_candidate": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_CANDIDATE
        ),
        "structural_policy_shell_rotation_no_descent": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_NO_DESCENT_PROBE
        ),
        "structural_policy_shell_rotation_ownership": (
            tmp_path
            / runner.DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_CANDIDATE_OWNERSHIP_PROBE
        ),
        "sparse_direct_scaled_lsmr_frontier": (
            tmp_path / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_PROBE
        ),
        "sparse_direct_scaled_lsmr_second": (
            tmp_path / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_PROBE
        ),
        "sparse_direct_scaled_lsmr_third": (
            tmp_path / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_PROBE
        ),
        "sparse_direct_scaled_lsmr_chain": (
            tmp_path / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_CHAIN_PROBE
        ),
        "sparse_direct_scaled_lsmr_long_chain": (
            tmp_path / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_LONG_CHAIN_PROBE
        ),
        "sparse_direct_scaled_lsmr_from_incomplete_preview": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_PROBE
        ),
        "sparse_direct_scaled_lsmr_from_incomplete_preview_chain": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE
        ),
        "sparse_direct_shifted_splu_from_incomplete_preview_chain": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE
        ),
        "sparse_direct_shifted_splu_from_gate_candidate_step2": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_GATE_CANDIDATE_STEP2_PROBE
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_ilu": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_ILU_PROBE
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_matrix_free": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_MATRIX_FREE_PROBE
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_PROBE
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview": (
            tmp_path
            / runner.DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_INCOMPLETE_PREVIEW_PROBE
        ),
        "hip_required_full_load_residual_jvp_frontier": (
            tmp_path / runner.DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_PROBE
        ),
        "hip_required_consistency_no_descent": (
            tmp_path / runner.DEFAULT_HIP_REQUIRED_CONSISTENCY_NO_DESCENT_PROBE
        ),
        "hip_required_scaled_global_krylov_no_descent": (
            tmp_path / runner.DEFAULT_HIP_REQUIRED_SCALED_GLOBAL_KRYLOV_NO_DESCENT_PROBE
        ),
        "current_frontier_operator_mismatch_audit": (
            tmp_path / runner.DEFAULT_CURRENT_FRONTIER_OPERATOR_MISMATCH_AUDIT
        ),
    }
    _write_json(paths["g1_lane"], _g1_lane_payload(action_id=action_id))
    _write_json(paths["cause"], _cause_narrowing_payload())
    _write_json(paths["hip"], _hip_probe_payload())
    _write_json(paths["global"], _global_connectivity_payload())
    _write_json(paths["assembly"], _assembly_contract_seed_payload())
    _write_json(paths["sweep"], _true_newton_load_sweep_payload())
    _write_json(paths["checkpoint_candidate"], _true_newton_checkpoint_candidate_payload())
    _write_json(paths["true_newton_from_active"], _true_newton_from_active_set_payload())
    _write_json(
        paths["true_newton_from_active_service_tangent"],
        _true_newton_from_active_set_service_tangent_payload(),
    )
    _write_json(paths["adaptive"], _adaptive_all_components_frontier_payload())
    _write_json(paths["shell_jvp"], _shell_hotspot_tangent_fd_jvp_payload())
    _write_json(paths["shell_diag"], _shell_hotspot_diagonal_sweep_payload())
    _write_json(paths["global_tangent"], _global_tangent_scaled_sweep_payload())
    _write_json(
        paths["residual_gradient"],
        _residual_norm_gradient_tiny_sweep_payload(),
    )
    _write_json(paths["active_set"], _active_set_ls_sweep_payload())
    _write_json(paths["active_set_candidate"], _active_set_ls_trust_candidate_payload())
    _write_json(
        paths["active_set_schedule"],
        _active_set_ls_trust_schedule_candidate_payload(),
    )
    _write_json(
        paths["active_set_tangent_jvp"],
        _active_set_ls_trust_tangent_fd_jvp_payload(),
    )
    _write_json(
        paths["active_set_minimax"],
        _active_set_minimax_trust_candidate_payload(),
    )
    _write_json(paths["frame_eps_sweep"], _frame_tangent_fd_epsilon_sweep_payload())
    _write_json(paths["mu_sweep"], _true_newton_from_active_set_mu_sweep_payload())
    _write_json(paths["load_parameter"], _active_set_load_parameter_payload())
    _write_json(
        paths["load_parameter_tiny"],
        _active_set_load_parameter_payload(tiny_trust=True),
    )
    _write_json(
        paths["residual_ownership"],
        _active_frontier_residual_ownership_payload(),
    )
    _write_json(
        paths["shell_neighborhood"],
        _active_frontier_shell_load_neighborhood_payload(),
    )
    _write_json(
        paths["shell_policy"],
        _active_frontier_shell_policy_replay_payload(),
    )
    _write_json(
        paths["shell_policy_linearized"],
        _active_frontier_shell_policy_linearized_active_set_payload(),
    )
    _write_json(
        paths["structural_policy_active_set"],
        _active_frontier_structural_policy_active_set_payload(),
    )
    _write_json(
        paths["structural_policy_alpha_sweep"],
        _active_frontier_structural_policy_alpha_sweep_payload(),
    )
    _write_json(
        paths["structural_policy_direct_replay"],
        _active_frontier_structural_policy_direct_material_replay_payload(),
    )
    _write_json(
        paths["structural_policy_component_row"],
        _active_frontier_structural_policy_current_component_row_correction_payload(),
    )
    _write_json(
        paths["structural_policy_component_row_step2"],
        _active_frontier_structural_policy_current_component_row_correction_step2_payload(),
    )
    _write_json(
        paths["structural_policy_component_row_step3"],
        _active_frontier_structural_policy_current_component_row_correction_step3_payload(),
    )
    _write_json(
        paths["structural_policy_ownership"],
        _active_frontier_structural_policy_residual_ownership_payload(),
    )
    _write_json(
        paths["structural_policy_linearized_after"],
        _active_frontier_structural_policy_linearized_after_two_step_payload(),
    )
    _write_json(
        paths["structural_policy_shell_rotation_candidate"],
        _active_frontier_structural_policy_shell_rotation_candidate_payload(),
    )
    _write_json(
        paths["structural_policy_shell_rotation_no_descent"],
        _active_frontier_structural_policy_shell_rotation_no_descent_payload(),
    )
    _write_json(
        paths["structural_policy_shell_rotation_ownership"],
        _active_frontier_structural_policy_shell_rotation_ownership_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_frontier"],
        _sparse_direct_scaled_lsmr_frontier_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_second"],
        _sparse_direct_scaled_lsmr_second_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_third"],
        _sparse_direct_scaled_lsmr_third_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_chain"],
        _sparse_direct_scaled_lsmr_chain_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_long_chain"],
        _sparse_direct_scaled_lsmr_long_chain_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_from_incomplete_preview"],
        _sparse_direct_scaled_lsmr_from_incomplete_preview_payload(),
    )
    _write_json(
        paths["sparse_direct_scaled_lsmr_from_incomplete_preview_chain"],
        _sparse_direct_scaled_lsmr_from_incomplete_preview_chain_payload(),
    )
    _write_json(
        paths["sparse_direct_shifted_splu_from_incomplete_preview_chain"],
        _sparse_direct_shifted_splu_payload(),
    )
    _write_json(
        paths["sparse_direct_shifted_splu_from_gate_candidate_step2"],
        _sparse_direct_shifted_splu_payload(from_gate_step2=True),
    )
    _write_json(
        paths["sparse_direct_adaptive_jvp_eps_gmres_ilu"],
        _sparse_direct_adaptive_jvp_eps_probe_payload(solver="gmres_ilu"),
    )
    _write_json(
        paths["sparse_direct_adaptive_jvp_eps_gmres_matrix_free"],
        _sparse_direct_adaptive_jvp_eps_probe_payload(solver="gmres_matrix_free"),
    )
    _write_json(
        paths["sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu"],
        _sparse_direct_adaptive_jvp_eps_probe_payload(solver="gmres_shifted_ilu"),
    )
    _write_json(
        paths["sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview"],
        _sparse_direct_adaptive_jvp_eps_probe_payload(
            solver="gmres_shifted_ilu",
            incomplete_preview=True,
        ),
    )
    _write_json(
        paths["hip_required_full_load_residual_jvp_frontier"],
        _hip_required_full_load_residual_jvp_frontier_payload(),
    )
    _write_json(
        paths["hip_required_consistency_no_descent"],
        _hip_required_consistency_no_descent_payload(),
    )
    _write_json(
        paths["hip_required_scaled_global_krylov_no_descent"],
        _hip_required_scaled_global_krylov_no_descent_payload(),
    )
    _write_json(
        paths["current_frontier_operator_mismatch_audit"],
        _current_frontier_operator_mismatch_audit_payload(),
    )
    return paths


def test_runner_packet_is_ready_for_implementation_without_promoting_g1(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path)

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        assembly_contract_seed_path=paths["assembly"],
        true_newton_load_sweep_path=paths["sweep"],
        true_newton_full_load_checkpoint_candidate_path=paths["checkpoint_candidate"],
    )

    assert payload["status"] == "ready_for_runner_implementation"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["promotes_g1_closure"] is False
    assert payload["summary"]["contract_status"] == "ready_for_runner_implementation"
    assert payload["summary"]["closure_blocker_count"] == len(
        payload["closure_blockers"]
    )
    assert payload["summary"]["next_action_ids"] == [
        "promote_g1_assembly_contract_to_live_runner",
        "generate_full_load_1p0_checkpoint_candidate",
        "close_consistent_residual_jacobian_newton_gate",
        "prove_production_rocm_hip_residual_jvp_worker",
    ]
    assert payload["summary"]["worker_path_operator_sequence_count"] == 4
    assert payload["runner_contract"]["runner_id"] == runner.RUNNER_ID
    assert (
        payload["runner_contract"]["preferred_candidate_generator"]
        == runner.PREFERRED_GENERATOR
    )
    assert runner.DISALLOWED_RETRY_ACTION_IDS[0] in payload["runner_contract"][
        "disallowed_retry_action_ids"
    ]
    assert payload["routing_evidence"]["row_only_correction_loop_stopped"] is True
    assert payload["routing_evidence"]["support_or_link_row_gap_disfavored"] is True
    assert payload["checkpoint_gap"]["highest_observed_load_scale"] == 0.656
    assert payload["summary"]["true_newton_load_sweep_present"] is True
    assert payload["summary"]["full_load_true_newton_attempted"] is True
    assert payload["summary"]["full_load_true_newton_residual_descent_observed"] is True
    assert payload["summary"]["full_load_true_newton_residual_gate_passed"] is False
    assert payload["summary"]["full_load_true_newton_final_residual_n"] == (
        716.2398790963002
    )
    assert payload["true_newton_load_sweep"]["path"] == paths["sweep"].as_posix()
    assert payload["true_newton_load_sweep"]["present"] is True
    assert payload["true_newton_load_sweep"]["promotes_g1_closure"] is False
    assert payload["true_newton_load_sweep"]["full_load_row"]["load_scale"] == 1.0
    assert (
        payload["summary"]["true_newton_full_load_checkpoint_candidate_present"]
        is True
    )
    assert (
        payload["summary"]["true_newton_full_load_checkpoint_candidate_written"]
        is True
    )
    assert payload["summary"][
        "true_newton_full_load_checkpoint_candidate_direct_residual_n"
    ] == 464.56223807569995
    assert payload["summary"]["true_newton_from_active_set_present"] is True
    assert payload["summary"][
        "true_newton_from_active_set_final_residual_n"
    ] == 0.42740724991695345
    assert payload["summary"][
        "true_newton_from_active_set_stop_reason"
    ] == "line_search_no_descent"
    assert payload["summary"][
        "true_newton_from_active_set_max_jvp_gap_relative_inf"
    ] == 4.088178091005261
    assert payload["summary"][
        "true_newton_from_active_set_dominant_gap_component"
    ] == "frame"
    assert (
        payload["summary"]["true_newton_from_active_set_service_tangent_present"]
        is True
    )
    assert payload["summary"][
        "true_newton_from_active_set_service_tangent_stop_reason"
    ] == "line_search_no_descent"
    assert payload["summary"][
        "true_newton_from_active_set_service_tangent_max_jvp_gap_relative_inf"
    ] == 4.088231545444302
    assert (
        payload["summary"][
            "true_newton_frame_tangent_source_comparison_both_line_search_no_descent"
        ]
        is True
    )
    assert (
        payload["summary"][
            "true_newton_frame_tangent_source_comparison_both_dominant_gap_component_frame"
        ]
        is True
    )
    assert payload["summary"]["frame_tangent_fd_epsilon_sweep_present"] is True
    assert payload["summary"][
        "frame_tangent_fd_epsilon_sweep_default_gap_relative_inf"
    ] == 4.088178091005261
    assert payload["summary"][
        "frame_tangent_fd_epsilon_sweep_best_gap_relative_inf"
    ] == 0.003379869645939948
    assert (
        payload["summary"][
            "frame_tangent_fd_epsilon_sweep_default_eps_artifact_likely"
        ]
        is True
    )
    assert payload["summary"]["true_newton_from_active_set_mu_sweep_present"] is True
    assert payload["summary"][
        "true_newton_from_active_set_mu_sweep_evaluated_mu_count"
    ] == 11
    assert payload["summary"][
        "true_newton_from_active_set_mu_sweep_descent_observed"
    ] is False
    assert payload["summary"][
        "true_newton_from_active_set_mu_sweep_best_mu"
    ] == 0.03
    assert payload["summary"][
        "true_newton_from_active_set_mu_sweep_best_improvement_inf_n"
    ] == -2.9530156098189764e-10
    assert payload["summary"][
        "active_set_load_parameter_probe_descent_observed"
    ] is False
    assert payload["summary"][
        "active_set_load_parameter_probe_best_residual_inf_n"
    ] == 66.12257730630517
    assert payload["summary"][
        "active_set_load_parameter_tiny_trust_descent_observed"
    ] is True
    assert payload["summary"][
        "active_set_load_parameter_tiny_trust_best_load_scale"
    ] == 0.99999
    assert payload["summary"][
        "active_set_load_parameter_tiny_trust_restored_full_load_descent_observed"
    ] is False
    assert payload["summary"][
        "active_set_load_parameter_tiny_trust_best_restored_full_load_residual_inf_n"
    ] == 0.42740796265036174
    assert (
        payload["summary"]["active_frontier_residual_ownership_present"] is True
    )
    assert payload["summary"][
        "active_frontier_residual_ownership_top_residual_inf_n"
    ] == 0.42740724991695345
    assert payload["summary"][
        "active_frontier_residual_ownership_top_row_node_id"
    ] == 2276
    assert payload["summary"][
        "active_frontier_residual_ownership_top_row_dof_label"
    ] == "UZ"
    assert payload["summary"][
        "active_frontier_residual_ownership_top_row_dominant_internal_component"
    ] == "shell_bending_drilling"
    assert payload["summary"][
        "active_frontier_residual_ownership_top_row_balance_driver"
    ] == "external_load_balance"
    assert payload["summary"][
        "active_frontier_residual_ownership_top_row_inferred_external_load_n"
    ] == 0.569876333333335
    assert (
        payload["summary"]["active_frontier_shell_load_neighborhood_present"]
        is True
    )
    assert payload["summary"][
        "active_frontier_shell_load_neighborhood_top_required_shell_load_scale"
    ] == 0.25000000014572954
    assert (
        payload["summary"][
            "active_frontier_shell_load_neighborhood_top_free_pressure_resultant"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_shell_load_neighborhood_top_incident_element_id"
    ] == 25880
    assert payload["summary"][
        "active_frontier_shell_load_neighborhood_top_surface_component_frame_connected_node_count"
    ] == 0
    assert payload["summary"][
        "active_frontier_shell_load_neighborhood_external_reconstruction_error_inf_n"
    ] == 1.1102230246251565e-16
    assert payload["summary"]["active_frontier_shell_policy_replay_present"] is True
    assert payload["summary"][
        "active_frontier_shell_policy_replay_best_policy"
    ] == "attached_components_only"
    assert payload["summary"][
        "active_frontier_shell_policy_replay_best_residual_inf_n"
    ] == 0.3818403374023447
    assert payload["summary"][
        "active_frontier_shell_policy_replay_best_improvement_inf_n"
    ] == 0.04556691251460876
    assert (
        payload["summary"]["active_frontier_shell_policy_replay_descent_observed"]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_shell_policy_replay_best_residual_gate_passed"
        ]
        is False
    )
    assert payload["summary"][
        "active_frontier_shell_policy_replay_pressure_suppressed_surface_element_count"
    ] == 2
    assert (
        payload["summary"][
            "active_frontier_shell_policy_linearized_active_set_present"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_shell_policy_linearized_active_set_policy"
    ] == "structural_components_only"
    assert payload["summary"][
        "active_frontier_shell_policy_linearized_active_set_best_active_row_count"
    ] == 8
    assert payload["summary"][
        "active_frontier_shell_policy_linearized_active_set_best_after_inf_n"
    ] == 7.245315458703772e-13
    assert (
        payload["summary"][
            "active_frontier_shell_policy_linearized_active_set_descent_observed"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_shell_policy_linearized_active_set_direct_replay_required"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_ls_trust_present"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_ls_trust_policy"
    ] == "structural_components_only"
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_ls_trust_final_residual_n"
    ] == 0.07205501101467937
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_ls_trust_total_reduction_n"
    ] == 0.048877269735777995
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_ls_trust_residual_gate_passed"
        ]
        is False
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_stop_reason"
    ] == "no_candidate_descent"
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_present"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_residual_n"
    ] == 44.08048153349253
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_gate"
        ]
        is False
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_gap_n"
    ] == 44.08048153349253 - 0.07205501101467937
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_row_component"
    ] == "shell_bending_drilling"
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_row_residual_n"
    ] == 44.08048153349253
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_row_global_dof"
    ] == 13610
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_present"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_accepted"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_current_component_row_correction_final_residual_n"
    ] == 44.08014382294667
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_current_component_row_correction_improvement_n"
    ] == 44.08048153349253 - 44.08014382294667
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_gate"
        ]
        is False
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_cpu_refresh"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_present"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_accepted"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_final_residual_n"
    ] == 43.816671401648165
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_improvement_n"
    ] == 44.08014382294667 - 43.816671401648165
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_gate"
        ]
        is False
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_present"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_accepted"
        ]
        is False
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_stop_reason"
        ]
        == "no_residual_descent"
    )
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_current_component_row_correction_step3_best_residual_n"
    ] == 43.883829113147186
    assert payload["summary"][
        "active_frontier_structural_policy_active_set_current_component_row_correction_chain_latest_residual_n"
    ] == 43.816671401648165
    assert (
        payload["summary"][
            "active_frontier_structural_policy_active_set_current_component_row_correction_chain_no_descent_stop"
        ]
        == "no_residual_descent"
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_residual_ownership_present"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_structural_policy_residual_ownership_top_residual_inf_n"
    ] == 0.07205501101467937
    assert payload["summary"][
        "active_frontier_structural_policy_residual_ownership_top_row_node_id"
    ] == 2274
    assert payload["summary"][
        "active_frontier_structural_policy_residual_ownership_top_row_dof_label"
    ] == "RX"
    assert payload["summary"][
        "active_frontier_structural_policy_residual_ownership_top_row_component"
    ] == "shell_bending_drilling"
    assert payload["summary"][
        "active_frontier_structural_policy_residual_ownership_top_row_balance_driver"
    ] == "shell_bending_drilling_internal_force"
    assert payload["summary"][
        "active_frontier_structural_policy_linearized_after_two_step_best_after_inf_n"
    ] == 3.396605913197348e-13
    assert (
        payload["summary"][
            "active_frontier_structural_policy_linearized_after_two_step_descent_observed"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_shell_rotation_candidate_present"
        ]
        is True
    )
    assert (
        payload["summary"][
            "active_frontier_structural_policy_shell_rotation_candidate_fd_consistent"
        ]
        is True
    )
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_best_residual_inf_n"
    ] == 0.04728610099315822
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_best_improvement_inf_n"
    ] == 0.006755157257430255
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_checkpoint_path"
    ].endswith("shell_rotation_row_second_candidate.npz")
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_checkpoint_alpha"
    ] == 0.125
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_no_descent_probe_best_improvement_inf_n"
    ] == -0.0016700968262350901
    assert (
        payload["summary"][
            "active_frontier_structural_policy_shell_rotation_no_descent_probe_descent_observed"
        ]
        is False
    )
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_residual_inf_n"
    ] == 0.04728610099315822
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_dof_label"
    ] == "RX"
    assert payload["summary"][
        "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_balance_driver"
    ] == "shell_bending_drilling_internal_force"
    assert payload["summary"]["sparse_direct_scaled_lsmr_frontier_present"] is True
    assert payload["summary"]["sparse_direct_scaled_lsmr_frontier_status"] == "ready"
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_frontier_jvp_parity_pass"]
        is True
    )
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_frontier_tangent_parity_pass"]
        is True
    )
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_frontier_direction_status"]
        == "ready"
    )
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_frontier_direction_iterations"]
        == 27
    )
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_frontier_line_search_status"]
        == "ready"
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_frontier_line_search_residual_after_n"
    ] == 0.04728606850215522
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_frontier_line_search_reduction_ratio"
    ] == 6.871152900485691e-07
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_written"
        ]
        is True
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_frontier_output_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_n"
    ] == 0.04728606850215522
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_gate_passed"
        ]
        is False
    )
    assert payload["summary"]["sparse_direct_scaled_lsmr_second_present"] is True
    assert payload["summary"]["sparse_direct_scaled_lsmr_second_status"] == "ready"
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_second_line_search_status"]
        == "ready"
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_second_line_search_residual_after_n"
    ] == 0.047285916814733264
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_second_line_search_reduction_ratio"
    ] == 3.2078670687026466e-06
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_second_output_checkpoint_written"
        ]
        is True
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_second_output_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_second_output_checkpoint_residual_n"
    ] == 0.047285916814733264
    assert payload["summary"]["sparse_direct_scaled_lsmr_chain_step_count"] == 3
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_chain_ready_step_count"]
        == 3
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_chain_monotonic_residual_descent"
        ]
        is True
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_chain_initial_residual_n"
    ] == 0.04728610099315822
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_chain_final_residual_n"
    ] == 0.047285863685509466
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_chain_latest_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz"
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_chain_latest_checkpoint_residual_gate_passed"
        ]
        is False
    )
    assert payload["summary"]["sparse_direct_scaled_lsmr_chain_probe_present"] is True
    assert payload["summary"]["sparse_direct_scaled_lsmr_chain_probe_status"] == "ready"
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_chain_probe_step_count"
    ] == 3
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_chain_probe_monotonic_residual_descent"
        ]
        is True
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_chain_probe_final_residual_n"
    ] == 0.047285863685509466
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_long_chain_probe_present"]
        is True
    )
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_long_chain_probe_status"]
        == "ready"
    )
    assert (
        payload["summary"]["sparse_direct_scaled_lsmr_long_chain_probe_step_count"]
        == 10
    )
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_long_chain_probe_final_residual_n"
    ] == 0.04728560329011722
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_long_chain_probe_final_residual_over_gate"
    ] == 94.57120658023443
    assert payload["summary"][
        "sparse_direct_scaled_lsmr_long_chain_probe_estimated_steps_to_gate_at_last_reduction"
    ] == 2008386
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_long_chain_probe_gate_convergence_assessment"
        ]
        == "stalled_for_gate"
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_long_chain_probe_recommended_next_action"
        ]
        == "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_status"
        ]
        == "ready"
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_line_search_residual_after_n"
        ]
        == 0.0033227123724053342
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_output_checkpoint_residual_n"
        ]
        == 0.0033227123724053342
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_output_checkpoint_residual_gate_passed"
        ]
        is False
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_step_count"
        ]
        == 10
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_final_residual_n"
        ]
        == 0.003321678662540961
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_estimated_steps_to_gate_at_last_reduction"
        ]
        == 27717
    )
    assert (
        payload["summary"][
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_gate_convergence_assessment"
        ]
        == "stalled_for_gate"
    )
    assert (
        payload["summary"][
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_output_checkpoint_residual_gate_passed"
        ]
        is True
    )
    assert (
        payload["summary"][
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_output_checkpoint_residual_n"
        ]
        == 3.694505585372099e-05
    )
    assert (
        payload["summary"][
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_output_checkpoint_residual_n"
        ]
        == 3.42023849952966e-05
    )
    assert (
        payload["summary"][
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_output_checkpoint_residual_gate_passed"
        ]
        is True
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_status"
        ]
        == "blocked"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_reason_code"
        ]
        == "ERR_ILU_FACTOR_FAILED"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_jvp_parity_max_absolute_error_n"
        ]
        == 0.001708984375
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_reason_code"
        ]
        == "ERR_DIRECTION_SOLVE_BLOCKED"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_direction_residual_after_n"
        ]
        == 0.05179151634140644
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_reason_code"
        ]
        == "ERR_ILU_GMRES_NOT_CONVERGED"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_preconditioner_shift_mu"
        ]
        == 1.0e-4
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_direction_residual_after_n"
        ]
        == 0.0001237155747730867
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_status"
        ]
        == "review"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_reason_code"
        ]
        == "PREVIEW_INCOMPLETE_GMRES_DIRECTION"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_direction_status"
        ]
        == "preview"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_line_search_status"
        ]
        == "ready"
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_line_search_residual_after_n"
        ]
        == 0.0033228596775920494
    )
    assert (
        payload["summary"][
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_incomplete_direction_preview"
        ]
        is True
    )
    assert payload["summary"]["adaptive_all_components_frontier_present"] is True
    assert payload["summary"][
        "adaptive_all_components_frontier_final_residual_n"
    ] == 0.4278304040181992
    assert payload["summary"][
        "adaptive_all_components_frontier_residual_gate_passed"
    ] is False
    assert payload["summary"]["shell_hotspot_tangent_fd_jvp_present"] is True
    assert payload["summary"]["shell_hotspot_tangent_fd_jvp_fd_consistent"] is True
    assert payload["summary"][
        "shell_hotspot_tangent_fd_jvp_evaluated_row_count"
    ] == 1
    assert payload["summary"]["shell_hotspot_diagonal_sweep_present"] is True
    assert payload["summary"][
        "shell_hotspot_diagonal_sweep_descent_observed"
    ] is False
    assert payload["summary"][
        "shell_hotspot_diagonal_sweep_best_residual_n"
    ] == 0.4278508811240626
    assert payload["summary"][
        "shell_hotspot_diagonal_sweep_best_improvement_n"
    ] == -2.0477105863392353e-05
    assert payload["summary"]["global_tangent_scaled_sweep_present"] is True
    assert payload["summary"][
        "global_tangent_scaled_sweep_descent_observed"
    ] is False
    assert payload["summary"][
        "global_tangent_scaled_sweep_best_residual_n"
    ] == 0.42783040426657654
    assert payload["summary"][
        "global_tangent_scaled_sweep_best_improvement_n"
    ] == -2.483773187123006e-10
    assert payload["summary"][
        "global_tangent_scaled_sweep_linear_relative_residual"
    ] == 0.4278305011820284
    assert payload["summary"]["residual_norm_gradient_tiny_sweep_present"] is True
    assert payload["summary"][
        "residual_norm_gradient_tiny_sweep_inf_descent_observed"
    ] is False
    assert payload["summary"][
        "residual_norm_gradient_tiny_sweep_l2_descent_observed"
    ] is True
    assert payload["summary"][
        "residual_norm_gradient_tiny_sweep_best_l2_residual_n"
    ] == 1.2159739821333575
    assert payload["summary"][
        "residual_norm_gradient_tiny_sweep_best_l2_improvement_n"
    ] == 0.16379561248899166
    assert payload["summary"]["active_set_ls_sweep_present"] is True
    assert payload["summary"][
        "active_set_ls_sweep_full_inf_descent_observed"
    ] is True
    assert payload["summary"][
        "active_set_ls_sweep_active_inf_descent_observed"
    ] is True
    assert payload["summary"][
        "active_set_ls_sweep_best_full_residual_n"
    ] == 0.4274072503950392
    assert payload["summary"][
        "active_set_ls_sweep_best_full_improvement_n"
    ] == 0.000423153623160033
    assert payload["summary"]["active_set_ls_trust_candidate_present"] is True
    assert payload["summary"][
        "active_set_ls_trust_candidate_checkpoint_written"
    ] is True
    assert payload["summary"][
        "active_set_ls_trust_candidate_final_residual_n"
    ] == 0.42740724991695345
    assert payload["summary"][
        "active_set_ls_trust_candidate_total_reduction_n"
    ] == 0.0004231541012457707
    assert payload["summary"][
        "active_set_ls_trust_candidate_residual_gate_passed"
    ] is False
    assert payload["summary"][
        "active_set_ls_trust_schedule_candidate_present"
    ] is True
    assert payload["summary"][
        "active_set_ls_trust_schedule_candidate_final_residual_n"
    ] == 0.4274072499174437
    assert payload["summary"][
        "active_set_ls_trust_schedule_candidate_active_row_count_schedule"
    ] == [8, 16, 32]
    assert payload["summary"][
        "active_set_ls_trust_tangent_fd_jvp_present"
    ] is True
    assert payload["summary"][
        "active_set_ls_trust_tangent_fd_jvp_fd_consistent"
    ] is True
    assert payload["summary"][
        "active_set_ls_trust_tangent_fd_jvp_evaluated_row_count"
    ] == 2
    assert payload["summary"][
        "active_set_minimax_trust_candidate_present"
    ] is True
    assert payload["summary"][
        "active_set_minimax_trust_candidate_final_residual_n"
    ] == 0.42740724991695345
    assert payload["summary"][
        "active_set_minimax_trust_candidate_steps_taken"
    ] == 0
    assert (
        payload["summary"]["hip_required_full_load_residual_jvp_frontier_present"]
        is True
    )
    assert payload["summary"][
        "hip_required_full_load_residual_jvp_frontier_final_residual_n"
    ] == 5.584111205301272
    assert (
        payload["summary"]["hip_required_full_load_residual_jvp_frontier_residual_gate"]
        is False
    )
    assert (
        payload["summary"][
            "hip_required_full_load_residual_jvp_frontier_global_krylov_hip_solver"
        ]
        is True
    )
    assert (
        payload["summary"][
            "hip_required_full_load_residual_jvp_frontier_hip_components_passed"
        ]
        is True
    )
    assert payload["summary"][
        "hip_required_consistency_direct_probe_final_residual_n"
    ] == 5.571832446441612
    assert (
        payload["summary"]["hip_required_consistency_direct_probe_residual_gate"]
        is False
    )
    assert (
        payload["summary"][
            "hip_required_consistency_direct_probe_worker_path_ready"
        ]
        is True
    )
    assert (
        payload["summary"][
            "hip_required_consistency_direct_probe_jvp_rows_retained"
        ]
        is True
    )
    assert (
        payload["summary"][
            "hip_required_consistency_direct_probe_output_checkpoint_written"
        ]
        is True
    )
    assert payload["summary"]["hip_required_frontier_no_descent_receipt_count"] == 2
    assert (
        payload["summary"]["hip_required_frontier_no_descent_all_no_descent"] is True
    )
    assert payload["summary"][
        "hip_required_scaled_global_krylov_no_descent_final_residual_n"
    ] == 5.571832446349628
    assert payload["summary"][
        "hip_required_scaled_global_krylov_no_descent_best_residual_n"
    ] == 5.572699041492692
    assert (
        payload["summary"][
            "hip_required_scaled_global_krylov_no_descent_output_written"
        ]
        is False
    )
    assert (
        payload["summary"]["current_frontier_operator_mismatch_audit_complete"]
        is True
    )
    assert payload["summary"]["current_frontier_full_load_no_descent"] is True
    assert payload["summary"]["current_frontier_operator_family_no_descent"] is True
    assert payload["summary"][
        "current_frontier_scaled_global_krylov_best_residual_n"
    ] == 5.572699041492692
    assert payload["summary"][
        "current_frontier_row_correction_best_residual_n"
    ] == 5.58261631268956
    assert payload["summary"]["current_frontier_next_required_operator"] == (
        "physical_consistent_frame_shell_material_geometric_with_state_"
        "updated_material_tangent_and_full_residual_globalization"
    )
    assert payload["hip_required_full_load_residual_jvp_frontier"]["load_scale"] == 1.0
    assert payload["hip_required_full_load_residual_jvp_frontier"][
        "final_direct_residual_inf_n"
    ] == 5.584111205301272
    assert payload["hip_required_full_load_residual_jvp_frontier"][
        "matrix_free_global_krylov_hip_solver_used"
    ] is True
    assert payload["hip_required_full_load_residual_jvp_frontier"][
        "current_tangent_residual_row_correction_residual_batch_backend"
    ] == "hip_full_residual"
    assert payload["hip_required_full_load_residual_jvp_frontier"][
        "direct_residual_gate_passed"
    ] is False
    assert payload["hip_required_full_load_residual_jvp_frontier"][
        "consistent_residual_jacobian_newton_passed"
    ] is False
    assert payload["hip_required_full_load_residual_jvp_frontier"][
        "material_newton_breadth_passed"
    ] is False
    assert payload["hip_required_consistency_direct_probe"][
        "final_direct_residual_inf_n"
    ] == 5.571832446441612
    assert payload["hip_required_consistency_direct_probe"][
        "residual_jvp_worker_path_ready"
    ] is True
    assert payload["hip_required_consistency_direct_probe"][
        "matrix_free_global_krylov_jvp_rows_retained"
    ] is True
    assert payload["hip_required_consistency_direct_probe"][
        "output_checkpoint_path"
    ].endswith("mgt_residual_jacobian_step15_material_active_set_ls_rows32_child_direct_candidate.npz")
    assert payload["hip_required_consistency_direct_probe"][
        "direct_residual_gate_passed"
    ] is False
    assert len(payload["hip_required_frontier_no_descent_receipts"]) == 2
    assert payload["hip_required_frontier_no_descent_receipts"][0][
        "variant"
    ] == "unscaled_consistency_wrapper_step16"
    assert payload["hip_required_frontier_no_descent_receipts"][0][
        "no_descent"
    ] is True
    assert payload["hip_required_frontier_no_descent_receipts"][1][
        "variant"
    ] == "scaled_global_krylov_step16"
    assert payload["hip_required_frontier_no_descent_receipts"][1][
        "no_descent"
    ] is True
    assert payload["hip_required_frontier_no_descent_receipts"][1][
        "matrix_free_global_krylov_scaling_mode"
    ] == "residual_diagonal_displacement"
    assert payload["hip_required_frontier_no_descent_receipts"][1][
        "current_tangent_residual_row_best_residual_inf_n"
    ] == 5.58261631268956
    assert payload["current_frontier_operator_mismatch_audit"][
        "audit_complete"
    ] is True
    assert payload["current_frontier_operator_mismatch_audit"][
        "frontier_probe"
    ]["full_load_no_descent"] is True
    assert payload["current_frontier_operator_mismatch_audit"][
        "current_frontier_no_descent"
    ]["global_and_row_operator_family_no_descent"] is True
    assert payload["true_newton_full_load_checkpoint_candidate"]["present"] is True
    assert payload["true_newton_full_load_checkpoint_candidate"][
        "checkpoint_written"
    ] is True
    assert payload["true_newton_full_load_checkpoint_candidate"][
        "checkpoint_schema"
    ] == "mgt-direct-residual-newton-state.v1"
    assert payload["true_newton_from_active_set_ls_trust_candidate"][
        "true_stop_reason"
    ] == "line_search_no_descent"
    assert payload["true_newton_from_active_set_ls_trust_candidate"][
        "max_regularized_linear_solve_relative_inf"
    ] == 3.197442310920451e-14
    assert payload["true_newton_from_active_set_ls_trust_candidate"][
        "dominant_jvp_gap_top_node_id"
    ] == 12385
    assert payload["true_newton_from_active_set_ls_trust_candidate"][
        "dominant_jvp_gap_component"
    ] == "frame"
    assert payload[
        "true_newton_from_active_set_service_tangent_ls_trust_candidate"
    ]["dominant_jvp_gap_top_node_id"] == 1420
    assert payload["true_newton_frame_tangent_source_comparison"][
        "service_minus_force_max_jvp_gap_relative_inf"
    ] == 5.3454439040478974e-05
    assert payload["frame_tangent_fd_epsilon_sweep"]["best_eps"] == 0.001
    assert (
        payload["frame_tangent_fd_epsilon_sweep"]["default_eps_artifact_likely"]
        is True
    )
    assert payload["true_newton_from_active_set_mu_sweep"][
        "factorable_mu_count"
    ] == 11
    assert (
        payload["true_newton_from_active_set_mu_sweep"]["descent_observed"]
        is False
    )
    assert payload["active_set_load_parameter_probe"][
        "actual_replay_descent_observed"
    ] is False
    assert payload["active_set_load_parameter_tiny_trust_probe"][
        "actual_replay_descent_observed"
    ] is True
    assert payload["active_set_load_parameter_tiny_trust_probe"][
        "restored_full_load_descent_observed"
    ] is False
    assert payload["active_frontier_residual_ownership_probe"][
        "top_row_balance_driver"
    ] == "external_load_balance"
    assert payload["active_frontier_residual_ownership_probe"][
        "top_row_dominant_internal_component"
    ] == "shell_bending_drilling"
    assert payload["active_frontier_shell_load_neighborhood_probe"][
        "top_row_surface_component_free_pressure_resultant"
    ] is True
    assert payload["active_frontier_shell_load_neighborhood_probe"][
        "top_incident_element_id"
    ] == 25880
    assert payload["active_frontier_shell_policy_replay_probe"][
        "structural_or_attached_policy_descent_observed"
    ] is True
    assert payload["active_frontier_shell_policy_replay_probe"][
        "best_residual_gate_passed"
    ] is False
    assert payload[
        "active_frontier_shell_policy_linearized_active_set_probe"
    ]["linearized_active_descent_observed"] is True
    assert payload[
        "active_frontier_shell_policy_linearized_active_set_probe"
    ]["direct_replay_required_for_candidate"] is True
    assert payload[
        "active_frontier_structural_policy_active_set_ls_trust_candidate"
    ]["final_residual_n"] == 0.07205501101467937
    assert payload[
        "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep"
    ]["stop_reason"] == "no_candidate_descent"
    assert payload[
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
    ]["state_updated_material_direct_residual_inf_n"] == 44.08048153349253
    assert payload[
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
    ]["direct_residual_gate_passed"] is False
    assert payload[
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
    ]["consistent_residual_jacobian_newton_passed"] is False
    assert payload[
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
    ]["residual_component_breakdown_included"] is True
    assert payload[
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
    ]["top_row_dominant_component"] == "shell_bending_drilling"
    assert payload[
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
    ]["top_row_component_values_n"]["shell_membrane"] == -72233.54910141167
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_probe"
    ]["row_correction_accepted"] is True
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_probe"
    ]["accepted_state_refresh_cpu_used"] is True
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_probe"
    ]["output_checkpoint_path"].endswith(
        "g1_active_frontier_structural_policy_active_set_current_component_row_correction_candidate.npz"
    )
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe"
    ]["row_correction_accepted"] is True
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe"
    ]["final_direct_residual_inf_n"] == 43.816671401648165
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe"
    ]["output_checkpoint_path"].endswith(
        "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step2_candidate.npz"
    )
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe"
    ]["row_correction_accepted"] is False
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe"
    ]["row_correction_stop_reason"] == "no_residual_descent"
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe"
    ]["best_candidate_direct_residual_inf_n"] == 43.883829113147186
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe"
    ]["output_checkpoint_written"] is False
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_chain"
    ]["accepted_step_count"] == 2
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_chain"
    ]["no_descent_step_count"] == 1
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_chain"
    ]["latest_accepted_final_residual_inf_n"] == 43.816671401648165
    assert payload[
        "active_frontier_structural_policy_active_set_current_component_row_correction_chain"
    ]["first_no_descent_best_residual_inf_n"] == 43.883829113147186
    assert (
        payload[
            "active_frontier_structural_policy_active_set_current_component_row_correction_chain"
        ]["first_no_descent_stop_reason"]
        == "no_residual_descent"
    )
    assert payload[
        "active_frontier_structural_policy_residual_ownership_probe"
    ]["top_row_balance_driver"] == "shell_bending_drilling_internal_force"
    assert payload[
        "active_frontier_structural_policy_linearized_active_set_after_two_step_probe"
    ]["best_linear_active_residual_after_inf_n"] == 3.396605913197348e-13
    assert payload[
        "active_frontier_structural_policy_shell_rotation_row_candidate"
    ]["best_direct_residual_inf_n"] == 0.04728610099315822
    assert payload[
        "active_frontier_structural_policy_shell_rotation_row_candidate"
    ]["fd_consistent"] is True
    assert payload[
        "active_frontier_structural_policy_shell_rotation_row_candidate"
    ]["checkpoint_best_alpha"] == 0.125
    assert payload[
        "active_frontier_structural_policy_shell_rotation_row_no_descent_probe"
    ]["direct_descent_observed"] is False
    assert payload[
        "active_frontier_structural_policy_shell_rotation_row_no_descent_probe"
    ]["checkpoint_accepted_iteration_count"] == 0
    assert payload[
        "active_frontier_structural_policy_shell_rotation_candidate_residual_ownership_probe"
    ]["top_row_balance_driver"] == "shell_bending_drilling_internal_force"
    assert payload["sparse_direct_scaled_lsmr_frontier_probe"][
        "line_search_residual_after_n"
    ] == 0.04728606850215522
    assert payload["sparse_direct_scaled_lsmr_frontier_probe"][
        "line_search_residual_reduction_ratio"
    ] == 6.871152900485691e-07
    assert payload["sparse_direct_scaled_lsmr_frontier_probe"][
        "promotes_g1_closure"
    ] is False
    assert payload["sparse_direct_scaled_lsmr_frontier_probe"][
        "output_checkpoint_written"
    ] is True
    assert payload["sparse_direct_scaled_lsmr_frontier_probe"][
        "output_checkpoint_direct_residual_inf_n"
    ] == 0.04728606850215522
    assert payload["sparse_direct_scaled_lsmr_second_probe"][
        "line_search_residual_after_n"
    ] == 0.047285916814733264
    assert payload["sparse_direct_scaled_lsmr_second_probe"][
        "output_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
    )
    assert payload["sparse_direct_scaled_lsmr_third_probe"][
        "line_search_residual_after_n"
    ] == 0.047285863685509466
    assert payload["sparse_direct_scaled_lsmr_chain"][
        "monotonic_residual_descent"
    ] is True
    assert payload["sparse_direct_scaled_lsmr_chain"][
        "latest_checkpoint_path"
    ].endswith(
        "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz"
    )
    assert payload["sparse_direct_scaled_lsmr_chain_probe"][
        "latest_checkpoint_path"
    ].endswith("g1_mgt_sparse_direct_scaled_lsmr_chain_step_03_candidate.npz")
    assert payload["sparse_direct_scaled_lsmr_long_chain_probe"][
        "latest_checkpoint_path"
    ].endswith("g1_mgt_sparse_direct_scaled_lsmr_long_chain_step_10_candidate.npz")
    assert (
        payload["sparse_direct_scaled_lsmr_long_chain_probe"][
            "gate_convergence_assessment"
        ]
        == "stalled_for_gate"
    )
    assert (
        payload["sparse_direct_scaled_lsmr_long_chain_probe"][
            "recommended_next_action"
        ]
        == "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
    )
    assert (
        payload["sparse_direct_scaled_lsmr_from_incomplete_preview_probe"][
            "output_checkpoint_direct_residual_inf_n"
        ]
        == 0.0033227123724053342
    )
    assert payload["sparse_direct_scaled_lsmr_from_incomplete_preview_probe"][
        "output_checkpoint_path"
    ].endswith("g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_candidate.npz")
    assert (
        payload["sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe"][
            "latest_checkpoint_path"
        ].endswith(
            "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_chain_step_10_candidate.npz"
        )
    )
    assert (
        payload["sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe"][
            "recommended_next_action"
        ]
        == "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
    )
    assert payload["sparse_direct_shifted_splu_from_gate_candidate_step2_probe"][
        "output_checkpoint_path"
    ].endswith("g1_mgt_sparse_direct_shifted_splu_mu_1e_4_from_gate_candidate_step2_candidate.npz")
    assert (
        payload["sparse_direct_shifted_splu_from_gate_candidate_step2_probe"][
            "recommended_next_action"
        ]
        == "run_full_load_lane_material_mesh_hip_proofs_from_shifted_splu_gate_checkpoint"
    )
    assert (
        payload["sparse_direct_adaptive_jvp_eps_gmres_ilu_probe"][
            "recommended_next_action"
        ]
        == "replace_or_shift_preconditioner_family_before_more_gmres_iterations"
    )
    assert (
        payload["sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe"][
            "recommended_next_action"
        ]
        == "avoid_matrix_free_only_retry_until_operator_preconditioner_changes"
    )
    assert (
        payload["sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe"][
            "preconditioner_mode"
        ]
        == "shifted_ilu"
    )
    assert (
        payload["sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe"][
            "recommended_next_action"
        ]
        == "tune_shift_or_multilevel_preconditioner_before_accepting_shifted_ilu_direction"
    )
    assert (
        payload[
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe"
        ]["line_search_residual_after_n"]
        == 0.0033228596775920494
    )
    assert (
        payload[
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe"
        ]["output_checkpoint_direct_residual_inf_n"]
        == 0.0033228596775920494
    )
    assert (
        payload[
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe"
        ]["incomplete_direction_preview"]
        is True
    )
    assert payload["adaptive_all_components_frontier"] == {
        "path": runner.DEFAULT_ADAPTIVE_ALL_COMPONENTS_FRONTIER.as_posix(),
        "present": True,
        "status": "review",
        "reason_code": "no_candidate_descent",
        "promotes_g1_closure": False,
        "shell_pressure_load_path_policy": "all_components",
        "frame_tangent_source": "force_based_residual_tangent",
        "initial_residual_n": 0.5698763332807477,
        "final_residual_n": 0.4278304040181992,
        "total_reduction_ratio": 0.24925746336016033,
        "residual_gate_passed": False,
        "stop_reason": "no_candidate_descent",
        "steps_taken": 38,
        "checkpoint_written": True,
        "checkpoint_path": (
            "implementation/phase1/release_evidence/productization/"
            "g1_adaptive_fixed_signed_all_components_from_structural_60step_diagnostic.npz"
        ),
        "checkpoint_load_scale": 1.0,
        "checkpoint_direct_residual_inf_n": 0.4278304040181992,
        "checkpoint_residual_gate_passed": False,
        "claim_boundary": "adaptive all-components fixture; not a G1 closure",
    }
    assert payload["shell_hotspot_tangent_fd_jvp"]["fd_consistent"] is True
    assert payload["shell_hotspot_tangent_fd_jvp"]["component_filter"] == (
        "shell_bending_drilling"
    )
    assert payload["shell_hotspot_tangent_fd_jvp"][
        "max_relative_inf_error"
    ] == 7.82988821999408e-14
    assert payload["shell_hotspot_diagonal_sweep"]["descent_observed"] is False
    assert payload["shell_hotspot_diagonal_sweep"][
        "best_improvement_inf_n"
    ] == -2.0477105863392353e-05
    assert payload["shell_hotspot_diagonal_sweep"]["component_filter"] == (
        "shell_bending_drilling"
    )
    assert payload["global_tangent_scaled_sweep"]["scaling_mode"] == "row_col_inf"
    assert payload["global_tangent_scaled_sweep"]["descent_observed"] is False
    assert payload["global_tangent_scaled_sweep"][
        "solver_iteration_count"
    ] == 128
    assert payload["global_tangent_scaled_sweep"][
        "best_improvement_inf_n"
    ] == -2.483773187123006e-10
    assert payload["residual_norm_gradient_tiny_sweep"][
        "l2_descent_observed"
    ] is True
    assert payload["residual_norm_gradient_tiny_sweep"][
        "inf_descent_observed"
    ] is False
    assert payload["residual_norm_gradient_tiny_sweep"][
        "best_l2_relative_improvement_l2"
    ] == 0.11871229307225273
    assert payload["active_set_ls_sweep"]["full_inf_descent_observed"] is True
    assert payload["active_set_ls_sweep"][
        "best_full_direct_residual_inf_n"
    ] == 0.4274072503950392
    assert payload["active_set_ls_sweep"][
        "best_full_improvement_inf_n"
    ] == 0.000423153623160033
    assert payload["active_set_ls_trust_candidate"]["checkpoint_written"] is True
    assert payload["active_set_ls_trust_candidate"][
        "final_residual_n"
    ] == 0.42740724991695345
    assert payload["active_set_ls_trust_candidate"][
        "checkpoint_path"
    ].endswith("active_set_ls_trust_candidate.npz")
    assert payload["active_set_ls_trust_schedule_candidate"][
        "active_row_count_schedule"
    ] == [8, 16, 32]
    assert payload["active_set_ls_trust_schedule_candidate"][
        "final_residual_n"
    ] == 0.4274072499174437
    assert payload["active_set_ls_trust_tangent_fd_jvp"][
        "base_residual_inf_n"
    ] == 0.42740724991695345
    assert payload["active_set_ls_trust_tangent_fd_jvp"][
        "fd_consistent"
    ] is True
    assert payload["active_set_ls_trust_tangent_fd_jvp"][
        "max_relative_inf_error"
    ] == 5.0e-14
    assert payload["active_set_ls_trust_tangent_fd_jvp"][
        "consistent_residual_jacobian_newton_gate_passed"
    ] is False
    assert payload["active_set_minimax_trust_candidate"][
        "status"
    ] == "review"
    assert payload["active_set_minimax_trust_candidate"][
        "steps_taken"
    ] == 0
    assert payload["active_set_minimax_trust_candidate"][
        "best_linear_active_inf_improvement_n"
    ] == 1.1784706543949142e-10
    assert payload["active_set_minimax_trust_candidate"][
        "best_support_column_count"
    ] == 143
    assert payload["assembly_contract_seed"] == {
        "path": paths["assembly"].as_posix(),
        "status": "ready",
        "contract_pass": True,
        "promotes_g1_closure": False,
        "phase_covered": "phase1_phase2_cpu_seed_contract_and_newton_parity",
        "residual_formula": "F_internal_minus_F_external",
        "fixed_point_residual_promoted_to_physical": False,
        "regularized_fixed_point_substitute": False,
        "cpu_seed_consistent_newton_gate_passed": True,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "case_count": 2,
    }
    assert payload["summary"]["assembly_contract_seed_ready"] is True
    assert payload["summary"]["assembly_contract_cpu_seed_newton_gate_passed"] is True
    assert payload["summary"]["live_g1_assembly_contract_present"] is True
    assert payload["summary"]["live_g1_assembly_contract_passed"] is True
    assert payload["live_g1_assembly_contract"]["contract_pass"] is True
    assert payload["live_g1_assembly_contract"]["assembly_result_schema"] == (
        "g1-assembly-result.v1"
    )
    assert payload["live_g1_assembly_contract"]["required_fields_present"] is True
    assert payload["hip_worker_contract"]["residual_jvp_worker_path_ready"] is True
    assert payload["hip_worker_contract"]["g1_closure_gate_ready"] is False
    assert payload["worker_path_repair_plan"] == {
        "schema_version": "g1-production-rocm-hip-worker-path-repair-plan.v1",
        "status": "ready",
        "next_action_id": "rerun_g1_full_load_hip_newton_lane",
        "blocker_count": 0,
        "blockers": [],
        "category_count": 0,
        "category_order": [],
        "category_counts": {},
        "categories": {},
        "runtime_blockers": [],
        "required_receipts": [
            paths["hip"].as_posix(),
            "implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json",
        ],
        "claim_boundary": (
            "This repair plan classifies the missing production ROCm/HIP residual/JVP "
            "worker path. It does not execute HIP, prove device residency, create a "
            "full-load checkpoint, or promote G1 closure."
        ),
    }
    assert payload["next_actions"][0]["required_receipts"] == [
        paths["assembly"].as_posix(),
        paths["hip"].as_posix(),
    ]
    assert payload["next_actions"][1]["gap_to_required_load_scale"] == 0.344
    assert payload["next_actions"][2]["required_receipts"] == [
        paths["assembly"].as_posix(),
        paths["hip"].as_posix()
    ]
    assert "g1_assembly_contract_seed_report_contract_passes" in payload[
        "runner_contract"
    ]["acceptance_criteria"]
    assert "cpu_seed_direct_residual_newton_parity_passes" in payload[
        "runner_contract"
    ]["acceptance_criteria"]
    assert "checkpoint_load_scale_gte_1p0" in payload["runner_contract"][
        "acceptance_criteria"
    ]
    assert "consistent_residual_jacobian_newton_gate_not_passed" in payload[
        "closure_blockers"
    ]
    sequence = payload["worker_path_operator_sequence"]
    assert [row["step_id"] for row in sequence] == [
        "verify_rocm_runtime_device_interface",
        "run_hip_required_direct_probe",
        "refresh_runner_contract_after_hip_probe",
        "rerun_g1_full_load_lane_with_full_load_checkpoint",
    ]
    assert sequence[0]["status"] == "ready"
    assert sequence[1]["status"] == "ready"
    assert "--require-hip-residual-engine" in sequence[1]["command"]
    assert "--hip-runtime-preflight-only" not in sequence[1]["command"]
    assert sequence[2]["required_receipts"] == [
        paths["hip"].as_posix(),
        runner.DEFAULT_OUT.as_posix(),
    ]


def test_runner_packet_accepts_missing_generator_action_after_full_load_checkpoint_ready(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path, action_id=None)
    lane = _g1_lane_payload(action_id=None)
    lane["blockers"] = ["hip_consistency_proof_gate_not_passed"]
    lane["checkpoint_resolution_gate"] = {
        "mode": "explicit",
        "passed": True,
        "required_load_scale": 1.0,
        "highest_observed_load_scale": 1.0,
        "highest_observed_gap_to_required_load_scale": 0.0,
        "full_load_candidate_count": 1,
    }
    _write_json(paths["g1_lane"], lane)

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        assembly_contract_seed_path=paths["assembly"],
        true_newton_load_sweep_path=paths["sweep"],
        true_newton_full_load_checkpoint_candidate_path=paths["checkpoint_candidate"],
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["highest_observed_load_scale"] == 1.0
    assert payload["summary"]["full_load_candidate_count"] == 1
    assert "consistent_newton_runner_next_action_missing" not in payload["blockers"]


def test_runner_packet_blocks_without_live_assembly_contract_receipt(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path)
    hip_payload = json.loads(paths["hip"].read_text(encoding="utf-8"))
    hip_payload.pop("live_g1_assembly_contract")
    _write_json(paths["hip"], hip_payload)

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        assembly_contract_seed_path=paths["assembly"],
        true_newton_load_sweep_path=paths["sweep"],
        true_newton_full_load_checkpoint_candidate_path=paths["checkpoint_candidate"],
    )

    assert payload["status"] == "blocked_runner_contract"
    assert payload["contract_pass"] is False
    assert "live_g1_assembly_contract_receipt_missing" in payload["blockers"]
    assert payload["summary"]["live_g1_assembly_contract_present"] is False
    assert payload["summary"]["live_g1_assembly_contract_passed"] is False
    assert payload["live_g1_assembly_contract"]["contract_pass"] is False
    assert payload["live_g1_assembly_contract"]["blockers"] == [
        "live_g1_assembly_contract_receipt_missing"
    ]


def test_runner_packet_classifies_blocked_worker_path_repair_plan(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    hip_payload = json.loads(paths["hip"].read_text(encoding="utf-8"))
    worker = hip_payload["production_rocm_hip_residual_jvp_worker"]
    worker["residual_jvp_worker_path_ready"] = False
    worker["residual_jvp_worker_path_blockers"] = [
        "rocm_hip_runtime_unavailable",
        "runtime::dev_kfd_missing",
        "direct_probe_not_executed_preflight_only",
        "production_hip_residual_jacobian_path_not_proven",
        "global_krylov_jvp_rows_not_retained",
        "current_tangent_residual_row_hip_replay_not_proven",
    ]
    worker["runtime"] = {"runtime_blockers": ["dev_kfd_missing"]}
    _write_json(paths["hip"], hip_payload)

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        assembly_contract_seed_path=paths["assembly"],
        true_newton_load_sweep_path=paths["sweep"],
        true_newton_full_load_checkpoint_candidate_path=paths["checkpoint_candidate"],
    )

    assert payload["status"] == "blocked_runner_contract"
    assert (
        "production_rocm_hip_residual_jvp_worker_path_not_ready"
        in payload["blockers"]
    )
    repair = payload["worker_path_repair_plan"]
    assert repair["status"] == "blocked"
    assert repair["next_action_id"] == "repair_production_rocm_hip_residual_jvp_worker_path"
    assert repair["blocker_count"] == 6
    assert repair["category_counts"] == {
        "runtime_device_interface": 2,
        "hip_required_direct_probe": 1,
        "production_hip_residual_jacobian_path": 1,
        "matrix_free_global_krylov": 1,
        "current_tangent_residual_row_replay": 1,
    }
    assert repair["runtime_blockers"] == ["dev_kfd_missing"]
    assert repair["categories"]["matrix_free_global_krylov"]["acceptance"] == [
        "matrix_free_global_krylov.proof.hip_krylov_solver_used == true",
        "matrix_free_global_krylov.proof.jvp_rows_retained == true",
        "accepted-state tangent refresh uses HIP, not CPU",
    ]
    sequence = payload["worker_path_operator_sequence"]
    assert sequence[0]["status"] == "required"
    assert sequence[0]["clears_categories"] == ["runtime_device_interface"]
    assert "--hip-runtime-preflight-only" in sequence[0]["command"]
    assert sequence[1]["status"] == "required"
    assert "matrix_free_global_krylov" in sequence[1]["clears_categories"]
    assert payload["summary"]["worker_path_repair_blocker_count"] == 6
    assert payload["summary"]["worker_path_repair_category_count"] == 5
    assert (
        payload["summary"]["worker_path_repair_next_action_id"]
        == "repair_production_rocm_hip_residual_jvp_worker_path"
    )


def test_runner_packet_blocks_when_lane_does_not_route_to_runner(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path, action_id="generate_full_load_1p0_checkpoint_candidate")

    payload = runner.build_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        assembly_contract_seed_path=paths["assembly"],
        true_newton_load_sweep_path=paths["sweep"],
        true_newton_full_load_checkpoint_candidate_path=paths["checkpoint_candidate"],
    )

    assert payload["status"] == "blocked_runner_contract"
    assert payload["contract_pass"] is False
    assert "consistent_newton_runner_next_action_missing" in payload["blockers"]


def test_runner_packet_writes_json_and_markdown(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    out = tmp_path / "runner.json"
    out_md = tmp_path / "runner.md"

    payload = runner.write_runner_packet(
        repo_root=tmp_path,
        g1_lane_path=paths["g1_lane"],
        cause_narrowing_path=paths["cause"],
        hip_probe_path=paths["hip"],
        global_connectivity_path=paths["global"],
        assembly_contract_seed_path=paths["assembly"],
        true_newton_load_sweep_path=paths["sweep"],
        true_newton_full_load_checkpoint_candidate_path=paths["checkpoint_candidate"],
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        runner.SCHEMA_VERSION
    )
    markdown = out_md.read_text(encoding="utf-8")
    assert "# G1 Consistent Newton Full-Load Runner Contract" in markdown
    assert runner.RUNNER_ID in markdown
    assert "## Next Actions" in markdown
    assert "promote_g1_assembly_contract_to_live_runner" in markdown
    assert "generate_full_load_1p0_checkpoint_candidate" in markdown
    assert "## Worker Path Operator Sequence" in markdown
    assert "run_hip_required_direct_probe" in markdown
    assert "## True-Newton Load Sweep" in markdown
    assert "## True-Newton Checkpoint Candidate" in markdown
    assert "checkpoint_direct_residual_inf_n" in markdown
    assert "full_load_true_newton_residual_descent_observed" in markdown
    assert "## Shell Hotspot Narrowing" in markdown
    assert "shell_hotspot_diagonal_sweep_descent" in markdown
    assert "## Global Tangent Sweep" in markdown
    assert "global_tangent_scaled_sweep_descent" in markdown
    assert "## Residual-Norm Gradient Sweep" in markdown
    assert "residual_norm_gradient_l2_descent" in markdown
    assert "## Active-Set LS Sweep" in markdown
    assert "active_set_ls_full_inf_descent" in markdown
    assert "## Active-Set LS Trust Candidate" in markdown
    assert "active_set_ls_trust_candidate_final_residual_n" in markdown
    assert "## Active-Set LS Schedule Candidate" in markdown
    assert "## Active Frontier Residual Ownership" in markdown
    assert "active_frontier_residual_ownership_top_row_balance_driver" in markdown
    assert "## Active Frontier Shell Load Neighborhood" in markdown
    assert "active_frontier_shell_load_required_scale" in markdown
    assert "## Active Frontier Shell Policy Replay" in markdown
    assert "active_frontier_shell_policy_best_policy" in markdown
    assert "## Active Frontier Shell Policy Linearized Active-Set" in markdown
    assert "## Active Frontier Shell Rotation Row Candidate" in markdown
    assert "shell_rotation_row_second_candidate.npz" in markdown
    assert "## Active Frontier Shell Rotation Row No-Descent Probe" in markdown
    assert "## Active Frontier Shell Rotation Candidate Residual Ownership" in markdown
    assert "active_frontier_shell_policy_linearized_best_after_n" in markdown
    assert "## Active Frontier Structural Policy Active-Set LS Trust" in markdown
    assert "active_frontier_structural_policy_active_set_final_residual_n" in markdown
    assert "## Active Frontier Structural Policy Alpha Sweep" in markdown
    assert (
        "## Active Frontier Structural Policy State-Updated Direct Replay"
        in markdown
    )
    assert (
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_residual_n"
        in markdown
    )
    assert "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_component" in markdown
    assert "top_row_component_values_n" in markdown
    assert (
        "## Active Frontier Structural Policy Current Component Row Correction"
        in markdown
    )
    assert (
        "active_frontier_structural_policy_active_set_current_component_row_correction_final_residual_n"
        in markdown
    )
    assert (
        "## Active Frontier Structural Policy Current Component Row Correction Step 2"
        in markdown
    )
    assert (
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_final_residual_n"
        in markdown
    )
    assert (
        "## Active Frontier Structural Policy Current Component Row Correction Step 3"
        in markdown
    )
    assert "no_residual_descent" in markdown
    assert (
        "## Active Frontier Structural Policy Current Component Row Correction Chain"
        in markdown
    )
    assert "first_no_descent_best_residual_inf_n" in markdown
    assert "## Active Frontier Structural Policy Residual Ownership" in markdown
    assert "shell_bending_drilling_internal_force" in markdown
    assert "## Active Frontier Structural Policy Linearized After Two-Step" in markdown
    assert "## Sparse Direct Scaled-LSMR Frontier Probe" in markdown
    assert "line_search_residual_reduction_ratio" in markdown
    assert "output_checkpoint_written" in markdown
    assert "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz" in markdown
    assert "## Sparse Direct Scaled-LSMR Second Step Probe" in markdown
    assert "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz" in markdown
    assert "## Sparse Direct Scaled-LSMR Accepted-Step Chain" in markdown
    assert "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz" in markdown
    assert "## Sparse Direct Scaled-LSMR Chain Receipt" in markdown
    assert "g1_mgt_sparse_direct_scaled_lsmr_chain_probe.json" in markdown
    assert "## Sparse Direct Scaled-LSMR Long-Chain Receipt" in markdown
    assert "g1_mgt_sparse_direct_scaled_lsmr_long_chain_step_10_candidate.npz" in markdown
    assert "## Sparse Direct Adaptive-JVP GMRES Receipts" in markdown
    assert "ERR_ILU_FACTOR_FAILED" in markdown
    assert "gmres_shifted_ilu" in markdown
    assert "0.0001237155747730867" in markdown
    assert "## HIP-Required Full-Load Residual/JVP Frontier" in markdown
    assert "hip_required_full_load_residual_jvp_frontier_final_residual_n" in markdown
    assert "5.584111205301272" in markdown
    assert "matrix_free_global_krylov_hip_solver_used" in markdown
    assert "does not close G1" in markdown
    assert "## HIP-Required Consistency Direct Probe" in markdown
    assert "hip_required_consistency_direct_probe_final_residual_n" in markdown
    assert "5.571832446441612" in markdown
    assert "matrix_free_global_krylov_jvp_rows_retained" in markdown
    assert "mgt_residual_jacobian_step15_material_active_set_ls_rows32_child_direct_candidate.npz" in markdown
    assert "## HIP-Required Frontier No-Descent Receipts" in markdown
    assert "unscaled_consistency_wrapper_step16.no_descent" in markdown
    assert "scaled_global_krylov_step16.no_descent" in markdown
    assert "residual_diagonal_displacement" in markdown
    assert "5.572699041492692" in markdown
    assert "5.58261631268956" in markdown
    assert "mgt_residual_jacobian_step16_scaled_global_krylov_candidate.npz" in markdown
    assert "## Current Frontier Operator Mismatch Audit" in markdown
    assert "current_frontier_operator_mismatch_audit_complete" in markdown
    assert "current_frontier_operator_family_no_descent" in markdown
    assert "physical_consistent_frame_shell_material_geometric" in markdown
    assert "frame_service_material_tangent_reduced_below_elastic" in markdown
    assert payload["status"] == "ready_for_runner_implementation"
