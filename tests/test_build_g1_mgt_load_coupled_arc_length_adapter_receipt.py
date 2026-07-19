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
    ROOT / "scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_load_coupled_arc_length_adapter_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_RECEIPT_OUT)


def _committed_summary() -> dict:
    return module._read_json(ROOT / module.DEFAULT_SUMMARY_OUT)


def test_committed_receipt_records_actual_adapter_and_fail_closed_boundaries() -> None:
    receipt = _committed_receipt()
    summary = _committed_summary()

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["evidence_closure_pass"] is False
    assert receipt["source_commit_exact_replay_claim"] is False
    assert receipt["adapter_metadata"]["node_count"] == 13_047
    assert receipt["adapter_metadata"]["global_dof_count"] == 78_282
    assert receipt["adapter_metadata"]["free_equation_count"] == 70_560
    assert receipt["adapter_metadata"]["checkpoint_load_factor"] == 0.656
    assert receipt["adapter_metadata"]["initial_state_policy"] == (
        "historical_checkpoint"
    )
    assert receipt["adapter_metadata"]["initial_load_factor"] == 0.656
    assert receipt["adapter_metadata"][
        "historical_checkpoint_state_consumed"
    ] is True
    assert receipt["adapter_metadata"][
        "roundtrip_generated_uncoarsened"
    ] is True
    assert receipt["adapter_metadata"][
        "source_material_properties_consumed"
    ] is True
    material_binding = receipt["adapter_metadata"][
        "material_analysis_property_binding"
    ]
    assert material_binding == {
        "resolution_policy": "MATERIAL_rows_only.v1",
        "dgn_alias_resolution_enabled": False,
        "source_material_count": 6,
        "dgn_alias_material_count_available": 24,
        "dgn_alias_material_count_applied": 0,
        "resolved_material_count": 6,
        "engineer_review_required": False,
    }
    dgn_alias_audit = receipt["adapter_metadata"][
        "dgn_material_property_alias_audit"
    ]
    assert dgn_alias_audit["contract_pass"] is True
    assert dgn_alias_audit["source_material_count"] == 6
    assert dgn_alias_audit["dgn_material_row_count"] == 29
    assert dgn_alias_audit["dgn_unique_material_id_count"] == 29
    assert dgn_alias_audit["existing_source_id_row_count"] == 5
    assert dgn_alias_audit[
        "exact_unique_identity_match_row_count"
    ] == 29
    assert dgn_alias_audit["alias_material_count"] == 24
    assert dgn_alias_audit["unresolved_identity_rows"] == []
    assert dgn_alias_audit["ambiguous_identity_rows"] == []
    assert dgn_alias_audit["duplicate_dgn_material_ids"] == []
    assert dgn_alias_audit[
        "dgn_numeric_elastic_override_consumed_count"
    ] == 0
    assert dgn_alias_audit["fuzzy_name_match_count"] == 0
    assert dgn_alias_audit["engineer_review_required"] is True
    property_coverage = receipt["adapter_metadata"][
        "frame_source_property_coverage_audit"
    ]
    assert property_coverage["frame_element_count"] == 5_572
    assert property_coverage[
        "section_property_resolved_element_count"
    ] == 5_572
    assert property_coverage[
        "material_property_resolved_element_count"
    ] == 5_493
    assert property_coverage[
        "resolved_source_property_element_count"
    ] == 5_493
    assert property_coverage[
        "unresolved_source_property_element_count"
    ] == 79
    assert property_coverage["source_property_coverage_ratio"] == pytest.approx(
        5_493 / 5_572
    )
    assert property_coverage["exact_source_property_coverage"] is False
    assert property_coverage["missing_section_element_count"] == 0
    assert property_coverage["missing_section_id_counts"] == []
    assert property_coverage["missing_material_element_count"] == 79
    assert property_coverage["missing_material_id_counts"] == [
        {"material_id": 16, "element_count": 5},
        {"material_id": 26, "element_count": 9},
        {"material_id": 27, "element_count": 9},
        {"material_id": 28, "element_count": 14},
        {"material_id": 29, "element_count": 17},
        {"material_id": 30, "element_count": 15},
        {"material_id": 31, "element_count": 10},
    ]
    assert property_coverage["unresolved_element_head"][0] == {
        "element_id": 1261,
        "section_id": 307,
        "material_id": 27,
        "missing_section_property": False,
        "missing_material_property": True,
    }
    assert property_coverage[
        "fallback_allowed_for_state_updated_geometry"
    ] is False
    assert receipt["adapter_metadata"][
        "all_frame_source_material_properties_resolved"
    ] is False
    state_updated_preflight = receipt["adapter_metadata"][
        "state_updated_frame_axial_geometry"
    ]
    assert state_updated_preflight["preflight_status"] == "blocked"
    assert state_updated_preflight["prepack_executed"] is False
    assert state_updated_preflight[
        "fallback_allowed_for_state_updated_geometry"
    ] is False
    assert receipt["claims"][
        "all_frame_source_material_properties_resolved"
    ] is False
    assert (
        "frame_source_material_property_binding_incomplete"
        in receipt["blockers_remaining"]
    )
    frame_connectivity = receipt["adapter_metadata"][
        "frame_connectivity_audit"
    ]
    assert frame_connectivity["frame_connectivity_source"] == (
        "elem_conn_ptr/elem_conn_idx"
    )
    assert frame_connectivity[
        "edge_index_used_for_element_binding"
    ] is False
    assert frame_connectivity[
        "skipped_invalid_line_connectivity_count"
    ] == 0
    assert frame_connectivity[
        "invalid_line_connectivity_element_id_head"
    ] == []
    assert frame_connectivity["line_element_row_accounting_exact"] is True
    assert frame_connectivity["line_elements_solved"] == receipt[
        "adapter_metadata"
    ]["frame_element_count"]
    assert receipt["claims"][
        "authoritative_element_connectivity_consumed"
    ] is True
    load_contract = receipt["adapter_metadata"]["reference_load_contract"]
    assert load_contract["benchmark_bridge_proxy"] is False
    assert load_contract["load_case"] == "LIVE"
    assert load_contract["selected_case_row_accounting_exact"] is True
    assert load_contract["source_mgt_nodal_load_rows_consumed"] is True
    assert load_contract["source_mgt_selfweight_rows_consumed"] is False
    assert load_contract["source_mgt_pressure_load_rows_consumed"] is True
    assert load_contract["source_mgt_load_combination_consumed"] is False
    assert load_contract["checkpoint_reference_load_contract_matches"] is False
    assert receipt["claims"][
        "actual_mgt_semantic_load_case_consumed"
    ] is True
    assert (
        "actual_mgt_semantic_load_case_not_connected"
        not in receipt["blockers_remaining"]
    )
    assert (
        "historical_checkpoint_reference_load_contract_not_proven_live"
        in receipt["blockers_remaining"]
    )
    semantic_load = receipt["adapter_metadata"]["semantic_load_assembly"]
    assert semantic_load["contract_pass"] is True
    assert semantic_load["target_kind"] == "static_load_case"
    assert semantic_load["target_name"] == "LIVE"
    assert semantic_load["case_factors"] == {"LIVE": 1.0}
    assert semantic_load["unit_contract"]["source_force_unit"] == "KN"
    assert semantic_load["unit_contract"]["source_length_unit"] == "M"
    assert semantic_load["selected_target_row_counts"] == {
        "nodal_loads": 6,
        "selfweight": 0,
        "pressure_loads": 3_644,
    }
    assert semantic_load["selected_target_rows_consumed"] == (
        semantic_load["selected_target_row_counts"]
    )
    assert semantic_load["unbound_source_row_counts"] == {
        "nodal_loads": 0,
        "selfweight": 0,
        "pressure_loads": 0,
    }
    assert semantic_load["unsupported_selected_row_count"] == 0
    assert semantic_load["pressure_loaded_area_m2"] == pytest.approx(
        7_802.903986433339
    )
    assert semantic_load["assembled_force_resultant_n"] == pytest.approx(
        [0.0, 0.0, -50_628_330.359766744]
    )
    assert semantic_load["reference_load_inf_n"] == pytest.approx(
        179_458.19249999968
    )
    assert semantic_load["resultant_gate_passed"] is True
    assert receipt["adapter_metadata"][
        "material_state_commit_rollback_connected"
    ] is False
    free_map_audit = receipt["adapter_metadata"][
        "zero_to_unit_free_map_audit"
    ]
    assert free_map_audit["fixed_free_map_exact"] is True
    assert free_map_audit["zero_state_free_equation_count"] == 70_560
    assert free_map_audit["unit_load_free_equation_count"] == 70_560
    assert free_map_audit["zero_tangent_on_unit_map_zero_row_count"] == 0
    assert free_map_audit["zero_tangent_on_unit_map_zero_diagonal_count"] == 0
    assert free_map_audit["zero_tangent_structural_rank_deficiency"] == 0
    assert free_map_audit["free_graph_component_count"] == 2_171
    assert free_map_audit["free_graph_loaded_component_count"] == 1
    assert free_map_audit["free_graph_unanchored_component_count"] == 2_167
    assert free_map_audit[
        "free_graph_unanchored_loaded_component_count"
    ] == 0
    assert free_map_audit["free_graph_unanchored_loaded_components"] == []
    assert receipt["claims"][
        "zero_to_unit_fixed_free_map_compatible"
    ] is True
    predictor_audit = receipt["adapter_metadata"][
        "zero_state_sparse_predictor_audit"
    ]
    assert predictor_audit["zero_state_equilibrium_gate_passed"] is True
    assert predictor_audit["zero_state_load_direction_gate_passed"] is True
    assert predictor_audit["sparse_direct_solve_attempted"] is True
    assert predictor_audit["loaded_component_count"] == 1
    assert predictor_audit["solved_component_count"] == 1
    assert predictor_audit["regularization_count"] == 0
    assert predictor_audit["fallback_count"] == 0
    assert predictor_audit["linear_residual_gate_passed"] is True
    assert predictor_audit["explicit_linear_residual_inf_n"] <= 5.0e-4
    assert predictor_audit["predictor_load_factors"] == [0.25, 0.5, 1.0]
    assert predictor_audit["minimum_observed_remainder_order"] is None
    assert predictor_audit["remainder_classification"] == (
        "linear_within_numerical_floor"
    )
    assert predictor_audit["linear_model_consistency_gate_passed"] is True
    assert predictor_audit[
        "measurable_quadratic_remainder_gate_passed"
    ] is False
    assert predictor_audit["predictor_remainder_gate_passed"] is True
    assert all(
        not row["nonlinear_remainder_above_noise"]
        for row in predictor_audit["predictor_rows"]
    )
    assert predictor_audit["quadratic_remainder_gate_passed"] is False
    assert predictor_audit["contract_pass"] is True
    assert predictor_audit["failure"] is None
    assert receipt["claims"][
        "zero_state_sparse_direct_predictor_contract"
    ] is True
    tangent_contract = receipt["adapter_metadata"][
        "state_invariant_tangent_contract"
    ]
    assert tangent_contract["status"] == "ready"
    assert tangent_contract["available"] is True
    assert tangent_contract["operator_classification"] == (
        "state_invariant_linear_reference_geometry"
    )
    assert tangent_contract["equation_count"] == 70_560
    assert tangent_contract["operator_nnz"] == 1_264_133
    assert tangent_contract["current_state_reassembly_required"] is False
    assert tangent_contract["exact_for_adapter_residual_model"] is True
    assert tangent_contract["nonlinear_current_tangent_claim"] is False
    assert tangent_contract["quadratic_convergence_claim"] is False
    assert tangent_contract["material_state_commit_rollback_claim"] is False
    assert tangent_contract["promotes_g1_closure"] is False
    assert receipt["claims"][
        "state_invariant_linear_reference_tangent_bound"
    ] is True
    reference_preconditioner = receipt["adapter_metadata"][
        "reference_preconditioner_contract"
    ]
    assert reference_preconditioner["status"] == "ready"
    assert reference_preconditioner["available"] is True
    assert reference_preconditioner["operator_classification"] == (
        "zero_state_linear_reference_geometry"
    )
    assert reference_preconditioner["equation_count"] == 70_560
    assert reference_preconditioner["operator_nnz"] == 1_264_133
    assert reference_preconditioner["intended_use"] == (
        "fixed_right_preconditioner"
    )
    assert reference_preconditioner[
        "exact_for_adapter_residual_model"
    ] is True
    assert reference_preconditioner[
        "approximate_for_state_dependent_adapter"
    ] is False
    assert reference_preconditioner[
        "factorization_executed_by_adapter"
    ] is False
    assert reference_preconditioner[
        "production_preconditioner_claim"
    ] is False
    assert reference_preconditioner["promotes_g1_closure"] is False
    assert reference_preconditioner[
        "operator_numeric_values_hash"
    ] == tangent_contract["operator_numeric_values_hash"]
    predictor_artifact = receipt["adapter_metadata"][
        "full_unit_predictor_vector_artifact"
    ]
    assert predictor_artifact["schema_version"] == (
        "g1-mgt-live-full-unit-predictor-vector.v1"
    )
    assert predictor_artifact["status"] == "ready"
    assert predictor_artifact["dtype"] == "<f8"
    assert predictor_artifact["layout"] == "C"
    assert predictor_artifact["byte_order"] == "little"
    assert predictor_artifact["equation_order"] == (
        "adapter_free_global_dof_order"
    )
    assert predictor_artifact["equation_count"] == 70_560
    assert predictor_artifact["byte_length"] == 564_480
    assert predictor_artifact["load_factor"] == 1.0
    assert predictor_artifact["residual_inf_n"] == pytest.approx(
        0.00024772050528554246
    )
    assert predictor_artifact["residual_tolerance_n"] == 5.0e-4
    assert predictor_artifact["residual_gate_passed"] is True
    assert predictor_artifact["maximum_translation_m"] == pytest.approx(
        0.003460998957181514
    )
    assert predictor_artifact["data_sha256"] == predictor_audit[
        "predictor_direction_hash"
    ]
    assert predictor_artifact[
        "persisted_nonlinear_continuation_checkpoint"
    ] is False
    assert predictor_artifact["large_vector_binary_trace_claim"] is False
    assert predictor_artifact["g1_full_load_checkpoint_claim"] is False
    assert predictor_artifact["promotes_g1_closure"] is False
    predictor_path = ROOT / receipt["artifacts"]["full_unit_predictor_vector"]
    assert predictor_artifact["artifact_path"] == predictor_path.relative_to(
        ROOT
    ).as_posix()
    assert predictor_path.is_file()
    assert predictor_path.stat().st_size == predictor_artifact["byte_length"]
    assert module.file_sha256(predictor_path) == predictor_artifact[
        "data_sha256"
    ]
    predictor_values = np.fromfile(predictor_path, dtype="<f8")
    assert predictor_values.shape == (70_560,)
    assert np.all(np.isfinite(predictor_values))
    assert receipt["claims"][
        "full_unit_semantic_live_predictor_binary_artifact"
    ] is True
    assert receipt["claims"]["large_vector_binary_trace"] is False
    component_audit = receipt["adapter_metadata"][
        "initial_state_component_audit"
    ]
    assert component_audit["component_sum_matches_internal_exact"] is True
    assert component_audit["dominant_component_by_free_inf"] == "frame"
    assert component_audit[
        "dominant_component_at_residual_argmax"
    ] == "frame"
    assert component_audit["hotspot_connected_frame_element_count"] == 3
    assert component_audit["hotspot_dominant_frame_element_id"] == 16_441
    assert component_audit[
        "hotspot_maximum_connected_frame_force_inf_n"
    ] > 1.0e12
    dominant_frame = component_audit[
        "hotspot_connected_frame_elements"
    ][0]
    assert dominant_frame["element_id"] == 16_441
    assert dominant_frame["node_ids"] == [336, 2_294]
    assert dominant_frame["material_name"] == "RigidBar"
    assert dominant_frame["section_area_m2"] == pytest.approx(0.01)
    assert dominant_frame[
        "material_elastic_modulus_n_per_m2"
    ] == pytest.approx(2.8e16)
    assert dominant_frame["reference_length_m"] == pytest.approx(
        0.4022747817102226
    )
    assert component_audit["hotspot_connected_shell_element_count"] == 4
    assert component_audit[
        "hotspot_maximum_perimeter_translation_jump_m"
    ] == pytest.approx(0.006714415448707063)
    assert component_audit[
        "hotspot_maximum_perimeter_edge_engineering_strain_abs"
    ] == pytest.approx(0.004664272204824238)
    audit = receipt["initial_state_audit"]
    assert audit["equation_count"] == 70_560
    assert audit["residual_inf_norm_kn"] == pytest.approx(
        1_277_024_522.7876618
    )
    assert audit["residual_equilibrium_gate_required_by_adapter_audit"] is False
    assert audit["residual_equilibrium_gate_passed"] is False
    assert audit["negative_load_derivative_gate_passed"] is True
    assert audit["maximum_negative_load_derivative_error_kn"] <= audit[
        "negative_load_derivative_absolute_tolerance_kn"
    ]
    assert audit["negative_load_derivative_relative_error"] <= 5.0e-8
    assert audit["tangent_step_comparison_gate_passed"] is True
    assert audit["tangent_step_comparison_relative_error"] <= 5.0e-3
    comparison = receipt["stored_receipt_comparison"]
    assert comparison["load_factor_matches"] is True
    assert comparison["stored_receipt_generated_at"] == (
        "2026-06-04T07:16:56.554987+00:00"
    )
    assert comparison["stored_receipt_source_commit_sha_present"] is False
    assert comparison["stored_receipt_input_checksums_present"] is False
    assert comparison["stored_receipt_replay_provenance_complete"] is False
    assert comparison["stored_base_direct_residual_inf_n"] == pytest.approx(
        42_754.66805918372
    )
    assert comparison["stored_receipt_equivalent_to_current_adapter"] is False
    assert comparison["current_to_stored_ratio"] > 10_000_000.0
    assert (
        "current_source_diverges_from_stored_direct_residual_receipt"
        in receipt["blockers_remaining"]
    )
    assert receipt["claims"]["full_arc_length_continuation"] is False
    assert receipt["claims"][
        "actual_mgt_frame_shell_spring_residual_adapter_evaluated"
    ] is True
    assert receipt["claims"][
        "initial_state_component_breakdown_recorded"
    ] is True
    assert receipt["claims"][
        "stored_direct_residual_receipt_replay_provenance_complete"
    ] is False
    assert receipt["claims"]["material_state_commit_rollback"] is False
    assert receipt["claims"]["production_rocm_hip_nonlinear_parity"] is False
    assert receipt["claims"]["load_1p0_checkpoint"] is False
    assert receipt["claims"]["g1_full_building_closure"] is False
    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["evidence_closure_pass"] is False
    assert summary["stored_receipt_equivalent_to_current_adapter"] is False
    assert summary["stored_receipt_replay_provenance_complete"] is False


