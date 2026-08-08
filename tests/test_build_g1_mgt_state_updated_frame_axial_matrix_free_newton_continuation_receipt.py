from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/"
    "build_g1_mgt_state_updated_frame_axial_matrix_free_newton_"
    "continuation_receipt.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_state_updated_frame_axial_matrix_free_newton_"
    "continuation_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_RECEIPT_OUT)


def test_committed_receipt_reaches_diagnostic_semantic_live_target() -> None:
    payload = _committed_receipt()

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["diagnostic_execution_ready"] is True
    assert payload["readiness_pass"] is False
    assert payload["engineer_review_required"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["source_commit_exact_replay_claim"] is True
    assert payload["source_tree_state"] == "commit_bound_inputs_exact"

    inputs = payload["inputs"]
    assert inputs["node_count"] == 13_047
    assert inputs["element_count"] == 12_728
    assert inputs["frame_element_count"] == 5_572
    assert inputs["global_dof_count"] == 78_282
    assert inputs["free_equation_count"] == 70_560
    assert inputs["semantic_load_case"] == "LIVE"
    assert inputs["initial_state_policy"] == "zero_state"
    assert inputs["target_load_factors"] == [0.25, 0.5, 0.75, 1.0]

    binding = payload["adapter_binding"]
    material = binding["material_analysis_property_binding"]
    assert material["dgn_alias_resolution_enabled"] is True
    assert material["dgn_alias_material_count_applied"] == 24
    assert material["resolved_material_count"] == 30
    assert material["engineer_review_required"] is True
    coverage = binding["frame_source_property_coverage_audit"]
    assert coverage["resolved_source_property_element_count"] == 5_572
    assert coverage["unresolved_source_property_element_count"] == 0
    assert coverage["exact_source_property_coverage"] is True
    geometry = binding["state_updated_frame_axial_geometry"]
    assert geometry["connected_to_physical_residual"] is True
    assert geometry["connected_to_consistent_state_tangent_action"] is True
    assert geometry["consistent_state_tangent_action_mode"] == (
        "analytic_reference_plus_exact_finite_chord_axial_correction"
    )
    assert geometry["finite_chord_extension_evaluation"] == (
        "difference_of_squares_cancellation_stable"
    )
    assert geometry["finite_chord_correction_evaluation"] == (
        "second_order_decomposition_cancellation_stable"
    )
    assert geometry["full_corotational_frame_claim"] is False
    residual_contract = binding["residual_evaluation_contract"]
    assert residual_contract["schema_version"] == (
        "mgt-residual-evaluation-contract.v1"
    )
    assert residual_contract["residual_formula_hash"] == (
        module.canonical_hash(residual_contract["residual_formula"])
    )
    assert residual_contract["mode"] == (
        "reference_csr_plus_load_frame_delta_plus_finite_chord_correction"
    )
    assert residual_contract[
        "reference_csr_parent_matches_analytic_tangent"
    ] is True
    assert residual_contract[
        "load_frame_delta_parent_matches_analytic_tangent"
    ] is True
    assert residual_contract[
        "finite_chord_correction_parent_matches_analytic_tangent"
    ] is True
    residual_audit = binding["residual_parent_equivalence_audit"]
    assert residual_audit["status"] == "ready"
    assert residual_audit["applicable"] is True
    assert residual_audit["parent_component_difference_inf_n"] <= (
        residual_audit["comparison_tolerance_n"]
    )
    assert residual_audit["parent_component_gate_passed"] is True
    assert residual_audit["parent_repeat_bytes_exact"] is True
    assert residual_audit["contract_pass"] is True
    preconditioner = binding["reference_preconditioner_contract"]
    assert preconditioner["available"] is True
    assert preconditioner["equation_count"] == 70_560
    assert preconditioner["intended_use"] == "fixed_right_preconditioner"
    assert preconditioner["exact_for_adapter_residual_model"] is False
    assert preconditioner["approximate_for_state_dependent_adapter"] is True
    assert preconditioner["production_preconditioner_claim"] is False

    recurrence_binding = payload[
        "matrix_free_operator_recurrence_binding_audit"
    ]
    assert recurrence_binding["status"] == "ready"
    assert recurrence_binding["solve_receipt_count"] == 21
    assert recurrence_binding["expected_solve_receipt_count"] == 21
    assert recurrence_binding["all_solve_receipts_operator_bound"] is True
    assert recurrence_binding["single_operator_binding_hash"] is True
    assert len(recurrence_binding["operator_binding_hashes"]) == 1
    assert recurrence_binding["free_equation_order_data_hash"] == (
        "sha256:21e0cef7915f3c68a772ca541123453a"
        "35535c3b172110ebd54f16695541c1b1"
    )
    assert recurrence_binding["residual_formula_hash"] == residual_contract[
        "residual_formula_hash"
    ]
    assert recurrence_binding["accumulation_profile"] == (
        "ascending_index_python_fsum_fp64.v1"
    )
    assert recurrence_binding[
        "all_solve_receipts_use_deterministic_host_arithmetic"
    ] is True
    assert len(
        recurrence_binding["reference_preconditioner_pattern_hashes"]
    ) == 1
    assert len(
        recurrence_binding["reference_preconditioner_values_hashes"]
    ) == 1
    assert recurrence_binding[
        "operator_callback_formula_parent_arrays_bound"
    ] is True
    assert recurrence_binding[
        "operator_callback_outputs_in_deterministic_contract"
    ] is False
    assert recurrence_binding[
        "preconditioner_callback_outputs_in_deterministic_contract"
    ] is False
    assert recurrence_binding[
        "cross_platform_end_to_end_deterministic_claim"
    ] is False
    assert recurrence_binding["production_solver_claim"] is False
    assert recurrence_binding["rocm_hip_parity_claim"] is False
    assert recurrence_binding["contract_pass"] is True

    continuation = payload["continuation"]
    assert continuation["status"] == "ready"
    assert continuation["terminal_reason"] == "target_load_factor_reached"
    assert continuation["config"]["residual_tolerance_inf_kn"] == 5.0e-7
    assert continuation["config"][
        "increment_absolute_tolerance_inf_m"
    ] == 1.0e-10
    assert continuation["config"]["increment_relative_tolerance"] == 1.0e-4
    assert continuation["config"]["step_acceptance"] == (
        "residual_and_absolute_or_relative_increment"
    )
    assert continuation["initial_checkpoint"]["load_factor"] == 0.0
    assert continuation["final_checkpoint"]["load_factor"] == 1.0
    assert [row["load_factor"] for row in continuation["checkpoints"]] == [
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    ]
    metrics = continuation["metrics"]
    assert metrics["contract_pass"] is True
    assert metrics["target_load_factor_reached"] is True
    assert metrics["accepted_step_count"] == 4
    assert metrics["failed_step_count"] == 0
    assert metrics["checkpoint_count"] == 5
    assert metrics["tangent_solve_count"] == 4
    assert metrics["maximum_tangent_solve_iterations"] <= 3
    assert metrics["maximum_independent_tangent_residual_inf_kn"] <= 1.0e-7
    assert metrics["maximum_checkpoint_residual_inf_kn"] <= 5.0e-7
    assert metrics["final_residual_inf_kn"] == pytest.approx(
        4.447424730642524e-7
    )
    assert metrics["maximum_accepted_increment_inf_m"] == pytest.approx(
        1.1873917886684743e-7
    )
    assert metrics["maximum_accepted_relative_increment"] == pytest.approx(
        4.5583426984171883e-5
    )
    assert metrics["residual_and_increment_acceptance_gate"] is True
    assert metrics["maximum_line_search_backtrack_count"] == 0
    assert metrics["minimum_accepted_line_search_alpha"] == 1.0
    assert metrics["fallback_count"] == 0
    assert metrics["regularization_count"] == 0
    assert metrics["restart_checkpoint_consumed"] is False

    reproduction = payload["load_scale_0p656_reproduction"]
    assert reproduction["target_load_factor"] == 0.656
    assert reproduction["result"]["final_checkpoint"]["load_factor"] == 0.656
    assert reproduction["final_residual_inf_n"] <= 0.0005
    assert reproduction["residual_gate_passed"] is True
    assert reproduction["increment_gate_passed"] is True
    assert reproduction["fallback_count"] == 0
    assert reproduction["regularization_count"] == 0
    assert reproduction["contract_pass"] is True
    assert payload["claims"]["actual_load_scale_0p656_reproduced"] is True

    assert [row["newton_solve_count"] for row in continuation["attempts"]] == [
        1,
        1,
        1,
        1,
    ]
    assert all(row["accepted"] for row in continuation["attempts"])
    assert all(
        row["rollback_performed"] is False
        for row in continuation["attempts"]
    )
    assert all(
        row["rollback_exact"] is True for row in continuation["attempts"]
    )
    assert all(
        row["history"][-1]["residual_gate_passed"] is True
        and row["history"][-1]["increment_gate_passed"] is True
        and row["history"][-1]["convergence_gate_passed"] is True
        for row in continuation["attempts"]
    )

    restart = payload["restart_replay"]
    assert restart["restart_load_factor"] == 0.5
    assert restart["restart_checkpoint_consumed"] is True
    assert restart["final_vector_bytes_exact"] is True
    assert restart["final_state_hash_exact"] is True
    assert restart["final_data_hash_exact"] is True
    assert restart["contract_pass"] is True
    assert restart["restart_result"]["metrics"][
        "restart_checkpoint_consumed"
    ] is True
    assert restart["restart_result"]["final_checkpoint"]["state_hash"] == (
        continuation["final_checkpoint"]["state_hash"]
    )

    strict = payload["strict_g1_gate_full_load_probe"]
    assert strict["configured_residual_tolerance_inf_n"] == 0.0005
    assert strict["final_residual_inf_n"] == pytest.approx(
        1.1767242540372536e-6
    )
    assert strict["full_load_target_reached"] is True
    assert strict["residual_gate_passed"] is True
    assert strict["rollback_performed"] is False
    assert strict["contract_pass"] is True
    strict_result = strict["result"]
    assert strict_result["status"] == "ready"
    assert strict_result["terminal_reason"] == "target_load_factor_reached"
    strict_metrics = strict_result["metrics"]
    assert strict_metrics["contract_pass"] is True
    assert strict_metrics["target_load_factor_reached"] is True
    assert strict_metrics["accepted_step_count"] == 1
    assert strict_metrics["failed_step_count"] == 0
    assert strict_metrics["checkpoint_count"] == 2
    assert strict_metrics["tangent_solve_count"] == 2
    assert strict_metrics["residual_and_increment_acceptance_gate"] is True
    assert strict_result["attempts"][0]["rollback_performed"] is False

    quadratic = payload["local_quadratic_convergence_audit"]
    assert quadratic["status"] == "ready"
    assert quadratic["reference_load_factor"] == 1.0
    assert quadratic["reference_residual_inf_n"] == pytest.approx(
        1.1767242540372536e-6
    )
    assert quadratic["perturbation_inf_m"] == [4.0e-6, 2.0e-6, 1.0e-6]
    assert quadratic["minimum_observed_order"] == pytest.approx(
        1.9999850689943242
    )
    assert quadratic["maximum_observed_order"] == pytest.approx(
        1.9999851530959427
    )
    assert quadratic["minimum_observed_order"] >= quadratic[
        "quadratic_order_lower_gate"
    ]
    assert quadratic["maximum_observed_order"] <= quadratic[
        "quadratic_order_upper_gate"
    ]
    assert quadratic["normalized_coefficient_relative_spread"] <= quadratic[
        "normalized_coefficient_relative_spread_gate"
    ]
    assert quadratic["fallback_count"] == 0
    assert quadratic["regularization_count"] == 0
    assert quadratic["contract_pass"] is True
    assert quadratic[
        "local_directional_quadratic_convergence_claim"
    ] is True
    assert quadratic["global_quadratic_convergence_claim"] is False
    assert quadratic["promotes_g1_closure"] is False
    quadratic_rows = quadratic["rows"]
    assert [row["residual_after_inf_n"] for row in quadratic_rows] == (
        pytest.approx(
            [
                0.009016784547384304,
                0.0022542193351000606,
                0.0005635606662508508,
            ]
        )
    )
    assert all(row["residual_descent"] for row in quadratic_rows)
    assert all(
        row["independent_linear_residual_inf_kn"] <= 1.0e-7
        and row["tangent_solve"]["contract_pass"]
        and row["tangent_solve"]["fallback_count"] == 0
        and row["tangent_solve"]["regularization_count"] == 0
        for row in quadratic_rows
    )

    failure = payload["iteration_limited_failure_rollback"]
    assert failure["configured_residual_tolerance_inf_n"] == 0.0005
    assert failure["configured_maximum_newton_iterations"] == 1
    assert failure["rejected_trial_residual_inf_n"] == pytest.approx(
        0.002323337105281098
    )
    assert failure["rollback_performed"] is True
    assert failure["rollback_exact"] is True
    assert failure["initial_final_checkpoint_state_hash_exact"] is True
    assert failure["accepted_state_hash_before"] == failure[
        "accepted_state_hash_after"
    ]
    assert failure["contract_pass"] is True
    failure_result = failure["failure_result"]
    assert failure_result["status"] == "blocked"
    assert failure_result["terminal_reason"] == (
        "maximum_newton_iterations_exhausted"
    )
    assert failure_result["initial_checkpoint"]["state_hash"] == (
        failure_result["final_checkpoint"]["state_hash"]
    )
    failure_metrics = failure_result["metrics"]
    assert failure_metrics["contract_pass"] is False
    assert failure_metrics["target_load_factor_reached"] is False
    assert failure_metrics["accepted_step_count"] == 0
    assert failure_metrics["failed_step_count"] == 1
    assert failure_metrics["checkpoint_count"] == 1
    assert failure_metrics["tangent_solve_count"] == 1
    assert failure_metrics["maximum_tangent_solve_iterations"] <= 3
    assert failure_metrics["maximum_line_search_backtrack_count"] == 0
    assert failure_metrics["minimum_accepted_line_search_alpha"] == 1.0
    assert failure_metrics["fallback_count"] == 0
    assert failure_metrics["regularization_count"] == 0
    assert failure_metrics["rollback_exact"] is True
    assert failure_metrics["residual_and_increment_acceptance_gate"] is False
    failure_attempt = failure_result["attempts"][0]
    assert failure_attempt["accepted"] is False
    assert failure_attempt["newton_solve_count"] == 1
    assert failure_attempt["rollback_performed"] is True
    assert failure_attempt["rollback_exact"] is True
    assert failure_attempt["accepted_state_hash_before"] == failure_attempt[
        "accepted_state_hash_after"
    ]

    adaptive = payload["adaptive_step_reduction_replay"]
    assert adaptive["restart_load_factor"] == 0.5
    assert adaptive["final_vector_bytes_exact"] is True
    assert adaptive["final_state_hash_exact"] is True
    assert adaptive["final_data_hash_exact"] is True
    assert adaptive["contract_pass"] is True
    adaptive_result = adaptive["result"]
    assert adaptive_result["status"] == "ready"
    assert adaptive_result["terminal_reason"] == (
        "target_load_factor_reached"
    )
    assert adaptive_result["config"]["initial_step_size"] == 1.0
    assert adaptive_result["config"]["minimum_step_size"] == 0.125
    assert adaptive_result["config"]["failed_step_reduction"] == 0.5
    assert adaptive_result["config"]["fast_step_growth"] == 2.0
    assert adaptive_result["config"]["step_config"][
        "maximum_newton_iterations"
    ] == 1
    assert [
        row["load_factor"] for row in adaptive_result["checkpoints"]
    ] == [0.0, 0.5, 0.75, 1.0]
    adaptive_metrics = adaptive_result["metrics"]
    assert adaptive_metrics["contract_pass"] is True
    assert adaptive_metrics["target_load_factor_reached"] is True
    assert adaptive_metrics["attempt_count"] == 5
    assert adaptive_metrics["accepted_step_count"] == 3
    assert adaptive_metrics["failed_step_count"] == 2
    assert adaptive_metrics["failed_step_reduction_count"] == 2
    assert adaptive_metrics["fast_step_growth_count"] == 2
    assert adaptive_metrics["checkpoint_count"] == 4
    assert adaptive_metrics["tangent_solve_count"] == 5
    assert adaptive_metrics["minimum_attempted_step_size"] == 0.25
    assert adaptive_metrics["maximum_attempted_step_size"] == 1.0
    assert adaptive_metrics["final_residual_inf_kn"] == pytest.approx(
        4.4469824842963137e-7
    )
    assert adaptive_metrics["rollback_exact"] is True
    assert adaptive_metrics[
        "residual_and_increment_acceptance_gate"
    ] is True
    assert adaptive_metrics["fallback_count"] == 0
    assert adaptive_metrics["regularization_count"] == 0
    adaptive_attempts = adaptive_result["attempts"]
    assert [row["target_load_factor"] for row in adaptive_attempts] == [
        1.0,
        0.5,
        1.0,
        0.75,
        1.0,
    ]
    assert [row["outcome"] for row in adaptive_attempts] == [
        "rolled_back",
        "committed",
        "rolled_back",
        "committed",
        "committed",
    ]
    assert [row["attempted_step_size"] for row in adaptive_attempts] == [
        1.0,
        0.5,
        0.5,
        0.25,
        0.25,
    ]
    assert all(
        row["rollback_performed"] and row["rollback_exact"]
        for row in adaptive_attempts
        if not row["accepted"]
    )
    assert adaptive_attempts[0]["history"][-1][
        "residual_inf_kn"
    ] * 1000.0 == pytest.approx(0.002323337105281098)
    assert adaptive_attempts[2]["history"][-1][
        "residual_inf_kn"
    ] * 1000.0 == pytest.approx(0.0013068756297798244)
    adaptive_restart = adaptive["restart_result"]
    assert adaptive_restart["status"] == "ready"
    assert adaptive_restart["metrics"]["restart_checkpoint_consumed"] is True
    assert adaptive_restart["metrics"]["attempt_count"] == 3
    assert adaptive_restart["metrics"]["accepted_step_count"] == 2
    assert adaptive_restart["metrics"]["failed_step_count"] == 1
    assert adaptive_restart["final_checkpoint"]["state_hash"] == (
        adaptive_result["final_checkpoint"]["state_hash"]
    )

    vector = payload["final_vector_artifact"]
    assert vector["equation_count"] == 70_560
    assert vector["byte_length"] == 70_560 * 8
    assert vector["load_factor"] == 1.0
    assert vector["residual_inf_n"] == pytest.approx(
        metrics["final_residual_inf_kn"] * 1000.0
    )
    assert vector["local_residual_tolerance_n"] == 0.0005
    assert vector["local_residual_gate_passed"] is True
    assert vector["accepted_displacement_checkpoint"] is True
    assert vector["engineer_review_required"] is True
    assert vector["g1_full_load_checkpoint_claim"] is False
    assert vector["promotes_g1_closure"] is False
    vector_path = ROOT / vector["artifact_path"]
    raw = vector_path.read_bytes()
    values = np.frombuffer(raw, dtype="<f8")
    assert values.shape == (70_560,)
    assert np.all(np.isfinite(values))
    assert float(np.linalg.norm(values, ord=np.inf)) == pytest.approx(
        continuation["final_checkpoint"]["displacement_inf_m"]
    )
    assert module.file_sha256(vector_path) == vector["data_sha256"]

    claims = payload["claims"]
    assert claims[
        "actual_mgt_state_updated_axial_load_controlled_continuation"
    ] is True
    assert claims["all_actual_tangent_solves_operator_bound"] is True
    assert claims[
        "all_actual_tangent_solves_deterministic_host_arithmetic"
    ] is True
    assert claims[
        "all_actual_tangent_operator_formula_parent_arrays_bound"
    ] is True
    assert claims["residual_tangent_parent_consistency_audited"] is True
    assert claims["residual_formula_hash_verified"] is True
    assert claims["semantic_live_target_load_1p0_reached"] is True
    assert claims["residual_and_increment_acceptance_gate"] is True
    assert claims["diagnostic_load_1p0_binary_checkpoint"] is True
    assert claims["local_g1_candidate_residual_gate_passed"] is True
    assert claims["direct_full_load_local_residual_gate_passed"] is True
    assert claims["actual_local_directional_quadratic_convergence"] is True
    assert claims["midpoint_restart_exact"] is True
    assert claims[
        "actual_iteration_limited_failure_rollback_exercised"
    ] is True
    assert claims["actual_adaptive_step_reduction_path"] is True
    assert claims["actual_adaptive_failed_step_rollback_exact"] is True
    assert claims["adaptive_midpoint_restart_exact"] is True
    assert claims["material_state_commit_rollback"] is False
    assert claims["full_corotational_frame"] is False
    assert claims["arc_length_branch"] is False
    assert claims["production_matrix_free_krylov"] is False
    assert claims["cross_platform_deterministic_recurrence"] is False
    assert claims["production_rocm_hip_nonlinear_parity"] is False
    assert claims["g1_full_load_checkpoint"] is False
    assert claims["g1_full_building_closure"] is False
    assert (
        "authoritative_g1_checkpoint_contract_not_satisfied"
        in payload["blockers_remaining"]
    )
    assert (
        "diagnostic_0p05_n_residual_floor_not_authoritative_g1_gate"
        not in payload["blockers_remaining"]
    )

    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_committed_receipt_and_binary_are_reproducible() -> None:
    passed, reason = module.check_receipt(repo_root=ROOT)

    assert passed is True, reason
    assert reason == "g1_state_updated_newton_continuation_consistent"
