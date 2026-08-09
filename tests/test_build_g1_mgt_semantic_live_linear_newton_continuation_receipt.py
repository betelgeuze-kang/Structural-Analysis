from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/"
    "build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_semantic_live_linear_newton_continuation_receipt",
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


def test_committed_receipt_records_actual_linear_path_without_promotion() -> None:
    receipt = _committed_receipt()
    summary = _committed_summary()

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["evidence_closure_pass"] is False
    binding = receipt["adapter_binding"]
    assert binding["initial_state_policy"] == "zero_state"
    assert binding["initial_load_factor"] == 0.0
    assert binding[
        "historical_checkpoint_free_vector_used_as_initial_state"
    ] is False
    assert binding["historical_checkpoint_used_for_operator_binding"] is True
    assert binding["historical_checkpoint_nonfree_displacement_inf_m"] == 0.0
    assert binding["node_count"] == 13_047
    assert binding["global_dof_count"] == 78_282
    assert binding["free_equation_count"] == 70_560
    semantic = binding["semantic_load_assembly"]
    assert semantic["target_kind"] == "static_load_case"
    assert semantic["target_name"] == "LIVE"
    assert semantic["selected_target_row_counts"] == {
        "nodal_loads": 6,
        "selfweight": 0,
        "pressure_loads": 3_644,
    }
    assert semantic["selected_case_row_accounting_exact"] is True
    assert semantic["unsupported_selected_row_count"] == 0
    tangent = binding["state_invariant_tangent_contract"]
    assert tangent["operator_classification"] == (
        "state_invariant_linear_reference_geometry"
    )
    assert tangent["equation_count"] == 70_560
    assert tangent["operator_nnz"] == 1_264_133
    assert tangent["exact_for_adapter_residual_model"] is True
    assert tangent["nonlinear_current_tangent_claim"] is False
    coverage = binding["frame_source_property_coverage_audit"]
    assert coverage["frame_element_count"] == 5_572
    assert coverage["resolved_source_property_element_count"] == 5_493
    assert coverage["unresolved_source_property_element_count"] == 79
    assert coverage["exact_source_property_coverage"] is False
    material_binding = binding["material_analysis_property_binding"]
    assert material_binding["resolution_policy"] == "MATERIAL_rows_only.v1"
    assert material_binding["source_material_count"] == 6
    assert material_binding["resolved_material_count"] == 6
    assert material_binding["dgn_alias_resolution_enabled"] is False
    assert material_binding["dgn_alias_material_count_available"] == 24
    assert material_binding["dgn_alias_material_count_applied"] == 0
    alias_audit = binding["dgn_material_property_alias_audit"]
    assert alias_audit["contract_pass"] is True
    assert alias_audit["dgn_material_row_count"] == 29
    assert alias_audit["exact_unique_identity_match_row_count"] == 29
    assert alias_audit["alias_material_count"] == 24
    assert alias_audit["unresolved_identity_rows"] == []
    assert alias_audit["ambiguous_identity_rows"] == []
    assert alias_audit["dgn_numeric_elastic_override_consumed_count"] == 0
    assert alias_audit["fuzzy_name_match_count"] == 0
    assert alias_audit["engineer_review_required"] is True
    assert binding["all_frame_source_material_properties_resolved"] is False
    assert binding["state_updated_frame_axial_geometry_applied"] is False

    direct = receipt["direct_continuation"]
    assert direct["status"] == "ready"
    assert direct["terminal_reason"] == "target_load_factor_reached"
    assert [row["load_factor"] for row in direct["checkpoints"]] == [
        0.0,
        0.25,
        0.75,
        1.0,
    ]
    metrics = direct["metrics"]
    assert metrics["accepted_step_count"] == 3
    assert metrics["failed_step_count"] == 0
    assert metrics["target_load_factor_reached"] is True
    assert metrics["residual_gate_passed"] is True
    assert metrics["fallback_count"] == 0
    assert metrics["regularization_count"] == 0
    assert metrics["material_state_commit_count"] == 0
    assert metrics["minimum_accepted_line_search_alpha"] == 1.0
    assert metrics["final_residual_inf_n"] <= 5.0e-4
    assert metrics["maximum_tangent_solve_explicit_residual_inf_n"] <= 5.0e-4
    assert direct["tangent_consistency_audit"]["all_gates_passed"] is True
    assert direct["claims"]["actual_mgt_semantic_live_load"] is True
    assert direct["claims"]["full_load_linear_reference_checkpoint"] is True
    assert direct["claims"]["failed_step_rollback_exact"] is False
    assert direct["claims"]["nonlinear_current_tangent"] is False
    assert direct["claims"]["quadratic_convergence"] is False
    assert direct["claims"]["g1_full_load_checkpoint"] is False

    replay = receipt["restart_replay_audit"]
    assert replay["status"] == "ready"
    assert replay["contract_pass"] is True
    assert replay["serialized_checkpoint_load_factor"] == 0.75
    assert replay["checkpoint_state_hash_validated_on_reload"] is True
    assert replay["serialization_roundtrip_byte_exact"] is True
    assert replay["restart_checkpoint_consumed"] is True
    assert replay["final_displacement_bytes_identical"] is True
    assert replay["final_state_hash_identical"] is True
    assert replay["direct_final_data_sha256"] == replay[
        "restarted_final_data_sha256"
    ]
    assert replay["direct_final_state_hash"] == replay[
        "restarted_final_state_hash"
    ]
    assert replay["serialized_checkpoint_data_sha256"] == (
        "sha256:54ff7e76815eea773df1ecb2e7eb70f4d7045c35449f3a618af6fa0d431ca2f8"
    )
    assert replay["direct_final_data_sha256"] == (
        "sha256:e598d1b996deb2260eac80c7c66b4da7e64202513c011f570f7c7dcc659279b2"
    )
    full_load_artifact = receipt["full_load_checkpoint_artifact"]
    full_load_descriptor = full_load_artifact["checkpoint"]
    full_load_vector = np.fromfile(
        ROOT / full_load_artifact["artifact_path"],
        dtype="<f8",
    )
    validated_full_load_checkpoint = module.LinearReferenceNewtonCheckpoint(
        schema_version=full_load_descriptor["schema_version"],
        case_id=full_load_descriptor["case_id"],
        path_contract_hash=full_load_descriptor["path_contract_hash"],
        step_index=full_load_descriptor["step_index"],
        load_factor=full_load_descriptor["load_factor"],
        free_displacements_m=full_load_vector,
        state_hash=full_load_descriptor["state_hash"],
        source_commit_sha=full_load_descriptor["source_commit_sha"],
        model_source_sha256=full_load_descriptor["model_source_sha256"],
        equilibrium_operator_binding_hash=full_load_descriptor[
            "equilibrium_operator_binding_hash"
        ],
    )
    assert validated_full_load_checkpoint.state_hash == replay[
        "direct_final_state_hash"
    ]

    rollback = receipt["failed_step_rollback_audit"]
    assert rollback["status"] == "partial"
    assert rollback["terminal_reason"] == "minimum_load_increment_exhausted"
    assert rollback["actual_linear_failed_step_rollback_contract_pass"] is True
    assert rollback["metrics"]["failed_step_count"] == 1
    assert rollback["metrics"]["failed_step_rollback_exercised"] is True
    assert rollback["metrics"]["rollback_exact"] is True
    assert rollback["metrics"]["final_load_factor"] == 0.0
    assert rollback["claims"]["failed_step_rollback_exact"] is True
    assert rollback["claims"]["full_load_linear_reference_checkpoint"] is False

    claims = receipt["claims"]
    assert claims["actual_mgt_semantic_live_load_consumed"] is True
    assert claims["full_load_linear_reference_checkpoint"] is True
    assert claims["persisted_linear_reference_restart_checkpoint"] is True
    assert claims["persisted_linear_reference_full_load_checkpoint"] is True
    assert claims["restart_replay_byte_identical"] is True
    assert claims["actual_linear_failed_step_rollback_exact"] is True
    assert claims["source_property_coverage_complete"] is False
    assert claims["raw_material_table_property_coverage_complete"] is False
    assert claims["dgn_exact_type_name_alias_contract_pass"] is True
    assert claims["dgn_alias_applied_to_linear_reference_adapter"] is False
    assert claims["dgn_alias_engineer_review_required"] is True
    assert claims["dgn_numeric_elastic_override_consumed"] is False
    assert claims["nonlinear_current_tangent"] is False
    assert claims["quadratic_convergence"] is False
    assert claims["material_state_commit_rollback"] is False
    assert claims["full_arc_length_continuation"] is False
    assert claims["production_matrix_free_krylov"] is False
    assert claims["production_rocm_hip_nonlinear_parity"] is False
    assert claims["g1_full_load_checkpoint"] is False
    assert claims["g1_full_building_closure"] is False
    assert (
        "raw_material_table_binding_incomplete_source_derived_alias_available"
        in receipt["blockers_remaining"]
    )
    assert (
        "dgn_exact_type_name_material_inheritance_engineer_review_required"
        in receipt["blockers_remaining"]
    )
    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["restart_replay_byte_identical"] is True
    assert summary["actual_linear_failed_step_rollback_exact"] is True
    assert summary["source_property_coverage_complete"] is False
    assert summary["raw_material_table_property_coverage_complete"] is False
    assert summary["dgn_exact_type_name_alias_contract_pass"] is True
    assert summary["dgn_alias_engineer_review_required"] is True


