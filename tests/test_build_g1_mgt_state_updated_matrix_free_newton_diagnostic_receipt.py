from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/"
    "build_g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_RECEIPT_OUT)


def test_committed_receipt_records_two_stable_full_step_descents() -> None:
    receipt = _committed_receipt()

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["readiness_pass"] is False
    assert receipt["evidence_closure_pass"] is False
    assert receipt["inputs"]["load_factor"] == 1.0
    assert receipt["inputs"]["free_equation_count"] == 70_560
    assert receipt["inputs"]["initial_state_policy"] == (
        "full_unit_zero_state_linear_predictor"
    )
    adapter = receipt["adapter_binding"]
    assert adapter["actual_mgt_semantic_live_target_consumed"] is True
    assert adapter["semantic_target_name"] == "LIVE"
    assert adapter["frame_element_count"] == 5_572
    assert adapter["exact_frame_source_property_coverage"] is True
    assert adapter["dgn_alias_contract_pass"] is True
    assert adapter["dgn_alias_engineer_review_required"] is True
    geometry = adapter["state_updated_frame_axial_geometry"]
    assert geometry["state_updated_frame_axial_geometry_applied"] is True
    assert geometry["connected_to_physical_residual"] is True
    assert geometry["connected_to_consistent_state_tangent_action"] is True
    assert geometry["consistent_state_tangent_action_mode"] == (
        "analytic_reference_plus_exact_finite_chord_axial_correction"
    )
    assert geometry["connected_to_centered_tangent_action"] is False
    assert geometry["finite_chord_extension_evaluation"] == (
        "difference_of_squares_cancellation_stable"
    )
    assert geometry["finite_chord_correction_evaluation"] == (
        "second_order_decomposition_cancellation_stable"
    )
    assert geometry["property_fallback_count"] == 0
    residual_contract = adapter["residual_evaluation_contract"]
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
    residual_audit = adapter["residual_parent_equivalence_audit"]
    assert residual_audit["status"] == "ready"
    assert residual_audit["applicable"] is True
    assert residual_audit["parent_component_difference_inf_n"] <= (
        residual_audit["comparison_tolerance_n"]
    )
    assert residual_audit["parent_component_gate_passed"] is True
    assert residual_audit["parent_repeat_bytes_exact"] is True
    assert residual_audit["contract_pass"] is True
    preconditioner = adapter["reference_preconditioner_contract"]
    assert preconditioner["intended_use"] == "fixed_right_preconditioner"
    assert preconditioner["exact_for_adapter_residual_model"] is False
    assert preconditioner["approximate_for_state_dependent_adapter"] is True
    assert preconditioner["production_preconditioner_claim"] is False
    solver_binding = receipt["solver_binding"]
    assert solver_binding["operator_binding"]["status"] == "ready"
    assert solver_binding["operator_binding"]["equation_count"] == 70_560
    assert solver_binding["operator_binding"]["residual_formula_hash"] == (
        residual_contract["residual_formula_hash"]
    )
    assert solver_binding["operator_binding"][
        "current_tangent_operator_contract_hash"
    ] == (
        "sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177"
    )
    assert solver_binding[
        "operator_callback_formula_parent_arrays_bound"
    ] is True
    assert solver_binding["accumulation_profile"] == (
        "ascending_index_python_fsum_fp64.v1"
    )
    assert solver_binding["deterministic_host_recurrence_arithmetic"] is True
    assert solver_binding[
        "cross_platform_end_to_end_deterministic_claim"
    ] is False

    attempts = receipt["newton_attempts"]
    assert len(attempts) == 2
    first, second = attempts
    assert first["attempt_index"] == 1
    assert first["accepted"] is True
    assert first["rejection_reason"] is None
    assert first["residual_descent"] is True
    assert first["rollback_exercised"] is False
    assert first["before_residual_inf_kn"] == pytest.approx(
        3.8238140951064206,
        rel=0.0,
        abs=1.0e-15,
    )
    assert first["trial_residual_inf_kn"] == pytest.approx(
        2.323337105281098e-06,
        rel=0.0,
        abs=1.0e-15,
    )
    assert first["trial_residual_gate_passed"] is False
    assert first["tangent_solve"]["contract_pass"] is True
    assert first["tangent_solve"]["iteration_count"] == 3
    assert first["tangent_solve"]["operator_action_count"] == 6
    assert first["tangent_solve"]["explicit_residual_inf_kn"] <= 5.0e-7
    assert first["tangent_solve"]["operator_binding_ready"] is True
    assert first["tangent_solve"][
        "deterministic_host_recurrence_arithmetic_claim"
    ] is True

    assert second["attempt_index"] == 2
    assert second["accepted"] is True
    assert second["rejection_reason"] is None
    assert second["residual_descent"] is True
    assert second["rollback_exercised"] is False
    assert second["rollback_byte_exact"] is False
    assert second["state_after_data_hash"] == second["trial_state_data_hash"]
    assert second["trial_state_data_hash"] != second["state_before_data_hash"]
    assert second["trial_residual_inf_kn"] == pytest.approx(
        1.1767242540372535e-09,
        rel=0.0,
        abs=1.0e-15,
    )
    assert second["trial_residual_inf_kn"] < second["before_residual_inf_kn"]
    assert second["trial_residual_gate_passed"] is True
    assert second["tangent_solve"]["contract_pass"] is True
    assert second["tangent_solve"]["iteration_count"] == 2
    assert second["tangent_solve"]["operator_action_count"] == 4
    assert second["tangent_solve"]["explicit_residual_inf_kn"] <= 5.0e-7

    metrics = receipt["metrics"]
    assert metrics["attempt_count"] == 2
    assert metrics["accepted_attempt_count"] == 2
    assert metrics["rejected_attempt_count"] == 0
    assert metrics["residual_gate_kn"] == 5.0e-7
    assert metrics["residual_gate_passed"] is True
    assert metrics["accepted_residual_reduction_factor_inf"] > 2.5e9
    assert metrics["final_accepted_state_data_hash"] == second[
        "state_after_data_hash"
    ]
    assert metrics["total_tangent_iteration_count"] == 5
    assert metrics["total_tangent_operator_action_count"] == 10
    assert metrics["fallback_count"] == 0
    assert metrics["regularization_count"] == 0
    assert metrics["line_search_executed"] is False

    claims = receipt["claims"]
    assert claims["analytic_current_state_tangent_action"] is True
    assert claims["local_cpu_matrix_free_state_tangent_diagnostic"] is True
    assert claims["all_tangent_solves_operator_bound"] is True
    assert claims["all_tangent_solves_deterministic_host_arithmetic"] is True
    assert claims[
        "all_tangent_operator_formula_parent_arrays_bound"
    ] is True
    assert claims["explicit_tangent_residual_replay"] is True
    assert claims["cancellation_stable_finite_chord_evaluation"] is True
    assert claims[
        "residual_parent_operator_matches_analytic_tangent"
    ] is True
    assert claims["residual_formula_hash_verified"] is True
    assert claims["first_full_newton_step_residual_descent"] is True
    assert claims["second_full_newton_step_residual_descent"] is True
    assert claims["full_load_residual_gate_passed"] is True
    assert claims["globalized_newton"] is False
    assert claims["full_nonlinear_continuation"] is False
    assert claims["persisted_load_1p0_checkpoint"] is False
    assert claims["production_matrix_free_state_tangent_krylov"] is False
    assert claims["cross_platform_deterministic_recurrence"] is False
    assert claims["production_rocm_hip_nonlinear_parity"] is False
    assert claims["g1_full_building_closure"] is False
    assert "accepted_diagnostic_residual_above_g1_gate" not in receipt[
        "blockers_remaining"
    ]
    assert "full_nonlinear_continuation_not_executed" in receipt[
        "blockers_remaining"
    ]


