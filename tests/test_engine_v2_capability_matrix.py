from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "validation/capabilities/engine_v2_capability_matrix.json"


def test_engine_v2_capability_matrix_keeps_implementation_and_promotion_separate() -> (
    None
):
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = payload["rows"]
    implementation_states = set(payload["allowed_implementation_states"])
    promotion_states = set(payload["allowed_promotion_states"])

    assert (
        payload["schema_version"]
        == "structural-analysis-engine-v2-capability-matrix.v1"
    )
    assert (
        payload["claim_boundary"]
        == "future_state_tracker_not_release_readiness_evidence"
    )
    assert len({row["capability_id"] for row in rows}) == len(rows)
    assert all(row["implementation_state"] in implementation_states for row in rows)
    assert all(row["promotion_state"] in promotion_states for row in rows)
    assert all(row["claim_level"] != "full_commercial" for row in rows)

    for row in rows:
        required = {
            "capability_id",
            "category",
            "phase_target",
            "implementation_state",
            "promotion_state",
            "supported_scope",
            "explicit_exclusions",
            "required_contracts",
            "verification_cases",
            "evidence_paths",
            "claim_level",
        }
        assert required.issubset(row)
        if row["promotion_state"] != "unavailable":
            assert row["evidence_paths"], row["capability_id"]
        for relative_path in row["evidence_paths"]:
            assert (REPO_ROOT / relative_path).exists(), relative_path


