"""Tests for commercial solver and AI-engine gap-ledger status."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from implementation.phase1.commercial_gap_ledger_status import (
    build_commercial_gap_ledger_status,
    inference_runtime_contract_closed,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_commercial_gap_ledger_status_covers_all_documented_gaps() -> None:
    payload = build_commercial_gap_ledger_status()
    assert payload["schema_version"] == "commercial-gap-ledger-status.v1"
    assert payload["doc_requirements"]["missing_doc_ids"] == []
    assert payload["doc_requirements"]["missing_status_ids"] == []
    ids = {row["id"] for row in payload["rows"]}
    assert {f"G{idx}" for idx in range(1, 11)} <= ids
    assert {f"AI-G{idx}" for idx in range(1, 11)} <= ids
    assert payload["summary"]["total_count"] == len(payload["rows"])
    assert payload["summary"]["total_count"] >= 20
    assert payload["full_gap_ledger_ready"] is False
    assert payload["status"] == "open"


def test_ai_inference_runtime_closed_allows_success_without_fallback_reason() -> None:
    receipt = {
        "schema_version": "ai-inference-runtime-receipt.v1",
        "status": "ready",
        "runtime_budget_contract": {
            "latency_budget_ms": 250,
            "memory_budget_mb": 512,
            "cpu_gpu_parity_policy": "required_before_production_promotion",
        },
    }
    assert inference_runtime_contract_closed(receipt) is True

    receipt["fallback_reason"] = ""
    assert inference_runtime_contract_closed(receipt) is True

    receipt["fallback_required"] = True
    assert inference_runtime_contract_closed(receipt) is False
    receipt["fallback_reason"] = "ood_solver_replay_required"
    assert inference_runtime_contract_closed(receipt) is True


def test_commercial_gap_ledger_status_is_honest_about_current_blockers() -> None:
    payload = build_commercial_gap_ledger_status()
    rows = {row["id"]: row for row in payload["rows"]}
    assert rows["G1"]["status"] in {"open", "partial"}
    assert rows["G1"]["evidence"]["nonlinear_equilibrium"] is False
    assert rows["G1"]["evidence"]["partial_connected_component_mesh"] is True
    assert rows["G1"]["evidence"]["full_line_mesh_sparse_elastic_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["full_line_mesh_linearized_geometric_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["full_line_mesh_nonlinear_equilibrium"] is False
    assert rows["G1"]["evidence"]["full_line_geometric_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert rows["G1"]["evidence"]["full_line_linearized_geometric_tangent"]["positive_axial_element_count"] > 0
    assert rows["G1"]["evidence"]["full_frame_6dof_sparse_elastic_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["full_frame_6dof_linearized_geometric_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["full_frame_6dof_deformed_state_pdelta_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["full_frame_6dof_nonlinear_equilibrium"] is False
    assert rows["G1"]["evidence"]["surface_membrane_tangent_ready"] is True
    assert rows["G1"]["evidence"]["surface_membrane_smoke_solve_ready"] is True
    assert rows["G1"]["evidence"]["surface_shell_full_bending_tangent_ready"] is False
    assert rows["G1"]["evidence"]["surface_shell_bending_drilling_smoke_ready"] is True
    assert rows["G1"]["evidence"]["surface_shell_transverse_pressure_smoke_ready"] is True
    assert rows["G1"]["evidence"]["shell_calibration_benchmarks_status"] == "ready"
    assert rows["G1"]["evidence"]["shell_calibration_benchmarks_ready"] is True
    assert rows["G1"]["evidence"]["shell_calibration_ready_case_count"] >= 5
    plate_cases = {
        row["case_id"]: row for row in rows["G1"]["evidence"]["shell_calibration_cases"]
    }
    assert plate_cases["clamped_square_plate_uniform_pressure"]["relative_error"] <= 0.15
    assert rows["G1"]["evidence"]["coupled_frame_surface_sparse_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["coupled_frame_surface_nonlinear_equilibrium"] is False
    assert rows["G1"]["evidence"]["full_frame_6dof_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert rows["G1"]["evidence"]["coupled_frame_surface_equilibrium_metrics"]["relative_residual_inf"] <= 2.0e-8
    assert rows["G1"]["evidence"]["full_frame_6dof_geometric_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert rows["G1"]["evidence"]["full_frame_6dof_linearized_geometric_tangent"]["positive_axial_element_count"] > 0
    assert rows["G1"]["evidence"]["full_frame_6dof_deformed_state_pdelta_path"]["load_scale_reached"] >= 0.5
    assert rows["G1"]["evidence"]["pdelta_continuation_status"] == "partial"
    assert rows["G1"]["evidence"]["full_load_pdelta_continuation_ready"] is False
    assert rows["G1"]["evidence"]["pdelta_direct_load_step_max_converged_load_scale"] == 0.5
    assert (
        abs(rows["G1"]["evidence"]["pdelta_continuation_max_converged_load_scale"] - 0.50765625)
        <= 1.0e-12
    )
    assert rows["G1"]["evidence"]["pdelta_continuation_first_failed_load_scale"] == 0.55
    assert rows["G1"]["evidence"]["full_load_nonlinear_newton_ready"] is False
    g1_micro = rows["G1"]["evidence"]["pdelta_post_converged_micro_step_probe"]
    assert g1_micro["ready"] is True
    assert g1_micro["target_load_scale"] == 0.505
    assert g1_micro["near_displacement_fixed_point"] is True
    assert g1_micro["residual_floor_above_tolerance"] is False
    assert g1_micro["residual_inf_n"] <= g1_micro["residual_tolerance_n"]
    assert g1_micro["linear_solver_refinement"]["max_iterations"] == 10
    assert g1_micro["convergence_increment_metric"] == "unrelaxed_fixed_point_relative_increment"
    g1_adaptive = rows["G1"]["evidence"]["pdelta_adaptive_micro_continuation_probe"]
    assert g1_adaptive["ready"] is False
    assert g1_adaptive["max_converged_load_scale"] == 0.505
    assert abs(g1_adaptive["first_failed_load_scale"] - 0.51) <= 1.0e-12
    assert g1_adaptive["accepted_step_count"] == 1
    assert g1_adaptive["rows"][1]["relative_increment"] > 0.5
    g1_relaxation = rows["G1"]["evidence"]["pdelta_post_failed_relaxation_sensitivity_probe"]
    assert g1_relaxation["ready"] is False
    assert g1_relaxation["target_load_scale"] == 0.5075
    assert g1_relaxation["relaxation_factors"] == [0.25]
    assert g1_relaxation["best_relative_increment"] < g1_adaptive["rows"][2]["relative_increment"]
    g1_secant = rows["G1"]["evidence"]["pdelta_secant_predictor_probe"]
    assert g1_secant["ready"] is True
    assert g1_secant["target_load_scale"] == 0.5075
    assert abs(g1_secant["extrapolation_factor"] - 0.5) <= 1.0e-12
    assert g1_secant["residual_gate_passed_by_any"] is True
    assert g1_secant["relative_increment_gate_passed_by_any"] is True
    assert g1_secant["accepted_as_path_state"] is True
    assert g1_secant["accepted_load_scale"] == 0.5075
    assert g1_secant["best_residual_inf_n"] < g1_relaxation["best_residual_inf_n"]
    g1_secant_micro = rows["G1"]["evidence"]["pdelta_secant_micro_continuation_probe"]
    assert g1_secant_micro["ready"] is False
    assert g1_secant_micro["max_converged_load_scale"] == 0.5075
    assert abs(g1_secant_micro["first_failed_load_scale"] - 0.51) <= 1.0e-12
    assert g1_secant_micro["accepted_step_count"] == 0
    assert g1_secant_micro["rows"][0]["residual_gate_passed_by_any"] is True
    assert g1_secant_micro["rows"][0]["relative_increment_gate_passed_by_any"] is False
    g1_fine_secant_micro = rows["G1"]["evidence"][
        "pdelta_fine_secant_micro_continuation_probe"
    ]
    assert g1_fine_secant_micro["ready"] is False
    assert abs(g1_fine_secant_micro["max_converged_load_scale"] - 0.50765625) <= 1.0e-12
    assert g1_fine_secant_micro["accepted_step_count"] == 1
    assert g1_fine_secant_micro["rows"][2]["ready"] is True
    assert g1_fine_secant_micro["rows"][2]["best_residual_inf_n"] <= 1.0e-3
    assert g1_fine_secant_micro["rows"][2]["best_relative_increment"] <= 1.0e-4
    assert g1_fine_secant_micro["rows"][3]["ready"] is False
    g1_frontier = rows["G1"]["evidence"]["pdelta_frontier_diagnostic"]
    assert g1_frontier["ready"] is False
    assert abs(g1_frontier["frontier_load_scale"] - 0.50765625) <= 1.0e-12
    assert abs(g1_frontier["next_failed_load_scale_after_frontier"] - 0.5078125) <= 1.0e-12
    assert abs(g1_frontier["frontier_to_next_failed_increment"] - 0.00015625) <= 1.0e-12
    assert g1_frontier["next_failed_gate_mode"] == "residual_gate_failed"
    assert (
        g1_frontier["diagnosis"]
        == "frontier_limited_before_full_load_consistent_newton_jacobian_required"
    )
    g1_frontier_jacobian = rows["G1"]["evidence"]["pdelta_frontier_residual_jacobian_probe"]
    assert g1_frontier_jacobian["ready"] is False
    assert g1_frontier_jacobian["target_load_scale"] == g1_frontier["next_failed_load_scale_after_frontier"]
    assert g1_frontier_jacobian["base_residual_inf_n"] > 1.0
    assert g1_frontier_jacobian["best_residual_inf_n"] > g1_frontier_jacobian["residual_tolerance_n"]
    assert g1_frontier_jacobian["correction_pass_count"] == 4
    assert g1_frontier_jacobian["requested_correction_passes"] == 4
    assert g1_frontier_jacobian["accepted_correction_count"] == 4
    assert g1_frontier_jacobian["best_residual_inf_n"] < g1_frontier_jacobian["base_residual_inf_n"]
    assert g1_frontier_jacobian["best_residual_inf_n"] < 2200.0
    assert g1_frontier_jacobian["best_residual_reduction_factor"] < 0.21
    assert len(g1_frontier_jacobian["pass_rows"]) == 4
    assert all(row["accepted"] is True for row in g1_frontier_jacobian["pass_rows"])
    assert (
        g1_frontier_jacobian["pass_rows"][1]["best_residual_inf_n"]
        < g1_frontier_jacobian["pass_rows"][0]["best_residual_inf_n"]
    )
    assert (
        g1_frontier_jacobian["pass_rows"][3]["best_residual_inf_n"]
        < g1_frontier_jacobian["pass_rows"][2]["best_residual_inf_n"]
    )
    assert (
        "previous_residual_jacobian_correction"
        in g1_frontier_jacobian["pass_rows"][1]["direction_labels"]
    )
    assert (
        g1_frontier_jacobian["best_fixed_point_relative_increment"]
        <= g1_frontier_jacobian["relative_increment_tolerance"]
    )
    assert "frontier_residual_jacobian_not_closed" in g1_frontier_jacobian["blockers"]
    g1_frontier_summary = rows["G1"]["evidence"]["pdelta_frontier_residual_jacobian_summary"]
    assert g1_frontier_summary["observed"] is True
    assert g1_frontier_summary["ready"] is False
    assert g1_frontier_summary["target_load_scale"] == g1_frontier_jacobian["target_load_scale"]
    assert g1_frontier_summary["best_residual_inf_n"] == g1_frontier_jacobian["best_residual_inf_n"]
    assert g1_frontier_summary["residual_gap_ratio_to_tolerance"] > 2.0e6
    assert g1_frontier_summary["residual_gate_passed"] is False
    assert g1_frontier_summary["relative_increment_gate_passed"] is True
    assert (
        g1_frontier_summary["diagnosis"]
        == "fixed_point_increment_small_but_direct_residual_gate_far_from_tolerance"
    )
    g1_authored_support = rows["G1"]["evidence"][
        "coarsened_authored_support_pdelta_step_results"
    ][0]
    assert rows["G1"]["evidence"]["coarsened_authored_support_pdelta_status"] == "partial"
    assert rows["G1"]["evidence"]["coarsened_authored_support_pdelta_ready"] is False
    assert rows["G1"]["evidence"]["coarsened_authored_support_pdelta_max_converged_load_scale"] == 0.0
    assert rows["G1"]["evidence"]["coarsened_authored_support_pdelta_first_failed_load_scale"] == 0.5
    assert g1_authored_support["load_step"] == 0.5
    assert g1_authored_support["ready"] is False
    assert g1_authored_support["relative_increment"] > 0.5
    assert g1_authored_support["max_translation_m"] > 20.0
    g1_authored_support_mapping = rows["G1"]["evidence"][
        "coarsened_authored_support_pdelta_support_mapping"
    ]
    assert g1_authored_support_mapping["authored_support_node_count"] == 2133
    assert g1_authored_support_mapping["mapped_support_node_count"] == 756
    assert g1_authored_support_mapping["authored_support_restrained_dof_count"] == 2544
    g1_authored_link_mapping = rows["G1"]["evidence"][
        "coarsened_authored_support_pdelta_elastic_link_mapping"
    ]
    assert g1_authored_link_mapping["elastic_link_row_count"] == 1692
    assert g1_authored_link_mapping["elastic_link_rows_both_endpoints_mapped_to_line_mesh"] == 0
    assert (
        "uncoarsened_boundary_nonlinear_continuation_required"
        in rows["G1"]["evidence"]["coarsened_authored_support_pdelta_blockers"]
    )
    g1_uncoarsened_pdelta = rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_step_results"
    ][0]
    assert rows["G1"]["evidence"]["uncoarsened_boundary_pdelta_status"] == "partial"
    assert rows["G1"]["evidence"]["uncoarsened_boundary_pdelta_ready"] is False
    assert rows["G1"]["evidence"]["uncoarsened_boundary_pdelta_max_converged_load_scale"] == 0.0
    assert rows["G1"]["evidence"]["uncoarsened_boundary_pdelta_first_failed_load_scale"] == 0.05
    assert len(rows["G1"]["evidence"]["uncoarsened_boundary_pdelta_step_results"]) == 1
    assert g1_uncoarsened_pdelta["load_scale"] == 0.05
    assert g1_uncoarsened_pdelta["ready"] is False
    assert g1_uncoarsened_pdelta["equilibrium_replay_gate_passed"] is False
    assert g1_uncoarsened_pdelta["iteration_count"] >= 1
    replay_residual = float(g1_uncoarsened_pdelta["best_equilibrium_replay_residual_inf_n"])
    solver_residual = float(g1_uncoarsened_pdelta["best_solver_residual_inf_n"])
    assert abs(solver_residual - replay_residual) <= 1.0e-6 * max(replay_residual, 1.0)
    assert replay_residual > g1_uncoarsened_pdelta["residual_tolerance_n"]
    assert (
        g1_uncoarsened_pdelta["best_fixed_point_relative_increment"]
        <= g1_uncoarsened_pdelta["relative_increment_tolerance"]
    )
    assert g1_uncoarsened_pdelta["rows"][-1]["outer_solver_mode"] == "newton_only"
    g1_uncoarsened_boundary = rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_boundary_summary"
    ]
    g1_uncoarsened_checkpoint_resume = rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_resume"
    ]
    if g1_uncoarsened_checkpoint_resume is not None:
        assert g1_uncoarsened_checkpoint_resume["supported"] is True
        assert (
            g1_uncoarsened_checkpoint_resume["checkpoint_schema_version"]
            == "mgt-uncoarsened-boundary-pdelta-checkpoint.v1"
        )
    g1_uncoarsened_checkpoint_probe = rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_resume_probe"
    ]
    assert g1_uncoarsened_checkpoint_probe["status"] == "partial"
    assert g1_uncoarsened_checkpoint_probe["max_converged_load_scale"] == 0.45
    assert g1_uncoarsened_checkpoint_probe["first_failed_load_scale"] == 0.45025
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_resume_probe_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_resume_probe_max_converged_load_scale"
    ] == 0.45
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_resume_probe_first_failed_load_scale"
    ] == 0.45025
    checkpoint_resume = g1_uncoarsened_checkpoint_probe["checkpoint_resume"]
    assert checkpoint_resume["supported"] is True
    assert checkpoint_resume["resume_from_load_scale"] == 0.45
    assert checkpoint_resume["skipped_load_steps_before_resume"] == [0.45]
    assert checkpoint_resume["attempted_load_steps_after_resume"] == [0.45025]
    assert checkpoint_resume["resume_checkpoint"]["load_scale"] == 0.45
    checkpoint_probe_step = g1_uncoarsened_checkpoint_probe["step_results"][0]
    assert checkpoint_probe_step["load_scale"] == 0.45025
    assert checkpoint_probe_step["ready"] is False
    assert checkpoint_probe_step["best_residual_inf_n"] <= checkpoint_probe_step[
        "residual_tolerance_n"
    ]
    assert (
        checkpoint_probe_step["best_fixed_point_relative_increment"]
        > checkpoint_probe_step["relative_increment_tolerance"]
    )
    g1_uncoarsened_checkpoint_continuation = rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_continuation"
    ]
    assert g1_uncoarsened_checkpoint_continuation["status"] == "partial"
    assert g1_uncoarsened_checkpoint_continuation["max_converged_load_scale"] == 0.0
    assert g1_uncoarsened_checkpoint_continuation["first_failed_load_scale"] == 0.05
    assert g1_uncoarsened_checkpoint_continuation["segment_count"] == 1
    assert g1_uncoarsened_checkpoint_continuation["accepted_step_count"] == 0
    assert g1_uncoarsened_checkpoint_continuation["saved_checkpoint_count"] == 0
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_continuation_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_continuation_max_converged_load_scale"
    ] == 0.0
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_checkpoint_continuation_first_failed_load_scale"
    ] == 0.05
    assert g1_uncoarsened_checkpoint_continuation["frontier_step"] is None
    continuation_failed = g1_uncoarsened_checkpoint_continuation["first_failed_step"]
    assert continuation_failed["load_scale"] == 0.05
    assert continuation_failed["ready"] is False
    assert continuation_failed["best_equilibrium_replay_residual_inf_n"] > continuation_failed[
        "residual_tolerance_n"
    ]
    assert (
        abs(
            continuation_failed["best_solver_residual_inf_n"]
            - continuation_failed["best_equilibrium_replay_residual_inf_n"]
        )
        <= 1.0e-6
        * max(continuation_failed["best_equilibrium_replay_residual_inf_n"], 1.0)
    )
    assert rows["G1"]["evidence"]["direct_residual_newton_status"] == "partial"
    assert rows["G1"]["evidence"]["direct_residual_newton_ready"] is False
    assert rows["G1"]["evidence"]["residual_jacobian_consistency_status"] == "ready"
    assert rows["G1"]["evidence"]["residual_jacobian_consistency_ready"] is True
    assert (
        rows["G1"]["evidence"]["residual_jacobian_consistency_base_residual_inf_n"]
        > 1.0
    )
    assert rows["G1"]["evidence"]["residual_jacobian_consistency_direction_rows"]
    component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_consistency_component_breakdown"
    ]
    assert component_breakdown["component_inf_n"]["shell_membrane"] > component_breakdown[
        "component_inf_n"
    ]["frame"]
    assert component_breakdown["component_inf_n"]["shell_bending_drilling"] < component_breakdown[
        "component_inf_n"
    ]["shell_membrane"]
    assert (
        component_breakdown["top_row_dominant_component_counts"]["shell_membrane"]
        >= 8
    )
    hotspot_rows = rows["G1"]["evidence"][
        "residual_jacobian_consistency_hotspot_shell_membrane_diagnostics"
    ]
    assert hotspot_rows
    assert hotspot_rows[0]["dominant_component"] == "shell_membrane"
    scale_sweep = rows["G1"]["evidence"][
        "residual_jacobian_consistency_state_scale_sweep"
    ]
    assert scale_sweep[0]["state_scale"] == 0.0
    assert scale_sweep[0]["residual_inf_n"] < scale_sweep[-1]["residual_inf_n"]
    assert rows["G1"]["evidence"]["equilibrium_newton_state_scale_status"] == "partial"
    assert (
        rows["G1"]["evidence"]["equilibrium_newton_state_scale_final_residual_inf_n"]
        < rows["G1"]["evidence"]["equilibrium_newton_state_scale_initial_residual_inf_n"]
    )
    assert (
        rows["G1"]["evidence"]["equilibrium_newton_state_scale_iterations"][0][
            "update_mode"
        ]
        == "state_scale_line_search"
    )
    assert rows["G1"]["evidence"]["equilibrium_preconditioned_zero_status"] == "ready"
    assert (
        rows["G1"]["evidence"]["equilibrium_preconditioned_zero_residual_gate_passed"]
        is False
    )
    assert (
        rows["G1"]["evidence"]["equilibrium_preconditioned_zero_zero_state_residual_inf_n"]
        > rows["G1"]["evidence"]["equilibrium_newton_state_scale_final_residual_inf_n"] - 1.0e-6
    )
    assert rows["G1"]["evidence"]["equilibrium_preconditioned_zero_best_correction_mode"]
    assert (
        rows["G1"]["evidence"]["equilibrium_preconditioned_zero_overall_best_residual_inf_n"]
        < rows["G1"]["evidence"]["equilibrium_preconditioned_zero_zero_state_residual_inf_n"]
    )
    assert (
        rows["G1"]["evidence"]["equilibrium_preconditioned_zero_iterative_search"][
            "accepted_iteration_count"
        ]
        >= 1
    )
    assert rows["G1"]["evidence"][
        "equilibrium_preconditioned_zero_output_final_checkpoint"
    ]["written"] is True
    assert (
        rows["G1"]["evidence"]["direct_residual_preconditioned_zero_seed_status"]
        == "partial"
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_zero_seed_base_residual_inf_n"
        ]
        == rows["G1"]["evidence"][
            "equilibrium_preconditioned_zero_overall_best_residual_inf_n"
        ]
    )
    assert rows["G1"]["evidence"]["equilibrium_preconditioned_continuation_status"] == "ready"
    assert (
        rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_overall_best_residual_inf_n"
        ]
        < rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_start_residual_inf_n"
        ]
    )
    assert rows["G1"]["evidence"][
        "equilibrium_preconditioned_continuation_output_final_checkpoint"
    ]["written"] is True
    assert (
        rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_checkpoint_standardization_status"
        ]
        == "ready"
    )
    assert (
        rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_standard_checkpoint_ready"
        ]
        is True
    )
    assert (
        rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_standard_checkpoint"
        ]["schema"]
        == "mgt-direct-residual-newton-state.v1"
    )
    assert (
        rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_standard_reloaded_checkpoint"
        ]["checkpoint_schema"]
        == "mgt-direct-residual-newton-state.v1"
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_seed_base_residual_inf_n"
        ]
        == rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_overall_best_residual_inf_n"
        ]
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_seed_status"
        ]
        == "partial"
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_seed_checkpoint_schema"
        ]
        == "mgt-direct-residual-newton-state.v1"
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_seed_base_residual_inf_n"
        ]
        == rows["G1"]["evidence"][
            "equilibrium_preconditioned_continuation_standard_checkpoint"
        ]["direct_residual_inf_n"]
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_rowcorr_status"
        ]
        == "partial"
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_rowcorr_accepted"
        ]
        is True
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_rowcorr_base_residual_inf_n"
        ]
        == rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_seed_base_residual_inf_n"
        ]
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_rowcorr_final_residual_inf_n"
        ]
        < rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_rowcorr_base_residual_inf_n"
        ]
    )
    assert (
        rows["G1"]["evidence"][
            "direct_residual_preconditioned_continuation_standard_rowcorr_final_checkpoint"
        ]["schema"]
        == "mgt-direct-residual-newton-state.v1"
    )
    direct_contract = rows["G1"]["evidence"]["direct_residual_contract"]
    assert direct_contract["definition"] == "R(u, lambda) = F_int(u) - lambda * F_ext"
    assert direct_contract["external_load_vector_configuration"] == "reference"
    assert direct_contract["external_load_vector_reassembled_with_displacement"] is False
    assert direct_contract["frame_geometric_tangent_included"] is True
    assert direct_contract["authored_support_restraints_included"] is True
    assert direct_contract["finite_elastic_link_springs_included"] is True
    assert direct_contract["shell_surface_tangent_included"] is True
    assert direct_contract["service_material_tangent_included"] is True
    assert direct_contract["directional_residual_jacobian_globalization_included"] is True
    direct_base = rows["G1"]["evidence"]["direct_residual_base"]
    assert direct_base["load_scale"] == 0.656
    assert direct_base["direct_residual_inf_n"] > 1.0
    assert direct_base["fixed_point_receipt_residual_inf_n"] <= continuation_failed[
        "residual_tolerance_n"
    ]
    direct_trust = rows["G1"]["evidence"]["direct_residual_trust_region"]
    assert direct_trust["accepted"] is True
    assert direct_trust["accepted_iteration_count"] == 6
    assert direct_trust["directional_jacobian_probe_alpha"] == 0.0000078125
    first_iteration = direct_trust["iterations"][0]
    assert first_iteration["directional_residual_jacobian"]["enabled"] is True
    assert (
        first_iteration["best_candidate"]["alpha_source"]
        == "directional_residual_jacobian_l2"
    )
    assert 0.0006 < first_iteration["best_candidate"]["alpha"] < 0.0007
    assert direct_trust["best_candidate"]["direct_residual_inf_n"] < direct_base[
        "direct_residual_inf_n"
    ]
    assert (
        rows["G1"]["evidence"]["direct_residual_final"]["direct_residual_inf_n"]
        <= direct_trust["best_candidate"]["direct_residual_inf_n"]
    )
    assert direct_trust["best_candidate"]["residual_gate_passed"] is False
    assert direct_trust["best_candidate"]["relative_increment_gate_passed"] is True
    direct_secant = rows["G1"]["evidence"][
        "direct_residual_secant_subspace_globalization"
    ]
    assert direct_secant["enabled"] is True
    assert direct_secant["attempted"] is True
    assert direct_secant["residual_descent"] is True
    assert direct_secant["promoted_to_final_state"] is True
    assert direct_secant["promotion_count"] == 6
    assert direct_secant["max_promotions"] == 6
    assert len(direct_secant["passes"]) == 6
    assert direct_secant["best_candidate"]["direct_residual_inf_n"] < rows["G1"][
        "evidence"
    ]["direct_residual_final"]["direct_residual_inf_n"]
    assert direct_secant["best_candidate"]["relative_increment_gate_passed"] is False
    gate_secant = direct_secant["best_gate_eligible_candidate"]
    assert gate_secant["relative_increment_gate_passed"] is True
    assert gate_secant["residual_gate_passed"] is False
    assert gate_secant["secant_pass"] == 6
    assert gate_secant["alpha"] == 0.015625
    assert direct_secant["passes"][-1]["promoted_to_final_state"] is True
    direct_matrix_free = rows["G1"]["evidence"][
        "direct_residual_matrix_free_consistent_jacobian_subspace"
    ]
    assert direct_matrix_free["enabled"] is True
    assert direct_matrix_free["attempted"] is True
    assert direct_matrix_free["accepted"] is True
    assert direct_matrix_free["promoted_to_final_state"] is True
    assert direct_matrix_free["basis_size"] == 2
    assert direct_matrix_free["promotion_count"] == 8
    assert direct_matrix_free["max_promotions"] == 8
    assert direct_matrix_free["minimum_relative_improvement"] == 1.0e-5
    assert direct_matrix_free["stop_reason"] == "max_promotions_exhausted"
    assert len(direct_matrix_free["passes"]) == 8
    assert direct_matrix_free["passes"][0]["matrix_free_pass"] == 1
    assert direct_matrix_free["passes"][1]["matrix_free_pass"] == 2
    assert direct_matrix_free["passes"][2]["matrix_free_pass"] == 3
    assert direct_matrix_free["passes"][3]["matrix_free_pass"] == 4
    assert direct_matrix_free["passes"][4]["matrix_free_pass"] == 5
    assert direct_matrix_free["passes"][5]["matrix_free_pass"] == 6
    assert direct_matrix_free["passes"][6]["matrix_free_pass"] == 7
    assert direct_matrix_free["passes"][7]["matrix_free_pass"] == 8
    assert direct_matrix_free["passes"][-1]["promoted_to_final_state"] is True
    assert all(
        row["accepted_relative_improvement"]
        >= direct_matrix_free["minimum_relative_improvement"]
        for row in direct_matrix_free["passes"]
    )
    assert [row["selected_basis_size"] for row in direct_matrix_free["passes"]] == [
        2,
        1,
        2,
        2,
        2,
        2,
        2,
        1,
    ]
    matrix_free_gate = direct_matrix_free["best_gate_eligible_candidate"]
    assert matrix_free_gate["matrix_free_pass"] == 8
    assert matrix_free_gate["basis_size_used"] == 1
    assert matrix_free_gate["relative_improvement"] >= 1.0e-5
    assert matrix_free_gate["relative_increment_gate_passed"] is True
    assert matrix_free_gate["residual_gate_passed"] is False
    assert (
        matrix_free_gate["direct_residual_inf_n"]
        < gate_secant["direct_residual_inf_n"]
    )
    assert matrix_free_gate["direct_residual_inf_n"] < 15516.5
    assert (
        direct_matrix_free["passes"][7]["best_gate_eligible_candidate"][
            "direct_residual_inf_n"
        ]
        < direct_matrix_free["passes"][6]["best_gate_eligible_candidate"][
            "direct_residual_inf_n"
        ]
    )
    assert (
        rows["G1"]["evidence"]["direct_residual_final"]["direct_residual_inf_n"]
        == matrix_free_gate["direct_residual_inf_n"]
    )
    direct_followup48_replay = rows["G1"]["evidence"][
        "direct_residual_newton_followup48_replay"
    ]
    assert direct_followup48_replay["status"] == "partial"
    assert direct_followup48_replay["ready"] is False
    assert (
        direct_followup48_replay["base_direct_residual_inf_n"]
        == 5662.74655057728
    )
    assert (
        direct_followup48_replay["final_direct_residual_inf_n"]
        == direct_followup48_replay["base_direct_residual_inf_n"]
    )
    assert direct_followup48_replay["matrix_free_global_krylov_enabled"] is False
    assert direct_followup48_replay["matrix_free_global_krylov_attempted"] is False
    assert direct_followup48_replay["promotion_count"] is None
    assert (
        direct_followup48_replay["promotion_candidate_residual_gate_passed"]
        is None
    )
    assert "direct_residual_gate_not_closed" in direct_followup48_replay["blockers"]
    direct_followup48_rowcorr = rows["G1"]["evidence"][
        "direct_residual_newton_followup48_rowcorr_narrow"
    ]
    assert direct_followup48_rowcorr["status"] == "partial"
    assert direct_followup48_rowcorr["ready"] is False
    assert direct_followup48_rowcorr["base_direct_residual_inf_n"] == 5662.74655057728
    assert (
        direct_followup48_rowcorr["final_direct_residual_inf_n"]
        == direct_followup48_rowcorr["base_direct_residual_inf_n"]
    )
    assert (
        direct_followup48_rowcorr["current_tangent_residual_row_correction_enabled"]
        is True
    )
    assert (
        direct_followup48_rowcorr["current_tangent_residual_row_correction_accepted"]
        is False
    )
    assert direct_followup48_rowcorr["current_tangent_residual_row_promotion_count"] == 0
    assert (
        direct_followup48_rowcorr["current_tangent_residual_row_stop_reason"]
        == "no_residual_descent"
    )
    assert direct_followup48_rowcorr["output_final_checkpoint_written"] is False
    assert (
        direct_followup48_rowcorr["output_final_checkpoint_reason"]
        == "no_residual_descent"
    )
    direct_followup48_largest_rows = rows["G1"]["evidence"][
        "direct_residual_newton_followup48_rowcorr_largest_rows_support4"
    ]
    assert direct_followup48_largest_rows["status"] == "partial"
    assert direct_followup48_largest_rows["ready"] is False
    assert direct_followup48_largest_rows["base_direct_residual_inf_n"] == (
        direct_followup48_replay["base_direct_residual_inf_n"]
    )
    assert (
        direct_followup48_largest_rows["final_direct_residual_inf_n"]
        == 5642.17709206959
    )
    assert (
        direct_followup48_largest_rows[
            "current_tangent_residual_row_correction_accepted"
        ]
        is True
    )
    assert (
        direct_followup48_largest_rows["current_tangent_residual_row_target_mode"]
        == "largest_rows"
    )
    assert direct_followup48_largest_rows["best_candidate_support_column_count"] == 4
    assert direct_followup48_largest_rows["output_final_checkpoint_written"] is True
    direct_followup48_largest_rows_followup2 = rows["G1"]["evidence"][
        "direct_residual_newton_followup48_rowcorr_largest_rows_support4_followup2"
    ]
    assert direct_followup48_largest_rows_followup2["status"] == "partial"
    assert (
        direct_followup48_largest_rows_followup2["base_direct_residual_inf_n"]
        == direct_followup48_largest_rows["final_direct_residual_inf_n"]
    )
    assert (
        direct_followup48_largest_rows_followup2["final_direct_residual_inf_n"]
        == direct_followup48_largest_rows["final_direct_residual_inf_n"]
    )
    assert (
        direct_followup48_largest_rows_followup2[
            "current_tangent_residual_row_correction_accepted"
        ]
        is False
    )
    assert (
        direct_followup48_largest_rows_followup2[
            "current_tangent_residual_row_stop_reason"
        ]
        == "no_residual_descent"
    )
    assert (
        direct_followup48_largest_rows_followup2["output_final_checkpoint_written"]
        is False
    )
    direct_followup48_fd_timeout = rows["G1"]["evidence"][
        "direct_residual_newton_followup48_rowcorr_largest_rows_fd_support4_timeout"
    ]
    assert direct_followup48_fd_timeout["status"] == "timeout"
    assert direct_followup48_fd_timeout["ready"] is False
    assert (
        direct_followup48_fd_timeout["source_checkpoint_direct_residual_inf_n"]
        == direct_followup48_largest_rows["final_direct_residual_inf_n"]
    )
    assert direct_followup48_fd_timeout["output_json_written"] is False
    assert (
        "finite_difference_row_correction_timed_out_before_receipt"
        in direct_followup48_fd_timeout["blockers"]
    )
    assert "direct_residual_gate_not_closed" in rows["G1"]["evidence"][
        "direct_residual_newton_blockers"
    ]
    g1_element_block = rows["G1"]["evidence"][
        "direct_residual_row_element_block_target_smoke"
    ]
    assert g1_element_block["status"] == "partial"
    assert g1_element_block["current_tangent_residual_row_target_mode"] == (
        "residual_element_blocks"
    )
    assert g1_element_block["current_tangent_residual_row_correction_accepted"] is True
    assert g1_element_block["best_candidate_configured_target_count"] == 2
    assert g1_element_block["best_candidate_target_row_count"] == 36
    assert g1_element_block["best_candidate_support_size"] == 16
    assert g1_element_block["final_direct_residual_inf_n"] == 6931.641138710459
    assert g1_element_block["final_direct_residual_inf_n"] < g1_element_block[
        "base_direct_residual_inf_n"
    ]
    g1_element_patch = rows["G1"]["evidence"][
        "direct_residual_row_element_patch_target_smoke"
    ]
    assert g1_element_patch["status"] == "partial"
    assert g1_element_patch["current_tangent_residual_row_element_neighbor_depth"] == 1
    assert g1_element_patch["current_tangent_residual_row_correction_accepted"] is False
    assert g1_element_patch["best_candidate_target_row_count"] == 114
    assert g1_element_patch["best_candidate_support_size"] == 16
    assert g1_element_patch["best_candidate_direct_residual_inf_n"] > g1_element_patch[
        "base_direct_residual_inf_n"
    ]
    g1_element_patch_fd32 = rows["G1"]["evidence"][
        "direct_residual_row_element_patch_fd32_smoke"
    ]
    assert g1_element_patch_fd32["status"] == "partial"
    assert g1_element_patch_fd32["current_tangent_residual_row_fd_max_support_columns"] == 32
    assert g1_element_patch_fd32["current_tangent_residual_row_correction_accepted"] is False
    assert g1_element_patch_fd32["best_candidate_target_row_count"] == 114
    assert g1_element_patch_fd32["best_candidate_support_size"] == 32
    assert g1_element_patch_fd32["best_candidate_direct_residual_inf_n"] > (
        g1_element_patch_fd32["base_direct_residual_inf_n"]
    )
    g1_element_block_fd32 = rows["G1"]["evidence"][
        "direct_residual_row_element_block_fd32_followup_smoke"
    ]
    assert g1_element_block_fd32["status"] == "partial"
    assert g1_element_block_fd32["current_tangent_residual_row_fd_max_support_columns"] == 32
    assert g1_element_block_fd32["current_tangent_residual_row_correction_accepted"] is False
    assert g1_element_block_fd32["best_candidate_target_row_count"] == 36
    assert g1_element_block_fd32["best_candidate_support_size"] == 32
    assert g1_element_block_fd32["best_candidate_direct_residual_inf_n"] > (
        g1_element_block_fd32["base_direct_residual_inf_n"]
    )
    g1_global_krylov = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_krylov_smoke"
    ]
    assert g1_global_krylov["status"] == "partial"
    assert g1_global_krylov["matrix_free_global_krylov_enabled"] is True
    assert g1_global_krylov["matrix_free_global_krylov_attempted"] is True
    assert g1_global_krylov["matrix_free_global_krylov_accepted"] is False
    assert g1_global_krylov["matrix_free_global_krylov_stop_reason"] == "no_residual_descent"
    assert g1_global_krylov["matrix_free_global_krylov_matvec_count"] == 3
    assert g1_global_krylov["matrix_free_global_krylov_unstable_free_dof_probe_count"] == 0
    assert g1_global_krylov[
        "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
    ] > g1_global_krylov["base_direct_residual_inf_n"]
    g1_scaled_krylov = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_scaled_krylov_smoke"
    ]
    assert g1_scaled_krylov["matrix_free_global_krylov_scaling_mode"] == (
        "residual_diagonal_displacement"
    )
    assert g1_scaled_krylov["matrix_free_global_krylov_accepted"] is False
    assert g1_scaled_krylov["matrix_free_global_krylov_stop_reason"] == "no_residual_descent"
    assert g1_scaled_krylov[
        "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
    ] > g1_scaled_krylov["base_direct_residual_inf_n"]
    assert (
        g1_scaled_krylov[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        - g1_scaled_krylov["base_direct_residual_inf_n"]
        < 1.0e-5
    )
    g1_scaled_signed_krylov = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_scaled_signed_krylov_smoke"
    ]
    assert g1_scaled_signed_krylov["matrix_free_global_krylov_scaling_mode"] == (
        "residual_diagonal_displacement"
    )
    assert g1_scaled_signed_krylov["matrix_free_global_krylov_allow_negative_alphas"] is True
    assert g1_scaled_signed_krylov["matrix_free_global_krylov_accepted"] is True
    assert g1_scaled_signed_krylov["matrix_free_global_krylov_stop_reason"] == "accepted"
    assert g1_scaled_signed_krylov[
        "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
    ] < g1_scaled_signed_krylov["base_direct_residual_inf_n"]
    assert (
        g1_scaled_signed_krylov["base_direct_residual_inf_n"]
        - g1_scaled_signed_krylov[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        < 1.0e-3
    )
    g1_tangent_preconditioned_krylov = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_smoke"
    ]
    assert g1_tangent_preconditioned_krylov["status"] == "partial"
    assert g1_tangent_preconditioned_krylov[
        "matrix_free_global_krylov_preconditioner_mode"
    ] == "current_tangent"
    assert g1_tangent_preconditioned_krylov[
        "matrix_free_global_krylov_column_scale_units"
    ] == "preconditioner_input_n"
    assert g1_tangent_preconditioned_krylov["matrix_free_global_krylov_accepted"] is True
    assert (
        g1_tangent_preconditioned_krylov[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
        == 0.0
    )
    assert (
        g1_tangent_preconditioned_krylov["matrix_free_global_krylov_stop_reason"]
        == "accepted"
    )
    assert (
        g1_tangent_preconditioned_krylov[
            "matrix_free_global_krylov_preconditioner_solve_count"
        ]
        >= g1_tangent_preconditioned_krylov[
            "matrix_free_global_krylov_matvec_count"
        ]
    )
    tangent_improvement = (
        g1_tangent_preconditioned_krylov["base_direct_residual_inf_n"]
        - g1_tangent_preconditioned_krylov[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    signed_improvement = (
        g1_scaled_signed_krylov["base_direct_residual_inf_n"]
        - g1_scaled_signed_krylov[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert tangent_improvement > 40.0 * signed_improvement
    assert tangent_improvement < 1.0e-2
    assert (
        g1_tangent_preconditioned_krylov[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        < 1.0e-6
    )
    g1_tangent_alpha8_floor = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_floor_smoke"
    ]
    assert g1_tangent_alpha8_floor["status"] == "partial"
    assert g1_tangent_alpha8_floor[
        "matrix_free_global_krylov_preconditioner_mode"
    ] == "current_tangent"
    assert g1_tangent_alpha8_floor["matrix_free_global_krylov_max_alpha"] == 8.0
    assert (
        g1_tangent_alpha8_floor[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
        == 1.0e-6
    )
    assert g1_tangent_alpha8_floor["matrix_free_global_krylov_accepted"] is True
    assert (
        g1_tangent_alpha8_floor[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > 1.0e-6
    )
    assert (
        g1_tangent_alpha8_floor[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        < g1_tangent_preconditioned_krylov[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_followup = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_smoke"
    ]
    assert g1_tangent_alpha8_followup["matrix_free_global_krylov_max_alpha"] == 8.0
    assert g1_tangent_alpha8_followup["matrix_free_global_krylov_accepted"] is True
    assert (
        g1_tangent_alpha8_followup[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > 1.0e-6
    )
    assert (
        g1_tangent_alpha8_followup["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_floor[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_followup[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        < g1_tangent_alpha8_floor[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_followup_2 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_2_smoke"
    ]
    assert g1_tangent_alpha8_followup_2["matrix_free_global_krylov_max_alpha"] == 8.0
    assert g1_tangent_alpha8_followup_2["matrix_free_global_krylov_accepted"] is True
    assert (
        g1_tangent_alpha8_followup_2[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > g1_tangent_alpha8_followup[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_followup_2["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_followup[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_followup_2[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        < g1_tangent_alpha8_followup[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_followup_3 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_3_smoke"
    ]
    assert g1_tangent_alpha8_followup_3["matrix_free_global_krylov_max_alpha"] == 8.0
    assert g1_tangent_alpha8_followup_3["matrix_free_global_krylov_accepted"] is True
    assert (
        g1_tangent_alpha8_followup_3[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > 1.0e-6
    )
    assert (
        g1_tangent_alpha8_followup_3[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        < g1_tangent_alpha8_followup_2[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_followup_3["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_followup_2[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_followup_3[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        < g1_tangent_alpha8_followup_2[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_followup_4 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_4_smoke"
    ]
    assert g1_tangent_alpha8_followup_4["matrix_free_global_krylov_max_alpha"] == 8.0
    assert g1_tangent_alpha8_followup_4["matrix_free_global_krylov_accepted"] is False
    assert (
        g1_tangent_alpha8_followup_4["matrix_free_global_krylov_stop_reason"]
        == "no_residual_descent"
    )
    assert (
        g1_tangent_alpha8_followup_4["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_followup_3[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_followup_4["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_followup_4["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_followup_4[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        > g1_tangent_alpha8_followup_4["base_direct_residual_inf_n"]
    )
    g1_tangent_alpha8_broader_basis = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_broader_basis_smoke"
    ]
    assert g1_tangent_alpha8_broader_basis["matrix_free_global_krylov_max_alpha"] == 8.0
    assert g1_tangent_alpha8_broader_basis[
        "matrix_free_global_krylov_accepted"
    ] is False
    assert (
        g1_tangent_alpha8_broader_basis["matrix_free_global_krylov_stop_reason"]
        == "no_residual_descent"
    )
    assert (
        g1_tangent_alpha8_broader_basis["matrix_free_global_krylov_matvec_count"]
        > g1_tangent_alpha8_followup_4["matrix_free_global_krylov_matvec_count"]
    )
    assert (
        g1_tangent_alpha8_broader_basis["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_followup_4["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_broader_basis[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        > g1_tangent_alpha8_followup_4[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_reg1e9 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e9_smoke"
    ]
    assert g1_tangent_alpha8_reg1e9["matrix_free_global_krylov_accepted"] is False
    assert (
        g1_tangent_alpha8_reg1e9["matrix_free_global_krylov_stop_reason"]
        == "no_residual_descent"
    )
    assert (
        g1_tangent_alpha8_reg1e9[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
        < g1_tangent_alpha8_followup_4[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e9[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        > g1_tangent_alpha8_reg1e9["base_direct_residual_inf_n"]
    )
    g1_tangent_alpha8_reg1e7 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_smoke"
    ]
    assert g1_tangent_alpha8_reg1e7["matrix_free_global_krylov_accepted"] is True
    assert (
        g1_tangent_alpha8_reg1e7[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
        > g1_tangent_alpha8_followup_4[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e7["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_followup_4["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e7["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_reg1e7["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e7["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_followup_3[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_reg1e7_followup = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_followup_smoke"
    ]
    assert g1_tangent_alpha8_reg1e7_followup[
        "matrix_free_global_krylov_accepted"
    ] is False
    assert (
        g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_stop_reason"
        ]
        == "relative_improvement_floor_not_met"
    )
    assert (
        g1_tangent_alpha8_reg1e7_followup["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e7["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e7_followup["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e7_followup["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        < g1_tangent_alpha8_reg1e7_followup["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        < g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        < 1.0e-6
    )
    assert (
        g1_tangent_alpha8_reg1e7_followup["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_followup_3[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_reg3e7 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e7_smoke"
    ]
    assert g1_tangent_alpha8_reg3e7["matrix_free_global_krylov_accepted"] is False
    assert (
        g1_tangent_alpha8_reg3e7["matrix_free_global_krylov_stop_reason"]
        == "relative_improvement_floor_not_met"
    )
    assert (
        g1_tangent_alpha8_reg3e7[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
        > g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
    )
    assert (
        g1_tangent_alpha8_reg3e7["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e7["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg3e7["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg3e7["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg3e7[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > g1_tangent_alpha8_reg1e7_followup[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_reg3e7[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        < g1_tangent_alpha8_reg3e7[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
    )
    g1_tangent_alpha8_reg1e6 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_smoke"
    ]
    assert g1_tangent_alpha8_reg1e6["matrix_free_global_krylov_accepted"] is True
    assert g1_tangent_alpha8_reg1e6["matrix_free_global_krylov_stop_reason"] == "accepted"
    assert (
        g1_tangent_alpha8_reg1e6[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
        > g1_tangent_alpha8_reg3e7[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e7["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e6[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > g1_tangent_alpha8_reg1e6[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_reg3e7[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_tangent_alpha8_reg1e6_followup = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_smoke"
    ]
    assert g1_tangent_alpha8_reg1e6_followup[
        "matrix_free_global_krylov_accepted"
    ] is True
    assert (
        g1_tangent_alpha8_reg1e6_followup[
            "matrix_free_global_krylov_stop_reason"
        ]
        == "accepted"
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > g1_tangent_alpha8_reg1e6_followup[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_reg1e6["final_direct_residual_inf_n"]
    )
    g1_tangent_alpha8_reg1e6_followup_2 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_2_smoke"
    ]
    assert g1_tangent_alpha8_reg1e6_followup_2[
        "matrix_free_global_krylov_accepted"
    ] is True
    assert (
        g1_tangent_alpha8_reg1e6_followup_2[
            "matrix_free_global_krylov_stop_reason"
        ]
        == "accepted"
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_2["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_2[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > g1_tangent_alpha8_reg1e6_followup_2[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_2["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_2[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_2["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_reg1e6_followup["final_direct_residual_inf_n"]
    )
    g1_tangent_alpha8_reg1e6_followup_3 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_3_smoke"
    ]
    assert g1_tangent_alpha8_reg1e6_followup_3[
        "matrix_free_global_krylov_accepted"
    ] is True
    assert (
        g1_tangent_alpha8_reg1e6_followup_3[
            "matrix_free_global_krylov_stop_reason"
        ]
        == "accepted"
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_3["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_2["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_3[
            "matrix_free_global_krylov_best_candidate_relative_improvement"
        ]
        > g1_tangent_alpha8_reg1e6_followup_3[
            "matrix_free_global_krylov_minimum_relative_improvement"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_3["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_3[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_3["final_direct_residual_inf_n"]
        < g1_tangent_alpha8_reg1e6_followup_2["final_direct_residual_inf_n"]
    )
    g1_tangent_alpha8_reg1e6_followup_4 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_4_smoke"
    ]
    assert g1_tangent_alpha8_reg1e6_followup_4[
        "matrix_free_global_krylov_accepted"
    ] is False
    assert (
        g1_tangent_alpha8_reg1e6_followup_4[
            "matrix_free_global_krylov_stop_reason"
        ]
        == "no_residual_descent"
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_4["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_3["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_4["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_4["base_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg1e6_followup_4[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        > g1_tangent_alpha8_reg1e6_followup_4["base_direct_residual_inf_n"]
    )
    g1_tangent_alpha8_reg3e6 = rows["G1"]["evidence"][
        "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e6_smoke"
    ]
    assert g1_tangent_alpha8_reg3e6["matrix_free_global_krylov_accepted"] is False
    assert (
        g1_tangent_alpha8_reg3e6["matrix_free_global_krylov_stop_reason"]
        == "no_residual_descent"
    )
    assert (
        g1_tangent_alpha8_reg3e6[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
        > g1_tangent_alpha8_reg1e6_followup_4[
            "matrix_free_global_krylov_preconditioner_regularization"
        ]
    )
    assert (
        g1_tangent_alpha8_reg3e6["base_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_3["final_direct_residual_inf_n"]
    )
    assert (
        g1_tangent_alpha8_reg3e6[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
        > g1_tangent_alpha8_reg3e6["base_direct_residual_inf_n"]
    )
    g1_adaptive_preconditioned_global_newton = rows["G1"]["evidence"][
        "direct_residual_adaptive_preconditioned_global_newton_smoke"
    ]
    assert g1_adaptive_preconditioned_global_newton["status"] == "partial"
    assert g1_adaptive_preconditioned_global_newton["ready"] is False
    assert g1_adaptive_preconditioned_global_newton["promotion_count"] == 0
    assert (
        g1_adaptive_preconditioned_global_newton["stop_reason"]
        == "no_regularization_factor_promoted"
    )
    assert g1_adaptive_preconditioned_global_newton["row_count"] == 2
    assert (
        g1_adaptive_preconditioned_global_newton["final_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_3["final_direct_residual_inf_n"]
    )
    adaptive_rows = g1_adaptive_preconditioned_global_newton["rows"]
    assert [row["tangent_regularization_factor"] for row in adaptive_rows] == [
        1.0e-6,
        3.0e-6,
    ]
    assert all(row["accepted"] is False for row in adaptive_rows)
    assert all(row["stop_reason"] == "no_residual_descent" for row in adaptive_rows)
    assert (
        adaptive_rows[0]["best_candidate_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg1e6_followup_4[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    assert (
        adaptive_rows[1]["best_candidate_direct_residual_inf_n"]
        == g1_tangent_alpha8_reg3e6[
            "matrix_free_global_krylov_best_candidate_direct_residual_inf_n"
        ]
    )
    g1_adaptive_preconditioned_global_newton_secant_seed = rows["G1"]["evidence"][
        "direct_residual_adaptive_preconditioned_global_newton_secant_seed_smoke"
    ]
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed[
            "secant_family_seed_enabled"
        ]
        is True
    )
    assert g1_adaptive_preconditioned_global_newton_secant_seed["promotion_count"] == 1
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed["stop_reason"]
        == "max_controller_steps_reached"
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed[
            "final_direct_residual_inf_n"
        ]
        < g1_adaptive_preconditioned_global_newton["final_direct_residual_inf_n"]
    )
    seeded_rows = g1_adaptive_preconditioned_global_newton_secant_seed["rows"]
    assert len(seeded_rows) == 1
    assert seeded_rows[0]["accepted"] is True
    assert (
        seeded_rows[0]["component_acceptance"]["secant_family"] is True
    )
    assert (
        seeded_rows[0]["component_acceptance"]["matrix_free_global_krylov"] is True
    )
    assert (
        seeded_rows[0]["final_relative_improvement"]
        > g1_adaptive_preconditioned_global_newton_secant_seed[
            "minimum_relative_improvement"
        ]
    )
    g1_adaptive_preconditioned_global_newton_secant_seed_followup = rows["G1"][
        "evidence"
    ][
        "direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_smoke"
    ]
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup[
            "secant_family_seed_enabled"
        ]
        is True
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup[
            "final_direct_residual_inf_n"
        ]
        < g1_adaptive_preconditioned_global_newton_secant_seed[
            "final_direct_residual_inf_n"
        ]
    )
    seeded_followup_rows = (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup["rows"]
    )
    assert len(seeded_followup_rows) == 1
    assert seeded_followup_rows[0]["accepted"] is True
    assert (
        seeded_followup_rows[0]["base_direct_residual_inf_n"]
        == g1_adaptive_preconditioned_global_newton_secant_seed[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        seeded_followup_rows[0]["component_acceptance"]["secant_family"] is True
    )
    assert (
        seeded_followup_rows[0]["component_acceptance"]["matrix_free_global_krylov"]
        is True
    )
    assert (
        seeded_followup_rows[0]["final_relative_improvement"]
        > g1_adaptive_preconditioned_global_newton_secant_seed_followup[
            "minimum_relative_improvement"
        ]
    )
    g1_adaptive_preconditioned_global_newton_secant_seed_followup_2 = rows["G1"][
        "evidence"
    ][
        "direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_2_smoke"
    ]
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup_2[
            "secant_family_seed_enabled"
        ]
        is True
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup_2[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup_2[
            "runtime_budget_exceeded"
        ]
        is False
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup_2[
            "runtime_budget_seconds"
        ]
        == 720.0
    )
    assert (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup_2[
            "final_direct_residual_inf_n"
        ]
        < g1_adaptive_preconditioned_global_newton_secant_seed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    seeded_followup_2_rows = (
        g1_adaptive_preconditioned_global_newton_secant_seed_followup_2["rows"]
    )
    assert len(seeded_followup_2_rows) == 1
    assert seeded_followup_2_rows[0]["accepted"] is True
    assert (
        seeded_followup_2_rows[0]["base_direct_residual_inf_n"]
        == g1_adaptive_preconditioned_global_newton_secant_seed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        seeded_followup_2_rows[0]["component_acceptance"]["secant_family"]
        is False
    )
    assert (
        seeded_followup_2_rows[0]["component_acceptance"][
            "matrix_free_global_krylov"
        ]
        is True
    )
    assert (
        seeded_followup_2_rows[0]["final_relative_improvement"]
        > g1_adaptive_preconditioned_global_newton_secant_seed_followup_2[
            "minimum_relative_improvement"
        ]
    )
    assert seeded_followup_2_rows[0]["child_runtime_seconds"] > 600.0
    g1_adaptive_preconditioned_global_newton_runtime_budget = rows["G1"][
        "evidence"
    ][
        "direct_residual_adaptive_preconditioned_global_newton_runtime_budget_smoke"
    ]
    assert (
        g1_adaptive_preconditioned_global_newton_runtime_budget[
            "runtime_budget_exceeded"
        ]
        is True
    )
    assert (
        g1_adaptive_preconditioned_global_newton_runtime_budget[
            "runtime_budget_seconds"
        ]
        == 0.0
    )
    assert (
        g1_adaptive_preconditioned_global_newton_runtime_budget["stop_reason"]
        == "runtime_budget_exceeded"
    )
    assert g1_adaptive_preconditioned_global_newton_runtime_budget["row_count"] == 0
    assert (
        g1_adaptive_preconditioned_global_newton_runtime_budget["promotion_count"]
        == 0
    )
    g1_current_checkpoint_single_row = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_single_largest_row_current_tangent"
    ]
    assert g1_current_checkpoint_single_row["status"] == "partial"
    assert (
        g1_current_checkpoint_single_row["base_direct_residual_inf_n"]
        == 7325.9547714166265
    )
    assert (
        g1_current_checkpoint_single_row["final_direct_residual_inf_n"]
        == 7312.271816678203
    )
    assert (
        g1_current_checkpoint_single_row[
            "current_tangent_residual_row_correction_accepted"
        ]
        is True
    )
    assert (
        g1_current_checkpoint_single_row["current_tangent_residual_row_promotion_count"]
        == 1
    )
    assert (
        g1_current_checkpoint_single_row[
            "best_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert (
        g1_current_checkpoint_single_row["best_candidate_residual_gate_passed"]
        is False
    )
    g1_current_checkpoint_single_row_replay = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_single_largest_row_current_tangent_replay"
    ]
    assert g1_current_checkpoint_single_row_replay["status"] == "partial"
    assert (
        g1_current_checkpoint_single_row_replay["base_direct_residual_inf_n"]
        == g1_current_checkpoint_single_row["final_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_single_row_replay["final_direct_residual_inf_n"]
        == g1_current_checkpoint_single_row_replay["base_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_single_row_replay[
            "current_tangent_residual_row_correction_enabled"
        ]
        is False
    )
    g1_current_checkpoint_single_row_followup = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_single_largest_row_current_tangent_followup"
    ]
    assert g1_current_checkpoint_single_row_followup["status"] == "partial"
    assert (
        g1_current_checkpoint_single_row_followup["base_direct_residual_inf_n"]
        == g1_current_checkpoint_single_row["final_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_single_row_followup["final_direct_residual_inf_n"]
        == g1_current_checkpoint_single_row_followup["base_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_single_row_followup[
            "current_tangent_residual_row_correction_accepted"
        ]
        is False
    )
    assert (
        g1_current_checkpoint_single_row_followup[
            "current_tangent_residual_row_stop_reason"
        ]
        == "no_residual_descent"
    )
    g1_current_checkpoint_single_row_fd = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_single_largest_row_fd_jacobian"
    ]
    assert g1_current_checkpoint_single_row_fd["status"] == "partial"
    assert (
        g1_current_checkpoint_single_row_fd["base_direct_residual_inf_n"]
        == g1_current_checkpoint_single_row["final_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_single_row_fd[
            "current_tangent_residual_row_jacobian_mode"
        ]
        == "finite_difference"
    )
    assert (
        g1_current_checkpoint_single_row_fd[
            "current_tangent_residual_row_correction_accepted"
        ]
        is False
    )
    assert (
        g1_current_checkpoint_single_row_fd[
            "current_tangent_residual_row_stop_reason"
        ]
        == "no_residual_descent"
    )
    g1_current_checkpoint_frame_tangent = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_frame_element_block_current_tangent"
    ]
    assert (
        g1_current_checkpoint_frame_tangent[
            "current_tangent_residual_row_target_mode"
        ]
        == "residual_frame_element_blocks"
    )
    assert (
        g1_current_checkpoint_frame_tangent[
            "current_tangent_residual_row_jacobian_mode"
        ]
        == "current_tangent"
    )
    assert (
        g1_current_checkpoint_frame_tangent[
            "current_tangent_residual_row_stop_reason"
        ]
        == "no_residual_descent"
    )
    g1_current_checkpoint_frame_fd = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_frame_element_block_fd_jacobian"
    ]
    assert (
        g1_current_checkpoint_frame_fd[
            "current_tangent_residual_row_target_mode"
        ]
        == "residual_frame_element_blocks"
    )
    assert (
        g1_current_checkpoint_frame_fd[
            "current_tangent_residual_row_jacobian_mode"
        ]
        == "finite_difference"
    )
    assert (
        g1_current_checkpoint_frame_fd[
            "current_tangent_residual_row_correction_accepted"
        ]
        is False
    )
    g1_current_checkpoint_trust = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_trust_iteration_strict_gate_probe"
    ]
    assert g1_current_checkpoint_trust["status"] == "partial"
    assert (
        g1_current_checkpoint_trust["base_direct_residual_inf_n"]
        == g1_current_checkpoint_single_row["final_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_trust["final_direct_residual_inf_n"]
        == 7312.271696594854
    )
    assert g1_current_checkpoint_trust["trust_region_accepted"] is True
    assert g1_current_checkpoint_trust["trust_region_accepted_iteration_count"] == 1
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_candidate_direct_residual_inf_n"
        ]
        == 7310.443801615268
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_candidate_relative_increment_gate_passed"
        ]
        is False
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_candidate_relative_increment"
        ]
        > 1.0
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_gate_eligible_candidate_direct_residual_inf_n"
        ]
        == g1_current_checkpoint_trust["final_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_gate_eligible_candidate_alpha"
        ]
        == g1_current_checkpoint_trust["trust_region_gate_limited_alpha"]
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_gate_eligible_candidate_alpha_source"
        ]
        == "trust_region_gate_limited"
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_gate_eligible_candidate_relative_increment"
        ]
        <= 1.0e-4
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_gate_eligible_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert (
        g1_current_checkpoint_trust[
            "trust_region_best_gate_eligible_candidate_free_dof_set_stable"
        ]
        is True
    )
    g1_current_checkpoint_trust_replay = rows["G1"]["evidence"][
        "direct_residual_current_checkpoint_trust_iteration_strict_gate_probe_replay"
    ]
    assert g1_current_checkpoint_trust_replay["status"] == "partial"
    assert (
        g1_current_checkpoint_trust_replay["base_direct_residual_inf_n"]
        == g1_current_checkpoint_trust["final_direct_residual_inf_n"]
    )
    assert (
        g1_current_checkpoint_trust_replay["final_direct_residual_inf_n"]
        == g1_current_checkpoint_trust["final_direct_residual_inf_n"]
    )
    assert g1_current_checkpoint_trust_replay["trust_region_accepted"] is False
    assert (
        g1_current_checkpoint_trust_replay["trust_region_accepted_iteration_count"]
        == 0
    )
    g1_frame_hotspot_diagonal = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier"
    ]
    assert g1_frame_hotspot_diagonal["status"] == "partial"
    assert (
        g1_frame_hotspot_diagonal["base_direct_residual_inf_n"]
        == g1_current_checkpoint_trust["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal["promoted_to_final_state"] is True
    assert (
        g1_frame_hotspot_diagonal["final_direct_residual_inf_n"]
        == 7305.146816442301
    )
    assert (
        g1_frame_hotspot_diagonal["promotion_candidate_relative_increment_gate_passed"]
        is True
    )
    assert g1_frame_hotspot_diagonal["promotion_candidate_alpha"] == 0.001
    assert (
        g1_frame_hotspot_diagonal["frame_hotspot_diagonal_newton_selected_count"]
        == 8
    )
    g1_frame_hotspot_diagonal_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_replay["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_diagonal_replay["final_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_diagonal_followup = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup"
    ]
    assert (
        g1_frame_hotspot_diagonal_followup["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal_followup["promoted_to_final_state"] is True
    assert (
        g1_frame_hotspot_diagonal_followup["final_direct_residual_inf_n"]
        == 7298.029063674274
    )
    assert (
        g1_frame_hotspot_diagonal_followup[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert g1_frame_hotspot_diagonal_followup["promotion_candidate_alpha"] == 0.001
    g1_frame_hotspot_diagonal_followup_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_followup_replay["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_followup["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_diagonal_followup_replay["final_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_followup["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_diagonal_multipass = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass"
    ]
    assert (
        g1_frame_hotspot_diagonal_multipass["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_followup["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal_multipass["promoted_to_final_state"] is True
    assert g1_frame_hotspot_diagonal_multipass["promotion_count"] == 6
    assert g1_frame_hotspot_diagonal_multipass["max_promotions"] == 6
    assert (
        g1_frame_hotspot_diagonal_multipass["stop_reason"]
        == "max_promotions_exhausted"
    )
    assert (
        g1_frame_hotspot_diagonal_multipass["final_direct_residual_inf_n"]
        == 7255.471813043352
    )
    g1_frame_hotspot_diagonal_multipass_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_multipass_replay["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_multipass["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_diagonal_multipass_replay["final_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_multipass["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_diagonal_multipass_followup = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup"
    ]
    assert (
        g1_frame_hotspot_diagonal_multipass_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_multipass["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal_multipass_followup[
        "promoted_to_final_state"
    ] is True
    assert g1_frame_hotspot_diagonal_multipass_followup["promotion_count"] == 6
    assert g1_frame_hotspot_diagonal_multipass_followup["max_promotions"] == 6
    assert (
        g1_frame_hotspot_diagonal_multipass_followup["stop_reason"]
        == "max_promotions_exhausted"
    )
    assert (
        g1_frame_hotspot_diagonal_multipass_followup[
            "final_direct_residual_inf_n"
        ]
        == 7216.53467452999
    )
    g1_frame_hotspot_diagonal_multipass_followup_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_multipass_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_multipass_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_multipass_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_multipass_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_signed = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier"
    ]
    assert (
        g1_frame_hotspot_signed["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_multipass_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_signed["promoted_to_final_state"] is True
    assert g1_frame_hotspot_signed["promotion_mode"] == "signed_displacement"
    assert g1_frame_hotspot_signed["promotion_count"] == 1
    assert g1_frame_hotspot_signed["max_promotions"] == 6
    assert g1_frame_hotspot_signed["stop_reason"] == "no_gate_eligible_descent"
    assert g1_frame_hotspot_signed["promotion_candidate_step_m"] == 1.0e-10
    assert (
        g1_frame_hotspot_signed["final_direct_residual_inf_n"]
        == 7213.16931149929
    )
    g1_frame_hotspot_signed_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_replay"
    ]
    assert (
        g1_frame_hotspot_signed_replay["base_direct_residual_inf_n"]
        == g1_frame_hotspot_signed["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_signed_replay["final_direct_residual_inf_n"]
        == g1_frame_hotspot_signed["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_diagonal_post_signed = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed["base_direct_residual_inf_n"]
        == g1_frame_hotspot_signed["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal_post_signed["promoted_to_final_state"] is True
    assert g1_frame_hotspot_diagonal_post_signed["promotion_count"] == 6
    assert g1_frame_hotspot_diagonal_post_signed["max_promotions"] == 6
    assert (
        g1_frame_hotspot_diagonal_post_signed["stop_reason"]
        == "max_promotions_exhausted"
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed["final_direct_residual_inf_n"]
        == 7171.102675752372
    )
    g1_frame_hotspot_diagonal_post_signed_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_diagonal_post_signed_followup = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal_post_signed_followup[
        "promoted_to_final_state"
    ] is True
    assert g1_frame_hotspot_diagonal_post_signed_followup["promotion_count"] == 12
    assert g1_frame_hotspot_diagonal_post_signed_followup["max_promotions"] == 12
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup["stop_reason"]
        == "max_promotions_exhausted"
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup[
            "final_direct_residual_inf_n"
        ]
        == 7105.697496519113
    )
    g1_frame_hotspot_diagonal_post_signed_followup_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_diagonal_post_signed_followup2 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_diagonal_post_signed_followup2[
        "promoted_to_final_state"
    ] is True
    assert g1_frame_hotspot_diagonal_post_signed_followup2["promotion_count"] == 12
    assert g1_frame_hotspot_diagonal_post_signed_followup2["max_promotions"] == 12
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2["stop_reason"]
        == "max_promotions_exhausted"
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2[
            "final_direct_residual_inf_n"
        ]
        == 7105.0304056597015
    )
    g1_frame_hotspot_diagonal_post_signed_followup2_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_signed_post_followup2 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2"
    ]
    assert (
        g1_frame_hotspot_signed_post_followup2["base_direct_residual_inf_n"]
        == g1_frame_hotspot_diagonal_post_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_signed_post_followup2["promoted_to_final_state"] is True
    assert g1_frame_hotspot_signed_post_followup2["promotion_mode"] == "signed_displacement"
    assert g1_frame_hotspot_signed_post_followup2["promotion_count"] == 1
    assert g1_frame_hotspot_signed_post_followup2["max_promotions"] == 12
    assert (
        g1_frame_hotspot_signed_post_followup2["stop_reason"]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_signed_post_followup2["final_direct_residual_inf_n"]
        == 7005.339091005231
    )
    g1_frame_hotspot_signed_post_followup2_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_signed_post_followup2_replay["base_direct_residual_inf_n"]
        == g1_frame_hotspot_signed_post_followup2["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_signed_post_followup2_replay["final_direct_residual_inf_n"]
        == g1_frame_hotspot_signed_post_followup2["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_followup2["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
        "promoted_to_final_state"
    ] is True
    assert g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
        "promotion_mode"
    ] == "diagonal_newton"
    assert g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
        "promotion_count"
    ] == 7
    assert g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
        "max_promotions"
    ] == 12
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
            "stop_reason"
        ]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
            "final_direct_residual_inf_n"
        ]
        == 6993.264581353599
    )
    g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup_replay = rows[
        "G1"
    ]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_signed_post_diagonal_signed_followup = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup"
    ]
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_signed_followup2_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_signed_post_diagonal_signed_followup[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup["promotion_mode"]
        == "signed_displacement"
    )
    assert g1_frame_hotspot_signed_post_diagonal_signed_followup[
        "promotion_count"
    ] == 1
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup["stop_reason"]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup[
            "final_direct_residual_inf_n"
        ]
        == 6957.716068351557
    )
    g1_frame_hotspot_signed_post_diagonal_signed_followup_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup_replay"
    ]
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_diagonal_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_diagonal_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_diagonal_post_diagonal_signed_followup2 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_diagonal_signed_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "promotion_mode"
        ]
        == "diagonal_newton"
    )
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "promotion_count"
        ]
        == 11
    )
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "stop_reason"
        ]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6892.053158842975
    )
    g1_frame_hotspot_diagonal_post_diagonal_signed_followup2_replay = rows[
        "G1"
    ]["evidence"][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_post_diagonal_signed_followup2_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_signed_post_diagonal_signed_followup2 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2"
    ]
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_signed_post_diagonal_signed_followup2[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "promotion_mode"
        ]
        == "signed_displacement"
    )
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2["stop_reason"]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6883.520270521328
    )
    g1_frame_hotspot_signed_post_diagonal_signed_followup2_replay = rows[
        "G1"
    ]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_signed_post_diagonal_signed_followup2_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_tiny = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_tiny["base_direct_residual_inf_n"]
        == g1_frame_hotspot_signed_post_diagonal_signed_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_tiny["promoted_to_final_state"] is True
    assert g1_frame_hotspot_block_lstsq_tiny["promotion_mode"] == "block_lstsq"
    assert g1_frame_hotspot_block_lstsq_tiny["promotion_count"] == 1
    assert g1_frame_hotspot_block_lstsq_tiny["stop_reason"] == "max_promotions_exhausted"
    assert (
        g1_frame_hotspot_block_lstsq_tiny["final_direct_residual_inf_n"]
        == 6876.6367502508065
    )
    assert g1_frame_hotspot_block_lstsq_tiny[
        "frame_hotspot_block_lstsq_selected_count"
    ] == 4
    assert g1_frame_hotspot_block_lstsq_tiny[
        "frame_hotspot_block_lstsq_support_size"
    ] >= 4
    g1_frame_hotspot_block_lstsq_tiny_followup = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_tiny["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup[
            "final_direct_residual_inf_n"
        ]
        == 6869.760113500556
    )
    g1_frame_hotspot_block_lstsq_tiny_followup2 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_tiny_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6862.890353387056
    )
    g1_frame_hotspot_block_lstsq_tiny_followup2_next = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup2_next[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_tiny_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup2_next[
            "final_direct_residual_inf_n"
        ]
        == 6856.027463033668
    )
    g1_frame_hotspot_block_lstsq_tiny_followup2_next_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup2_next_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_tiny_followup2_next[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_tiny_followup2_next_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_tiny_followup2_next[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_batch = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch["base_direct_residual_inf_n"]
        == g1_frame_hotspot_block_lstsq_tiny_followup2_next[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_batch["promotion_count"] == 1
    assert g1_frame_hotspot_block_lstsq_batch["promotion_mode"] == "block_lstsq"
    assert (
        g1_frame_hotspot_block_lstsq_batch["final_direct_residual_inf_n"]
        == 6849.171435570635
    )
    g1_frame_hotspot_block_lstsq_batch_fine = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine[
            "promotion_candidate_alpha"
        ]
        == 0.0005
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine[
            "final_direct_residual_inf_n"
        ]
        == 6845.74684985285
    )
    g1_frame_hotspot_block_lstsq_batch_fine_followup = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup[
            "final_direct_residual_inf_n"
        ]
        == 6842.323976427923
    )
    g1_frame_hotspot_block_lstsq_batch_fine_followup2 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6838.902814439709
    )
    g1_frame_hotspot_block_lstsq_batch_fine_followup2_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
        "promotion_count"
    ] == 4
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
            "promotion_candidate_alpha"
        ]
        == 0.0005
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
            "final_direct_residual_inf_n"
        ]
        == 6825.235263746027
    )
    g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch_replay = rows[
        "G1"
    ]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_wide8 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_wide8["base_direct_residual_inf_n"]
        == g1_frame_hotspot_block_lstsq_batch_fine_followup2_batch[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_wide8["promotion_mode"] == "block_lstsq"
    assert g1_frame_hotspot_block_lstsq_wide8["promotion_count"] == 1
    assert g1_frame_hotspot_block_lstsq_wide8[
        "frame_hotspot_block_lstsq_selected_count"
    ] == 8
    assert g1_frame_hotspot_block_lstsq_wide8[
        "frame_hotspot_block_lstsq_support_size"
    ] == 58
    assert (
        g1_frame_hotspot_block_lstsq_wide8["final_direct_residual_inf_n"]
        == 6818.410028482282
    )
    g1_frame_hotspot_block_lstsq_wide8_followup = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_block_lstsq_wide8_followup[
        "promotion_count"
    ] == 2
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup[
            "promotion_candidate_alpha"
        ]
        == 0.001
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup[
            "final_direct_residual_inf_n"
        ]
        == 6804.780026835346
    )
    g1_frame_hotspot_block_lstsq_wide8_followup_replay = rows["G1"][
        "evidence"
    ]["direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup_replay"]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_wide8_followup2 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_wide8_followup2[
        "promotion_count"
    ] == 2
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup2[
            "promotion_candidate_alpha"
        ]
        == 0.001
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6791.177271561701
    )
    g1_frame_hotspot_block_lstsq_wide8_followup2_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup2_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_followup2_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_wide8_alpha = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha["base_direct_residual_inf_n"]
        == g1_frame_hotspot_block_lstsq_wide8_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_wide8_alpha[
        "promotion_candidate_alpha"
    ] == 0.005
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha[
            "promotion_candidate_relative_increment"
        ]
        < 1.0e-4
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha[
            "final_direct_residual_inf_n"
        ]
        == 6757.221385203893
    )
    g1_frame_hotspot_block_lstsq_wide8_alpha_replay = rows["G1"][
        "evidence"
    ]["direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_replay"]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_alpha[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_alpha[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_wide8_alpha_followup = rows["G1"][
        "evidence"
    ]["direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup"]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_alpha[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha_followup[
            "final_direct_residual_inf_n"
        ]
        == 6716.711842999595
    )
    g1_frame_hotspot_block_lstsq_wide8_alpha_followup_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_alpha_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_wide8_alpha_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_wide8_alpha_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_gate_alpha = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha["base_direct_residual_inf_n"]
        == g1_frame_hotspot_block_lstsq_wide8_alpha_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        0.005
        < g1_frame_hotspot_block_lstsq_gate_alpha["promotion_candidate_alpha"]
        < 0.006
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha[
            "promotion_candidate_relative_increment"
        ]
        <= 1.0e-4
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha[
            "final_direct_residual_inf_n"
        ]
        == 6680.772153435075
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_block_lstsq_gate_alpha_followup[
        "promoted_to_final_state"
    ] is True
    assert (
        0.005
        < g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "promotion_candidate_alpha"
        ]
        < 0.006
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "promotion_candidate_relative_increment"
        ]
        <= 1.0e-4
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "final_direct_residual_inf_n"
        ]
        == 6645.0522909041065
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup2 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
        "promoted_to_final_state"
    ] is True
    assert (
        0.005
        < g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "promotion_candidate_alpha"
        ]
        < 0.006
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "promotion_candidate_relative_increment"
        ]
        <= 1.0e-4
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6607.81899605729
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup2_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup2_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup2_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup3 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
        "promoted_to_final_state"
    ] is True
    assert (
        0.005
        < g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "promotion_candidate_alpha"
        ]
        < 0.006
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "promotion_candidate_relative_increment"
        ]
        <= 1.0e-4
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "final_direct_residual_inf_n"
        ]
        == 6570.266723299206
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup3_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3_replay"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup3_replay[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup3_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4[
            "promoted_to_final_state"
        ]
        is False
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4["stop_reason"]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup4[
            "base_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup4_support16 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support16"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_support16[
            "stop_reason"
        ]
        == "no_gate_eligible_descent"
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup4_support32 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support32"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_support32[
            "stop_reason"
        ]
        == "no_gate_eligible_descent"
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4"
    ]
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup3[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
            "promotion_candidate_alpha"
        ]
        == 0.001
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6569.156742952773
    )
    g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4_replay = rows[
        "G1"
    ]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4_replay"
    ]
    assert (
        abs(
            g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4_replay[
                "base_direct_residual_inf_n"
            ]
            - g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
                "final_direct_residual_inf_n"
            ]
        )
        <= 1.0e-9
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_signed_post_rows4 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4"
    ]
    assert (
        abs(
            g1_frame_hotspot_signed_post_rows4["base_direct_residual_inf_n"]
            - g1_frame_hotspot_block_lstsq_gate_alpha_followup4_rows4[
                "final_direct_residual_inf_n"
            ]
        )
        <= 1.0e-9
    )
    assert g1_frame_hotspot_signed_post_rows4["promoted_to_final_state"] is True
    assert g1_frame_hotspot_signed_post_rows4["promotion_candidate_step_m"] == 1.0e-10
    assert (
        g1_frame_hotspot_signed_post_rows4["final_direct_residual_inf_n"]
        == 6563.696456575908
    )
    g1_frame_hotspot_signed_post_rows4_replay = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4_replay"
    ]
    assert (
        g1_frame_hotspot_signed_post_rows4_replay["base_direct_residual_inf_n"]
        == g1_frame_hotspot_signed_post_rows4["final_direct_residual_inf_n"]
    )
    assert (
        g1_frame_hotspot_signed_post_rows4_replay["final_direct_residual_inf_n"]
        == g1_frame_hotspot_signed_post_rows4["final_direct_residual_inf_n"]
    )
    g1_frame_hotspot_block_post_signed_rows4 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4"
    ]
    assert (
        g1_frame_hotspot_block_post_signed_rows4["stop_reason"]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_block_post_signed_rows4["final_direct_residual_inf_n"]
        == g1_frame_hotspot_block_post_signed_rows4["base_direct_residual_inf_n"]
    )
    g1_frame_hotspot_block_post_signed_rows4_rows4 = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4"
    ]
    assert (
        g1_frame_hotspot_block_post_signed_rows4_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_rows4["final_direct_residual_inf_n"]
    )
    assert g1_frame_hotspot_block_post_signed_rows4_rows4[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_block_post_signed_rows4_rows4[
            "promotion_candidate_alpha"
        ]
        == 0.001
    )
    assert (
        g1_frame_hotspot_block_post_signed_rows4_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6560.830484870141
    )
    g1_frame_hotspot_block_post_signed_rows4_rows4_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4_replay"
    ]
    assert (
        g1_frame_hotspot_block_post_signed_rows4_rows4_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_signed_rows4_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    g1_current_tangent_post_signed_rows4_rows4 = rows["G1"]["evidence"][
        "direct_residual_current_frontier_frame_block_current_tangent_narrow_post_signed_rows4_rows4"
    ]
    assert g1_current_tangent_post_signed_rows4_rows4[
        "current_tangent_residual_row_correction_accepted"
    ] is True
    assert (
        g1_current_tangent_post_signed_rows4_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_signed_rows4_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_current_tangent_post_signed_rows4_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6557.5500695988685
    )
    g1_frame_hotspot_signed_post_tangent_narrow = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow"
    ]
    assert (
        g1_frame_hotspot_signed_post_tangent_narrow[
            "base_direct_residual_inf_n"
        ]
        == g1_current_tangent_post_signed_rows4_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_signed_post_tangent_narrow[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_signed_post_tangent_narrow[
            "promotion_candidate_step_m"
        ]
        == 1.0e-10
    )
    assert (
        g1_frame_hotspot_signed_post_tangent_narrow[
            "final_direct_residual_inf_n"
        ]
        == 6557.132760119332
    )
    g1_frame_hotspot_signed_post_tangent_narrow_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow_replay"
    ]
    assert (
        g1_frame_hotspot_signed_post_tangent_narrow_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_tangent_narrow[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_post_tangent_signed = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed"
    ]
    assert (
        g1_frame_hotspot_block_post_tangent_signed[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_signed_post_tangent_narrow[
            "final_direct_residual_inf_n"
        ]
    )
    assert g1_frame_hotspot_block_post_tangent_signed[
        "promoted_to_final_state"
    ] is True
    assert (
        g1_frame_hotspot_block_post_tangent_signed[
            "promotion_candidate_alpha"
        ]
        == 0.001
    )
    assert (
        g1_frame_hotspot_block_post_tangent_signed[
            "final_direct_residual_inf_n"
        ]
        == 6550.575627359212
    )
    g1_frame_hotspot_block_post_tangent_signed_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_replay"
    ]
    assert (
        g1_frame_hotspot_block_post_tangent_signed_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_tangent_signed[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_post_tangent_signed_rows4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4"
    ]
    assert (
        g1_frame_hotspot_block_post_tangent_signed_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_tangent_signed[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_tangent_signed_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6547.300339545533
    )
    g1_frame_hotspot_block_post_tangent_signed_rows4_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4_replay"
    ]
    assert (
        g1_frame_hotspot_block_post_tangent_signed_rows4_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_tangent_signed_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_diagonal_post_tangent_signed_rows4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_tangent_signed_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_tangent_signed_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_post_tangent_signed_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6540.922416805359
    )
    g1_frame_hotspot_diagonal_post_tangent_signed_rows4_followup = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4_followup"
    ]
    assert (
        g1_frame_hotspot_diagonal_post_tangent_signed_rows4_followup[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_tangent_signed_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_diagonal_post_tangent_signed_rows4_followup[
            "final_direct_residual_inf_n"
        ]
        == 6534.550925656016
    )
    g1_frame_hotspot_block_post_diagonal_followup_rows4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_diagonal_followup_rows4"
    ]
    assert (
        g1_frame_hotspot_block_post_diagonal_followup_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_diagonal_post_tangent_signed_rows4_followup[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_diagonal_followup_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6531.283650193189
    )
    g1_frame_hotspot_block_post_block_followup_rows4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4"
    ]
    assert (
        g1_frame_hotspot_block_post_block_followup_rows4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_diagonal_followup_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_followup_rows4[
            "final_direct_residual_inf_n"
        ]
        == 6524.752366542994
    )
    assert (
        g1_frame_hotspot_block_post_block_followup_rows4[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 4
    )
    assert (
        g1_frame_hotspot_block_post_block_followup_rows4[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 34
    )
    g1_frame_hotspot_block_post_block_followup_rows4_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4_replay"
    ]
    assert (
        g1_frame_hotspot_block_post_block_followup_rows4_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_followup_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_post_block_rows8_followup2 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows8_followup2"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows8_followup2[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_followup_rows4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows8_followup2[
            "final_direct_residual_inf_n"
        ]
        == 6521.489990359723
    )
    assert (
        g1_frame_hotspot_block_post_block_rows8_followup2[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 8
    )
    g1_frame_hotspot_block_post_block_rows12_followup3 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows12_followup3"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows12_followup3[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows8_followup2[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows12_followup3[
            "final_direct_residual_inf_n"
        ]
        == 6483.933515906723
    )
    assert (
        g1_frame_hotspot_block_post_block_rows12_followup3[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 12
    )
    g1_frame_hotspot_block_post_block_rows16_followup4 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows16_followup4"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows16_followup4[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows12_followup3[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows16_followup4[
            "final_direct_residual_inf_n"
        ]
        == 6449.142677918151
    )
    assert (
        g1_frame_hotspot_block_post_block_rows16_followup4[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 16
    )
    g1_frame_hotspot_block_post_block_rows20_followup5 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup5"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup5[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows16_followup4[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup5[
            "final_direct_residual_inf_n"
        ]
        == 6417.030627577194
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup5[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    g1_frame_hotspot_block_post_block_rows20_followup6 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup6[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows20_followup5[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup6[
            "final_direct_residual_inf_n"
        ]
        == 6385.116404581466
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup6[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup6[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 142
    )
    g1_frame_hotspot_block_post_block_rows20_followup6_replay = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6_replay"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup6_replay[
            "final_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows20_followup6[
            "final_direct_residual_inf_n"
        ]
    )
    g1_frame_hotspot_block_post_block_rows20_followup7 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup7"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup7[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows20_followup6[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup7[
            "final_direct_residual_inf_n"
        ]
        == 6355.187822144744
    )
    assert (
        g1_frame_hotspot_block_post_block_rows20_followup7[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    g1_frame_hotspot_block_post_block_rows21_followup7 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_followup7"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_followup7[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows20_followup6[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_followup7[
            "final_direct_residual_inf_n"
        ]
        == 6354.8767856721515
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_followup7[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 21
    )
    g1_frame_hotspot_block_post_block_rows21_support16_followup7 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup7"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows20_followup6[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "final_direct_residual_inf_n"
        ]
        == 6354.488211004593
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_post_block_rows21_followup7[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 21
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 202
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup7_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup7_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup7_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup7_component_breakdown"
    ]
    assert post_block_component_breakdown["component_inf_n"]["frame"] > 2418.0
    assert post_block_component_breakdown["component_inf_n"]["shell_membrane"] > 2614.0
    assert post_block_component_breakdown["top_row_dominant_component_counts"][
        "frame"
    ] == 20
    g1_frame_hotspot_block_post_block_rows21_support16_followup8 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup8"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup7[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "final_direct_residual_inf_n"
        ]
        == 6322.126691982422
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 203
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    g1_frame_hotspot_block_post_block_rows21_support16_followup9 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup9"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "final_direct_residual_inf_n"
        ]
        == 6291.868996137375
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_post_block_rows21_support16_followup8[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 206
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup9_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup9_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup9_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_followup9_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup9_component_breakdown"
    ]
    assert post_block_followup9_component_breakdown["component_inf_n"]["frame"] > 2358.0
    assert post_block_followup9_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2614.0
    assert post_block_followup9_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_post_block_rows21_support16_followup10 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup10"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup9[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "final_direct_residual_inf_n"
        ]
        == 6262.085519334063
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 205
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    g1_frame_hotspot_block_post_block_rows21_support16_followup11 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup11"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "final_direct_residual_inf_n"
        ]
        == 6231.827823489015
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_post_block_rows21_support16_followup10[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 207
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup11_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup11_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup11_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_followup11_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup11_component_breakdown"
    ]
    assert post_block_followup11_component_breakdown["component_inf_n"]["frame"] > 2410.0
    assert post_block_followup11_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2614.0
    assert post_block_followup11_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_post_block_rows21_support16_followup12 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup12"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup11[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "final_direct_residual_inf_n"
        ]
        == 6201.526714728498
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 206
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    g1_frame_hotspot_block_post_block_rows21_support16_followup13 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup13"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "final_direct_residual_inf_n"
        ]
        == 6168.906165812469
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_post_block_rows21_support16_followup12[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 19
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 202
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "promotion_candidate_relative_increment_gate_passed"
        ]
        is True
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup13_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup13_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup13_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_followup13_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup13_component_breakdown"
    ]
    assert post_block_followup13_component_breakdown["component_inf_n"]["frame"] > 2474.0
    assert post_block_followup13_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2614.0
    assert post_block_followup13_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_post_block_rows21_support16_followup16 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup16"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup13[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "final_direct_residual_inf_n"
        ]
        == 6078.021415574665
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "promotion_count"
        ]
        == 3
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "promotion_pass_base_direct_residual_inf_n"
        ]
        == [6168.906165812469, 6138.649616571666, 6108.335516073165]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [6138.649616571666, 6108.335516073165, 6078.021415574665]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True, True, True]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 217
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup16_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup16_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup16_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_followup16_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup16_component_breakdown"
    ]
    assert post_block_followup16_component_breakdown["component_inf_n"]["frame"] > 2566.0
    assert post_block_followup16_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2614.0
    assert post_block_followup16_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_post_block_rows21_support16_followup21 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup21"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup16[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "final_direct_residual_inf_n"
        ]
        == 5927.737618081928
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "final_direct_residual_inf_n"
        ]
        < 6000.0
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "promotion_count"
        ]
        == 5
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "promotion_pass_base_direct_residual_inf_n"
        ]
        == [
            6078.021415574665,
            6049.100599700492,
            6018.844050459689,
            5988.369093656822,
            5958.051403925605,
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [
            6049.100599700492,
            6018.844050459689,
            5988.369093656822,
            5958.051403925605,
            5927.737618081928,
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True, True, True, True, True]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 20
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 222
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup21_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup21_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup21_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_followup21_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup21_component_breakdown"
    ]
    assert post_block_followup21_component_breakdown["component_inf_n"]["frame"] > 2908.0
    assert post_block_followup21_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2614.0
    assert post_block_followup21_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 19
    assert post_block_followup21_component_breakdown[
        "top_row_dominant_component_counts"
    ]["shell_bending_drilling"] == 4
    g1_frame_hotspot_block_post_block_rows21_support16_followup31 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup31"
    ]
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup21[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "final_direct_residual_inf_n"
        ]
        == 5886.372194347398
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "final_direct_residual_inf_n"
        ]
        < 5900.0
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "promotion_count"
        ]
        == 2
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "stop_reason"
        ]
        == "no_gate_eligible_descent"
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5897.376264903195, 5886.372194347398]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True, True]
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 19
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 205
    )
    assert (
        g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup31_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup31_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_followup31_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_followup31_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_followup31_component_breakdown"
    ]
    assert post_block_followup31_component_breakdown["component_inf_n"]["frame"] > 3098.0
    assert post_block_followup31_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2614.0
    assert post_block_followup31_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 19
    assert post_block_followup31_component_breakdown[
        "top_row_dominant_component_counts"
    ]["shell_membrane"] == 1
    g1_frame_hotspot_block_translation_rows21_support16_followup34 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support16_followup34"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "final_direct_residual_inf_n"
        ]
        == 5850.328431810043
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_post_block_rows21_support16_followup31[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "promotion_count"
        ]
        == 3
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "stop_reason"
        ]
        == "max_promotions_exhausted"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5874.357606834948, 5862.343019322496, 5850.328431810043]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True, True, True]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 16, "shell_bending_drilling": 4}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "frame_hotspot_block_lstsq_selected_count"
        ]
        == 21
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 238
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_translation_followup34_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_translation_followup34_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support16_translation_followup34_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup34_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support16_translation_followup34_component_breakdown"
    ]
    assert post_block_translation_followup34_component_breakdown["component_inf_n"][
        "frame"
    ] > 3207.0
    assert post_block_translation_followup34_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2579.0
    assert post_block_translation_followup34_component_breakdown[
        "top_row_dominant_component_counts"
    ]["shell_membrane"] == 1
    g1_frame_hotspot_block_translation_rows21_support32_followup35 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup35"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "final_direct_residual_inf_n"
        ]
        == 5836.367803368419
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_translation_rows21_support16_followup34[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 17, "shell_bending_drilling": 3}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 342
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5836.367803368419]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup35_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup35_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup35_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup35_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup35_component_breakdown"
    ]
    assert post_block_translation_followup35_component_breakdown["component_inf_n"][
        "frame"
    ] > 3249.0
    assert post_block_translation_followup35_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2565.0
    assert post_block_translation_followup35_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_translation_rows21_support64_followup36 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support64_followup36"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "final_direct_residual_inf_n"
        ]
        == 5824.357499442276
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_translation_rows21_support32_followup35[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 17, "shell_bending_drilling": 3}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 354
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5824.357499442276]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support64_translation_followup36_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support64_translation_followup36_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support64_translation_followup36_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup36_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support64_translation_followup36_component_breakdown"
    ]
    assert post_block_translation_followup36_component_breakdown["component_inf_n"][
        "frame"
    ] > 3285.0
    assert post_block_translation_followup36_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2553.0
    assert post_block_translation_followup36_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_translation_rows21_support32_followup37 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup37"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "final_direct_residual_inf_n"
        ]
        == 5810.396871000652
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_translation_rows21_support64_followup36[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 18, "shell_bending_drilling": 2}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 327
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5810.396871000652]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup37_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup37_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup37_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup37_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup37_component_breakdown"
    ]
    assert post_block_translation_followup37_component_breakdown["component_inf_n"][
        "frame"
    ] > 3328.0
    assert post_block_translation_followup37_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2539.0
    assert post_block_translation_followup37_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_translation_rows21_support32_followup42 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup42"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup37[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "final_direct_residual_inf_n"
        ]
        == 5742.548363248055
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "promotion_count"
        ]
        == 5
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [
            5798.39087701455,
            5784.430248572926,
            5770.469620131304,
            5756.5089916896795,
            5742.548363248055,
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True, True, True, True, True]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 18, "shell_bending_drilling": 2}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 322
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup42_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup42_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup42_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup42_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup42_component_breakdown"
    ]
    assert post_block_translation_followup42_component_breakdown["component_inf_n"][
        "frame"
    ] > 3481.0
    assert post_block_translation_followup42_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] > 2473.0
    assert post_block_translation_followup42_component_breakdown[
        "top_row_dominant_component_counts"
    ]["frame"] == 20
    g1_frame_hotspot_block_translation_rows21_support32_followup47 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup47"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup42[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "final_direct_residual_inf_n"
        ]
        == 5674.717309170781
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "promotion_count"
        ]
        == 5
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [
            5730.559822937275,
            5716.599194495651,
            5702.63856605403,
            5688.677937612405,
            5674.717309170781,
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True, True, True, True, True]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 18, "shell_bending_drilling": 2}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 332
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup47_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup47_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup47_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup47_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup47_component_breakdown"
    ]
    assert post_block_translation_followup47_component_breakdown["component_inf_n"][
        "frame"
    ] == 3482.1284647623875
    assert post_block_translation_followup47_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] == 2406.362748364031
    assert post_block_translation_followup47_component_breakdown[
        "top_row_dominant_component_counts"
    ] == {"shell_membrane": 1, "frame": 20, "shell_bending_drilling": 3}
    g1_frame_hotspot_block_translation_rows21_support32_followup48 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup48"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup47[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "final_direct_residual_inf_n"
        ]
        == 5662.74655057728
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5662.74655057728]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "promotion_pass_relative_increment_gate_passed"
        ]
        == [True]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 17, "shell_bending_drilling": 3}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 319
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "promotion_candidate_residual_gate_passed"
        ]
        is False
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup48_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup48_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup48_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup48_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup48_component_breakdown"
    ]
    assert post_block_translation_followup48_component_breakdown["component_inf_n"][
        "frame"
    ] == 3517.743223902462
    assert post_block_translation_followup48_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] == 2394.594587483238
    assert post_block_translation_followup48_component_breakdown[
        "top_row_dominant_component_counts"
    ] == {"shell_membrane": 1, "frame": 20, "shell_bending_drilling": 3}
    g1_frame_hotspot_block_translation_rows21_support32_followup49 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup49"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "final_direct_residual_inf_n"
        ]
        == 5648.785922135653
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_translation_rows21_support32_followup48[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5648.785922135653]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 315
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "output_final_checkpoint_path"
        ]
        == "/tmp/g1_followup_progress_archive/mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup49_probe_final_checkpoint.npz"
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup49_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup49_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup49_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup49_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup49_component_breakdown"
    ]
    assert post_block_translation_followup49_component_breakdown["component_inf_n"][
        "frame"
    ] == 3506.9437246956677
    assert post_block_translation_followup49_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] == 2380.8702340753234
    assert post_block_translation_followup49_component_breakdown[
        "top_row_dominant_component_counts"
    ] == {"shell_membrane": 1, "frame": 20, "shell_bending_drilling": 3}
    g1_frame_hotspot_block_translation_rows21_support32_followup50 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup50"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "final_direct_residual_inf_n"
        ]
        == 5634.82529369403
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_translation_rows21_support32_followup49[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5634.82529369403]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 18, "shell_bending_drilling": 2}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 320
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "output_final_checkpoint_path"
        ]
        == "/tmp/g1_followup_progress_archive/mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup50_probe_final_checkpoint.npz"
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup50_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup50_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup50_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup50_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup50_component_breakdown"
    ]
    assert post_block_translation_followup50_component_breakdown["component_inf_n"][
        "frame"
    ] == 3496.1390256393806
    assert post_block_translation_followup50_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] == 2367.1458806674123
    assert post_block_translation_followup50_component_breakdown[
        "top_row_dominant_component_counts"
    ] == {"shell_membrane": 1, "frame": 20, "shell_bending_drilling": 3}
    g1_frame_hotspot_block_translation_rows21_support32_followup51 = rows["G1"][
        "evidence"
    ][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup51"
    ]
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "base_direct_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "final_direct_residual_inf_n"
        ]
        == 5622.863556797554
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "final_direct_residual_inf_n"
        ]
        < g1_frame_hotspot_block_translation_rows21_support32_followup50[
            "final_direct_residual_inf_n"
        ]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "promotion_count"
        ]
        == 1
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "promotion_pass_actual_direct_residual_inf_n"
        ]
        == [5622.863556797554]
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "frame_hotspot_block_lstsq_component_filter"
        ]
        == "translation"
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "frame_hotspot_block_lstsq_selected_component_counts"
        ]
        == {"shell_membrane": 1, "frame": 17, "shell_bending_drilling": 3}
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "frame_hotspot_block_lstsq_support_size"
        ]
        == 312
    )
    assert (
        g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "output_final_checkpoint_path"
        ]
        == "/tmp/g1_followup_progress_archive/mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup51_probe_final_checkpoint.npz"
    )
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup51_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup51_component_only"
    ] is True
    assert (
        rows["G1"]["evidence"][
            "residual_jacobian_post_block_rows21_support32_translation_followup51_base_residual_inf_n"
        ]
        == g1_frame_hotspot_block_translation_rows21_support32_followup51[
            "final_direct_residual_inf_n"
        ]
    )
    post_block_translation_followup51_component_breakdown = rows["G1"]["evidence"][
        "residual_jacobian_post_block_rows21_support32_translation_followup51_component_breakdown"
    ]
    assert post_block_translation_followup51_component_breakdown["component_inf_n"][
        "frame"
    ] == 3486.881350177466
    assert post_block_translation_followup51_component_breakdown["component_inf_n"][
        "shell_membrane"
    ] == 2355.386588796982
    assert post_block_translation_followup51_component_breakdown[
        "top_row_dominant_component_counts"
    ] == {"shell_membrane": 1, "frame": 21, "shell_bending_drilling": 2}
    support32_translation_series = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup_series"
    ]
    assert support32_translation_series["series_schema"] == (
        "mgt-translation-frontier-followup-series.v1"
    )
    assert support32_translation_series["count"] >= 11
    assert support32_translation_series["strictly_decreasing_final_residual"] is True
    series_rows = support32_translation_series["rows"]
    assert support32_translation_series["count"] == len(series_rows)
    assert (
        support32_translation_series["latest_followup_index"]
        == series_rows[-1]["followup_index"]
    )
    assert (
        support32_translation_series["latest_final_direct_residual_inf_n"]
        == series_rows[-1]["final_direct_residual_inf_n"]
    )
    assert support32_translation_series["latest_followup_index"] >= 54
    assert support32_translation_series["latest_final_direct_residual_inf_n"] <= (
        5555.073010872516
    )
    followup57_timeout = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_diagnostic"
    ]
    assert followup57_timeout["status"] == "partial"
    assert followup57_timeout["stop_reason"] == "max_wall_seconds_exceeded"
    assert followup57_timeout["promotion_count"] == 0
    assert (
        followup57_timeout["base_direct_residual_inf_n"]
        == support32_translation_series["latest_final_direct_residual_inf_n"]
    )
    assert (
        followup57_timeout["final_direct_residual_inf_n"]
        == support32_translation_series["latest_final_direct_residual_inf_n"]
    )
    assert "frontier_probe_wall_time_exceeded" in followup57_timeout["blockers"]
    followup57_timeout_runtime = rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_runtime"
    ]
    assert followup57_timeout_runtime["max_wall_seconds"] == 0.0
    assert followup57_timeout_runtime["total_seconds"] > 0.0
    assert "frontier_probe_wall_time_exceeded" in rows["G1"]["evidence"][
        "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_blockers"
    ]
    assert series_rows[-1]["component_status"] == "partial"
    assert series_rows[-1]["component_only"] is True
    assert series_rows[-1]["component_base_residual_inf_n"] == series_rows[-1][
        "final_direct_residual_inf_n"
    ]
    contiguous_rows = [row for row in series_rows if int(row["followup_index"]) >= 37]
    assert all(
        later["base_direct_residual_inf_n"] == earlier["final_direct_residual_inf_n"]
        for earlier, later in zip(contiguous_rows, contiguous_rows[1:], strict=False)
    )
    followup54 = next(row for row in series_rows if row["followup_index"] == 54)
    assert followup54["final_direct_residual_inf_n"] == 5555.073010872516
    assert followup54["promotion_count"] == 3
    assert followup54["promotion_pass_actual_direct_residual_inf_n"] == [
        5580.981671472682,
        5569.033639314141,
        5555.073010872516,
    ]
    assert followup54["promotion_pass_relative_increment_gate_passed"] == [
        True,
        True,
        True,
    ]
    assert followup54["frame_hotspot_block_lstsq_support_size"] == 339
    assert followup54["frame_hotspot_block_lstsq_selected_component_counts"] == {
        "shell_membrane": 1,
        "frame": 18,
        "shell_bending_drilling": 2,
    }
    assert (
        followup54["output_final_checkpoint_path"]
        == "/tmp/g1_followup_progress_archive/mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup54_probe_final_checkpoint.npz"
    )
    assert followup54["component_status"] == "partial"
    assert followup54["component_only"] is True
    assert followup54["component_base_residual_inf_n"] == followup54[
        "final_direct_residual_inf_n"
    ]
    assert followup54["component_inf_n"]["frame"] == 3539.777606168417
    assert followup54["component_inf_n"]["shell_membrane"] == 2288.743356088593
    assert followup54["top_row_dominant_component_counts"] == {
        "shell_membrane": 1,
        "frame": 20,
        "shell_bending_drilling": 3,
    }
    assert rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_component_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_component_only"
    ] is True
    assert (
        abs(
            rows["G1"]["evidence"][
                "residual_jacobian_current_frontier_base_residual_inf_n"
            ]
            - g1_frame_hotspot_block_post_block_rows20_followup6[
                "final_direct_residual_inf_n"
            ]
        )
        <= 1.0e-9
    )
    current_frontier_components = rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_component_breakdown"
    ]
    assert current_frontier_components["component_inf_n"]["frame"] > 2440.0
    assert current_frontier_components["top_row_dominant_component_counts"][
        "frame"
    ] == 21
    current_frontier_frame_hotspots = rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_hotspot_frame_diagnostics"
    ]
    assert current_frontier_frame_hotspots
    assert current_frontier_frame_hotspots[0]["raw_node_id"] == 11233
    assert (
        current_frontier_frame_hotspots[0][
            "incident_frame_target_dof_contribution_sum_n"
        ]
        == current_frontier_frame_hotspots[0]["component_frame_n"]
    )
    assert (
        abs(current_frontier_frame_hotspots[0]["component_reconstruction_error_n"])
        <= 1.0e-9
    )
    assert (
        current_frontier_frame_hotspots[0]["sample_incident_frame_elements"][0][
            "verticality_abs_dz_over_length"
        ]
        == 1.0
    )
    assert (
        abs(
            current_frontier_frame_hotspots[0]["sample_incident_frame_elements"][
                0
            ]["target_dof_force_contribution_n"]
        )
        > 1100.0
    )
    current_frontier_frame_sweep = rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_frame_hotspot_signed_sweep"
    ]
    assert current_frontier_frame_sweep["evaluated"] is True
    assert current_frontier_frame_sweep["selected_hotspot_row_count"] == 21
    assert (
        abs(
            current_frontier_frame_sweep["best_gate_eligible_candidate"][
                "direct_residual_inf_n"
            ]
            - current_frontier_frame_sweep["base_direct_residual_inf_n"]
        )
        <= 1.0e-9
    )
    assert (
        current_frontier_frame_sweep["best_gate_eligible_candidate"][
            "direct_residual_inf_n"
        ]
        <= current_frontier_frame_sweep["base_direct_residual_inf_n"]
    )
    current_frontier_frame_large_sweep = rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_frame_hotspot_large_signed_sweep"
    ]
    assert current_frontier_frame_large_sweep["evaluated"] is True
    assert current_frontier_frame_large_sweep["best_gate_eligible_candidate"] == {}
    assert (
        current_frontier_frame_large_sweep["best_candidate"][
            "direct_residual_inf_n"
        ]
        >= current_frontier_frame_large_sweep["base_direct_residual_inf_n"]
    )
    current_frontier_jvp = rows["G1"]["evidence"][
        "residual_jacobian_current_frontier_frame_hotspot_jvp"
    ]
    assert (
        abs(
            current_frontier_jvp["base_residual_inf_n"]
            - rows["G1"]["evidence"][
                "residual_jacobian_current_frontier_base_residual_inf_n"
            ]
        )
        <= 1.0e-9
    )
    assert current_frontier_jvp["evaluated_row_count"] == 8
    assert current_frontier_jvp["max_relative_inf_error"] <= 1.0e-12
    assert current_frontier_jvp["max_relative_l2_error"] <= 1.0e-12
    assert current_frontier_jvp["min_action_cosine"] >= 0.999999999999
    assert (
        current_frontier_jvp["first_evaluated_row"]["global_dof"]
        == current_frontier_frame_hotspots[0]["global_dof"]
    )
    g1_current_frontier_frame_block_narrow = rows["G1"]["evidence"][
        "direct_residual_current_frontier_frame_block_current_tangent_narrow"
    ]
    assert (
        abs(
            g1_current_frontier_frame_block_narrow["base_direct_residual_inf_n"]
            - rows["G1"]["evidence"][
                "residual_jacobian_current_frontier_base_residual_inf_n"
            ]
        )
        <= 1.0e-9
    )
    assert (
        g1_current_frontier_frame_block_narrow["final_direct_residual_inf_n"]
        == g1_current_frontier_frame_block_narrow["base_direct_residual_inf_n"]
    )
    assert (
        g1_current_frontier_frame_block_narrow[
            "current_tangent_residual_row_correction_enabled"
        ]
        is True
    )
    assert (
        g1_current_frontier_frame_block_narrow[
            "current_tangent_residual_row_correction_accepted"
        ]
        is False
    )
    assert (
        g1_current_frontier_frame_block_narrow[
            "current_tangent_residual_row_stop_reason"
        ]
        == "no_residual_descent"
    )
    g1_historical_adaptive_replay_audit = rows["G1"]["evidence"][
        "direct_residual_historical_adaptive_checkpoint_current_residual_replay_audit"
    ]
    assert g1_historical_adaptive_replay_audit["status"] == "partial"
    assert (
        g1_historical_adaptive_replay_audit["base_direct_residual_inf_n"]
        == 34170785996.372658
    )
    assert (
        g1_historical_adaptive_replay_audit["base_direct_residual_inf_n"]
        > g1_current_checkpoint_single_row_replay["base_direct_residual_inf_n"]
    )
    assert (
        g1_historical_adaptive_replay_audit[
            "current_tangent_residual_row_correction_enabled"
        ]
        is False
    )
    g1_uncoarsened_secant_seed = rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_secant_seed_probe"
    ]
    assert g1_uncoarsened_secant_seed["status"] == "partial"
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_secant_seed_probe_status"
    ] == "partial"
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_secant_seed_probe_max_converged_load_scale"
    ] == 0.5406
    assert rows["G1"]["evidence"][
        "uncoarsened_boundary_pdelta_secant_seed_probe_first_failed_load_scale"
    ] == 0.540601
    secant_failed = g1_uncoarsened_secant_seed["step_results"][0]
    assert secant_failed["initial_seed_strategy"] == "secant_predicted_checkpoint_seed"
    assert secant_failed["secant_seed"]["enabled"] is True
    assert secant_failed["secant_seed"]["previous_load_scale"] == 0.54
    assert secant_failed["secant_seed"]["current_load_scale"] == 0.5406
    assert secant_failed["secant_seed"]["target_load_scale"] == 0.540601
    assert secant_failed["best_residual_inf_n"] <= secant_failed["residual_tolerance_n"]
    assert (
        secant_failed["best_fixed_point_relative_increment"]
        > secant_failed["relative_increment_tolerance"]
    )
    assert g1_uncoarsened_boundary["authored_support_restrained_dof_count"] == 7707
    assert g1_uncoarsened_boundary["finite_spring_component_count"] == 1692 * 6
    assert g1_uncoarsened_boundary["elastic_link_rows_skipped"] == 0
    assert (
        "consistent_newton_jacobian_required"
        in rows["G1"]["evidence"]["uncoarsened_boundary_pdelta_blockers"]
    )
    g1_line_search = rows["G1"]["evidence"]["pdelta_first_failed_one_step_line_search_probe"]
    assert g1_line_search["ready"] is False
    assert g1_line_search["target_load_scale"] == 0.55
    assert g1_line_search["best_residual_reduction_factor"] > 1.0
    g1_anderson = rows["G1"]["evidence"]["pdelta_first_failed_anderson_acceleration_probe"]
    assert g1_anderson["iteration_count"] == 48
    assert g1_anderson["history_depth"] == 8
    assert g1_anderson["best_relative_increment"] > g1_anderson["relative_increment_tolerance"]
    assert g1_anderson["best_relative_increment"] < 3.0e-3
    g1_bounded_anderson = rows["G1"]["evidence"][
        "pdelta_first_failed_coefficient_bounded_anderson_probe"
    ]
    assert g1_bounded_anderson["ready"] is False
    assert g1_bounded_anderson["coefficient_l1_limit"] == 8.0
    assert g1_bounded_anderson["coefficient_bounded_count"] > 0
    assert g1_bounded_anderson["max_coefficient_l1"] <= 8.0 + 1.0e-12
    assert (
        g1_bounded_anderson["best_relative_increment"]
        > g1_bounded_anderson["relative_increment_tolerance"]
    )
    assert g1_bounded_anderson["best_relative_increment"] < 3.0e-3
    g1_trust_region_anderson = rows["G1"]["evidence"][
        "pdelta_first_failed_residual_trust_region_anderson_probe"
    ]
    assert g1_trust_region_anderson["ready"] is False
    assert g1_trust_region_anderson["best_residual_inf_n"] <= g1_trust_region_anderson[
        "residual_tolerance_n"
    ]
    assert (
        g1_trust_region_anderson["best_fixed_point_relative_increment"]
        > g1_trust_region_anderson["relative_increment_tolerance"]
    )
    assert (
        "residual_trust_region_anderson_not_closed"
        in g1_trust_region_anderson["blockers"]
    )
    assert rows["G1"]["evidence"]["frame_material_nonlinear_tangent_status"] == "ready"
    assert rows["G1"]["evidence"]["frame_material_nonlinear_tangent_ready"] is True
    assert rows["G1"]["evidence"]["service_load_material_state_ready"] is True
    assert rows["G1"]["evidence"]["controlled_probe_material_state_ready"] is True
    assert rows["G1"]["evidence"]["bounded_material_tangent_global_smoke_ready"] is True
    assert rows["G1"]["evidence"]["global_smoke_solver_uses_per_element_material_tangent"] is True
    assert rows["G1"]["evidence"]["full_material_nonlinear_newton_equilibrium"] is False
    assert rows["G1"]["evidence"]["frame_material_probe_summary"]["nonlinear_tangent_element_count"] > 0
    assert rows["G1"]["evidence"]["frame_material_tangent_smoke_equilibrium"]["residual_inf_n"] <= 1.0e-3
    assert rows["G1"]["evidence"]["typed_mgt_offset_parser_ready"] is True
    assert rows["G1"]["evidence"]["offset_element_refs_match_mgt_elements"] is True
    assert rows["G1"]["evidence"]["beam_offset_row_count"] >= 700
    assert rows["G1"]["evidence"]["solver_rigid_end_offset_tangent_ready"] is True
    assert rows["G1"]["evidence"]["frame_rigid_end_offset_transform_applied"] is True
    assert rows["G1"]["evidence"]["frame_offset_applied_element_count"] >= 700
    assert rows["G1"]["evidence"]["coupled_frame_surface_offset_transform_applied"] is True
    assert rows["G1"]["evidence"]["coupled_frame_shell_offset_transform_applied"] is True
    assert rows["G1"]["evidence"]["local_axis_opening_status"] == "ready"
    assert rows["G1"]["evidence"]["frame_angle_parser_ready"] is True
    assert rows["G1"]["evidence"]["frame_angle_source_has_nonzero_rows"] is True
    assert rows["G1"]["evidence"]["frame_angle_solver_consumption_ready"] is True
    assert rows["G1"]["evidence"]["frame_angle_nonzero_row_count"] == 150
    assert rows["G1"]["evidence"]["surface_lcaxis_parser_ready"] is True
    assert rows["G1"]["evidence"]["surface_lcaxis_source_all_default"] is True
    assert rows["G1"]["evidence"]["opening_source_inventory_ready"] is True
    assert rows["G1"]["evidence"]["opening_source_rows_present"] is False
    assert rows["G1"]["evidence"]["current_source_opening_absence_policy_ready"] is True
    assert rows["G1"]["evidence"]["current_source_opening_noop_runtime_ready"] is True
    assert rows["G1"]["evidence"]["opening_runtime_semantics_ready"] is True
    assert rows["G1"]["evidence"]["generic_opening_cutout_runtime_semantics_ready"] is False
    assert rows["G1"]["evidence"]["boundary_entity_support_status"] == "partial"
    assert rows["G1"]["evidence"]["support_constraint_row_count"] == 8
    assert rows["G1"]["evidence"]["distinct_support_constraint_node_count"] == 2133
    assert rows["G1"]["evidence"]["elastic_link_row_count"] == 1692
    assert rows["G1"]["evidence"]["typed_mgt_support_constraint_parser_ready"] is True
    assert rows["G1"]["evidence"]["typed_mgt_elastic_link_parser_ready"] is True
    assert rows["G1"]["evidence"]["typed_mgt_story_eccentricity_parser_ready"] is True
    assert rows["G1"]["evidence"]["roundtrip_rigid_like_elastic_link_coarsening_ready"] is True
    assert rows["G1"]["evidence"]["solver_uses_authored_support_restraint_masks"] is False
    assert rows["G1"]["evidence"]["solver_assembles_finite_elastic_link_springs"] is False
    assert rows["G1"]["evidence"]["boundary_spring_tangent_status"] == "ready"
    assert rows["G1"]["evidence"]["boundary_finite_spring_component_count"] == 1692 * 6
    assert rows["G1"]["evidence"]["boundary_authored_support_restrained_dof_count"] == 7707
    assert rows["G1"]["evidence"]["boundary_tangent_nnz"] == 1692 * 6 * 4
    assert rows["G1"]["evidence"]["boundary_subsystem_authored_support_mask_application_ready"] is True
    assert rows["G1"]["evidence"]["boundary_subsystem_finite_elastic_link_spring_tangent_ready"] is True
    assert rows["G1"]["evidence"]["boundary_subsystem_probe_solve_ready"] is True
    assert rows["G1"]["evidence"]["boundary_subsystem_relative_residual_inf"] <= 1.0e-8
    assert rows["G1"]["evidence"]["boundary_subsystem_global_frame_shell_tangent_integration_ready"] is False
    assert rows["G1"]["evidence"]["uncoarsened_boundary_global_status"] == "ready"
    assert rows["G1"]["evidence"]["uncoarsened_boundary_global_equilibrium_ready"] is True
    assert rows["G1"]["evidence"]["global_frame_shell_boundary_tangent_integration_ready"] is True
    assert rows["G1"]["evidence"]["global_boundary_solver_uses_authored_support_restraint_masks"] is True
    assert rows["G1"]["evidence"]["global_boundary_solver_assembles_finite_elastic_link_springs"] is True
    assert rows["G1"]["evidence"]["global_boundary_uncoarsened_elastic_link_endpoints_preserved"] is True
    assert rows["G1"]["evidence"]["global_boundary_finite_spring_component_count"] == 1692 * 6
    assert rows["G1"]["evidence"]["global_boundary_authored_support_restrained_dof_count"] == 7707
    assert rows["G1"]["evidence"]["global_boundary_equilibrium_metrics"]["relative_residual_inf"] <= 2.0e-8
    assert rows["G1"]["evidence"]["story_eccentricity_load_status"] == "ready"
    assert rows["G1"]["evidence"]["story_eccentricity_story_count"] >= 20
    assert rows["G1"]["evidence"]["story_eccentricity_generated_case_count"] == 4
    assert rows["G1"]["evidence"]["story_eccentricity_generated_seismic_case_count"] == 4
    assert rows["G1"]["evidence"]["story_eccentricity_max_abs_torsional_moment_nm"] > 0.0
    assert rows["G1"]["evidence"]["story_eccentricity_load_generation_ready"] is True
    assert rows["G1"]["evidence"]["seismic_story_eccentricity_load_generation_ready"] is True
    assert rows["G1"]["evidence"]["global_solver_consumes_story_eccentricity_loads"] is False
    assert rows["G1"]["evidence"]["coupled_frame_shell_story_eccentricity_status"] == "ready"
    assert rows["G1"]["evidence"]["coupled_frame_shell_story_eccentricity_ready"] is True
    assert rows["G1"]["evidence"]["coupled_story_eccentricity_case_count"] == 4
    assert rows["G1"]["evidence"]["coupled_story_eccentricity_ready_case_count"] == 4
    assert rows["G1"]["evidence"]["coupled_story_eccentricity_max_relative_residual_inf"] <= 1.0e-6
    assert rows["G1"]["evidence"]["coupled_global_solver_consumes_story_eccentricity_loads"] is True
    assert rows["G2"]["status"] == "closed"
    assert rows["G2"]["evidence"]["native_solver_ready"] is True
    assert rows["G2"]["evidence"]["benchmark_contract_pass"] is True
    assert rows["G2"]["evidence"]["mode_count"] >= 3
    assert rows["G2"]["evidence"]["critical_load_factor"] > 1.0
    assert rows["G3"]["status"] == "closed"
    assert rows["G3"]["evidence"]["load_stage_runtime_flow_status"] == "ready"
    assert rows["G3"]["evidence"]["solve_flow_ready"] is True
    assert rows["G3"]["evidence"]["viewer_flow_ready"] is True
    assert rows["G3"]["evidence"]["export_flow_ready"] is True
    assert rows["G3"]["evidence"]["audit_flow_ready"] is True
    assert rows["G4"]["status"] == "closed"
    assert rows["G4"]["evidence"]["material_element_tangent_status"] == "ready"
    assert rows["G4"]["evidence"]["line_beam_tangent_ready"] is True
    assert rows["G4"]["evidence"]["unsupported_queue_ready"] is True
    assert rows["G4"]["evidence"]["surface_membrane_tangent_ready"] is True
    assert rows["G4"]["evidence"]["surface_shell_full_bending_tangent_ready"] is False
    assert rows["G4"]["evidence"]["surface_shell_bending_drilling_smoke_ready"] is True
    assert rows["G4"]["evidence"]["shell_calibration_benchmarks_ready"] is True
    assert rows["G4"]["evidence"]["shell_calibration_ready_case_count"] >= 5
    assert rows["G4"]["evidence"]["coupled_frame_surface_sparse_equilibrium_ready"] is True
    assert rows["G4"]["evidence"]["frame_material_nonlinear_tangent_ready"] is True
    assert rows["G4"]["evidence"]["frame_material_probe_state_summary"]["nonlinear_tangent_element_count"] > 0
    nonlinear_rows = {
        row["family"]: row for row in rows["G4"]["evidence"]["support_matrix"]
    }
    assert (
        nonlinear_rows["nonlinear_rc_steel_composite_material_laws"]["status"]
        == "bounded_frame_material_nonlinear_tangent_smoke_ready_full_newton_unsupported"
    )
    assert rows["G5"]["status"] == "closed"
    assert rows["G5"]["evidence"]["kds_detailing_support_status"] == "ready"
    assert rows["G5"]["evidence"]["clause_breadth_ready"] is True
    assert rows["G5"]["evidence"]["optimization_rows_guarded"] is True
    assert rows["G5"]["evidence"]["trace_ready"] is True
    assert rows["G6"]["status"] == "external_blocked"
    assert rows["G6"]["locally_closable"] is False
    assert rows["G7"]["status"] == "partial"
    assert rows["G7"]["evidence"]["operator_attached_ifc_count"] == 5
    assert rows["G7"]["evidence"]["operator_attached_real_artifact_count"] == 5
    assert rows["G7"]["evidence"]["operator_attached_real_mgt_header_ok_count"] == 0
    assert len(rows["G7"]["evidence"]["metadata_only_source_ids"]) == 9
    assert len(rows["G7"]["evidence"]["repo_benchmark_bridge_source_ids"]) == 4
    assert len(rows["G7"]["evidence"]["operator_attach_required_source_ids"]) >= 9
    assert rows["G7"]["evidence"]["operator_action_queue_count"] >= 13
    operator_action_queue = rows["G7"]["evidence"]["operator_action_queue"]
    assert len(operator_action_queue) == rows["G7"]["evidence"][
        "operator_action_queue_count"
    ]
    operator_action_by_source = {
        row["source_id"]: row for row in operator_action_queue
    }
    assert (
        operator_action_by_source[
            "koneps_goyang_changneung_powerplant_design_service"
        ]["action_type"]
        == "replace_repo_benchmark_bridge_mgt_with_operator_real_mgt"
    )
    assert (
        "sha256_differs_from_repo_benchmark_bridge"
        in operator_action_by_source[
            "koneps_goyang_changneung_powerplant_design_service"
        ]["acceptance_checks"]
    )
    assert operator_action_by_source[
        "koneps_goyang_changneung_powerplant_design_service"
    ]["specific_remote_download"] is True
    assert operator_action_by_source[
        "koneps_goyang_changneung_powerplant_design_service"
    ]["download_url"].startswith("https://www.g2b.go.kr/")
    assert operator_action_by_source[
        "koneps_goyang_changneung_powerplant_design_service"
    ]["license_hint"] == "public_attachment_check_terms"
    assert (
        operator_action_by_source[
            "lh_bucheon_yeokgok_a1_housing_competition"
        ]["action_type"]
        == "attach_operator_real_pdf_or_pdf_derived_mgt"
    )
    operator_action_packet = rows["G7"]["evidence"]["operator_action_packet"]
    assert operator_action_packet["schema_version"] == (
        "korean-medium-large-operator-action-packet.v1"
    )
    assert operator_action_packet["status"] == "pending"
    assert operator_action_packet["action_count"] == rows["G7"]["evidence"][
        "operator_action_queue_count"
    ]
    assert operator_action_packet[
        "operator_attached_real_mgt_header_ok_remaining"
    ] == 4
    assert (
        "sha256_differs_from_repo_benchmark_bridge"
        in operator_action_packet["acceptance_check_inventory"]
    )
    assert operator_action_packet["specific_remote_download_action_count"] == 5
    assert operator_action_packet["portal_landing_action_count"] == 9
    assert len(operator_action_packet["source_url_matrix"]) == operator_action_packet[
        "action_count"
    ]
    assert len(operator_action_packet["direct_download_actions"]) == 5
    assert len(operator_action_packet["portal_landing_actions"]) == 9
    assert {
        row["url_kind"] for row in operator_action_packet["source_url_matrix"]
    } == {"specific_remote_download", "portal_or_landing_page"}
    assert {
        row["source_id"] for row in operator_action_packet["direct_download_actions"]
    } == {
        "koneps_goyang_changneung_powerplant_design_service",
        "lh_bucheon_yeokgok_a1_housing_competition",
        "lh_happy_city_5_1_design_competition",
        "lh_bucheon_yeokgok_a1_housing_native_baseline",
        "lh_happy_city_5_1_native_baseline",
    }
    assert operator_action_packet["next_actions"][0]["specific_remote_download"] is True
    assert operator_action_packet["next_actions"][0]["download_url"].startswith(
        "https://www.g2b.go.kr/"
    )
    resolution_plan = operator_action_packet["operator_resolution_plan"]
    assert (
        resolution_plan["schema_version"]
        == "korean-medium-large-operator-resolution-plan.v1"
    )
    assert resolution_plan["minimum_operator_real_mgt_needed"] == 4
    assert resolution_plan["auto_promotable_repo_candidate_count"] == 0
    assert resolution_plan["priority_batches"][0]["batch_id"] == (
        "replace_benchmark_bridge_mgt"
    )
    assert resolution_plan["priority_batches"][0][
        "closes_operator_real_mgt_target"
    ] is True
    assert (
        rows["G7"]["evidence"]["operator_action_type_counts"][
            "replace_repo_benchmark_bridge_mgt_with_operator_real_mgt"
        ]
        == 4
    )
    assert rows["G7"]["evidence"]["operator_attached_real_mgt_header_ok_remaining"] == 4
    assert rows["G7"]["evidence"]["local_private_candidate_count"] >= 20
    assert rows["G7"]["evidence"]["existing_local_private_candidate_count"] >= 20
    assert rows["G7"]["evidence"]["kr_local_private_candidate_count"] >= 2
    assert rows["G7"]["evidence"]["mgt_local_private_candidate_count"] >= 4
    assert (
        rows["G7"]["evidence"]["mgt_header_ok_local_private_candidate_count"] >= 4
    )
    assert rows["G7"]["evidence"]["g7_counted_local_private_candidate_count"] == 0
    assert rows["G7"]["evidence"][
        "operator_action_private_candidate_match_count"
    ] == 10
    assert rows["G7"]["evidence"][
        "operator_action_private_candidate_source_count"
    ] == 5
    assert rows["G7"]["evidence"][
        "operator_action_private_candidate_file_count"
    ] == 2
    assert rows["G7"]["evidence"][
        "operator_action_private_candidate_requires_rights_count"
    ] == 10
    assert rows["G7"]["evidence"]["repo_public_candidate_count"] >= 22
    assert rows["G7"]["evidence"]["repo_public_candidate_mgt_count"] >= 12
    assert rows["G7"]["evidence"]["repo_public_candidate_ifc_count"] >= 10
    assert rows["G7"]["evidence"]["repo_public_candidate_benchmark_bridge_count"] >= 8
    assert rows["G7"]["evidence"]["g7_counted_repo_public_candidate_count"] == 0
    assert rows["G7"]["evidence"]["operator_action_repo_candidate_match_count"] >= 160
    assert rows["G7"]["evidence"]["operator_action_repo_candidate_source_count"] == 14
    assert rows["G7"]["evidence"]["operator_action_repo_candidate_file_count"] >= 22
    assert (
        rows["G7"]["evidence"][
            "operator_action_repo_candidate_exact_source_match_count"
        ]
        == 10
    )
    assert (
        rows["G7"]["evidence"]["operator_action_repo_candidate_exact_clean_count"]
        == 0
    )
    assert rows["G7"]["evidence"][
        "operator_action_repo_candidate_exact_blocker_counts"
    ] == {
        "repo_benchmark_bridge_mgt": 8,
        "mgt_file_too_small": 2,
    }
    assert (
        rows["G7"]["evidence"][
            "operator_action_repo_candidate_requires_source_mapping_count"
        ]
        >= 150
    )
    assert (
        rows["G7"]["evidence"][
            "operator_action_repo_candidate_ifc_source_mapping_candidate_count"
        ]
        >= 20
    )
    assert (
        rows["G7"]["evidence"][
            "operator_action_repo_candidate_ifc_source_mapping_candidate_source_count"
        ]
        == 2
    )
    assert (
        rows["G7"]["evidence"][
            "operator_action_repo_candidate_ifc_source_mapping_candidate_file_count"
        ]
        >= 10
    )
    ifc_mapping_candidates = rows["G7"]["evidence"][
        "operator_action_repo_candidate_ifc_source_mapping_candidates"
    ]
    assert len(ifc_mapping_candidates) == rows["G7"]["evidence"][
        "operator_action_repo_candidate_ifc_source_mapping_candidate_count"
    ]
    assert {
        row["source_id"] for row in ifc_mapping_candidates
    } == {
        "ifc_public_buildingsmart_korea_awards_hub",
        "ifc_public_buildingsmart_2025_megaproject_lane",
    }
    assert all(
        row["promotion_blockers"] == ["catalog_source_unmatched_candidate"]
        for row in ifc_mapping_candidates
    )
    assert (
        rows["G7"]["evidence"][
            "operator_action_repo_candidate_benchmark_bridge_count"
        ]
        >= 90
    )
    operator_candidate_matches = rows["G7"]["evidence"][
        "operator_action_private_candidate_matches"
    ]
    assert operator_candidate_matches
    assert all(row["counted_in_g7"] is False for row in operator_candidate_matches)
    assert all(
        row["requires_rights_confirmation"] is True
        for row in operator_candidate_matches
    )
    assert (
        rows["G7"]["evidence"]["catalog_source_unmatched_candidate_count"]
        == rows["G7"]["evidence"]["local_private_candidate_count"]
    )
    assert rows["G7"]["evidence"]["local_private_candidate_artifacts"]
    assert all(
        row["counted_in_g7"] is False
        for row in rows["G7"]["evidence"]["local_private_candidate_artifacts"]
    )
    operator_repo_candidate_matches = rows["G7"]["evidence"][
        "operator_action_repo_candidate_matches"
    ]
    assert operator_repo_candidate_matches
    assert all(row["counted_in_g7"] is False for row in operator_repo_candidate_matches)
    assert any(
        "repo_benchmark_bridge_mgt" in row["promotion_blockers"]
        for row in operator_repo_candidate_matches
    )
    assert any(
        "catalog_source_unmatched_candidate" in row["promotion_blockers"]
        for row in operator_repo_candidate_matches
    )
    assert "metadata_only_sources_present" in rows["G7"]["blockers"]
    assert "operator_attached_real_mgt_header_ok_below_target" in rows["G7"]["blockers"]
    assert rows["AI-G2"]["status"] == "closed"
    assert rows["AI-G2"]["evidence"]["production_ml_wired"] is True
    assert rows["AI-G2"]["evidence"]["checkpoint_validated"] is True
    assert rows["AI-G2"]["evidence"]["solver_fallback_ready"] is True
    assert (
        rows["AI-G2"]["evidence"]["pdelta_frontier_residual_jacobian_summary"]["diagnosis"]
        == "fixed_point_increment_small_but_direct_residual_gate_far_from_tolerance"
    )
    assert rows["AI-G3"]["status"] in {"closed", "partial"}
    assert rows["AI-G1"]["status"] in {"closed", "partial"}
    assert rows["AI-G5"]["status"] in {"closed", "partial"}
    assert rows["AI-G6"]["status"] in {"closed", "partial"}
    assert rows["AI-G7"]["status"] in {"closed", "partial"}
    assert rows["AI-G8"]["status"] in {"closed", "partial"}
    assert rows["AI-G9"]["status"] in {"closed", "partial"}
    assert rows["AI-G10"]["status"] in {"closed", "partial"}
    assert rows["G10"]["status"] in {"closed", "partial"}
    assert rows["AI-G4"]["status"] in {"closed", "partial"}
    assert rows["G8"]["status"] in {"closed", "partial"}
    assert rows["G9"]["evidence"]["full_line_sparse_elastic_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["nvidia_smi_not_required_for_amd_rocm"] is True
    assert rows["G9"]["evidence"]["rocm_tool_paths"]["rocm_smi"]
    assert rows["G9"]["evidence"]["rocm_tool_paths"]["rocminfo"]
    assert rows["G9"]["evidence"]["rocm_tool_paths"]["hipcc"]
    assert rows["G9"]["evidence"]["rocm_device_nodes"]["dev_kfd_present"] in {True, False}
    assert rows["G9"]["evidence"]["solver_runtime_backend_policy_status"] == "ready"
    assert rows["G9"]["evidence"]["official_solver_compute_backend"] == "amd_rocm_hip"
    assert rows["G9"]["evidence"]["official_solver_backend"] == "amd_rocm_hip"
    assert rows["G9"]["evidence"]["official_solver_backend_family"] == "rocm_hip"
    assert rows["G9"]["evidence"]["gpu_required_for_commercial_solver_closure"] is True
    assert rows["G9"]["evidence"]["torch_device_label_is_pytorch_rocm_compat_alias"] is True
    assert rows["G9"]["evidence"]["cpu_diagnostic_promotes_solver_closure"] is False
    assert rows["G9"]["evidence"]["cpu_solver_fallback_detected"] is False
    assert rows["G9"]["evidence"]["cpu_fallback_allowed_for_official_solver_closure"] is False
    assert rows["G9"]["evidence"]["cpu_reference_allowed_for_validation_replay"] is True
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_schur_interface_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_schur_interface_correction_equilibrium_ready"
        ]
        is False
    )
    assert rows["G9"]["evidence"]["full_line_sparse_geometric_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["full_line_sparse_geometric_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert rows["G9"]["evidence"]["full_frame_6dof_sparse_elastic_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["full_frame_6dof_linearized_geometric_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["full_frame_6dof_geometric_equilibrium_metrics"]["residual_inf_n"] <= 1.0e-3
    assert rows["G9"]["evidence"]["full_frame_6dof_deformed_state_pdelta_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["full_frame_6dof_linear_solver_refinement"]["enabled"] is True
    assert (
        rows["G9"]["evidence"]["full_frame_6dof_linear_solver_refinement"]["strategy"]
        == "best_residual_iterative_refinement"
    )
    assert rows["G9"]["evidence"]["pdelta_continuation_status"] == "partial"
    assert rows["G9"]["evidence"]["full_load_pdelta_continuation_ready"] is False
    assert rows["G9"]["evidence"]["pdelta_direct_load_step_max_converged_load_scale"] == 0.5
    assert (
        abs(rows["G9"]["evidence"]["pdelta_continuation_max_converged_load_scale"] - 0.50765625)
        <= 1.0e-12
    )
    assert rows["G9"]["evidence"]["pdelta_continuation_first_failed_load_scale"] == 0.55
    assert rows["G9"]["evidence"]["pdelta_post_converged_micro_step_probe"]["ready"] is True
    assert (
        rows["G9"]["evidence"]["pdelta_post_converged_micro_step_probe"][
            "convergence_increment_metric"
        ]
        == "unrelaxed_fixed_point_relative_increment"
    )
    assert (
        abs(
            rows["G9"]["evidence"]["pdelta_adaptive_micro_continuation_probe"][
                "first_failed_load_scale"
            ]
            - 0.51
        )
        <= 1.0e-12
    )
    assert (
        rows["G9"]["evidence"]["pdelta_post_failed_relaxation_sensitivity_probe"][
            "target_load_scale"
        ]
        == 0.5075
    )
    assert (
        rows["G9"]["evidence"]["pdelta_post_failed_relaxation_sensitivity_probe"][
            "best_relative_increment"
        ]
        < rows["G9"]["evidence"]["pdelta_adaptive_micro_continuation_probe"]["rows"][2][
            "relative_increment"
        ]
    )
    assert rows["G9"]["evidence"]["pdelta_secant_predictor_probe"]["target_load_scale"] == 0.5075
    assert rows["G9"]["evidence"]["pdelta_secant_predictor_probe"]["ready"] is True
    assert rows["G9"]["evidence"]["pdelta_secant_predictor_probe"]["residual_gate_passed_by_any"] is True
    assert (
        rows["G9"]["evidence"]["pdelta_secant_predictor_probe"][
            "relative_increment_gate_passed_by_any"
        ]
        is True
    )
    assert rows["G9"]["evidence"]["pdelta_secant_micro_continuation_probe"]["ready"] is False
    assert (
        rows["G9"]["evidence"]["pdelta_secant_micro_continuation_probe"][
            "max_converged_load_scale"
        ]
        == 0.5075
    )
    g9_fine_secant_micro = rows["G9"]["evidence"][
        "pdelta_fine_secant_micro_continuation_probe"
    ]
    assert g9_fine_secant_micro["ready"] is False
    assert abs(g9_fine_secant_micro["max_converged_load_scale"] - 0.50765625) <= 1.0e-12
    assert g9_fine_secant_micro["accepted_step_count"] == 1
    assert g9_fine_secant_micro["rows"][2]["ready"] is True
    g9_frontier = rows["G9"]["evidence"]["pdelta_frontier_diagnostic"]
    assert g9_frontier["ready"] is False
    assert abs(g9_frontier["frontier_load_scale"] - 0.50765625) <= 1.0e-12
    assert abs(g9_frontier["frontier_to_full_load_increment"] - 0.49234375) <= 1.0e-12
    assert g9_frontier["last_accepted_micro_row"]["source"] == "fine_secant_micro_continuation_probe"
    assert g9_frontier["next_failed_gate_mode"] == "residual_gate_failed"
    g9_frontier_jacobian = rows["G9"]["evidence"]["pdelta_frontier_residual_jacobian_probe"]
    assert g9_frontier_jacobian["ready"] is False
    assert g9_frontier_jacobian["target_load_scale"] == g9_frontier["next_failed_load_scale_after_frontier"]
    assert g9_frontier_jacobian["base_residual_inf_n"] > 1.0
    assert g9_frontier_jacobian["best_residual_inf_n"] > g9_frontier_jacobian["residual_tolerance_n"]
    assert g9_frontier_jacobian["correction_pass_count"] == 4
    assert g9_frontier_jacobian["accepted_correction_count"] == 4
    assert g9_frontier_jacobian["best_residual_reduction_factor"] < 0.21
    assert "previous_residual_jacobian_correction" in g9_frontier_jacobian["pass_rows"][1]["direction_labels"]
    assert rows["G9"]["evidence"]["pdelta_first_failed_one_step_line_search_probe"]["ready"] is False
    assert rows["G9"]["evidence"]["pdelta_first_failed_anderson_acceleration_probe"]["ready"] is False
    assert (
        rows["G9"]["evidence"]["pdelta_first_failed_anderson_acceleration_probe"][
            "best_relative_increment"
        ]
        > 1.0e-4
    )
    assert (
        rows["G9"]["evidence"]["pdelta_first_failed_anderson_acceleration_probe"][
            "best_relative_increment"
        ]
        < 3.0e-3
    )
    assert (
        rows["G9"]["evidence"][
            "pdelta_first_failed_coefficient_bounded_anderson_probe"
        ]["coefficient_l1_limit"]
        == 8.0
    )
    assert (
        rows["G9"]["evidence"][
            "pdelta_first_failed_coefficient_bounded_anderson_probe"
        ]["best_relative_increment"]
        > rows["G9"]["evidence"][
            "pdelta_first_failed_coefficient_bounded_anderson_probe"
        ]["relative_increment_tolerance"]
    )
    g9_trust_region_anderson = rows["G9"]["evidence"][
        "pdelta_first_failed_residual_trust_region_anderson_probe"
    ]
    assert g9_trust_region_anderson["ready"] is False
    assert g9_trust_region_anderson["best_residual_inf_n"] <= g9_trust_region_anderson[
        "residual_tolerance_n"
    ]
    assert (
        g9_trust_region_anderson["best_fixed_point_relative_increment"]
        > g9_trust_region_anderson["relative_increment_tolerance"]
    )
    assert rows["G9"]["evidence"]["surface_membrane_smoke_solve_ready"] is True
    assert rows["G9"]["evidence"]["surface_shell_bending_drilling_smoke_ready"] is True
    assert rows["G9"]["evidence"]["coupled_frame_surface_sparse_equilibrium_ready"] is True
    assert rows["G9"]["status"] == "closed"
    assert rows["G9"]["blockers"] == []
    assert rows["G9"]["evidence"]["mgt_rocm_sparse_probe_status"] == "ready"
    assert rows["G9"]["evidence"]["rocm_sparse_solver_probe_ready"] is True
    assert rows["G9"]["evidence"]["line_frame_rocm_sparse_solver_ready"] is True
    assert rows["G9"]["evidence"]["full_line_rocm_sparse_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["full_frame_6dof_rocm_sparse_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["full_frame_6dof_rocm_component_direct_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_cg_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_bicgstab_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_block_bicgstab_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_block_gmres_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_node_block_gmres_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_solution_fusion_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_hotspot_correction_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready"] is False
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready"] is False
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"]["surface_shell_rocm_sparse_residual_polishing_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "surface_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_spsolve_supported"] is False
    assert rows["G9"]["evidence"]["surface_shell_rocm_sparse_residual_replay_ready"] is True
    assert rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_equilibrium_ready"] is True
    assert rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_cg_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_bicgstab_equilibrium_ready"] is False
    assert rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_block_bicgstab_equilibrium_ready"] is False
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_restarted_block_bicgstab_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_restarted_defect_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_block_gmres_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_node_block_gmres_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_solution_fusion_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_hotspot_correction_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_residual_polishing_equilibrium_ready"]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        rows["G9"]["evidence"][
            "coupled_frame_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_spsolve_supported"] is False
    assert rows["G9"]["evidence"]["coupled_frame_shell_rocm_sparse_residual_replay_ready"] is True
    rocm_rows = {
        row["label"]: row for row in rows["G9"]["evidence"]["mgt_rocm_sparse_probe_rows"]
    }
    shell_rocm = rocm_rows["surface_shell_bending_rocm_sparse_solve_attempt"]
    coupled_rocm = rocm_rows["coupled_frame_shell_rocm_sparse_solve_attempt"]
    shell_host_ilu = shell_rocm["rocm_sparse_host_ilu_device_gmres"]
    coupled_host_ilu = coupled_rocm["rocm_sparse_host_ilu_device_gmres"]
    assert shell_rocm["rocm_sparse_host_ilu_device_gmres_ready"] is True
    assert coupled_rocm["rocm_sparse_host_ilu_device_gmres_ready"] is True
    assert shell_host_ilu["backend"] == "rocm_torch_sparse_host_ilu_device_gmres"
    assert shell_host_ilu["converged"] is True
    assert shell_host_ilu["residual_inf_n"] <= 1.0e-3
    assert shell_host_ilu["cpu_solver_fallback_detected"] is False
    assert shell_host_ilu["matvec_backend"] == "rocm_torch_sparse_csr"
    assert coupled_host_ilu["converged"] is True
    assert coupled_host_ilu["residual_inf_n"] <= 5.0e-2
    assert coupled_host_ilu["cpu_solver_fallback_detected"] is False
    assert shell_rocm["rocm_sparse_block_bicgstab"]["skipped"] is True
    assert (
        shell_rocm["rocm_sparse_block_bicgstab"]["skip_reason"]
        == "host_ilu_device_gmres_closed_residual_gate"
    )
    rocalution_sweep = rows["G9"]["evidence"]["rocalution_shell_preconditioner_sweep"]
    assert rocalution_sweep["status"] == "partial"
    assert rocalution_sweep["selected_residual_inf_n"] > rocalution_sweep["selected_threshold_n"]
    assert any(
        row["preconditioner"] == "ilut" and row["ilu_q"] == 15
        for row in rocalution_sweep["candidate_rows"]
    )
    streamed_large_ras = rows["G9"]["evidence"][
        "dof_block_schur_streamed_large_ras_shell_probe"
    ]
    assert streamed_large_ras["status"] == "partial"
    assert streamed_large_ras["best_node_block_subdomain_smoother_storage_mode"] == (
        "streamed_dense_inverse"
    )
    assert streamed_large_ras["best_node_block_subdomain_smoother_max_width"] >= 4096
    assert streamed_large_ras["best_residual_inf_n"] > streamed_large_ras["best_threshold_n"]
    assert streamed_large_ras["nonzero_subdomain_smoother_worsened_zero_weight"] is True
    assert streamed_large_ras["nonzero_weight_best_residual_inf_n"] > streamed_large_ras[
        "zero_weight_best_residual_inf_n"
    ]
    multiplicative_ras = rows["G9"]["evidence"][
        "dof_block_schur_multiplicative_ras_shell_smoke"
    ]
    assert multiplicative_ras["status"] == "partial"
    assert multiplicative_ras["best_residual_inf_n"] > multiplicative_ras["best_threshold_n"]
    assert {
        row["node_block_subdomain_smoother_update_mode"]
        for row in multiplicative_ras["candidate_rows"]
    } == {"additive", "multiplicative"}
    additive_nonzero = min(
        row["residual_inf_n"]
        for row in multiplicative_ras["candidate_rows"]
        if row["node_block_subdomain_smoother_weight"] > 0.0
        and row["node_block_subdomain_smoother_update_mode"] == "additive"
    )
    multiplicative_nonzero = min(
        row["residual_inf_n"]
        for row in multiplicative_ras["candidate_rows"]
        if row["node_block_subdomain_smoother_weight"] > 0.0
        and row["node_block_subdomain_smoother_update_mode"] == "multiplicative"
    )
    assert multiplicative_nonzero >= additive_nonzero
    interface_edge_probe = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_coarse_shell_probe"
    ]
    assert interface_edge_probe["status"] == "partial"
    assert interface_edge_probe["best_node_block_coarse_mode"] == "interface_edge"
    assert interface_edge_probe["best_node_block_coarse_interface_pair_count"] > 0
    assert interface_edge_probe["best_node_block_coarse_column_count"] > 0
    assert interface_edge_probe["best_residual_inf_n"] > interface_edge_probe["best_threshold_n"]
    assert interface_edge_probe["nonzero_coarse_worsened_zero_weight"] is True
    interface_edge_smoothed = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_smoothed_shell_probe"
    ]
    assert interface_edge_smoothed["status"] == "partial"
    assert interface_edge_smoothed["best_node_block_coarse_mode"] == "interface_edge"
    assert interface_edge_smoothed["best_node_block_coarse_interface_pair_count"] > 0
    assert interface_edge_smoothed["best_residual_inf_n"] > interface_edge_smoothed["best_threshold_n"]
    assert interface_edge_smoothed["nonzero_coarse_worsened_zero_weight"] is True
    assert any(
        row["node_block_coarse_smoothing_applied_steps"] == 1
        for row in interface_edge_smoothed["candidate_rows"]
    )
    interface_edge_repeated = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_repeated_coarse_shell_probe"
    ]
    assert interface_edge_repeated["status"] == "partial"
    assert interface_edge_repeated["best_node_block_coarse_mode"] == "interface_edge"
    assert interface_edge_repeated["best_node_block_coarse_interface_pair_count"] > 0
    assert interface_edge_repeated["best_residual_inf_n"] > interface_edge_repeated["best_threshold_n"]
    assert interface_edge_repeated["nonzero_coarse_worsened_zero_weight"] is True
    assert any(
        row["node_block_coarse_correction_passes"] > 1
        for row in interface_edge_repeated["candidate_rows"]
    )
    interface_edge_rhs_weighted = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_weighted_shell_weight_sweep_probe"
    ]
    assert interface_edge_rhs_weighted["status"] == "partial"
    assert interface_edge_rhs_weighted["best_node_block_coarse_mode"] == "interface_edge_rhs_weighted"
    assert interface_edge_rhs_weighted["best_residual_inf_n"] > interface_edge_rhs_weighted["best_threshold_n"]
    assert interface_edge_rhs_weighted["nonzero_coarse_worsened_zero_weight"] is False
    assert interface_edge_rhs_weighted["nonzero_coarse_weight_best_residual_inf_n"] < interface_edge_rhs_weighted[
        "zero_coarse_weight_best_residual_inf_n"
    ]
    interface_edge_rhs_signed = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_signed_shell_weight_sweep_probe"
    ]
    assert interface_edge_rhs_signed["status"] == "partial"
    assert interface_edge_rhs_signed["best_node_block_coarse_mode"] == "interface_edge_rhs_signed"
    assert interface_edge_rhs_signed["best_residual_inf_n"] > interface_edge_rhs_signed["best_threshold_n"]
    assert interface_edge_rhs_signed["nonzero_coarse_worsened_zero_weight"] is False
    assert interface_edge_rhs_signed["nonzero_coarse_weight_best_residual_inf_n"] < interface_edge_rhs_signed[
        "zero_coarse_weight_best_residual_inf_n"
    ]
    assert interface_edge_rhs_weighted["best_residual_inf_n"] < interface_edge_rhs_signed["best_residual_inf_n"]
    interface_edge_rhs_enriched = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_enriched_shell_weight_sweep_probe"
    ]
    assert interface_edge_rhs_enriched["status"] == "partial"
    assert interface_edge_rhs_enriched["best_node_block_coarse_mode"] == "interface_edge_rhs_enriched"
    assert interface_edge_rhs_enriched["best_residual_inf_n"] > interface_edge_rhs_enriched["best_threshold_n"]
    assert interface_edge_rhs_enriched["best_node_block_coarse_column_count"] > interface_edge_rhs_weighted[
        "best_node_block_coarse_column_count"
    ]
    assert interface_edge_rhs_enriched["nonzero_coarse_worsened_zero_weight"] is True
    interface_edge_rhs_enriched_restricted = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_enriched_restricted_shell_weight_sweep_probe"
    ]
    assert interface_edge_rhs_enriched_restricted["status"] == "partial"
    assert interface_edge_rhs_enriched_restricted["best_node_block_coarse_mode"] == (
        "interface_edge_rhs_enriched_restricted"
    )
    assert interface_edge_rhs_enriched_restricted["best_residual_inf_n"] > (
        interface_edge_rhs_enriched_restricted["best_threshold_n"]
    )
    assert interface_edge_rhs_enriched_restricted["best_node_block_coarse_load_restriction_applied"] is True
    assert interface_edge_rhs_enriched_restricted[
        "best_node_block_coarse_load_restriction_column_count"
    ] == interface_edge_rhs_weighted["best_node_block_coarse_column_count"]
    assert interface_edge_rhs_enriched_restricted["best_residual_inf_n"] < interface_edge_rhs_weighted[
        "best_residual_inf_n"
    ]
    interface_edge_rhs_enriched_restricted_fine = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_enriched_restricted_shell_fine_weight_probe"
    ]
    assert interface_edge_rhs_enriched_restricted_fine["status"] == "partial"
    assert interface_edge_rhs_enriched_restricted_fine["best_residual_inf_n"] == (
        interface_edge_rhs_enriched_restricted["best_residual_inf_n"]
    )
    interface_edge_rhs_enriched_restricted_coupled = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_smoke"
    ]
    assert interface_edge_rhs_enriched_restricted_coupled["status"] == "partial"
    assert interface_edge_rhs_enriched_restricted_coupled["best_node_block_coarse_mode"] == (
        "interface_edge_rhs_enriched_restricted"
    )
    assert interface_edge_rhs_enriched_restricted_coupled[
        "best_node_block_coarse_load_restriction_applied"
    ] is True
    assert interface_edge_rhs_enriched_restricted_coupled["best_residual_inf_n"] > (
        interface_edge_rhs_enriched_restricted_coupled["best_threshold_n"]
    )
    assert interface_edge_rhs_enriched_restricted_coupled[
        "nonzero_coarse_weight_best_residual_inf_n"
    ] < interface_edge_rhs_enriched_restricted_coupled[
        "zero_coarse_weight_best_residual_inf_n"
    ]
    interface_edge_rhs_enriched_restricted_coupled_current = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_current_single_probe"
    ]
    assert interface_edge_rhs_enriched_restricted_coupled_current["status"] == "partial"
    assert interface_edge_rhs_enriched_restricted_coupled_current["best_node_block_coarse_mode"] == (
        "interface_edge_rhs_enriched_restricted"
    )
    assert interface_edge_rhs_enriched_restricted_coupled_current[
        "best_node_block_coarse_load_restriction_applied"
    ] is True
    assert interface_edge_rhs_enriched_restricted_coupled_current["best_residual_inf_n"] > (
        interface_edge_rhs_enriched_restricted_coupled_current["best_threshold_n"]
    )
    assert interface_edge_rhs_enriched_restricted_coupled_current["best_residual_inf_n"] < (
        interface_edge_rhs_enriched_restricted_coupled["best_residual_inf_n"]
    )
    rigid_body_baseline = rows["G9"]["evidence"][
        "dof_block_schur_rigid_body_current_coupled_smoke_baseline"
    ]
    rigid_body_hybrid = rows["G9"]["evidence"][
        "dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_smoke"
    ]
    rigid_body_hybrid_tiny = rows["G9"]["evidence"][
        "dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_tiny_smoke"
    ]
    assert rigid_body_baseline["status"] == "partial"
    assert rigid_body_hybrid["status"] == "partial"
    assert rigid_body_hybrid_tiny["status"] == "partial"
    assert rigid_body_baseline["best_residual_inf_n"] == 719.4718284713658
    assert rigid_body_hybrid["best_node_block_coarse_mode"] == "rigid_body"
    assert rigid_body_hybrid["best_node_block_coarse_secondary_mode"] == (
        "interface_edge_rhs_enriched_restricted"
    )
    assert rigid_body_hybrid[
        "best_node_block_coarse_secondary_load_restriction_applied"
    ] is True
    assert rigid_body_hybrid[
        "best_node_block_coarse_secondary_load_restriction_column_count"
    ] == 1628
    assert rigid_body_hybrid["best_residual_inf_n"] > rigid_body_baseline[
        "best_residual_inf_n"
    ]
    assert rigid_body_hybrid_tiny["best_node_block_coarse_secondary_weight"] == 0.00025
    assert rigid_body_hybrid_tiny["best_residual_inf_n"] > rigid_body_baseline[
        "best_residual_inf_n"
    ]
    energy_restricted_shell = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_energy_restricted_shell_smoke"
    ]
    assert energy_restricted_shell["status"] == "partial"
    assert energy_restricted_shell["best_node_block_coarse_mode"] == (
        "interface_edge_energy_restricted"
    )
    assert energy_restricted_shell["best_node_block_coarse_operator"] == "galerkin_ptap"
    assert energy_restricted_shell["best_node_block_coarse_load_restriction_applied"] is True
    assert energy_restricted_shell["best_node_block_coarse_energy_mode_count"] > 0
    assert energy_restricted_shell["best_residual_inf_n"] < energy_restricted_shell[
        "zero_coarse_weight_best_residual_inf_n"
    ]
    assert energy_restricted_shell["best_residual_inf_n"] > energy_restricted_shell[
        "best_threshold_n"
    ]
    geneo_restricted_shell = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_restricted_shell_smoke"
    ]
    assert geneo_restricted_shell["status"] == "partial"
    assert geneo_restricted_shell["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_restricted"
    )
    assert geneo_restricted_shell["best_node_block_coarse_operator"] == "galerkin_ptap"
    assert geneo_restricted_shell["best_node_block_coarse_load_restriction_applied"] is True
    assert geneo_restricted_shell["best_node_block_coarse_interface_pair_count"] > 0
    assert geneo_restricted_shell["best_node_block_coarse_energy_mode_count"] > 0
    assert geneo_restricted_shell["best_residual_inf_n"] < geneo_restricted_shell[
        "zero_coarse_weight_best_residual_inf_n"
    ]
    assert geneo_restricted_shell["best_residual_inf_n"] < energy_restricted_shell[
        "best_residual_inf_n"
    ]
    assert geneo_restricted_shell["best_residual_inf_n"] > geneo_restricted_shell[
        "best_threshold_n"
    ]
    geneo_mode_count_sweep = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_mode_count_sweep_shell_smoke"
    ]
    assert geneo_mode_count_sweep["status"] == "partial"
    assert geneo_mode_count_sweep["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_restricted"
    )
    assert geneo_mode_count_sweep["best_node_block_coarse_energy_modes_per_dof"] == 3
    assert geneo_mode_count_sweep["best_node_block_coarse_interface_pair_count"] > 0
    assert geneo_mode_count_sweep["best_node_block_coarse_energy_mode_count"] > (
        geneo_restricted_shell["best_node_block_coarse_energy_mode_count"]
    )
    assert geneo_mode_count_sweep["best_residual_inf_n"] < geneo_restricted_shell[
        "best_residual_inf_n"
    ]
    assert geneo_mode_count_sweep["best_residual_inf_n"] > geneo_mode_count_sweep[
        "best_threshold_n"
    ]
    geneo_selection_sweep = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_selection_sweep_shell_smoke"
    ]
    assert geneo_selection_sweep["status"] == "partial"
    assert geneo_selection_sweep["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_restricted"
    )
    assert geneo_selection_sweep["best_node_block_coarse_energy_modes_per_dof"] == 3
    assert geneo_selection_sweep["best_node_block_coarse_energy_mode_selection"] == (
        "low_eigen"
    )
    assert geneo_selection_sweep["best_residual_inf_n"] == geneo_mode_count_sweep[
        "best_residual_inf_n"
    ]
    assert geneo_selection_sweep["best_residual_inf_n"] > geneo_selection_sweep[
        "best_threshold_n"
    ]
    geneo_weight_pass_sweep = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_weight_pass_sweep_shell_smoke"
    ]
    assert geneo_weight_pass_sweep["status"] == "partial"
    assert geneo_weight_pass_sweep["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_restricted"
    )
    assert geneo_weight_pass_sweep["best_node_block_coarse_energy_modes_per_dof"] == 3
    assert geneo_weight_pass_sweep["best_node_block_coarse_energy_mode_selection"] == (
        "low_eigen"
    )
    assert geneo_weight_pass_sweep["best_node_block_coarse_weight"] == 0.0015
    assert geneo_weight_pass_sweep["best_node_block_coarse_correction_passes"] == 5
    assert geneo_weight_pass_sweep["best_residual_inf_n"] < geneo_mode_count_sweep[
        "best_residual_inf_n"
    ]
    assert (
        geneo_mode_count_sweep["best_residual_inf_n"]
        - geneo_weight_pass_sweep["best_residual_inf_n"]
    ) < 1.0e-3
    assert geneo_weight_pass_sweep["best_residual_inf_n"] > geneo_weight_pass_sweep[
        "best_threshold_n"
    ]
    geneo_schur_cycle = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_schur_cycle_shell_smoke"
    ]
    assert geneo_schur_cycle["status"] == "partial"
    assert geneo_schur_cycle["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_restricted"
    )
    assert geneo_schur_cycle["best_node_block_coarse_schur_cycle_passes"] == 0
    assert geneo_schur_cycle["best_residual_inf_n"] == geneo_weight_pass_sweep[
        "best_residual_inf_n"
    ]
    assert geneo_schur_cycle["best_residual_inf_n"] > geneo_schur_cycle[
        "best_threshold_n"
    ]
    geneo_harmonic = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_harmonic_shell_smoke"
    ]
    assert geneo_harmonic["status"] == "partial"
    assert geneo_harmonic["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_harmonic_restricted"
    )
    assert geneo_harmonic["best_node_block_coarse_operator"] == "galerkin_ptap"
    assert geneo_harmonic["best_node_block_coarse_harmonic_extension_weight"] == 0.5
    assert geneo_harmonic["best_node_block_coarse_harmonic_extension_dof_count"] > 0
    assert geneo_harmonic["best_residual_inf_n"] < geneo_weight_pass_sweep[
        "best_residual_inf_n"
    ]
    assert geneo_harmonic["best_residual_inf_n"] > geneo_harmonic["best_threshold_n"]
    geneo_harmonic_depth = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_harmonic_depth_shell_smoke"
    ]
    assert geneo_harmonic_depth["status"] == "partial"
    assert geneo_harmonic_depth["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_harmonic_restricted"
    )
    assert geneo_harmonic_depth["best_node_block_coarse_harmonic_extension_weight"] == 0.5
    assert geneo_harmonic_depth["best_node_block_coarse_harmonic_extension_steps"] == 1
    assert geneo_harmonic_depth["best_residual_inf_n"] == geneo_harmonic[
        "best_residual_inf_n"
    ]
    assert geneo_harmonic_depth["best_residual_inf_n"] > geneo_harmonic_depth[
        "best_threshold_n"
    ]
    geneo_harmonic_qr = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_harmonic_qr_shell_smoke"
    ]
    assert geneo_harmonic_qr["status"] == "partial"
    assert geneo_harmonic_qr["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_harmonic_restricted"
    )
    assert geneo_harmonic_qr["best_node_block_coarse_basis_orthogonalization"] == "qr"
    assert geneo_harmonic_qr["best_node_block_coarse_basis_orthogonalization_used"] == "qr"
    assert geneo_harmonic_qr["best_node_block_coarse_harmonic_extension_steps"] == 1
    assert geneo_harmonic_qr["best_residual_inf_n"] < geneo_harmonic_depth[
        "best_residual_inf_n"
    ]
    assert geneo_harmonic_qr["best_residual_inf_n"] > geneo_harmonic_qr[
        "best_threshold_n"
    ]
    geneo_harmonic_residual_restriction = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_harmonic_residual_restriction_shell_smoke"
    ]
    assert geneo_harmonic_residual_restriction["status"] == "partial"
    assert geneo_harmonic_residual_restriction["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_harmonic_restricted"
    )
    assert geneo_harmonic_residual_restriction[
        "best_node_block_coarse_load_restriction_target"
    ] == "load"
    assert geneo_harmonic_residual_restriction[
        "best_node_block_coarse_basis_orthogonalization"
    ] == "qr"
    assert geneo_harmonic_residual_restriction["best_residual_inf_n"] == geneo_harmonic_qr[
        "best_residual_inf_n"
    ]
    assert geneo_harmonic_residual_restriction["best_residual_inf_n"] > (
        geneo_harmonic_residual_restriction["best_threshold_n"]
    )
    geneo_harmonic_dof_filter = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_harmonic_dof_filter_shell_smoke"
    ]
    assert geneo_harmonic_dof_filter["status"] == "partial"
    assert geneo_harmonic_dof_filter["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_harmonic_restricted"
    )
    assert geneo_harmonic_dof_filter[
        "best_node_block_coarse_local_dof_filter_used"
    ] == "all"
    dof_filter_candidates = geneo_harmonic_dof_filter["candidate_rows"]
    assert {
        row["node_block_coarse_local_dof_filter_used"]
        for row in dof_filter_candidates
    } == {"all", "translations", "rotations"}
    all_dof_row = next(
        row
        for row in dof_filter_candidates
        if row["node_block_coarse_local_dof_filter_used"] == "all"
    )
    translation_row = next(
        row
        for row in dof_filter_candidates
        if row["node_block_coarse_local_dof_filter_used"] == "translations"
    )
    rotation_row = next(
        row
        for row in dof_filter_candidates
        if row["node_block_coarse_local_dof_filter_used"] == "rotations"
    )
    assert translation_row["node_block_coarse_column_count"] < all_dof_row[
        "node_block_coarse_column_count"
    ]
    assert rotation_row["node_block_coarse_column_count"] < all_dof_row[
        "node_block_coarse_column_count"
    ]
    assert translation_row["residual_inf_n"] > all_dof_row["residual_inf_n"]
    assert rotation_row["residual_inf_n"] > all_dof_row["residual_inf_n"]
    assert geneo_harmonic_dof_filter["best_residual_inf_n"] == (
        geneo_harmonic_residual_restriction["best_residual_inf_n"]
    )
    assert geneo_harmonic_dof_filter["best_residual_inf_n"] > (
        geneo_harmonic_dof_filter["best_threshold_n"]
    )
    geneo_harmonic_energy_orthogonalization = rows["G9"]["evidence"][
        "dof_block_schur_interface_edge_geneo_harmonic_energy_orthogonalization_shell_smoke"
    ]
    assert geneo_harmonic_energy_orthogonalization["status"] == "partial"
    assert geneo_harmonic_energy_orthogonalization[
        "best_node_block_coarse_mode"
    ] == "interface_edge_geneo_harmonic_restricted"
    assert geneo_harmonic_energy_orthogonalization[
        "best_node_block_coarse_basis_orthogonalization"
    ] == "qr"
    energy_orthogonalization_candidates = geneo_harmonic_energy_orthogonalization[
        "candidate_rows"
    ]
    assert {
        row["node_block_coarse_basis_orthogonalization"]
        for row in energy_orthogonalization_candidates
    } == {"qr", "energy"}
    qr_orthogonalization_row = next(
        row
        for row in energy_orthogonalization_candidates
        if row["node_block_coarse_basis_orthogonalization"] == "qr"
    )
    energy_orthogonalization_row = next(
        row
        for row in energy_orthogonalization_candidates
        if row["node_block_coarse_basis_orthogonalization"] == "energy"
    )
    assert energy_orthogonalization_row[
        "node_block_coarse_basis_orthogonalization_used"
    ] == "energy"
    assert energy_orthogonalization_row[
        "node_block_coarse_basis_orthogonalization_dropped_column_count"
    ] == 0
    assert energy_orthogonalization_row["residual_inf_n"] > (
        qr_orthogonalization_row["residual_inf_n"]
    )
    assert geneo_harmonic_energy_orthogonalization["best_residual_inf_n"] == (
        geneo_harmonic_dof_filter["best_residual_inf_n"]
    )
    assert geneo_harmonic_energy_orthogonalization["best_residual_inf_n"] > (
        geneo_harmonic_energy_orthogonalization["best_threshold_n"]
    )
    interface_pair_dd = rows["G9"]["evidence"][
        "dof_block_schur_interface_pair_dd_smoother_shell_smoke"
    ]
    assert interface_pair_dd["status"] == "partial"
    assert interface_pair_dd["best_node_block_coarse_mode"] == (
        "interface_edge_geneo_harmonic_restricted"
    )
    assert interface_pair_dd["best_node_block_interface_pair_smoother_weight"] == 0.0
    assert interface_pair_dd[
        "best_node_block_interface_pair_smoother_block_count"
    ] == 22
    assert interface_pair_dd["best_node_block_interface_pair_smoother_max_width"] == 128
    assert (
        interface_pair_dd["best_node_block_interface_pair_smoother_storage_mode"]
        == "padded_batched_dense_inverse"
    )
    assert interface_pair_dd["best_residual_inf_n"] == (
        geneo_harmonic_residual_restriction["best_residual_inf_n"]
    )
    assert interface_pair_dd["best_residual_inf_n"] > (
        interface_pair_dd["best_threshold_n"]
    )
    interface_pair_swept = rows["G9"]["evidence"][
        "dof_block_schur_interface_pair_dd_swept_shell_smoke"
    ]
    assert interface_pair_swept["status"] == "partial"
    assert interface_pair_swept[
        "best_node_block_interface_pair_smoother_update_mode"
    ] == "additive"
    assert interface_pair_swept["best_node_block_interface_pair_smoother_weight"] == 0.0
    swept_candidates = interface_pair_swept["candidate_rows"]
    swept_nonzero = [
        row
        for row in swept_candidates
        if row["node_block_interface_pair_smoother_weight"] > 0.0
    ]
    swept_additive = min(
        row["residual_inf_n"]
        for row in swept_nonzero
        if row["node_block_interface_pair_smoother_update_mode"] == "additive"
    )
    swept_multiplicative = min(
        row["residual_inf_n"]
        for row in swept_nonzero
        if row["node_block_interface_pair_smoother_update_mode"] == "multiplicative"
    )
    assert swept_multiplicative < swept_additive
    assert swept_multiplicative > interface_pair_swept["best_residual_inf_n"]
    assert interface_pair_swept["best_residual_inf_n"] == (
        interface_pair_dd["best_residual_inf_n"]
    )
    interface_pair_rebalance = rows["G9"]["evidence"][
        "dof_block_schur_interface_pair_dd_coarse_rebalance_shell_smoke"
    ]
    assert interface_pair_rebalance["status"] == "partial"
    assert interface_pair_rebalance[
        "best_node_block_interface_pair_smoother_update_mode"
    ] == "multiplicative"
    assert interface_pair_rebalance[
        "best_node_block_interface_pair_coarse_rebalance_passes"
    ] == 0
    assert interface_pair_rebalance[
        "best_node_block_interface_pair_coarse_rebalance_weight"
    ] == 0.5
    rebalance_candidates = interface_pair_rebalance["candidate_rows"]
    no_rebalance = min(
        row["residual_inf_n"]
        for row in rebalance_candidates
        if row["node_block_interface_pair_coarse_rebalance_passes"] == 0
    )
    rebalance_nonzero = min(
        row["residual_inf_n"]
        for row in rebalance_candidates
        if row["node_block_interface_pair_coarse_rebalance_passes"] > 0
    )
    assert no_rebalance == interface_pair_rebalance["best_residual_inf_n"]
    assert rebalance_nonzero > interface_pair_rebalance["best_residual_inf_n"]
    assert interface_pair_rebalance["best_residual_inf_n"] == (
        interface_pair_dd["best_residual_inf_n"]
    )
    interface_pair_rebalance_sweep = rows["G9"]["evidence"][
        "dof_block_schur_interface_pair_dd_coarse_rebalance_weight_sweep_shell_smoke"
    ]
    assert interface_pair_rebalance_sweep["status"] == "partial"
    assert interface_pair_rebalance_sweep[
        "best_node_block_interface_pair_smoother_weight"
    ] == 0.001
    assert interface_pair_rebalance_sweep[
        "best_node_block_interface_pair_smoother_update_mode"
    ] == "multiplicative"
    assert interface_pair_rebalance_sweep[
        "best_node_block_interface_pair_coarse_rebalance_passes"
    ] == 0
    rebalance_sweep_candidates = interface_pair_rebalance_sweep["candidate_rows"]
    rebalance_sweep_without = min(
        row["residual_inf_n"]
        for row in rebalance_sweep_candidates
        if row["node_block_interface_pair_coarse_rebalance_passes"] == 0
    )
    rebalance_sweep_with = min(
        row["residual_inf_n"]
        for row in rebalance_sweep_candidates
        if row["node_block_interface_pair_coarse_rebalance_passes"] > 0
    )
    assert rebalance_sweep_without == interface_pair_rebalance_sweep["best_residual_inf_n"]
    assert rebalance_sweep_with > interface_pair_rebalance_sweep["best_residual_inf_n"]
    assert interface_pair_rebalance_sweep["best_residual_inf_n"] == swept_multiplicative
    residual_region = rows["G9"]["evidence"][
        "dof_block_schur_residual_region_diagnostic_shell_smoke"
    ]
    assert residual_region["status"] == "partial"
    assert residual_region["best_node_block_coarse_operator"] == "galerkin_ptap"
    region_summary = residual_region["best_residual_region_summary"]
    assert region_summary["operator"] == "galerkin_ptap"
    assert region_summary["primary_support"]["top64_abs_residual_share"] > 0.5
    assert region_summary["translation_dofs"]["top64_abs_residual_share"] == 1.0
    assert region_summary["rotation_dofs"]["residual_inf_fraction_of_global"] < 0.5
    assert rows["G9"]["evidence"]["full_3d_rocm_nonlinear_equilibrium_ready"] is False


def test_report_commercial_gap_ledger_status_cli(tmp_path: Path) -> None:
    out = tmp_path / "commercial_gap_ledger_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_commercial_gap_ledger_status.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "commercial-gap-ledger-status.v1"
    assert payload["summary"]["total_count"] == len(payload["rows"])
    assert payload["summary"]["total_count"] >= 20


def test_report_commercial_gap_ledger_status_fail_open(tmp_path: Path) -> None:
    out = tmp_path / "commercial_gap_ledger_status.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_commercial_gap_ledger_status.py"),
            "--output-json",
            str(out),
            "--fail-open",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
