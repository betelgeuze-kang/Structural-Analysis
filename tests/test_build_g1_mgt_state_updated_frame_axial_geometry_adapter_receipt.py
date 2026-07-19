from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/"
    "build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_RECEIPT_OUT)


def test_committed_receipt_records_actual_state_dependent_adapter() -> None:
    payload = _committed_receipt()

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["readiness_pass"] is False
    assert payload["diagnostic_execution_ready"] is True
    assert payload["engineer_review_required"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["inputs"]["node_count"] == 13_047
    assert payload["inputs"]["element_count"] == 12_728
    assert payload["inputs"]["frame_element_count"] == 5_572
    assert payload["inputs"]["global_dof_count"] == 78_282
    assert payload["inputs"]["free_equation_count"] == 70_560
    assert payload["inputs"]["semantic_load_case"] == "LIVE"
    assert payload["inputs"][
        "historical_checkpoint_equilibrium_claim"
    ] is False

    connectivity = payload["frame_connectivity_audit"]
    assert connectivity["frame_connectivity_source"] == (
        "elem_conn_ptr/elem_conn_idx"
    )
    assert connectivity["edge_index_used_for_element_binding"] is False
    assert connectivity["line_elements_solved"] == 5_572
    assert connectivity["skipped_invalid_line_connectivity_count"] == 0

    binding = payload["material_analysis_property_binding"]
    assert binding == {
        "resolution_policy": (
            "exact_normalized_type_and_name_unique_source_material.v1"
        ),
        "dgn_alias_resolution_enabled": True,
        "source_material_count": 6,
        "dgn_alias_material_count_available": 24,
        "dgn_alias_material_count_applied": 24,
        "resolved_material_count": 30,
        "engineer_review_required": True,
    }
    alias_audit = payload["dgn_material_property_alias_audit"]
    assert alias_audit["contract_pass"] is True
    assert alias_audit["dgn_material_row_count"] == 29
    assert alias_audit["exact_unique_identity_match_row_count"] == 29
    assert alias_audit["existing_source_id_row_count"] == 5
    assert alias_audit["alias_material_count"] == 24
    assert alias_audit["unresolved_identity_rows"] == []
    assert alias_audit["ambiguous_identity_rows"] == []
    assert alias_audit["dgn_numeric_elastic_override_consumed_count"] == 0
    assert alias_audit["fuzzy_name_match_count"] == 0
    assert alias_audit["engineer_review_required"] is True

    coverage = payload["frame_source_property_coverage_audit"]
    assert coverage["source_section_property_count"] == 183
    assert coverage["source_material_property_count"] == 30
    assert coverage["section_property_resolved_element_count"] == 5_572
    assert coverage["material_property_resolved_element_count"] == 5_572
    assert coverage["resolved_source_property_element_count"] == 5_572
    assert coverage["unresolved_source_property_element_count"] == 0
    assert coverage["source_property_coverage_ratio"] == 1.0
    assert coverage["exact_source_property_coverage"] is True
    assert coverage["missing_section_id_counts"] == []
    assert coverage["missing_material_id_counts"] == []

    geometry = payload["state_updated_frame_axial_geometry"]
    assert geometry["formulation_profile"] == (
        "finite_chord_conservative_axial_replacement.v1"
    )
    assert geometry["state_updated_frame_axial_geometry_applied"] is True
    assert geometry["preflight_status"] == "ready"
    assert geometry["prepack_executed"] is True
    assert geometry["element_count"] == 5_572
    assert geometry["real_property_element_count"] == 5_572
    assert geometry["property_fallback_count"] == 0
    assert geometry["beam_end_offset_element_count"] == 706
    assert geometry["reference_linear_axial_contribution_replaced"] is True
    assert geometry["conservative_energy_gradient"] is True
    assert geometry["consistent_tangent_action_available"] is True
    assert geometry["connected_to_physical_residual"] is True
    assert geometry[
        "connected_to_consistent_state_tangent_action"
    ] is True
    assert geometry["consistent_state_tangent_action_mode"] == (
        "analytic_reference_plus_exact_finite_chord_axial_correction"
    )
    assert geometry["finite_chord_extension_evaluation"] == (
        "difference_of_squares_cancellation_stable"
    )
    assert geometry["finite_chord_correction_evaluation"] == (
        "second_order_decomposition_cancellation_stable"
    )
    assert geometry["connected_to_centered_tangent_action"] is False
    assert geometry[
        "centered_tangent_action_available_for_independent_audit"
    ] is True
    assert geometry["frame_bending_torsion_state_update_connected"] is False
    assert geometry["full_corotational_frame_claim"] is False

    tangent = payload["state_dependent_tangent_contract"]
    assert tangent["status"] == "blocked"
    assert tangent["available"] is False
    assert tangent["operator_classification"] == (
        "state_dependent_frame_axial_geometry"
    )
    assert tangent["equation_count"] == 70_560
    assert tangent["current_state_reassembly_required"] is True
    assert tangent["exact_for_adapter_residual_model"] is False
    assert tangent["nonlinear_current_tangent_claim"] is False
    assert tangent["promotes_g1_closure"] is False

    current_tangent = payload["current_tangent_operator_contract"]
    manifest = current_tangent["manifest"]
    assert module.validate_current_tangent_operator_manifest(manifest)
    assert manifest["contract_hash"] == (
        "sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177"
    )
    assert manifest["array_bundle_hash"] == (
        "sha256:19b833d0334ed923586aa9797459fec2814f138d1d7cf525d4f62ea9267a9118"
    )
    assert manifest["dimensions"] == {
        "equation_count": 70_560,
        "frame_element_count": 5_572,
        "geometry_element_count": 5_572,
        "global_dof_count": 78_282,
        "reference_nnz": 1_262_462,
    }
    assert len(manifest["array_descriptors"]) == 12
    operator_binding = current_tangent["operator_binding"]
    assert operator_binding["current_tangent_operator_contract_hash"] == (
        manifest["contract_hash"]
    )
    assert operator_binding[
        "current_tangent_operator_array_bundle_hash"
    ] == manifest["array_bundle_hash"]
    assert operator_binding["operator_callback_outputs_in_contract"] is True
    assert current_tangent["array_total_byte_length"] == 31_271_000
    assert current_tangent[
        "residual_centered_difference_gate_passed"
    ] is True
    assert current_tangent["operator_callback_outputs_in_contract"] is True
    assert current_tangent["cpu_reference_evaluator_executed"] is True
    assert current_tangent["hip_execution"] is False
    assert current_tangent["cpu_hip_numerical_parity"] is False
    assert current_tangent["contract_pass"] is True

    residual_contract = payload["residual_evaluation_contract"]
    assert residual_contract["schema_version"] == (
        "mgt-residual-evaluation-contract.v1"
    )
    assert residual_contract["residual_formula"][
        "residual_sign_convention"
    ] == "internal_minus_external"
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
    assert residual_contract[
        "prescribed_background_term_included"
    ] is True
    assert residual_contract[
        "component_force_assembly_retained_for_diagnostics"
    ] is True
    assert residual_contract["full_corotational_frame_claim"] is False
    assert residual_contract["material_state_update_claim"] is False
    assert residual_contract["promotes_g1_closure"] is False

    parent_audit = payload["residual_parent_equivalence_audit"]
    assert parent_audit["status"] == "ready"
    assert parent_audit["applicable"] is True
    assert parent_audit["probe_state"] == (
        "full_unit_zero_state_linear_predictor"
    )
    assert parent_audit["probe_load_factor"] == 1.0
    assert parent_audit["parent_residual_inf_n"] == pytest.approx(
        3823.8140951064206
    )
    assert parent_audit["component_sum_residual_inf_n"] == pytest.approx(
        3823.8140951476234
    )
    assert parent_audit["parent_component_difference_inf_n"] <= (
        parent_audit["comparison_tolerance_n"]
    )
    assert parent_audit["parent_component_gate_passed"] is True
    assert parent_audit["parent_repeat_bytes_exact"] is True
    assert parent_audit["contract_pass"] is True

    reference_preconditioner = payload[
        "reference_preconditioner_contract"
    ]
    assert reference_preconditioner["status"] == "ready"
    assert reference_preconditioner["available"] is True
    assert reference_preconditioner["equation_count"] == 70_560
    assert reference_preconditioner["intended_use"] == (
        "fixed_right_preconditioner"
    )
    assert reference_preconditioner[
        "exact_for_adapter_residual_model"
    ] is False
    assert reference_preconditioner[
        "approximate_for_state_dependent_adapter"
    ] is True
    assert reference_preconditioner[
        "factorization_executed_by_adapter"
    ] is False
    assert reference_preconditioner[
        "production_preconditioner_claim"
    ] is False

    predictor = payload["zero_state_sparse_predictor_audit"]
    assert predictor["status"] == "ready"
    assert predictor["contract_pass"] is True
    assert predictor["loaded_component_count"] == 1
    assert predictor["solved_component_count"] == 1
    assert predictor["regularization_count"] == 0
    assert predictor["fallback_count"] == 0
    assert predictor["predictor_load_factors"] == [0.25, 0.5, 1.0]
    assert predictor["remainder_classification"] == "measurable_quadratic"
    assert predictor["minimum_observed_remainder_order"] == pytest.approx(
        1.9999997268745022
    )
    assert predictor["linear_model_consistency_gate_passed"] is False
    assert predictor[
        "measurable_quadratic_remainder_gate_passed"
    ] is True
    assert predictor["predictor_remainder_gate_passed"] is True
    assert predictor["quadratic_remainder_gate_passed"] is True
    assert predictor["full_arc_length_continuation_executed"] is False
    assert predictor["production_solver_claim"] is False
    assert predictor["failure"] is None

    replay = payload["callback_replay"]
    assert replay["equation_count"] == 70_560
    assert replay["zero_state_residual_inf_n"] <= 1.0e-9
    assert replay["predictor_residual_replay_matches"] is True
    assert replay["full_unit_predictor_residual_inf_n"] == pytest.approx(
        replay["recorded_full_unit_predictor_residual_inf_n"]
    )
    assert replay["tangent_state_difference_inf_kn_per_m"] > replay[
        "tangent_state_dependence_tolerance_kn_per_m"
    ]
    assert replay["tangent_state_dependence_detected"] is True
    assert replay["analytic_centered_reference_step_m"] == 2.0e-7
    assert replay["analytic_centered_relative_error"] <= replay[
        "analytic_centered_relative_tolerance"
    ]
    assert replay["analytic_centered_gate_passed"] is True
    assert replay["finite"] is True
    assert replay["contract_pass"] is True

    assert payload["claims"][
        "finite_chord_axial_geometry_connected_to_physical_residual"
    ] is True
    assert payload["claims"][
        "finite_chord_axial_geometry_connected_to_consistent_state_tangent"
    ] is True
    assert payload["claims"][
        "measurable_quadratic_predictor_remainder"
    ] is True
    assert payload["claims"][
        "residual_parent_matches_analytic_tangent"
    ] is True
    assert payload["claims"]["residual_formula_hash_verified"] is True
    assert payload["claims"][
        "residual_parent_component_equivalence_audited"
    ] is True
    assert payload["claims"][
        "backend_neutral_current_tangent_operator_contract"
    ] is True
    assert payload["claims"][
        "operator_callback_formula_and_parent_arrays_in_contract"
    ] is True
    assert payload["claims"]["full_corotational_frame"] is False
    assert payload["claims"]["full_nonlinear_continuation"] is False
    assert payload["claims"]["g1_full_building_closure"] is False
    assert (
        "dgn_exact_type_name_material_inheritance_engineer_review_required"
        in payload["blockers_remaining"]
    )
    assert (
        "production_matrix_free_state_tangent_krylov_not_executed"
        in payload["blockers_remaining"]
    )
    assert "current_tangent_operator_hip_execution_not_performed" in (
        payload["blockers_remaining"]
    )

    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_committed_receipt_is_reproducible() -> None:
    passed, reason = module.check_receipt(repo_root=ROOT)

    assert passed is True, reason
    assert reason == "g1_mgt_state_updated_frame_axial_adapter_consistent"