def test_engine_v2_adr_index_contains_every_required_contract() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    adr_index = (REPO_ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    required_contracts = {
        contract for row in payload["rows"] for contract in row["required_contracts"]
    }

    assert required_contracts == {f"ADR-{index:03d}" for index in range(1, 8)}
    for contract in sorted(required_contracts):
        assert contract in adr_index


def test_engine_v2_ai_rows_keep_shadow_memory_and_learning_claims_separate() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    proposal = rows["ai_correction_proposal_physics_gate_shadow_v1"]
    assert proposal["implementation_state"] == "implemented"
    assert proposal["promotion_state"] == "shadow"
    assert "proposal_consumed_by_solver" in proposal["explicit_exclusions"]
    assert "solver_speedup" in proposal["explicit_exclusions"]

    memory = rows["solver_approved_fixed_rank_qr_memory_v1"]
    assert memory["implementation_state"] == "implemented"
    assert memory["promotion_state"] == "contract_only"
    assert "online_parameter_learning" in memory["explicit_exclusions"]

    learning = rows["no_backprop_local_learning"]
    assert learning["implementation_state"] == "in_progress"
    assert learning["promotion_state"] == "unavailable"
    assert "online_learning_claim" in learning["explicit_exclusions"]


def test_engine_v2_hip_rows_separate_artifact_replay_and_native_parity() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    artifact = rows["hip_canonical_csr_aot_kernel_artifact_v1"]
    assert artifact["implementation_state"] == "implemented"
    assert artifact["promotion_state"] == "contract_only"
    assert "native_kernel_execution_receipt" in artifact["explicit_exclusions"]
    assert "performance_or_speedup_claim" in artifact["explicit_exclusions"]

    replay = rows["hip_canonical_csr_residual_jvp_replay_v1"]
    assert replay["implementation_state"] == "implemented"
    assert replay["promotion_state"] == "contract_only"
    assert "test_double_native_evidence_separation" in replay["supported_scope"]
    assert "global_cpu_hip_parity" in replay["explicit_exclusions"]

    native = rows["hip_native_csr_residual_jvp_parity"]
    assert native["implementation_state"] == "in_progress"
    assert native["promotion_state"] == "unavailable"
    assert "test_double_as_native_evidence" in native["explicit_exclusions"]

    assembly = rows["hip_device_linear_frame_truss_assembly_v1"]
    assert assembly["implementation_state"] == "implemented"
    assert assembly["promotion_state"] == "contract_only"
    assert "host_csr_numeric_h2d_forbidden" in assembly["supported_scope"]
    assert "unsigned_v1_forced_non_promoting" in assembly["supported_scope"]
    assert (
        "fresh_native_gpu_frame_truss_numerical_launch_parity"
        in assembly["explicit_exclusions"]
    )
    assert "device_krylov_or_preconditioner" in assembly["explicit_exclusions"]
    assert "end_to_end_on_complexity" in assembly["explicit_exclusions"]
    assert "commercial_readiness" in assembly["explicit_exclusions"]
    assert (
        assembly["claim_level"]
        == "device_assembly_contract_and_hiprtc_compile_only_fresh_native_launch_unavailable"
    )


def test_all_converged_result_ir_v1_stays_contract_only_after_local_hardware() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    capability = rows["hip_fgmres_all_converged_result_ir_v1"]
    assert payload["rows"][0]["capability_id"] == (
        "hip_fgmres_all_converged_result_ir_v1"
    )
    assert capability["implementation_state"] == "implemented"
    assert capability["promotion_state"] == "contract_only"
    assert {
        "separate_package_owned_all_converged_fixed_registry",
        "current_source_actual_local_gfx1030_all_converged_ten_result_ir_gate_passed",
        "actual_local_gfx1030_process_peak_rss_450868_kib",
        "per_case_family_aggregate_and_post_close_rss_checkpoints_measured",
        "engine_source_aggregate_sha256_41bf10b8e4fb506b5829d386ff3ad24a7ece76bcfbd4be4865e2fa8dedcaac30",
        "hardware_harness_sha256_4d43b262b57696de8e04b591fa79adad0dc06815114176319d45e25f03d67681",
        "registry_generator_sha256_b5a196b93fac4807308df56fc05096ae34f43e0a364c42d2231613e28a66ebff",
        "strict_registry_schema_full_manifest_registry_case_registration_and_all_expected_cpu_oracle_package_hash_exact_const_pinning",
        "ten_unique_model_ir_content_and_execution_plan_hashes",
        "seven_termination_source_models_preserved_two_normalized_unit_load_derivatives_one_new_normalized_serial_model",
        "nine_nontrivial_solution_cases_and_one_explicit_zero_free_rhs_edge",
        "cpu_reference_converged_solver_tolerance_and_authoritative_plan_tolerance_ten_of_ten",
        "historical_termination_registry_bytes_and_seven_result_three_diagnostic_truth_preserved",
        "process_local_exact_ten_live_case_all_converged_family_authority",
        "exact_ten_already_issued_result_ir_v2_bridge_identity_binding",
        "weak_key_family_and_aggregate_issuance_collection_without_token_reuse",
        "canonical_ten_ready_ten_solution_zero_not_issued_zero_diagnostic_ten_committed_state_aggregate",
        "package_totals_g168_e18_f103_nnz2304",
        "sixty_result_arrays_6728_bytes_and_detached_raw_payload_1648_bytes",
        "upstream_completion_export_thirty_attempts_thirty_success_zero_failure_and_actual_allocated_4288_bytes",
        "aggregate_direct_additional_device_d2h_solve_export_and_fallback_zero",
        "post_close_detached_value_and_process_local_issuance_validation",
        "bounded_registry_family_and_aggregate_replay_counts",
        "actual_wheel_exact_paths_and_source_bytes_for_eleven_fixture_json_and_three_schemas",
    }.issubset(capability["supported_scope"])
    assert {
        "registry_validation_cpu_reference_replay_zero",
        "actual_external_gfx1100_result_ir",
        "multiarchitecture_or_same_process_two_isa_result_ir",
        "process_wide_rocm_activity_or_host_transfer_completeness",
        "broad_iteration_host_copy_zero",
        "gpu_native_reaction_member_force_or_energy_recovery",
        "gpu_crash_reset_or_cross_process_abandoned_owner_recovery",
        "standalone_detached_or_serialized_provenance_authenticity",
        "persistent_external_hardware_log",
        "reproducible_wheel_build",
        "signed_evidence",
        "promotion_eligibility",
        "end_to_end_o_n",
        "performance_speedup",
        "nonlinear_analysis",
        "dynamic_analysis",
        "shell_elements",
        "solid_elements",
        "contact_analysis",
        "commercial_readiness",
    }.issubset(capability["explicit_exclusions"])
    assert capability["required_contracts"] == [
        "ADR-001",
        "ADR-002",
        "ADR-003",
        "ADR-004",
        "ADR-006",
        "ADR-007",
    ]
    assert {
        "strict_registry_schema_raw_bytes_and_canonical_content_hash",
        "strict_registry_schema_full_manifest_registry_case_registration_model_bytes_and_all_expected_cpu_oracle_package_hashes_exact_const",
        "all_cpu_converged_and_dual_tolerance_ten_of_ten",
        "historical_termination_registry_raw_hash_and_public_slot_contract_frozen",
        "family_canonical_order_exact_live_identity_and_double_capture",
        "family_and_aggregate_weak_key_issuance_garbage_collection_and_token_nonreuse",
        "aggregate_ten_ready_zero_not_issued_zero_diagnostic_exact_totals",
        "post_close_validation_without_live_family_or_case_replay",
        "aggregate_module_direct_ast_native_device_builder_and_runtime_entrypoint_absence_cpu_registry_replay_allowed",
        "family_factory_one_full_registry_replay_and_one_post_final_raw_digest_refresh",
        "public_family_result_and_receipt_one_fresh_full_registry_replay_each",
        "aggregate_factory_one_entry_full_registry_replay_three_live_recaptures_three_fast_raw_refreshes_and_no_detached_self_validator_full_replay",
        "public_aggregate_result_and_receipt_one_fresh_full_registry_replay_each",
        "required_hardware_flow_four_full_registry_replays_forty_cpu_solves_forty_dense_oracles_and_four_fast_raw_refreshes",
        "hardware_harness_static_full_replay_bound_and_actual_gate",
        "actual_wheel_build_exact_archive_paths_and_source_bytes_for_eleven_fixture_json_and_three_schemas",
        "registry_contract_16_functions_27_collected_cases_passed",
        "family_contract_9_functions_10_collected_cases_passed",
        "aggregate_contract_10_functions_15_collected_cases_passed",
        "public_api_and_actual_wheel_tests_5_passed",
        "combined_contract_scope_57_passed_within_five_file_crosscheck",
        "capability_matrix_tests_11_passed_in_0_31_seconds",
        "current_source_contract_and_capability_five_file_crosscheck_68_passed_in_259_34_seconds",
        "final_nonrelease_wheel_1401602_bytes_sha256_d9deea5512465f5fea353fffa4cab036eb03dff91fbbedf78c8a98bc560efc00_engine886_assembly730_contracts63_elements10_schema5_fixture11_registry10_replay",
        "sequential_wheel_rebuilds_1401602_bytes_264_members_zero_content_diffs_five_dist_info_timestamp_diffs_sha256_f704a687e0ca13233c2fb379a9b71714888c6e0c192b120f3fa2cae82fa08838_and_18bcb7f7f405ceb5be75474e0926bcf906bc35ad274d9946faa7d09ba4da0ba0",
        "hardware_harness_two_tests_collected",
        "current_root_host_dev_kfd_present_gfx1030_probe_ready_hip_native_fallback_false",
        "separate_restricted_namespace_dev_kfd_absent_no_durable_hardware_observation",
        "separate_restricted_namespace_nonrequired_hardware_static_one_passed_actual_one_skipped_in_1_74_seconds_without_real_gfx_agent",
        "separate_restricted_namespace_required_hardware_static_one_passed_actual_one_failed_in_1_76_seconds_no_real_gfx_agent_detected",
        "actual_local_gfx1030_ten_result_ir_bridge_family_aggregate_post_close_gate_1_passed_in_1087_52_seconds_without_cpu_fallback",
        "actual_local_gfx1030_process_peak_rss_450868_kib_post_close_current_rss_433188_kib",
        "rss_baseline_and_ten_case_family_aggregate_post_close_checkpoints_measured",
        "engine_source_aggregate_and_harness_hashes_identical_before_after_actual_gate",
        "first_actual_attempt_failed_rotated_axis_terminal_metric_near_zero_absolute_scale_then_second_failed_four_span_same_boundary",
        "three_cancellation_sensitive_slots_normalized_to_unit_load_without_tolerance_relaxation",
        "normalized_rotated_four_span_five_span_strict_case_parity_and_result_ir_ready_verified",
    }.issubset(capability["verification_cases"])
    assert capability["claim_level"] == (
        "separate_all_converged_registry_exact_ten_result_ir_and_actual_local_"
        "gfx1030_gate_observed_contract_only_unsigned_nonpersistent_detached_"
        "non_provenance_nonpromoting"
    )


def test_fp64_csr_residual_roundoff_contract_stays_nonpromoting() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    capability = rows["fp64_csr_residual_roundoff_backward_error_v1"]
    assert payload["rows"][1]["capability_id"] == (
        "fp64_csr_residual_roundoff_backward_error_v1"
    )
    assert capability["implementation_state"] == "implemented"
    assert capability["promotion_state"] == "contract_only"
    assert {
        "backend_neutral_execution_plan_v2_bound_value_contract",
        "componentwise_abs_delta_r_bounded_by_solution_transport_plus_two_path_roundoff",
        "caller_absolute_or_relative_tolerance_not_accepted",
        "componentwise_backward_error_for_reference_and_candidate",
        "detached_fgmres_cpu_vs_candidate_and_candidate_vs_independent_fsum_replay_adapter",
        "legacy_model_case_parity_v1_solution_and_residual_gate_not_relaxed",
        "sparse_o_nnz_plus_n_narrow_contract_without_dense_matrix_or_solve",
        "actual_wheel_contains_contract_module_and_strict_schema_exact_source_bytes",
        "actual_local_gfx1030_original_scale_three_case_observation_passed",
        "actual_local_gfx1030_completion_export_three_d2h_and_fallback_zero",
        "core_schema_adapter_harness_aggregate_sha256_d30dd5e67d1b7cc994bb2a050689eda79d02a6b93d2af7418a51f51671c176f6",
    }.issubset(capability["supported_scope"])
    assert {
        "model_case_parity_v1_terminal_or_history_metric_rule_replacement",
        "high_load_result_ir_or_aggregate_authority",
        "core_receipt_actual_backend_or_hardware_provenance",
        "formal_machine_checked_kernel_instruction_error_proof",
        "actual_external_gfx1100",
        "persistent_or_signed_hardware_evidence",
        "end_to_end_o_n",
        "performance_speedup",
        "promotion_eligibility",
        "commercial_readiness",
    }.issubset(capability["explicit_exclusions"])
    assert {
        "power_of_two_load_scaling_2_pow_minus_20_one_and_2_pow_20_preserves_bound_and_ratios",
        "fraction_exact_add_multiply_distance_and_gamma_outward_primitive_checks",
        "detached_adapter_accepts_high_scale_roundoff_while_legacy_v1_remains_fail_closed",
        "focused_contract_adapter_and_actual_wheel_20_passed_in_6_85_seconds",
        "legacy_model_case_parity_v1_24_passed_in_1_83_seconds",
        "current_contract_legacy_and_capability_three_file_crosscheck_56_passed_in_7_06_seconds",
        "current_seven_file_adjacent_crosscheck_116_passed_in_264_39_seconds",
        "single_nonrelease_wheel_1411419_bytes_266_members_sha256_1e61eac1fddf52329d1daa3b789e1f59b838054aff87b908d7adfed19ce56e28",
        "isolated_wheel_public_symbols_engine_903_assembly_732_contracts_78_elements_10",
        "actual_local_gfx1030_high_load_three_case_gate_1_passed_in_218_17_seconds",
        "actual_local_gfx1030_process_peak_rss_428820_kib",
        "rotated_cpu_hip_ratio_0_021012885183208055_and_hip_replay_ratio_0_03547771831820348",
        "four_and_five_span_max_ratio_0_0029520720720720497",
        "actual_local_gfx1030_maximum_hip_componentwise_backward_error_1_2238707852511078e_minus_15",
        "source_aggregate_identical_before_and_after_actual_gate",
    }.issubset(capability["verification_cases"])
    assert capability["claim_level"] == (
        "backend_neutral_scale_aware_fp64_csr_residual_bound_and_unsigned_local_"
        "gfx1030_high_load_observation_contract_only_nonpromoting"
    )


def test_fp64_csr_normwise_terminal_metric_v2_stays_additive_and_nonpromoting() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    capability = rows["fp64_csr_residual_normwise_terminal_metric_parity_v2"]
    assert payload["rows"][2]["capability_id"] == (
        "fp64_csr_residual_normwise_terminal_metric_parity_v2"
    )
    assert capability["implementation_state"] == "implemented"
    assert capability["promotion_state"] == "contract_only"
    assert {
        "full_replay_of_fp64_csr_componentwise_roundoff_receipt",
        "outward_l2_linf_and_scaled_linf_exact_vector_norm_intervals",
        "reverse_triangle_projection_of_componentwise_bound_to_three_norm_budgets",
        "validated_cpu_stable_l2_and_hip_gpu_tree_l2_record_path_binding",
        "record_to_exact_norm_interval_evaluation_error_in_total_budget",
        "caller_absolute_or_relative_tolerance_not_accepted",
        "legacy_model_case_parity_v1_wire_solution_residual_terminal_and_history_gates_preserved",
        "subnormal_nonzero_multiply_or_divide_upper_bound_raised_to_smallest_subnormal",
        "actual_local_gfx1030_original_scale_three_case_terminal_metric_observation_passed",
        "current_source_aggregate_sha256_f88ab16874385d6a48dde6a17b26effda7fc93a25756f76b81b1ba7ad9366dc3",
    }.issubset(capability["supported_scope"])
    assert {
        "legacy_model_case_parity_v1_receipt_replacement_or_migration",
        "restart_history_metric_v2",
        "high_load_result_ir_or_family_aggregate_authority",
        "core_receipt_actual_backend_or_hardware_provenance",
        "formal_machine_checked_reverse_triangle_or_kernel_instruction_error_proof",
        "actual_external_gfx1100",
        "persistent_or_signed_hardware_evidence",
        "end_to_end_o_n",
        "performance_speedup",
        "promotion_eligibility",
        "commercial_readiness",
    }.issubset(capability["explicit_exclusions"])
    assert {
        "exact_fraction_sum_of_squares_enclosed_by_outward_l2_intervals",
        "terminal_difference_above_legacy_absolute_floor_accepted_only_by_derived_budget",
        "candidate_gpu_tree_record_relabel_rejected",
        "coherent_receipt_rehash_source_splice_and_forged_solution_child_rejected",
        "subnormal_underflowing_nonzero_product_outward_upper_primitive_check",
        "focused_normwise_terminal_metric_contract_14_passed_in_9_53_seconds",
        "componentwise_and_normwise_combined_34_passed_in_14_57_seconds",
        "normwise_componentwise_legacy_model_case_and_capability_crosscheck_71_passed_in_15_06_seconds",
        "terminal_observer_all_converged_registry_family_result_ir_public_adjacent_crosscheck_140_passed_in_395_82_seconds",
        "single_nonrelease_wheel_1427672_bytes_270_members_sha256_da8eeef8160cdd4dfdd0f83250162b603ae3a4e37453ecd5c65dadcd28b355ae",
        "isolated_wheel_public_symbols_engine_932_assembly_746_contracts_93_elements_10",
        "actual_local_gfx1030_high_load_three_case_gate_1_passed_in_226_25_seconds",
        "actual_local_gfx1030_process_peak_rss_429808_kib",
        "four_span_max_ratio_0_002952072072072049",
        "source_aggregate_identical_before_and_after_actual_gate",
    }.issubset(capability["verification_cases"])
    assert capability["claim_level"] == (
        "backend_neutral_normwise_projection_and_detached_terminal_metric_v2_with_"
        "unsigned_local_gfx1030_high_load_observation_contract_only_nonpromoting"
    )


def test_high_load_model_case_v2_result_ir_v3_stays_scoped_and_nonpromoting() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    capability = rows["hip_fgmres_high_load_model_case_parity_v2_result_ir_v3"]
    assert payload["rows"][3]["capability_id"] == (
        "hip_fgmres_high_load_model_case_parity_v2_result_ir_v3"
    )
    assert capability["implementation_state"] == "implemented"
    assert capability["promotion_state"] == "contract_only"
    assert {
        "process_local_high_load_model_case_parity_v2_actual_hip_authority",
        "exactly_one_populated_terminal_restart_row",
        "explicit_restart_history_evidence_disposition",
        "roundoff_aware_two_stage_exported_hip_to_independent_fsum_to_result_ir_plan_residual_chain",
        "retained_structurally_valid_result_ir_v2_marked_not_ready_without_fixed_policy_relaxation",
        "fixed_physics_witness_sparse_reaction_member_force_energy_and_state_lineage_replay",
        "actual_local_gfx1030_original_high_load_rotated_four_span_and_five_span_gate_passed",
        "actual_local_gfx1030_recurrence_d2h_zero_completion_d2h_exact_three_and_fallback_zero",
        "current_source_aggregate_sha256_9b902eb0b70102875b60efff4adbffc70420aeff26d7eb854988a080dea285f8",
        "actual_dirty_nonrelease_wheel_exact_new_module_and_schema_bytes_and_isolated_public_exports",
    }.issubset(capability["supported_scope"])
    assert {
        "general_multi_restart_history_v2",
        "per_restart_checkpoint_solution_and_true_residual_vector_export_v2",
        "estimated_residual_roundoff_error_model",
        "solution_update_roundoff_error_model",
        "retained_base_result_ir_v2_ready_under_fixed_allclose_policy",
        "high_load_compatibility_registry_or_family_aggregate",
        "actual_external_gfx1100",
        "standalone_detached_or_serialized_provenance_authenticity",
        "reproducible_wheel_build",
        "signed_evidence",
        "broad_iteration_host_copy_zero",
        "end_to_end_o_n",
        "performance_speedup",
        "promotion_eligibility",
        "commercial_readiness",
    }.issubset(capability["explicit_exclusions"])
    assert capability["required_contracts"] == [
        "ADR-001",
        "ADR-002",
        "ADR-003",
        "ADR-004",
        "ADR-006",
        "ADR-007",
    ]
    assert {
        "model_case_v2_multirow_alias_scalar_slot_and_schema_tamper_fail_closed",
        "legacy_model_case_v1_schema_and_fixed_tolerance_policy_frozen",
        "result_ir_v2_fixed_residual_sign_gate_rejects_original_high_load_synthetic_case",
        "result_ir_v3_two_componentwise_fp64_csr_residual_receipts_validate_same_case",
        "result_ir_v3_core_four_passed_in_8_26_seconds_and_complete_public_package_six_passed_in_11_92_seconds",
        "current_result_ir_v2_model_case_v2_result_ir_v3_and_capability_crosscheck_fifty_six_passed_in_45_09_seconds",
        "adjacent_roundoff_model_case_result_ir_all_converged_diagnostic_and_capability_222_passed_in_739_43_seconds",
        "single_dirty_nonrelease_wheel_1462632_bytes_287_members_sha256_5e55cfc00386d1c2a3ec6d2684a723e9eee661f904e10b01e469afba94c2971e",
        "actual_local_gfx1030_high_load_three_case_gate_one_passed_in_430_66_seconds",
        "actual_local_gfx1030_wall_time_431_29_seconds_and_process_peak_rss_430796_kib",
        "source_aggregate_identical_before_and_after_actual_gate",
    }.issubset(capability["verification_cases"])
    assert capability["claim_level"] == (
        "single_terminal_restart_high_load_actual_local_gfx1030_model_case_v2_and_"
        "roundoff_aware_result_ir_v3_process_local_contract_only_unsigned_"
        "nonpersistent_nonpromoting"
    )


def test_fgmres_registry_family_v2_and_external_signature_claims_stay_bounded() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    family_disposition = rows["hip_fgmres_model_family_result_ir_disposition_v1"]
    assert payload["rows"][5]["capability_id"] == (
        "hip_fgmres_model_family_result_ir_disposition_v1"
    )
    assert family_disposition["implementation_state"] == "implemented"
    assert family_disposition["promotion_state"] == "contract_only"
    assert {
        "exact_package_registry_gfx1030_canonical_ten_slot_disposition",
        "audited_v0242_family_receipt_and_v0243_result_ir_bridge_cross_binding",
        "seven_converged_result_ir_v2_ready_and_three_intentional_max_iterations_not_issued",
        "nonconverged_source_solution_ready_result_ir_v2_fail_closed",
        "non_recycled_weak_registry_exact_live_model_case_identity_token_binding",
        "factory_retains_no_live_audited_result_transfer_or_ordinal_context",
        "post_close_detached_audited_receipt_and_seven_bridge_validation",
        "ready_package_totals_g90_e8_f43_nnz1116",
        "ready_six_array_payload_3336_bytes_and_detached_raw_payload_688_bytes",
        "aggregate_projection_additional_device_operation_d2h_solve_export_and_fallback_zero",
        "current_source_actual_local_gfx1030_integrated_ten_slot_seven_ready_three_not_issued_post_close_validated_without_cpu_fallback",
    }.issubset(family_disposition["supported_scope"])
    assert {
        "exact_package_all_ten_result_ir_v2_ready",
        "all_ten_solution_ready",
        "nonconverged_partial_iterate_diagnostic_ir",
        "all_converged_fixture_registry",
        "registry_validation_cpu_reference_replay_zero",
        "actual_external_gfx1100_result_ir",
        "broad_iteration_host_copy_zero",
        "standalone_detached_or_serialized_provenance_authenticity",
        "end_to_end_o_n",
        "performance_speedup",
        "commercial_readiness",
    }.issubset(family_disposition["explicit_exclusions"])
    assert {
        "canonical_reversed_seven_ready_three_not_issued_disposition",
        "each_registered_nonconverged_source_rejected_by_result_ir_v2_bridge",
        "forced_valid_nonconverged_result_ir_injection_forbidden_for_all_three_slots",
        "missing_duplicate_non_tuple_and_foreign_bridge_rejection",
        "coherent_rehash_and_bridge_issuance_transplant_rejection",
        "source_change_during_factory_rejected_before_issuance",
        "aggregate_exact_clone_source_receipt_swap_and_issuance_transplant_rejection",
        "post_close_validation_does_not_replay_live_audited_contexts",
        "serially_identical_cross_run_bridge_splice_rejection",
        "final_live_source_capture_after_second_composition",
        "schema_alone_canonical_ten_slot_truth_table_rejection",
        "registry_validation_cpu_reference_replay_zero_explicitly_false",
        "focused_disposition_contract_tests_23_passed",
        "public_api_and_capability_tests_19_passed",
        "hardware_harness_collection_one_test_collected",
        "current_source_actual_local_gfx1030_integrated_ten_slot_gate_1_passed_in_7820_35_seconds_without_cpu_fallback",
    }.issubset(family_disposition["verification_cases"])
    assert family_disposition["claim_level"] == (
        "current_source_actual_local_gfx1030_integrated_ten_slot_seven_result_ir_"
        "v2_ready_three_nonconverged_not_issued_post_close_validated_contract_only_"
        "unsigned_nonpersistent_detached_"
        "non_provenance_nonpromoting"
    )

    result_ir = rows["hip_fgmres_result_ir_v2"]
    assert payload["rows"][6]["capability_id"] == "hip_fgmres_result_ir_v2"
    assert result_ir["implementation_state"] == "implemented"
    assert result_ir["promotion_state"] == "contract_only"
    assert set(result_ir["supported_scope"]) == {
        "retained_converged_hip_single_model_case_live_authority_factory",
        "public_generic_builder_result_ir_ready_false_private_bridge_exact_object_mint_true",
        "scoped_result_ir_v2_result_ir_ready_true_upstream_false_claims_unchanged",
        "exact_completion_export_solution_and_true_residual_raw_byte_binding",
        "canonical_full_displacement_free_solution_and_constrained_positive_zero",
        "execution_plan_v2_sparse_full_internal_minus_external_residual_replay",
        "free_reaction_exact_positive_zero",
        "reaction_local_member_force_element_global_external_and_residual_work_energy_recovery",
        "trial_to_committed_state_ir_lineage",
        "descriptor_only_result_ir_v2_manifest_without_json_array_values",
        "live_source_authority_checked_only_during_factory",
        "detached_post_close_value_seal_plan_state_and_physics_validation",
        "factory_direct_call_surface_retained_source_additional_device_d2h_solve_export_and_fallback_zero_contract",
        "upstream_completion_export_existing_three_blocking_d2h_preserved",
        "materialization_o_g_plus_nnz_plus_144e",
        "result_ir_six_raw_arrays_24g_plus_104e_plus_8f_bytes",
        "detached_source_seal_additional_raw_solution_and_residual_16f_bytes",
        "non_recycled_weak_registry_exact_model_case_identity_token_without_live_context_retention",
        "historical_pre_identity_token_patch_local_gfx1030_single_model_case_result_ir_gate_without_cpu_fallback",
        "current_source_actual_local_gfx1030_integrated_ten_slot_seven_converged_result_ir_v2_bridges_post_close_validated_without_cpu_fallback",
        "strict_unsigned_contract_only_historical_local_single_case_non_promoting",
    }
    assert set(result_ir["explicit_exclusions"]) == {
        "nonconverged_or_failed_terminal_result_ir",
        "exact_package_all_ten_result_ir_integration",
        "actual_external_gfx1100_result_ir",
        "process_wide_rocm_activity_completeness",
        "transitive_or_process_wide_projection_operation_instrumentation",
        "broad_iteration_host_copy_zero",
        "gpu_reaction_member_force_or_energy_recovery",
        "standalone_detached_or_serialized_provenance_authenticity",
        "hostile_same_process_private_mint_or_object_identity_attack_resistance",
        "signed_evidence",
        "promotion_eligibility",
        "commercial_readiness",
        "end_to_end_o_n",
        "performance_speedup",
        "nonlinear_analysis",
        "dynamic_analysis",
        "shell_elements",
        "solid_elements",
        "contact_analysis",
    }
    assert result_ir["required_contracts"] == [
        "ADR-001",
        "ADR-002",
        "ADR-003",
        "ADR-004",
        "ADR-006",
        "ADR-007",
    ]
    assert set(result_ir["verification_cases"]) == {
        "generic_descriptor_only_result_ir_v2_contract_and_schema",
        "public_generic_ready_false_private_bridge_mint_true_and_coherent_rehash_replace_direct_manifest_forgery_rejection",
        "exact_execution_plan_v2_trial_committed_state_physics_replay",
        "six_immutable_bytes_backed_f8_arrays_and_signed_zero_canonicalization",
        "constrained_zero_residual_sign_reaction_member_force_and_energy_identity",
        "free_reaction_exact_positive_zero_coherent_1_25e_minus_8_rehash_attack_rejection",
        "raw_hip_payload_hash_kept_separate_from_canonical_result_array_hash",
        "live_factory_double_capture_and_authority_drift_rejection",
        "non_recycled_identity_token_and_unissued_exact_clone_rejection",
        "detached_post_close_bridge_validation_without_resolve_or_export",
        "factory_direct_call_surface_zero_contract_not_transitive_or_process_wide_instrumentation",
        "manifest_unknown_property_exact_type_numeric_alias_mutable_array_and_rehash_forgery_rejection",
        "materialization_and_raw_array_formula_contract",
        "exact_clone_coherent_rehash_and_registry_transplant_final_issuance_rejection",
        "generic_contract_tests_16_passed",
        "bridge_contract_tests_13_passed",
        "focused_generic_and_bridge_contract_tests_29_passed",
        "public_api_tests_3_passed",
        "capability_matrix_tests_9_passed",
        "combined_result_ir_public_capability_and_model_case_tests_65_passed",
        "model_case_downstream_authority_tests_24_passed",
        "current_source_nonrequired_hardware_gate_1_skipped_without_real_gfx_agent",
        "current_source_required_hardware_gate_1_failed_without_real_gfx_agent",
        "fresh_outer_source_authority_wrapper_hardware_lifecycle_verified_on_pre_identity_token_patch_source",
        "historical_pre_identity_token_patch_gfx1030_single_model_case_result_ir_gate_1_passed_in_169_10_seconds_without_cpu_fallback",
        "current_source_actual_local_gfx1030_integrated_ten_slot_seven_result_ir_v2_bridges_post_close_gate_1_passed_in_7820_35_seconds_without_cpu_fallback",
    }
    assert result_ir["evidence_paths"] == [
        "docs/engine-v2-hip-fgmres-result-ir-v2.md",
        "src/structural_analysis/engine_v2/contracts/result_ir_v2.py",
        "src/structural_analysis/schemas/result_ir_v2.schema.json",
        "src/structural_analysis/engine_v2/assembly_backend/fgmres_result_ir_v2.py",
        "tests/test_engine_v2_result_ir_v2.py",
        "tests/test_engine_v2_hip_fgmres_result_ir_v2.py",
        "tests/test_engine_v2_result_ir_v2_public_api.py",
        "tests/test_engine_v2_hip_fgmres_model_case_parity_hardware_v1.py",
        "tests/test_engine_v2_capability_matrix.py",
    ]
    assert result_ir["claim_level"] == (
        "current_source_actual_local_gfx1030_integrated_ten_slot_seven_converged_"
        "sparse_result_ir_v2_bridges_post_close_validated_contract_only_unsigned_"
        "nonpersistent_detached_non_provenance_nonpromoting"
    )

    audited_family = rows["hip_fgmres_model_family_audited_parity_v2"]
    assert payload["rows"][7]["capability_id"] == (
        "hip_fgmres_model_family_audited_parity_v2"
    )
    assert audited_family["implementation_state"] == "implemented"
    assert audited_family["promotion_state"] == "contract_only"
    assert {
        "retained_model_case_parity_host_transfer_and_launch_fence_authority_replay",
        "same_completion_export_object_identity_replayed_by_source_composition",
        "transfer_and_ordinal_canonical_sealed_global_completion_plan_abi_kernel_schedule_device_lineage_cross_binding",
        "detached_fixed_package_recurrence_abi_combined_abi_kernel_source_canonical_checkpoint_and_program_descriptor_recalculation",
        "contract_expected_per_slot_bound_runtime_recurrence_copy_api_attempt_zero",
        "contract_expected_ten_slot_total_thirty_blocking_d2h_and_4408_bytes",
        "contract_expected_ten_slot_total_1230_launch_attempts_and_successes",
        "historical_pre_identity_token_patch_local_gfx1030_ten_slot_single_live_aggregate_triple_composition",
        "current_source_actual_local_gfx1030_integrated_ten_slot_single_live_aggregate_triple_composition_without_cpu_fallback",
        "synthetic_retained_authority_per_slot_owned_eight_memsets_full_launch_program_and_three_fences",
        "synthetic_retained_authority_ten_slot_total_eighty_memsets_and_thirty_fences",
        "synthetic_retained_authority_owned_rtc_memset_launch_and_fence_rejected_ambiguous_and_in_flight_counts_zero",
        "composition_factory_direct_call_surface_reuses_retained_authorities_without_solve_export_seal_or_native_entrypoint",
        "strict_process_local_unsigned_non_promoting_receipt_schema",
    }.issubset(audited_family["supported_scope"])
    assert {
        "actual_external_gfx1100_ten_slot_audit",
        "process_wide_rocm_activity_host_transfer_or_launch_completeness",
        "pre_window_dma_setup_teardown_or_between_case_transfer_zero",
        "whole_process_additional_device_solve_or_export_absence",
        "hostile_same_process_mutation_or_interposition_resistance",
        "device_kernel_semantic_execution_success_from_ordinal_chain",
        "device_content_or_numerical_outcome_from_ordinal_chain",
        "iteration_host_copy_zero",
        "standalone_receipt_provenance_authenticity_without_retained_authorities_or_signature",
        "result_ir",
        "reaction_member_force_recovery_or_energy",
        "end_to_end_o_n",
        "commercial_readiness",
    }.issubset(audited_family["explicit_exclusions"])
    assert {
        "synthetic_exact_ten_slot_three_authority_composition",
        "actual_v041_counter_type_shape_used_by_synthetic_rejected_ambiguous_and_in_flight_zero",
        "reversed_ordinal_input_canonical_registry_order",
        "unsealed_poisoned_and_closed_retained_lifecycle",
        "missing_duplicate_foreign_and_wrong_expected_context_rejection",
        "serially_identical_cross_run_retained_identity_rejection",
        "canonical_sealed_abi_schedule_projection_and_device_lineage_splice_rejection",
        "retained_context_result_source_registry_and_duplicate_receipt_replay_rejection",
        "detached_claim_order_triple_hash_counter_logical_schedule_zero_launch_safe_integer_and_exact_type_forgery_rejection",
        "detached_fixed_package_abi_source_schedule_and_program_descriptor_forgery_rejection",
        "factory_exact_direct_call_surface_ast_and_export_seal_runtime_purity_guard",
        "valid_payload_all_object_levels_strict_schema",
        "public_export_and_package_schema_resource_integrity",
        "hardware_test_loop_integration_contract_without_duplicate_solve_or_export",
        "historical_pre_identity_token_patch_gfx1030_ten_slot_gate_1_passed_in_3171_31_seconds_without_cpu_fallback",
        "current_source_actual_local_gfx1030_integrated_ten_slot_triple_composition_gate_1_passed_in_7820_35_seconds_without_cpu_fallback",
    }.issubset(audited_family["verification_cases"])
    assert audited_family["claim_level"] == (
        "current_source_actual_local_gfx1030_integrated_ten_slot_retained_parity_"
        "transfer_and_owned_rtc_operation_order_triple_composition_contract_only_"
        "unsigned_nonpersistent_detached_non_provenance_nonpromoting"
    )

    ordinal_audit = rows["hip_fgmres_recurrence_launch_fence_rolling_ordinal_audit_v1"]
    assert payload["rows"][8]["capability_id"] == (
        "hip_fgmres_recurrence_launch_fence_rolling_ordinal_audit_v1"
    )
    assert ordinal_audit["implementation_state"] == "implemented"
    assert ordinal_audit["promotion_state"] == "contract_only"
    assert {
        "exact_process_local_fgmres_v2_kernel_ledger",
        "native_memset_launch_and_stream_fence_attempt_recorded_before_call_on_receipt_eligible_path",
        "success_rejected_ambiguous_and_in_flight_disposition_accounting_on_receipt_eligible_path",
        "fixed_eight_prelaunch_memsets_and_full_recurrence_descriptor_replay",
        "canonical_sealed_and_global_terminal_fence_order",
        "constant_space_fixed_binary_sha256_rolling_predecessor_chain",
        "completion_export_not_opened_at_terminal_seal_boundary",
        "audit_fault_poison_forbids_receipt_without_blocking_valid_solver_native_lifecycle",
        "actual_local_gfx1030_single_case_owned_eight_memsets_full_launch_chain_and_three_fences",
    }.issubset(ordinal_audit["supported_scope"])
    assert {
        "process_wide_rocm_launch_completeness",
        "all_device_operations_observed",
        "device_kernel_semantic_execution_success",
        "device_content_terminal_outcome_solution_or_numerical_parity",
        "iteration_host_copy_zero",
        "persistent_hardware_receipt_or_external_execution_log",
        "actual_external_gfx1100_receipt",
        "end_to_end_o_n",
        "performance_speedup",
        "commercial_readiness",
    }.issubset(ordinal_audit["explicit_exclusions"])
    assert ordinal_audit["claim_level"] == (
        "exact_process_local_owned_rtc_operation_order_replayed_actual_local_gfx1030_"
        "single_case_working_session_nonpersistent_non_promoting"
    )
    assert (
        "tests/test_engine_v2_hip_fgmres_iteration_host_transfer_audit_hardware_v1.py"
        in ordinal_audit["evidence_paths"]
    )
    family_transfer = rows["hip_fgmres_model_family_host_transfer_audit_v1"]
    assert payload["rows"][9]["capability_id"] == (
        "hip_fgmres_model_family_host_transfer_audit_v1"
    )
    assert family_transfer["implementation_state"] == "implemented"
    assert family_transfer["promotion_state"] == "contract_only"
    assert {
        "exact_package_registry_gfx1030_ten_slot_family_v2_binding",
        "source_family_and_composition_registry_identity_atomic_binding",
        "ten_same_process_audit_authorities_captured_while_exported",
        "case_parity_and_audit_same_completion_export_object_identity",
        "completion_global_recurrence_kernel_device_and_dimension_cross_binding",
        "per_slot_bound_runtime_recurrence_copy_api_attempt_zero",
        "per_slot_post_fence_exact_three_blocking_d2h",
        "ten_slot_total_thirty_blocking_d2h_and_4408_bytes",
        "composition_factory_reuses_retained_export_identity_only",
        "detached_context_uniqueness_and_architecture_device_kernel_consistency",
        "actual_local_gfx1030_ten_slot_family_parity_and_bound_runtime_transfer_audit_composed",
        "strict_non_promoting_structural_receipt_schema",
    }.issubset(family_transfer["supported_scope"])
    assert {
        "actual_external_gfx1100_ten_slot_audit",
        "persistent_hardware_receipt_or_external_execution_log",
        "process_wide_rocm_activity_or_host_transfer_zero",
        "pre_window_async_copy_completion_or_device_dma_activity_zero",
        "whole_process_additional_device_solve_or_export_absence",
        "iteration_host_copy_zero",
        "standalone_receipt_provenance_authenticity_without_retained_expected_context_and_family_case_source_authorities_or_signature",
        "signed_evidence",
        "result_ir",
        "end_to_end_o_n",
        "commercial_readiness",
    }.issubset(family_transfer["explicit_exclusions"])
    assert {
        "synthetic_exact_ten_slot_exported_authority_capture",
        "reversed_context_input_canonical_registry_order",
        "missing_duplicate_wrong_order_and_explicit_foreign_expected_context_rejection",
        "source_family_composition_registry_cross_snapshot_rejection",
        "same_export_object_identity_and_lineage_forgery_rejection",
        "detached_claim_order_pair_hash_exact_type_duplicate_context_and_device_kernel_forgery_rejection",
        "valid_payload_all_object_levels_strict_schema",
        "failure_complete_hardware_resource_cleanup",
        "public_export_and_package_schema_resource_integrity",
        "actual_gfx1030_ten_slot_composed_hardware_receipt_one_passed_in_2004_37_seconds",
    }.issubset(family_transfer["verification_cases"])
    assert family_transfer["claim_level"] == (
        "actual_local_gfx1030_ten_slot_family_parity_and_bound_runtime_"
        "transfer_audit_composed_working_session_nonpersistent_non_promoting"
    )

    transfer_audit = rows["hip_fgmres_bound_runtime_recurrence_host_transfer_audit_v1"]
    assert payload["rows"][10]["capability_id"] == (
        "hip_fgmres_bound_runtime_recurrence_host_transfer_audit_v1"
    )
    assert transfer_audit["implementation_state"] == "implemented"
    assert transfer_audit["promotion_state"] == "contract_only"
    assert {
        "monotonic_process_local_copy_attempt_success_failure_and_byte_accounting",
        "bound_runtime_h2d_async_d2h_async_and_blocking_d2h_paths",
        "failed_or_raised_copy_accounted_before_native_call",
        "canonical_context_ready_before_enqueue_to_global_terminal_fence_window",
        "recurrence_program_bound_runtime_copy_attempt_delta_zero",
        "post_fence_completion_export_exact_three_blocking_d2h",
        "strict_non_promoting_receipt_schema_and_public_result_binding",
        "actual_local_gfx1030_single_case_zero_copy_window_and_three_d2h_360_bytes",
    }.issubset(transfer_audit["supported_scope"])
    assert {
        "process_wide_rocm_activity_trace",
        "loaded_runtime_cdll_compatibility_view",
        "fresh_loaded_runtime_bind_calls",
        "direct_ctypes_dlsym_or_c_extension_calls",
        "third_party_rocm_or_external_dma",
        "pre_window_async_copy_completion_or_device_dma_activity_zero",
        "hostile_same_process_monkeypatch_or_interposition",
        "synchronization_zero",
        "full_solver_setup_transfer_zero",
        "iteration_host_copy_zero",
        "standalone_receipt_provenance_authenticity_without_expected_context_or_signature",
        "actual_gfx1030_ten_case_family_receipt",
        "actual_external_gfx1100_receipt",
        "commercial_readiness",
    }.issubset(transfer_audit["explicit_exclusions"])
    assert {
        "bound_runtime_all_three_copy_paths_success_return_error_and_raised_exception_accounting",
        "atomic_start_boundary_reentrant_enqueue_rejection",
        "test_double_canonical_to_global_fence_zero_copy_and_exact_export",
        "window_copy_attempt_fail_closed",
        "detached_broad_claim_rehash_rejection",
        "valid_payload_top_level_and_nested_strict_schema_unknown_property_rejection",
        "exact_numeric_and_nested_string_type_alias_rejection",
        "completion_export_backend_and_binding_forgery_rejection",
        "cached_result_exact_input_identity_and_zero_recopy",
        "package_copy_binding_and_private_invocation_ast_heuristic_allowlist",
        "public_export_and_package_schema_resource_integrity",
        "working_session_actual_gfx1030_single_case_one_passed_in_36_34_seconds",
    }.issubset(transfer_audit["verification_cases"])
    assert transfer_audit["claim_level"] == (
        "exact_bound_runtime_canonical_to_global_fence_copy_attempt_zero_plus_"
        "fenced_three_d2h_export_actual_local_gfx1030_single_case_non_promoting"
    )

    reviewer_bootstrap = rows["hip_fgmres_reviewer_root_bootstrap_new_trust_genesis_v1"]
    assert reviewer_bootstrap["implementation_state"] == "implemented"
    assert reviewer_bootstrap["promotion_state"] == "contract_only"
    assert {
        "exact_v0237_empty_registry_v2_source_identity_binding",
        "package_code_pinned_pending_bootstrap_status",
        "explicit_new_registry_v3_id_and_lineage_generation",
        "all_three_root_endorsements_required_for_bootstrap",
        "future_two_of_three_event_approval_policy",
        "second_three_of_three_exact_target_genesis_activation_required",
        "target_genesis_must_bind_bootstrap_plan_and_receipt_hashes",
        "lineage_bound_runner_enrollment_required",
        "detached_root_possession_signatures_receipt_non_authoritative",
        "explicit_absence_of_predecessor_reviewer_authority_continuity",
        "exact_pep517_command_reproducibility_smoke_non_authoritative",
    }.issubset(reviewer_bootstrap["supported_scope"])
    assert {
        "actual_independent_reviewer_root_material",
        "package_bootstrap_inclusion",
        "target_registry_v3_genesis_activation",
        "operational_reviewer_bootstrap",
        "predecessor_reviewer_authority_continuity",
        "reviewer_human_or_organization_identity",
        "reviewer_hsm_origin_or_non_exportability",
        "ceremony_nonce_entropy_or_global_uniqueness",
        "hostile_same_process_python_module_mutation",
        "authoritative_release_identity_publication_gate",
        "clean_committed_source_replay",
        "separate_build_system_dependency_lock_and_wheelhouse",
        "build_system_dependency_closure",
        "runtime_dependency_wheelhouse_closure_for_exact_build",
        "external_transparency_log_or_monotonic_anchor",
        "runner_key_enrollment_or_activation",
        "signed_evidence_v3",
        "durable_ledger_v3",
        "actual_external_gfx1100_signed_cell",
        "commercial_readiness",
    }.issubset(reviewer_bootstrap["explicit_exclusions"])
    assert {
        "exact_package_pending_status_and_raw_schema_pins",
        "source_schema_raw_registry_head_time_reviewer_commitment_and_receipt_mutation_rejection",
        "new_registry_id_generation_and_full_ceremony_lineage_binding",
        "bootstrap_strictly_after_source_head",
        "root_insert_remove_reorder_duplicate_and_public_key_reuse_rejection",
        "missing_extra_duplicate_reordered_wrong_key_wrong_domain_and_transplanted_endorsement_rejection",
        "no_reviewer_signature_or_private_material_in_pending_fixture",
        "two_clean_materialized_source_exact_pep517_byte_reproducibility_smoke",
        "isolated_exact_wheel_resource_import",
        "runtime_and_build_system_wheelhouse_conflation_remains_fail_closed",
    }.issubset(reviewer_bootstrap["verification_cases"])
    assert reviewer_bootstrap["claim_level"] == (
        "fresh_genesis_bootstrap_contract_pending_reviewer_roots_zero_"
        "target_registry_inactive_non_promoting"
    )

    trust_lifecycle = rows["hip_fgmres_reviewed_trust_anchor_lifecycle_v2"]
    assert trust_lifecycle["implementation_state"] == "implemented"
    assert trust_lifecycle["promotion_state"] == "contract_only"
    assert {
        "detached_domain_separated_ed25519_key_proof_of_possession",
        "canonical_nonidentity_prime_order_ed25519_runner_and_reviewer_keys",
        "package_owned_reviewer_authority_commitment",
        "quorum_signed_append_only_registry_events",
        "fixed_shape_rolling_registry_hash_and_linear_event_key_replay",
        "reviewer_activation_time_preserved_and_enforced_as_authorization_lower_bound",
        "cross_role_unique_public_keys_contiguous_key_epochs_and_nonoverlapping_sequence_time_ranges",
        "exact_registry_v2_authority_for_signed_evidence_v2_and_replay_ledger_v2",
    }.issubset(trust_lifecycle["supported_scope"])
    assert {
        "operational_reviewer_bootstrap",
        "active_package_runner_key",
        "actual_hsm_or_hardware_token_key",
        "hostile_same_process_python_module_mutation",
        "actual_external_gfx1100_signed_cell",
        "historical_recovery_across_package_trust_or_fixture_registry_rotation",
        "external_transparency_log_or_monotonic_anchor",
        "same_artifact_two_architecture_evidence",
        "result_ir",
        "iteration_host_copy_zero",
        "performance_speedup",
        "end_to_end_o_n",
        "commercial_readiness",
    }.issubset(trust_lifecycle["explicit_exclusions"])
    assert {
        "low_order_identity_noncanonical_and_mixed_order_ed25519_point_rejection",
        "pre_reviewer_activation_authorization_rejection",
        "reviewer_runner_cross_role_and_global_runner_public_key_reuse_rejection",
        "signed_v2_exact_registry_type_and_inactive_key_rejection",
        "durable_v2_registry_drift_revocation_and_v1_downgrade_rejection",
    }.issubset(trust_lifecycle["verification_cases"])
    assert (
        trust_lifecycle["claim_level"]
        == "reviewed_event_sourced_trust_lifecycle_contract_reviewer_roots_zero_active_keys_zero_external_cells_zero_non_promoting"
    )

    replay_ledger = rows["hip_fgmres_external_replay_ledger_v1"]
    assert replay_ledger["implementation_state"] == "implemented"
    assert replay_ledger["promotion_state"] == "contract_only"
    assert {
        "expected_ledger_id_and_immutable_namespace_open",
        "directory_and_database_inode_pin",
        "begin_immediate_cross_process_writer_serialization",
        "runner_sequence_monotonic_across_key_epochs_and_campaigns",
        "post_commit_response_crash_recovery_lookup_and_reverification",
        "acceptance_commit_head_event_snapshot",
        "single_configured_ledger_cross_process_at_most_once_acceptance",
    }.issubset(replay_ledger["supported_scope"])
    assert {
        "exactly_once_delivery",
        "cross_host_or_cross_ledger_replay_prevention",
        "coordinated_storage_snapshot_rollback_resistance",
        "same_uid_root_or_storage_administrator_attack_resistance",
        "cryptographic_ledger_authenticity",
        "tpm_or_remote_monotonic_anchor",
        "nfs_fuse_or_non_posix_filesystem",
        "current_ledger_head_attestation_after_later_appends",
        "serialized_signed_release_identity_receipt_binding",
        "runner_honesty",
        "hardware_execution_truth",
        "active_package_trust_anchor",
        "actual_external_gfx1100_signed_cell",
        "same_artifact_two_architecture_evidence",
        "release_promotion",
        "result_ir",
        "iteration_host_copy_zero",
        "performance_speedup",
        "end_to_end_o_n",
        "commercial_readiness",
    }.issubset(replay_ledger["explicit_exclusions"])
    assert (
        replay_ledger["claim_level"]
        == "single_configured_owner_private_local_posix_sqlite_ledger_cross_process_at_most_once_acceptance_active_keys_zero_external_cells_zero_non_promoting"
    )

    release_identity = rows["hip_fgmres_external_release_identity_v1"]
    assert release_identity["implementation_state"] == "implemented"
    assert release_identity["promotion_state"] == "contract_only"
    assert {
        "candidate_wheel_bytes_and_record_identity_replay",
        "current_installed_distribution_record_replay",
        "clean_git_source_commit_and_manifest_replay",
        "exact_git_archive_source_bundle_replay",
        "runner_source_aggregate_identity",
        "declared_canonical_build_recipe_policy_identity",
        "declared_target_runtime_dependency_lock_and_wheelhouse_closure",
        "two_sequential_full_artifact_replays_before_challenge_and_signed_verification",
        "process_local_verified_release_capability_wrapper",
    }.issubset(release_identity["supported_scope"])
    assert {
        "atomic_multi_artifact_snapshot",
        "build_recipe_execution",
        "reproducible_build_proof",
        "remote_commit_authenticity",
        "build_system_dependency_closure",
        "runtime_dependency_installation_execution",
        "current_interpreter_wheel_tag_compatibility",
        "bounded_source_artifact_memory",
        "hostile_in_process_mint_isolation",
        "serialized_signed_release_identity_receipt_binding",
        "durable_cross_process_replay_ledger",
        "hardware_root_attestation",
        "hardware_execution",
        "actual_external_gfx1100_signed_cell",
        "same_artifact_two_architecture_evidence",
        "result_ir",
        "iteration_host_copy_zero",
        "performance_speedup",
        "end_to_end_o_n",
        "commercial_readiness",
    }.issubset(release_identity["explicit_exclusions"])
    assert (
        release_identity["claim_level"]
        == "local_double_replay_sequential_artifact_identity_active_keys_zero_external_cells_zero_non_promoting"
    )
    assert (
        "durable_cross_process_replay_ledger" in release_identity["explicit_exclusions"]
    )

    registry = rows["hip_fgmres_package_fixture_registry_v1"]
    assert registry["implementation_state"] == "implemented"
    assert registry["promotion_state"] == "contract_only"
    assert "hardware_execution" in registry["explicit_exclusions"]
    assert "package_fixture_registration_ten_of_ten" in registry["claim_level"]

    family = rows["hip_fgmres_registry_bound_model_family_parity_v2"]
    assert "actual_local_gfx1030_ten_of_ten" in family["supported_scope"]
    assert "actual_external_gfx1100_cell" in family["explicit_exclusions"]
    assert "serialized_external_evidence_counting" in family["explicit_exclusions"]
    assert "external_gfx1100_zero" in family["claim_level"]

    signed = rows["hip_fgmres_external_signed_evidence_v1"]
    assert signed["implementation_state"] == "implemented"
    assert signed["promotion_state"] == "contract_only"
    assert "domain_separated_ed25519_verification" in signed["supported_scope"]
    assert "active_package_trust_anchor" in signed["explicit_exclusions"]
    assert "actual_external_gfx1100_signed_cell" in signed["explicit_exclusions"]
    assert (
        "independent_installed_wheel_and_source_bundle_hash_recomputation"
        in signed["explicit_exclusions"]
    )
    assert "same_artifact_two_architecture_evidence" in signed["explicit_exclusions"]
    assert "durable_cross_process_replay_ledger" in signed["explicit_exclusions"]
    assert "active_keys_zero_external_cells_zero" in signed["claim_level"]

    signed_schema = json.loads(
        (
            REPO_ROOT
            / "src/structural_analysis/schemas/hip_fgmres_external_signed_evidence_receipt_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    identity_schema = json.loads(
        (
            REPO_ROOT
            / "src/structural_analysis/schemas/hip_fgmres_external_release_identity_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        signed_schema["$defs"]["claims"]["properties"][
            "durable_replay_ledger_verified"
        ]["const"]
        is False
    )
    assert (
        identity_schema["$defs"]["claims"]["properties"][
            "durable_replay_ledger_verified"
        ]["const"]
        is False
    )
    assert (
        identity_schema["$defs"]["claims"]["properties"][
            "signed_envelope_binds_release_identity_receipt"
        ]["const"]
        is False
    )

    signed_identity_v2 = rows["hip_fgmres_signed_release_identity_binding_v2"]
    assert signed_identity_v2["implementation_state"] == "implemented"
    assert signed_identity_v2["promotion_state"] == "contract_only"
    assert {
        "signed_payload_exact_release_identity_receipt_schema_and_hash_binding",
        "strict_v1_v2_downgrade_and_cross_protocol_rejection",
        "dedicated_v2_owner_private_local_posix_sqlite_ledger_namespace",
        "durable_v2_challenge_acceptance_and_post_response_loss_recovery",
    }.issubset(signed_identity_v2["supported_scope"])
    assert {
        "active_package_trust_anchor",
        "actual_external_gfx1100_signed_cell",
        "trust_anchor_rotation_or_revocation_lifecycle",
        "cross_host_or_cross_ledger_replay_prevention",
        "hardware_execution_truth",
        "release_promotion",
        "commercial_readiness",
    }.issubset(signed_identity_v2["explicit_exclusions"])
    assert (
        signed_identity_v2["claim_level"]
        == "signed_full_release_identity_receipt_binding_with_single_configured_local_v2_replay_ledger_active_keys_zero_external_cells_zero_non_promoting"
    )

    signed_identity_schema_v2 = json.loads(
        (
            REPO_ROOT
            / "src/structural_analysis/schemas/hip_fgmres_external_signed_evidence_receipt_v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    replay_ledger_schema_v2 = json.loads(
        (
            REPO_ROOT
            / "src/structural_analysis/schemas/hip_fgmres_external_replay_ledger_receipt_v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        signed_identity_schema_v2["$defs"]["claims"]["properties"][
            "signed_envelope_binds_release_identity_receipt"
        ]["const"]
        is True
    )
    assert (
        signed_identity_schema_v2["$defs"]["claims"]["properties"][
            "durable_replay_ledger_verified"
        ]["const"]
        is False
    )
    assert (
        replay_ledger_schema_v2["$defs"]["claims"]["properties"][
            "signed_envelope_binds_release_identity_receipt"
        ]["const"]
        is True
    )
    assert (
        replay_ledger_schema_v2["$defs"]["claims"]["properties"][
            "durable_replay_ledger_verified"
        ]["const"]
        is True
    )

    resident = rows["hip_assembly_resident_csr_residual_jvp_consumer_v1"]
    assert resident["implementation_state"] == "implemented"
    assert resident["promotion_state"] == "contract_only"
    assert (
        "borrowed_device_csr_row_column_values_without_reallocation"
        in resident["supported_scope"]
    )
    assert "borrowed_foundation_load_without_reupload" in resident["supported_scope"]
    assert (
        "zero_transfer_allocation_sync_enqueue_after_direction_producer"
        in resident["supported_scope"]
    )
    assert "public_device_direction_producer_token" in resident["explicit_exclusions"]
    assert "device_krylov_or_preconditioner" in resident["explicit_exclusions"]
    assert "iteration_host_copy_zero" in resident["explicit_exclusions"]
    assert "end_to_end_on_complexity" in resident["explicit_exclusions"]
    assert "commercial_readiness" in resident["explicit_exclusions"]
    assert (
        resident["claim_level"]
        == "same_stream_resident_csr_consumer_contract_test_double_parity_native_hardware_unavailable"
    )


def test_engine_v2_rtc_backend_records_native_parity_without_promotion() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    rtc = rows["hip_rtc_canonical_csr_residual_jvp_v1"]
    assert rtc["implementation_state"] == "implemented"
    assert rtc["promotion_state"] == "contract_only"
    assert (
        "native_gfx1030_full_free_constrained_fp64_parity" in (rtc["supported_scope"])
    )
    assert "unsigned_v1_forced_non_promoting" in rtc["supported_scope"]
    assert "signed_promotion_evidence" in rtc["explicit_exclusions"]
    assert "measured_complexity_slope" in rtc["explicit_exclusions"]

    scaling = rows["hip_rtc_fixed_degree3_kernel_scaling_v1"]
    assert scaling["implementation_state"] == "implemented"
    assert scaling["promotion_state"] == "non_promoting"
    assert (
        "measured_fixed_degree3_kernel_only_near_linear_scaling"
        in (scaling["supported_scope"])
    )
    assert "end_to_end_on_complexity" in scaling["explicit_exclusions"]
    assert "linear_or_nonlinear_solver" in scaling["explicit_exclusions"]
    assert "signed_promotion_evidence" in scaling["explicit_exclusions"]


def test_engine_v2_sparse_v2_stays_a_bounded_cpu_foundation() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    sparse = rows["sparse_execution_plan_v2_cpu_direct_csr"]
    assert sparse["implementation_state"] == "implemented"
    assert sparse["promotion_state"] == "contract_only"
    assert "global_dense_stiffness_materialization_zero" in sparse["supported_scope"]
    assert "support_mask_partition_rederivation" in sparse["supported_scope"]
    assert "state_ir_or_result_ir_receipt_chain" in sparse["explicit_exclusions"]
    assert "device_resident_krylov_or_preconditioner" in sparse["explicit_exclusions"]
    assert "sparse_direct_or_end_to_end_on_complexity" in sparse["explicit_exclusions"]


def test_shared_linear_frame_truss_semantics_stays_a_compatibility_contract() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    semantics = rows["linear_frame_truss_element_semantics_v1"]
    assert semantics["implementation_state"] == "implemented"
    assert semantics["promotion_state"] == "contract_only"
    assert {
        "backend_neutral_versioned_linear_frame_truss_public_module",
        "cpu_reference_public_shared_consumer_with_legacy_error_code_wrappers",
        "sparse_execution_plan_v2_public_shared_consumer_without_cpu_backend_import",
        "hip_symbolic_assembly_shared_axis_and_transform_consumer_without_cpu_backend_import",
        "current_source_actual_native_rtc_global_z_and_global_y_frame_truss_coefficients_checked_against_shared_public_oracle",
        "separate_source_semantics_and_historical_wire_operator_versions",
        "frozen_cpu_operator_recovery_numeric_and_sparse_plan_hashes_preserved",
    }.issubset(semantics["supported_scope"])
    assert {
        "shared_generated_hip_cpp_coefficients",
        "broad_or_signed_native_hip_numerical_parity_beyond_narrow_rtc_shared_oracle",
        "shell_solid_spring_mpc_or_diaphragm_elements",
        "element_offsets_or_releases",
        "slender_or_ill_conditioned_scaling_and_iterative_refinement",
        "peak_rss_measurement",
        "end_to_end_on_complexity",
        "performance_or_speedup_claim",
        "commercial_readiness",
    }.issubset(semantics["explicit_exclusions"])
    assert (
        "focused_cpu_execution_plan_v1_v2_hip_symbolic_and_rtc_117_passed_"
        "including_conditional_native_global_z_and_global_y_shared_oracle"
        in semantics["verification_cases"]
    )
    assert semantics["claim_level"] == (
        "shared_linear_frame_truss_dependency_and_numeric_compatibility_contract_"
        "only_narrow_native_rtc_shared_oracle_not_broad_native_parity_or_"
        "commercial_readiness"
    )


def test_cpu_fgmres_reference_stays_separate_from_device_solver_claims() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    fgmres = rows["cpu_fixed_restart_fgmres_reference_v1"]
    assert fgmres["implementation_state"] == "implemented"
    assert fgmres["promotion_state"] == "cpu_reference"
    assert "actual_initial_residual_b_minus_a_x0" in fgmres["supported_scope"]
    assert (
        "mandatory_deterministic_full_recurrence_validation"
        in (fgmres["supported_scope"])
    )
    assert "hip_or_hiprtc_execution" in fgmres["explicit_exclusions"]
    assert "iteration_host_copy_zero" in fgmres["explicit_exclusions"]
    assert "end_to_end_on_complexity" in fgmres["explicit_exclusions"]
    assert "commercial_readiness" in fgmres["explicit_exclusions"]

    hip_plan = rows["hip_fixed_restart_fgmres_allocation_policy_plan_v1"]
    assert hip_plan["implementation_state"] == "implemented"
    assert hip_plan["promotion_state"] == "contract_only"
    assert (
        "seven_borrowed_and_nine_owned_physical_device_buffer_extents"
        in (hip_plan["supported_scope"])
    )
    assert "hiprtc_fgmres_recurrence_execution" in hip_plan["explicit_exclusions"]
    assert "iteration_host_copy_zero" in hip_plan["explicit_exclusions"]
    assert "commercial_readiness" in hip_plan["explicit_exclusions"]

    rtc_substrate = rows["hip_fgmres_seven_symbol_rtc_substrate_v1"]
    assert rtc_substrate["implementation_state"] == "implemented"
    assert rtc_substrate["promotion_state"] == "contract_only"
    assert (
        "package_owned_fixed_seven_symbol_hiprtc_source"
        in (rtc_substrate["supported_scope"])
    )
    assert (
        "native_gfx1030_hiprtc_compile_and_seven_symbol_inspection"
        in (rtc_substrate["supported_scope"])
    )
    assert "arnoldi_mgs_or_dgks_recurrence" in (rtc_substrate["explicit_exclusions"])
    assert (
        "authoritative_solver_completion_or_solution_receipt"
        in (rtc_substrate["explicit_exclusions"])
    )
    assert (
        "native_gpu_numerical_execution_or_cpu_hip_recurrence_parity"
        in (rtc_substrate["explicit_exclusions"])
    )
    assert "iteration_host_copy_zero" in rtc_substrate["explicit_exclusions"]
    assert "commercial_readiness" in rtc_substrate["explicit_exclusions"]

    recurrence_plan_v2 = rows["hip_fgmres_recurrence_allocation_control_plan_v2"]
    assert recurrence_plan_v2["implementation_state"] == "implemented"
    assert recurrence_plan_v2["promotion_state"] == "contract_only"
    assert (
        "seven_borrowed_and_ten_owned_device_buffer_extents"
        in (recurrence_plan_v2["supported_scope"])
    )
    assert (
        "hashed_initial_mode_schedule_and_reduction_target_stage_compatibility"
        in (recurrence_plan_v2["supported_scope"])
    )
    assert (
        "hashed_first_column_partial_schedule_through_device_dgks_decide"
        in (recurrence_plan_v2["supported_scope"])
    )
    assert (
        "hashed_first_column_completion_schedule_through_normalize_v_next_and_arnoldi_givens"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "hashed_first_column_candidate_preparation_schedule_through_vector_accept"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "candidate_preparation_schedule_hash_sha256_8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "candidate_residual_schedule_hash_sha256_c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "candidate_scale_metrics_schedule_hash_sha256_1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "checkpoint_transaction_schedule_hash_sha256_0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d"
        in recurrence_plan_v2["supported_scope"]
    )
    assert {
        "checkpoint_nonadvancing_source_preflight_mode9_and_state3_ticket_contract",
        "checkpoint_legacy_zero_to_three_to_zero_and_sealed_two_to_three_to_zero_lifecycle",
        "checkpoint_source_preflight_destination_access_zero_and_no_new_f_workspace",
        "checkpoint_invalid_source_failure_status_code47_error_bit4_origin2_destination_preservation_contract",
        "checkpoint_fixed_four_row_parallel_o_f_preflight_without_product_h2d_d2h_sync_or_fallback",
        "checkpoint_mandatory_handoff_required_and_prestate_validity_separated",
        "checkpoint_malformed_mandatory_handoff_fails_before_restart_row_and_result_header_publication",
    }.issubset(recurrence_plan_v2["supported_scope"])
    assert (
        "checkpoint_finalizer_only_restart_row_and_result_metric_header_publish_contract"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "checkpoint_pre_finalizer_numerical_failure_terminal_status_code_error_header_only"
        in recurrence_plan_v2["supported_scope"]
    )
    assert (
        "conditional_second_dgks_claim_only_false_path_and_h_next_target_contract"
        in (recurrence_plan_v2["supported_scope"])
    )
    assert (
        "device_allocation_or_kernel_execution"
        in (recurrence_plan_v2["explicit_exclusions"])
    )

    initial_rtc_v2 = rows["hip_fgmres_initial_recurrence_rtc_v2"]
    assert initial_rtc_v2["implementation_state"] == "implemented"
    assert initial_rtc_v2["promotion_state"] == "contract_only"
    assert (
        "native_gfx1030_f513_initial_numerical_gpu_tree_parity"
        in (initial_rtc_v2["supported_scope"])
    )
    assert (
        "native_duplicate_reduction_epoch_fail_closed_without_hang"
        in (initial_rtc_v2["supported_scope"])
    )
    assert (
        "single_pending_stream_recurrence_enforcement"
        in (initial_rtc_v2["supported_scope"])
    )
    assert (
        "device_dot_accept_y0_h00_accumulation_and_strict_dgks_decision"
        in (initial_rtc_v2["supported_scope"])
    )
    assert (
        "device_conditional_second_dgks_dot_and_mgs_with_false_path_epoch_claim_only"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "device_h_next_lassq_tau_two_to_minus_46_v1_normalization_and_canonical_positive_zero_breakdown"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "device_signed_incremental_givens_candidate_reason_state_and_successful_counters"
        in (initial_rtc_v2["supported_scope"])
    )
    assert (
        "device_column0_scale_relative_backsolve_gated_trial_update_l2_and_vector_accept"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "candidate_false_and_triangular_breakdown_followup_claim_only_without_candidate_numeric_publish"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "combined_kernel_abi_hash_sha256_31fbff2fa25c221a99f28e170818990a8ed71211169d239e05d28628941941c9"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "fixed_source_hash_sha256_34049a08119b19382c26fbe310f957d7af9c41db037dfcbab521828732025e9b"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "checkpoint_transaction_schedule_hash_sha256_d9b9115287e3b5839096e3f4417c04899ffc7592864483d918be55deaf4b4442"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "raw_checkpoint_launch_owner_only_not_authoritative_transaction_owner"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "checkpoint_v0_2_15_validation_plan58_rtc57_oracle95_focused222_hardware12_fgmres289_broad1019"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "checkpoint_numerical_failure_status_code_error_header_without_result_metric_or_row_publish"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "device_only_active_cycle_end_dual_gate_invariant_strict_divergence_priority_predicate"
        in initial_rtc_v2["supported_scope"]
    )
    assert (
        "native_gfx1030_f513_dgks_true_false_and_exact_happy_breakdown_through_givens_gpu_tree_parity"
        in initial_rtc_v2["verification_cases"]
    )
    assert (
        "authoritative_checkpoint_transaction"
        in (initial_rtc_v2["explicit_exclusions"])
    )
    assert (
        "authoritative_rtc_transaction_owner" in initial_rtc_v2["explicit_exclusions"]
    )
    assert (
        "invalid_source_multiblock_commit_all_or_nothing_proof"
        in initial_rtc_v2["explicit_exclusions"]
    )
    assert (
        "shifted_or_range_overlap_raw_pointer_validation"
        in initial_rtc_v2["explicit_exclusions"]
    )
    assert (
        "same_buffer_three_launch_atomic_enqueue_and_state_tracking"
        in initial_rtc_v2["explicit_exclusions"]
    )
    assert (
        "native_duplicate_checkpoint_decide_commit_finalize_policy"
        in initial_rtc_v2["explicit_exclusions"]
    )
    assert "later_columns_or_restarts" in initial_rtc_v2["explicit_exclusions"]
    assert "iteration_host_copy_zero" in initial_rtc_v2["explicit_exclusions"]
    assert "commercial_readiness" in initial_rtc_v2["explicit_exclusions"]

    checkpoint_context = rows["hip_fgmres_checkpoint_transaction_context_v2"]
    assert checkpoint_context["implementation_state"] == "implemented"
    assert checkpoint_context["promotion_state"] == "contract_only"
    assert (
        "caller_attested_valid_predecessor_non_promoting_scope"
        in checkpoint_context["supported_scope"]
    )
    assert (
        "exact_eleven_role_f64_u8_allocation_extents"
        in checkpoint_context["supported_scope"]
    )
    assert (
        "conservative_process_native_runtime_domain_per_device_ordinal"
        in checkpoint_context["supported_scope"]
    )
    assert (
        "loader_minted_runtime_and_read_only_library_identity"
        in checkpoint_context["supported_scope"]
    )
    assert (
        "private_dlsym_fresh_fixed_cfunctype_prototypes_isolated_from_public_ctypes_mutation"
        in checkpoint_context["supported_scope"]
    )
    assert (
        "actual_hip_get_device_module_lease_launch_fence_consume_authority_and_close_checks"
        in checkpoint_context["supported_scope"]
    )
    assert (
        "one_queue_lock_decide_commit_finalize_same_stream_submission"
        in checkpoint_context["supported_scope"]
    )
    assert {
        "exact_loaded_runtime_stream_query_sealed_in_checkpoint_lease_witness_snapshot",
        "hip_stream_query_status_zero_complete_six_hundred_pending_and_other_status_or_exception_fail_closed",
        "checkpoint_lease_exact_query_callable_runtime_device_stream_and_binding_snapshot",
        "rtc_v0_2_25_full_111_passed_in_34_77_seconds",
    }.issubset(checkpoint_context["supported_scope"])
    for fixed_evidence in (
        "v0_2_16_historical_checkpoint_context_source_hash_sha256_52d95b7a57a9c851c52fa8012047e2399e84e8da65cb686346f1ab2694cc2f23",
        "v0_2_16_historical_raw_rtc_python_source_hash_sha256_d6e312fba83d60c87dedc10aa5b8c0525cb1715b4beb5980df9b0f9dc40e7f59",
        "v0_2_16_historical_hip_native_binding_source_hash_sha256_35dad9d9a303d71ffef975e99247dc1ca08f1bfa7a871bf67746a75f3225a59e",
        "v0_2_16_historical_hip_context_binding_source_hash_sha256_de916fe1a41a7aedec49fe1170fe8153fa75babc4d644ac0c27a974dd03f554e",
        "v0_2_16_historical_checkpoint_context246_raw_rtc60_combined_hip_context258_fgmres538_broad1268_hardware12_validation",
    ):
        assert fixed_evidence in checkpoint_context["supported_scope"]
    assert (
        "authoritative_predecessor_producer_receipt"
        in checkpoint_context["explicit_exclusions"]
    )
    assert (
        "live_parent_resource_context_not_bound_into_this_caller_attested_transaction"
        in checkpoint_context["explicit_exclusions"]
    )
    assert (
        "live_allocator_resource_context_not_bound_into_this_caller_attested_transaction"
        in checkpoint_context["explicit_exclusions"]
    )
    assert (
        "invalid_source_multiblock_commit_all_or_nothing_proof"
        in checkpoint_context["explicit_exclusions"]
    )
    assert "later_columns_or_restarts" in checkpoint_context["explicit_exclusions"]
    assert (
        "adversarial_runtime_library_path_to_loaded_mapping_toctou_or_amd_signature_attestation"
        in checkpoint_context["explicit_exclusions"]
    )
    assert "iteration_host_copy_zero" in checkpoint_context["explicit_exclusions"]
    assert (
        "stream_completion_query_as_numerical_or_solver_outcome"
        in checkpoint_context["explicit_exclusions"]
    )
    assert "commercial_readiness" in checkpoint_context["explicit_exclusions"]

    live_resources = rows["hip_fgmres_live_checkpoint_resource_context_v1"]
    assert live_resources["implementation_state"] == "implemented"
    assert live_resources["promotion_state"] == "contract_only"
    assert (
        "exact_krylov_parent_three_capability_binding"
        in live_resources["supported_scope"]
    )
    assert (
        "fresh_exclusive_solver_owned_eight_allocation_owner"
        in live_resources["supported_scope"]
    )
    assert "exact_eleven_capability_atomic_borrow" in live_resources["supported_scope"]
    assert "semantic_last_reverse_cleanup" in live_resources["supported_scope"]
    assert (
        "owned_device_content_initialization" in live_resources["explicit_exclusions"]
    )
    assert "authoritative_predecessor" in live_resources["explicit_exclusions"]
    assert "device_mask_domain_validation" in live_resources["explicit_exclusions"]
    assert "live_solver_or_solution" in live_resources["explicit_exclusions"]
    assert "iteration_host_copy_zero" in live_resources["explicit_exclusions"]
    assert "commercial_readiness" in live_resources["explicit_exclusions"]

    row_ids = [row["capability_id"] for row in payload["rows"]]
    live_resource_index = row_ids.index(
        "hip_fgmres_live_checkpoint_resource_context_v1"
    )
    assert (
        row_ids[live_resource_index + 1]
        == "hip_fgmres_canonical_predecessor_producer_v1"
    )

    canonical_predecessor = rows["hip_fgmres_canonical_predecessor_producer_v1"]
    assert canonical_predecessor["implementation_state"] == "implemented"
    assert canonical_predecessor["promotion_state"] == "contract_only"
    assert canonical_predecessor["claim_level"].endswith("contract_only_non_promoting")
    assert {
        "canonical_first_column_exact_27_plus_14s_kernel_schedule_fenced",
        "exact_owned_eight_zero_initialized_before_canonical_schedule_then_fenced",
        "source_apply_completion_bound",
        "positive_jacobi_completion_bound",
        "device_validator_mask_domain_zero_1792_7936_gate_bound",
        "same_runtime_device_stream_bound",
        "persistent_parent_three_owned_eight_exact_eleven_bound",
        "delegated_reduced_csr_three_and_reduction_scratch_two_bound",
        "exact_sixteen_physical_capability_projection_without_additional_allocation",
    }.issubset(canonical_predecessor["supported_scope"])
    assert {
        "authoritative_predecessor_proven",
        "actual_mask_host_observed",
        "device_validation_outcome_host_observed",
        "checkpoint_transaction_ready",
        "invalid_source_destination_atomicity_proven",
        "live_solver_ready",
        "solution_ready",
        "iteration_host_copy_zero_proven",
        "asymptotic_o_n_proven",
        "speedup_proven",
        "commercial_ready",
        "promotion_eligible",
    }.issubset(canonical_predecessor["explicit_exclusions"])

    atomicity = rows["hip_fgmres_checkpoint_invalid_source_atomicity_v1"]
    assert atomicity["implementation_state"] == "implemented"
    assert atomicity["promotion_state"] == "contract_only"
    assert atomicity["claim_level"].startswith(
        "raw_fixed_four_row_invalid_source_destination_atomicity_scoped"
    )
    assert {
        "raw_exact_registered_nonoverlap_allocation_scope",
        "same_stream_exclusive_source_ownership_fixed_four_row_owner_sequence",
        "checkpoint_decide_preflight_commit_finalize_control_vector_vector_control_rows",
        "checkpoint_schedule_hash_sha256_2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5",
        "combined_kernel_abi_hash_sha256_bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f",
        "fixed_source_hash_sha256_a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113",
        "source_preflight_destination_access_zero",
        "late_invalid_source_preserves_entire_solution_and_residual_raw_bytes",
        "terminal_failure_clears_commit_and_continuation_required",
        "gate_false_source_and_destination_no_read_no_write",
        "no_new_order_f_workspace_allocation_h2d_d2h_intermediate_sync_or_fallback",
        "context_new_and_adjacent_focused_seventy_seven_cases",
        "full_checkpoint_context_two_hundred_sixty_one_cases_in_523_33_seconds",
        "first_error_cas_diagnostic_latch",
        "complete_row_canonical_tuple_kernel_token_stream_policy_and_eleven_pointer_frozen_binding",
        "control_and_solve_record_u8_allocation_eight_byte_alignment",
    }.issubset(atomicity["supported_scope"])
    assert {
        "canonical_conditional_capability_consumed_by_live_transaction",
        "authoritative_predecessor",
        "authoritative_checkpoint_transaction",
        "arbitrary_raw_duplicate_commit_device_only_rejection",
        "host_four_launch_enqueue_indivisible_atomicity",
        "external_kernel_dma_or_other_stream_writer",
        "dedicated_native_sealed_plus_invalid_source_combination_case",
        "iteration_host_copy_zero",
        "end_to_end_on_complexity",
        "performance_or_speedup_claim",
        "commercial_readiness",
    }.issubset(atomicity["explicit_exclusions"])
    assert (
        "full_context_ruff_pycompile_canonical_hash_and_actual_hip_source_hash_assertion"
        in atomicity["verification_cases"]
    )
    assert (
        "checkpoint_context_full_261_and_focused_77" in atomicity["verification_cases"]
    )

    atomicity_index = row_ids.index("hip_fgmres_checkpoint_invalid_source_atomicity_v1")
    assert (
        row_ids[atomicity_index - 1] == "hip_fgmres_checkpoint_transaction_context_v2"
    )
    assert row_ids[atomicity_index + 1] == (
        "hip_fgmres_sealed_checkpoint_transaction_context_v1"
    )

    sealed = rows["hip_fgmres_sealed_checkpoint_transaction_context_v1"]
    assert sealed["implementation_state"] == "implemented"
    assert sealed["promotion_state"] == "contract_only"
    assert sealed["claim_level"] == (
        "canonical_capability_consuming_live_sealed_transaction_contract_only_"
        "device_outcome_unobserved_non_promoting"
    )
    assert {
        "still_open_canonical_predecessor_conditional_capability_reserved_and_consumed_exactly_once",
        "nonowning_nested_child_over_exact_live_kernel_checkpoint_token_and_stream",
        "exact_control_vector_vector_control_four_row_program",
        "transaction_final_exact_runtime_fence_one_and_atomic_pending_consume_four",
        "canonical_prefix_plus_transaction_total_final_fence_count_two",
        "frozen_kernel_token_stream_cleanup_after_mutable_projection_drift",
        "post_fence_authority_revalidation_before_conditional_continuation_issue",
        "additional_allocation_borrow_checkpoint_owner_module_h2d_d2h_intermediate_sync_and_fallback_zero",
        "device_outcome_unobserved_conditional_continuation_capability_only",
        "focused_adversarial_transaction_twenty_three_cases",
        "legacy_live_and_canonical_boundary_fifty_six_cases",
        "broad_engine_v2_midas_v2_model_ir_v2_one_thousand_seven_hundred_seventy_eight_passed",
        "wheel_826616_bytes_sha256_9c0eaaa4e27f2cbb9b2ac827a91b1f3785c8ca01c3e494077d01aae763420ffb_isolated_public_api_schema_kernel_resource_import",
        "native_gfx1030_valid_canonical_to_sealed_chain",
        "native_gfx1030_late_nonfinite_sealed_source_preserves_full_destination_and_source_bytes",
        "native_terminal_and_pending_status_six_code_forty_seven_with_future_action_gates_cleared",
        "dead_unconsumed_stream_idle_global_child_weak_lease_lazily_reaped_by_sealed_parent_close",
        "v0_2_25_parent_owned_weak_liveness_recovery_cell_without_strong_child_context_or_lease_retention",
        "global_child_gc_callback_marks_abandoned_without_hip_runtime_call",
        "process_local_abandoned_consumed_pending_query_optional_single_sync_exact_pending_ack_and_terminal_release",
        "monotonic_interruption_recovery_exact_bool_parent_ledger_reconciliation_and_frozen_authority_validation",
        "sealed_transaction_v0_2_25_full_30_passed_in_507_23_seconds",
        "sealed_global_lifecycle_six_passed_in_123_64_seconds",
        "independent_lifecycle_audit_no_additional_defect",
    }.issubset(sealed["supported_scope"])
    assert {
        "actual_mask_host_observed",
        "device_validation_outcome_host_observed",
        "authoritative_predecessor_proven",
        "authoritative_numerical_transaction_proven",
        "live_solver_ready",
        "solution_ready",
        "later_columns_or_restarts",
        "iteration_host_copy_zero_proven",
        "end_to_end_on_complexity",
        "performance_or_speedup_claim",
        "process_crash_gpu_reset_or_cross_process_abandoned_owner_recovery",
        "abandoned_owner_recovery_as_completion_numerical_parity_or_solution_evidence",
        "standalone_receipt_provenance_authenticity_without_expected_context_or_signature",
        "commercial_readiness",
        "promotion_eligible",
    }.issubset(sealed["explicit_exclusions"])
    assert {
        "abandoned_unconsumed_factory_result_reaped_before_parent_close",
        "consume_without_registered_recovery_cell_zero_hip_fail_closed_and_unused_release_reopen",
        "abandoned_consumed_or_pending_global_child_recovered_by_parent_owned_weak_liveness_cell",
        "query_optional_single_sync_ack_and_monotonic_terminal_release_interruption_recovery",
        "stale_pending_partial_close_exact_bool_and_frozen_authority_fail_closed_regressions",
    }.issubset(sealed["verification_cases"])
    assert {
        "combined_kernel_abi_hash_sha256_bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f",
        "fixed_source_hash_sha256_a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113",
    }.issubset(sealed["supported_scope"])
    assert row_ids[atomicity_index + 2] == "hip_fgmres_global_recurrence_owner_v1"

    global_owner = rows["hip_fgmres_global_recurrence_owner_v1"]
    assert global_owner["implementation_state"] == "implemented"
    assert global_owner["promotion_state"] == "contract_only"
    assert global_owner["claim_level"] == (
        "sealed_continuation_consuming_fixed_suffix_fence_contract_only_"
        "device_outcome_unobserved_non_promoting"
    )
    assert {
        "immutable_initial_plus_r_times_m_columns_plus_final_guard_schedule",
        "current_checkpoint_transaction_schedule_hash_sha256_0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d",
        "global_schedule_semantic_contract_hash_sha256_7c18ba9190fef663fec8e1f87e0f56ec393e23f04d4753ffbc3c707bff1a10ea",
        "current_combined_recurrence_abi_hash_sha256_6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b",
        "current_fixed_source_hash_sha256_a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d",
        "v0_2_24_python_host_control_only_cpp_hip_public_schema_and_abi_unchanged",
        "v0_2_25_exact_stream_query_and_parent_owned_abandoned_child_recovery",
        "v0_2_25_cpp_hip_public_schema_and_abi_identities_unchanged",
        "v0_2_26_exact_full_final_cycle_checkpoint_to_guard_handoff",
        "v0_2_26_cpp_hip_recurrence_plan_schema_and_semantic_identities_changed",
        "v0_2_26_global_receipt_completion_and_completion_capability_schema_unchanged",
        "gap_free_nonoverlap_full_sealed_prefix_and_continuation_partition",
        "sealed_conditional_continuation_capability_reserved_and_consumed_exactly_once",
        "prefix_replay_rejected_and_suffix_only_submission",
        "direct_eleven_csr_three_scratch_two_physical_sixteen_continuity",
        "global_suffix_final_fence_one_and_exact_pending_consume",
        "global_owner_additional_allocation_borrow_checkpoint_owner_module_h2d_d2h_intermediate_sync_fallback_live_read_and_host_branch_zero",
        "rtc_flat_exact_type_identity_value_witness_without_per_launch_semantic_serialization",
        "four_launch_paths_private_expected_prior_pending_count_atomic_owner_lock_gate",
        "phase_boundary_deep_binding_checks_two_for_l1_and_l35",
        "per_row_exact_child_frozen_resource_canonical_row_and_pending_count",
        "fixed_suffix_host_submission_control_o_l_structural_gate_with_fixed_work_per_row",
        "deterministic_l1_l35_identity_to_dict_zero_and_pending_zero_through_l_minus_one",
        "registry_sealed_tuple_backed_immutable_dispatch_snapshot_and_canonical_row_value_tuple",
        "dispatch_transient_toctou_high_fixed_regression_one_passed_in_26_62_seconds",
        "post_toctou_fix_f12_and_f24_required_gfx1030_cases_two_passed_in_96_11_seconds",
        "final_independent_linear_reaudit_no_remaining_defect_in_requested_host_control_scope",
        "linear_reaudit_transient_row_pointer_two_thread_bool_int_value_equal_tuple_and_forged_registry_slot_safe",
        "signed_zero_float_hex_exact_seal_binding_invalid_zero_launch",
        "aggregate_deep_validator_counts_l1_l35_enqueue_three_fence_four_constant",
        "linear_reaudit_focused_four_passed_in_120_65_seconds",
        "immutable_dispatch_regression_rerun_one_passed_in_26_74_seconds",
        "linear_reaudit_ruff_format_pycompile_green",
        "rtc_focused_103_passed",
        "global_owner_ten_passed_in_246_23_seconds",
        "sealed_global_lifecycle_six_passed_in_123_64_seconds",
        "independent_lifecycle_audit_no_additional_defect",
        "dead_unconsumed_stream_idle_factory_lease_lazily_reaped",
        "parent_owned_weak_liveness_recovery_cell_without_strong_child_context_or_lease_retention",
        "abandoned_callback_marks_only_and_makes_no_hip_runtime_call",
        "abandoned_consumed_pending_child_query_optional_one_successful_exact_checkpoint_sync_query_ack_and_terminal_release",
        "frozen_kernel_checkpoint_token_stream_runtime_device_and_binding_authority_validated_before_recovery_work",
        "monotonic_release_phases_and_interruption_safe_exact_parent_ledger_reconciliation",
        "exact_bool_only_state_repair_and_stale_pending_partial_close_fail_closed",
        "outcome_free_completion_capability_only",
        "standalone_receipt_structural_and_semantic_validation_only",
        "expected_context_or_signed_chain_required_for_provenance_authenticity",
        "native_raw_gfx1030_f513_m2_i5_three_restart_exhaustion_cpu_oracle_parity",
        "native_raw_gfx1030_active_valid_and_malformed_final_guard",
        "native_integrated_gfx1030_f12_nnz144_m2_i2_full_prefix_suffix_84_45_39",
        "native_integrated_active_later_column_terminal_epoch_e79_q26",
        "native_integrated_global_product_path_allocation_h2d_d2h_intermediate_sync_zero_and_one_global_fence",
        "verification_only_cpu_solution_and_residual_exact_parity_after_product_receipt_freeze",
        "native_integrated_owner_later_column_one_case_passed_in_38_29_seconds_vs_165_02_seconds_4_31x_shorter_test_wall_clock",
        "native_integrated_active_later_restarts_f24_nnz360_m2_i5_r3_full_prefix_suffix_228_45_183",
        "native_integrated_restart_one_two_three_terminal_restart3_column0_e179_q58",
        "native_integrated_cpu_max_iterations_exhausted_iterations_restarts_5_3_operator_preconditioner_9_5_solution_residual_allclose",
        "native_integrated_active_restart_one_passed_one_deselected_in_59_39_seconds",
        "native_integrated_final_guard_expected_e215_q70_submitted_inactive_after_terminal_checkpoint_finalize",
        "native_integrated_active_final_guard_f24_nnz360_m2_i4_r2_full_prefix_suffix_156_45_111",
        "native_integrated_full_final_checkpoint_handoff_e147_q48_guard_terminal_e148_q48",
        "native_integrated_active_final_guard_cpu_counts_iterations_restarts_4_2_operator_preconditioner_7_4_solution_residual_allclose",
        "native_integrated_active_final_guard_product_path_zero_copy_zero_allocation_one_fence_and_outcome_free_receipt",
        "native_integrated_active_final_guard_full_cycle_one_passed_in_60_93_seconds",
        "native_integrated_partial_final_cycle_regression_one_passed_in_61_97_seconds",
        "native_gfx1030_normal_next_restart_and_operator_count_malformed_handoff_three_passed_in_8_12_seconds",
        "native_integrated_gfx1030_f12_m2_i2_suffix_pending_39_to_zero_lifecycle_gate",
        "native_integrated_recovery_query_not_ready_then_complete_and_successful_sync_one",
        "native_integrated_recovery_product_malloc_h2d_d2h_runtime_facade_sync_and_verification_d2h_zero",
        "native_integrated_recovery_lifecycle_only_without_numerical_completion_or_product_outcome_claim",
        "native_integrated_recovery_one_passed_two_deselected_in_37_42_seconds",
        "rtc_v0_2_25_full_111_passed_in_34_77_seconds",
        "checkpoint_context_v2_full_261_passed_in_248_58_seconds",
        "global_owner_v0_2_25_full_54_passed_in_1387_12_seconds",
        "sealed_transaction_v0_2_25_full_30_passed_in_507_23_seconds",
        "independent_v0_2_25_recovery_audit_blocker_high_medium_low_zero",
        "wheel_875235_bytes_sha256_e6522f810af2a4a0f6d62c770f510bcab57278e64cec4e0070b8fbec2eb2b8e2",
        "sdist_823734_bytes_sha256_8094a8bcaf30d3aaf954d5c5f0183baaf03881ff96ae62b33b6832276b2b3d3c",
        "isolated_wheel_global_public_api_schema_and_hip_kernel_resource_import",
    }.issubset(global_owner["supported_scope"])
    assert {
        "actual_terminal_outcome_host_observed_in_product_receipt",
        "authoritative_terminal_status_proven",
        "product_receipt_numerical_parity_verified",
        "solution_ready",
        "completion_only_solution_record_and_residual_export",
        "model_family_and_multi_architecture_cpu_hip_full_recurrence_parity",
        "iteration_host_copy_zero_proven",
        "end_to_end_on_complexity",
        "general_n_dof_o_n_claim",
        "kernel_speedup_claim",
        "solver_end_to_end_speedup_claim",
        "performance_or_speedup_claim",
        "process_crash_gpu_reset_or_cross_process_abandoned_owner_recovery",
        "abandoned_recovery_as_terminal_numerical_parity_completion_or_solution_evidence",
        "standalone_receipt_provenance_authenticity_without_expected_context_or_signed_chain",
        "commercial_readiness",
        "promotion_eligible",
    }.issubset(global_owner["explicit_exclusions"])
    assert (
        "integrated_active_later_restart_proven"
        not in (global_owner["explicit_exclusions"])
    )
    assert (
        "final_independent_linear_reaudit_closure"
        not in global_owner["explicit_exclusions"]
    )
    assert {
        "flat_identity_atomic_pending_and_constant_phase_boundary_deep_check_l1_l35",
        "validated_immutable_dispatch_snapshot_resists_transient_live_row_and_pointer_drift",
        "post_toctou_fix_two_required_integrated_hardware_cases_repassed_without_audit_promotion",
        "final_linear_host_control_reaudit_transient_alias_forgery_and_signed_zero_cases_closed",
        "direct_and_aggregate_deep_validator_counts_constant_for_l1_and_l35",
        "final_linear_reaudit_focused_and_immutable_regressions_repassed",
        "abandoned_unconsumed_lease_and_consumed_pending_owner_process_local_parent_recovery",
        "abandoned_query_optional_single_sync_ack_and_terminal_release_without_numerical_claim",
        "recovery_dual_store_release_poison_publication_stale_pending_partial_close_and_false_ready_regressions",
        "recovery_exact_bool_cleanup_owner_frozen_authority_and_baseexception_fail_closed_regressions",
        "native_integrated_recovery_not_ready_sync_complete_pending_39_to_zero_zero_product_calls",
        "native_integrated_active_later_restart_one_through_three_max_iteration_exhaustion",
        "native_integrated_partial_final_cycle_checkpoint_terminalization_kept_inactive_guard",
        "native_integrated_exact_full_final_cycle_checkpoint_handoff_and_active_guard_epoch_claim",
        "native_malformed_next_restart_and_operator_count_handoff_prepublication_fail_closed",
    }.issubset(global_owner["verification_cases"])
    assert (
        "integrated_active_final_guard_fallthrough_proven"
        not in global_owner["explicit_exclusions"]
    )
    assert {
        "docs/engine-v2-hip-fgmres-global-recurrence-v1.md",
        "src/structural_analysis/engine_v2/assembly_backend/fgmres_global_schedule_plan_v1.py",
        "src/structural_analysis/engine_v2/assembly_backend/fgmres_global_recurrence_context_v1.py",
        "src/structural_analysis/schemas/hip_fgmres_global_recurrence_context_v1.schema.json",
        "tests/test_engine_v2_hip_fgmres_global_recurrence_context_hardware_v1.py",
    }.issubset(global_owner["evidence_paths"])
    assert row_ids[atomicity_index + 3] == "hip_fgmres_completion_export_v1"

    completion_export = rows["hip_fgmres_completion_export_v1"]
    assert completion_export["implementation_state"] == "implemented"
    assert completion_export["promotion_state"] == "contract_only"
    assert completion_export["claim_level"] == (
        "fenced_completion_three_raw_buffer_blocking_d2h_export_"
        "outcome_uninterpreted_non_promoting"
    )
    assert {
        "exact_fenced_global_completion_capability_reserved_and_consumed_once",
        "preconsume_three_host_staging_allocations_retryable_before_irreversible_consume",
        "exact_blocking_d2h_order_solution_x_true_residual_solve_record",
        "exact_solution_and_true_residual_extent_eight_f_bytes_each",
        "exact_opaque_solve_record_extent_192_plus_72r_bytes",
        "exact_total_export_extent_16f_plus_192_plus_72r_bytes",
        "loader_bound_hip_memcpy_device_to_host_binding_and_immutable_source_pointer_snapshots",
        "native_exact_bound_copy_type_call_ctypes_abi_errcheck_memcpy_and_loaded_runtime_relationship",
        "authority_and_copy_binding_revalidated_before_each_copy_and_before_publication",
        "exact_three_blocking_d2h_attempts_successes_and_completions_on_exported_path",
        "immutable_detached_bytes_read_only_numpy_views_and_payload_bundle_receipt_hashes",
        "no_partial_result_publication_and_consumed_failure_no_recopy",
        "repeat_and_concurrent_result_retrieval_same_identity_without_additional_copy",
        "global_owner_receipt_and_hash_unchanged_by_separate_export_telemetry",
        "export_owner_device_allocation_borrow_h2d_kernel_explicit_stream_sync_fallback_and_numerical_host_branch_zero",
        "single_active_child_parent_close_gate_and_unused_child_weak_reap",
        "consume_ambiguity_release_return_loss_and_publication_interruption_fail_closed_reconciliation",
        "upstream_regular_errors_rebound_to_exact_export_cleanup_owner",
        "consumed_release_store_interruption_cannot_wedge_parent_or_reopen_export",
        "standalone_exact_type_schema_hash_and_semantic_validation",
        "expected_context_required_for_process_local_provenance_authenticity",
        "private_atomic_final_result_identity_and_exact_recurrence_policy_seal_for_downstream_observation_without_raw_receipt_change",
        "native_gfx1030_f6_m1_i1_exact_three_copies_48_48_264_total_360_bytes",
        "verification_only_cpu_payload_comparison_after_outcome_free_product_receipt_freeze",
    }.issubset(completion_export["supported_scope"])
    assert {
        "solve_record_semantics_interpreted",
        "solve_record_status_code_active_error_counter_or_metric_validation",
        "actual_terminal_outcome_host_observed",
        "authoritative_terminal_status_proven",
        "authoritative_completion_or_solution_receipt",
        "finite_or_numerical_invariant_validation",
        "numerical_parity_verified_in_product_receipt",
        "solution_ready",
        "result_ir_ready",
        "iteration_host_copy_zero_proven",
        "model_family_and_multi_architecture_cpu_hip_full_recurrence_parity",
        "asynchronous_d2h_export",
        "general_n_dof_o_n_claim",
        "kernel_speedup_claim",
        "solver_end_to_end_speedup_claim",
        "performance_or_speedup_claim",
        "process_crash_gpu_reset_or_cross_process_abandoned_owner_recovery",
        "standalone_receipt_provenance_authenticity_without_expected_context_or_signed_chain",
        "signed_promotion_evidence",
        "commercial_readiness",
        "promotion_eligible",
    }.issubset(completion_export["explicit_exclusions"])
    assert {
        "exact_three_buffer_order_extent_payload_hash_and_global_receipt_immutability",
        "single_use_repeat_and_two_thread_concurrent_export_identity",
        "pre_fence_foreign_forged_stale_and_binding_drift_zero_copy_rejection",
        "preconsume_host_staging_allocation_failure_retry_without_capability_loss",
        "copy_one_two_and_three_failure_exact_attempt_success_prefix_without_partial_publication",
        "consume_query_ambiguity_and_release_return_loss_cleanup_authority_reconciliation",
        "upstream_error_cleanup_owner_and_consumed_release_terminal_store_interruption_recovery",
        "publication_and_result_store_interruption_monotonic_recovery_without_recopy",
        "closed_context_no_result_resurrection",
        "closed_context_expected_provenance_rejects_semantically_valid_rehashed_receipt_forgery",
        "strict_schema_semantic_hash_result_immutability_and_bool_as_int_forgery_rejection",
        "fresh_parent_authority_policy_seal_toctou_and_single_store_publication_interruption_recovery",
        "native_gfx1030_exact_three_blocking_d2h_and_verification_only_cpu_payload_comparison",
    }.issubset(completion_export["verification_cases"])
    assert {
        "docs/engine-v2-hip-fgmres-completion-export-v1.md",
        "src/structural_analysis/engine_v2/assembly_backend/fgmres_completion_export_v1.py",
        "src/structural_analysis/schemas/hip_fgmres_completion_export_v1.schema.json",
        "tests/test_engine_v2_hip_fgmres_completion_export_v1.py",
        "tests/test_engine_v2_hip_fgmres_completion_export_hardware_v1.py",
    }.issubset(completion_export["evidence_paths"])
    assert (
        "completion_only_solution_record_and_residual_export"
        in global_owner["explicit_exclusions"]
    )

    assert row_ids[atomicity_index + 4] == "hip_fgmres_terminal_outcome_observation_v1"

    terminal_observation = rows["hip_fgmres_terminal_outcome_observation_v1"]
    assert terminal_observation["implementation_state"] == "implemented"
    assert terminal_observation["promotion_state"] == "contract_only"
    assert terminal_observation["claim_level"] == (
        "context_bound_exported_terminal_record_semantics_observed_non_promoting"
    )
    assert {
        "exact_final_immutable_completion_export_result_and_process_local_context_seal_required",
        "separate_observer_receipt_preserves_raw_completion_export_receipt_payload_and_hashes",
        "explicit_little_endian_192_plus_72r_solve_record_decode",
        "all_seventeen_current_terminal_termination_codes_without_invented_cancelled_status",
        "numerical_failure_stale_header_metrics_hidden_and_committed_row_prefix_only",
        "nonfailure_true_residual_payload_deterministic_tree_l2_linf_and_scaled_metric_match",
        "solution_payload_finiteness_observed_without_solution_norm_or_solution_ready_claim",
        "authoritative_terminal_record_status_with_exact_process_local_export_provenance",
        "context_required_public_receipt_validation_and_nonserialized_result_identity",
        "observer_additional_device_allocation_borrow_h2d_d2h_kernel_sync_and_fallback_zero",
        "host_observation_cost_o_f_plus_r_without_solver_o_n_claim",
        "native_gfx1030_later_column_convergence_and_active_final_guard_max_iteration_observation",
    }.issubset(terminal_observation["supported_scope"])
    assert {
        "authoritative_completion_or_solution_receipt",
        "numerical_parity_verified",
        "solution_ready",
        "result_ir_ready",
        "equilibrium_or_residual_equation_replay",
        "iteration_host_copy_zero_proven",
        "model_family_and_multi_architecture_cpu_hip_full_recurrence_parity",
        "general_n_dof_o_n_claim",
        "performance_or_speedup_claim",
        "standalone_serialized_receipt_provenance_authenticity_without_process_local_context_or_signed_chain",
        "commercial_readiness",
        "promotion_eligible",
    }.issubset(terminal_observation["explicit_exclusions"])
    assert {
        "complete_terminal_code_table_status_code_error_name_and_restart_hint_mapping",
        "exact_policy_counter_gate_flag_stagnation_divergence_and_priority_semantic_replay",
        "context_required_receipt_provenance_backend_dimension_and_source_binding_forgery_rejection",
        "native_gfx1030_two_terminal_paths_exact_three_raw_d2h_and_observer_zero_device_operations",
    }.issubset(terminal_observation["verification_cases"])
    assert {
        "docs/engine-v2-hip-fgmres-terminal-outcome-observation-v1.md",
        "src/structural_analysis/engine_v2/assembly_backend/fgmres_terminal_outcome_observation_v1.py",
        "src/structural_analysis/schemas/hip_fgmres_terminal_outcome_observation_v1.schema.json",
        "tests/test_engine_v2_hip_fgmres_terminal_outcome_observation_v1.py",
        "tests/test_engine_v2_hip_fgmres_terminal_outcome_observation_hardware_v1.py",
    }.issubset(terminal_observation["evidence_paths"])

    assert row_ids[atomicity_index + 5] == "hip_fgmres_full_device_recurrence_abi_v2"

    recurrence_v2 = rows["hip_fgmres_full_device_recurrence_abi_v2"]
    assert recurrence_v2["implementation_state"] == "in_progress"
    assert recurrence_v2["promotion_state"] == "unavailable"
    assert (
        "accepted_256_byte_transient_device_control_state_design"
        in (recurrence_v2["supported_scope"])
    )
    assert (
        "implemented_first_restart_column0_through_valid_predecessor_checkpoint_raw_numerical_slice_kept_partial"
        in (recurrence_v2["supported_scope"])
    )
    assert (
        "implemented_caller_attested_non_promoting_checkpoint_transaction_context_kept_partial"
        in recurrence_v2["supported_scope"]
    )
    assert (
        "implemented_live_krylov_parent_allocator_resource_context_kept_partial"
        in recurrence_v2["supported_scope"]
    )
    assert (
        "implemented_canonical_device_predecessor_prefix_and_mask_domain_gate_kept_partial"
        in recurrence_v2["supported_scope"]
    )
    assert (
        "implemented_raw_fixed_four_row_invalid_source_atomicity_in_exact_registered_nonoverlap_same_stream_exclusive_owner_scope_kept_partial"
        in recurrence_v2["supported_scope"]
    )
    assert (
        "authoritative_checkpoint_transaction" in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "device_validation_outcome_and_actual_mask_host_observation"
        in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "implemented_canonical_capability_consuming_live_sealed_checkpoint_transaction_kept_partial"
        in recurrence_v2["supported_scope"]
    )
    assert {
        "implemented_global_fixed_schedule_later_columns_restarts_terminal_padding_and_final_guard_raw_kernel",
        "implemented_gap_free_sealed_prefix_and_continuation_partition",
        "implemented_conditional_sealed_continuation_consuming_global_suffix_owner_kept_non_promoting",
        "implemented_process_local_parent_owned_weak_liveness_recovery_for_abandoned_consumed_or_pending_suffix_owner",
        "implemented_exact_stream_query_optional_single_checkpoint_sync_ack_and_terminal_release_recovery",
        "recovery_kept_lifecycle_only_without_terminal_numerical_completion_or_solution_promotion",
        "implemented_exact_full_final_cycle_checkpoint_to_final_guard_handoff",
        "implemented_mandatory_handoff_required_and_full_prestate_validity_separation",
        "implemented_malformed_mandatory_handoff_prepublication_fail_closed",
        "native_raw_three_restart_exhaustion_early_terminal_padding_and_final_guard_evidence",
        "native_integrated_active_later_column_and_suffix_zero_copy_one_fence_evidence",
        "native_integrated_active_later_restarts_one_through_three_evidence",
        "native_integrated_active_final_guard_full_cycle_e147_to_e148_evidence",
        "native_malformed_handoff_next_restart_and_operator_count_prepublication_evidence",
        "implemented_completion_only_solution_true_residual_and_opaque_solve_record_export_kept_outcome_uninterpreted",
        "native_gfx1030_completion_export_exact_three_blocking_d2h_360_bytes_evidence",
        "implemented_context_bound_terminal_record_observation_with_zero_additional_device_operations_kept_non_promoting",
        "native_gfx1030_later_column_convergence_and_final_guard_max_iteration_terminal_observation_evidence",
        "implemented_fixed_suffix_host_submission_control_o_l_structural_gate_not_general_n_dof_o_n",
        "implemented_registry_sealed_immutable_dispatch_snapshot_and_canonical_row_tuple",
        "final_independent_linear_reaudit_no_remaining_defect_in_requested_host_control_scope",
        "current_checkpoint_transaction_schedule_hash_sha256_0583f66e5faa848da734ff8fbcc430d8bb71ef9fc854fab49121be3f61691e5d",
        "current_global_schedule_semantic_contract_hash_sha256_7c18ba9190fef663fec8e1f87e0f56ec393e23f04d4753ffbc3c707bff1a10ea",
        "current_combined_recurrence_abi_hash_sha256_6a361ccfd0dbbe544e93b6c9ea788cc3702f6f924a969a3aa3deebf3292f315b",
        "current_fixed_source_hash_sha256_a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d",
        "native_integrated_recovery_pending_39_to_zero_query_not_ready_then_complete_sync_one_zero_product_calls",
        "independent_v0_2_25_recovery_audit_blocker_high_medium_low_zero",
    }.issubset(recurrence_v2["supported_scope"])
    assert (
        "sealed_predecessor_checkpoint_transaction_integration"
        not in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "global_atomicity_beyond_fixed_four_row_registered_nonoverlap_same_stream_exclusive_owner_scope"
        in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "later_columns_and_restarts_kernel_implementation"
        not in (recurrence_v2["explicit_exclusions"])
    )
    assert (
        "integrated_active_later_restart_execution"
        not in (recurrence_v2["explicit_exclusions"])
    )
    assert {
        "native_cpu_hip_full_recurrence_parity",
        "general_n_dof_o_n_claim",
        "process_crash_gpu_reset_or_cross_process_abandoned_owner_recovery",
        "abandoned_recovery_as_terminal_numerical_parity_completion_or_solution_evidence",
    }.issubset(recurrence_v2["explicit_exclusions"])
    assert (
        "completion_only_solution_record_and_residual_export"
        not in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "product_terminal_outcome_observation"
        not in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "integrated_active_final_guard_fallthrough"
        not in recurrence_v2["explicit_exclusions"]
    )
    assert (
        "final_independent_linear_reaudit_closure"
        not in recurrence_v2["explicit_exclusions"]
    )
    assert {
        "integrated_active_later_restart_and_active_final_guard_kept_separate_from_authoritative_outcome_claims",
        "fixed_suffix_host_control_o_l_kept_separate_from_general_n_dof_o_n_and_speedup_claims",
        "final_linear_reaudit_closed_only_requested_host_control_scope_without_product_promotion",
        "terminal_outcome_observer_kept_separate_from_completion_solution_parity_result_ir_and_promotion_claims",
        "process_local_abandoned_suffix_owner_recovery_kept_separate_from_numerical_completion_claim",
        "native_integrated_recovery_lifecycle_gate_kept_separate_from_full_recurrence_parity_and_solution",
    }.issubset(recurrence_v2["verification_cases"])
    assert "iteration_host_copy_zero" in recurrence_v2["explicit_exclusions"]
    assert "commercial_readiness" in recurrence_v2["explicit_exclusions"]


def test_nonconverged_diagnostic_ir_v1_claims_stay_diagnostic_only() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = {row["capability_id"]: row for row in payload["rows"]}

    diagnostic = rows["hip_fgmres_nonconverged_diagnostic_ir_v1"]
    assert payload["rows"][4]["capability_id"] == (
        "hip_fgmres_nonconverged_diagnostic_ir_v1"
    )
    assert diagnostic["implementation_state"] == "implemented"
    assert diagnostic["promotion_state"] == "contract_only"
    assert {
        "exact_fixed_registry_three_intentional_max_iterations_cases",
        "hip_source_bound_v1_provenance_with_backend_independent_numeric_replay",
        "descriptor_only_diagnostic_ir_v1_three_immutable_arrays",
        "public_generic_builder_diagnostic_ready_and_raw_source_preservation_claims_false",
        "private_process_local_exact_object_bridge_ready_issuer_after_second_live_capture",
        "ready_identity_lost_by_replace_copy_direct_construction_coherent_rehash_and_detached_manifest",
        "canonical_initial_accepted_state_evaluated_trial_and_exact_rollback_without_commit",
        "raw_solution_true_residual_and_solve_record_payload_hashes_separate_from_canonical_array_hashes",
        "post_close_detached_raw_solve_record_decode_sparse_physics_state_and_issuance_validation",
        "v0244_seven_ready_result_ir_v2_three_not_issued_nonconverged_truth_table_preserved",
        "diagnostic_totals_g72_e9_f54_nnz1080",
        "three_array_categories_across_three_slots_nine_arrays_aggregate_1584_bytes",
        "detached_raw_payload_1872_bytes",
        "retained_source_factory_direct_call_projection_additional_device_d2h_solve_export_fallback_and_state_commit_literal_zero_contract",
        "current_source_actual_local_gfx1030_integrated_ten_slot_three_diagnostic_ir_v1_bridges_family_exact_seven_result_ir_v2_three_diagnostic_ir_v1_totals_projection_and_commit_zero_post_close_validated_without_cpu_fallback",
    }.issubset(diagnostic["supported_scope"])
    assert {
        "public_generic_ready_and_raw_source_claims_false",
        "private_ready_issuer_absent_from_all_public_exports",
        "coherent_ready_rehash_replace_copy_deepcopy_direct_and_standalone_manifest_rejected",
        "retained_source_factory_direct_call_projection_operation_literal_zero_guards_and_fixed_false_claims",
        "generic_diagnostic_contract_tests_14_passed",
        "hip_diagnostic_bridge_tests_13_passed",
        "family_diagnostic_companion_tests_12_passed",
        "public_api_tests_3_passed",
        "capability_matrix_tests_9_passed",
        "adjacent_v0243_v0244_v0245_integrated_tests_138_passed",
        "hardware_harness_one_test_collected",
        "current_source_execution_aggregate_sha256_5a977e48c7735b694e4b76752494c92bea89f69fb74c3bcb738a5a36b722b6cc",
        "current_source_hardware_harness_sha256_3b0acb3ab1af894f5ef099c227614b54983f51857c1dce08e0def9977df00bde",
        "current_source_sealed_harness_sha256_660806190c2ba8b6b9a436126082f047881646ef413811760a771df9ddf11693",
        "nonrequired_hardware_gate_1_skipped_without_real_gfx_agent",
        "required_hardware_gate_1_failed_not_skipped_without_real_gfx_agent",
        "current_source_actual_local_gfx1030_integrated_ten_slot_three_diagnostic_ir_v1_bridges_family_exact_seven_result_ir_v2_three_diagnostic_ir_v1_totals_projection_and_commit_zero_post_close_gate_1_passed_in_7820_35_seconds_without_cpu_fallback",
    }.issubset(diagnostic["verification_cases"])
    assert {
        "hostile_same_process_security_boundary",
        "transitive_or_process_wide_projection_operation_instrumentation",
        "nonconverged_partial_iterate_solution_ready",
        "nonconverged_result_ir_v2",
        "nonconverged_state_commit",
        "restart_checkpoint_eligibility",
        "reaction_recovery",
        "member_force_recovery",
        "energy_recovery",
        "code_check_consumption",
        "design_or_optimization_consumption",
        "all_converged_fixture_registry",
        "exact_package_all_ten_result_ir_v2_ready",
        "standalone_detached_or_serialized_provenance_authenticity",
        "end_to_end_o_n",
        "performance_speedup",
        "commercial_readiness",
    }.issubset(diagnostic["explicit_exclusions"])
    assert diagnostic["required_contracts"] == [
        "ADR-001",
        "ADR-002",
        "ADR-003",
        "ADR-004",
        "ADR-006",
        "ADR-007",
    ]
    assert diagnostic["claim_level"] == (
        "current_source_actual_local_gfx1030_integrated_ten_slot_three_"
        "nonconverged_partial_iterate_diagnostic_ir_v1_family_post_close_"
        "validated_contract_only_unsigned_nonpersistent_detached_"
        "non_provenance_nonpromoting"
    )
