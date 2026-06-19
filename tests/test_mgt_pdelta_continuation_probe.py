"""Tests for the full 6-DOF frame P-Delta continuation probe."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PDELTA_RECEIPT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_pdelta_continuation_probe.json"
)


def test_mgt_pdelta_continuation_receipt_records_first_failed_step() -> None:
    assert PDELTA_RECEIPT.is_file()
    payload = json.loads(PDELTA_RECEIPT.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "mgt-pdelta-continuation-probe.v1"
    assert payload["status"] == "partial"
    assert payload["full_load_pdelta_continuation_ready"] is False
    assert payload["direct_load_step_max_converged_load_scale"] == 0.5
    assert abs(payload["max_converged_load_scale"] - 0.50765625) <= 1.0e-12
    assert payload["first_failed_load_scale"] == 0.55
    assert payload["full_load_nonlinear_newton_ready"] is False
    assert payload["material_newton_ready"] is False
    assert payload["pdelta_fixed_point_linear_solver_refinement"]["enabled"] is True
    assert payload["line_search_linear_solver"]["uses_frame_solver_iterative_refinement"] is False
    assert "consistent_newton_jacobian_required" in payload["blockers"]
    first, second = payload["step_results"]
    assert first["load_step"] == 0.5
    assert first["ready"] is True
    assert first["initial_displacement_was_seeded"] is False
    assert first["linear_solver_refinement_enabled"] is True
    assert second["load_step"] == 0.55
    assert second["ready"] is False
    assert second["initial_displacement_was_seeded"] is True
    assert second["relaxation_factor"] == 0.7
    assert second["linear_solver_refinement_strategy"] == "best_residual_iterative_refinement"
    micro = payload["post_converged_micro_step_probe"]
    assert micro["seed_load_scale"] == 0.5
    assert micro["target_load_scale"] == 0.505
    assert micro["ready"] is True
    assert micro["near_displacement_fixed_point"] is True
    assert micro["residual_floor_above_tolerance"] is False
    assert micro["relative_increment"] <= micro["relative_increment_tolerance"]
    assert micro["residual_inf_n"] <= micro["residual_tolerance_n"]
    assert micro["linear_solver_refinement"]["enabled"] is True
    assert micro["linear_solver_refinement"]["max_iterations"] == 10
    assert micro["convergence_increment_metric"] == "unrelaxed_fixed_point_relative_increment"
    assert micro["fixed_point_increment_m"] > 0.0
    adaptive = payload["adaptive_micro_continuation_probe"]
    assert adaptive["ready"] is False
    assert adaptive["seed_load_scale"] == 0.5
    assert adaptive["target_load_scale"] == 0.55
    assert adaptive["max_converged_load_scale"] == 0.505
    assert abs(adaptive["first_failed_load_scale"] - 0.51) <= 1.0e-12
    assert adaptive["accepted_step_count"] == 1
    assert adaptive["attempt_count"] == 3
    assert adaptive["rows"][0]["target_load_scale"] == 0.505
    assert adaptive["rows"][0]["accepted_as_path_state"] is True
    assert (
        adaptive["rows"][0]["convergence_increment_metric"]
        == "unrelaxed_fixed_point_relative_increment"
    )
    assert abs(adaptive["rows"][1]["target_load_scale"] - 0.51) <= 1.0e-12
    assert adaptive["rows"][1]["ready"] is False
    assert adaptive["rows"][1]["relative_increment"] > 0.5
    assert adaptive["rows"][2]["target_load_scale"] == 0.5075
    assert adaptive["rows"][2]["ready"] is False
    assert adaptive["rows"][2]["relative_increment"] > 0.1
    assert "adaptive_micro_continuation_not_full_load_closed" in adaptive["blockers"]
    relaxation = payload["post_failed_relaxation_sensitivity_probe"]
    assert relaxation["ready"] is False
    assert relaxation["seed_load_scale"] == 0.505
    assert relaxation["target_load_scale"] == 0.5075
    assert relaxation["relaxation_factors"] == [0.25]
    assert relaxation["row_count"] == 1
    assert relaxation["rows"][0]["relaxation_factor"] == 0.25
    assert relaxation["rows"][0]["near_displacement_fixed_point"] is False
    assert relaxation["rows"][0]["residual_floor_above_tolerance"] is True
    assert relaxation["best_relative_increment"] < adaptive["rows"][2]["relative_increment"]
    assert "post_failed_relaxation_sensitivity_not_closed" in relaxation["blockers"]
    secant = payload["secant_predictor_probe"]
    assert secant["ready"] is True
    assert secant["previous_load_scale"] == 0.5
    assert secant["seed_load_scale"] == 0.505
    assert secant["target_load_scale"] == 0.5075
    assert abs(secant["extrapolation_factor"] - 0.5) <= 1.0e-12
    assert secant["relaxation_factors"] == [0.5, 0.25]
    assert secant["row_count"] == 2
    assert secant["residual_gate_passed_by_any"] is True
    assert secant["relative_increment_gate_passed_by_any"] is True
    assert secant["accepted_as_path_state"] is True
    assert secant["accepted_load_scale"] == 0.5075
    assert secant["accepted_relaxation_factor"] in {0.5, 0.25}
    assert any(row["accepted_as_path_state"] for row in secant["rows"])
    assert secant["best_residual_inf_n"] < relaxation["best_residual_inf_n"]
    assert secant["best_relative_increment"] < relaxation["best_relative_increment"]
    assert secant["blockers"] == []
    secant_micro = payload["secant_micro_continuation_probe"]
    assert secant_micro["ready"] is False
    assert secant_micro["initial_seed_load_scale"] == 0.5075
    assert secant_micro["target_load_scale"] == 0.55
    assert secant_micro["max_converged_load_scale"] == 0.5075
    assert abs(secant_micro["first_failed_load_scale"] - 0.51) <= 1.0e-12
    assert secant_micro["attempt_count"] == 2
    assert secant_micro["accepted_step_count"] == 0
    assert abs(secant_micro["rows"][0]["target_load_scale"] - 0.51) <= 1.0e-12
    assert secant_micro["rows"][0]["residual_gate_passed_by_any"] is True
    assert secant_micro["rows"][0]["relative_increment_gate_passed_by_any"] is False
    assert secant_micro["rows"][0]["best_relative_increment"] > 0.1
    assert abs(secant_micro["rows"][1]["target_load_scale"] - 0.50875) <= 1.0e-12
    assert "secant_micro_continuation_not_full_load_closed" in secant_micro["blockers"]
    fine_secant = payload["fine_secant_micro_continuation_probe"]
    assert fine_secant["ready"] is False
    assert fine_secant["initial_seed_load_scale"] == 0.5075
    assert fine_secant["target_load_scale"] == 0.55
    assert abs(fine_secant["max_converged_load_scale"] - 0.50765625) <= 1.0e-12
    assert abs(fine_secant["first_failed_load_scale"] - 0.508125) <= 1.0e-12
    assert fine_secant["initial_increment"] == 0.000625
    assert fine_secant["min_increment"] == 0.000078125
    assert fine_secant["max_attempts"] == 4
    assert fine_secant["attempt_count"] == 4
    assert fine_secant["accepted_step_count"] == 1
    assert abs(fine_secant["rows"][0]["target_load_scale"] - 0.508125) <= 1.0e-12
    assert fine_secant["rows"][0]["residual_gate_passed_by_any"] is False
    assert fine_secant["rows"][0]["relative_increment_gate_passed_by_any"] is True
    assert abs(fine_secant["rows"][1]["target_load_scale"] - 0.5078125) <= 1.0e-12
    assert fine_secant["rows"][1]["residual_gate_passed_by_any"] is False
    assert fine_secant["rows"][1]["relative_increment_gate_passed_by_any"] is True
    assert abs(fine_secant["rows"][2]["target_load_scale"] - 0.50765625) <= 1.0e-12
    assert fine_secant["rows"][2]["ready"] is True
    assert fine_secant["rows"][2]["residual_gate_passed_by_any"] is True
    assert fine_secant["rows"][2]["relative_increment_gate_passed_by_any"] is True
    assert fine_secant["rows"][2]["best_residual_inf_n"] <= 1.0e-3
    assert fine_secant["rows"][2]["best_relative_increment"] <= 1.0e-4
    assert abs(fine_secant["rows"][3]["target_load_scale"] - 0.50828125) <= 1.0e-12
    assert fine_secant["rows"][3]["ready"] is False
    assert "secant_micro_continuation_not_full_load_closed" in fine_secant["blockers"]
    frontier_jacobian = payload["frontier_residual_jacobian_probe"]
    assert frontier_jacobian["seed_load_scale"] == payload["max_converged_load_scale"]
    assert frontier_jacobian["target_load_scale"] == 0.5078125
    assert frontier_jacobian["ready"] is False
    assert frontier_jacobian["base_fixed_point_ready"] is False
    assert frontier_jacobian["direction_labels"] == [
        "regularized_tangent_newton",
        "fixed_point_delta",
        "load_path_secant_delta",
    ]
    assert frontier_jacobian["least_squares_backend"] == "numpy_lstsq_finite_difference_residual_jacobian"
    assert frontier_jacobian["base_fixed_point_map_residual_inf_n"] <= 1.0e-2
    assert frontier_jacobian["base_residual_inf_n"] > 1.0
    assert frontier_jacobian["best_residual_inf_n"] > frontier_jacobian["residual_tolerance_n"]
    assert payload["frontier_residual_jacobian_requested_correction_passes"] == 4
    assert frontier_jacobian["correction_pass_count"] == 4
    assert frontier_jacobian["requested_correction_passes"] == 4
    assert frontier_jacobian["accepted_correction_count"] == 4
    assert frontier_jacobian["best_residual_inf_n"] < frontier_jacobian["base_residual_inf_n"]
    assert frontier_jacobian["best_residual_inf_n"] < 2200.0
    assert frontier_jacobian["best_residual_reduction_factor"] < 0.21
    assert len(frontier_jacobian["pass_rows"]) == 4
    assert all(row["accepted"] is True for row in frontier_jacobian["pass_rows"])
    assert (
        frontier_jacobian["pass_rows"][1]["best_residual_inf_n"]
        < frontier_jacobian["pass_rows"][0]["best_residual_inf_n"]
    )
    assert (
        frontier_jacobian["pass_rows"][3]["best_residual_inf_n"]
        < frontier_jacobian["pass_rows"][2]["best_residual_inf_n"]
    )
    assert (
        "previous_residual_jacobian_correction"
        in frontier_jacobian["pass_rows"][1]["direction_labels"]
    )
    assert (
        frontier_jacobian["best_fixed_point_relative_increment"]
        <= frontier_jacobian["relative_increment_tolerance"]
    )
    assert any(row["relative_increment_gate_passed"] for row in frontier_jacobian["candidate_rows"])
    assert all(not row["residual_gate_passed"] for row in frontier_jacobian["candidate_rows"])
    assert "frontier_residual_jacobian_not_closed" in frontier_jacobian["blockers"]
    line_search = payload["first_failed_one_step_line_search_probe"]
    assert line_search["target_load_scale"] == 0.55
    assert line_search["ready"] is False
    assert line_search["candidate_count"] == 4
    assert line_search["seed_residual_inf_n"] > 0.0
    assert line_search["correction_norm_inf_m"] > 0.0
    assert line_search["best_alpha"] in {1.0, 0.5, 0.25, 0.125}
    assert line_search["best_residual_inf_n"] > line_search["seed_residual_inf_n"]
    assert line_search["best_residual_reduction_factor"] > 1.0
    assert line_search["linear_solver"]["uses_frame_solver_iterative_refinement"] is False
    assert "one_step_line_search_newton_not_closed" in line_search["blockers"]
    anderson = payload["first_failed_anderson_acceleration_probe"]
    assert anderson["target_load_scale"] == 0.55
    assert anderson["ready"] is False
    assert anderson["iteration_count"] == 48
    assert anderson["history_depth"] == 8
    assert anderson["best_map_residual_inf_n"] > 0.0
    assert anderson["best_relative_increment"] > anderson["relative_increment_tolerance"]
    assert anderson["best_relative_increment"] < 3.0e-3
    assert anderson["max_coefficient_l1"] >= 1.0
    assert "anderson_acceleration_pdelta_not_closed" in anderson["blockers"]
    bounded = payload["first_failed_coefficient_bounded_anderson_probe"]
    assert bounded["target_load_scale"] == 0.55
    assert bounded["ready"] is False
    assert bounded["coefficient_l1_limit"] == 8.0
    assert bounded["coefficient_bounded_count"] > 0
    assert bounded["max_coefficient_l1"] <= 8.0 + 1.0e-12
    assert bounded["max_unbounded_coefficient_l1"] > bounded["max_coefficient_l1"]
    assert bounded["best_relative_increment"] > bounded["relative_increment_tolerance"]
    assert bounded["best_relative_increment"] < 3.0e-3
    assert "anderson_acceleration_pdelta_not_closed" in bounded["blockers"]
    trust_region = payload["first_failed_residual_trust_region_anderson_probe"]
    assert trust_region["target_load_scale"] == 0.55
    assert trust_region["ready"] is False
    assert trust_region["iteration_count"] == 8
    assert trust_region["history_depth"] == 8
    assert trust_region["best_candidate_label"] in {
        "fixed_point_map",
        "anderson_blend_1",
        "anderson_blend_0.5",
        "anderson_blend_0.25",
    }
    assert trust_region["best_residual_inf_n"] <= trust_region["residual_tolerance_n"]
    assert (
        trust_region["best_fixed_point_relative_increment"]
        > trust_region["relative_increment_tolerance"]
    )
    assert trust_region["max_coefficient_l1"] <= bounded["coefficient_l1_limit"]
    assert "residual_trust_region_anderson_not_closed" in trust_region["blockers"]