def test_committed_receipt_validates_against_schema() -> None:
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_committed_receipt())


def test_committed_input_checksums_match_files() -> None:
    receipt = _committed_receipt()

    for relative_path, expected in receipt["input_checksums"].items():
        assert module.file_sha256(ROOT / relative_path) == expected


def test_check_reports_missing_receipt_without_running_actual_model(
    tmp_path: Path,
) -> None:
    ok, message = module.check_receipt(
        repo_root=ROOT,
        receipt_out=tmp_path / "missing.json",
    )

    assert ok is False
    assert message == "g1_mgt_state_updated_matrix_free_newton_missing"


def test_portable_comparison_accepts_bounded_platform_numeric_drift() -> None:
    existing = _committed_receipt()
    expected = deepcopy(existing)
    expected["generated_at"] = "2099-01-01T00:00:00+00:00"
    expected["source_commit_sha"] = "f" * 40
    expected["inputs"]["initial_state_data_hash"] = "sha256:" + "1" * 64
    first = expected["newton_attempts"][0]
    first["trial_residual_inf_kn"] += 1.0e-10
    first["accepted_after_residual_inf_kn"] += 1.0e-10
    expected["newton_attempts"][1]["before_residual_inf_kn"] += 1.0e-10
    first["trial_state_data_hash"] = "sha256:" + "2" * 64
    first["tangent_solve"]["contract_hash"] = "sha256:" + "3" * 64
    first["tangent_solve"]["solution_data_hash"] = "sha256:" + "4" * 64

    assert module._portable_receipt_difference(existing, expected) is None
    assert module._portable_receipt_invariant_error(existing) is None
    assert module._portable_receipt_invariant_error(expected) is None


def test_portable_comparison_rejects_source_or_contract_tampering() -> None:
    existing = _committed_receipt()

    checksum_tamper = deepcopy(existing)
    first_path = next(iter(checksum_tamper["input_checksums"]))
    checksum_tamper["input_checksums"][first_path] = "sha256:" + "0" * 64
    assert module._portable_receipt_difference(existing, checksum_tamper) == (
        f"input_checksums.{first_path}"
    )

    claim_tamper = deepcopy(existing)
    claim_tamper["claims"]["globalized_newton"] = True
    assert module._portable_receipt_difference(existing, claim_tamper) == (
        "claims.globalized_newton"
    )

    failed_gate = deepcopy(existing)
    failed_gate["metrics"]["final_accepted_residual_inf_kn"] += 1.0e-4
    assert module._portable_receipt_invariant_error(failed_gate) == (
        "metrics.final_accepted_residual_inf_kn"
    )