def test_checkpoint_vector_artifacts_are_hash_bound_and_finite() -> None:
    receipt = _committed_receipt()
    replay = receipt["restart_replay_audit"]
    roles = (
        ("restart_checkpoint_artifact", 0.75),
        ("full_load_checkpoint_artifact", 1.0),
    )
    for label, load_factor in roles:
        artifact = receipt[label]
        path = ROOT / artifact["artifact_path"]
        assert artifact["status"] == "ready"
        assert artifact["dtype"] == "<f8"
        assert artifact["byte_length"] == 564_480
        assert artifact["equation_count"] == 70_560
        assert artifact["checkpoint"]["load_factor"] == load_factor
        assert artifact["residual_gate_passed"] is True
        assert artifact["persisted_nonlinear_continuation_checkpoint"] is False
        assert artifact["g1_full_load_checkpoint_claim"] is False
        assert path.is_file()
        assert path.stat().st_size == artifact["byte_length"]
        assert module.file_sha256(path) == artifact["data_sha256"]
        values = np.fromfile(path, dtype="<f8")
        assert values.shape == (70_560,)
        assert np.all(np.isfinite(values))
    assert receipt["restart_checkpoint_artifact"]["data_sha256"] == replay[
        "serialized_checkpoint_data_sha256"
    ]
    assert receipt["full_load_checkpoint_artifact"]["data_sha256"] == replay[
        "direct_final_data_sha256"
    ]


def test_committed_receipt_validates_against_schema() -> None:
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_committed_receipt())


def test_check_reports_missing_receipt_without_running_actual_model(
    tmp_path: Path,
) -> None:
    ok, message = (
        module.check_g1_mgt_semantic_live_linear_newton_continuation_receipt(
            repo_root=ROOT,
            receipt_out=tmp_path / "missing.json",
            summary_out=tmp_path / "missing-summary.json",
            restart_vector_out=tmp_path / "missing-restart.f64le",
            full_load_vector_out=tmp_path / "missing-full.f64le",
        )
    )

    assert ok is False
    assert message == "g1_linear_newton_continuation_missing:receipt"