def test_committed_receipt_validates_against_schema() -> None:
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_committed_receipt())


def test_stored_receipt_comparison_requires_matching_value_and_load(
    tmp_path: Path,
) -> None:
    stored_path = tmp_path / "stored.json"
    stored_path.write_text(
        json.dumps(
            {
                "checkpoint": {"load_scale": 0.656},
                "base_direct_residual": {"direct_residual_inf_n": 100.0},
            }
        ),
        encoding="utf-8",
    )

    comparison = module._stored_receipt_comparison(
        repo_root=ROOT,
        stored_receipt_path=stored_path,
        current_audit={"load_factor": 0.656, "residual_inf_norm_kn": 0.2},
    )

    assert comparison["load_factor_matches"] is True
    assert comparison["current_adapter_initial_residual_inf_n"] == 200.0
    assert comparison["absolute_difference_n"] == 100.0
    assert comparison["stored_receipt_equivalent_to_current_adapter"] is False


def test_check_reports_missing_artifact_without_running_actual_adapter(
    tmp_path: Path,
) -> None:
    ok, message = (
        module.check_g1_mgt_load_coupled_arc_length_adapter_receipt(
            repo_root=ROOT,
            receipt_out=tmp_path / "missing-receipt.json",
            summary_out=tmp_path / "missing-summary.json",
        )
    )

    assert ok is False
    assert message == "g1_mgt_load_coupled_adapter_missing:receipt"
