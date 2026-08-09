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
    "build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_RECEIPT_OUT)


def test_committed_receipt_records_one_actual_matrix_free_correction() -> None:
    payload = _committed_receipt()

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["diagnostic_execution_ready"] is True
    assert payload["readiness_pass"] is False
    assert payload["engineer_review_required"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["inputs"]["free_equation_count"] == 70_560
    assert payload["inputs"]["semantic_load_case"] == "LIVE"
    assert payload["inputs"]["probe_load_factor"] == 1.0
    assert payload["inputs"]["probe_state"] == (
        "full_unit_zero_state_linear_predictor"
    )

    binding = payload["adapter_binding"]
    material_binding = binding["material_analysis_property_binding"]
    assert material_binding["dgn_alias_resolution_enabled"] is True
    assert material_binding["dgn_alias_material_count_applied"] == 24
    assert material_binding["resolved_material_count"] == 30
    assert material_binding["engineer_review_required"] is True
    coverage = binding["frame_source_property_coverage_audit"]
    assert coverage["resolved_source_property_element_count"] == 5_572
    assert coverage["unresolved_source_property_element_count"] == 0
    assert coverage["exact_source_property_coverage"] is True
    geometry = binding["state_updated_frame_axial_geometry"]
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
    assert preconditioner[
        "approximate_for_state_dependent_adapter"
    ] is True
    assert preconditioner["production_preconditioner_claim"] is False

    solve = payload["tangent_solve"]
    assert solve["status"] == "ready"
    assert solve["contract_pass"] is True
    assert solve["converged"] is True
    assert solve["terminal_reason"] == "converged_explicit_residual"
    assert solve["equation_count"] == 70_560
    assert solve["iteration_count"] == 3
    assert solve["restart_count"] == 0
    assert solve["operator_action_count"] == 5
    assert solve["preconditioner_application_count"] == 3
    assert solve["explicit_residual_check_count"] == 2
    assert solve["right_hand_side_inf_kn"] == pytest.approx(
        3.8238140951064206
    )
    assert solve["explicit_residual_inf_kn"] == pytest.approx(
        4.116211926429719e-10
    )
    assert solve["explicit_residual_inf_kn"] <= solve[
        "explicit_residual_tolerance_inf_kn"
    ]
    assert solve["matrix_free_current_state_operator_action"] is True
    assert solve["materialized_current_tangent"] is False
    assert solve["fallback_count"] == 0
    assert solve["regularization_count"] == 0
    operator_binding = solve["operator_binding"]
    assert solve["operator_binding_ready"] is True
    assert operator_binding["status"] == "ready"
    assert operator_binding["equation_count"] == 70_560
    assert operator_binding["free_equation_order_data_hash"] == (
        "sha256:21e0cef7915f3c68a772ca541123453a"
        "35535c3b172110ebd54f16695541c1b1"
    )
    assert operator_binding["residual_formula_hash"] == residual_contract[
        "residual_formula_hash"
    ]
    assert operator_binding["current_tangent_action_contract"] == (
        "analytic_reference_load_frame_delta_finite_chord_axial_action.v1"
    )
    assert operator_binding["current_tangent_operator_profile"] == (
        "reference_csr_load_frame_delta_finite_chord_axial.v1"
    )
    assert operator_binding["current_tangent_operator_contract_hash"] == (
        "sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177"
    )
    assert operator_binding["operator_callback_outputs_in_contract"] is True
    recurrence = solve["recurrence"]
    assert recurrence["accumulation_profile"] == (
        "ascending_index_python_fsum_fp64.v1"
    )
    assert recurrence["deterministic_host_arithmetic"] is True
    assert recurrence["operator_callback_outputs_in_contract"] is True
    assert recurrence["preconditioner_callback_outputs_in_contract"] is False
    assert solve["deterministic_host_recurrence_arithmetic_claim"] is True
    assert solve["cross_platform_deterministic_recurrence_claim"] is False
    assert solve["production_solver_claim"] is False
    assert solve["rocm_hip_parity_claim"] is False

    probe = payload["newton_correction_probe"]
    assert probe["initial_residual_inf_n"] == pytest.approx(
        3_823.8140951064206
    )
    assert probe["initial_residual_replay_matches"] is True
    assert probe["correction_inf_m"] == pytest.approx(
        2.7140069223677e-07
    )
    assert probe["independent_linear_residual_inf_kn"] <= probe[
        "independent_linear_residual_tolerance_inf_kn"
    ]
    assert probe["trial_residual_inf_n"] == pytest.approx(
        0.002323337105281098
    )
    assert probe["full_step_alpha"] == 1.0
    assert probe["residual_reduction_ratio"] == pytest.approx(
        6.075967731418798e-07
    )
    assert probe["residual_reduction_gate_passed"] is True
    assert probe["accepted_state_committed"] is False
    assert probe["contract_pass"] is True

    claims = payload["claims"]
    assert claims["actual_mgt_current_state_matrix_free_tangent_solve"] is True
    assert claims["actual_mgt_operator_binding_ready"] is True
    assert claims[
        "current_tangent_operator_formula_parent_arrays_bound"
    ] is True
    assert claims["deterministic_host_recurrence_arithmetic"] is True
    assert claims["residual_tangent_parent_consistency_audited"] is True
    assert claims["residual_formula_hash_verified"] is True
    assert claims["explicit_linear_residual_gate_passed"] is True
    assert claims["one_full_step_newton_residual_reduction"] is True
    assert claims["accepted_state_committed"] is False
    assert claims["full_nonlinear_continuation"] is False
    assert claims["production_matrix_free_krylov"] is False
    assert claims["accepted_semantic_live_load_1p0_checkpoint"] is False
    assert claims["g1_full_building_closure"] is False
    assert (
        "single_newton_correction_smoke_not_continuation"
        in payload["blockers_remaining"]
    )

    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_committed_receipt_is_reproducible() -> None:
    passed, reason = module.check_receipt(repo_root=ROOT)

    assert passed is True, reason
    assert reason == "g1_mgt_state_updated_matrix_free_fgmres_smoke_consistent"


def test_source_commit_only_drift_is_volatile_but_input_checksums_are_not() -> None:
    recorded = {
        "generated_at": "2026-08-08T00:00:00Z",
        "source_commit_sha": "a" * 40,
        "input_checksums": {"adapter_receipt": "sha256:recorded"},
    }
    descendant = {
        "generated_at": "2026-08-09T00:00:00Z",
        "source_commit_sha": "b" * 40,
        "input_checksums": {"adapter_receipt": "sha256:recorded"},
    }

    assert module._strip_volatile(recorded) == module._strip_volatile(descendant)

    descendant["input_checksums"]["adapter_receipt"] = "sha256:changed"
    assert module._strip_volatile(recorded) != module._strip_volatile(descendant)
